"""岗位—活动—职责投影；角色归位先核完整成员，再裁剪可见输出。"""

from datetime import date
from typing import Optional
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.asset_graph import NodeActivityLink
from app.models.org import Position
from app.models.process import ProcessArch
from app.models.process_task import ProcessTaskDefinition
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import User
from app.schemas.position_coverage import (
    CoverageActivityOut,
    CoverageGapOut,
    CoverageProcessOut,
    CoverageRaciOut,
    CoverageSourceOut,
    PositionCoverageOut,
)
from app.schemas.workload import WorkloadSummaryOut, WorkloadTotals
from app.services import binding_snapshot, org_access, process_model, workload
from app.services.raci import RACI_LABELS

SOURCE_LABELS = {
    "NODE_POSITION": "节点责任岗位",
    "TASK_DEFINITION": "任务定义岗位",
    "WORK_STANDARD": "标准工时岗位",
    "ROLE_MEMBER": "治理角色成员推导",
    "ACTUAL": "实际工时记录（不证明标准职责）",
}


def role_position(db: Session, role: GovernanceRole) -> Optional[int]:
    """全成员必须有效且归于同一有效岗位，不能过滤后制造唯一性。"""
    members = list(role.members)
    if not role.is_active or not members:
        return None
    positions = set()
    for member in members:
        user = member.user
        if user is None or not user.is_active or user.position_id is None:
            return None
        position = db.get(Position, user.position_id)
        if position is None or not position.is_active:
            return None
        positions.add(position.id)
    return next(iter(positions)) if len(positions) == 1 else None


def raci_out(row: RaciAssignment) -> CoverageRaciOut:
    return CoverageRaciOut(
        id=row.id,
        role_id=row.role_id,
        role_name=row.role.name,
        raci=row.raci,
        raci_label=RACI_LABELS[row.raci],
        scope_key=row.scope_key,
        node_key=row.node_key,
        activity_id=row.activity_id,
    )


