"""流程项目组合：立项、查询、五阶段进度、立项向导。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import (
    MANAGER_ROLES,
    DbSession,
    ManagerUser,
    WriteUser,
    apply_owner_update,
    ensure_can_edit_owned,
    resolve_owner,
)
from app.core.timeutil import utcnow
from app.models.deliverable import DeliverableInstance, DeliverableVersion
from app.models.enums import Methodology, ProjectStatus, ProjectType, Role, StepStatus
from app.models.evidence import ProjectEvidenceClaim
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.project import Project, ProjectGateCondition, ProjectStep, WorkflowTemplate
from app.schemas.common import DeleteResult, Page, as_columns
from app.schemas.evidence import (
    EvidenceClaimMetaOut,
    ProjectEvidenceClaimCreate,
    ProjectEvidenceClaimDecision,
    ProjectEvidenceClaimOut,
)
from app.schemas.project import (
    MethodologyRecommendation,
    MethodologyRecommendRequest,
    MilestoneItem,
    NextAction,
    ProjectCreate,
    ProjectDetail,
    ProjectKpiPoint,
    ProjectMetaOut,
    ProjectOut,
    ProjectSchedule,
    ProjectStepOut,
    ProjectStepUpdate,
    ProjectUpdate,
    ScheduleStage,
    ScheduleStep,
    SetupProgramCreate,
    StageProgress,
)
from app.schemas.project_workflow import (
    AdvanceResultOut,
    GateConditionCreateIn,
    GateConditionUpdateIn,
    StepUpdateIn,
    WorkbenchOut,
)
from app.services import audit as audit_service
from app.services import deliverable as deliverable_service
from app.services import evidence as evidence_service
from app.services import improvement as improvement_service
from app.services import kpi as kpi_service
from app.services import methodology as methodology_service
from app.services import project_workflow as workbench_service
from app.services import setup_program as setup_service
from app.services import startup as startup_service
from app.services import storage as storage_service
from app.services.workflow import STAGE_NAMES, recompute_progress, seed_project_steps

router = APIRouter(prefix="/projects", tags=["流程项目组合"])

METHODOLOGY_LABELS: Dict[str, str] = {
    Methodology.BPR.value: "BPR 阶跃式重组",
    Methodology.BPI.value: "BPI 渐进式优化",
    Methodology.LEAN.value: "精益改善·消除浪费",
    Methodology.HYBRID.value: "混合模式",
}

STATUS_LABELS: Dict[str, str] = {
    ProjectStatus.PLANNING.value: "待启动",
    ProjectStatus.ACTIVE.value: "进行中",
    ProjectStatus.ON_HOLD.value: "已暂停",
    ProjectStatus.CLOSED.value: "已完成",
    ProjectStatus.CANCELLED.value: "已取消",
}

PROJECT_TYPE_LABELS: Dict[str, str] = {
    ProjectType.IMPROVEMENT.value: "流程改善",
    ProjectType.GOVERNANCE_SETUP.value: "治理体系落地",
}


def _stage_names(project: Project) -> Dict[int, str]:
    if project.project_type == ProjectType.GOVERNANCE_SETUP.value:
        return setup_service.SETUP_STAGE_NAMES
    return STAGE_NAMES


# ------------------------------------------------------------------ 工具函数


def _process_names(db: DbSession) -> Dict[int, str]:
    return {p.id: p.name for p in db.scalars(select(ProcessArch)).all()}


def _to_out(p: Project, process_name: Optional[str] = None) -> ProjectOut:
    data = {c.name: getattr(p, c.name) for c in p.__table__.columns}
    data["process_name"] = process_name
    data["methodology_label"] = METHODOLOGY_LABELS.get(p.methodology, p.methodology)
    data["status_label"] = STATUS_LABELS.get(p.status, p.status)
    data["stage_name"] = _stage_names(p).get(p.current_stage)
    data["project_type_label"] = PROJECT_TYPE_LABELS.get(p.project_type, p.project_type)
    data["source_label"] = improvement_service.SOURCE_LABELS.get(p.source, p.source)
    data["replication_status_label"] = improvement_service.REPLICATION_LABELS.get(
        p.replication_status, p.replication_status
    )
    data["source_kpi_code"] = p.source_kpi.code if p.source_kpi else None
    data["source_kpi_name"] = p.source_kpi.name if p.source_kpi else None
    data["dmaic_stage_label"] = improvement_service.DMAIC_STAGE_LABELS.get(
        p.dmaic_stage, p.dmaic_stage
    )
    return ProjectOut.model_validate(data)


def _validate_source_kpi(db: DbSession, data: dict) -> None:
    kpi_id = data.get("source_kpi_id")
    if kpi_id is not None and db.get(KpiDefinition, kpi_id) is None:
        raise HTTPException(status_code=400, detail="source_kpi_id 指向的 KPI 不存在")


# ------------------------------------------------------------------ 立项向导


@router.post(
    "/recommend-methodology",
    response_model=MethodologyRecommendation,
    summary="立项向导：自动匹配 BPR / BPI / 精益 / 混合",
)
def recommend_methodology(payload: MethodologyRecommendRequest, db: DbSession):
    return methodology_service.recommend(db, payload)


# ------------------------------------------------------------------ 汇总


@router.get("/meta", response_model=ProjectMetaOut, summary="项目来源与复制状态标签")
def project_meta():
    return ProjectMetaOut(
        source_labels=improvement_service.SOURCE_LABELS,
        replication_status_labels=improvement_service.REPLICATION_LABELS,
    )


@router.get("/meta/summary", summary="项目组合汇总（按方法论 / 状态 / 优先级）")
def summary(db: DbSession):
    by_methodology = dict(
        db.execute(
            select(Project.methodology, func.count(Project.id)).group_by(Project.methodology)
        ).all()
    )
    by_status = dict(
        db.execute(select(Project.status, func.count(Project.id)).group_by(Project.status)).all()
    )
    by_stage = dict(
        db.execute(
            select(Project.current_stage, func.count(Project.id)).group_by(Project.current_stage)
        ).all()
    )
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    return {
        "total": total,
        "by_methodology": by_methodology,
        "by_status": by_status,
        "by_stage": {str(k): v for k, v in by_stage.items()},
        "methodology_labels": METHODOLOGY_LABELS,
        "status_labels": STATUS_LABELS,
        "stage_names": STAGE_NAMES,
        "setup_stage_names": setup_service.SETUP_STAGE_NAMES,
        "project_type_labels": PROJECT_TYPE_LABELS,
        "dmaic_stage_labels": improvement_service.DMAIC_STAGE_LABELS,
    }


# ------------------------------------------------------------------ 列表 / 新建


def _refresh_shared_measures(db: DbSession) -> None:
    """项目当前值与治理阶段在读之前对齐到唯一口径，并写回。"""
    kpi_service.align_open_projects(db)
    startup_service.apply_governance_stages(db)
    db.commit()


@router.get("", response_model=Page[ProjectOut], summary="项目列表（多维筛选）")
def list_projects(
    db: DbSession,
    methodology: Optional[Methodology] = None,
    status_: Optional[ProjectStatus] = Query(default=None, alias="status"),
    stage: Optional[int] = Query(default=None, ge=1, le=9),
    priority: Optional[int] = Query(default=None, ge=1, le=5),
    process_id: Optional[int] = None,
    project_type: Optional[ProjectType] = None,
    owner: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    _refresh_shared_measures(db)
    stmt = select(Project).options(joinedload(Project.source_kpi))
    if methodology is not None:
        stmt = stmt.where(Project.methodology == methodology.value)
    if status_ is not None:
        stmt = stmt.where(Project.status == status_.value)
    if stage is not None:
        stmt = stmt.where(Project.current_stage == stage)
    if priority is not None:
        stmt = stmt.where(Project.priority == priority)
    if process_id is not None:
        stmt = stmt.where(Project.process_id == process_id)
    if project_type is not None:
        stmt = stmt.where(Project.project_type == project_type.value)
    if owner:
        stmt = stmt.where(Project.owner.like(f"%{owner}%"))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(Project.name.like(like), Project.code.like(like), Project.objective.like(like))
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Project.priority, Project.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    names = _process_names(db)
    return Page[ProjectOut](
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_out(p, names.get(p.process_id)) for p in rows],
    )


@router.post(
    "", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="新建流程项目"
)
def create_project(payload: ProjectCreate, db: DbSession, user: WriteUser):
    if payload.project_type == ProjectType.GOVERNANCE_SETUP:
        raise HTTPException(
            status_code=400,
            detail="治理体系落地项目请使用 /projects/setup-program 创建（9 阶段模板）",
        )
    if payload.current_stage != 1:
        raise HTTPException(status_code=400, detail="新建改善项目必须从阶段1开始")
    if not payload.seed_workflow:
        raise HTTPException(
            status_code=400,
            detail="改善项目必须生成标准工作流；请使用 seed_workflow=true 创建",
        )
    data = as_columns(payload.model_dump(exclude={"code", "seed_workflow"}))
    # 归属以账号 id 为准；只给了姓名的历史数据按唯一 display_name 尝试绑定
    data["owner_user_id"], data["owner"] = resolve_owner(
        db, data.get("owner_user_id"), data.get("owner")
    )
    # 流程 Owner 角色立项时，只能挂在自己名下
    if user.role == Role.OWNER.value:
        data["owner_user_id"] = user.id
        data["owner"] = user.display_name
    if not data.get("owner"):
        raise HTTPException(status_code=400, detail="必须指定 Owner（owner 或 owner_user_id）")
    code = payload.code or improvement_service.next_project_code(db)
    if db.scalar(select(Project).where(Project.code == code)):
        raise HTTPException(status_code=409, detail=f"项目编码 {code} 已存在")
    if data.get("process_id") is not None and db.get(ProcessArch, data["process_id"]) is None:
        raise HTTPException(status_code=400, detail="process_id 指向的流程不存在")
    _validate_source_kpi(db, data)

    # 自动推算目标改善幅度
    baseline, target = data.get("baseline_value"), data.get("target_value")
    if baseline and target and data.get("improvement_pct") is None:
        data["improvement_pct"] = round(abs(baseline - target) / abs(baseline) * 100, 1)

    project = Project(code=code, **data)
    db.add(project)
    db.flush()
    if payload.seed_workflow:
        seed_project_steps(db, project)
        db.flush()
        # 按交付物定义给每个步骤生成实例，之后产出的文件挂到实例的版本上
        deliverable_service.sync_project_instances(db, project)
    audit_service.record(
        db,
        user,
        "CREATE",
        "project",
        project.id,
        f"立项 {project.code} {project.name}（{project.methodology}）",
    )
    db.commit()
    db.refresh(project)
    return _to_out(project, _process_names(db).get(project.process_id))


@router.get("/claims/meta", response_model=EvidenceClaimMetaOut, summary="判断证据标签")
def evidence_claim_meta():
    return EvidenceClaimMetaOut(
        evidence_level_labels=evidence_service.EVIDENCE_LEVEL_LABELS,
        evidence_type_labels=evidence_service.EVIDENCE_TYPE_LABELS,
        verdict_labels=evidence_service.VERDICT_LABELS,
    )


@router.get(
    "/{project_id}/claims",
    response_model=List[ProjectEvidenceClaimOut],
    summary="项目主张与证据链",
)
def list_project_claims(project_id: int, db: DbSession):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return evidence_service.list_claims(db, project_id)


@router.post(
    "/{project_id}/claims",
    response_model=ProjectEvidenceClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记主张、反证与证据",
)
def create_project_claim(
    project_id: int,
    payload: ProjectEvidenceClaimCreate,
    db: DbSession,
    user: WriteUser,
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    if payload.gate_condition_id is not None:
        condition = db.get(ProjectGateCondition, payload.gate_condition_id)
        if condition is None or condition.project_id != project_id:
            raise HTTPException(status_code=400, detail="关联的门槛条件不存在或不属于该项目")
        if condition.condition_code != "ROOT_CAUSE_EVIDENCE":
            raise HTTPException(status_code=400, detail="目前只有根因门条件可以关联证据")
    row = evidence_service.create_claim(db, project_id, payload.model_dump(), user)
    audit_service.record(
        db,
        user,
        "CREATE",
        "project_evidence_claim",
        row.id,
        f"项目 {project.code} 登记主张：{row.claim[:100]}",
    )
    db.commit()
    db.refresh(row)
    return evidence_service.claim_out(row)


@router.patch(
    "/{project_id}/claims/{claim_id}",
    response_model=ProjectEvidenceClaimOut,
    summary="独立裁决项目主张",
)
def decide_project_claim(
    project_id: int,
    claim_id: int,
    payload: ProjectEvidenceClaimDecision,
    db: DbSession,
    user: WriteUser,
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    row = db.get(ProjectEvidenceClaim, claim_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="证据主张不存在")
    try:
        evidence_service.decide_claim(db, row, payload.verdict, payload.decision_note, user)
    except evidence_service.EvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "project_evidence_claim",
        row.id,
        f"项目 {project.code} 主张裁决为 {row.verdict}",
    )
    db.commit()
    db.refresh(row)
    return evidence_service.claim_out(row)


@router.post(
    "/setup-program",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建治理体系落地项目（9 阶段，MANAGER+）",
)
def create_setup_program(payload: SetupProgramCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump())
    data["owner_user_id"], data["owner"] = resolve_owner(
        db, data.get("owner_user_id"), data.get("owner")
    )
    if not data.get("owner") or not data.get("owner_user_id"):
        raise HTTPException(status_code=400, detail="必须指定项目 Owner 账号")
    code = setup_service.next_setup_code(db)
    project = Project(
        code=code,
        name=payload.name,
        project_type=ProjectType.GOVERNANCE_SETUP.value,
        methodology=Methodology.HYBRID.value,
        status=ProjectStatus.PLANNING.value,
        current_stage=1,
        priority=payload.priority,
        owner=data["owner"],
        owner_user_id=data["owner_user_id"],
        sponsor=payload.sponsor,
        objective=payload.objective,
        scope=payload.scope,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(project)
    db.flush()
    setup_service.seed_setup_steps(db, project)
    recompute_progress(db, project, auto_advance=False)
    audit_service.record(
        db,
        user,
        "CREATE",
        "project",
        project.id,
        f"创建治理体系落地项目 {project.code} {project.name}（9 阶段）",
    )
    db.commit()
    db.refresh(project)
    return _to_out(project)


# ------------------------------------------------------------------ 详情 / 更新 / 删除


@router.get(
    "/{project_id}", response_model=ProjectDetail, summary="项目详情（含五阶段进度与下一步）"
)
def get_project(project_id: int, db: DbSession):
    _refresh_shared_measures(db)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    steps = db.scalars(
        select(ProjectStep)
        .where(ProjectStep.project_id == project_id)
        .order_by(ProjectStep.stage_no, ProjectStep.step_no)
    ).all()

    names = _stage_names(project)
    stage_numbers = sorted({s.stage_no for s in steps}) or sorted(names)
    stages: List[StageProgress] = []
    for stage_no in stage_numbers:
        stage_steps = [s for s in steps if s.stage_no == stage_no]
        done = sum(1 for s in stage_steps if s.status == StepStatus.DONE.value)
        total = len(stage_steps)
        stages.append(
            StageProgress(
                stage_no=stage_no,
                stage_name=names.get(stage_no, f"阶段 {stage_no}"),
                total=total,
                done=done,
                progress=round(done / total * 100, 1) if total else 0.0,
            )
        )

    current_steps = [
        s
        for s in steps
        if s.stage_no == project.current_stage and s.status != StepStatus.DONE.value
    ]

    next_action = None
    if current_steps:
        head = current_steps[0]
        if project.project_type == ProjectType.GOVERNANCE_SETUP.value:
            suggestion = (
                f"按九阶段体系落地路径推进：{head.deliverable or head.name}；完成后标记为已完成。"
            )
        else:
            tpl = db.scalar(
                select(WorkflowTemplate).where(WorkflowTemplate.step_no == head.step_no)
            )
            suggestion = (tpl.action if tpl else "按标准工作流推进该步骤。") + (
                f" 关键要点：{tpl.key_points}" if tpl else ""
            )
        next_action = NextAction(
            step_no=head.step_no,
            name=head.name,
            stage_no=head.stage_no,
            suggestion=suggestion,
        )

    kpi_trend = [
        ProjectKpiPoint(period=r.period, value=r.value, note=r.note)
        for r in db.scalars(
            select(KpiRecord).where(KpiRecord.project_id == project_id).order_by(KpiRecord.period)
        ).all()
    ]

    return ProjectDetail(
        project=_to_out(project, _process_names(db).get(project.process_id)),
        stages=stages,
        steps=[ProjectStepOut.model_validate(s) for s in steps],
        current_steps=[ProjectStepOut.model_validate(s) for s in current_steps],
        next_action=next_action,
        kpi_trend=kpi_trend,
        step_status_labels=workbench_service.STEP_STATUS_LABELS,
    )


@router.patch("/{project_id}", response_model=ProjectOut, summary="更新项目")
def update_project(project_id: int, payload: ProjectUpdate, db: DbSession, user: WriteUser):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    data = as_columns(payload.model_dump(exclude_unset=True))
    _validate_source_kpi(db, data)
    if user.role == Role.OWNER.value:
        # 归属不由 OWNER 自己变更，避免把项目转给他人或冒名
        data.pop("owner", None)
        data.pop("owner_user_id", None)
    else:
        apply_owner_update(db, data, project.owner)
        if "owner_user_id" in data and not data.get("owner"):
            raise HTTPException(status_code=400, detail="Owner 姓名不能为空")
    changed = sorted(data.keys())
    if "dmaic_stage" in data:
        data["dmaic_updated_at"] = utcnow()
    previous_stage = project.current_stage
    if "project_type" in data and data["project_type"] != project.project_type:
        raise HTTPException(status_code=400, detail="项目类型创建后不可变更")
    if "gate_required" in data:
        if data["gate_required"] is None:
            raise HTTPException(status_code=400, detail="严格门禁开关不能为空")
        if data["gate_required"] != project.gate_required and user.role not in MANAGER_ROLES:
            raise HTTPException(
                status_code=403,
                detail="严格门禁开关只能由流程管理科或系统管理员变更",
            )
    if project.project_type == ProjectType.GOVERNANCE_SETUP.value:
        data.pop("current_stage", None)
    target_stage = data.get("current_stage")
    if target_stage is not None and target_stage > previous_stage:
        # 用本次请求合并后的有效状态校验，避免“同一次 PATCH 里先关/开门禁再推进”
        # 读到更新前的 project_type / gate_required。
        effective = SimpleNamespace(
            id=project.id,
            project_type=data.get("project_type", project.project_type),
            gate_required=data.get("gate_required", project.gate_required),
            current_stage=previous_stage,
            process_id=data.get("process_id", project.process_id),
        )
        try:
            workbench_service.ensure_advance_allowed(db, effective, target_stage)
        except workbench_service.WorkbenchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    for field, value in data.items():
        setattr(project, field, value)
    kpi_service.align_project(db, project)
    if project.project_type == ProjectType.GOVERNANCE_SETUP.value:
        recompute_progress(db, project, auto_advance=False)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "project",
        project.id,
        f"更新项目 {project.code}：{', '.join(changed) if changed else '（无变更）'}",
    )
    db.commit()
    db.refresh(project)
    return _to_out(project, _process_names(db).get(project.process_id))


@router.get(
    "/{project_id}/workflow",
    response_model=WorkbenchOut,
    summary="五阶段项目工作台（当前阶段、步骤闭环与阶段门）",
)
def project_workbench(
    project_id: int,
    db: DbSession,
    user: WriteUser,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return workbench_service.workbench(db, project, view_stage=stage_no)


@router.patch(
    "/{project_id}/workflow/steps/{step_id}",
    response_model=WorkbenchOut,
    summary="更新项目步骤闭环字段与状态",
)
def update_workbench_step(
    project_id: int,
    step_id: int,
    payload: StepUpdateIn,
    db: DbSession,
    user: WriteUser,
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    step = db.get(ProjectStep, step_id)
    if step is None or step.project_id != project_id:
        raise HTTPException(status_code=404, detail="项目步骤不存在")
    try:
        workbench_service.update_step(
            db, project, step, payload.model_dump(exclude_unset=True), user
        )
    except workbench_service.WorkbenchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "project_step",
        step.id,
        f"更新项目 {project.code} 步骤 {step.step_no} {step.name}：{step.status}",
    )
    db.commit()
    db.refresh(project)
    return workbench_service.workbench(db, project)


@router.patch(
    "/{project_id}/workflow/conditions/{condition_id}",
    response_model=WorkbenchOut,
    summary="更新阶段退出门槛",
)
def update_gate_condition(
    project_id: int,
    condition_id: int,
    payload: GateConditionUpdateIn,
    db: DbSession,
    user: WriteUser,
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    condition = db.get(ProjectGateCondition, condition_id)
    if condition is None or condition.project_id != project_id:
        raise HTTPException(status_code=404, detail="门槛条件不存在")
    try:
        workbench_service.update_condition(
            db, project, condition, payload.model_dump(exclude_unset=True), user
        )
    except workbench_service.WorkbenchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "project_gate_condition",
        condition.id,
        f"更新项目 {project.code} 阶段{condition.stage_no}门槛：{condition.text}",
    )
    db.commit()
    db.refresh(project)
    return workbench_service.workbench(db, project)


@router.post(
    "/{project_id}/workflow/conditions",
    response_model=WorkbenchOut,
    summary="新增阶段退出门槛",
)
def create_gate_condition(
    project_id: int,
    payload: GateConditionCreateIn,
    db: DbSession,
    user: WriteUser,
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    condition = workbench_service.add_condition(db, project, payload.model_dump())
    audit_service.record(
        db,
        user,
        "CREATE",
        "project_gate_condition",
        condition.id,
        f"新增项目 {project.code} 阶段{condition.stage_no}门槛：{condition.text}",
    )
    db.commit()
    db.refresh(project)
    return workbench_service.workbench(db, project)


@router.post(
    "/{project_id}/workflow/advance",
    response_model=AdvanceResultOut,
    summary="通过阶段门并进入下一阶段",
)
def advance_project_stage(project_id: int, db: DbSession, user: WriteUser):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    previous = project.current_stage
    try:
        result = workbench_service.advance(db, project)
    except workbench_service.WorkbenchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "project",
        project.id,
        f"项目 {project.code} 阶段门通过：阶段{previous} → 阶段{project.current_stage}",
    )
    db.commit()
    return result


@router.delete("/{project_id}", response_model=DeleteResult, summary="删除项目（含步骤）")
def delete_project(project_id: int, db: DbSession, user: ManagerUser):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    code, name = project.code, project.name

    # 步骤由 ORM 的 delete-orphan 级联处理；KPI 数据点与异常事件引用项目，
    # 置空而不是跟着删——历史数据要留在台账里
    db.query(KpiRecord).filter(KpiRecord.project_id == project_id).update(
        {KpiRecord.project_id: None}, synchronize_session=False
    )
    db.query(ExceptionEvent).filter(ExceptionEvent.project_id == project_id).update(
        {ExceptionEvent.project_id: None}, synchronize_session=False
    )

    # 交付物实例与版本随步骤级联删除；文件不在数据库里，提交后再清理
    attachment_keys = db.scalars(
        select(DeliverableVersion.storage_key)
        .join(DeliverableInstance, DeliverableInstance.id == DeliverableVersion.instance_id)
        .where(
            DeliverableInstance.project_id == project_id,
            DeliverableVersion.storage_key.is_not(None),
        )
    ).all()

    audit_service.record(
        db, user, "DELETE", "project", project_id, f"删除项目 {code} {name}（含步骤）"
    )
    db.delete(project)
    db.commit()

    # 尽力清理；失败不改变业务删除结果，残留文件需人工清理
    if attachment_keys:
        storage = storage_service.get_storage()
        for key in attachment_keys:
            try:
                storage.delete(key)
            except (storage_service.StorageError, OSError):
                continue
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 步骤


@router.get("/{project_id}/steps", response_model=List[ProjectStepOut], summary="项目步骤清单")
def list_steps(
    project_id: int, db: DbSession, stage_no: Optional[int] = Query(default=None, ge=1, le=9)
):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    stmt = select(ProjectStep).where(ProjectStep.project_id == project_id)
    if stage_no is not None:
        stmt = stmt.where(ProjectStep.stage_no == stage_no)
    rows = db.scalars(stmt.order_by(ProjectStep.stage_no, ProjectStep.step_no)).all()
    return [ProjectStepOut.model_validate(r) for r in rows]


@router.get("/{project_id}/schedule", response_model=ProjectSchedule, summary="甘特图与里程碑")
def get_schedule(project_id: int, db: DbSession):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    steps = db.scalars(
        select(ProjectStep)
        .where(ProjectStep.project_id == project_id)
        .order_by(ProjectStep.stage_no, ProjectStep.step_no)
    ).all()

    today = date.today()
    names = _stage_names(project)
    stages: List[ScheduleStage] = []
    for stage_no in sorted({s.stage_no for s in steps}):
        stage_steps = [s for s in steps if s.stage_no == stage_no]
        if not stage_steps:
            continue
        dates = [s.due_date for s in stage_steps if s.due_date]
        done = sum(1 for s in stage_steps if s.status == StepStatus.DONE.value)
        stages.append(
            ScheduleStage(
                stage_no=stage_no,
                stage_name=names.get(stage_no, f"阶段 {stage_no}"),
                start=min(dates) if dates else None,
                end=max(dates) if dates else None,
                progress=round(done / len(stage_steps) * 100, 1),
                done=done,
                total=len(stage_steps),
                steps=[
                    ScheduleStep(
                        id=s.id,
                        step_no=s.step_no,
                        name=s.name,
                        status=s.status,
                        due_date=s.due_date,
                        is_milestone=s.is_milestone,
                    )
                    for s in stage_steps
                ],
            )
        )

    milestones = [
        MilestoneItem(
            step_id=s.id,
            stage_no=s.stage_no,
            step_no=s.step_no,
            name=s.name,
            due_date=s.due_date,
            status=s.status,
            is_overdue=bool(
                s.due_date and s.due_date < today and s.status != StepStatus.DONE.value
            ),
        )
        for s in steps
        if s.is_milestone
    ]

    total_days = elapsed = None
    if project.start_date and project.end_date:
        total_days = (project.end_date - project.start_date).days
        elapsed = max(0, min(total_days, (today - project.start_date).days))

    return ProjectSchedule(
        project_id=project.id,
        project_code=project.code,
        project_name=project.name,
        owner=project.owner,
        start_date=project.start_date,
        end_date=project.end_date,
        today=today,
        total_days=total_days,
        elapsed_days=elapsed,
        stages=stages,
        milestones=milestones,
    )


@router.patch(
    "/steps/{step_id}", response_model=ProjectStepOut, summary="更新某一步骤的状态 / 负责人 / 备注"
)
def update_step(step_id: int, payload: ProjectStepUpdate, db: DbSession, user: WriteUser):
    step = db.get(ProjectStep, step_id)
    if step is None:
        raise HTTPException(status_code=404, detail="步骤不存在")
    project = db.get(Project, step.project_id)
    if project is not None:
        ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    previous = step.status
    for field, value in as_columns(payload.model_dump(exclude_unset=True)).items():
        setattr(step, field, value)
    if step.status == StepStatus.DONE.value and step.completed_at is None:
        step.completed_at = utcnow()
    elif step.status != StepStatus.DONE.value:
        step.completed_at = None
    db.flush()  # 先落库，保证下面统计阶段完成度时读到的是最新状态

    # 阶段内步骤全部完成则推进阶段，并按完成占比回算整体进度
    if project is not None:
        recompute_progress(
            db,
            project,
            auto_advance=project.project_type == ProjectType.GOVERNANCE_SETUP.value,
        )
        audit_service.record(
            db,
            user,
            "UPDATE",
            "project_step",
            step.id,
            f"{project.code} 步骤 {step.step_no} {step.name}：{previous} → {step.status}",
        )
    db.commit()
    db.refresh(step)
    return ProjectStepOut.model_validate(step)
