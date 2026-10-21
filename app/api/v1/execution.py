"""流程执行：启动实例、任务队列、认领/完成/改派、取消。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.models.enums import InstanceStatus, TaskStatus
from app.models.process import ProcessArch
from app.schemas.common import DeleteResult
from app.schemas.execution import (
    ExecutableProcessOut,
    InstanceDetail,
    InstanceOut,
    InstanceStartRequest,
    TaskAssignRequest,
    TaskCompleteRequest,
    TaskOut,
)
from app.services import audit as audit_service
from app.services import execution as execution_service

router = APIRouter(prefix="/execution", tags=["流程执行"])


@router.get(
    "/processes",
    response_model=List[ExecutableProcessOut],
    summary="可启动的流程（已建模的节点）",
)
def list_executable_processes(db: DbSession):
    return execution_service.executable_processes(db)


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
