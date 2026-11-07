"""Single merge point for confirmed engine snapshots, receipts and journal-triggered reconciliation."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models.engine import EngineCursor, EngineDeployment, EngineInbox
from app.models.execution import ProcessInstance, ProcessTask
from app.services import notifications
from app.services.engine_transport import engine_client


def parsed(value):
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
        if value
        else None
    )


def actor_id(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith("pms:") or not value[4:].isdigit():
        raise HTTPException(409, "引擎处理人身份无法核对")
    return int(value[4:])


def apply_snapshot(db, instance, view):
    from app.models.user import User
    from app.services.execution import lock_instance, record_task_event

    lock_instance(db, instance.id)
    db.refresh(instance)
    deployment = db.get(EngineDeployment, instance.deployment_id)
    context = view.get("context") or {}
    if (
        view.get("instance_id") != instance.engine_instance_id
        or view.get("definition_id") != deployment.definition_id
        or context.get("instance_id") != instance.id
        or context.get("process_id") != instance.process_id
        or context.get("model_version_id") != instance.model_version_id
        or context.get("namespace") != instance.engine_namespace
        or context.get("project_id") != instance.project_id
        or context.get("round_id") != instance.round_id
    ):
        raise HTTPException(409, "引擎实例、定义或业务身份不一致，待核对")
    if view.get("status") not in {"RUNNING", "SUSPENDED", "COMPLETED", "CANCELLED"}:
        raise HTTPException(409, "未知引擎实例状态")
    if instance.status in {"COMPLETED", "CANCELLED"} and view["status"] in {"RUNNING", "SUSPENDED"}:
        return
    active = {item["task_id"]: item for item in view["tasks"]}
    history = {item["task_id"]: item for item in view["history_tasks"]}
    if (
        len(active) != len(view["tasks"])
        or len(history) != len(view["history_tasks"])
        or set(active) != {key for key, fact in history.items() if not fact.get("completed_at")}
    ):
        raise HTTPException(409, "引擎活跃任务与历史快照不一致")
    configuration = deployment.configuration
    previous_status = instance.status
    for fact in view["history_tasks"]:
        key = fact["activity_id"]
        if key not in configuration["assignments"]:
            raise HTTPException(409, "任务不属于部署时固定活动")
        item = db.scalar(
            select(ProcessTask).where(
                ProcessTask.engine_namespace == instance.engine_namespace,
                ProcessTask.engine_task_id == fact["task_id"],
            )
        )
        status = (
            (
                "CANCELLED"
                if fact.get("delete_reason") and fact.get("delete_reason") != "completed"
                else "COMPLETED"
            )
            if fact.get("completed_at")
            else "CLAIMED"
            if fact.get("assignee")
            else "PENDING"
        )
        if item and item.instance_id != instance.id:
            raise HTTPException(409, "引擎任务已属于其他实例")
        if item and item.status in {"COMPLETED", "CANCELLED"} and status in {"PENDING", "CLAIMED"}:
            continue
        new = item is None
        if new:
            item = ProcessTask(
                instance_id=instance.id,
                provider="FLOWABLE",
                engine_namespace=instance.engine_namespace,
                engine_task_id=fact["task_id"],
                execution_id=fact.get("execution_id"),
                node_key=key,
                name=fact.get("name") or key,
                task_type="APPROVAL",
                status="PENDING",
                created_at=parsed(fact.get("created_at")) or utcnow(),
            )
            db.add(item)
            db.flush()
        old_status, old_assignee = item.status, item.assignee_user_id
        item.status = status
        item.assignee_user_id = actor_id(fact.get("assignee"))
        person = db.get(User, item.assignee_user_id) if item.assignee_user_id else None
        item.assignee_name = person.display_name if person else None
        item.completed_at = parsed(fact.get("completed_at"))
        if status == "COMPLETED":
            item.completed_by_id = item.assignee_user_id
            item.completed_by_name = item.assignee_name
        if new:
            record_task_event(
                db,
                item,
                "CREATED",
                None,
                status,
                None,
                {"source": "FLOWABLE", "engine_task_id": item.engine_task_id},
            )
            for candidate in configuration["assignments"][key]:
                uid = actor_id(candidate)
                if db.get(User, uid):
                    notifications.notify(
                        db,
                        uid,
                        "TASK_ASSIGNED",
                        "沙箱任务：" + item.name,
                        instance.code,
                        link="execution",
                        entity_type="process_task",
                        entity_id=item.id,
                    )
        elif old_status != status or old_assignee != item.assignee_user_id:
            record_task_event(
                db,
                item,
                "COMPLETED"
                if status == "COMPLETED"
                else "CANCELLED"
                if status == "CANCELLED"
                else "ASSIGNED",
                old_status,
                status,
                None,
                {"source": "FLOWABLE", "engine_task_id": item.engine_task_id},
            )
    instance.status = view["status"]
    instance.completed_at = parsed(view.get("completed_at"))
    instance.suspended_at = (
        (instance.suspended_at or utcnow()) if instance.status == "SUSPENDED" else None
    )
    instance.sync_status, instance.synced_at = "CURRENT", utcnow()
    instance.current_node_key = (
        next(iter(active.values()))["activity_id"] if len(active) == 1 else None
    )
    instance.current_node_name = (
        next(iter(active.values())).get("name")
        if len(active) == 1
        else f"并行办理：{len(active)}项"
        if active
        else None
    )
    if (
        previous_status != instance.status
        and instance.status == "COMPLETED"
        and instance.started_by_id
    ):
        notifications.notify(
            db,
            instance.started_by_id,
            "INSTANCE_COMPLETED",
            "沙箱流程已完成",
            instance.code,
            link="execution",
            entity_type="process_instance",
            entity_id=instance.id,
        )
    db.flush()


def reconcile(db, instance, transport=None):
    from app.services.execution import lock_instance

    # Fetch after serializing this instance so an older in-flight response cannot undo a newer fact.
    lock_instance(db, instance.id)
    transport = transport or engine_client()
    apply_snapshot(db, instance, transport.get("/instances/" + instance.engine_instance_id))


def consume(db):
    transport = engine_client()
    namespace = transport.namespace
    cursor = db.get(EngineCursor, namespace)
    if cursor is None:
        cursor = EngineCursor(namespace=namespace, after_id=0)
        db.add(cursor)
        db.commit()
    page = transport.get(f"/events?after_id={cursor.after_id}&limit=100")
    try:
        for event in page["events"]:
            context = event.get("context") or {}
            # Separate POC events in the shared low-throughput journal have no sandbox namespace.
            if context.get("namespace") != namespace:
                continue
            known = db.scalar(
                select(EngineInbox).where(
                    EngineInbox.namespace == namespace, EngineInbox.event_id == event["event_id"]
                )
            )
            if known:
                continue
            instance = db.get(ProcessInstance, context.get("instance_id"))
            if (
                instance is None
                or instance.provider != "FLOWABLE"
                or instance.engine_instance_id != event.get("engine_instance_id")
            ):
                raise HTTPException(409, "未知引擎实例事件，游标保留待核对")
            if (
                event.get("definition_id")
                != db.get(EngineDeployment, instance.deployment_id).definition_id
            ):
                raise HTTPException(409, "事件定义不一致")
            reconcile(db, instance, transport)
            db.add(
                EngineInbox(
                    namespace=namespace,
                    event_id=event["event_id"],
                    journal_id=event["journal_id"],
                    payload=event,
                )
            )
        if page["next_after_id"] < cursor.after_id:
            raise HTTPException(409, "事件游标回退")
        cursor.after_id = page["next_after_id"]
        cursor.error = None
        db.commit()
    except Exception:
        db.rollback()
        cursor = db.get(EngineCursor, namespace)
        cursor.error = "事件核对失败，未前移游标"
        db.commit()
        raise
    return {"after_id": cursor.after_id, "has_more": page["has_more"]}