def coverage(
    db: Session,
    position_id: int,
    user: User,
    period: Optional[date] = None,
    *,
    model_basis: str = "CURRENT",
) -> PositionCoverageOut:
    position = db.get(Position, position_id)
    if position is None:
        raise HTTPException(404, "岗位不存在")
    org_access.ensure_visible(db, user, position.org_unit_id)
    summary = workload.summary(db, period=period, user=user)
    standards = [r for r in summary.standards if r.position_id == position_id]
    actual = [r for r in summary.actual if r.position_id == position_id]
    capacity = [r for r in summary.capacity if r.position_id == position_id]
    demand = round(sum(r.demand_minutes for r in standards if r.included), 2)
    available = round(sum(r.available_minutes for r in capacity), 2)
    projected = WorkloadSummaryOut(
        period=summary.period,
        standards=standards,
        actual=actual,
        capacity=capacity,
        totals=WorkloadTotals(
            demand_minutes=demand,
            available_minutes=available,
            actual_minutes=round(sum(r.effort_minutes for r in actual), 2),
            utilization=round(demand / available, 4) if available > 0 else None,
        ),
    )
    activities = []
    processes = []
    unmapped = []
    matters = []
    gaps = []
    process_rows = db.scalars(
        org_access.restrict(
            select(ProcessArch).where(ProcessArch.level == 3, ProcessArch.is_draft.is_(False)),
            db,
            user,
            ProcessArch.org_unit_id,
        ).order_by(ProcessArch.code)
    ).all()
    for process in process_rows:
        version = process_model.latest_version(db, process.id)
        if model_basis == "PUBLISHED":
            from app.services.asset_graph import published_model

            version = published_model(db, process)
            if version is None:
                continue
        nodes, _ = process_model.rows_from_snapshot(
            process.id,
            version.snapshot if version else process_model.current_snapshot(db, process.id),
        )
        links = list(
            db.scalars(
                select(NodeActivityLink).where(
                    NodeActivityLink.process_id == process.id,
                    NodeActivityLink.relation.in_(["REALIZES", "PART_OF"]),
                    or_(
                        NodeActivityLink.model_version_id == version.id if version else False,
                        NodeActivityLink.model_version_id.is_(None),
                    ),
                )
            ).all()
        )
        l4s = {
            r.id: r
            for r in db.scalars(
                select(ProcessArch).where(
                    ProcessArch.parent_id == process.id,
                    ProcessArch.level == 4,
                    ProcessArch.is_draft.is_(False),
                )
            ).all()
        }
        node_ids = {}
        for node in nodes:
            authoritative = [r.activity_id for r in links if r.node_key == node.node_key]
            node_ids[node.node_key] = (
                set(authoritative or ([node.process_arch_id] if node.process_arch_id else []))
                & l4s.keys()
            )
        assignments = list(
            db.scalars(
                org_access.restrict(
                    select(RaciAssignment)
                    .join(GovernanceRole)
                    .options(
                        selectinload(RaciAssignment.role)
                        .selectinload(GovernanceRole.members)
                        .joinedload(GovernanceRoleMember.user)
                    )
                    .where(
                        RaciAssignment.process_id == process.id, GovernanceRole.is_active.is_(True)
                    ),
                    db,
                    user,
                    GovernanceRole.org_unit_id,
                )
            ).all()
        )
        tasks = list(
            db.scalars(
                select(ProcessTaskDefinition).where(
                    ProcessTaskDefinition.activity_id.in_(l4s),
                    ProcessTaskDefinition.position_id == position_id,
                    ProcessTaskDefinition.is_active.is_(True),
                )
            ).all()
        )
        relevant = {}
        local_unmapped = []
        local_matters = []
        assignments.sort(key=lambda row: row.id)
        tasks.sort(key=lambda row: row.id)
        for assignment in assignments:
            mapped_position = role_position(db, assignment.role)
            if mapped_position is None:
                local_unmapped.append(
                    CoverageGapOut(
                        code="UNMAPPED_ROLE",
                        message="角色无法明确归位到一个有效岗位",
                        process_id=process.id,
                        role_id=assignment.role_id,
                        activity_id=assignment.activity_id,
                        node_key=assignment.node_key,
                    )
                )
            elif mapped_position == position_id:
                if assignment.activity_id:
                    aids = {assignment.activity_id} & l4s.keys()
                elif assignment.node_key:
                    aids = node_ids.get(assignment.node_key, set())
                else:
                    local_matters.append(raci_out(assignment))
                    aids = set()
                for aid in aids:
                    relevant.setdefault(aid, []).append(assignment)
        local_rows = []
        for aid, activity in sorted(l4s.items()):
            related = [n for n in nodes if aid in node_ids[n.node_key]]
            sources = [
                CoverageSourceOut(
                    kind="NODE_POSITION", label=SOURCE_LABELS["NODE_POSITION"], node_key=n.node_key
                )
                for n in related
                if n.owner_position_id == position_id
            ]
            sources += [
                CoverageSourceOut(
                    kind="TASK_DEFINITION", label=SOURCE_LABELS["TASK_DEFINITION"], id=t.id
                )
                for t in tasks
                if t.activity_id == aid
            ]
            ws = [r for r in standards if r.activity_id == aid]
            sources += [
                CoverageSourceOut(
                    kind="WORK_STANDARD", label=SOURCE_LABELS["WORK_STANDARD"], id=r.standard_id
                )
                for r in ws
            ]
            sources += [
                CoverageSourceOut(kind="ROLE_MEMBER", label=SOURCE_LABELS["ROLE_MEMBER"], id=r.id)
                for r in relevant.get(aid, [])
            ]
            if any(r.activity_id == aid for r in actual):
                sources.append(CoverageSourceOut(kind="ACTUAL", label=SOURCE_LABELS["ACTUAL"]))
            if not sources:
                continue
            keys = sorted(n.node_key for n in related)
            local_rows.append(
                CoverageActivityOut(
                    process_id=process.id,
                    process_code=process.code,
                    process_name=process.name,
                    activity_id=aid,
                    activity_code=activity.code,
                    activity_name=activity.name,
                    node_keys=keys,
                    model_version_id=version.id if version else None,
                    model_status=version.status if version else "UNVERSIONED",
                    sources=sources,
                    raci=[raci_out(r) for r in relevant.get(aid, [])],
                    standard_ids=[r.standard_id for r in ws],
                    designer_url="#designer?"
                    + urlencode(
                        {
                            "process": process.id,
                            "node": keys[0] if keys else "",
                            "activity": aid,
                            "basis": version.id if version else "",
                        }
                    ),
                )
            )
            if not any(r.included for r in ws):
                gaps.append(
                    CoverageGapOut(
                        code="NO_VERIFIED_STANDARD",
                        message="无已验证标准工时",
                        process_id=process.id,
                        activity_id=aid,
                    )
                )
        for node in nodes:
            if node.owner_position_id == position_id and not node_ids[node.node_key]:
                gaps.append(
                    CoverageGapOut(
                        code="UNMAPPED_NODE",
                        message="岗位节点未明确映射活动",
                        process_id=process.id,
                        node_key=node.node_key,
                    )
                )
        if local_rows or local_matters:
            processes.append(
                CoverageProcessOut(
                    id=process.id,
                    code=process.code,
                    name=process.name,
                    model_version_id=version.id if version else None,
                    model_status=version.status if version else "UNVERSIONED",
                )
            )
            state = binding_snapshot.compare(
                binding_snapshot.capture(db, process, version),
                version.binding_snapshot if version else None,
            )
            for row in local_rows:
                row.binding_consistency = state
            activities += local_rows
            unmapped += local_unmapped
            matters += local_matters
        elif local_unmapped:
            unmapped += local_unmapped
    if not capacity:
        gaps.append(CoverageGapOut(code="NO_CAPACITY", message="所选期间未登记岗位产能"))
    if not activities:
        gaps.append(
            CoverageGapOut(code="NO_ACTIVITY", message="未发现可核对活动绑定，不代表岗位无职责")
        )
    return PositionCoverageOut(
        position_id=position.id,
        code=position.code,
        name=position.name,
        org_unit_id=position.org_unit_id,
        org_unit_name=position.org_unit_name,
        is_active=position.is_active,
        period=summary.period,
        processes=processes,
        activities=activities,
        unmapped_roles=unmapped,
        matter_assignments=matters,
        workload=projected,
        gaps=gaps,
        limitations=[
            "当前岗位职责诊断，不代替有权组织确认。",
            "实际工时按登记时段与人员当前岗位归集，不是历史任职快照。",
            "职级、能力等级与人数配置留到工作量表环节。",
        ],
    )
