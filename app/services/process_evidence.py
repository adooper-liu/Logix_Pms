"""单流程证据计数：十层退出门专用。

与开始使用的全公司能力计数拆开：
- 公司能力（九阶段）：会不会做（框架/主数据/方法是否存在）
- 单流程落地（十层）：这条会不会跑（对象是否绑到本流程及祖先链）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.authorization import AuthorizationException, AuthorizationRule
from app.models.benchmark import ProcessBenchmarkMap
from app.models.change import ProcessChangeRequest
from app.models.enums import ChangeStatus, WorkMeasurementStatus
from app.models.execution import FormDefinition, ProcessRule
from app.models.governance import GovernanceFinding
from app.models.monitor import KpiDefinition
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.raci import RaciAssignment
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.services import authorization as authorization_service
from app.services import kpi as kpi_service
from app.services import process_document as document_service
from app.services import raci as raci_service
from app.services import workload as workload_service

# 十层上展示的本流程口径标签（键仍与公司证据对齐，避免两套键名）
PROCESS_EVIDENCE_LABELS: Dict[str, str] = {
    "objectives": "本流程已挂年度目标",
    "linked_objectives": "本流程已挂目标",
    "objectives_with_owner": "本流程目标有责任人和目标值",
    "objectives_with_baseline": "本流程目标有现状基线",
    "l1": "本流程上溯有 L1",
    "l2": "本流程上溯有 L2",
    "l3": "本流程落在 L3（或上溯有 L3）",
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
    "bindings": "本流程表单/规则/工具绑定",
    "forms": "本流程表单",
    "rules": "本流程规则",
    "node_tools": "本流程工具绑定",
    "verified_standards": "本流程已验证标准工时",
    "capacity_rows": "当月产能记录",
    "actual_worklogs": "实际工时记录",
    "kpi_cards": "本流程完整 KPI 卡",
    "kpi_records": "本流程 KPI 数据点",
    "red_yellow": "本流程红/黄指标",
    "improvement_projects": "本流程改善项目",
    "applied_changes": "本流程已应用变更",
    "open_findings": "本流程未闭环治理待办",
    "knowledge_items": "知识条目",
    "kpi_records_30d": "本流程近 30 天数据",
}


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


def _kpi_stats_for(db: Session, process_ids: Set[int]) -> tuple[int, int, int, int]:
    if not process_ids:
        return 0, 0, 0, 0
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
        status = kpi_service.status_for(
            periods[-1].value,
            kpi.direction,
            kpi.red_threshold,
            kpi.yellow_threshold,
            kpi.green_threshold,
        )
        if status in ("RED", "YELLOW"):
            red_yellow += 1
    return cards, records, red_yellow, recent


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
    kpi_cards, kpi_records, red_yellow, kpi_records_30d = _kpi_stats_for(db, scope_set)

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
        "l1": l1,
        "l2": l2,
        "l3": l3,
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
        "kpi_cards": kpi_cards,
        "kpi_records": kpi_records,
        "red_yellow": red_yellow,
        "improvement_projects": improvement_projects,
        "applied_changes": applied_changes,
        "open_findings": open_findings,
        "knowledge_items": 0,
        "kpi_records_30d": kpi_records_30d,
    }
