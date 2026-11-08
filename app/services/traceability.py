"""追溯矩阵只读面：目标/KPI → L3/L4 → BPMN 节点 → 资产版本 → 证据。

只读，不新建主数据表；缺链接写进 gaps，不推断关系。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Set

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget, NodeActivityLink
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.process_document import (
    CompiledAssetComponent,
    ProcessDocument,
    ProcessDocumentVersion,
)
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.schemas.traceability import (
    TraceabilityOut,
    TraceAssetOut,
    TraceClaimOut,
    TraceKpiOut,
    TraceOrphanOut,
    TraceRowOut,
)
from app.services import asset_graph as asset_service
from app.services import deliverable as deliverable_service
from app.services import org_access


def _visible(db: Session, user: User, process: ProcessArch) -> bool:
    try:
        org_access.ensure_visible(db, user, process.org_unit_id)
        return True
    except HTTPException:
        return False


def _process_path(db: Session, process: ProcessArch) -> str:
    names: List[str] = []
    current: Optional[ProcessArch] = process
    guard = 0
    while current is not None and guard < 8:
        names.append(f"L{current.level} {current.code} {current.name}")
        current = db.get(ProcessArch, current.parent_id) if current.parent_id else None
        guard += 1
    return " / ".join(reversed(names))


def _l4_activities(db: Session, process: ProcessArch) -> List[ProcessArch]:
    if process.level == 4:
        return [process]
    found: List[ProcessArch] = []
    frontier = [process.id]
    for _ in range(4):
        children = list(
            db.scalars(select(ProcessArch).where(ProcessArch.parent_id.in_(frontier))).all()
        )
        if not children:
            break
        found.extend(row for row in children if row.level == 4)
        frontier = [row.id for row in children if row.level < 4]
        if not frontier:
            break
    return found[:100]


def _kpi_out(db: Session, kpi: KpiDefinition) -> TraceKpiOut:
    latest = db.scalar(
        select(KpiRecord)
        .where(KpiRecord.kpi_id == kpi.id)
        .order_by(KpiRecord.period.desc(), KpiRecord.id.desc())
    )
    return TraceKpiOut(
        id=kpi.id,
        code=kpi.code,
        name=kpi.name,
        unit=kpi.unit,
        direction=kpi.direction,
        target_value=kpi.target_value,
        baseline_value=kpi.baseline_value,
        latest_value=latest.value if latest else None,
        latest_period=latest.period.isoformat() if latest else None,
    )


def _kpis_for(
    db: Session,
    process: ProcessArch,
    activity_ids: Sequence[int],
    link_kpi_id: Optional[int],
) -> List[KpiDefinition]:
    if link_kpi_id is not None:
        kpi = db.get(KpiDefinition, link_kpi_id)
        return [kpi] if kpi else []
    conditions = [KpiDefinition.process_id == process.id]
    if activity_ids:
        conditions.append(KpiDefinition.activity_id.in_(activity_ids))
    return list(
        db.scalars(select(KpiDefinition).where(or_(*conditions)).order_by(KpiDefinition.code)).all()
    )


def _assets_for(
    db: Session, process: ProcessArch, activity_ids: Sequence[int]
) -> List[TraceAssetOut]:
    stmt = (
        select(CompiledAssetComponent)
        .join(
            ProcessDocumentVersion,
            ProcessDocumentVersion.id == CompiledAssetComponent.document_version_id,
        )
        .join(
            ProcessDocument,
            ProcessDocument.id == ProcessDocumentVersion.document_id,
        )
        .where(
            ProcessDocument.process_id == process.id,
            ProcessDocumentVersion.source_kind == "COMPILED",
        )
    )
    if activity_ids:
        stmt = stmt.where(CompiledAssetComponent.activity_id.in_(activity_ids))
    else:
        stmt = stmt.where(CompiledAssetComponent.activity_id.is_(None))
    rows = list(db.scalars(stmt.order_by(CompiledAssetComponent.id.desc())).all())
    seen: Set[int] = set()
    result: List[TraceAssetOut] = []
    for component in rows:
        if component.document_version_id in seen:
            continue
        seen.add(component.document_version_id)
        version = db.get(ProcessDocumentVersion, component.document_version_id)
        document = db.get(ProcessDocument, version.document_id) if version else None
        if version is None or document is None:
            continue
        manifest = version.compile_manifest or {}
        kind = manifest.get("kind")
        kind_labels = {
            "ASSET_PACKAGE": "资产包",
            "DIAGNOSIS": "诊断证据包",
            "DIAGNOSIS_R1": "R1 诊断证据包",
        }
        result.append(
            TraceAssetOut(
                document_id=document.id,
                document_code=document.code,
                document_title=document.title,
                version_id=version.id,
                version_label=version.version_label,
                status=version.status,
                status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
                kind=kind,
                kind_label=kind_labels.get(kind, kind),
                model_version=manifest.get("model_version"),
            )
        )
    return result[:12]


def _claims_for(
    db: Session, process: ProcessArch, kpi: Optional[KpiDefinition], activity_ids: Sequence[int]
) -> List[TraceClaimOut]:
    conditions = [
        and_(
            EvidenceClaimTarget.target_type == "PROCESS",
            EvidenceClaimTarget.target_id == process.id,
        )
    ]
    if activity_ids:
        conditions.append(
            and_(
                EvidenceClaimTarget.target_type.in_(["ACTIVITY", "TIME_FIELD"]),
                EvidenceClaimTarget.target_id.in_(activity_ids),
            )
        )
    if kpi is not None:
        conditions.append(
            and_(
                EvidenceClaimTarget.target_type == "KPI",
                EvidenceClaimTarget.target_id == kpi.id,
            )
        )
    rows = list(
        db.scalars(
            select(EvidenceClaim)
            .join(EvidenceClaimTarget, EvidenceClaimTarget.claim_id == EvidenceClaim.id)
            .where(
                EvidenceClaim.process_id == process.id,
                or_(*conditions),
            )
            .order_by(EvidenceClaim.id.desc())
        ).all()
    )
    today = utcnow().date()
    seen: Set[int] = set()
    result: List[TraceClaimOut] = []
    for claim in rows:
        if claim.id in seen or claim.status == "EXPIRED":
            continue
        if claim.valid_to is not None and claim.valid_to < today:
            continue
        seen.add(claim.id)
        result.append(
            TraceClaimOut(
                id=claim.id,
                claim=claim.claim,
                method=claim.method,
                method_label=asset_service.LABELS["method"].get(claim.method, claim.method),
                status=claim.status,
                status_label=asset_service.LABELS["status"].get(claim.status, claim.status),
                samples=claim.samples,
                conflict_group=claim.conflict_group,
            )
        )
    return result[:20]


def _nodes_for(
    db: Session, process: ProcessArch, activity_ids: Sequence[int]
) -> tuple[Optional[int], Optional[int], List[str]]:
    version = asset_service.published_model(db, process)
    if version is None or not activity_ids:
        return None, None, []
    rows = list(
        db.scalars(
            select(NodeActivityLink).where(
                NodeActivityLink.process_id == process.id,
                NodeActivityLink.activity_id.in_(activity_ids),
                NodeActivityLink.relation.in_(["REALIZES", "PART_OF"]),
                or_(
                    NodeActivityLink.model_version_id == version.id,
                    NodeActivityLink.model_version_id.is_(None),
                ),
            )
        ).all()
    )
    return version.id, version.version, sorted({row.node_key for row in rows})


def _make_row(
    db: Session,
    objective: Optional[StrategyObjective],
    process: ProcessArch,
    kpi: Optional[KpiDefinition],
    activity: Optional[ProcessArch],
    *,
    objective_gap: bool = False,
) -> TraceRowOut:
    activity_ids = [activity.id] if activity is not None else []
    model_version_id, model_version, node_keys = _nodes_for(db, process, activity_ids)
    assets = _assets_for(db, process, activity_ids)
    claims = _claims_for(db, process, kpi, activity_ids)
    gaps: List[str] = []
    if objective_gap:
        gaps.append("目标未承接")
    if kpi is None:
        gaps.append("流程未挂KPI")
    if activity is None:
        gaps.append("流程没有L4活动")
    if activity is not None and not node_keys:
        gaps.append("活动未映射BPMN节点")
    if not assets:
        gaps.append("没有编译资产")
    if not claims:
        gaps.append("没有证据/观测")
    return TraceRowOut(
        objective_id=objective.id if objective else None,
        objective_code=objective.code if objective else None,
        objective_name=objective.name if objective else None,
        kpi=_kpi_out(db, kpi) if kpi else None,
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        process_level=process.level,
        process_path=_process_path(db, process),
        activity_id=activity.id if activity else None,
        activity_code=activity.code if activity else None,
        activity_name=activity.name if activity else None,
        model_version_id=model_version_id,
        model_version=model_version,
        node_keys=node_keys,
        assets=assets,
        claims=claims,
        gaps=gaps,
    )


def _rows_for_process(
    db: Session,
    process: ProcessArch,
    objective: Optional[StrategyObjective],
    *,
    link_kpi_id: Optional[int] = None,
    kpi_filter: Optional[KpiDefinition] = None,
    activity_filter: Optional[ProcessArch] = None,
    objective_gap: bool = False,
) -> List[TraceRowOut]:
    activities = [activity_filter] if activity_filter else _l4_activities(db, process)
    if kpi_filter is not None:
        kpis: List[Optional[KpiDefinition]] = [kpi_filter]
    elif link_kpi_id is not None:
        kpi = db.get(KpiDefinition, link_kpi_id)
        kpis = [kpi] if kpi else [None]
    else:
        kpis = list(_kpis_for(db, process, [row.id for row in activities], None)) or [None]
    rows: List[TraceRowOut] = []
    for kpi in kpis:
        target_activities: List[Optional[ProcessArch]]
        if activity_filter is not None:
            target_activities = [activity_filter]
        elif kpi is not None and kpi.activity_id:
            activity = db.get(ProcessArch, kpi.activity_id)
            target_activities = [activity] if activity else [None]
        else:
            target_activities = list(activities) or [None]
        for activity in target_activities:
            rows.append(
                _make_row(
                    db,
                    objective,
                    process,
                    kpi,
                    activity,
                    objective_gap=objective_gap,
                )
            )
    return rows


def traceability(
    db: Session,
    user: User,
    *,
    objective_id: Optional[int] = None,
    kpi_id: Optional[int] = None,
    process_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    limit: int = 200,
) -> TraceabilityOut:
    limit = max(1, min(limit, 500))
    activity_filter: Optional[ProcessArch] = None
    process_filter: Optional[ProcessArch] = None
    kpi_filter: Optional[KpiDefinition] = None
    objective_filter: Optional[StrategyObjective] = None

    if activity_id is not None:
        activity_filter = db.get(ProcessArch, activity_id)
        if activity_filter is None or activity_filter.level != 4:
            raise HTTPException(404, "L4 活动不存在")
        process_filter = db.get(ProcessArch, activity_filter.parent_id)
        if process_filter is None or not _visible(db, user, process_filter):
            raise HTTPException(404, "活动所属流程不存在")
    if process_id is not None:
        process_filter = db.get(ProcessArch, process_id)
        if process_filter is None or not _visible(db, user, process_filter):
            raise HTTPException(404, "流程不存在")
    if kpi_id is not None:
        kpi_filter = db.get(KpiDefinition, kpi_id)
        if kpi_filter is None:
            raise HTTPException(404, "KPI 不存在")
    if objective_id is not None:
        objective_filter = db.get(StrategyObjective, objective_id)
        if objective_filter is None:
            raise HTTPException(404, "战略目标不存在")

    if objective_filter is not None:
        objectives = [objective_filter]
    elif kpi_filter is not None:
        objectives = list(
            {
                link.objective: link.objective
                for link in db.scalars(
                    select(ObjectiveProcessLink).where(ObjectiveProcessLink.kpi_id == kpi_filter.id)
                ).all()
            }
        )
    elif process_filter is not None:
        objectives = list(
            {
                link.objective: link.objective
                for link in db.scalars(
                    select(ObjectiveProcessLink).where(
                        ObjectiveProcessLink.process_id == process_filter.id
                    )
                ).all()
            }
        )
    else:
        objectives = list(
            db.scalars(select(StrategyObjective).order_by(StrategyObjective.code).limit(50)).all()
        )

    rows: List[TraceRowOut] = []
    orphans: List[TraceOrphanOut] = []
    seen: Set[tuple] = set()

    def add(row: TraceRowOut) -> None:
        key = (row.objective_id, row.kpi.id if row.kpi else None, row.process_id, row.activity_id)
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    for objective in objectives:
        links = list(
            db.scalars(
                select(ObjectiveProcessLink).where(
                    ObjectiveProcessLink.objective_id == objective.id
                )
            ).all()
        )
        if process_filter is not None:
            links = [link for link in links if link.process_id == process_filter.id]
        if kpi_filter is not None:
            links = [link for link in links if link.kpi_id == kpi_filter.id]
        if not links:
            if (objective_filter is not None) or (process_filter is None and kpi_filter is None):
                orphans.append(
                    TraceOrphanOut(
                        kind="OBJECTIVE",
                        id=objective.id,
                        code=objective.code,
                        name=objective.name,
                        reason="目标未承接流程",
                    )
                )
            continue
        for link in links:
            process = db.get(ProcessArch, link.process_id)
            if process is None or not _visible(db, user, process):
                continue
            for row in _rows_for_process(
                db,
                process,
                objective,
                link_kpi_id=link.kpi_id,
                kpi_filter=kpi_filter,
                activity_filter=activity_filter,
            ):
                add(row)

    if kpi_filter is not None and not rows:
        process = db.get(ProcessArch, kpi_filter.process_id) if kpi_filter.process_id else None
        if process is None and kpi_filter.activity_id:
            activity = db.get(ProcessArch, kpi_filter.activity_id)
            process = db.get(ProcessArch, activity.parent_id) if activity else None
        if process is None or not _visible(db, user, process):
            orphans.append(
                TraceOrphanOut(
                    kind="KPI",
                    id=kpi_filter.id,
                    code=kpi_filter.code,
                    name=kpi_filter.name,
                    reason="KPI 未挂流程",
                )
            )
        else:
            for row in _rows_for_process(
                db,
                process,
                None,
                kpi_filter=kpi_filter,
                activity_filter=activity_filter,
                objective_gap=True,
            ):
                add(row)

    if process_filter is not None and not rows and kpi_filter is None:
        for row in _rows_for_process(
            db,
            process_filter,
            None,
            activity_filter=activity_filter,
            objective_gap=True,
        ):
            add(row)

    objective_ids = {row.objective_id for row in rows if row.objective_id}
    kpi_ids = {row.kpi.id for row in rows if row.kpi}
    process_ids = {row.process_id for row in rows}
    activity_ids = {row.activity_id for row in rows if row.activity_id}
    asset_ids = {asset.version_id for row in rows for asset in row.assets}
    claim_ids = {claim.id for row in rows for claim in row.claims}
    gap_count = sum(1 for row in rows if row.gaps)
    truncated = len(rows) > limit
    return TraceabilityOut(
        filters={
            "objective_id": objective_id,
            "kpi_id": kpi_id,
            "process_id": process_id,
            "activity_id": activity_id,
            "limit": limit,
        },
        total=len(rows),
        rows=rows[:limit],
        orphans=orphans,
        summary={
            "objectives": len(objective_ids),
            "kpis": len(kpi_ids),
            "processes": len(process_ids),
            "activities": len(activity_ids),
            "asset_versions": len(asset_ids),
            "claims": len(claim_ids),
            "gap_rows": gap_count,
            "orphans": len(orphans),
        },
        truncated=truncated,
    )
