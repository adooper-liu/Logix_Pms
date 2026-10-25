"""场景驱动的知识推荐。

推荐依据不是浏览量，而是：
  1. 场景命中（用户选择的痛点）；
  2. 文本命中（自由描述的问题）；
  3. 工作流位置（阶段/步骤）；
  4. 使用证据（Wilson 下界，避免小样本 100% 排到最前）；
  5. 审核状态（已验证 / 最佳实践）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.enums import KnowledgeStatus
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeScenario,
    KnowledgeScenarioLink,
    KnowledgeUsage,
    KnowledgeWorkflowLink,
)
from app.schemas.knowledge import (
    KnowledgeArchiveCandidateOut,
    KnowledgeEffectItemOut,
    KnowledgeEffectStatsOut,
    KnowledgeRecommendationOut,
    KnowledgeScenarioOut,
    KnowledgeTypeEffectOut,
)
from app.services.scoring import wilson_lower_bound
from app.services.text_match import tokens

TYPE_LABELS = {
    "CASE": "案例",
    "TEMPLATE": "模板",
    "METHOD": "方法",
    "TOOL": "工具",
    "BEST_PRACTICE": "方法",  # 旧数据兼容：最佳实践已改为标志位
    "STANDARD": "制度",
}

STATUS_LABELS = {
    KnowledgeStatus.DRAFT.value: "草稿",
    KnowledgeStatus.IN_REVIEW.value: "待审核",
    KnowledgeStatus.PUBLISHED.value: "待复核",
    KnowledgeStatus.VERIFIED.value: "已验证",
    KnowledgeStatus.ARCHIVED.value: "已归档",
}

OUTCOME_LABELS = {
    "EFFECTIVE": "有效",
    "PARTIAL": "部分有效",
    "INEFFECTIVE": "无效",
}

VISIBLE_STATUSES = (KnowledgeStatus.PUBLISHED.value, KnowledgeStatus.VERIFIED.value)

HINT = (
    "推荐按「场景匹配 + 使用证据 + 工作流位置」排序，浏览量不参与排序。"
    "先选一个最突出的痛点，比一次勾选全部场景更容易得到有用的结果。"
)

# 各分项上限之和，用于把原始分归一化到 0–100
_MAX_RAW = 14.6


def scenario_list(db: Session) -> List[KnowledgeScenarioOut]:
    rows = db.scalars(
        select(KnowledgeScenario)
        .where(KnowledgeScenario.is_active.is_(True))
        .order_by(KnowledgeScenario.sort_order, KnowledgeScenario.id)
    ).all()
    return [
        KnowledgeScenarioOut(
            id=row.id,
            code=row.code,
            name=row.name,
            description=row.description,
            sort_order=row.sort_order,
        )
        for row in rows
    ]


def effectiveness_stats(
    db: Session, knowledge_ids: Sequence[int]
) -> Dict[int, Tuple[int, int, Optional[float]]]:
    """返回 {knowledge_id: (used, effective, rate)}，一次聚合完成。"""
    if not knowledge_ids:
        return {}
    rows = db.execute(
        select(
            KnowledgeUsage.knowledge_id,
            func.count(KnowledgeUsage.id),
            func.sum(case((KnowledgeUsage.outcome == "EFFECTIVE", 1), else_=0)),
        )
        .where(KnowledgeUsage.knowledge_id.in_(knowledge_ids))
        .group_by(KnowledgeUsage.knowledge_id)
    ).all()
    result: Dict[int, Tuple[int, int, Optional[float]]] = {}
    for kid, used, effective in rows:
        used = int(used or 0)
        effective = int(effective or 0)
        rate = round(effective / used * 100, 1) if used else None
        result[kid] = (used, effective, rate)
    return result


def _item_scenarios(item: KnowledgeItem) -> List[KnowledgeScenarioOut]:
    return [
        KnowledgeScenarioOut(
            id=row.scenario.id,
            code=row.scenario.code,
            name=row.scenario.name,
            description=row.scenario.description,
            sort_order=row.scenario.sort_order,
        )
        for row in item.scenario_rows
        if row.scenario is not None
    ]


def review_overdue(item: KnowledgeItem) -> bool:
    """待复核：过了复核日期，或从未验证过（仅对已发布条目）。"""
    if item.review_due_at is None:
        return item.last_verified_at is None and item.status == KnowledgeStatus.PUBLISHED.value
    return item.review_due_at < date.today()


def _score(
    item: KnowledgeItem,
    problem: str,
    scenario_codes: Sequence[str],
    stage_no: Optional[int],
    step_no: Optional[str],
    stats: Tuple[int, int, Optional[float]],
) -> Tuple[float, List[str], List[str]]:
    score = 0.0
    matched_on: List[str] = []
    hit_scenarios: List[str] = []

    item_codes = {row.scenario.code for row in item.scenario_rows if row.scenario}
    for code in scenario_codes:
        if code in item_codes:
            score += 3.0
            hit_scenarios.append(code)

    if problem:
        haystack = " ".join(
            filter(
                None,
                [
                    item.title,
                    item.summary,
                    item.claim or "",
                    item.applicable_when or "",
                    item.not_applicable_when or "",
                    item.content,
                ],
            )
        )
        for token in tokens(problem):
            if token and token in haystack:
                score += 1.0
                matched_on.append(token)

    linked_steps = {row.step_no for row in item.workflow_links if row.step_no}
    linked_stages = {row.stage_no for row in item.workflow_links}
    if step_no and step_no in linked_steps:
        score += 2.0
        matched_on.append(f"步骤 {step_no}")
    elif stage_no and stage_no in linked_stages:
        score += 1.0
        matched_on.append(f"阶段 {stage_no}")

    if item.status == KnowledgeStatus.VERIFIED.value:
        score += 0.8
    if item.is_best_practice:
        score += 0.8

    used, effective, _rate = stats
    score += 2.0 * wilson_lower_bound(effective, used)

    if review_overdue(item):
        score -= 1.0

    return score, matched_on, hit_scenarios


def _to_recommendation(
    item: KnowledgeItem,
    score: float,
    matched_on: List[str],
    hit_scenarios: List[str],
    stats: Tuple[int, int, Optional[float]],
) -> KnowledgeRecommendationOut:
    used, effective, rate = stats
    normalized = max(0.0, min(99.0, round(score / _MAX_RAW * 100, 1)))
    level = "high" if normalized >= 70 else "mid" if normalized >= 45 else "low"
    scenarios = [s for s in _item_scenarios(item) if s.code in hit_scenarios] or _item_scenarios(
        item
    )
    reason = [f"场景：{s.name}" for s in scenarios if s.code in hit_scenarios] + matched_on
    return KnowledgeRecommendationOut(
        kind="knowledge",
        id=item.id,
        title=item.title,
        type=item.type,
        type_label=TYPE_LABELS.get(item.type, item.type),
        status=item.status,
        status_label=STATUS_LABELS.get(item.status, item.status),
        summary=item.summary,
        score=normalized,
        match_level=level,
        matched_on=reason,
        scenarios=scenarios,
        claim=item.claim,
        applicable_when=item.applicable_when,
        not_applicable_when=item.not_applicable_when,
        owner=item.author,
        tool_code=item.tool_code,
        is_best_practice=item.is_best_practice,
        last_verified_at=item.last_verified_at,
        review_overdue=review_overdue(item),
        used_count=used,
        effective_count=effective,
        effectiveness_rate=rate,
    )


def _visible_query():
    return (
        select(KnowledgeItem)
        .options(
            selectinload(KnowledgeItem.scenario_rows).selectinload(KnowledgeScenarioLink.scenario),
            selectinload(KnowledgeItem.workflow_links),
        )
        .where(
            KnowledgeItem.status.in_(VISIBLE_STATUSES),
            KnowledgeItem.type != "STANDARD",
        )
    )


def recommend(
    db: Session,
    problem: Optional[str] = None,
    scenario_codes: Optional[Sequence[str]] = None,
    stage_no: Optional[int] = None,
    step_no: Optional[str] = None,
    limit: int = 6,
) -> List[KnowledgeRecommendationOut]:
    problem = (problem or "").strip()
    scenario_codes = [code for code in (scenario_codes or []) if code]
    items = list(db.scalars(_visible_query().limit(500)).all())
    if not items:
        return []
    stats = effectiveness_stats(db, [item.id for item in items])
    scored = []
    for item in items:
        score, matched_on, hit_scenarios = _score(
            item,
            problem,
            scenario_codes,
            stage_no,
            step_no,
            stats.get(item.id, (0, 0, None)),
        )
        if not problem and not scenario_codes and not stage_no and not step_no:
            # 没有任何查询条件时，按证据和验证状态做默认推荐
            used, effective, _ = stats.get(item.id, (0, 0, None))
            score = item.is_best_practice * 1.0 + wilson_lower_bound(effective, used) * 2.0
        scored.append((score, item, matched_on, hit_scenarios))
    scored.sort(
        key=lambda row: (
            -row[0],
            -int(row[1].is_best_practice),
            -row[1].download_count,
            row[1].title,
        )
    )
    return [
        _to_recommendation(item, score, matched_on, hit_scenarios, stats.get(item.id, (0, 0, None)))
        for score, item, matched_on, hit_scenarios in scored[:limit]
    ]


def recommend_for_step(
    db: Session, stage_no: int, step_no: str, limit: int = 3
) -> List[KnowledgeRecommendationOut]:
    """工作流步骤弹窗用：只返回明确挂到该步骤/阶段的知识。"""
    linked_ids = set(
        db.scalars(
            select(KnowledgeWorkflowLink.knowledge_id).where(
                (KnowledgeWorkflowLink.step_no == step_no)
                | (
                    (KnowledgeWorkflowLink.stage_no == stage_no)
                    & (KnowledgeWorkflowLink.step_no == "")
                )
            )
        ).all()
    )
    if not linked_ids:
        return []
    items = list(
        db.scalars(_visible_query().where(KnowledgeItem.id.in_(linked_ids)).limit(100)).all()
    )
    stats = effectiveness_stats(db, [item.id for item in items])
    scored = []
    for item in items:
        score, matched_on, hit_scenarios = _score(
            item, "", [], stage_no, step_no, stats.get(item.id, (0, 0, None))
        )
        scored.append((score, item, matched_on, hit_scenarios))
    scored.sort(key=lambda row: (-row[0], -int(row[1].is_best_practice), row[1].title))
    return [
        _to_recommendation(item, score, matched_on, hit_scenarios, stats.get(item.id, (0, 0, None)))
        for score, item, matched_on, hit_scenarios in scored[:limit]
    ]


def step_counts(db: Session, steps: Iterable[Tuple[int, str]]) -> Dict[Tuple[int, str], int]:
    """每个步骤可推荐的知识数：步骤级 + 阶段级，按知识去重。

    与 `recommend_for_step` 的口径保持一致，供步骤清单卡片显示「推荐知识 N」。
    """
    rows = db.execute(
        select(
            KnowledgeWorkflowLink.stage_no,
            KnowledgeWorkflowLink.step_no,
            KnowledgeWorkflowLink.knowledge_id,
        )
        .join(KnowledgeItem, KnowledgeItem.id == KnowledgeWorkflowLink.knowledge_id)
        .where(
            KnowledgeItem.status.in_(VISIBLE_STATUSES),
            KnowledgeItem.type != "STANDARD",
        )
    ).all()
    stage_ids: Dict[int, set] = {}
    step_ids: Dict[Tuple[int, str], set] = {}
    for stage_no, step_no, knowledge_id in rows:
        if step_no:
            step_ids.setdefault((stage_no, step_no), set()).add(knowledge_id)
        else:
            stage_ids.setdefault(stage_no, set()).add(knowledge_id)

    return {
        (stage_no, step_no): len(
            step_ids.get((stage_no, step_no), set()) | stage_ids.get(stage_no, set())
        )
        for stage_no, step_no in steps
    }


def knowledge_counts_by_tool(db: Session, codes: Iterable[str]) -> Dict[str, int]:
    """每个工具关联的公开知识数（不含 STANDARD，和详情页列表口径一致）。"""
    wanted = {code for code in codes if code}
    if not wanted:
        return {}
    rows = db.execute(
        select(KnowledgeItem.tool_code, func.count(KnowledgeItem.id))
        .where(
            KnowledgeItem.tool_code.in_(wanted),
            KnowledgeItem.status.in_(VISIBLE_STATUSES),
            KnowledgeItem.type != "STANDARD",
        )
        .group_by(KnowledgeItem.tool_code)
    ).all()
    return {code: int(count) for code, count in rows}


def stage_counts(db: Session, stage_nos: Iterable[int]) -> Dict[int, int]:
    """每个阶段可推荐的知识数（阶段级 + 该阶段下所有步骤级，按知识去重）。"""
    wanted = set(stage_nos)
    if not wanted:
        return {}
    rows = db.execute(
        select(KnowledgeWorkflowLink.stage_no, KnowledgeWorkflowLink.knowledge_id)
        .join(KnowledgeItem, KnowledgeItem.id == KnowledgeWorkflowLink.knowledge_id)
        .where(
            KnowledgeItem.status.in_(VISIBLE_STATUSES),
            KnowledgeItem.type != "STANDARD",
            KnowledgeWorkflowLink.stage_no.in_(wanted),
        )
    ).all()
    buckets: Dict[int, set] = {}
    for stage_no, knowledge_id in rows:
        buckets.setdefault(stage_no, set()).add(knowledge_id)
    return {stage_no: len(ids) for stage_no, ids in buckets.items()}


def archive_candidates(
    db: Session, months: int = 12, limit: int = 50
) -> List[KnowledgeArchiveCandidateOut]:
    """超过 `months` 个月没有使用证据的公开知识，供 Manager 确认归档。

    只统计「最近一次使用」而不是浏览量；从未使用过的条目以创建时间为准，
    避免因为改过一次错别字就被重新计时。
    """
    cutoff = utcnow() - timedelta(days=months * 30)
    items = list(db.scalars(_visible_query()).all())
    if not items:
        return []
    last_used = dict(
        db.execute(
            select(KnowledgeUsage.knowledge_id, func.max(KnowledgeUsage.used_at))
            .where(KnowledgeUsage.knowledge_id.in_([item.id for item in items]))
            .group_by(KnowledgeUsage.knowledge_id)
        ).all()
    )
    stats = effectiveness_stats(db, [item.id for item in items])
    candidates: List[Tuple[datetime, KnowledgeArchiveCandidateOut]] = []
    for item in items:
        last = last_used.get(item.id)
        baseline = last or item.created_at
        if baseline is None or baseline >= cutoff:
            continue
        unused_days = max(0, (utcnow() - baseline).days)
        brief = to_brief(item, stats.get(item.id, (0, 0, None)))
        candidates.append(
            (
                baseline,
                KnowledgeArchiveCandidateOut(
                    **brief.model_dump(),
                    last_used_at=last,
                    unused_days=unused_days,
                ),
            )
        )
    candidates.sort(key=lambda row: row[0])
    return [row for _baseline, row in candidates[:limit]]


def effect_stats(db: Session) -> KnowledgeEffectStatsOut:
    """全局使用效果：按结果、类型和条目聚合，供运营面板使用。"""
    visible = (
        KnowledgeItem.status.in_(VISIBLE_STATUSES),
        KnowledgeItem.type != "STANDARD",
    )
    rows = db.execute(
        select(
            KnowledgeItem.type,
            KnowledgeUsage.outcome,
            func.count(KnowledgeUsage.id),
        )
        .join(KnowledgeItem, KnowledgeItem.id == KnowledgeUsage.knowledge_id)
        .where(*visible)
        .group_by(KnowledgeItem.type, KnowledgeUsage.outcome)
    ).all()

    outcomes: Dict[str, int] = {"EFFECTIVE": 0, "PARTIAL": 0, "INEFFECTIVE": 0}
    by_type: Dict[str, Dict[str, int]] = {}
    for item_type, outcome, count in rows:
        outcomes[outcome] = outcomes.get(outcome, 0) + int(count)
        bucket = by_type.setdefault(item_type, {"used": 0, "effective": 0})
        bucket["used"] += int(count)
        if outcome == "EFFECTIVE":
            bucket["effective"] += int(count)

    used_total = sum(outcomes.values())
    effective_total = outcomes.get("EFFECTIVE", 0)
    type_rows = [
        KnowledgeTypeEffectOut(
            type=item_type,
            type_label=TYPE_LABELS.get(item_type, item_type),
            used_count=bucket["used"],
            effective_count=bucket["effective"],
            effectiveness_rate=_rate(bucket["effective"], bucket["used"]),
        )
        for item_type, bucket in by_type.items()
    ]
    type_rows.sort(key=lambda row: (-row.used_count, row.type))

    top = db.execute(
        select(
            KnowledgeItem.id,
            KnowledgeItem.title,
            KnowledgeItem.type,
            func.count(KnowledgeUsage.id).label("used"),
            func.sum(case((KnowledgeUsage.outcome == "EFFECTIVE", 1), else_=0)).label("effective"),
        )
        .join(KnowledgeUsage, KnowledgeUsage.knowledge_id == KnowledgeItem.id)
        .where(*visible)
        .group_by(KnowledgeItem.id, KnowledgeItem.title, KnowledgeItem.type)
        .order_by(
            func.sum(case((KnowledgeUsage.outcome == "EFFECTIVE", 1), else_=0)).desc(),
            func.count(KnowledgeUsage.id).desc(),
            KnowledgeItem.id.desc(),
        )
        .limit(5)
    ).all()

    return KnowledgeEffectStatsOut(
        usage_total=used_total,
        effective_count=effective_total,
        partial_count=outcomes.get("PARTIAL", 0),
        ineffective_count=outcomes.get("INEFFECTIVE", 0),
        effectiveness_rate=_rate(effective_total, used_total),
        by_type=type_rows,
        top_items=[
            KnowledgeEffectItemOut(
                id=item_id,
                title=title,
                type=item_type,
                type_label=TYPE_LABELS.get(item_type, item_type),
                used_count=int(used),
                effective_count=int(effective or 0),
                effectiveness_rate=_rate(int(effective or 0), int(used)),
            )
            for item_id, title, item_type, used, effective in top
        ],
    )


def _rate(effective: int, used: int) -> Optional[float]:
    return round(effective / used * 100, 1) if used else None


def to_brief(item: KnowledgeItem, stats: Tuple[int, int, Optional[float]]):
    """把 ORM 条目转成列表卡片用的简要结构。"""
    from app.schemas.knowledge import KnowledgeBrief

    used, effective, rate = stats
    return KnowledgeBrief(
        id=item.id,
        title=item.title,
        type=item.type,
        type_label=TYPE_LABELS.get(item.type, item.type),
        status=item.status,
        status_label=STATUS_LABELS.get(item.status, item.status),
        methodology=item.methodology,
        tags=item.tags,
        scenario_codes=item.scenario_codes,
        scenario_names=item.scenario_names,
        stage_nos=item.stage_nos,
        summary=item.summary,
        claim=item.claim,
        applicable_when=item.applicable_when,
        not_applicable_when=item.not_applicable_when,
        owner=item.author,
        version=item.version,
        is_best_practice=item.is_best_practice,
        last_verified_at=item.last_verified_at,
        review_due_at=item.review_due_at,
        review_overdue=review_overdue(item),
        used_count=used,
        effective_count=effective,
        effectiveness_rate=rate,
        download_count=item.download_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def to_out(item: KnowledgeItem, stats: Tuple[int, int, Optional[float]]):
    """把 ORM 条目转成详情结构。"""
    from app.schemas.knowledge import KnowledgeOut

    used, effective, rate = stats
    return KnowledgeOut(
        id=item.id,
        title=item.title,
        type=item.type,
        type_label=TYPE_LABELS.get(item.type, item.type),
        status=item.status,
        status_label=STATUS_LABELS.get(item.status, item.status),
        methodology=item.methodology,
        tags=item.tags,
        scenario_codes=item.scenario_codes,
        scenario_names=item.scenario_names,
        stage_nos=item.stage_nos,
        step_nos=item.step_nos,
        summary=item.summary,
        content=item.content,
        claim=item.claim,
        applicable_when=item.applicable_when,
        not_applicable_when=item.not_applicable_when,
        input_conditions=item.input_conditions,
        steps_summary=item.steps_summary,
        outputs=item.outputs,
        evidence_summary=item.evidence_summary,
        process_id=item.process_id,
        project_id=item.project_id,
        tool_code=item.tool_code,
        author=item.author,
        owner=item.author,
        owner_user_id=item.owner_user_id,
        verified_by=item.verified_by.display_name if item.verified_by else None,
        version=item.version,
        is_best_practice=item.is_best_practice,
        last_verified_at=item.last_verified_at,
        review_due_at=item.review_due_at,
        review_overdue=review_overdue(item),
        used_count=used,
        effective_count=effective,
        effectiveness_rate=rate,
        download_count=item.download_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def used_count_map(db: Session, ids: Iterable[int]) -> Dict[int, Tuple[int, int, Optional[float]]]:
    return effectiveness_stats(db, list(ids))
