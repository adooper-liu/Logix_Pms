"""流程执行引擎：单令牌顺序执行 + 任务队列。

当前版本刻意保持简单，先跑通「实例 → 待办任务 → 完成 → 下一任务」：

- 一个实例同一时刻只有一个 OPEN 任务；
- 节点有多条出边时，由处理人在完成时选择下一步（`next_node_key`）；
- 并行网关、子流程、定时器、自动规则留到后续版本；
- 实例启动时快照流程模型，运行中的实例不受设计器后续修改影响。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import utcnow
from app.models.enums import InstanceStatus, NodeType, Role, TaskStatus
from app.models.execution import (
    NodeAssignment,
    ProcessExecutionConfig,
    ProcessInstance,
    ProcessTask,
    ProcessTaskEvent,
    TaskWorklog,
)
from app.models.org import OrgUnit
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.project import Project
from app.models.user import ROLE_LABELS, User
from app.schemas.execution import (
    ExecutableProcessOut,
    InstanceDetail,
    InstanceOut,
    InstanceStartRequest,
    NextOption,
    TaskCompleteRequest,
    TaskEventOut,
    TaskOut,
    WorkloadSummary,
    WorkloadSummaryRow,
    WorklogCreate,
    WorklogOut,
)
from app.services import compensation as compensation_service
from app.services import forms as forms_service
from app.services import org_scope

INSTANCE_LABELS = {
    InstanceStatus.RUNNING.value: "运行中",
    InstanceStatus.SUSPENDED.value: "已挂起",
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

TASK_EVENT_LABELS = {
    "CREATED": "创建",
    "CLAIMED": "认领",
    "RELEASED": "退回队列",
    "ASSIGNED": "改派",
    "ESCALATED": "升级",
    "SLA_SHIFTED": "SLA 顺延",
    "COMPLETED": "完成",
    "CANCELLED": "取消",
}

OPEN_STATUSES = (TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)
MANAGER_ROLES = {Role.ADMIN.value, Role.MANAGER.value}
ROLE_CANDIDATES = {role.value for role in Role} | set(ROLE_LABELS.values())


def _is_manager(user: User) -> bool:
    return user.role in MANAGER_ROLES


def _candidate_matches(db: Session, user: User, candidate: Optional[str]) -> bool:
    """候选角色/泳道校验。

    节点的 owner_role/lane 是自由文本，不能假设它一定是系统角色：
    - 空、或管理者：直接放行；
    - 命中系统角色值/标签：要求角色一致；
    - 命中用户部门/组织：放行；
    - 如果系统里确实有人以该值作为部门或组织：说明它是可识别的分组，其他人不放行；
    - 其余无法识别的自由文本不硬拦，避免历史节点全部卡死，交给改派处理。
    """
    if not candidate or _is_manager(user):
        return True
    if candidate in ROLE_CANDIDATES:
        return user.role == candidate or ROLE_LABELS.get(user.role) == candidate
    org_name = user.org_unit.name if user.org_unit else None
    if candidate in {user.department, org_name}:
        return True
    department_exists = (
        db.scalar(select(func.count()).select_from(User).where(User.department == candidate)) or 0
    )
    if department_exists:
        return False
    org_exists = (
        db.scalar(select(func.count()).select_from(OrgUnit).where(OrgUnit.name == candidate)) or 0
    )
    return not org_exists


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
    config = db.scalar(
        select(ProcessExecutionConfig)
        .options(joinedload(ProcessExecutionConfig.default_escalation_user))
        .where(ProcessExecutionConfig.process_id == process.id)
    )
    assignment_rows = db.scalars(
        select(NodeAssignment)
        .options(
            joinedload(NodeAssignment.org_unit),
            joinedload(NodeAssignment.default_assignee),
            joinedload(NodeAssignment.escalation_user),
        )
        .where(
            NodeAssignment.process_id == process.id,
            NodeAssignment.is_active.is_(True),
        )
    ).all()
    assignments = {
        row.node_key: {
            "role": row.role,
            "role_label": ROLE_LABELS.get(row.role, row.role) if row.role else None,
            "org_unit_id": row.org_unit_id,
            "org_name": row.org_unit.name if row.org_unit else None,
            "default_user_id": row.default_assignee_user_id,
            "default_user_name": (
                row.default_assignee.display_name if row.default_assignee else None
            ),
            "due_hours": row.due_hours,
            "escalation_hours": row.escalation_hours,
            "escalation_user_id": row.escalation_user_id,
            "escalation_user_name": (
                row.escalation_user.display_name if row.escalation_user else None
            ),
        }
        for row in assignment_rows
    }
    return {
        "nodes": [
            {
                "key": n.node_key,
                "name": n.name,
                "type": n.node_type,
                "lane": n.lane,
                "owner": n.owner_role,
                "standard_minutes": n.duration_minutes,
                "activity_id": n.process_arch_id,
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
        "forms": forms_service.form_snapshot(db, process.id),
        "rules": forms_service.rule_snapshot(db, process.id),
        "assignments": assignments,
        "config": {
            "task_due_hours": config.default_task_due_hours if config else None,
            "escalation_hours": config.default_escalation_hours if config else None,
            "escalation_user_id": config.default_escalation_user_id if config else None,
            "escalation_user_name": (
                config.default_escalation_user.display_name
                if config and config.default_escalation_user
                else None
            ),
        },
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


def lock_instance(db: Session, instance_id: int) -> None:
    """锁住实例行，串行化同一实例上的任务动作与实例控制。"""
    db.execute(
        select(ProcessInstance.id).where(ProcessInstance.id == instance_id).with_for_update()
    )


def record_task_event(
    db: Session,
    task: ProcessTask,
    event_type: str,
    from_status: Optional[str],
    to_status: Optional[str],
    actor: Optional[User],
    detail: Optional[dict] = None,
) -> ProcessTaskEvent:
    event = ProcessTaskEvent(
        task_id=task.id,
        instance_id=task.instance_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor.id if actor else None,
        actor_name=actor.display_name if actor else "系统",
        detail=detail or {},
    )
    db.add(event)
    db.flush()
    return event


def _claim_update(
    db: Session,
    task: ProcessTask,
    *,
    assignee: Optional[User],
    status: str,
    claimed_at,
    extra: Optional[dict] = None,
) -> bool:
    """条件更新任务，防止并发覆盖；返回是否更新成功。"""
    values = {
        "assignee_user_id": assignee.id if assignee else None,
        "assignee_name": assignee.display_name if assignee else None,
        "status": status,
        "claimed_at": claimed_at,
        "row_version": ProcessTask.row_version + 1,
    }
    if extra:
        values.update(extra)
    result = db.execute(
        update(ProcessTask)
        .where(
            ProcessTask.id == task.id,
            ProcessTask.status.in_(OPEN_STATUSES),
            ProcessTask.row_version == task.row_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False
    db.flush()
    db.refresh(task)
    return True


def _create_task(
    db: Session,
    instance: ProcessInstance,
    node: dict,
    assignee_user_id: Optional[int],
    actor: Optional[User] = None,
) -> ProcessTask:
    assignment = (instance.snapshot.get("assignments") or {}).get(node["key"], {})
    assignee = _assign_user(db, assignee_user_id) if assignee_user_id else None
    if assignee is None and assignment.get("default_user_id"):
        default_user = db.get(User, assignment["default_user_id"])
        if default_user is not None and default_user.is_active:
            assignee = default_user
    due_hours = assignment.get("due_hours")
    if due_hours is None:
        due_hours = (instance.snapshot.get("config") or {}).get("task_due_hours")
    candidate_text = (
        assignment.get("role_label")
        or assignment.get("org_name")
        or node.get("owner")
        or node.get("lane")
    )
    task = ProcessTask(
        instance_id=instance.id,
        node_key=node["key"],
        name=node["name"],
        task_type=node.get("type") or NodeType.TASK.value,
        lane=node.get("lane"),
        activity_id=node.get("activity_id"),
        candidate_role=candidate_text,
        candidate_role_code=assignment.get("role"),
        candidate_org_unit_id=assignment.get("org_unit_id"),
        status=TaskStatus.CLAIMED.value if assignee else TaskStatus.PENDING.value,
        assignee_user_id=assignee.id if assignee else None,
        assignee_name=assignee.display_name if assignee else None,
        claimed_at=utcnow() if assignee else None,
        due_at=utcnow() + timedelta(hours=due_hours) if due_hours is not None else None,
    )
    db.add(task)
    instance.current_node_key = node["key"]
    instance.current_node_name = node["name"]
    instance.status = InstanceStatus.RUNNING.value
    db.flush()
    record_task_event(
        db,
        task,
        "CREATED",
        None,
        task.status,
        actor,
        {
            "node_key": task.node_key,
            "assignee_user_id": task.assignee_user_id,
            "assignee_name": task.assignee_name,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        },
    )
    return task


def _complete_instance(db: Session, instance: ProcessInstance) -> None:
    instance.status = InstanceStatus.COMPLETED.value
    instance.current_node_key = None
    instance.current_node_name = None
    instance.completed_at = utcnow()
    db.flush()
    from app.services import kpi as kpi_service

    kpi_service.record_completed_instance(db, instance)


def _advance(
    db: Session,
    instance: ProcessInstance,
    node_key: str,
    assignments: Optional[Dict[str, int]] = None,
    actor: Optional[User] = None,
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
            _complete_instance(db, instance)
            db.flush()
            return None
        if node_type == NodeType.START.value:
            outgoing = _outgoing(instance.snapshot, current)
            if not outgoing:
                _complete_instance(db, instance)
                db.flush()
                return None
            if len(outgoing) > 1:
                raise HTTPException(
                    status_code=400, detail="开始节点有多条出边，当前执行引擎无法自动选择"
                )
            current = outgoing[0]["dst"]
            continue
        return _create_task(db, instance, node, (assignments or {}).get(current), actor=actor)
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
        definition_version=process.published_model_version or process.model_version,
        snapshot=snapshot,
        variables=payload.variables or {},
        started_by_id=user.id,
        started_by_name=user.display_name,
    )
    db.add(instance)
    db.flush()
    _advance(db, instance, start["key"], payload.assignments, actor=user)
    return instance


def _ensure_task_action(db: Session, task: ProcessTask, user: User) -> None:
    if task.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="任务已结束，不能再操作")
    if task.instance.status == InstanceStatus.SUSPENDED.value:
        raise HTTPException(
            status_code=409,
            detail=f"流程实例已挂起（{task.instance.code}），恢复后才能处理任务",
        )
    if task.instance.status != InstanceStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="流程实例已结束，不能再处理任务")
    if task.assignee_user_id == user.id:
        return
    if task.assignee_user_id is not None and not _is_manager(user):
        raise HTTPException(
            status_code=403,
            detail=f"任务已指派给 {task.assignee_name or '其他用户'}，只有本人或流程管理科可以处理",
        )
    if _is_manager(user):
        return
    if task.candidate_role_code and user.role != task.candidate_role_code:
        raise HTTPException(
            status_code=403,
            detail=(
                f"该任务只允许「{ROLE_LABELS.get(task.candidate_role_code, task.candidate_role_code)}」"
                "角色处理；请联系流程管理科改派"
            ),
        )
    if task.candidate_org_unit_id:
        allowed_orgs = org_scope.ancestor_ids(db, user.org_unit_id) if user.org_unit_id else set()
        if task.candidate_org_unit_id not in allowed_orgs:
            raise HTTPException(
                status_code=403,
                detail="该任务限定在指定组织范围内处理；请联系流程管理科改派",
            )
    if task.candidate_role_code or task.candidate_org_unit_id:
        return
    if task.assignee_user_id is None and not _candidate_matches(db, user, task.candidate_role):
        raise HTTPException(
            status_code=403,
            detail=(
                f"该任务的候选角色/泳道为「{task.candidate_role}」，当前账号不符合；"
                "请联系流程管理科改派"
            ),
        )


def claim_task(db: Session, task: ProcessTask, user: User) -> ProcessTask:
    lock_instance(db, task.instance_id)
    db.refresh(task)
    _ensure_task_action(db, task, user)
    if task.status == TaskStatus.CLAIMED.value and task.assignee_user_id == user.id:
        return task

    previous_status = task.status
    previous_assignee = task.assignee_name
    updated = _claim_update(
        db,
        task,
        assignee=user,
        status=TaskStatus.CLAIMED.value,
        claimed_at=task.claimed_at or utcnow(),
    )
    if not updated:
        raise HTTPException(status_code=409, detail="任务已被他人处理，请刷新后重试")
    record_task_event(
        db,
        task,
        "CLAIMED",
        previous_status,
        TaskStatus.CLAIMED.value,
        user,
        {
            "assignee_user_id": user.id,
            "assignee_name": user.display_name,
            "previous_assignee": previous_assignee,
        },
    )
    return task


WORKLOG_TYPE_LABELS = {
    "HANDLE": "处理",
    "WAIT": "等待",
    "REWORK": "返工",
    "OTHER": "其他",
}


def worklog_out(row: TaskWorklog) -> WorklogOut:
    return WorklogOut(
        id=row.id,
        task_id=row.task_id,
        user_id=row.user_id,
        user_name=row.user_name,
        work_type=row.work_type,
        work_type_label=WORKLOG_TYPE_LABELS.get(row.work_type, row.work_type),
        started_at=row.started_at,
        ended_at=row.ended_at,
        effort_minutes=row.effort_minutes,
        note=row.note,
        created_at=row.created_at,
    )


def record_worklog(
    db: Session,
    task: ProcessTask,
    user: User,
    payload: WorklogCreate,
) -> TaskWorklog:
    """登记实际工时。开放任务沿用处理权限；已完成任务允许本人/完成人/管理科补录。"""
    if task.status == TaskStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="任务已取消，不能登记工时")
    if task.status in OPEN_STATUSES:
        _ensure_task_action(db, task, user)
    elif not (
        _is_manager(user) or task.completed_by_id == user.id or task.assignee_user_id == user.id
    ):
        raise HTTPException(status_code=403, detail="只有任务处理人或流程管理科可以登记工时")

    effort = payload.effort_minutes
    if effort is None and payload.started_at and payload.ended_at:
        effort = max(0.0, (payload.ended_at - payload.started_at).total_seconds() / 60)
    if effort is None or effort < 0:
        raise HTTPException(status_code=400, detail="请填写实际工时，或提供开始/结束时间")
    if effort > 10080:
        raise HTTPException(status_code=400, detail="单条工时不能超过 10080 分钟")

    work_type = (payload.work_type or "HANDLE").upper()
    if work_type not in WORKLOG_TYPE_LABELS:
        work_type = "OTHER"
    row = TaskWorklog(
        task_id=task.id,
        user_id=user.id,
        user_name=user.display_name,
        work_type=work_type,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        effort_minutes=float(effort),
        note=payload.note,
        created_at=utcnow(),
    )
    db.add(row)
    task.actual_minutes = float(task.actual_minutes or 0) + float(effort)
    db.flush()
    return row


def list_task_worklogs(db: Session, task_id: int) -> List[TaskWorklog]:
    return list(
        db.scalars(
            select(TaskWorklog).where(TaskWorklog.task_id == task_id).order_by(TaskWorklog.id)
        ).all()
    )


def workload_summary(
    db: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    user_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
    process_id: Optional[int] = None,
) -> WorkloadSummary:
    stmt = (
        select(
            TaskWorklog.user_id,
            TaskWorklog.user_name,
            func.count(func.distinct(TaskWorklog.task_id)),
            func.coalesce(func.sum(TaskWorklog.effort_minutes), 0.0),
        )
        .join(ProcessTask, ProcessTask.id == TaskWorklog.task_id)
        .join(ProcessInstance, ProcessInstance.id == ProcessTask.instance_id)
    )
    if from_date is not None:
        stmt = stmt.where(TaskWorklog.created_at >= datetime.combine(from_date, time.min))
    if to_date is not None:
        stmt = stmt.where(
            TaskWorklog.created_at < datetime.combine(to_date + timedelta(days=1), time.min)
        )
    if user_id is not None:
        stmt = stmt.where(TaskWorklog.user_id == user_id)
    if org_unit_id is not None:
        stmt = stmt.where(ProcessTask.candidate_org_unit_id == org_unit_id)
    if process_id is not None:
        stmt = stmt.where(ProcessInstance.process_id == process_id)
    stmt = stmt.group_by(TaskWorklog.user_id, TaskWorklog.user_name).order_by(
        func.sum(TaskWorklog.effort_minutes).desc()
    )
    rows = [
        WorkloadSummaryRow(
            user_id=row[0],
            user_name=row[1],
            task_count=int(row[2] or 0),
            effort_minutes=float(row[3] or 0),
        )
        for row in db.execute(stmt).all()
    ]
    return WorkloadSummary(
        from_date=from_date.isoformat() if from_date else None,
        to_date=to_date.isoformat() if to_date else None,
        total_minutes=round(sum(row.effort_minutes for row in rows), 2),
        rows=rows,
    )


def complete_task(
    db: Session,
    task: ProcessTask,
    user: User,
    payload: TaskCompleteRequest,
) -> ProcessTask:
    lock_instance(db, task.instance_id)
    db.refresh(task)
    _ensure_task_action(db, task, user)
    instance = task.instance
    if instance.status != InstanceStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="流程实例已结束，不能再处理任务")

    outgoing = _outgoing(instance.snapshot, task.node_key)
    form = forms_service.form_for_snapshot(instance.snapshot, task.node_key)
    fields = form.get("fields", []) if form else []
    form_data = forms_service.validate_form_data(fields, payload.form_data)
    context = {**(instance.variables or {}), **form_data}

    next_key: Optional[str] = None
    if payload.next_node_key:
        targets = {e["dst"] for e in outgoing}
        if payload.next_node_key not in targets:
            raise HTTPException(
                status_code=400,
                detail=f"next_node_key 不在该节点的出边目标中（可选：{'、'.join(sorted(targets))}）",
            )
        next_key = payload.next_node_key
    else:
        rule_target = forms_service.evaluate_rules(
            (instance.snapshot.get("rules") or {}).get(task.node_key, []), context
        )
        if rule_target:
            targets = {e["dst"] for e in outgoing}
            if rule_target not in targets:
                raise HTTPException(
                    status_code=400, detail=f"规则目标 {rule_target} 不是该节点的出边目标"
                )
            next_key = rule_target
        elif len(outgoing) == 1:
            next_key = outgoing[0]["dst"]
        elif len(outgoing) > 1:
            options = "、".join(f"{e['dst']}" for e in outgoing)
            raise HTTPException(
                status_code=400,
                detail=f"该节点有多个分支，请用 next_node_key 指定下一步（可选：{options}）",
            )

    # 表单值是流程上下文的一部分：后续节点的规则必须能读到上游填写的数据。
    # 采用扁平合并，后填的字段覆盖先前的；显式传入的 variables 优先级最高。
    merged_variables = {**(instance.variables or {}), **form_data}
    if payload.variables:
        merged_variables.update(payload.variables)

    now = utcnow()
    previous_status = task.status
    updated = _claim_update(
        db,
        task,
        assignee=_assign_user(db, task.assignee_user_id or user.id),
        status=TaskStatus.COMPLETED.value,
        claimed_at=task.claimed_at or now,
        extra={
            "completed_at": now,
            "completed_by_id": user.id,
            "completed_by_name": user.display_name,
            "form_data": form_data,
            "comment": payload.comment,
        },
    )
    if not updated:
        raise HTTPException(status_code=409, detail="任务已被他人处理，请刷新后重试")

    if payload.effort_minutes is not None and payload.effort_minutes > 0:
        task.actual_minutes = float(task.actual_minutes or 0) + float(payload.effort_minutes)
        db.add(
            TaskWorklog(
                task_id=task.id,
                user_id=user.id,
                user_name=user.display_name,
                work_type="HANDLE",
                started_at=task.claimed_at or now,
                ended_at=now,
                effort_minutes=float(payload.effort_minutes),
                note="完成任务时登记",
                created_at=now,
            )
        )
        db.flush()

    instance.variables = merged_variables
    record_task_event(
        db,
        task,
        "COMPLETED",
        previous_status,
        TaskStatus.COMPLETED.value,
        user,
        {
            "comment": payload.comment,
            "next_node_key": next_key,
            "form_data": form_data,
        },
    )

    if next_key is None:
        _complete_instance(db, instance)
        db.flush()
    else:
        _advance(db, instance, next_key, actor=user)
    return task


def assign_task(
    db: Session,
    task: ProcessTask,
    assignee_user_id: Optional[int],
    actor: Optional[User] = None,
) -> ProcessTask:
    lock_instance(db, task.instance_id)
    db.refresh(task)
    if task.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="任务已结束，不能改派")
    assignee = _assign_user(db, assignee_user_id) if assignee_user_id is not None else None
    previous_status = task.status
    previous_assignee = task.assignee_name
    target_status = TaskStatus.CLAIMED.value if assignee else TaskStatus.PENDING.value
    updated = _claim_update(
        db,
        task,
        assignee=assignee,
        status=target_status,
        claimed_at=(task.claimed_at or utcnow()) if assignee else None,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="任务已被他人处理，请刷新后重试")
    record_task_event(
        db,
        task,
        "ASSIGNED" if assignee else "RELEASED",
        previous_status,
        target_status,
        actor,
        {
            "previous_assignee": previous_assignee,
            "assignee_user_id": assignee.id if assignee else None,
            "assignee_name": assignee.display_name if assignee else None,
        },
    )
    return task


def cancel_instance(
    db: Session, instance: ProcessInstance, actor: Optional[User] = None
) -> ProcessInstance:
    lock_instance(db, instance.id)
    db.refresh(instance)
    if instance.status not in (
        InstanceStatus.RUNNING.value,
        InstanceStatus.SUSPENDED.value,
    ):
        raise HTTPException(status_code=409, detail="只有运行中或已挂起的实例可以取消")
    now = utcnow()
    instance.status = InstanceStatus.CANCELLED.value
    instance.completed_at = now
    instance.current_node_key = None
    instance.current_node_name = None
    for task in instance.tasks:
        if task.status in OPEN_STATUSES:
            previous_status = task.status
            task.status = TaskStatus.CANCELLED.value
            task.completed_at = now
            task.row_version = (task.row_version or 0) + 1
            record_task_event(
                db,
                task,
                "CANCELLED",
                previous_status,
                TaskStatus.CANCELLED.value,
                actor,
                {"reason": "instance_cancelled"},
            )
    compensation_service.create_records_on_cancel(db, instance)
    db.flush()
    return instance


def suspend_instance(
    db: Session, instance: ProcessInstance, reason: Optional[str] = None
) -> ProcessInstance:
    lock_instance(db, instance.id)
    db.refresh(instance)
    if instance.status != InstanceStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="只有运行中的实例可以挂起")
    instance.status = InstanceStatus.SUSPENDED.value
    instance.suspended_at = utcnow()
    instance.suspend_reason = reason
    db.flush()
    return instance


def resume_instance(
    db: Session, instance: ProcessInstance, actor: Optional[User] = None
) -> ProcessInstance:
    lock_instance(db, instance.id)
    db.refresh(instance)
    if instance.status != InstanceStatus.SUSPENDED.value:
        raise HTTPException(status_code=409, detail="只有已挂起的实例可以恢复")
    now = utcnow()
    paused = now - instance.suspended_at if instance.suspended_at else timedelta(0)
    instance.status = InstanceStatus.RUNNING.value
    instance.suspended_at = None
    instance.suspend_reason = None
    # 挂起期间不消耗 SLA：恢复时把未完成任务的到期时间整体顺延。
    if paused.total_seconds() > 0:
        for task in instance.tasks:
            if task.status in OPEN_STATUSES and task.due_at is not None:
                previous_due = task.due_at
                task.due_at = task.due_at + paused
                task.row_version = (task.row_version or 0) + 1
                record_task_event(
                    db,
                    task,
                    "SLA_SHIFTED",
                    task.status,
                    task.status,
                    actor,
                    {
                        "previous_due_at": previous_due.isoformat(),
                        "due_at": task.due_at.isoformat(),
                        "paused_seconds": round(paused.total_seconds(), 3),
                    },
                )
    db.flush()
    return instance


# ------------------------------------------------------------------ 查询与序列化


def get_execution_config(db: Session, process_id: int) -> Optional[ProcessExecutionConfig]:
    return db.scalar(
        select(ProcessExecutionConfig).where(ProcessExecutionConfig.process_id == process_id)
    )


def save_execution_config(
    db: Session,
    process_id: int,
    due_hours: Optional[int],
    escalation_hours: Optional[int] = None,
    escalation_user_id: Optional[int] = None,
) -> ProcessExecutionConfig:
    config = get_execution_config(db, process_id)
    if config is None:
        config = ProcessExecutionConfig(process_id=process_id)
        db.add(config)
    config.default_task_due_hours = due_hours
    config.default_escalation_hours = escalation_hours
    config.default_escalation_user_id = escalation_user_id
    db.flush()
    return config


def get_node_assignment(db: Session, process_id: int, node_key: str) -> Optional[NodeAssignment]:
    return db.scalar(
        select(NodeAssignment).where(
            NodeAssignment.process_id == process_id,
            NodeAssignment.node_key == node_key,
        )
    )


def save_node_assignment(
    db: Session, process_id: int, node_key: str, data: dict
) -> Optional[NodeAssignment]:
    row = get_node_assignment(db, process_id, node_key)
    fields = (
        "role",
        "org_unit_id",
        "default_assignee_user_id",
        "due_hours",
        "escalation_hours",
        "escalation_user_id",
    )
    if all(data.get(field) is None for field in fields):
        if row is not None:
            db.delete(row)
        db.flush()
        return None
    if row is None:
        row = NodeAssignment(process_id=process_id, node_key=node_key)
        db.add(row)
    for field in fields:
        setattr(row, field, data.get(field))
    db.flush()
    return row


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
            model_version=p.published_model_version or p.model_version,
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
    form = forms_service.form_for_snapshot(instance.snapshot, task.node_key)
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
        candidate_role_code=task.candidate_role_code,
        candidate_org_unit_id=task.candidate_org_unit_id,
        status=task.status,
        status_label=TASK_LABELS.get(task.status, task.status),
        instance_status=instance.status,
        instance_status_label=INSTANCE_LABELS.get(instance.status, instance.status),
        assignee_user_id=task.assignee_user_id,
        assignee_name=task.assignee_name,
        created_at=task.created_at,
        claimed_at=task.claimed_at,
        due_at=task.due_at,
        escalated_at=task.escalated_at,
        escalated_to_user_id=task.escalated_to_user_id,
        escalated_to_name=task.escalated_to_name,
        completed_at=task.completed_at,
        completed_by_name=task.completed_by_name,
        form_data=task.form_data,
        form_schema=(form or {}).get("fields", []),
        form_name=(form or {}).get("name"),
        comment=task.comment,
        standard_minutes=float(node.get("standard_minutes") or 0),
        actual_minutes=float(task.actual_minutes or 0),
        next_options=options,
    )


def list_task_events(db: Session, task_id: int) -> List[TaskEventOut]:
    rows = db.scalars(
        select(ProcessTaskEvent)
        .where(ProcessTaskEvent.task_id == task_id)
        .order_by(ProcessTaskEvent.id)
    ).all()
    return [
        TaskEventOut(
            id=row.id,
            task_id=row.task_id,
            event_type=row.event_type,
            event_label=TASK_EVENT_LABELS.get(row.event_type, row.event_type),
            from_status=row.from_status,
            from_status_label=(
                TASK_LABELS.get(row.from_status, row.from_status) if row.from_status else None
            ),
            to_status=row.to_status,
            to_status_label=(
                TASK_LABELS.get(row.to_status, row.to_status) if row.to_status else None
            ),
            actor_name=row.actor_name,
            detail=row.detail or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


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
        suspended_at=instance.suspended_at,
        suspend_reason=instance.suspend_reason,
        completed_at=instance.completed_at,
        archived_at=instance.archived_at,
        task_count=len(tasks),
        open_task_count=sum(1 for t in tasks if t.status in OPEN_STATUSES),
    )


def instance_detail(db: Session, instance: ProcessInstance) -> InstanceDetail:
    return InstanceDetail(
        instance=instance_out(instance),
        tasks=[task_out(t) for t in instance.tasks],
        compensations=[
            compensation_service.record_out(row)
            for row in compensation_service.records_for_instance(db, instance.id)
        ],
        configuration={
            "forms": instance.snapshot.get("forms", {}),
            "rules": instance.snapshot.get("rules", {}),
        },
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
    include_archived: bool = False,
) -> List[InstanceOut]:
    stmt = select(ProcessInstance)
    if status:
        stmt = stmt.where(ProcessInstance.status == status)
    if process_id is not None:
        stmt = stmt.where(ProcessInstance.process_id == process_id)
    if not include_archived:
        stmt = stmt.where(ProcessInstance.archived_at.is_(None))
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
