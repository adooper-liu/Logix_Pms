"""管理驾驶舱聚合。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.change import ProcessChangeRequest
from app.models.enums import (
    ChangeStatus,
    ExceptionStatus,
    Methodology,
    ProjectStatus,
    Role,
    StepStatus,
)
from app.models.governance import GovernanceFinding
from app.models.knowledge import KnowledgeItem
from app.models.monitor import ExceptionEvent, KpiDefinition
from app.models.process import ProcessArch
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.user import User
from app.schemas.dashboard import (
    DashboardHome,
    DashboardHomeBlock,
    DashboardOverview,
    HealthAlert,
    HomeAction,
    HomeItem,
    HomeNextAction,
    KpiCard,
    MethodologySlice,
    ProjectBoardItem,
    StageHealth,
)
from app.services import kpi as kpi_service
from app.services import startup as startup_service

STAGE_NAMES: Dict[int, str] = {
    1: "识别与优先级排序",
    2: "诊断与根因分析",
    3: "方案设计与选择",
    4: "试点与推广落地",
    5: "运营监控与持续改进",
}

METHODOLOGY_LABELS: Dict[str, str] = {
    Methodology.BPR.value: "BPR 重组",
    Methodology.BPI.value: "BPI 优化",
    Methodology.LEAN.value: "精益改善",
    Methodology.HYBRID.value: "混合模式",
}

STATUS_LABELS: Dict[str, str] = {
    ProjectStatus.PLANNING.value: "待启动",
    ProjectStatus.ACTIVE.value: "进行中",
    ProjectStatus.ON_HOLD.value: "已暂停",
    ProjectStatus.CLOSED.value: "已完成",
    ProjectStatus.CANCELLED.value: "已取消",
}

HEALTH_ALERT_THRESHOLD = 70.0


def build_overview(db: Session, board_limit: int = 8) -> DashboardOverview:
    projects = db.scalars(select(Project).where(Project.project_type == "IMPROVEMENT")).all()
    steps = db.scalars(
        select(ProjectStep).join(Project).where(Project.project_type == "IMPROVEMENT")
    ).all()

    active = [p for p in projects if p.status == ProjectStatus.ACTIVE.value]
    this_year = date.today().year
    closed_this_year = [
        p
        for p in projects
        if p.status == ProjectStatus.CLOSED.value
        and p.end_date is not None
        and p.end_date.year == this_year
    ]

    process_total = (
        db.scalar(
            select(func.count()).select_from(ProcessArch).where(ProcessArch.is_draft.is_(False))
        )
        or 0
    )
    improvement_targets = (
        db.scalar(
            select(func.count())
            .select_from(ProcessArch)
            .where(ProcessArch.is_improvement_target.is_(True))
        )
        or 0
    )

    exceptions = db.scalars(select(ExceptionEvent)).all()
    open_exceptions = [
        e
        for e in exceptions
        if e.status in (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
    ]

    improvements = [p.improvement_pct for p in active if p.improvement_pct is not None]
    avg_improvement = round(sum(improvements) / len(improvements), 1) if improvements else 0.0

    cards: List[KpiCard] = [
        KpiCard(
            key="active_projects",
            label="在办流程项目",
            value=len(active),
            unit="个",
            status="NORMAL" if active else "WATCH",
        ),
        KpiCard(
            key="closed_this_year",
            label=f"{this_year} 年结项",
            value=len(closed_this_year),
            unit="个",
        ),
        KpiCard(
            key="improvement_targets",
            label="待改善流程",
            value=improvement_targets,
            unit="个",
            status="WATCH" if improvement_targets > 5 else "NORMAL",
        ),
        KpiCard(
            key="avg_improvement",
            label="在办项目平均目标改善",
            value=avg_improvement,
            unit="%",
            status="NORMAL" if avg_improvement >= 20 else "WATCH",
        ),
        KpiCard(
            key="open_exceptions",
            label="未闭环异常",
            value=len(open_exceptions),
            unit="件",
            status="RISK"
            if any(e.severity in ("HIGH", "CRITICAL") for e in open_exceptions)
            else ("WATCH" if open_exceptions else "NORMAL"),
        ),
        KpiCard(key="process_total", label="流程资产（L1–L4）", value=process_total, unit="项"),
    ]

    # ---- 五阶段健康度
    stage_health: List[StageHealth] = []
    for stage_no, stage_name in STAGE_NAMES.items():
        stage_projects = [p for p in active if p.current_stage == stage_no]
        stage_steps = [
            s for s in steps if s.stage_no == stage_no and _project_active(projects, s.project_id)
        ]
        done = sum(1 for s in stage_steps if s.status == "DONE")
        total = len(stage_steps)
        if stage_projects:
            avg_progress = round(sum(p.progress for p in stage_projects) / len(stage_projects), 1)
        else:
            avg_progress = 0.0
        if not stage_projects:
            health = "GOOD"
        elif avg_progress >= 60:
            health = "GOOD"
        elif avg_progress >= 30:
            health = "WATCH"
        else:
            health = "RISK"
        stage_health.append(
            StageHealth(
                stage_no=stage_no,
                stage_name=stage_name,
                project_count=len(stage_projects),
                avg_progress=avg_progress,
                done_steps=done,
                total_steps=total,
                health=health,
            )
        )

    # ---- 方法论分布
    counts: Dict[str, int] = {m.value: 0 for m in Methodology}
    for p in projects:
        counts[p.methodology] = counts.get(p.methodology, 0) + 1
    total_projects = sum(counts.values()) or 1
    methodology_distribution = [
        MethodologySlice(
            methodology=method,
            label=METHODOLOGY_LABELS.get(method, method),
            count=count,
            share=round(count / total_projects, 4),
        )
        for method, count in sorted(counts.items(), key=lambda kv: -kv[1])
        if count > 0
    ]

    # ---- 项目看板
    today = date.today()
    ranked = sorted(active, key=lambda p: (p.priority, p.end_date or date.max))[:board_limit]
    project_board = [
        ProjectBoardItem(
            id=p.id,
            code=p.code,
            name=p.name,
            methodology=p.methodology,
            methodology_label=METHODOLOGY_LABELS.get(p.methodology, p.methodology),
            status=p.status,
            status_label=STATUS_LABELS.get(p.status, p.status),
            current_stage=p.current_stage,
            stage_name=STAGE_NAMES.get(p.current_stage, ""),
            priority=p.priority,
            owner=p.owner,
            progress=p.progress,
            improvement_pct=p.improvement_pct,
            metric_name=p.metric_name,
            target_value=p.target_value,
            current_value=p.current_value,
            metric_unit=p.metric_unit,
            is_overdue=bool(p.end_date and p.end_date < today and p.progress < 100),
        )
        for p in ranked
    ]

    # ---- 健康度预警
    health_alerts = _health_alerts(db)

    exception_summary = {
        "total": len(exceptions),
        "open": sum(1 for e in exceptions if e.status == ExceptionStatus.OPEN.value),
        "in_progress": sum(1 for e in exceptions if e.status == ExceptionStatus.IN_PROGRESS.value),
        "resolved": sum(1 for e in exceptions if e.status == ExceptionStatus.RESOLVED.value),
        "closed": sum(1 for e in exceptions if e.status == ExceptionStatus.CLOSED.value),
        "overdue": sum(1 for e in open_exceptions if e.due_at is not None and e.due_at < utcnow()),
        "by_severity": {
            sev: sum(1 for e in open_exceptions if e.severity == sev)
            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        },
    }

    knowledge_count = db.scalar(select(func.count()).select_from(KnowledgeItem)) or 0

    return DashboardOverview(
        cards=cards,
        stage_health=stage_health,
        methodology_distribution=methodology_distribution,
        project_board=project_board,
        health_alerts=health_alerts,
        exception_summary=exception_summary,
        knowledge_count=knowledge_count,
    )


def _project_active(projects: List[Project], project_id: int) -> bool:
    return any(p.id == project_id and p.status == ProjectStatus.ACTIVE.value for p in projects)


def _health_alerts(db: Session, limit: int = 8) -> List[HealthAlert]:
    rows = db.scalars(
        select(ProcessArch).where(
            ProcessArch.level >= 2,
            ProcessArch.is_draft.is_(False),
        )
    ).all()
    alerts: List[HealthAlert] = []
    for p in rows:
        reasons: List[str] = []
        level = "LOW"
        if p.health_score is not None and p.health_score < HEALTH_ALERT_THRESHOLD:
            reasons.append(
                f"流程健康度 {p.health_score:.0f} 分，低于 {HEALTH_ALERT_THRESHOLD:.0f} 分警戒线"
            )
            level = "HIGH" if p.health_score < 60 else "MEDIUM"
        if p.pain_score >= 4:
            reasons.append(f"痛点评分 {p.pain_score:.1f}/5")
            level = "HIGH"
        if not p.owner:
            reasons.append("未指定流程 Owner")
            level = level if level != "LOW" else "MEDIUM"
        if not reasons:
            continue
        alerts.append(
            HealthAlert(
                process_id=p.id,
                code=p.code,
                name=p.name,
                health_score=p.health_score,
                pain_score=p.pain_score,
                priority_score=p.priority_score,
                reason="；".join(reasons),
                level=level,
            )
        )
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: (rank.get(a.level, 3), -a.priority_score))
    return alerts[:limit]


def _kpi_red_yellow(db: Session, owner_user_id: int | None = None) -> tuple[int, int]:
    stmt = (
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True))
    )
    if owner_user_id is not None:
        stmt = stmt.where(KpiDefinition.owner_user_id == owner_user_id)
    total = 0
    red_yellow = 0
    for kpi in db.scalars(stmt).all():
        total += 1
        records = sorted(kpi.records, key=lambda row: row.period)
        if not records:
            continue
        state = kpi_service.status_for(
            records[-1].value,
            kpi.direction,
            kpi.red_threshold,
            kpi.yellow_threshold,
            kpi.green_threshold,
        )
        if state in ("RED", "YELLOW"):
            red_yellow += 1
    return total, red_yellow


def _next_actions(db: Session, user: User, limit: int = 3) -> List[HomeNextAction]:
    """当前用户最该继续推进的改善项目：阶段、下一步和阻塞项都来自真实记录。"""
    stmt = (
        select(Project)
        .where(
            Project.status == ProjectStatus.ACTIVE.value,
            Project.project_type == "IMPROVEMENT",
        )
        .order_by(Project.priority, Project.end_date, Project.id.desc())
    )
    if user.role == Role.OWNER.value:
        stmt = stmt.where(Project.owner_user_id == user.id)
    projects = list(db.scalars(stmt).all())[:limit]
    today = date.today()
    result: List[HomeNextAction] = []
    for project in projects:
        steps = list(
            db.scalars(
                select(ProjectStep)
                .where(ProjectStep.project_id == project.id)
                .order_by(ProjectStep.stage_no, ProjectStep.step_no)
            ).all()
        )
        head = next(
            (
                step
                for step in steps
                if step.status not in (StepStatus.DONE.value, StepStatus.SKIPPED.value)
            ),
            None,
        )
        template = (
            db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.step_no == head.step_no))
            if head
            else None
        )
        suggestion = None
        if head:
            suggestion = template.action if template else "按标准工作流推进该步骤。"
            if template and template.key_points:
                suggestion += f" 关键要点：{template.key_points}"
        open_exceptions = int(
            db.scalar(
                select(func.count())
                .select_from(ExceptionEvent)
                .where(
                    ExceptionEvent.project_id == project.id,
                    ExceptionEvent.status.in_(
                        [ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value]
                    ),
                )
            )
            or 0
        )
        result.append(
            HomeNextAction(
                project_id=project.id,
                code=project.code,
                name=project.name,
                owner=project.owner,
                current_stage=project.current_stage,
                stage_name=STAGE_NAMES.get(project.current_stage, f"阶段 {project.current_stage}"),
                progress=project.progress,
                next_step_no=head.step_no if head else None,
                next_step_name=head.name if head else None,
                next_suggestion=suggestion,
                open_exceptions=open_exceptions,
                is_overdue=bool(
                    project.end_date and project.end_date < today and project.progress < 100
                ),
            )
        )
    return result


def build_home(db: Session, user: User) -> DashboardHome:
    """角色化工作台：不同角色只看到自己需要先处理的事。"""
    startup = startup_service.status(db)
    open_findings = (
        db.scalar(
            select(func.count())
            .select_from(GovernanceFinding)
            .where(GovernanceFinding.status == "OPEN")
        )
        or 0
    )
    pending_changes = (
        db.scalar(
            select(func.count())
            .select_from(ProcessChangeRequest)
            .where(ProcessChangeRequest.status == ChangeStatus.SUBMITTED.value)
        )
        or 0
    )
    active_projects = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.status == ProjectStatus.ACTIVE.value,
                Project.project_type == "IMPROVEMENT",
            )
        )
        or 0
    )
    setup_projects = (
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.status.in_([ProjectStatus.PLANNING.value, ProjectStatus.ACTIVE.value]),
                Project.project_type == "GOVERNANCE_SETUP",
            )
        )
        or 0
    )
    next_step = next((s for s in startup.steps if s.key == startup.next_step), None)
    next_title = next_step.title if next_step else "九步已全部就绪"
    invalid_raci = next(
        (s.evidence.get("invalid_processes", 0) for s in startup.steps if s.key == "org_raci"),
        0,
    )
    total_kpi, red_yellow = _kpi_red_yellow(db)

    blocks: list[DashboardHomeBlock] = []
    if user.role in (Role.ADMIN.value, Role.MANAGER.value):
        blocks.append(
            DashboardHomeBlock(
                key="setup",
                title="流程试点进度",
                description="从立项定界到改善复制，按 9 个阶段推进",
                items=[
                    HomeItem(
                        label="已具备",
                        value=f"{startup.ready_count}/{startup.total} 个阶段",
                        hint=f"完成度 {startup.readiness_pct}%",
                    ),
                    HomeItem(label="下一步", value=next_title),
                ],
                actions=[
                    HomeAction(label="打开试点路径", view="start"),
                    HomeAction(label="战略目标", view="strategy"),
                    HomeAction(label="流程地图", view="map"),
                ],
            )
        )
        blocks.append(
            DashboardHomeBlock(
                key="governance",
                title="治理待办",
                description="先处理会阻塞发布或口径统一的事项",
                items=[
                    HomeItem(label="治理待办", value=f"{open_findings} 项"),
                    HomeItem(label="待审变更", value=f"{pending_changes} 张"),
                    HomeItem(label="RACI 不完整", value=f"{invalid_raci} 条流程"),
                    HomeItem(label="红/黄 KPI", value=f"{red_yellow}/{total_kpi}"),
                ],
                actions=[
                    HomeAction(label="治理概览", view="deliverables"),
                    HomeAction(label="变更审批", view="designer", hint="设计器 → 变更"),
                    HomeAction(label="KPI 明细", view="monitor"),
                ],
            )
        )
        blocks.append(
            DashboardHomeBlock(
                key="execution",
                title="正在推进",
                description="当前执行中的流程项目",
                items=[
                    HomeItem(label="执行中项目", value=f"{active_projects} 个"),
                    HomeItem(label="体系落地项目", value=f"{setup_projects} 个"),
                ],
                actions=[
                    HomeAction(label="项目组合", view="projects"),
                    HomeAction(
                        label="体系落地项目",
                        view="projects",
                        hint="9 阶段 / 27 步",
                        action="dashboard.setupProjects",
                    ),
                ],
            )
        )
        headline = (
            f"{user.display_name}，流程试点已具备 {startup.ready_count}/{startup.total} 个阶段；"
            f"当前 {open_findings} 项治理待办、{pending_changes} 张变更待审。"
        )
    elif user.role == Role.OWNER.value:
        owned_processes = list(
            db.scalars(
                select(ProcessArch)
                .where(ProcessArch.level == 3, ProcessArch.owner_user_id == user.id)
                .order_by(ProcessArch.code)
            ).all()
        )
        owned_total, owned_red_yellow = _kpi_red_yellow(db, user.id)
        owned_projects = list(
            db.scalars(
                select(Project)
                .where(
                    Project.owner_user_id == user.id,
                    Project.status.in_([ProjectStatus.PLANNING.value, ProjectStatus.ACTIVE.value]),
                    Project.project_type == "IMPROVEMENT",
                )
                .order_by(Project.id.desc())
                .limit(5)
            ).all()
        )
        owned_exceptions = (
            db.scalar(
                select(func.count())
                .select_from(ExceptionEvent)
                .where(
                    ExceptionEvent.owner_user_id == user.id,
                    ExceptionEvent.status.in_(
                        [ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value]
                    ),
                )
            )
            or 0
        )
        blocks.append(
            DashboardHomeBlock(
                key="my_processes",
                title="我的流程",
                description="你负责的 L3 端到端流程",
                items=[
                    HomeItem(
                        label=row.code,
                        value=row.name,
                        hint=f"健康度 {row.health_score if row.health_score is not None else '—'}",
                    )
                    for row in owned_processes[:5]
                ]
                or [HomeItem(label="暂无", value="还没有分配到你的 L3 流程")],
                actions=[HomeAction(label="流程地图", view="map")],
            )
        )
        blocks.append(
            DashboardHomeBlock(
                key="my_kpi",
                title="我的指标",
                description="你作为责任人的 KPI",
                items=[
                    HomeItem(label="指标总数", value=f"{owned_total} 个"),
                    HomeItem(label="红/黄", value=f"{owned_red_yellow} 个"),
                    HomeItem(label="待处理异常", value=f"{owned_exceptions} 件"),
                ],
                actions=[HomeAction(label="KPI 明细", view="monitor")],
            )
        )
        blocks.append(
            DashboardHomeBlock(
                key="my_projects",
                title="我的改善项目",
                description="进行中的改善项目与下一步",
                items=[
                    HomeItem(label=row.code, value=row.name, hint=f"进度 {row.progress:.0f}%")
                    for row in owned_projects
                ]
                or [HomeItem(label="暂无", value="还没有进行中的改善项目")],
                actions=[HomeAction(label="项目组合", view="projects")],
            )
        )
        headline = (
            f"{user.display_name}，你名下有 {len(owned_processes)} 条 L3 流程、"
            f"{owned_red_yellow} 个红/黄 KPI、{owned_exceptions} 件待处理异常。"
        )
    else:
        blocks.append(
            DashboardHomeBlock(
                key="readonly",
                title="只读概览",
                description="你可以查看整体进度，但不能修改业务数据",
                items=[
                    HomeItem(label="九步启动", value=f"{startup.ready_count}/{startup.total} 步"),
                    HomeItem(label="治理待办", value=f"{open_findings} 项"),
                    HomeItem(label="执行中项目", value=f"{active_projects} 个"),
                ],
                actions=[
                    HomeAction(label="启动向导", view="start"),
                    HomeAction(label="运营监控", view="monitor"),
                ],
            )
        )
        headline = (
            f"{user.display_name}，当前流程试点已具备 {startup.ready_count}/{startup.total} 个阶段，"
            f"有 {open_findings} 项治理待办。"
        )

    return DashboardHome(
        role=user.role,
        role_label=user.role_label,
        display_name=user.display_name,
        headline=headline,
        blocks=blocks,
        next_actions=_next_actions(db, user),
    )
