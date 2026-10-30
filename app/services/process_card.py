"""流程卡：把一条流程的战略、权责、制度、模型、工时、KPI、变更与改善聚合到一页。"""

from __future__ import annotations

from datetime import datetime, time
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.change import ProcessChangeRequest
from app.models.enums import WorkMeasurementStatus
from app.models.execution import (
    FormDefinition,
    ProcessInstance,
    ProcessRule,
    ProcessTask,
    TaskWorklog,
)
from app.models.governance import GovernanceFinding
from app.models.monitor import KpiDefinition
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.schemas.process_card import (
    CardChainItem,
    CardChangeOut,
    CardDocumentOut,
    CardFindingOut,
    CardImprovementOut,
    CardKpiOut,
    CardModelOut,
    CardObjectiveOut,
    CardProcessOut,
    CardRaciEntryOut,
    CardRaciMatterOut,
    CardWorkloadOut,
    ProcessCardOut,
)
from app.services import change as change_service
from app.services import deliverable as deliverable_service
from app.services import governance as governance_service
from app.services import improvement as improvement_service
from app.services import kpi as kpi_service
from app.services import process_document as document_service
from app.services import process_model as model_service
from app.services import raci as raci_service
from app.services import strategy as strategy_service
from app.services import workload as workload_service


class ProcessCardError(ValueError):
    pass


def _ancestor_ids(db: Session, process_id: int) -> List[int]:
    ids: List[int] = []
    current: Optional[ProcessArch] = db.get(ProcessArch, process_id)
    guard = 0
    while current is not None and guard < 16:
        ids.append(current.id)
        current = db.get(ProcessArch, current.parent_id) if current.parent_id else None
        guard += 1
    return ids


def _l4_ids(db: Session, process_id: int) -> List[int]:
    """流程下属的 L4 活动（包含流程本身是 L4 的情况）。"""
    rows = db.scalars(select(ProcessArch).where(ProcessArch.level == 4)).all()
    result = []
    for row in rows:
        if process_id in _ancestor_ids(db, row.id):
            result.append(row.id)
    return result


def _chain(db: Session, process: ProcessArch) -> List[CardChainItem]:
    chain: List[CardChainItem] = []
    current: Optional[ProcessArch] = process
    guard = 0
    while current is not None and guard < 16:
        chain.append(
            CardChainItem(id=current.id, code=current.code, name=current.name, level=current.level)
        )
        current = db.get(ProcessArch, current.parent_id) if current.parent_id else None
        guard += 1
    chain.reverse()
    return chain


def _documents(db: Session, process_id: int) -> List[CardDocumentOut]:
    ancestors = _ancestor_ids(db, process_id)
    rows = db.scalars(
        select(ProcessDocument)
        .options(selectinload(ProcessDocument.versions))
        .where(
            ProcessDocument.is_active.is_(True),
            ProcessDocument.process_id.in_(ancestors),
        )
        .order_by(ProcessDocument.code)
    ).all()
    result: List[CardDocumentOut] = []
    for document in rows:
        version = document_service.effective_version_on(document)
        if version is None:
            continue
        result.append(
            CardDocumentOut(
                id=document.id,
                code=document.code,
                title=document.title,
                category=document.category,
                category_label=document_service.CATEGORY_LABELS.get(
                    document.category, document.category
                ),
                version_label=f"v{version.version_label}",
                status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
            )
        )
    return result


