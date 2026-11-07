"""Governed sandbox deployment and original-object commands; never computes a route."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.engine import EngineCommand, EngineDeployment
from app.models.execution import NodeAssignment, ProcessInstance
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.user import User
from app.services import audit, execution, forms, org_access, process_model
from app.services import engine_commands as commands
from app.services import engine_projection as projection
from app.services import execution_readiness as readiness
from app.services.engine_bpmn import inspect_xml


def enabled():
    if not settings.flowable_sandbox_enabled:
        raise HTTPException(503, "Flowable沙箱未启用")


def manager(user):
    if not user.is_active or user.role not in {"ADMIN", "MANAGER"}:
        raise HTTPException(403, "仅流程管理者可管理沙箱部署")


def basis(db, user, pid):
    process = readiness.require_process(db, pid)
    version = readiness.published(db, process)
    if version is None or version.execution_provider != "FLOWABLE":
        raise HTTPException(409, "当前发布模型不是Flowable沙箱模型")
    checked = inspect_xml(version.bpmn_xml or "")
    snapshot = readiness.basis(db, process)[2]
    assignments = {}
    users = db.scalars(select(User).where(User.is_active.is_(True), User.role != "VIEWER")).all()
    for key in checked["tasks"]:
        assignment = db.scalar(
            select(NodeAssignment).where(
                NodeAssignment.process_id == pid,
                NodeAssignment.node_key == key,
                NodeAssignment.is_active.is_(True),
            )
        )
        if not assignment:
            raise HTTPException(409, f"活动{key}尚未明确分派")
        people = [
            u
            for u in users
            if (not assignment.role or u.role == assignment.role)
            and (
                not assignment.org_unit_id
                or u.org_unit_id in org_access.subtree_ids(db, assignment.org_unit_id)
            )
            and (
                not assignment.default_assignee_user_id
                or u.id == assignment.default_assignee_user_id
            )
        ]
        if not people or not (
            assignment.role or assignment.org_unit_id or assignment.default_assignee_user_id
        ):
            raise HTTPException(409, f"活动{key}没有可核验候选人")
        assignments[key] = [f"pms:{u.id}" for u in people]
    configuration = {**snapshot, "candidate_users": assignments}
    configuration["assignments"] = assignments
    configuration["assignment_basis"] = snapshot["assignments"]
    return process, version, checked, configuration, commands.digest(configuration)


def deployment_status(db, user, pid):
    process = readiness.require_process(db, pid)
    version = readiness.published(db, process)
    config = execution.get_execution_config(db, pid)
    deployment = (
        db.get(EngineDeployment, config.engine_deployment_id)
        if config and config.engine_deployment_id
        else None
    )
    missing = []
    try:
        _, current, checked, configuration, fingerprint = basis(db, user, pid)
        valid = bool(
            deployment
            and deployment.model_version_id == current.id
            and deployment.xml_hash == checked["sha256"]
            and deployment.basis_hash == fingerprint
        )
    except HTTPException as error:
        valid = False
        missing.append(error.detail)
    return {
        "enabled": settings.flowable_sandbox_enabled,
        "provider": version.execution_provider if version else "LEGACY",
        "provider_label": commands.PROVIDER_LABELS[
            version.execution_provider if version else "LEGACY"
        ],
        "model_version_id": version.id if version else None,
        "deployment_id": deployment.id if deployment else None,
        "definition_id": deployment.definition_id if deployment else None,
        "deployment_current": valid,
        "allow_start": bool(
            config and config.engine_enabled and valid and readiness.get(db, user, pid)["confirmed"]
        ),
        "state_label": "部署成功，待确认启用" if valid else "已发布，尚未部署",
        "missing": missing,
    }


def deploy(db, user, version_id, key):
    enabled()
    manager(user)
    version = db.get(ProcessModelVersion, version_id)
    if version is None:
        raise HTTPException(404, "模型版本不存在")
    process_model.lock_process(db, db.get(ProcessArch, version.process_id))
    process, current, checked, configuration, fingerprint = basis(db, user, version.process_id)
    if current.id != version_id:
        raise HTTPException(409, "只能部署当前明确发布版本")
    payload = {
        "xml": version.bpmn_xml,
        "xml_hash": checked["sha256"],
        "basis_hash": fingerprint,
        "model_version_id": version.id,
        "process_id": process.id,
        "assignments": configuration["assignments"],
    }
    command = commands.prepare(db, user, "SB_DEPLOY", f"model:{version.id}", payload, key)
    return finish(db, command)


def enable(db, user, pid, deployment_id, active):
    enabled()
    manager(user)
    if not active:
        process = readiness.require_process(db, pid)
        process_model.lock_process(db, process)
        config = readiness.config_row(db, pid)
        config.engine_enabled = False
        audit.record(
            db, user, "UPDATE", "process_execution_config", config.id, "停止Flowable沙箱新启动"
        )
        db.commit()
        return deployment_status(db, user, pid)
    process, version, checked, configuration, fingerprint = basis(db, user, pid)
    process_model.lock_process(db, process)
    deployment = db.get(EngineDeployment, deployment_id)
    if (
        not deployment
        or deployment.model_version_id != version.id
        or deployment.basis_hash != fingerprint
        or deployment.xml_hash != checked["sha256"]
    ):
        raise HTTPException(409, "部署或配置依据已变化")
    if active and not readiness.get(db, user, pid)["confirmed"]:
        raise HTTPException(409, "上线准备尚未本人确认")
    config = readiness.config_row(db, pid)
    config.engine_deployment_id, config.engine_enabled = deployment.id, active
    audit.record(
        db,
        user,
        "UPDATE",
        "process_execution_config",
        config.id,
        "启用Flowable沙箱新实例" if active else "停止Flowable沙箱新启动",
    )
    db.commit()
    return deployment_status(db, user, pid)


def instance_visible(db, user, instance):
    if not user.is_active or user.role == "VIEWER":
        raise HTTPException(403, "无权操作沙箱实例")
    process = db.get(ProcessArch, instance.process_id)
    if process is None:
        raise HTTPException(404, "流程不存在")
    org_access.ensure_visible(db, user, process.org_unit_id)
    if instance.project_id:
        from app.models.project import Project

        org_access.ensure_visible(db, user, db.get(Project, instance.project_id).org_unit_id)
    return process


def start(db, process, user, payload, key):
    enabled()
    org_access.ensure_visible(db, user, process.org_unit_id)
    process_model.lock_process(db, process)
    state = deployment_status(db, user, process.id)
    if not state["allow_start"]:
        raise HTTPException(409, "没有当前有效沙箱部署与准备确认")
    execution.validate_start_context(db, process, user, payload)
    version = readiness.published(db, process)
    if payload.round_id:
        round_row = execution.validate_start_context(db, process, user, payload)
        if round_row.released_model_version_id != version.id:
            raise HTTPException(409, "轮次上线模型与部署不一致")
    if payload.variables or payload.assignments:
        raise HTTPException(400, "首片沙箱不接受启动变量或临时分派")
    # A stable client key identifies the original local intent even after the engine response is lost.
    prior = (
        db.scalar(
            select(EngineCommand).where(
                EngineCommand.namespace == settings.flowable_sandbox_namespace,
                EngineCommand.user_id == user.id,
                EngineCommand.idempotency_key == key,
            )
        )
        if key
        else None
    )
    if prior:
        if (
            prior.action != "SB_START"
            or prior.request["payload"]["context"].get("process_id") != process.id
            or prior.request["payload"]["context"].get("project_id") != payload.project_id
            or prior.request["payload"]["context"].get("round_id") != payload.round_id
        ):
            raise HTTPException(409, "原启动键用于不同请求")
        instance_visible(db, user, db.get(ProcessInstance, prior.instance_id))
        return finish(db, prior)
    deployment = db.get(EngineDeployment, state["deployment_id"])
    snapshot = {
        "nodes": [
            {
                "key": n["node_key"],
                "name": n["name"],
                "type": n["node_type"],
                "lane": n.get("lane"),
                "standard_minutes": n.get("duration_minutes", 0),
                "activity_id": n.get("process_arch_id"),
            }
            for n in version.snapshot.get("nodes", [])
        ],
        "edges": [],
    }
    snapshot["forms"] = deployment.configuration.get("forms", {})
    snapshot["rules"] = {}
    instance = ProcessInstance(
        code="SB-" + uuid.uuid4().hex[:24],
        process_id=process.id,
        process_name=process.name,
        project_id=payload.project_id,
        round_id=payload.round_id,
        model_version_id=version.id,
        definition_version=version.version,
        provider="FLOWABLE",
        engine_namespace=deployment.namespace,
        deployment_id=deployment.id,
        snapshot=snapshot,
        variables={},
        started_by_id=user.id,
        started_by_name=user.display_name,
        sync_status="PENDING",
    )
    db.add(instance)
    db.flush()
    context = {
        "process_id": process.id,
        "model_version_id": version.id,
        "instance_id": instance.id,
        "project_id": payload.project_id,
        "round_id": payload.round_id,
    }
    command = commands.prepare(
        db,
        user,
        "SB_START",
        deployment.definition_id,
        {"business_key": f"sandbox:{deployment.namespace}:{instance.code}", "context": context},
        key,
        instance_id=instance.id,
    )
    return finish(db, command)


def allowed_task(db, task, user, replay=False):
    instance_visible(db, user, task.instance)
    deployment = db.get(EngineDeployment, task.instance.deployment_id)
    assignment = next(
        (
            a
            for a in deployment.configuration.get("assignment_basis", [])
            if a["node_key"] == task.node_key
        ),
        None,
    )
    if assignment and (
        (assignment.get("role") and user.role != assignment["role"])
        or (
            assignment.get("org_unit_id")
            and user.org_unit_id not in org_access.subtree_ids(db, assignment["org_unit_id"])
        )
    ):
        raise HTTPException(403, "当前角色或组织已不符合冻结分派")
    if (
        (
            not replay
            and (task.status not in {"PENDING", "CLAIMED"} or task.instance.status != "RUNNING")
        )
        or f"pms:{user.id}" not in deployment.configuration["assignments"].get(task.node_key, [])
        or (task.assignee_user_id is not None and task.assignee_user_id != user.id)
    ):
        raise HTTPException(403, "无权办理此任务，须符合冻结候选及本人分派")


def task_command(db, task, user, action, key, payload=None, assignee=None):
    enabled()
    instance_visible(db, user, task.instance)
    prior = (
        db.scalar(
            select(EngineCommand).where(
                EngineCommand.namespace == settings.flowable_sandbox_namespace,
                EngineCommand.user_id == user.id,
                EngineCommand.idempotency_key == key,
            )
        )
        if key
        else None
    )
    if action == "SB_ASSIGN":
        manager(user)
        if not assignee:
            raise HTTPException(400, "沙箱改派必须明确处理人")
        person = db.get(User, assignee)
        if not person or not person.is_active or person.role == "VIEWER":
            raise HTTPException(400, "处理人不存在或已停用")
        request = {"actor": f"pms:{user.id}", "assignee": f"pms:{assignee}"}
    else:
        allowed_task(db, task, user, replay=bool(prior))
        request = {"actor": f"pms:{user.id}"}
    if payload:
        request["form_hash"] = commands.digest(payload.model_dump(mode="json"))
        if payload.next_node_key or payload.variables:
            raise HTTPException(400, "由引擎决定后续路径，不能指定下一节点或自由变量")
        validated = forms.validate_form_data(
            forms.form_for_snapshot(task.instance.snapshot, task.node_key).get("fields", [])
            if forms.form_for_snapshot(task.instance.snapshot, task.node_key)
            else [],
            payload.form_data,
        )
        from app.services import authorization

        try:
            authorization.assert_task_allowed(db, task, user, validated)
        except authorization.AuthorizationError as error:
            raise HTTPException(403, str(error)) from error
        request["completion"] = {
            "form_data": validated,
            "comment": payload.comment,
            "effort_minutes": payload.effort_minutes,
        }
    command = commands.prepare(
        db,
        user,
        action,
        task.engine_task_id,
        request,
        key,
        instance_id=task.instance_id,
        task_id=task.id,
    )
    return finish(db, command)


def control(db, instance, user, action, key):
    enabled()
    manager(user)
    instance_visible(db, user, instance)
    return finish(
        db,
        commands.prepare(
            db, user, action, instance.engine_instance_id, {}, key, instance_id=instance.id
        ),
    )


def finish(db, command):
    commands.dispatch(db, command)
    if command.status != "SUCCEEDED" or (command.receipt or {}).get("local_applied"):
        return command
    try:
        result = command.receipt["result"]
        if command.action == "SB_DEPLOY":
            payload = command.request["payload"]
            if (
                result.get("xml_hash") != payload["xml_hash"]
                or result.get("namespace") != command.namespace
            ):
                raise HTTPException(409, "部署回执身份不一致")
            deployment = db.scalar(
                select(EngineDeployment).where(EngineDeployment.command_id == command.id)
            )
            if deployment is None:
                user = db.get(User, command.user_id)
                _, version, _, configuration, fingerprint = basis(db, user, payload["process_id"])
                if (
                    version.id != payload["model_version_id"]
                    or fingerprint != payload["basis_hash"]
                ):
                    raise HTTPException(409, "部署时配置已变化，保留回执待核对")
                deployment = db.scalar(
                    select(EngineDeployment).where(
                        EngineDeployment.namespace == command.namespace,
                        EngineDeployment.model_version_id == version.id,
                        EngineDeployment.basis_hash == fingerprint,
                        EngineDeployment.xml_hash == payload["xml_hash"],
                    )
                )
                if deployment is None:
                    deployment = EngineDeployment(
                        namespace=command.namespace,
                        model_version_id=version.id,
                        xml_hash=payload["xml_hash"],
                        basis_hash=fingerprint,
                        definition_id=result["definition_id"],
                        deployment_id=result["deployment_id"],
                        execution_hash=result["execution_hash"],
                        command_id=command.id,
                        configuration=configuration,
                        created_by_id=user.id,
                    )
                    db.add(deployment)
                    db.flush()
                config = readiness.config_row(db, version.process_id)
                config.engine_deployment_id, config.engine_enabled = deployment.id, False
        else:
            instance = db.get(ProcessInstance, command.instance_id)
            if command.action == "SB_START":
                instance.engine_instance_id = result["instance_id"]
                db.flush()
            projection.reconcile(db, instance)
            db.refresh(command)
            if command.action == "SB_COMPLETE" and not (command.receipt or {}).get("local_applied"):
                from app.models.execution import ProcessTask, TaskWorklog

                task = db.get(ProcessTask, command.task_id)
                completion = command.request["payload"].get("completion", {})
                task.form_data, task.comment = (
                    completion.get("form_data", {}),
                    completion.get("comment"),
                )
                minutes = completion.get("effort_minutes")
                if minutes and minutes > 0:
                    task.actual_minutes = float(task.actual_minutes or 0) + minutes
                    actor = db.get(User, command.user_id)
                    db.add(
                        TaskWorklog(
                            task_id=task.id,
                            user_id=actor.id,
                            user_name=actor.display_name,
                            work_type="HANDLE",
                            effort_minutes=minutes,
                            note="完成任务时登记（引擎回执已核对）",
                        )
                    )
        command.receipt = {**command.receipt, "local_applied": True}
        command.lock_key = None
        command.error = None
        db.commit()
    except Exception:
        db.rollback()
        command = db.get(EngineCommand, command.id)
        command.error = "引擎已确认，本地投影待核对"
        db.commit()
    return command


def recover(db, user, ident):
    command = db.get(EngineCommand, ident)
    if command is None or command.user_id != user.id:
        raise HTTPException(404, "原命令不存在")
    if not user.is_active or user.role == "VIEWER":
        raise HTTPException(403, "无权恢复原命令")
    if command.action == "SB_DEPLOY":
        manager(user)
    elif command.instance_id:
        instance_visible(db, user, db.get(ProcessInstance, command.instance_id))
        if command.task_id and command.action in {"SB_CLAIM", "SB_COMPLETE"}:
            from app.models.execution import ProcessTask

            allowed_task(db, db.get(ProcessTask, command.task_id), user, replay=True)
        elif command.action in {"SB_ASSIGN", "SB_SUSPEND", "SB_RESUME", "SB_CANCEL"}:
            manager(user)
    return finish(db, command)
