"""流程执行引擎：单令牌顺序执行 + 任务队列。

当前版本刻意保持简单，先跑通「实例 → 待办任务 → 完成 → 下一任务」：

- 一个实例同一时刻只有一个 OPEN 任务；
- 节点有多条出边时，由处理人在完成时选择下一步（`next_node_key`）；
- 并行网关、子流程、定时器、自动规则留到后续版本；
- 实例启动时快照流程模型，运行中的实例不受设计器后续修改影响。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.enums import InstanceStatus, NodeType, Role, TaskStatus
from app.models.execution import ProcessInstance, ProcessTask
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.project import Project
from app.models.user import User
from app.schemas.execution import (
    ExecutableProcessOut,
    InstanceDetail,
    InstanceOut,
    InstanceStartRequest,
    NextOption,
    TaskCompleteRequest,
    TaskOut,
)

INSTANCE_LABELS = {
    InstanceStatus.RUNNING.value: "运行中",
    InstanceStatus.COMPLETED.value: "已完成",
    InstanceStatus.CANCELLED.value: "已取消",
}

TASK_LABELS = {
    TaskStatus.PENDING.value: "待认领",
    TaskStatus.CLAIMED.value: "处理中",
    TaskStatus.COMPLETED.value: "已完成",
    TaskStatus.CANCELLED.value: "已取消",
}

TASK_TYPE_LABELS = {
    NodeType.START.value: "开始",
    NodeType.END.value: "结束",
    NodeType.TASK.value: "作业",
    NodeType.APPROVAL.value: "审批",
    NodeType.WAIT.value: "等待",
    NodeType.DECISION.value: "判断",
    NodeType.HANDOFF.value: "移交",
}

OPEN_STATUSES = (TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)
MANAGER_ROLES = {Role.ADMIN.value, Role.MANAGER.value}


def _is_manager(user: User) -> bool:
    return user.role in MANAGER_ROLES


def _next_instance_code(db: Session) -> str:
    prefix = f"PI-{date.today().year}-"
    existing = db.scalars(
        select(ProcessInstance.code).where(ProcessInstance.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def _snapshot(db: Session, process: ProcessArch) -> dict:
    nodes = db.scalars(
        select(ProcessNode)
        .where(ProcessNode.process_id == process.id)
        .order_by(ProcessNode.sequence_order, ProcessNode.id)
    ).all()
    edges = db.scalars(select(ProcessEdge).where(ProcessEdge.process_id == process.id)).all()
    return {
        "nodes": [
            {
                "key": n.node_key,
                "name": n.name,
                "type": n.node_type,
                "lane": n.lane,
                "owner": n.owner_role,
            }
            for n in nodes
        ],
        "edges": [
            {
                "src": e.source_key,
                "dst": e.target_key,
                "label": e.label,
                "condition": e.condition,
                "probability": e.probability,
            }
            for e in edges
        ],
    }


def _node_map(snapshot: dict) -> Dict[str, dict]:
    return {n["key"]: n for n in snapshot.get("nodes", [])}


def _outgoing(snapshot: dict, node_key: str) -> List[dict]:
    edges = [e for e in snapshot.get("edges", []) if e.get("src") == node_key]
    return sorted(edges, key=lambda e: -(e.get("probability") or 0))


def _start_node(snapshot: dict) -> dict:
    nodes = snapshot.get("nodes", [])
    if not nodes:
        raise HTTPException(status_code=400, detail="流程没有节点，无法启动")
    starts = [n for n in nodes if n.get("type") == NodeType.START.value]
    if len(starts) > 1:
        raise HTTPException(status_code=400, detail="流程有多个开始节点，当前执行引擎只支持单入口")
    if starts:
        return starts[0]
    targets = {e.get("dst") for e in snapshot.get("edges", [])}
    sources = [n for n in nodes if n["key"] not in targets and n.get("type") != NodeType.END.value]
    if len(sources) == 1:
        return sources[0]
    if not sources:
        raise HTTPException(status_code=400, detail="流程没有入口节点，无法启动")
    raise HTTPException(status_code=400, detail="流程有多个入口节点，当前执行引擎只支持单入口")


def _assign_user(db: Session, assignee_user_id: Optional[int]) -> Optional[User]:
    if assignee_user_id is None:
        return None
    user = db.get(User, assignee_user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="assignee_user_id 指向的用户不存在")
    return user


def _create_task(
    db: Session,
    instance: ProcessInstance,
    node: dict,
    assignee_user_id: Optional[int],
) -> ProcessTask:
    assignee = _assign_user(db, assignee_user_id)
    task = ProcessTask(
        instance_id=instance.id,
        node_key=node["key"],
        name=node["name"],
        task_type=node.get("type") or NodeType.TASK.value,
        lane=node.get("lane"),
        candidate_role=node.get("owner") or node.get("lane"),
        status=TaskStatus.CLAIMED.value if assignee else TaskStatus.PENDING.value,
        assignee_user_id=assignee.id if assignee else None,
        assignee_name=assignee.display_name if assignee else None,
        claimed_at=utcnow() if assignee else None,
    )
    db.add(task)
    instance.current_node_key = node["key"]
    instance.current_node_name = node["name"]
    instance.status = InstanceStatus.RUNNING.value
    db.flush()
    return task


def _complete_instance(instance: ProcessInstance) -> None:
    instance.status = InstanceStatus.COMPLETED.value
    instance.current_node_key = None
    instance.current_node_name = None
    instance.completed_at = utcnow()


def _advance(
    db: Session,
    instance: ProcessInstance,
    node_key: str,
    assignments: Optional[Dict[str, int]] = None,
) -> Optional[ProcessTask]:
    """从 node_key 开始推进，直到创建任务或实例结束。"""
    nodes = _node_map(instance.snapshot)
    guard = 0
    current = node_key
    while guard < 100:
        guard += 1
        node = nodes.get(current)
        if node is None:
            raise HTTPException(status_code=400, detail=f"流程模型缺少节点 {current}")
        node_type = node.get("type")
        if node_type == NodeType.END.value:
            _complete_instance(instance)
            db.flush()
            return None
        if node_type == NodeType.START.value:
            outgoing = _outgoing(instance.snapshot, current)
            if not outgoing:
                _complete_instance(instance)
                db.flush()
                return None
            if len(outgoing) > 1:
                raise HTTPException(
                    status_code=400, detail="开始节点有多条出边，当前执行引擎无法自动选择"
                )
            current = outgoing[0]["dst"]
            continue
        return _create_task(db, instance, node, (assignments or {}).get(current))
    raise HTTPException(status_code=400, detail="流程疑似存在无法退出的自动节点环路")


def start_instance(
    db: Session,
    process: ProcessArch,
    user: User,
    payload: InstanceStartRequest,
) -> ProcessInstance:
    snapshot = _snapshot(db, process)
    start = _start_node(snapshot)
    if payload.project_id is not None and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=400, detail="project_id 指向的项目不存在")
    instance = ProcessInstance(
        code=_next_instance_code(db),
        process_id=process.id,
        process_name=process.name,
        project_id=payload.project_id,
        status=InstanceStatus.RUNNING.value,
        definition_version=process.model_version,
        snapshot=snapshot,
        variables=payload.variables or {},
        started_by_id=user.id,
        started_by_name=user.display_name,
    )
    db.add(instance)
    db.flush()
    _advance(db, instance, start["key"], payload.assignments)
    return instance


def _ensure_task_action(task: ProcessTask, user: User) -> None:
    if task.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="任务已结束，不能再操作")
    if (
        task.assignee_user_id is not None
        and task.assignee_user_id != user.id
        and not _is_manager(user)
    ):
        raise HTTPException(
            status_code=403,
            detail=f"任务已指派给 {task.assignee_name or '其他用户'}，只有本人或流程管理科可以处理",
        )


def claim_task(db: Session, task: ProcessTask, user: User) -> ProcessTask:
    _ensure_task_action(task, user)
    task.assignee_user_id = user.id
    task.assignee_name = user.display_name
    task.status = TaskStatus.CLAIMED.value
    task.claimed_at = task.claimed_at or utcnow()
    db.flush()
    return task


def complete_task(
    db: Session,
    task: ProcessTask,
    user: User,
    payload: TaskCompleteRequest,
) -> ProcessTask:
    _ensure_task_action(task, user)
    instance = task.instance
    if instance.status != InstanceStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="流程实例已结束，不能再处理任务")

    if task.assignee_user_id is None:
        task.assignee_user_id = user.id
        task.assignee_name = user.display_name
        task.claimed_at = utcnow()

    outgoing = _outgoing(instance.snapshot, task.node_key)
    next_key: Optional[str] = None
    if len(outgoing) == 1:
        next_key = outgoing[0]["dst"]
    elif len(outgoing) > 1:
        if not payload.next_node_key:
            options = "、".join(f"{e['dst']}" for e in outgoing)
            raise HTTPException(
                status_code=400,
                detail=f"该节点有多个分支，请用 next_node_key 指定下一步（可选：{options}）",
            )
        targets = {e["dst"] for e in outgoing}
        if payload.next_node_key not in targets:
            raise HTTPException(
                status_code=400,
                detail=f"next_node_key 不在该节点的出边目标中（可选：{'、'.join(sorted(targets))}）",
            )
        next_key = payload.next_node_key

    task.status = TaskStatus.COMPLETED.value
    task.completed_at = utcnow()
    task.completed_by_id = user.id
    task.completed_by_name = user.display_name
    task.form_data = payload.form_data
    task.comment = payload.comment
    if payload.variables:
        instance.variables = {**(instance.variables or {}), **payload.variables}
    db.flush()

    if next_key is None:
        _complete_instance(instance)
        db.flush()
    else:
        _advance(db, instance, next_key)
    return task


def assign_task(db: Session, task: ProcessTask, assignee_user_id: Optional[int]) -> ProcessTask:
    if task.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="任务已结束，不能改派")
    if assignee_user_id is None:
        task.assignee_user_id = None
        task.assignee_name = None
        task.status = TaskStatus.PENDING.value
        task.claimed_at = None
    else:
        assignee = _assign_user(db, assignee_user_id)
        assert assignee is not None
        task.assignee_user_id = assignee.id
        task.assignee_name = assignee.display_name
        task.status = TaskStatus.CLAIMED.value
        task.claimed_at = task.claimed_at or utcnow()
    db.flush()
    return task


def cancel_instance(db: Session, instance: ProcessInstance) -> ProcessInstance:
    if instance.status != InstanceStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="只有运行中的实例可以取消")
    instance.status = InstanceStatus.CANCELLED.value
    instance.completed_at = utcnow()
    instance.current_node_key = None
    instance.current_node_name = None
    for task in instance.tasks:
        if task.status in OPEN_STATUSES:
            task.status = TaskStatus.CANCELLED.value
            task.completed_at = utcnow()
    db.flush()
    return instance


# ------------------------------------------------------------------ 查询与序列化


def executable_processes(db: Session) -> List[ExecutableProcessOut]:
    counts = dict(
        db.execute(
            select(ProcessNode.process_id, func.count(ProcessNode.id)).group_by(
                ProcessNode.process_id
            )
        ).all()
    )
    rows = db.scalars(
        select(ProcessArch).where(ProcessArch.id.in_(counts.keys())).order_by(ProcessArch.code)
    ).all()
    return [
        ExecutableProcessOut(
            id=p.id,
            code=p.code,
            name=p.name,
            level=p.level,
            node_count=counts.get(p.id, 0),
            model_version=p.model_version,
        )
        for p in rows
    ]


def task_out(task: ProcessTask) -> TaskOut:
    instance = task.instance
    node = _node_map(instance.snapshot).get(task.node_key, {})
    options = [
        NextOption(
            node_key=e["dst"],
            name=_node_map(instance.snapshot).get(e["dst"], {}).get("name", e["dst"]),
            label=e.get("label"),
            condition=e.get("condition"),
            probability=e.get("probability") or 1.0,
        )
        for e in _outgoing(instance.snapshot, task.node_key)
    ]
    return TaskOut(
        id=task.id,
        instance_id=instance.id,
        instance_code=instance.code,
        process_id=instance.process_id,
        process_name=instance.process_name,
        node_key=task.node_key,
        name=task.name,
        task_type=task.task_type,
        task_type_label=TASK_TYPE_LABELS.get(task.task_type, task.task_type),
        lane=task.lane or node.get("lane"),
        candidate_role=task.candidate_role,
        status=task.status,
        status_label=TASK_LABELS.get(task.status, task.status),
        assignee_user_id=task.assignee_user_id,
        assignee_name=task.assignee_name,
        created_at=task.created_at,
        claimed_at=task.claimed_at,
        due_at=task.due_at,
        completed_at=task.completed_at,
        completed_by_name=task.completed_by_name,
        form_data=task.form_data,
        comment=task.comment,
        next_options=options,
    )


def instance_out(instance: ProcessInstance) -> InstanceOut:
    tasks = instance.tasks
    return InstanceOut(
        id=instance.id,
        code=instance.code,
        process_id=instance.process_id,
        process_name=instance.process_name,
        project_id=instance.project_id,
        status=instance.status,
        status_label=INSTANCE_LABELS.get(instance.status, instance.status),
        current_node_key=instance.current_node_key,
        current_node_name=instance.current_node_name,
        definition_version=instance.definition_version,
        started_by_name=instance.started_by_name,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        task_count=len(tasks),
        open_task_count=sum(1 for t in tasks if t.status in OPEN_STATUSES),
    )


def instance_detail(instance: ProcessInstance) -> InstanceDetail:
    return InstanceDetail(
        instance=instance_out(instance),
        tasks=[task_out(t) for t in instance.tasks],
        variables=instance.variables,
    )


def list_tasks(
    db: Session,
    status: Optional[str] = None,
    assignee_user_id: Optional[int] = None,
    instance_id: Optional[int] = None,
    process_id: Optional[int] = None,
    only_open: bool = False,
    limit: int = 200,
) -> List[TaskOut]:
    stmt = select(ProcessTask).join(ProcessInstance, ProcessTask.instance_id == ProcessInstance.id)
    if status:
        stmt = stmt.where(ProcessTask.status == status)
    if only_open:
        stmt = stmt.where(ProcessTask.status.in_(OPEN_STATUSES))
    if assignee_user_id is not None:
        stmt = stmt.where(ProcessTask.assignee_user_id == assignee_user_id)
    if instance_id is not None:
        stmt = stmt.where(ProcessTask.instance_id == instance_id)
    if process_id is not None:
        stmt = stmt.where(ProcessInstance.process_id == process_id)
    rows = db.scalars(
        stmt.order_by(ProcessTask.created_at.desc(), ProcessTask.id.desc()).limit(limit)
    ).all()
    return [task_out(t) for t in rows]


def list_instances(
    db: Session,
    status: Optional[str] = None,
    process_id: Optional[int] = None,
    limit: int = 100,
) -> List[InstanceOut]:
    stmt = select(ProcessInstance)
    if status:
        stmt = stmt.where(ProcessInstance.status == status)
    if process_id is not None:
        stmt = stmt.where(ProcessInstance.process_id == process_id)
    rows = db.scalars(
        stmt.order_by(ProcessInstance.started_at.desc(), ProcessInstance.id.desc()).limit(limit)
    ).all()
    return [instance_out(i) for i in rows]


def get_task(db: Session, task_id: int) -> ProcessTask:
    task = db.get(ProcessTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def get_instance(db: Session, instance_id: int) -> ProcessInstance:
    instance = db.get(ProcessInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="流程实例不存在")
    return instance