def _model(db: Session, process_id: int) -> CardModelOut:
    latest = model_service.latest_version(db, process_id)
    snapshot = model_service.current_snapshot(db, process_id)
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []
    forms = (
        db.scalar(
            select(func.count())
            .select_from(FormDefinition)
            .where(FormDefinition.process_id == process_id)
        )
        or 0
    )
    rules = (
        db.scalar(
            select(func.count())
            .select_from(ProcessRule)
            .where(ProcessRule.process_id == process_id)
        )
        or 0
    )
    tools = (
        db.scalar(
            select(func.count()).select_from(NodeTool).where(NodeTool.process_id == process_id)
        )
        or 0
    )
    return CardModelOut(
        status=latest.status if latest else ("PUBLISHED" if nodes else None),
        status_label=(
            model_service.STATUS_LABELS.get(latest.status, latest.status)
            if latest
            else ("已发布" if nodes else None)
        ),
        version=latest.version if latest else 0,
        node_count=len(nodes),
        edge_count=len(edges),
        form_count=int(forms),
        rule_count=int(rules),
        tool_count=int(tools),
    )


def _workload(db: Session, process_id: int, l4_ids: List[int]) -> CardWorkloadOut:
    activity_ids = l4_ids or [process_id]
    standards = list(
        db.scalars(
            select(WorkMeasurementStandard).where(
                WorkMeasurementStandard.activity_id.in_(activity_ids),
                WorkMeasurementStandard.status == WorkMeasurementStatus.VERIFIED.value,
            )
        ).all()
    )
    demand_minutes = sum(row.standard_minutes * (row.monthly_frequency or 0) for row in standards)
    start, end = workload_service.month_bounds()
    actual_minutes = (
        db.scalar(
            select(func.coalesce(func.sum(TaskWorklog.effort_minutes), 0.0))
            .join(ProcessTask, ProcessTask.id == TaskWorklog.task_id)
            .join(ProcessInstance, ProcessInstance.id == ProcessTask.instance_id)
            .where(
                ProcessInstance.process_id == process_id,
                TaskWorklog.created_at >= datetime.combine(start, time.min),
                TaskWorklog.created_at < datetime.combine(end, time.min),
            )
        )
        or 0.0
    )
    position_ids = {row.position_id for row in standards}
    capacity_minutes = 0.0
    if position_ids:
        for row in db.scalars(
            select(CapacityCalendar).where(
                CapacityCalendar.position_id.in_(position_ids),
                CapacityCalendar.period == start,
            )
        ).all():
            capacity_minutes += (
                row.headcount
                * row.available_hours_per_person
                * 60
                * row.attendance_rate
                * row.equipment_availability
            )
    return CardWorkloadOut(
        verified_standards=len(standards),
        demand_hours=round(demand_minutes / 60, 1),
        actual_hours=round(float(actual_minutes) / 60, 1),
        capacity_hours=round(capacity_minutes / 60, 1),
        utilization=(round(demand_minutes / capacity_minutes, 4) if capacity_minutes > 0 else None),
    )


def _kpis(db: Session, process_id: int, l4_ids: List[int]) -> List[CardKpiOut]:
    conditions = [KpiDefinition.process_id == process_id]
    if l4_ids:
        conditions.append(KpiDefinition.activity_id.in_(l4_ids))
    from sqlalchemy import or_

    rows = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True), or_(*conditions))
        .order_by(KpiDefinition.code)
    ).all()
    result: List[CardKpiOut] = []
    for kpi in rows:
        records = kpi_service.ordered_records(kpi.records)
        latest = records[-1].value if records else None
        state = kpi_service.status_for(
            latest,
            kpi.direction,
            kpi.red_threshold,
            kpi.yellow_threshold,
            kpi.green_threshold,
        )
        result.append(
            CardKpiOut(
                id=kpi.id,
                code=kpi.code,
                name=kpi.name,
                latest_value=latest,
                target_value=kpi.target_value,
                unit=kpi.unit,
                status=state,
                status_label=kpi_service.STATUS_LABELS.get(state, state),
            )
        )
    return result


def _changes(db: Session, process_id: int) -> List[CardChangeOut]:
    rows = db.scalars(
        select(ProcessChangeRequest)
        .where(ProcessChangeRequest.process_id == process_id)
        .order_by(ProcessChangeRequest.id.desc())
        .limit(5)
    ).all()
    return [
        CardChangeOut(
            id=row.id,
            code=row.code,
            title=row.title,
            status_label=change_service.STATUS_LABELS.get(row.status, row.status),
            impact_level_label=change_service.IMPACT_LEVEL_LABELS.get(
                row.impact_level, row.impact_level
            ),
        )
        for row in rows
    ]


