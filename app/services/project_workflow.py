"""五阶段项目工作台：当前阶段、步骤闭环与阶段门。"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, ProcessBenchmarkMap
from app.models.enums import ProjectStatus, ProjectType, StepStatus
from app.models.process import ProcessArch
from app.models.project import Project, ProjectGateCondition, ProjectStep
from app.schemas.project_workflow import (
    AdvanceResultOut,
    GateConditionOut,
    WorkbenchContextOut,
    WorkbenchGateOut,
    WorkbenchLinkOut,
    WorkbenchOut,
    WorkbenchProjectOut,
    WorkbenchStageOut,
    WorkbenchStepOut,
)
from app.services import evidence as evidence_service
from app.services import improvement as improvement_service
from app.services import maturity as maturity_service
from app.services import workflow as workflow_service

STEP_STATUS_LABELS = {
    StepStatus.PENDING.value: "未开始",
    StepStatus.IN_PROGRESS.value: "进行中",
    StepStatus.PENDING_VERIFY.value: "待验证",
    StepStatus.DONE.value: "已满足",
    StepStatus.BLOCKED.value: "受阻",
    StepStatus.DECISION.value: "需决策",
    StepStatus.SKIPPED.value: "已跳过",
}

STAGE_STATUS_LABELS = {"complete": "已完成", "current": "当前阶段", "locked": "未解锁"}

STAGE_GOALS = {
    1: "明确改善对象、价值假设、项目边界、责任人和优先级。",
    2: "形成问题事实—假设—验证方法—根因—影响范围—责任方的闭环。",
    3: "形成可比较、可试点、可回退的方案选择。",
    4: "用试点证据验证方案，并形成推广、培训与责任计划。",
    5: "建立运行基线、控制限、复盘周期与偏差触发机制。",
}

HINT = (
    "阶段门看证据，不看勾选。存在未关闭关键条件、受阻/需决策步骤或待验证产物时，下一阶段保持锁定。"
)


class WorkbenchError(ValueError):
    pass


def _template_tools(template) -> List[str]:
    if template is None:
        return []
    raw = (template.tools or "").replace("，", "、").replace(",", "、")
    return [item.strip() for item in raw.split("、") if item.strip()]


def _step_out(step: ProjectStep, tools: Optional[List[str]] = None) -> WorkbenchStepOut:
    return WorkbenchStepOut(
        id=step.id,
        stage_no=step.stage_no,
        step_no=step.step_no,
        name=step.name,
        status=step.status,
        status_label=STEP_STATUS_LABELS.get(step.status, step.status),
        goal=step.goal,
        inputs=list(step.inputs or []),
        process_steps=list(step.process_steps or []),
        output=step.output,
        evidence=list(step.evidence or []),
        owner=step.owner,
        next_action=step.next_action,
        tools=list(tools or []),
        receiver=step.receiver,
        verified_by=step.verified_by,
        verified_at=step.verified_at,
        blocked_reason=step.blocked_reason,
        blocked_owner=step.blocked_owner,
        blocked_due=step.blocked_due,
        decision_options=list(step.decision_options or []),
        decision_maker=step.decision_maker,
        decision_due=step.decision_due,
        due_date=step.due_date,
        updated_at=step.updated_at,
    )


def _condition_out(row: ProjectGateCondition) -> GateConditionOut:
    return GateConditionOut(
        id=row.id,
        stage_no=row.stage_no,
        condition_code=row.condition_code,
        text=row.text,
        evidence=row.evidence,
        owner=row.owner,
        due_date=row.due_date,
        is_met=row.is_met,
        is_critical=row.is_critical,
        note=row.note,
        met_at=row.met_at,
        met_by=row.met_by,
    )


def _stage_status(stage_no: int, current_stage: int, project: Project) -> str:
    if project.status == ProjectStatus.CLOSED.value or stage_no < current_stage:
        return "complete"
    if stage_no == current_stage:
        return "current"
    return "locked"


def _blocking_reasons(
    steps: List[ProjectStep], conditions: List[ProjectGateCondition]
) -> List[str]:
    reasons: List[str] = []
    for condition in conditions:
        if condition.is_critical and not condition.is_met:
            reasons.append(f"门槛未满足：{condition.text}")
    for step in steps:
        if step.status == StepStatus.BLOCKED.value:
            reasons.append(f"步骤受阻：{step.name}（{step.blocked_reason or '未填写原因'}）")
        elif step.status == StepStatus.DECISION.value:
            reasons.append(f"步骤需决策：{step.name}（决策人 {step.decision_maker or '未指定'}）")
        elif step.status == StepStatus.PENDING_VERIFY.value:
            reasons.append(f"步骤待验证：{step.name}（接收方 {step.receiver or '未指定'}）")
        elif step.status != StepStatus.DONE.value:
            reasons.append(f"步骤未完成：{step.name}")
        elif not step.evidence:
            reasons.append(f"步骤缺少验收证据：{step.name}")
    return reasons


def _apqc_architecture_reasons(db: Session, project: Project, stage_no: int) -> List[str]:
    if (
        not project.gate_required
        or project.project_type != ProjectType.IMPROVEMENT.value
        or stage_no != 1
    ):
        return []

    reasons: List[str] = []
    process = db.get(ProcessArch, project.process_id) if project.process_id else None
    if process is None:
        return ["未关联企业 L3 流程，无法建立 APQC 对标"]
    if process.level != 3:
        reasons.append("项目必须承接企业 L3 端到端流程")
    if not (process.owner_user_id or (process.owner or "").strip()):
        reasons.append("企业 L3 流程尚未指定 Owner")
    if not (process.org_unit_id or (process.department or "").strip()):
        reasons.append("企业 L3 流程尚未指定责任部门")

    framework_rows = db.scalars(
        select(BenchmarkFramework).where(BenchmarkFramework.is_active.is_(True))
    ).all()
    base = next((row for row in framework_rows if row.code == "APQC_PCF"), None)
    framework_ids = {
        row.id
        for row in framework_rows
        if row.code == "APQC_PCF" or (base is not None and row.base_framework_id == base.id)
    }
    mapped = False
    if framework_ids:
        mapped = (
            db.scalar(
                select(ProcessBenchmarkMap.id)
                .join(BenchmarkCategory, BenchmarkCategory.id == ProcessBenchmarkMap.category_id)
                .where(
                    ProcessBenchmarkMap.process_id == process.id,
                    BenchmarkCategory.framework_id.in_(framework_ids),
                    BenchmarkCategory.level <= 3,
                )
                .limit(1)
            )
            is not None
        )
    if not mapped:
        reasons.append("企业 L3 流程尚未映射到 APQC PCF L1-L3")
    return reasons


def _stage_blocking_reasons(db: Session, project: Project, stage_no: int) -> List[str]:
    steps = list(
        db.scalars(
            select(ProjectStep).where(
                ProjectStep.project_id == project.id,
                ProjectStep.stage_no == stage_no,
            )
        ).all()
    )
    conditions = list(
        db.scalars(
            select(ProjectGateCondition).where(
                ProjectGateCondition.project_id == project.id,
                ProjectGateCondition.stage_no == stage_no,
            )
        ).all()
    )
    reasons = _blocking_reasons(steps, conditions)
    if any(row.condition_code == "ROOT_CAUSE_EVIDENCE" for row in conditions) and (
        not evidence_service.root_cause_evidence_ready(db, project.id)
    ):
        reasons.append("根因判断需有同一主张下至少两类已独立裁决的 L1-L3 证据")
    reasons.extend(_apqc_architecture_reasons(db, project, stage_no))
    return reasons


def ensure_advance_allowed(db: Session, project: Project, target_stage: int) -> None:
    if target_stage <= project.current_stage:
        return
    if project.project_type == ProjectType.GOVERNANCE_SETUP.value:
        return
    if target_stage != project.current_stage + 1:
        raise WorkbenchError("一次只能通过当前阶段退出门进入紧邻的下一阶段")
    if project.gate_required:
        try:
            maturity_service.ensure_advance_allowed(db, project, target_stage)
        except maturity_service.MaturityError as exc:
            raise WorkbenchError(str(exc)) from exc

    for stage_no in range(project.current_stage, target_stage):
        reasons = _stage_blocking_reasons(db, project, stage_no)
        if reasons:
            raise WorkbenchError(f"阶段门未通过（阶段{stage_no}）：" + "；".join(reasons))


def workbench(db: Session, project: Project, view_stage: Optional[int] = None) -> WorkbenchOut:
    target_stage = view_stage if view_stage in range(1, 6) else project.current_stage
    steps = list(
        db.scalars(
            select(ProjectStep)
            .where(ProjectStep.project_id == project.id)
            .order_by(ProjectStep.stage_no, ProjectStep.step_no)
        ).all()
    )
    gate_conditions = list(
        db.scalars(
            select(ProjectGateCondition)
            .where(ProjectGateCondition.project_id == project.id)
            .order_by(ProjectGateCondition.stage_no, ProjectGateCondition.sort_order)
        ).all()
    )
    templates = {
        row.step_no: row for row in db.scalars(select(workflow_service.WorkflowTemplate)).all()
    }
    stages: List[WorkbenchStageOut] = []
    for stage_no in range(1, 6):
        stage_steps = [row for row in steps if row.stage_no == stage_no]
        status = _stage_status(stage_no, project.current_stage, project)
        stages.append(
            WorkbenchStageOut(
                stage_no=stage_no,
                name=workflow_service.STAGE_NAMES.get(stage_no, f"阶段{stage_no}"),
                status=status,
                status_label=STAGE_STATUS_LABELS[status],
                goal=STAGE_GOALS.get(stage_no),
                summary=(
                    f"{sum(1 for row in stage_steps if row.status == StepStatus.DONE.value)}"
                    f"/{len(stage_steps)} 步已满足"
                ),
                step_count=len(stage_steps),
                done_count=sum(1 for row in stage_steps if row.status == StepStatus.DONE.value),
            )
        )
    current_stage = next(row for row in stages if row.stage_no == target_stage)
    current_steps = [row for row in steps if row.stage_no == target_stage]
    current_ids = {row.id for row in current_steps}
    conditions = [row for row in gate_conditions if row.stage_no == target_stage]
    conditions.sort(key=lambda row: (row.sort_order, row.id))
    is_current = target_stage == project.current_stage
    reasons = _blocking_reasons(current_steps, conditions)
    if any(row.condition_code == "ROOT_CAUSE_EVIDENCE" for row in conditions) and (
        not evidence_service.root_cause_evidence_ready(db, project.id)
    ):
        reasons.append("根因判断需有同一主张下至少两类已独立裁决的 L1-L3 证据")
    if is_current:
        reasons.extend(_apqc_architecture_reasons(db, project, target_stage))
        if project.gate_required and target_stage < 5:
            try:
                maturity_service.ensure_advance_allowed(db, project, target_stage + 1)
            except maturity_service.MaturityError as exc:
                reasons.append(str(exc))
    reasons = list(dict.fromkeys(reasons))
    met_count = sum(1 for row in conditions if row.is_met)
    can_advance = is_current and not reasons and project.current_stage < 5

    previous_stage = target_stage - 1
    prev_items: List[str] = []
    prev_name: Optional[str] = None
    if previous_stage >= 1:
        prev_name = workflow_service.STAGE_NAMES.get(previous_stage)
        prev_steps = [row for row in steps if row.stage_no == previous_stage]
        prev_items = [
            f"{row.step_no} {row.name}：{'已满足' if row.status == StepStatus.DONE.value else STEP_STATUS_LABELS.get(row.status, row.status)}"
            for row in prev_steps
        ]

    next_stage = target_stage + 1
    next_items: List[str] = []
    next_name: Optional[str] = None
    if next_stage <= 5:
        next_name = workflow_service.STAGE_NAMES.get(next_stage)
        next_conditions = [row for row in gate_conditions if row.stage_no == next_stage]
        next_items = [row.text for row in sorted(next_conditions, key=lambda row: row.sort_order)]

    return WorkbenchOut(
        project=WorkbenchProjectOut(
            id=project.id,
            code=project.code,
            name=project.name,
            owner=project.owner,
            status=project.status,
            status_label=improvement_service.PROJECT_STATUS_LABELS.get(
                project.status, project.status
            ),
            current_stage=project.current_stage,
            objective=project.objective,
        ),
        stages=stages,
        current_stage=current_stage,
        viewing_stage=target_stage,
        read_only=not is_current,
        steps=[
            _step_out(row, tools=_template_tools(templates.get(row.step_no)))
            for row in current_steps
            if row.id in current_ids
        ],
        claims=evidence_service.list_claims(db, project.id),
        evidence_level_labels=evidence_service.EVIDENCE_LEVEL_LABELS,
        evidence_verdict_labels=evidence_service.VERDICT_LABELS,
        gate=WorkbenchGateOut(
            conditions=[_condition_out(row) for row in conditions],
            met_count=met_count,
            total=len(conditions),
            can_advance=can_advance,
            block_reasons=reasons,
        ),
        previous=WorkbenchContextOut(
            stage_no=previous_stage if previous_stage >= 1 else None,
            name=prev_name,
            summary="上一阶段结果与证据",
            items=prev_items,
        ),
        next=WorkbenchContextOut(
            stage_no=next_stage if next_stage <= 5 else None,
            name=next_name,
            summary="下一阶段进入条件",
            items=next_items,
        ),
        links=WorkbenchLinkOut(
            project=f"/projects?project={project.id}",
            ten_layer=f"/pilot?project={project.id}&stage={target_stage}",
            stage=f"/workflow?project={project.id}&stage={target_stage}",
        ),
        step_status_labels=STEP_STATUS_LABELS,
        stage_status_labels=STAGE_STATUS_LABELS,
        hint=HINT,
    )


def update_step(db: Session, project: Project, step: ProjectStep, data: dict, user) -> ProjectStep:
    if step.project_id != project.id:
        raise WorkbenchError("步骤不属于该项目")
    status = data.get("status")
    if status == StepStatus.PENDING_VERIFY.value:
        receiver = data.get("receiver", step.receiver)
        if not (receiver or "").strip():
            raise WorkbenchError("提交待验证必须指定接收方")
    if status == StepStatus.BLOCKED.value:
        reason = data.get("blocked_reason", step.blocked_reason)
        owner = data.get("blocked_owner", step.blocked_owner)
        due = data.get("blocked_due", step.blocked_due)
        if not (reason or "").strip() or not (owner or "").strip() or due is None:
            raise WorkbenchError("受阻状态必须填写原因、责任人和预计解除日期")
    if status == StepStatus.DECISION.value:
        options = data.get("decision_options", step.decision_options)
        maker = data.get("decision_maker", step.decision_maker)
        due = data.get("decision_due", step.decision_due)
        if not options or not (maker or "").strip() or due is None:
            raise WorkbenchError("需决策状态必须填写选项、决策人和时限")

    for field, value in data.items():
        if field == "note":
            continue
        if hasattr(step, field):
            setattr(step, field, value)
    if status == StepStatus.DONE.value:
        step.completed_at = step.completed_at or utcnow()
        step.verified_by = data.get("verified_by") or step.verified_by or user.display_name
        step.verified_at = step.verified_at or utcnow()
    elif status in (
        StepStatus.PENDING.value,
        StepStatus.IN_PROGRESS.value,
        StepStatus.PENDING_VERIFY.value,
        StepStatus.BLOCKED.value,
        StepStatus.DECISION.value,
        StepStatus.SKIPPED.value,
    ):
        step.completed_at = None
    step.updated_by = user.display_name
    step.updated_at = utcnow()
    if data.get("note"):
        step.notes = data["note"]
    db.flush()
    workflow_service.recompute_progress(db, project, auto_advance=False)
    return step


def update_condition(
    db: Session,
    project: Project,
    condition: ProjectGateCondition,
    data: dict,
    user,
) -> ProjectGateCondition:
    if condition.project_id != project.id:
        raise WorkbenchError("门槛条件不属于该项目")
    if (
        condition.condition_code == "ROOT_CAUSE_EVIDENCE"
        and data.get("is_met")
        and not evidence_service.root_cause_evidence_ready(db, project.id)
    ):
        raise WorkbenchError("根因结论至少需要两类已独立裁决、相互印证的 L1-L3 证据")
    for field, value in data.items():
        if hasattr(condition, field):
            setattr(condition, field, value)
    if condition.is_met:
        if not (condition.evidence or "").strip():
            raise WorkbenchError("标记满足前必须填写可核验的证据")
        condition.met_at = condition.met_at or utcnow()
        condition.met_by = condition.met_by or user.display_name
    else:
        condition.met_at = None
        condition.met_by = None
    condition.updated_at = utcnow()
    db.flush()
    return condition


def add_condition(db: Session, project: Project, data: dict) -> ProjectGateCondition:
    row = ProjectGateCondition(
        project_id=project.id,
        stage_no=data["stage_no"],
        text=data["text"],
        evidence=data.get("evidence"),
        owner=data.get("owner"),
        due_date=data.get("due_date"),
        is_met=False,
        is_critical=data.get("is_critical", True),
        sort_order=data.get("sort_order", 99),
    )
    db.add(row)
    db.flush()
    return row


def advance(db: Session, project: Project) -> AdvanceResultOut:
    if project.current_stage >= 5:
        raise WorkbenchError("已经是最后一个阶段，不能继续推进")
    ensure_advance_allowed(db, project, project.current_stage + 1)
    project.current_stage += 1
    db.flush()
    workflow_service.recompute_progress(db, project, auto_advance=False)
    return AdvanceResultOut(
        current_stage=project.current_stage,
        status=project.status,
        status_label=improvement_service.PROJECT_STATUS_LABELS.get(project.status, project.status),
        message=f"已进入阶段{project.current_stage}：{workflow_service.STAGE_NAMES.get(project.current_stage, '')}",
    )
