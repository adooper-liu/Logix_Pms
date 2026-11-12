"""关键过程覆盖度矩阵：只读投影，不创建新的主数据。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.adoption import SiblingBoundaryLine, SiblingBoundaryReview
from app.models.asset_graph import NodeActivityLink, UnmodeledActivity
from app.models.org import Position
from app.models.process import ProcessArch, ProcessModelVersion, ProcessNode
from app.models.raci import GovernanceRoleMember, RaciAssignment
from app.models.user import User
from app.schemas.key_process_coverage import (
    BoundaryLineOut,
    BoundaryReviewOut,
    CoverageGapOut,
    CoverageImplementationOut,
    CoverageProcessOut,
    CoverageSummaryOut,
    GapOwnerPositionOut,
    KeyActivityCoverageOut,
    KeyProcessCoverageOut,
    UnmodeledCoverageOut,
)

RELATION_LABELS = {
    "REALIZES": "实现",
    "PART_OF": "组成",
}
SOURCE_LABELS = {
    "CURRENT": "当前版本",
    "HISTORICAL": "历史关系",
    "LEGACY": "兼容主活动指针",
}
LINE_COMPLETE_LABELS = {True: "完整", False: "不完整"}
STATUS_LABELS = {
    "IMPLEMENTED": "已覆盖",
    "UNMODELED": "未建模",
    "UNCOVERED": "未覆盖",
    "MULTI_PROCESS": "多流程实现，需核对",
    "INVALID_KEY_BASIS": "关键依据缺失",
    "INVALID_HIERARCHY": "层级关系无效",
}
BOUNDARY_LABELS = {
    "REVIEWED": "已评审",
    "UNREVIEWED": "未评审",
    "EVIDENCE_INCOMPLETE": "证据不足",
}
GAP_LABELS = {
    "INVALID_KEY_BASIS": "关键过程缺少关键依据",
    "UNMAPPED_POSITION": "缺口责任岗位未归位",
    "INVALID_IMPLEMENTATION": "实现关系指向无效活动",
    "INVALID_HIERARCHY": "关键活动层级关系无效",
}


def _ancestors(
    rows: Dict[int, ProcessArch], row: ProcessArch
) -> Tuple[List[ProcessArch], Optional[str]]:
    ancestors: List[ProcessArch] = []
    seen: Set[int] = set()
    parent_id = row.parent_id
    while parent_id is not None:
        if parent_id in seen:
            return ancestors, "循环"
        seen.add(parent_id)
        parent = rows.get(parent_id)
        if parent is None:
            return ancestors, "缺少上级"
        ancestors.append(parent)
        parent_id = parent.parent_id
    return ancestors, None


def _key_source(
    rows: Dict[int, ProcessArch], activity: ProcessArch
) -> Tuple[bool, Optional[str], str, List[CoverageGapOut]]:
    gaps: List[CoverageGapOut] = []
    if activity.is_key_process:
        if not (activity.key_basis or "").strip():
            gaps.append(
                CoverageGapOut(code="INVALID_KEY_BASIS", message=GAP_LABELS["INVALID_KEY_BASIS"])
            )
            return True, None, "DIRECT", gaps
        basis = activity.key_basis.strip()
        ancestors, hierarchy_error = _ancestors(rows, activity)
        if hierarchy_error:
            gaps.append(
                CoverageGapOut(
                    code="INVALID_HIERARCHY",
                    message=GAP_LABELS["INVALID_HIERARCHY"] + "：" + hierarchy_error,
                )
            )
            return True, basis, "DIRECT", gaps
        return True, basis, "DIRECT", gaps
    ancestors, hierarchy_error = _ancestors(rows, activity)
    if hierarchy_error:
        for parent in ancestors:
            if parent.level == 3 and parent.is_key_process:
                if not (parent.key_basis or "").strip():
                    gaps.append(
                        CoverageGapOut(
                            code="INVALID_KEY_BASIS", message=GAP_LABELS["INVALID_KEY_BASIS"]
                        )
                    )
                    return True, None, "INHERITED", gaps
                gaps.append(
                    CoverageGapOut(
                        code="INVALID_HIERARCHY",
                        message=GAP_LABELS["INVALID_HIERARCHY"] + "：" + hierarchy_error,
                    )
                )
                return True, parent.key_basis.strip(), "INHERITED", gaps
        return (
            False,
            None,
            "NONE",
            [
                CoverageGapOut(
                    code="INVALID_HIERARCHY",
                    message=GAP_LABELS["INVALID_HIERARCHY"] + "：" + hierarchy_error,
                )
            ],
        )
    for parent in ancestors:
        if parent.level == 3 and parent.is_key_process:
            if not (parent.key_basis or "").strip():
                gaps.append(
                    CoverageGapOut(
                        code="INVALID_KEY_BASIS", message=GAP_LABELS["INVALID_KEY_BASIS"]
                    )
                )
                return True, None, "INHERITED", gaps
            return True, parent.key_basis.strip(), "INHERITED", gaps
    return False, None, "NONE", gaps


def _published_version(db: Session, process: ProcessArch) -> Optional[int]:
    if process.published_model_version:
        version = db.scalar(
            select(ProcessModelVersion).where(
                ProcessModelVersion.process_id == process.id,
                ProcessModelVersion.version == process.published_model_version,
                ProcessModelVersion.status == "PUBLISHED",
            )
        )
        if version is not None:
            return version.id
    version = db.scalar(
        select(ProcessModelVersion.id)
        .where(
            ProcessModelVersion.process_id == process.id, ProcessModelVersion.status == "PUBLISHED"
        )
        .order_by(ProcessModelVersion.version.desc())
    )
    return version


def _implementation_rows(
    db: Session, processes: Dict[int, ProcessArch], activities: Dict[int, ProcessArch]
) -> Tuple[Dict[int, List[CoverageImplementationOut]], Dict[int, List[CoverageGapOut]]]:
    nodes = list(
        db.scalars(
            select(ProcessNode).order_by(
                ProcessNode.process_id, ProcessNode.sequence_order, ProcessNode.id
            )
        ).all()
    )
    nodes_by_process_key = {(node.process_id, node.node_key): node for node in nodes}
    current_versions = {
        process_id: _published_version(db, process) for process_id, process in processes.items()
    }
    links = list(db.scalars(select(NodeActivityLink).order_by(NodeActivityLink.id)).all())
    grouped: Dict[Tuple[int, str, int, str, str], List[NodeActivityLink]] = defaultdict(list)
    invalid: Dict[int, List[CoverageGapOut]] = defaultdict(list)
    for link in links:
        if link.process_id not in processes:
            continue
        if (
            link.activity_id not in activities
            or (link.process_id, link.node_key) not in nodes_by_process_key
        ):
            invalid[link.activity_id].append(
                CoverageGapOut(
                    code="INVALID_IMPLEMENTATION",
                    message=GAP_LABELS["INVALID_IMPLEMENTATION"],
                    targets=[f"{link.process_id}:{link.node_key}"],
                )
            )
            continue
        current_version = current_versions.get(link.process_id)
        if current_version is not None and link.model_version_id not in {None, current_version}:
            continue
        if link.relation not in {"REALIZES", "PART_OF"}:
            continue
        grouped[
            (link.process_id, link.node_key, link.activity_id, link.relation, link.path_condition)
        ].append(link)

    output: Dict[int, List[CoverageImplementationOut]] = defaultdict(list)
    seen_keys = set()
    for key, rows in grouped.items():
        process_id, node_key, activity_id, relation, _ = key
        process = processes[process_id]
        node = nodes_by_process_key[(process_id, node_key)]
        current_version = current_versions.get(process_id)
        version_ids = sorted(
            {row.model_version_id for row in rows if row.model_version_id is not None}
        )
        source_ids: List[Optional[int]] = (
            [None] if any(row.model_version_id is None for row in rows) else []
        ) + version_ids
        current = current_version is not None and current_version in version_ids
        output[activity_id].append(
            CoverageImplementationOut(
                process_id=process_id,
                process_code=process.code,
                process_name=process.name,
                node_key=node_key,
                node_name=node.name,
                relation=relation,
                relation_label=RELATION_LABELS.get(relation, relation),
                coverage=max(row.coverage for row in rows),
                model_version_id=current_version
                if current
                else (version_ids[-1] if version_ids else None),
                source_model_version_ids=source_ids,
                current=current,
                historical=any(row.model_version_id is None for row in rows),
                legacy=False,
                source_note=(
                    "含未绑定模型版本的历史关系"
                    if any(row.model_version_id is None for row in rows)
                    else None
                ),
                source_label=(
                    SOURCE_LABELS["HISTORICAL"]
                    if any(row.model_version_id is None for row in rows)
                    else SOURCE_LABELS["CURRENT"]
                ),
            )
        )
        seen_keys.add((process_id, node_key, activity_id))

    for node in nodes:
        if not node.process_arch_id or node.process_arch_id not in activities:
            continue
        key = (node.process_id, node.node_key, node.process_arch_id)
        if key in seen_keys or node.process_id not in processes:
            continue
        process = processes[node.process_id]
        output[node.process_arch_id].append(
            CoverageImplementationOut(
                process_id=process.id,
                process_code=process.code,
                process_name=process.name,
                node_key=node.node_key,
                node_name=node.name,
                relation="REALIZES",
                relation_label=RELATION_LABELS["REALIZES"],
                coverage=1.0,
                current=False,
                historical=False,
                legacy=True,
                source_note=SOURCE_LABELS["LEGACY"] + "，尚未在关系表确认",
                source_label=SOURCE_LABELS["LEGACY"],
            )
        )
    for values in output.values():
        values.sort(key=lambda item: (item.process_code, item.node_key, item.relation))
    for values in invalid.values():
        values.sort(key=lambda item: item.targets)
    return output, invalid


def _unmodeled_rows(
    db: Session, process_ids: Set[int], activity_ids: Set[int]
) -> Dict[int, List[UnmodeledCoverageOut]]:
    result: Dict[int, List[UnmodeledCoverageOut]] = defaultdict(list)
    rows = db.scalars(select(UnmodeledActivity).order_by(UnmodeledActivity.id)).all()
    for row in rows:
        if row.process_id in process_ids and row.activity_id in activity_ids:
            result[row.activity_id].append(
                UnmodeledCoverageOut(
                    id=row.id,
                    process_id=row.process_id,
                    model_version_id=row.model_version_id,
                    reason=row.reason,
                    source_ref=row.source_ref,
                )
            )
    return result


def _owners(
    db: Session,
    implementations: List[CoverageImplementationOut],
    activity_id: int,
) -> Tuple[List[GapOwnerPositionOut], List[CoverageGapOut]]:
    positions: Dict[int, GapOwnerPositionOut] = {}
    gaps: List[CoverageGapOut] = []
    implementation_keys = {(item.process_id, item.node_key) for item in implementations}
    nodes = (
        db.scalars(
            select(ProcessNode)
            .where(ProcessNode.process_id.in_({pid for pid, _ in implementation_keys}))
            .order_by(ProcessNode.process_id, ProcessNode.node_key, ProcessNode.id)
        ).all()
        if implementation_keys
        else []
    )
    for node in nodes:
        if (node.process_id, node.node_key) not in implementation_keys:
            continue
        if node.owner_position_id:
            position = db.get(Position, node.owner_position_id)
            if position:
                entry = positions.setdefault(
                    position.id,
                    GapOwnerPositionOut(
                        id=position.id, code=position.code, name=position.name, mapped=True
                    ),
                )
                if "NODE_POSITION" not in entry.source:
                    entry.source.append("NODE_POSITION")
    assignments = db.scalars(
        select(RaciAssignment)
        .where(RaciAssignment.activity_id == activity_id)
        .order_by(RaciAssignment.process_id, RaciAssignment.node_key, RaciAssignment.id)
    ).all()
    process_ids = {pid for pid, _ in implementation_keys}
    if not process_ids:
        process_ids = set(
            db.scalars(
                select(RaciAssignment.process_id)
                .where(RaciAssignment.activity_id == activity_id)
                .order_by(RaciAssignment.process_id)
            )
        )
    role_ids = {
        row.role_id
        for row in assignments
        if (row.node_key is None and row.process_id in process_ids)
        or (row.process_id, row.node_key) in implementation_keys
    }
    members = (
        db.scalars(
            select(GovernanceRoleMember)
            .where(GovernanceRoleMember.role_id.in_(role_ids))
            .order_by(GovernanceRoleMember.role_id, GovernanceRoleMember.id)
        ).all()
        if role_ids
        else []
    )
    for member in members:
        position = db.scalar(
            select(Position)
            .join(User, User.position_id == Position.id)
            .where(User.id == member.user_id)
        )
        if position:
            entry = positions.setdefault(
                position.id,
                GapOwnerPositionOut(
                    id=position.id, code=position.code, name=position.name, mapped=True
                ),
            )
            if "RACI_MEMBER" not in entry.source:
                entry.source.append("RACI_MEMBER")
        else:
            gaps.append(
                CoverageGapOut(code="UNMAPPED_POSITION", message=GAP_LABELS["UNMAPPED_POSITION"])
            )
    if not positions:
        gaps.append(
            CoverageGapOut(code="UNMAPPED_POSITION", message=GAP_LABELS["UNMAPPED_POSITION"])
        )
    return sorted(positions.values(), key=lambda item: item.code or ""), gaps


def _boundaries(db: Session, l2_rows: List[ProcessArch]) -> List[BoundaryReviewOut]:
    result = []
    for parent in sorted(l2_rows, key=lambda row: row.code):
        children = list(
            db.scalars(
                select(ProcessArch)
                .where(ProcessArch.parent_id == parent.id, ProcessArch.level == 3)
                .order_by(ProcessArch.code)
            ).all()
        )
        review = db.scalar(
            select(SiblingBoundaryReview).where(SiblingBoundaryReview.parent_id == parent.id)
        )
        lines = list(
            db.scalars(
                select(SiblingBoundaryLine)
                .where(SiblingBoundaryLine.parent_id == parent.id)
                .order_by(SiblingBoundaryLine.child_id)
            ).all()
        )
        by_child = {line.child_id: line for line in lines}
        complete = all(child.id in by_child for child in children)
        if review is None:
            status = "UNREVIEWED"
        elif not complete:
            status = "EVIDENCE_INCOMPLETE"
        else:
            status = "REVIEWED"
        result.append(
            BoundaryReviewOut(
                parent_id=parent.id,
                code=parent.code,
                name=parent.name,
                status=status,
                status_label=BOUNDARY_LABELS[status],
                overlap_found=review.overlap_found if review and status == "REVIEWED" else None,
                overlap_work=review.overlap_work if review and status == "REVIEWED" else None,
                note=review.note if review else None,
                line_complete=complete,
                line_complete_label=LINE_COMPLETE_LABELS[complete],
                lines=[
                    BoundaryLineOut(
                        child_id=child.id,
                        child_code=child.code,
                        child_name=child.name,
                        starts_at=by_child[child.id].starts_at,
                        ends_at=by_child[child.id].ends_at,
                        in_scope=by_child[child.id].in_scope,
                        out_of_scope=by_child[child.id].out_of_scope,
                        distinct_work=by_child[child.id].distinct_work,
                    )
                    for child in children
                    if child.id in by_child
                ],
            )
        )
    return result


def coverage(db: Session, user: User) -> KeyProcessCoverageOut:
    rows = {
        row.id: row
        for row in db.scalars(
            select(ProcessArch).where(ProcessArch.is_draft.is_(False)).order_by(ProcessArch.code)
        ).all()
    }
    activities: Dict[int, Tuple[ProcessArch, str, Optional[str], str, List[CoverageGapOut]]] = {}
    for row in rows.values():
        if row.level != 4:
            continue
        is_key, basis, source, gaps = _key_source(rows, row)
        if is_key:
            activities[row.id] = (row, source, basis, source, gaps)
    l3 = {row.id: row for row in rows.values() if row.level == 3}
    implementations, invalid_implementations = _implementation_rows(
        db, l3, {aid: data[0] for aid, data in activities.items()}
    )
    unmodeled = _unmodeled_rows(db, set(l3), set(activities))
    out = []
    summary = CoverageSummaryOut(key_activities=len(activities))
    for activity_id, (activity, _, basis, source, initial_gaps) in sorted(
        activities.items(), key=lambda item: item[1][0].code
    ):
        impl = implementations.get(activity_id, [])
        unm = unmodeled.get(activity_id, [])
        process_ids = {item.process_id for item in impl}
        duplicate = [
            CoverageProcessOut(id=pid, code=l3[pid].code, name=l3[pid].name)
            for pid in sorted(process_ids, key=lambda pid: l3[pid].code)
        ]
        gaps = list(initial_gaps)
        gaps.extend(invalid_implementations.get(activity_id, []))
        owners, owner_gaps = _owners(db, impl, activity_id)
        gaps.extend(owner_gaps)
        if initial_gaps:
            status = (
                "INVALID_HIERARCHY"
                if any(g.code == "INVALID_HIERARCHY" for g in initial_gaps)
                else "INVALID_KEY_BASIS"
            )
            if status == "INVALID_HIERARCHY":
                summary.invalid_hierarchy += 1
            else:
                summary.invalid_key_basis += 1
        elif len(duplicate) > 1:
            status = "MULTI_PROCESS"
            summary.multi_process += 1
        elif impl:
            status = "IMPLEMENTED"
            summary.implemented += 1
        elif unm:
            status = "UNMODELED"
            summary.unmodeled += 1
        else:
            status = "UNCOVERED"
            summary.uncovered += 1
        out.append(
            KeyActivityCoverageOut(
                id=activity.id,
                code=activity.code,
                name=activity.name,
                parent_id=activity.parent_id,
                key_basis=basis,
                key_basis_source=source,
                coverage_status=status,
                coverage_status_label=STATUS_LABELS[status],
                implementations=impl,
                unmodeled=unm,
                duplicate_processes=duplicate,
                gap_owner_positions=owners,
                gaps=gaps,
            )
        )
    related_l2_ids = {
        row.parent_id
        for row in l3.values()
        if any(activity.parent_id == row.id for activity, *_ in activities.values())
    }
    boundaries = _boundaries(
        db, [row for row in rows.values() if row.level == 2 and row.id in related_l2_ids]
    )
    summary.unreviewed = sum(item.status == "UNREVIEWED" for item in boundaries)
    summary.evidence_incomplete = sum(item.status == "EVIDENCE_INCOMPLETE" for item in boundaries)
    return KeyProcessCoverageOut(
        generated_at=utcnow(),
        summary=summary,
        activities=out,
        boundary_reviews=boundaries,
        labels={
            "coverage_status": STATUS_LABELS,
            "boundary_status": BOUNDARY_LABELS,
            "gap": GAP_LABELS,
        },
    )
