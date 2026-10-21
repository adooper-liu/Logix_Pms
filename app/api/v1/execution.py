"""流程执行：启动实例、任务队列、认领/完成/改派、取消。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.models.enums import InstanceStatus, TaskStatus
from app.models.execution import FormDefinition, ProcessRule, ProcessTask
from app.models.process import ProcessArch, ProcessNode
from app.schemas.common import DeleteResult
from app.schemas.execution import (
    ExecutableProcessOut,
    FormDefinitionCreate,
    FormDefinitionOut,
    FormDefinitionUpdate,
    InstanceDetail,
    InstanceOut,
    InstanceStartRequest,
    ProcessRuleCreate,
    ProcessRuleOut,
    ProcessRuleUpdate,
    TaskAssignRequest,
    TaskCompleteRequest,
    TaskOut,
)
from app.services import audit as audit_service
from app.services import execution as execution_service
from app.services import forms as forms_service
from app.services import integrations as integration_service
from app.services import notifications as notification_service

router = APIRouter(prefix="/execution", tags=["流程执行"])


@router.get(
    "/processes",
    response_model=List[ExecutableProcessOut],
    summary="可启动的流程（已建模的节点）",
)
def list_executable_processes(db: DbSession):
    return execution_service.executable_processes(db)


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


def _open_task(db, instance_id: int):
    return db.scalar(
        select(ProcessTask)
        .where(
            ProcessTask.instance_id == instance_id,
            ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
        )
        .order_by(ProcessTask.id)
    )


def _notify_open_task(db, instance) -> None:
    task = _open_task(db, instance.id)
    if task is not None and task.assignee_user_id is not None:
        notification_service.notify(
            db,
            task.assignee_user_id,
            "TASK_ASSIGNED",
            f"新任务：{task.name}",
            f"{instance.process_name}（{instance.code}）",
            link="execution",
            entity_type="process_task",
            entity_id=task.id,
        )


def _instance_event(instance) -> dict:
    return {
        "instance_id": instance.id,
        "code": instance.code,
        "process_id": instance.process_id,
        "process_name": instance.process_name,
        "project_id": instance.project_id,
        "status": instance.status,
        "current_node_key": instance.current_node_key,
        "started_by_id": instance.started_by_id,
        "started_by_name": instance.started_by_name,
        "started_at": instance.started_at,
    }


def _task_event(task) -> dict:
    return {
        "task_id": task.id,
        "instance_id": task.instance_id,
        "instance_code": task.instance.code,
        "process_name": task.instance.process_name,
        "node_key": task.node_key,
        "name": task.name,
        "task_type": task.task_type,
        "status": task.status,
        "assignee_user_id": task.assignee_user_id,
        "assignee_name": task.assignee_name,
        "created_at": task.created_at,
    }


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
def start_instance(payload: InstanceStartRequest, db: DbSession, user: WriteUser):
    process = db.get(ProcessArch, payload.process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    instance = execution_service.start_instance(db, process, user, payload)
    _notify_open_task(db, instance)
    integration_service.enqueue(db, "instance.started", _instance_event(instance))
    opened = _open_task(db, instance.id)
    if opened is not None:
        integration_service.enqueue(db, "task.created", _task_event(opened))
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_instance",
        instance.id,
        f"启动流程 {instance.code}：{instance.process_name}",
    )
    db.commit()
    db.refresh(instance)
    return execution_service.instance_out(instance)


@router.get(
    "/instances/{instance_id}", response_model=InstanceDetail, summary="实例详情与任务时间线"
)
def get_instance(instance_id: int, db: DbSession):
    instance = execution_service.get_instance(db, instance_id)
    return execution_service.instance_detail(instance)


@router.post(
    "/instances/{instance_id}/cancel",
    response_model=InstanceOut,
    summary="取消运行中的实例（流程管理科及以上）",
)
def cancel_instance(instance_id: int, db: DbSession, user: ManagerUser):
    instance = execution_service.get_instance(db, instance_id)
    execution_service.cancel_instance(db, instance)
    integration_service.enqueue(db, "instance.cancelled", _instance_event(instance))
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


@router.post("/tasks/{task_id}/claim", response_model=TaskOut, summary="认领任务")
def claim_task(task_id: int, db: DbSession, user: WriteUser):
    task = execution_service.get_task(db, task_id)
    execution_service.claim_task(db, task, user)
    integration_service.enqueue(db, "task.claimed", _task_event(task))
    audit_service.record(
        db, user, "UPDATE", "process_task", task.id, f"认领任务 {task.name}（{task.instance.code}）"
    )
    db.commit()
    db.refresh(task)
    return execution_service.task_out(task)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut, summary="完成任务并推进流程")
def complete_task(task_id: int, payload: TaskCompleteRequest, db: DbSession, user: WriteUser):
    task = execution_service.get_task(db, task_id)
    instance_code = task.instance.code
    execution_service.complete_task(db, task, user, payload)
    instance = task.instance
    if instance.status == InstanceStatus.COMPLETED.value:
        if instance.started_by_id:
            notification_service.notify(
                db,
                instance.started_by_id,
                "INSTANCE_COMPLETED",
                f"流程已完成：{instance.process_name}",
                f"{instance.code}",
                link="execution",
                entity_type="process_instance",
                entity_id=instance.id,
            )
    else:
        _notify_open_task(db, instance)
    integration_service.enqueue(db, "task.completed", _task_event(task))
    if instance.status == InstanceStatus.COMPLETED.value:
        integration_service.enqueue(db, "instance.completed", _instance_event(instance))
    else:
        following = _open_task(db, instance.id)
        if following is not None:
            integration_service.enqueue(db, "task.created", _task_event(following))
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_task",
        task.id,
        f"完成任务 {task.name}（{instance_code}）",
    )
    db.commit()
    db.refresh(task)
    return execution_service.task_out(task)


@router.patch(
    "/tasks/{task_id}/assignee",
    response_model=TaskOut,
    summary="改派任务（流程管理科及以上）",
)
def assign_task(task_id: int, payload: TaskAssignRequest, db: DbSession, user: ManagerUser):
    task = execution_service.get_task(db, task_id)
    execution_service.assign_task(db, task, payload.assignee_user_id)
    integration_service.enqueue(db, "task.assigned", _task_event(task))
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
