"""管理驾驶舱聚合。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.enums import ExceptionStatus, Methodology, ProjectStatus
from app.models.knowledge import KnowledgeItem
from app.models.monitor import ExceptionEvent
from app.models.process import ProcessArch
from app.models.project import Project, ProjectStep
from app.schemas.dashboard import (
    DashboardOverview,
    HealthAlert,
    KpiCard,
    MethodologySlice,
    ProjectBoardItem,
    StageHealth,
)

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
    projects = db.scalars(select(Project)).all()
    steps = db.scalars(select(ProjectStep)).all()

    active = [p for p in projects if p.status == ProjectStatus.ACTIVE.value]
    this_year = date.today().year
    closed_this_year = [
        p
        for p in projects
        if p.status == ProjectStatus.CLOSED.value
        and p.end_date is not None
        and p.end_date.year == this_year
    ]

    process_total = db.scalar(select(func.count()).select_from(ProcessArch)) or 0
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
    rows = db.scalars(select(ProcessArch).where(ProcessArch.level >= 2)).all()
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
