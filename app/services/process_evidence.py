"""单流程证据计数：十层退出门专用。

与开始使用的全公司计数拆开：
- 开始使用：公司流程地图的框架边界（哪些工作进图、上下级、PCF、谁能改图）
- 十层核对：这一条流程会不会跑（起止、活动、工时、指标是否绑到本流程）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.adoption import (
    ProcessCase,
    ProcessTechnologyUse,
    ProcessTrainingRecord,
    RpaBot,
    RpaRun,
)
from app.models.authorization import AuthorizationException, AuthorizationRule
from app.models.benchmark import ProcessBenchmarkMap
from app.models.change import ProcessChangeRequest
from app.models.enums import ChangeStatus, WorkMeasurementStatus
from app.models.execution import FormDefinition, ProcessRule
from app.models.governance import GovernanceFinding
from app.models.integration import IntegrationEndpoint
from app.models.monitor import KpiDefinition
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.raci import RaciAssignment
from app.models.startup import ProcessCharter
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.services import authorization as authorization_service
from app.services import kpi as kpi_service
from app.services import process_document as document_service
from app.services import process_mining
from app.services import raci as raci_service
from app.services import workload as workload_service

# 十层上展示的本流程口径标签（键仍与公司证据对齐，避免两套键名）
PROCESS_EVIDENCE_LABELS: Dict[str, str] = {
    "objectives": "本流程已挂年度目标",
    "linked_objectives": "本流程已挂目标",
    "objectives_with_owner": "本流程目标有责任人和目标值",
    "objectives_with_baseline": "本流程目标有现状基线",
    "objective_complete": "本流程同一条目标具备责任人、目标值和基线",
    "l1": "本流程上溯有 L1",
    "l2": "本流程上溯有 L2",
    "l3": "本流程落在 L3（或上溯有 L3）",
    "process_charters": "本流程写全起止和范围",
    "pcf_mapped_l3": "本流程 L3 已对标 PCF",
    "benchmark_maps": "本流程有对标映射",
    "positions": "岗位主数据",
    "raci_matters": "本流程关键事项 RACI",
    "invalid_processes": "本流程权责冲突（应为 0）",
    "documents": "本流程制度/SOP",
    "effective_documents": "本流程已生效制度/SOP",
    "effective_authorization_rules": "本流程生效授权规则",
    "open_authorization_exceptions": "本流程未闭环授权例外",
    "l3_published": "本流程 L3 已发布模型",
    "bindings": "本流程表单/规则/工具绑定（方法工具可选）",
    "forms": "本流程表单",
    "rules": "本流程规则",
    "node_tools": "本流程方法工具绑定（设计证据，可选）",
    "verified_standards": "本流程已验证标准工时",
    "capacity_rows": "当月产能记录",
    "actual_worklogs": "实际工时记录",
    "kpi_monitored": "本流程同一张 KPI 具备公式、阈值、责任人和数据点",
    "kpi_cards": "本流程完整 KPI 卡",
    "kpi_records": "本流程 KPI 数据点",
    "mining_variants": "本流程已挖出的路径变体（执行实例或记入的日志）",
    "rpa_bots": "本流程已登记的机器人",
    "rpa_runs": "本流程已记下、并挂了集成端点的机器人运行",
    "process_cases": "本流程已登记的案例",
    "technology_uses": "本流程已登记的区块链、人工智能或物联网用途",
    "training_records": "本流程培训到场，或已应用变更上写明的培训说明",
    "red_yellow": "本流程红/黄指标",
    "improvement_projects": "本流程改善项目",
    "applied_changes": "本流程已应用变更",
    "open_findings": "本流程未闭环治理待办",
    "knowledge_items": "知识条目",
    "kpi_records_30d": "本流程近 30 天数据",
}


_CHARTER_TEXT = (
    "purpose",
    "starts_at",
    "ends_at",
    "in_scope",
    "out_of_scope",
    "stop_condition",
)


def _complete_charters(db: Session, l3_ids: List[int]) -> int:
    """本流程范围内写全起止的 L3。口径与开始使用里的范围说明相同，只按本流程过滤。"""
    if not l3_ids:
        return 0
    rows = db.execute(
        select(ProcessCharter, ProcessArch)
        .join(ProcessArch, ProcessArch.id == ProcessCharter.process_id)
        .where(ProcessCharter.process_id.in_(l3_ids))
    ).all()
    count = 0
    for charter, process in rows:
        if process.owner_user_id is None or charter.sponsor_user_id is None:
            continue
        if all((getattr(charter, name) or "").strip() for name in _CHARTER_TEXT):
            count += 1
    return count


def ancestor_ids(db: Session, process_id: Optional[int]) -> List[int]:
    ids: List[int] = []
    current = db.get(ProcessArch, process_id) if process_id else None
    guard = 0
    while current is not None and guard < 16:
        ids.append(current.id)
        current = db.get(ProcessArch, current.parent_id) if current.parent_id else None
        guard += 1
    return ids


def descendant_activity_ids(db: Session, process_id: int) -> List[int]:
    """本流程下属 L4 活动（含自身为 L4）。"""
    rows = db.scalars(select(ProcessArch).where(ProcessArch.level == 4)).all()
    result: List[int] = []
    for row in rows:
        if process_id in ancestor_ids(db, row.id):
            result.append(row.id)
    return result


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _filled(value: object) -> bool:
    return bool(str(value or "").strip())


def _mining_variants(db: Session, process_ids: List[int]) -> int:
    """复用执行实例上的挖掘，不另写一套。同一流程只数一次。"""
    total = 0
    seen: Set[int] = set()
    for process_id in process_ids:
        if process_id in seen:
            continue
        seen.add(process_id)
        total += process_mining.completed_variant_count(db, process_id)
    return total


def _complete_rpa(db: Session, process_ids: Set[int]) -> int:
    if not process_ids:
        return 0
    rows = db.scalars(select(RpaBot).where(RpaBot.process_id.in_(process_ids))).all()
    return sum(
        1
        for row in rows
        if row.owner_user_id is not None
        and _filled(row.activity_name)
        and _filled(row.bot_name)
        and _filled(row.manual_step)
    )


def _complete_runs(db: Session, process_ids: Set[int]) -> int:
    """写全的机器人上，记下一次运行，并且指向一个已经登记的集成端点。"""
    if not process_ids:
        return 0
    bots = {
        row.id: row
        for row in db.scalars(select(RpaBot).where(RpaBot.process_id.in_(process_ids))).all()
    }
    if not bots:
        return 0
    endpoints = set(db.scalars(select(IntegrationEndpoint.id)).all())
    runs = db.scalars(select(RpaRun).where(RpaRun.bot_id.in_(bots))).all()
    count = 0
    for run in runs:
        bot = bots.get(run.bot_id)
        if bot is None or run.endpoint_id not in endpoints or run.ran_at is None:
            continue
        if run.outcome not in ("SUCCEEDED", "FAILED"):
            continue
        if (
            bot.owner_user_id is not None
            and _filled(bot.activity_name)
            and _filled(bot.bot_name)
            and _filled(bot.manual_step)
        ):
            count += 1
    return count


def _complete_cases(db: Session, process_ids: Set[int]) -> int:
    if not process_ids:
        return 0
    rows = db.scalars(select(ProcessCase).where(ProcessCase.process_id.in_(process_ids))).all()
    return sum(
        1
        for row in rows
        if row.owner_user_id is not None and _filled(row.title) and _filled(row.situation)
    )


def _complete_technology(db: Session, process_ids: Set[int]) -> int:
    if not process_ids:
        return 0
    rows = db.scalars(
        select(ProcessTechnologyUse).where(
            ProcessTechnologyUse.process_id.in_(process_ids),
            ProcessTechnologyUse.kind.in_(("BLOCKCHAIN", "AI", "IOT")),
        )
    ).all()
    return sum(
        1
        for row in rows
        if row.owner_user_id is not None and _filled(row.name) and _filled(row.usage_note)
    )


def _complete_training(db: Session, process_ids: Set[int]) -> int:
    if not process_ids:
        return 0
    rows = db.scalars(
        select(ProcessTrainingRecord).where(ProcessTrainingRecord.process_id.in_(process_ids))
    ).all()
    return sum(
        1
        for row in rows
        if row.trainee_user_id is not None and row.completed_on is not None and _filled(row.topic)
    )


def _training_from_changes(db: Session, process_ids: Set[int]) -> int:
    """已应用变更上写明的培训说明。这段文字单独计数，不再要求另写到场人名。"""
    if not process_ids:
        return 0
    rows = db.scalars(
        select(ProcessChangeRequest).where(
            ProcessChangeRequest.process_id.in_(process_ids),
            ProcessChangeRequest.status == ChangeStatus.APPLIED.value,
        )
    ).all()
    return sum(1 for row in rows if _filled((row.impact or {}).get("training")))


def _kpi_stats_for(db: Session, process_ids: Set[int]) -> tuple[int, int, int, int, int]:
    if not process_ids:
        return 0, 0, 0, 0, 0
    kpis = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(
            KpiDefinition.is_active.is_(True),
            KpiDefinition.process_id.in_(process_ids),
        )
    ).all()
    cards = 0
    records = 0
    red_yellow = 0
    recent = 0
    monitored = 0
    last_30 = date.today() - timedelta(days=30)
    for kpi in kpis:
        has_card = bool(
            (kpi.formula or "").strip()
            and kpi.target_value is not None
            and kpi.red_threshold is not None
            and kpi.yellow_threshold is not None
            and kpi.green_threshold is not None
        )
        if has_card:
            cards += 1
        periods = kpi_service.ordered_records(kpi.records)
        records += len(periods)
        recent += sum(1 for row in periods if row.period >= last_30)
        if not periods:
            continue
        status, _label, _kind = kpi_service.presentation(db, kpi, periods[-1].value)
        if status in ("RED", "YELLOW"):
            red_yellow += 1
        if has_card and kpi.owner_user_id is not None and periods:
            monitored += 1
    return cards, records, red_yellow, recent, monitored


def collect(db: Session, process_id: int) -> Dict[str, int]:
    """本流程（含祖先链 / 下属 L4）的落地证据。"""
    scope = ancestor_ids(db, process_id)
    if not scope:
        return {key: 0 for key in PROCESS_EVIDENCE_LABELS}
    scope_set = set(scope)
    activities = descendant_activity_ids(db, process_id)
    activity_set = set(activities) | scope_set

    nodes = {
        row.id: row
        for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(scope))).all()
    }
    l1 = 1 if any(nodes[i].level == 1 for i in scope if i in nodes) else 0
    l2 = 1 if any(nodes[i].level == 2 for i in scope if i in nodes) else 0
    l3 = 1 if any(nodes[i].level == 3 for i in scope if i in nodes) else 0
    l3_ids = [i for i in scope if i in nodes and nodes[i].level == 3]

    linked_obj_ids = set(
        db.scalars(
            select(ObjectiveProcessLink.objective_id).where(
                ObjectiveProcessLink.process_id.in_(scope)
            )
        ).all()
    )
    objectives = 0
    objectives_with_owner = 0
    objectives_with_baseline = 0
    objective_complete = 0
    if linked_obj_ids:
        obj_rows = db.scalars(
            select(StrategyObjective).where(
                StrategyObjective.id.in_(linked_obj_ids),
                StrategyObjective.status == "ACTIVE",
            )
        ).all()
        objectives = len(obj_rows)
        objectives_with_owner = sum(
            1 for row in obj_rows if row.owner_user_id is not None and row.target_value is not None
        )
        objectives_with_baseline = sum(1 for row in obj_rows if row.baseline_value is not None)
        objective_complete = sum(
            1
            for row in obj_rows
            if row.owner_user_id is not None
            and row.target_value is not None
            and row.baseline_value is not None
        )
    linked_objectives = objectives

    pcf_mapped_l3 = (
        _count(
            db,
            select(func.count(func.distinct(ProcessBenchmarkMap.process_id))).where(
                ProcessBenchmarkMap.process_id.in_(l3_ids)
            ),
        )
        if l3_ids
        else 0
    )
    process_charters = _complete_charters(db, l3_ids)
    benchmark_maps = _count(
        db,
        select(func.count())
        .select_from(ProcessBenchmarkMap)
        .where(ProcessBenchmarkMap.process_id.in_(scope)),
    )

    positions = _count(db, select(func.count()).select_from(Position))
    raci_matters = _count(
        db,
        select(func.count()).select_from(
            select(RaciAssignment.process_id, RaciAssignment.matter)
            .where(RaciAssignment.process_id.in_(scope))
            .distinct()
            .subquery()
        ),
    )
    invalid_processes = (
        1 if any(row.process_id in scope_set for row in raci_service.invalid_processes(db)) else 0
    )

    doc_rows = db.scalars(
        select(ProcessDocument)
        .options(selectinload(ProcessDocument.versions))
        .where(
            ProcessDocument.is_active.is_(True),
            ProcessDocument.process_id.in_(scope),
        )
    ).all()
    documents = len(doc_rows)
    effective_documents = sum(
        1 for document in doc_rows if document_service.effective_version_on(document) is not None
    )

    rules = db.scalars(
        select(AuthorizationRule).where(
            or_(
                AuthorizationRule.process_id.is_(None),
                AuthorizationRule.process_id.in_(scope),
            )
        )
    ).all()
    effective_authorization_rules = sum(
        1
        for rule in rules
        if rule.status == authorization_service.AuthorizationStatus.EFFECTIVE.value
    )
    exceptions = db.scalars(
        select(AuthorizationException).where(
            or_(
                AuthorizationException.process_id.is_(None),
                AuthorizationException.process_id.in_(scope),
            )
        )
    ).all()
    open_authorization_exceptions = sum(
        1
        for row in exceptions
        if row.status
        in (
            authorization_service.AuthorizationExceptionStatus.REQUESTED.value,
            authorization_service.AuthorizationExceptionStatus.APPROVED.value,
        )
    )

    l3_published = (
        _count(
            db,
            select(func.count())
            .select_from(ProcessArch)
            .where(
                ProcessArch.id.in_(l3_ids),
                ProcessArch.published_model_version > 0,
            ),
        )
        if l3_ids
        else 0
    )

    forms = _count(
        db,
        select(func.count())
        .select_from(FormDefinition)
        .where(FormDefinition.process_id.in_(activity_set)),
    )
    proc_rules = _count(
        db,
        select(func.count())
        .select_from(ProcessRule)
        .where(ProcessRule.process_id.in_(activity_set)),
    )
    node_tools = _count(
        db,
        select(func.count()).select_from(NodeTool).where(NodeTool.process_id.in_(activity_set)),
    )

    verified_standards = (
        _count(
            db,
            select(func.count())
            .select_from(WorkMeasurementStandard)
            .where(
                WorkMeasurementStandard.status == WorkMeasurementStatus.VERIFIED.value,
                WorkMeasurementStandard.activity_id.in_(activity_set),
            ),
        )
        if activity_set
        else 0
    )
    month_start = workload_service.normalize_period(date.today())
    capacity_rows = _count(
        db,
        select(func.count())
        .select_from(CapacityCalendar)
        .where(CapacityCalendar.period == month_start),
    )
    kpi_cards, kpi_records, red_yellow, kpi_records_30d, kpi_monitored = _kpi_stats_for(
        db, scope_set
    )
    mining_variants = _mining_variants(db, [*l3_ids, process_id])
    rpa_bots = _complete_rpa(db, activity_set)
    training_records = _complete_training(db, activity_set) + _training_from_changes(
        db, activity_set
    )
    rpa_runs = _complete_runs(db, activity_set)
    process_cases = _complete_cases(db, activity_set)
    technology_uses = _complete_technology(db, activity_set)

    improvement_projects = _count(
        db,
        select(func.count())
        .select_from(Project)
        .where(
            Project.source == "KPI_THRESHOLD",
            Project.process_id.in_(scope),
        ),
    )
    applied_changes = _count(
        db,
        select(func.count())
        .select_from(ProcessChangeRequest)
        .where(
            ProcessChangeRequest.status == ChangeStatus.APPLIED.value,
            ProcessChangeRequest.process_id.in_(scope),
        ),
    )
    open_findings = _count(
        db,
        select(func.count())
        .select_from(GovernanceFinding)
        .where(
            GovernanceFinding.status == "OPEN",
            GovernanceFinding.entity_type == "process",
            GovernanceFinding.entity_id.in_(scope),
        ),
    )

    return {
        "objectives": objectives,
        "linked_objectives": linked_objectives,
        "objectives_with_owner": objectives_with_owner,
        "objectives_with_baseline": objectives_with_baseline,
        "objective_complete": objective_complete,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "process_charters": process_charters,
        "pcf_mapped_l3": pcf_mapped_l3,
        "benchmark_maps": benchmark_maps,
        "positions": positions,
        "raci_matters": raci_matters,
        "invalid_processes": invalid_processes,
        "documents": documents,
        "effective_documents": effective_documents,
        "effective_authorization_rules": effective_authorization_rules,
        "open_authorization_exceptions": open_authorization_exceptions,
        "l3_published": l3_published,
        "bindings": forms + proc_rules + node_tools,
        "forms": forms,
        "rules": proc_rules,
        "node_tools": node_tools,
        "verified_standards": verified_standards,
        "capacity_rows": capacity_rows,
        "actual_worklogs": 0,
        "kpi_monitored": kpi_monitored,
        "kpi_cards": kpi_cards,
        "kpi_records": kpi_records,
        "mining_variants": mining_variants,
        "rpa_bots": rpa_bots,
        "rpa_runs": rpa_runs,
        "process_cases": process_cases,
        "technology_uses": technology_uses,
        "training_records": training_records,
        "red_yellow": red_yellow,
        "improvement_projects": improvement_projects,
        "applied_changes": applied_changes,
        "open_findings": open_findings,
        "knowledge_items": 0,
        "kpi_records_30d": kpi_records_30d,
    }
