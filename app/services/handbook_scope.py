"""手册作业归属：只投影原发布节点与显式职责，不用工时推导执行。"""

from fastapi import HTTPException
from sqlalchemy import select

from app.models.org import Position
from app.models.process import ProcessArch
from app.models.process_task import ProcessTaskDefinition
from app.models.raci import GovernanceRole, RaciAssignment
from app.services import asset_graph, binding_readiness, org_access, process_model
from app.services.position_coverage import role_position
from app.services.raci import RACI_LABELS

SUBJECTS = {"POSITION": (Position, "岗位"), "ROLE": (GovernanceRole, "治理角色")}


def subject(db, scope, subject_id, user):
    if scope not in SUBJECTS:
        raise HTTPException(400, "手册主体只支持岗位或治理角色")
    model, label = SUBJECTS[scope]
    row = db.get(model, subject_id)
    if row is None:
        raise HTTPException(404, "手册主体不存在")
    org_access.ensure_visible(db, user, row.org_unit_id)
    return row, {
        "scope": scope,
        "scope_label": label,
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "org_unit_id": row.org_unit_id,
        "is_active": row.is_active,
    }


def collect(db, scope: str, subject_id: int, user) -> dict:
    owner, identity = subject(db, scope, subject_id, user)
    result = {"subject": identity, "processes": [], "steps": [], "collaboration": [], "gaps": []}
    if not owner.is_active:
        result["gaps"].append({"code": "SUBJECT_INACTIVE", "message": "手册主体已停用"})
    processes = db.scalars(
        org_access.restrict(
            select(ProcessArch).where(ProcessArch.level == 3, ProcessArch.is_draft.is_(False)),
            db,
            user,
            ProcessArch.org_unit_id,
        ).order_by(ProcessArch.code, ProcessArch.id)
    ).all()
    for process in processes:
        version = asset_graph.published_model(db, process)
        if version is None:
            # 不借设计器GET补建基线，也不把未发布作业编入正式依据。
            continue
        bindings = binding_readiness.activity_bindings(
            db, process.id, user, model_version_id=version.id
        )
        mapped = {n.node_key: n for n in bindings.nodes}
        nodes, _ = process_model.rows_from_snapshot(process.id, version.snapshot or {})
        assignments = list(
            db.scalars(
                org_access.restrict(
                    select(RaciAssignment)
                    .join(GovernanceRole)
                    .where(
                        RaciAssignment.process_id == process.id, GovernanceRole.is_active.is_(True)
                    ),
                    db,
                    user,
                    GovernanceRole.org_unit_id,
                ).order_by(RaciAssignment.id)
            ).all()
        )
        mine = [
            r
            for r in assignments
            if (
                r.role_id == subject_id
                if scope == "ROLE"
                else role_position(db, r.role) == subject_id
            )
        ]
        before = len(result["steps"])
        local_collaboration = []
        activity_ids = set()
        for node in nodes:
            if node.node_key not in mapped:
                continue
            aids = mapped[node.node_key].activity_ids
            specific = [r for r in assignments if r.node_key == node.node_key and r.raci == "R"]
            relevant = [
                r
                for r in mine
                if r.node_key == node.node_key or r.activity_id in aids and r.node_key is None
            ]
            for row in relevant:
                if row.raci != "R":
                    local_collaboration.append(
                        {
                            "id": row.id,
                            "raci": row.raci,
                            "raci_label": RACI_LABELS[row.raci],
                            "process_id": process.id,
                            "model_version_id": version.id,
                            "node_key": node.node_key,
                            "activity_id": row.activity_id,
                            "role_id": row.role_id,
                            "role_name": row.role.name,
                        }
                    )
            explicit = scope == "POSITION" and node.owner_position_id == subject_id
            chosen = [r for r in relevant if r.raci == "R" and (not specific or r in specific)]
            if scope == "POSITION" and node.owner_position_id not in {None, subject_id}:
                chosen = []
            if (
                scope == "ROLE"
                and node.owner_position_id
                and role_position(db, owner) != node.owner_position_id
            ):
                chosen = []
            if not explicit and not chosen:
                continue
            activity_ids.update(aids)
            basis = (
                "节点责任岗位（不自动等于R）"
                if explicit
                else "节点RACI-R"
                if any(r.node_key for r in chosen)
                else "活动RACI-R"
            )
            result["steps"].append(
                {
                    "key": f"{process.id}:NODE:{node.node_key}",
                    "process_id": process.id,
                    "process_code": process.code,
                    "process_name": process.name,
                    "model_version_id": version.id,
                    "node_key": node.node_key,
                    "task_id": None,
                    "activity_ids": aids,
                    "name": node.name,
                    "instruction": node.description or "",
                    "assignment_label": basis,
                    "raci_ids": [r.id for r in chosen],
                    "owner_position_id": node.owner_position_id,
                    "node_type": node.node_type,
                    "mapping_blockers": mapped[node.node_key].blockers,
                }
            )
        if scope == "POSITION":
            tasks = db.scalars(
                select(ProcessTaskDefinition)
                .join(ProcessArch, ProcessArch.id == ProcessTaskDefinition.activity_id)
                .where(
                    ProcessArch.parent_id == process.id,
                    ProcessArch.is_draft.is_(False),
                    ProcessTaskDefinition.position_id == subject_id,
                    ProcessTaskDefinition.is_active.is_(True),
                )
                .order_by(
                    ProcessTaskDefinition.activity_id,
                    ProcessTaskDefinition.sort_order,
                    ProcessTaskDefinition.id,
                )
            ).all()
            for task in tasks:
                activity_ids.add(task.activity_id)
                result["steps"].append(
                    {
                        "key": f"{process.id}:TASK:{task.id}",
                        "process_id": process.id,
                        "process_code": process.code,
                        "process_name": process.name,
                        "model_version_id": version.id,
                        "node_key": None,
                        "task_id": task.id,
                        "activity_ids": [task.activity_id],
                        "name": task.name,
                        "instruction": task.description or "",
                        "assignment_label": "任务定义岗位（不推定模型节点）",
                        "raci_ids": [],
                        "owner_position_id": subject_id,
                        "node_type": "TASK_DEFINITION",
                        "mapping_blockers": [],
                    }
                )
        # 流程事项只有协作身份，不按名称猜活动。
        local_collaboration.extend(
            {
                "id": r.id,
                "raci": r.raci,
                "raci_label": RACI_LABELS[r.raci],
                "process_id": process.id,
                "model_version_id": version.id,
                "node_key": None,
                "activity_id": None,
                "role_id": r.role_id,
                "role_name": r.role.name,
            }
            for r in mine
            if not r.activity_id and not r.node_key
        )
        unique = {row["id"]: row for row in local_collaboration}
        result["collaboration"].extend(unique.values())
        if len(result["steps"]) > before or local_collaboration:
            result["processes"].append(
                {
                    "id": process.id,
                    "code": process.code,
                    "name": process.name,
                    "model_version_id": version.id,
                    "activity_ids": sorted(activity_ids),
                }
            )
    if not result["steps"]:
        result["gaps"].append(
            {
                "code": "NO_EXECUTION_STEPS",
                "message": "未发现明确归属的已发布作业步骤；不代表岗位或角色没有职责",
            }
        )
    return result
