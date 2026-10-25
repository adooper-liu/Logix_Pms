"""问题驱动的工具匹配。

文本/同义词复用 `tool_finder.score_text`，这里补上：
  - 场景命中（复用 knowledge_scenario 字典）；
  - 使用证据（Wilson 下界）；
  - 适配度归一化与「为什么推荐」。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import KnowledgeStatus, ToolStatus
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeScenario,
    KnowledgeUsage,
)
from app.models.project import WorkflowTemplate
from app.models.tool import Tool, ToolScenarioLink, ToolUsage
from app.schemas.tool import (
    ToolMatchHit,
    ToolOut,
    ToolUsageSummary,
)
from app.services import knowledge_match, tool_finder
from app.services.scoring import wilson_lower_bound

DIFFICULTY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
MAX_TEXT_SCORE = 8.0
SCENARIO_WEIGHT = 3.0
EVIDENCE_WEIGHT = 2.0
VERIFIED_WEIGHT = 0.3
OVERDUE_PENALTY = 0.5

HINT = (
    "适配度按「问题匹配 + 场景 + 使用证据」计算，四象限只用于辅助筛选。"
    "先描述一个最突出的问题，比一次勾选全部工具更容易得到有用的结果。"
)


def _tool_query():
    return (
        select(Tool)
        .options(
            selectinload(Tool.scenario_rows).selectinload(ToolScenarioLink.scenario),
            selectinload(Tool.owner_user),
        )
        .where(
            Tool.is_active.is_(True),
            Tool.status.in_((ToolStatus.PUBLISHED.value, ToolStatus.VERIFIED.value)),
        )
        .order_by(Tool.category, Tool.sort_order)
    )


def load_tools(db: Session) -> List[Tool]:
    return list(db.scalars(_tool_query()).all())


def tool_usage(db: Session, codes: Sequence[str]) -> Dict[str, Tuple[int, int, Optional[float]]]:
    """工具使用证据 = 关联知识条目的使用记录 + 工具自身的现场使用记录。"""
    if not codes:
        return {}
    totals: Dict[str, List[int]] = {}

    knowledge_rows = db.execute(
        select(
            KnowledgeItem.tool_code,
            func.count(KnowledgeUsage.id),
            func.sum(case((KnowledgeUsage.outcome == "EFFECTIVE", 1), else_=0)),
        )
        .join(KnowledgeUsage, KnowledgeUsage.knowledge_id == KnowledgeItem.id)
        .where(
            KnowledgeItem.tool_code.in_(list(codes)),
            KnowledgeItem.status.in_(
                (KnowledgeStatus.PUBLISHED.value, KnowledgeStatus.VERIFIED.value)
            ),
        )
        .group_by(KnowledgeItem.tool_code)
    ).all()
    for code, used, effective in knowledge_rows:
        bucket = totals.setdefault(code, [0, 0])
        bucket[0] += int(used or 0)
        bucket[1] += int(effective or 0)

    direct_rows = db.execute(
        select(
            ToolUsage.tool_code,
            func.count(ToolUsage.id),
            func.sum(case((ToolUsage.outcome == "EFFECTIVE", 1), else_=0)),
        )
        .where(ToolUsage.tool_code.in_(list(codes)))
        .group_by(ToolUsage.tool_code)
    ).all()
    for code, used, effective in direct_rows:
        bucket = totals.setdefault(code, [0, 0])
        bucket[0] += int(used or 0)
        bucket[1] += int(effective or 0)

    return {
        code: (used, effective, round(effective / used * 100, 1) if used else None)
        for code, (used, effective) in totals.items()
    }


def _stage_for_step(db: Session, step_no: Optional[str]) -> Optional[int]:
    if not step_no:
        return None
    return db.scalar(select(WorkflowTemplate.stage_no).where(WorkflowTemplate.step_no == step_no))


def _duration_days(text: Optional[str]) -> int:
    """把「3 天 / 2–3 周 / 持续」粗排成天数，仅用于排序。"""
    if not text:
        return 3650
    if "持续" in text:
        return 3650
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    if not numbers:
        return 3650
    value = max(numbers)
    if "月" in text:
        return value * 30
    if "周" in text:
        return value * 7
    return value


def _is_overdue(tool: Tool) -> bool:
    return tool.review_overdue


def match_tools(
    db: Session,
    problem: Optional[str],
    scenario_codes: Optional[Sequence[str]] = None,
    category_filters: Optional[Sequence[str]] = None,
    stage_no: Optional[int] = None,
    step_no: Optional[str] = None,
    sort: str = "fit",
    limit: int = 8,
) -> List[ToolMatchHit]:
    problem = (problem or "").strip()
    scenario_codes = [code for code in (scenario_codes or []) if code]
    categories = set(category_filters or [])
    resolved_stage = stage_no or _stage_for_step(db, step_no)

    tools = load_tools(db)
    if categories:
        tools = [tool for tool in tools if tool.category in categories]
    if resolved_stage and not problem and not scenario_codes:
        # 只按阶段进入（如从工作流阶段点过来）时，先收窄到该阶段的主要工具
        staged = [tool for tool in tools if tool.stage_no == resolved_stage]
        if staged:
            tools = staged
    if not tools:
        return []

    usage = tool_usage(db, [tool.code for tool in tools])
    knowledge_counts = knowledge_match.knowledge_counts_by_tool(db, [tool.code for tool in tools])
    # 只选了场景、没有自由文本时，用场景名称/说明作为「伪问题」，
    # 让工具自身的 purpose/when_to_use 也参与匹配，避免同一场景下全部同分。
    scenario_text = ""
    if not problem and scenario_codes:
        rows = db.scalars(
            select(KnowledgeScenario).where(KnowledgeScenario.code.in_(scenario_codes))
        ).all()
        scenario_text = " ".join(f"{row.name} {row.description or ''}" for row in rows).strip()
    effective_problem = problem or scenario_text

    scored = []
    for tool in tools:
        text_score, matched_on = tool_finder.score_text(tool, effective_problem, resolved_stage)
        relevance = min(text_score, MAX_TEXT_SCORE)

        tool_scenarios = set(tool.scenario_codes)
        scenario_names = {
            row.scenario.code: row.scenario.name
            for row in tool.scenario_rows
            if row.scenario is not None
        }
        hit_scenarios = [code for code in scenario_codes if code in tool_scenarios]
        relevance += SCENARIO_WEIGHT * min(len(hit_scenarios), 2)
        for code in hit_scenarios:
            matched_on.append(f"场景：{scenario_names.get(code, code)}")

        # 用户明确提了问题/场景时，只用证据分硬凑结果会误导；必须先有相关性
        if (problem or scenario_codes) and relevance <= 0:
            continue

        used, effective, rate = usage.get(tool.code, (0, 0, None))
        raw = relevance
        raw += EVIDENCE_WEIGHT * wilson_lower_bound(effective, used)
        if tool.last_verified_at is not None:
            raw += VERIFIED_WEIGHT
        if _is_overdue(tool):
            raw -= OVERDUE_PENALTY

        scored.append(
            {
                "tool": tool,
                "raw": raw,
                "matched_on": matched_on,
                "usage": (used, effective, rate),
            }
        )

    if not scored:
        return []

    if sort == "difficulty":
        scored.sort(
            key=lambda row: (
                DIFFICULTY_ORDER.get(row["tool"].difficulty, 9),
                -row["raw"],
            )
        )
    elif sort == "duration":
        scored.sort(key=lambda row: (_duration_days(row["tool"].typical_duration), -row["raw"]))
    elif sort == "usage":
        scored.sort(key=lambda row: (-row["usage"][0], -row["raw"]))
    else:
        scored.sort(
            key=lambda row: (
                -row["raw"],
                DIFFICULTY_ORDER.get(row["tool"].difficulty, 9),
                row["tool"].sort_order,
            )
        )

    top = scored[0]["raw"] or 1.0
    hits: List[ToolMatchHit] = []
    for row in scored[:limit]:
        tool = row["tool"]
        used, effective, rate = row["usage"]
        ratio = max(0.0, min(99.0, round(row["raw"] / top * 99, 1)))
        level = "high" if ratio >= 85 else "mid" if ratio >= 65 else "low"
        hits.append(
            ToolMatchHit(
                tool=ToolOut.model_validate(tool).model_copy(
                    update={"knowledge_count": knowledge_counts.get(tool.code, 0)}
                ),
                score=ratio,
                match_level=level,
                matched_on=sorted(set(row["matched_on"])),
                why=tool.purpose,
                verification_standard=tool.verification_standard,
                usage=ToolUsageSummary(used=used, effective=effective, rate=rate),
            )
        )
    return hits
