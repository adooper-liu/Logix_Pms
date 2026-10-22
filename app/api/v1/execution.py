"""流程执行：启动实例、任务队列、认领/完成/改派、取消。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.models.enums import InstanceStatus, Role, TaskStatus
from app.models.execution import FormDefinition, NodeAssignment, ProcessRule
from app.models.process import ProcessArch, ProcessNode
from app.models.user import ROLE_LABELS, User
from app.schemas.common import DeleteResult
from app.schemas.execution import (
    AssigneeOut,
    EscalationScanResult,
    ExecutableProcessOut,
    ExecutionConfigOut,
    ExecutionConfigUpdate,
    FormDefinitionCreate,
    FormDefinitionOut,
    FormDefinitionUpdate,
    InstanceDetail,
    InstanceOut,
    InstanceStartRequest,
    InstanceSuspendRequest,
    NodeAssignmentOut,
    NodeAssignmentUpdate,
    ProcessRuleCreate,
    ProcessRuleOut,
    ProcessRuleUpdate,
    TaskAssignRequest,
    TaskCompleteRequest,
    TaskEventOut,
    TaskOut,
)
from app.services import audit as audit_service
from app.services import escalation as escalation_service
from app.services import execution as execution_service
from app.services import execution_flow as flow_service
from app.services import forms as forms_service
from app.services import idempotency as idempotency_service
from app.services import integrations as integration_service
from app.services import notifications as notification_service
from app.services import org_unit as org_service

router = APIRouter(prefix="/execution", tags=["流程执行"])


def _validate_assignee(db, user_id: int, label: str) -> User:
    assignee = db.get(User, user_id)
    if assignee is None or not assignee.is_active:
        raise HTTPException(status_code=400, detail=f"{label}不存在或已停用")
    if assignee.role == Role.VIEWER.value:
        raise HTTPException(status_code=400, detail=f"只读账号不能作为{label}")
    return assignee


@router.get(
    "/processes",
    response_model=List[ExecutableProcessOut],
    summary="可启动的流程（已建模的节点）",
)
def list_executable_processes(db: DbSession):
    return execution_service.executable_processes(db)


@router.get(
    "/config",
    response_model=ExecutionConfigOut,
    summary="流程执行配置（任务时限与超期升级）",
)
def get_config(db: DbSession, process_id: int):
    _ensure_process(db, process_id)
    config = execution_service.get_execution_config(db, process_id)
    return ExecutionConfigOut(
        process_id=process_id,
        default_task_due_hours=config.default_task_due_hours if config else None,
        default_escalation_hours=config.default_escalation_hours if config else None,
        default_escalation_user_id=(config.default_escalation_user_id if config else None),
        default_escalation_user_name=(
            config.default_escalation_user.display_name
            if config and config.default_escalation_user
            else None
        ),
        updated_at=config.updated_at if config else None,
    )


@router.put(
    "/config",
    response_model=ExecutionConfigOut,
    summary="维护流程执行配置（MANAGER+）",
)
def save_config(payload: ExecutionConfigUpdate, db: DbSession, user: ManagerUser, process_id: int):
    process = _ensure_process(db, process_id)
    if payload.default_escalation_user_id is not None:
        _validate_assignee(db, payload.default_escalation_user_id, "升级处理人")
    config = execution_service.save_execution_config(
        db,
        process_id,
        payload.default_task_due_hours,
        payload.default_escalation_hours,
        payload.default_escalation_user_id,
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_execution_config",
        config.id,
        f"流程 {process.code} 任务时限设为 "
        f"{payload.default_task_due_hours if payload.default_task_due_hours is not None else '不设'}；"
        f"升级时限 "
        f"{payload.default_escalation_hours if payload.default_escalation_hours is not None else '不升级'}"
        f"，升级处理人 {payload.default_escalation_user_id or '不设'}",
    )
    db.commit()
    db.refresh(config)
    return ExecutionConfigOut(
        process_id=process_id,
        default_task_due_hours=config.default_task_due_hours,
        default_escalation_hours=config.default_escalation_hours,
        default_escalation_user_id=config.default_escalation_user_id,
        default_escalation_user_name=(
            config.default_escalation_user.display_name if config.default_escalation_user else None
        ),
        updated_at=config.updated_at,
    )


@router.post(
    "/escalations/scan",
    response_model=EscalationScanResult,
    summary="运行超期任务升级扫描（MANAGER+）",
)
def scan_escalations(
    db: DbSession,
    user: ManagerUser,
    process_id: Optional[int] = None,
    limit: int = Query(default=500, ge=1, le=2000),
):
    if process_id is not None:
        _ensure_process(db, process_id)
    result = escalation_service.scan_escalations(db, user, process_id=process_id, limit=limit)
    if result.escalated:
        audit_service.record(
            db,
            user,
            "UPDATE",
            "process_task",
            None,
            f"运行升级扫描：扫描 {result.scanned}、升级 {result.escalated}、跳过 {result.skipped}",
        )
    db.commit()
    return result


@router.get(
    "/assignments",
    response_model=List[NodeAssignmentOut],
    summary="节点分派配置（角色 / 组织 / 默认处理人 / 时限 / 升级）",
)
def list_assignments(db: DbSession, user: CurrentUser, process_id: int):
    _ensure_process(db, process_id)
    nodes = db.scalars(
        select(ProcessNode)
        .where(ProcessNode.process_id == process_id)
        .order_by(ProcessNode.sequence_order, ProcessNode.id)
    ).all()
    rows = {
        row.node_key: row
        for row in db.scalars(
            select(NodeAssignment)
            .options(
                joinedload(NodeAssignment.org_unit),
                joinedload(NodeAssignment.default_assignee),
            )
            .where(
                NodeAssignment.process_id == process_id,
                NodeAssignment.is_active.is_(True),
            )
        ).all()
    }
    return [_assignment_out(node, rows.get(node.node_key)) for node in nodes]


@router.put(
    "/assignments",
    response_model=NodeAssignmentOut,
    summary="维护节点分派（MANAGER+）",
)
def save_assignment(payload: NodeAssignmentUpdate, db: DbSession, user: ManagerUser):
    _ensure_process(db, payload.process_id)
    _ensure_node(db, payload.process_id, payload.node_key)
    if payload.org_unit_id is not None:
        try:
            org_service.require_org(db, payload.org_unit_id)
        except org_service.OrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.default_assignee_user_id is not None:
        _validate_assignee(db, payload.default_assignee_user_id, "默认处理人")
    if payload.escalation_user_id is not None:
        _validate_assignee(db, payload.escalation_user_id, "升级处理人")
    row = execution_service.save_node_assignment(
        db,
        payload.process_id,
        payload.node_key,
        {
            "role": payload.role.value if payload.role else None,
            "org_unit_id": payload.org_unit_id,
            "default_assignee_user_id": payload.default_assignee_user_id,
            "due_hours": payload.due_hours,
            "escalation_hours": payload.escalation_hours,
            "escalation_user_id": payload.escalation_user_id,
        },
    )
    node = db.scalar(
        select(ProcessNode).where(
            ProcessNode.process_id == payload.process_id,
            ProcessNode.node_key == payload.node_key,
        )
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "node_assignment",
        row.id if row else None,
        f"节点分派 {payload.process_id}/{payload.node_key}："
        f"角色={payload.role.value if payload.role else '不限'}，"
        f"组织={payload.org_unit_id or '不限'}，"
        f"默认处理人={payload.default_assignee_user_id or '公共队列'}，"
        f"升级={payload.escalation_hours if payload.escalation_hours is not None else '不升级'}"
        f"/{payload.escalation_user_id or '不设'}",
    )
    db.commit()
    if row is not None:
        db.refresh(row)
    return _assignment_out(node, row)


def _assignment_out(node: ProcessNode, row: Optional[NodeAssignment]) -> NodeAssignmentOut:
    return NodeAssignmentOut(
        process_id=node.process_id,
        node_key=node.node_key,
        name=node.name,
        node_type=node.node_type,
        lane=node.lane,
        owner_role=node.owner_role,
        role=row.role if row else None,
        role_label=ROLE_LABELS.get(row.role, row.role) if row and row.role else None,
        org_unit_id=row.org_unit_id if row else None,
        org_unit_name=row.org_unit.name if row and row.org_unit else None,
        default_assignee_user_id=row.default_assignee_user_id if row else None,
        default_assignee_name=(
            row.default_assignee.display_name if row and row.default_assignee else None
        ),
        due_hours=row.due_hours if row else None,
        escalation_hours=row.escalation_hours if row else None,
        escalation_user_id=row.escalation_user_id if row else None,
        escalation_user_name=(
            row.escalation_user.display_name if row and row.escalation_user else None
        ),
    )


@router.get(
    "/assignees",
    response_model=List[AssigneeOut],
    summary="可指派人员（启用账号，不含只读）",
)
def list_assignees(db: DbSession, user: CurrentUser):
    rows = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role != Role.VIEWER.value)
        .order_by(User.display_name)
    ).all()
    return [
        AssigneeOut(
            id=row.id,
            display_name=row.display_name,
            role=row.role,
            role_label=ROLE_LABELS.get(row.role, row.role),
            department=row.department,
            org_unit_name=row.org_unit_name,
        )
        for row in rows
    ]


# ------------------------------------------------------------------ 表单与规则配置


def _ensure_process(db, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return process


def _ensure_node(db, process_id: int, node_key: str) -> None:
    if not node_key:
        return
    exists = db.scalar(
        select(ProcessNode.id).where(
            ProcessNode.process_id == process_id, ProcessNode.node_key == node_key
        )
    )
    if exists is None:
        raise HTTPException(status_code=400, detail=f"节点 {node_key} 不存在于该流程")


def _form_out(form: FormDefinition) -> FormDefinitionOut:
    return FormDefinitionOut(
        id=form.id,
        process_id=form.process_id,
        node_key=form.node_key,
        name=form.name,
        fields=form.fields or [],
        is_active=form.is_active,
        updated_at=form.updated_at,
    )


def _rule_out(rule: ProcessRule) -> ProcessRuleOut:
    return ProcessRuleOut(
        id=rule.id,
        process_id=rule.process_id,
        node_key=rule.node_key,
        name=rule.name,
        conditions=rule.conditions or [],
        target_node_key=rule.target_node_key,
        priority=rule.priority,
        is_active=rule.is_active,
        updated_at=rule.updated_at,
    )


@router.get("/forms", response_model=List[FormDefinitionOut], summary="表单定义列表")
def list_forms(db: DbSession, process_id: int, node_key: Optional[str] = None):
    stmt = select(FormDefinition).where(FormDefinition.process_id == process_id)
    if node_key is not None:
        stmt = stmt.where(FormDefinition.node_key == node_key)
    rows = db.scalars(stmt.order_by(FormDefinition.node_key)).all()
    return [_form_out(f) for f in rows]


@router.post(
    "/forms",
    response_model=FormDefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增表单定义（MANAGER+）",
)
def create_form(payload: FormDefinitionCreate, db: DbSession, user: ManagerUser):
    _ensure_process(db, payload.process_id)
    _ensure_node(db, payload.process_id, payload.node_key)
    existing = db.scalar(
        select(FormDefinition).where(
            FormDefinition.process_id == payload.process_id,
            FormDefinition.node_key == payload.node_key,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该流程/节点已有表单定义，请直接修改")
    form = FormDefinition(
        process_id=payload.process_id,
        node_key=payload.node_key or "",
        name=payload.name,
        fields=forms_service.normalize_fields(payload.fields),
        is_active=payload.is_active,
    )
    db.add(form)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "form_definition",
        form.id,
        f"新增表单 {form.name}（{form.node_key or '流程默认'}）",
    )
    db.commit()
    db.refresh(form)
    return _form_out(form)


@router.patch(
    "/forms/{form_id}", response_model=FormDefinitionOut, summary="修改表单定义（MANAGER+）"
)
def update_form(form_id: int, payload: FormDefinitionUpdate, db: DbSession, user: ManagerUser):
    form = db.get(FormDefinition, form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="表单定义不存在")
    data = payload.model_dump(exclude_unset=True)
    if "fields" in data and data["fields"] is not None:
        form.fields = forms_service.normalize_fields(data.pop("fields"))
    for key, value in data.items():
        setattr(form, key, value)
    audit_service.record(db, user, "UPDATE", "form_definition", form.id, f"修改表单 {form.name}")
    db.commit()
    db.refresh(form)
    return _form_out(form)


@router.delete("/forms/{form_id}", response_model=DeleteResult, summary="删除表单定义（MANAGER+）")
def delete_form(form_id: int, db: DbSession, user: ManagerUser):
    form = db.get(FormDefinition, form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="表单定义不存在")
    audit_service.record(db, user, "DELETE", "form_definition", form.id, f"删除表单 {form.name}")
    db.delete(form)
    db.commit()
    return DeleteResult(deleted=1)


@router.get("/rules", response_model=List[ProcessRuleOut], summary="分支规则列表")
def list_rules(db: DbSession, process_id: int, node_key: Optional[str] = None):
    stmt = select(ProcessRule).where(ProcessRule.process_id == process_id)
    if node_key is not None:
        stmt = stmt.where(ProcessRule.node_key == node_key)
    rows = db.scalars(
        stmt.order_by(ProcessRule.node_key, ProcessRule.priority, ProcessRule.id)
    ).all()
    return [_rule_out(r) for r in rows]


@router.post(
    "/rules",
    response_model=ProcessRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增分支规则（MANAGER+）",
)
def create_rule(payload: ProcessRuleCreate, db: DbSession, user: ManagerUser):
    _ensure_process(db, payload.process_id)
    forms_service.validate_rule_target(
        db, payload.process_id, payload.node_key, payload.target_node_key
    )
    rule = ProcessRule(
        process_id=payload.process_id,
        node_key=payload.node_key,
        name=payload.name,
        conditions=forms_service.normalize_conditions([c.model_dump() for c in payload.conditions]),
        target_node_key=payload.target_node_key,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_rule",
        rule.id,
        f"新增规则 {rule.name}：{rule.node_key} → {rule.target_node_key}",
    )
    db.commit()
    db.refresh(rule)
    return _rule_out(rule)


@router.patch("/rules/{rule_id}", response_model=ProcessRuleOut, summary="修改分支规则（MANAGER+）")
def update_rule(rule_id: int, payload: ProcessRuleUpdate, db: DbSession, user: ManagerUser):
    rule = db.get(ProcessRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="分支规则不存在")
    data = payload.model_dump(exclude_unset=True)
    if "conditions" in data and data["conditions"] is not None:
        rule.conditions = forms_service.normalize_conditions(
            [c if isinstance(c, dict) else c.model_dump() for c in data.pop("conditions")]
        )
    if "target_node_key" in data and data["target_node_key"] is not None:
        forms_service.validate_rule_target(
            db, rule.process_id, rule.node_key, data["target_node_key"]
        )
    for key, value in data.items():
        setattr(rule, key, value)
    audit_service.record(db, user, "UPDATE", "process_rule", rule.id, f"修改规则 {rule.name}")
    db.commit()
    db.refresh(rule)
    return _rule_out(rule)


@router.delete("/rules/{rule_id}", response_model=DeleteResult, summary="删除分支规则（MANAGER+）")
def delete_rule(rule_id: int, db: DbSession, user: ManagerUser):
    rule = db.get(ProcessRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="分支规则不存在")
    audit_service.record(db, user, "DELETE", "process_rule", rule.id, f"删除规则 {rule.name}")
    db.delete(rule)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 实例


@router.get("/instances", response_model=List[InstanceOut], summary="流程实例列表")
def list_instances(
    db: DbSession,
    status_: Optional[InstanceStatus] = Query(default=None, alias="status"),
    process_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    return execution_service.list_instances(
        db,
        status=status_.value if status_ else None,
        process_id=process_id,
        limit=limit,
    )


@router.post(
    "/instances",
    response_model=InstanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="启动流程实例",
)
def start_instance(
    payload: InstanceStartRequest,
    db: DbSession,
    user: WriteUser,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    digest = idempotency_service.request_hash(payload)
    record = idempotency_service.begin(db, "instance.start", idempotency_key, digest)
    if record is not None and record.status == "SUCCESS":
        return InstanceOut.model_validate(record.response)

    process = db.get(ProcessArch, payload.process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    instance = flow_service.start_instance(db, process, user, payload)
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_instance",
        instance.id,
        f"启动流程 {instance.code}：{instance.process_name}",
    )
    out = execution_service.instance_out(instance)
    idempotency_service.finish(record, out.model_dump(mode="json"))
    db.commit()
    db.refresh(instance)
    return out


@router.get(
    "/instances/{instance_id}", response_model=InstanceDetail, summary="实例详情与任务时间线"
)
def get_instance(instance_id: int, db: DbSession):
    instance = execution_service.get_instance(db, instance_id)
    return execution_service.instance_detail(instance)


@router.post(
    "/instances/{instance_id}/suspend",
    response_model=InstanceOut,
    summary="挂起运行中的实例（流程管理科及以上）",
)
def suspend_instance(
    instance_id: int,
    payload: InstanceSuspendRequest,
    db: DbSession,
    user: ManagerUser,
):
    instance = execution_service.get_instance(db, instance_id)
    execution_service.suspend_instance(db, instance, payload.reason)
    integration_service.enqueue(db, "instance.suspended", flow_service.instance_event(instance))
    notification_service.notify(
        db,
        instance.started_by_id,
        "INSTANCE_SUSPENDED",
        f"流程已挂起：{instance.process_name}",
        f"{instance.code}" + (f" · {payload.reason}" if payload.reason else ""),
        link="execution",
        entity_type="process_instance",
        entity_id=instance.id,
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_instance",
        instance.id,
        f"挂起流程实例 {instance.code}" + (f"：{payload.reason}" if payload.reason else ""),
    )
    db.commit()
    db.refresh(instance)
    return execution_service.instance_out(instance)


@router.post(
    "/instances/{instance_id}/resume",
    response_model=InstanceOut,
    summary="恢复已挂起的实例（流程管理科及以上）",
)
def resume_instance(instance_id: int, db: DbSession, user: ManagerUser):
    instance = execution_service.get_instance(db, instance_id)
    execution_service.resume_instance(db, instance, user)
    integration_service.enqueue(db, "instance.resumed", flow_service.instance_event(instance))
    notification_service.notify(
        db,
        instance.started_by_id,
        "INSTANCE_RESUMED",
        f"流程已恢复：{instance.process_name}",
        f"{instance.code}",
        link="execution",
        entity_type="process_instance",
        entity_id=instance.id,
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_instance",
        instance.id,
        f"恢复流程实例 {instance.code}",
    )
    db.commit()
    db.refresh(instance)
    return execution_service.instance_out(instance)


@router.post(
    "/instances/{instance_id}/cancel",
    response_model=InstanceOut,
    summary="取消运行中/已挂起的实例（流程管理科及以上）",
)
def cancel_instance(instance_id: int, db: DbSession, user: ManagerUser):
    instance = execution_service.get_instance(db, instance_id)
    execution_service.cancel_instance(db, instance, user)
    integration_service.enqueue(db, "instance.cancelled", flow_service.instance_event(instance))
    notification_service.notify(
        db,
        instance.started_by_id,
        "INSTANCE_CANCELLED",
        f"流程已取消：{instance.process_name}",
        f"{instance.code}",
        link="execution",
        entity_type="process_instance",
        entity_id=instance.id,
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_instance",
        instance.id,
        f"取消流程实例 {instance.code}",
    )
    db.commit()
    db.refresh(instance)
    return execution_service.instance_out(instance)


@router.delete(
    "/instances/{instance_id}",
    response_model=DeleteResult,
    summary="删除实例及其任务（流程管理科及以上，用于清理测试数据）",
)
def delete_instance(instance_id: int, db: DbSession, user: ManagerUser):
    instance = execution_service.get_instance(db, instance_id)
    code = instance.code
    audit_service.record(
        db, user, "DELETE", "process_instance", instance.id, f"删除流程实例 {code}"
    )
    db.delete(instance)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 任务队列


def _resolve_assignee(assignee: Optional[str], user) -> Optional[int]:
    if not assignee:
        return None
    if assignee == "me":
        return user.id
    try:
        return int(assignee)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="assignee 只支持 me 或用户 id") from exc


@router.get("/tasks", response_model=List[TaskOut], summary="任务队列")
def list_tasks(
    db: DbSession,
    user: CurrentUser,
    status_: Optional[TaskStatus] = Query(default=None, alias="status"),
    assignee: Optional[str] = Query(default=None, description="me 或用户 id"),
    instance_id: Optional[int] = None,
    process_id: Optional[int] = None,
    only_open: bool = Query(default=True, description="只返回待认领/处理中的任务"),
    limit: int = Query(default=200, ge=1, le=500),
):
    return execution_service.list_tasks(
        db,
        status=status_.value if status_ else None,
        assignee_user_id=_resolve_assignee(assignee, user),
        instance_id=instance_id,
        process_id=process_id,
        only_open=only_open,
        limit=limit,
    )


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="任务详情")
def get_task(task_id: int, db: DbSession):
    return execution_service.task_out(execution_service.get_task(db, task_id))


@router.get(
    "/tasks/{task_id}/events",
    response_model=List[TaskEventOut],
    summary="任务生命周期事件",
)
def list_task_events(task_id: int, db: DbSession, user: CurrentUser):
    execution_service.get_task(db, task_id)
    return execution_service.list_task_events(db, task_id)


@router.post("/tasks/{task_id}/claim", response_model=TaskOut, summary="认领任务")
def claim_task(task_id: int, db: DbSession, user: WriteUser):
    task = execution_service.get_task(db, task_id)
    execution_service.claim_task(db, task, user)
    integration_service.enqueue(db, "task.claimed", flow_service.task_event(task))
    audit_service.record(
        db, user, "UPDATE", "process_task", task.id, f"认领任务 {task.name}（{task.instance.code}）"
    )
    db.commit()
    db.refresh(task)
    return execution_service.task_out(task)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut, summary="完成任务并推进流程")
def complete_task(
    task_id: int,
    payload: TaskCompleteRequest,
    db: DbSession,
    user: WriteUser,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    digest = idempotency_service.request_hash(payload)
    record = idempotency_service.begin(db, "task.complete", idempotency_key, digest)
    if record is not None and record.status == "SUCCESS":
        return TaskOut.model_validate(record.response)

    task = execution_service.get_task(db, task_id)
    instance_code = task.instance.code
    flow_service.complete_task(db, task, user, payload)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_task",
        task.id,
        f"完成任务 {task.name}（{instance_code}）",
    )
    out = execution_service.task_out(task)
    idempotency_service.finish(record, out.model_dump(mode="json"))
    db.commit()
    db.refresh(task)
    return out


@router.patch(
    "/tasks/{task_id}/assignee",
    response_model=TaskOut,
    summary="改派任务（流程管理科及以上）",
)
def assign_task(task_id: int, payload: TaskAssignRequest, db: DbSession, user: ManagerUser):
    task = execution_service.get_task(db, task_id)
    execution_service.assign_task(db, task, payload.assignee_user_id, user)
    integration_service.enqueue(db, "task.assigned", flow_service.task_event(task))
    if task.assignee_user_id is not None:
        notification_service.notify(
            db,
            task.assignee_user_id,
            "TASK_ASSIGNED",
            f"新任务：{task.name}",
            f"{task.instance.process_name}（{task.instance.code}）",
            link="execution",
            entity_type="process_task",
            entity_id=task.id,
        )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_task",
        task.id,
        f"改派任务 {task.name} → {task.assignee_name or '公共队列'}",
    )
    db.commit()
    db.refresh(task)
    return execution_service.task_out(task)