def _improvements(db: Session, process_id: int, kpi_ids: List[int]) -> List[CardImprovementOut]:
    conditions = [Project.process_id == process_id]
    if kpi_ids:
        conditions.append(Project.source_kpi_id.in_(kpi_ids))
    from sqlalchemy import or_

    rows = db.scalars(
        select(Project)
        .where(
            Project.project_type == "IMPROVEMENT",
            or_(*conditions),
        )
        .order_by(Project.id.desc())
        .limit(5)
    ).all()
    return [
        CardImprovementOut(
            id=row.id,
            code=row.code,
            name=row.name,
            status_label=improvement_service.PROJECT_STATUS_LABELS.get(row.status, row.status),
            progress=row.progress,
            source_label=improvement_service.SOURCE_LABELS.get(row.source, row.source),
        )
        for row in rows
    ]


def _findings(db: Session, process_id: int) -> List[CardFindingOut]:
    rows = db.scalars(
        select(GovernanceFinding)
        .where(
            GovernanceFinding.entity_type == "process",
            GovernanceFinding.entity_id == process_id,
            GovernanceFinding.status == "OPEN",
        )
        .order_by(GovernanceFinding.id.desc())
        .limit(10)
    ).all()
    return [
        CardFindingOut(
            id=row.id,
            type=row.type,
            type_label=governance_service.TYPE_LABELS.get(row.type, row.type),
            severity=row.severity,
            title=row.title,
        )
        for row in rows
    ]


def build(db: Session, process_id: int) -> ProcessCardOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ProcessCardError(f"流程 {process_id} 不存在")

    objectives = strategy_service.objectives_for_process(db, process_id)
    raci = raci_service.process_raci(db, process_id)
    l4_ids = _l4_ids(db, process_id)
    documents = _documents(db, process_id)
    model = _model(db, process_id)
    workload = _workload(db, process_id, l4_ids)
    kpis = _kpis(db, process_id, l4_ids)
    changes = _changes(db, process_id)
    improvements = _improvements(db, process_id, [kpi.id for kpi in kpis])
    findings = _findings(db, process_id)

    readiness = {
        "strategy": bool(objectives),
        "raci": bool(raci.matters) and raci.valid,
        "policy": bool(documents),
        "model": model.status == "PUBLISHED",
        "workload": workload.verified_standards > 0,
        "kpi": bool(kpis),
        "improvement": bool(improvements) or bool(changes),
        "governance": not findings,
    }

    return ProcessCardOut(
        process=CardProcessOut(
            id=process.id,
            code=process.code,
            name=process.name,
            level=process.level,
            owner=process.owner,
            owner_user_id=process.owner_user_id,
            org_unit_name=process.org_unit_name,
            department=process.department,
            health_score=process.health_score,
        ),
        chain=_chain(db, process),
        objectives=[
            CardObjectiveOut(
                id=row.id,
                code=row.code,
                name=row.name,
                year=row.year,
                target_value=row.target_value,
                unit=row.unit,
                status_label=row.status_label,
            )
            for row in objectives
        ],
        raci=[
            CardRaciMatterOut(
                matter=matter.matter,
                has_accountable=matter.has_accountable,
                entries=[
                    CardRaciEntryOut(
                        raci=entry.raci,
                        raci_label=entry.raci_label,
                        role_name=entry.role_name,
                        role_type_label=entry.role_type_label,
                    )
                    for entry in matter.entries
                ],
            )
            for matter in raci.matters
        ],
        documents=documents,
        model=model,
        workload=workload,
        kpis=kpis,
        changes=changes,
        improvements=improvements,
        findings=findings,
        readiness=readiness,
    )
