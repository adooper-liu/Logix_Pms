"""改善项目卡：从 KPI 越线生成草稿，并维护来源与复制口径。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ImprovementSource,
    Methodology,
    ProjectStatus,
    ReplicationStatus,
)
from app.models.monitor import ExceptionEvent, KpiDefinition
from app.models.process import ProcessArch
from app.models.project import Project
from app.models.user import User
from app.schemas.monitor import ImprovementCandidateOut
from app.services import deliverable as deliverable_service
from app.services import kpi as kpi_service
from app.services.workflow import seed_project_steps

SOURCE_LABELS = {
    ImprovementSource.MANUAL.value: "手工立项",
    ImprovementSource.KPI_THRESHOLD.value: "KPI 越线",
    ImprovementSource.EXCEPTION.value: "流程异常",
    ImprovementSource.AUDIT_FINDING.value: "审计发现",
    ImprovementSource.CUSTOMER_COMPLAINT.value: "客户投诉",
    ImprovementSource.EMPLOYEE_SUGGESTION.value: "员工建议",
    ImprovementSource.BENCHMARK_GAP.value: "对标差距",
    ImprovementSource.OTHER.value: "其他",
}

REPLICATION_LABELS = {
    ReplicationStatus.NOT_EVALUATED.value: "未评估",
    ReplicationStatus.PILOT.value: "试点中",
    ReplicationStatus.REPLICATED.value: "已复制",
    ReplicationStatus.REJECTED.value: "拒绝复制",
}

KPI_STATUS_LABELS = {"RED": "红", "YELLOW": "黄", "GREEN": "绿"}

EXCEPTION_SEVERITY_LABELS = {
    ExceptionSeverity.CRITICAL.value: "紧急",
    ExceptionSeverity.HIGH.value: "高",
    ExceptionSeverity.MEDIUM.value: "中",
    ExceptionSeverity.LOW.value: "低",
}

# 严重度 → 项目优先级：紧急/高先做，低优先级放后
EXCEPTION_PRIORITY = {
    ExceptionSeverity.CRITICAL.value: 1,
    ExceptionSeverity.HIGH.value: 1,
    ExceptionSeverity.MEDIUM.value: 2,
    ExceptionSeverity.LOW.value: 3,
}

PROJECT_STATUS_LABELS = {
    ProjectStatus.PLANNING.value: "立项中",
    ProjectStatus.ACTIVE.value: "执行中",
    ProjectStatus.ON_HOLD.value: "暂停",
    ProjectStatus.CLOSED.value: "已结项",
    ProjectStatus.CANCELLED.value: "已取消",
}

ACTIVE_PROJECT_STATUSES = (
    ProjectStatus.PLANNING.value,
    ProjectStatus.ACTIVE.value,
    ProjectStatus.ON_HOLD.value,
)


class ImprovementError(ValueError):
    """改善项目规则拒绝；API 层转成 400/409。"""


def next_project_code(db: Session) -> str:
    prefix = f"PRJ-{date.today().year}-"
    existing = db.scalars(select(Project.code).where(Project.code.like(f"{prefix}%"))).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def candidates(db: Session) -> list[ImprovementCandidateOut]:
    """自动扫描红/黄 KPI，排除已有进行中改善项目的指标。"""
    kpis = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True))
    ).all()
    active_project_kpi_ids = set(
        db.scalars(
            select(Project.source_kpi_id).where(
                Project.source_kpi_id.is_not(None),
                Project.status.in_(ACTIVE_PROJECT_STATUSES),
            )
        ).all()
    )
    process_ids = {kpi.process_id for kpi in kpis if kpi.process_id is not None}
    processes = (
        {
            row.id: row
            for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(process_ids)))
        }
        if process_ids
        else {}
    )

    rows: list[ImprovementCandidateOut] = []
    for kpi in kpis:
        if kpi.id in active_project_kpi_ids:
            continue
        records = sorted(kpi.records, key=lambda item: item.period)
        latest = records[-1].value if records else None
        status = kpi_service.status_for(
            latest,
            kpi.direction,
            kpi.red_threshold,
            kpi.yellow_threshold,
            kpi.green_threshold,
        )
        if status not in ("RED", "YELLOW"):
            continue
        process = processes.get(kpi.process_id) if kpi.process_id else None
        rows.append(
            ImprovementCandidateOut(
                kpi_id=kpi.id,
                code=kpi.code,
                name=kpi.name,
                status=status,
                status_label=KPI_STATUS_LABELS.get(status, status),
                latest_value=latest,
                target_value=kpi.target_value,
                unit=kpi.unit,
                red_threshold=kpi.red_threshold,
                yellow_threshold=kpi.yellow_threshold,
                green_threshold=kpi.green_threshold,
                process_id=kpi.process_id,
                process_code=process.code if process else None,
                process_name=process.name if process else None,
                owner=kpi.owner,
                owner_user_id=kpi.owner_user_id,
            )
        )
    rows.sort(key=lambda row: (0 if row.status == "RED" else 1, row.code))
    return rows


def draft_from_kpi(db: Session, kpi: KpiDefinition, user: User) -> Project:
    """把红/黄 KPI 转成一张改善项目草稿；同一 KPI 不允许并行多张。"""
    records = sorted(kpi.records, key=lambda row: row.period)
    latest = records[-1].value if records else None
    if latest is None:
        raise ImprovementError("该 KPI 还没有数据点，无法判断是否越线")
    status = kpi_service.status_for(
        latest,
        kpi.direction,
        kpi.red_threshold,
        kpi.yellow_threshold,
        kpi.green_threshold,
    )
    if status not in ("RED", "YELLOW"):
        raise ImprovementError("该 KPI 当前不在红/黄区间，不需要自动立项")
    if kpi.target_value is None:
        raise ImprovementError("该 KPI 没有目标值，无法形成改善目标")

    existing = db.scalar(
        select(Project).where(
            Project.source_kpi_id == kpi.id,
            Project.status.in_(ACTIVE_PROJECT_STATUSES),
        )
    )
    if existing is not None:
        raise ImprovementError(f"该 KPI 已有进行中的改善项目 {existing.code}")

    unit = kpi.unit or ""
    status_label = KPI_STATUS_LABELS.get(status, status)
    improvement_pct = (
        round(abs(latest - kpi.target_value) / abs(latest) * 100, 1) if latest else None
    )
    project = Project(
        code=next_project_code(db),
        name=f"改善：{kpi.name}",
        methodology=Methodology.BPI.value,
        status=ProjectStatus.PLANNING.value,
        current_stage=1,
        priority=1 if status == "RED" else 2,
        process_id=kpi.process_id or kpi.activity_id,
        owner=kpi.owner or user.display_name,
        owner_user_id=kpi.owner_user_id or user.id,
        objective=(
            f"将 {kpi.name} 从 {latest}{unit} 改善到 {kpi.target_value}{unit}"
            f"（当前{status_label}区间）"
        ),
        scope=f"KPI 定义卡 {kpi.code}；公式：{kpi.formula or '—'}",
        metric_name=kpi.name,
        baseline_value=latest,
        target_value=kpi.target_value,
        current_value=latest,
        metric_unit=kpi.unit,
        improvement_pct=improvement_pct,
        source=ImprovementSource.KPI_THRESHOLD.value,
        source_kpi_id=kpi.id,
        problem_statement=(
            f"{kpi.name} 当前 {latest}{unit}，处于{status_label}区间"
            f"（红线 {kpi.red_threshold} / 黄线 {kpi.yellow_threshold} / "
            f"绿线 {kpi.green_threshold}）"
        ),
    )
    db.add(project)
    db.flush()
    seed_project_steps(db, project)
    db.flush()
    deliverable_service.sync_project_instances(db, project)
    return project


def draft_from_exception(db: Session, exception: ExceptionEvent, user: User) -> Project:
    """把未闭环异常转成一张改善项目草稿；同一条异常只允许一张进行中的项目。"""
    if exception.status not in (
        ExceptionStatus.OPEN.value,
        ExceptionStatus.IN_PROGRESS.value,
    ):
        raise ImprovementError("该异常已解决或已闭环，不需要再转改善项目")

    existing = db.get(Project, exception.project_id) if exception.project_id else None
    if existing is not None and existing.status in ACTIVE_PROJECT_STATUSES:
        raise ImprovementError(f"该异常已有进行中的改善项目 {existing.code}")

    severity_label = EXCEPTION_SEVERITY_LABELS.get(exception.severity, exception.severity)
    project = Project(
        code=next_project_code(db),
        name=f"改善：{exception.title}",
        methodology=Methodology.BPI.value,
        status=ProjectStatus.PLANNING.value,
        current_stage=1,
        priority=EXCEPTION_PRIORITY.get(exception.severity, 3),
        process_id=exception.process_id,
        owner=exception.owner or user.display_name,
        owner_user_id=exception.owner_user_id or user.id,
        objective=f"闭环异常 {exception.code}：{exception.title}",
        scope=(
            f"异常事件 {exception.code}（{severity_label}，"
            f"发现于 {exception.detected_at:%Y-%m-%d}）"
        ),
        source=ImprovementSource.EXCEPTION.value,
        problem_statement=exception.description or exception.title,
        root_cause=exception.root_cause,
        countermeasure=exception.action_taken,
    )
    db.add(project)
    db.flush()
    seed_project_steps(db, project)
    db.flush()
    deliverable_service.sync_project_instances(db, project)

    # 关联指针只保留在异常侧，避免项目和异常各存一份关系
    exception.project_id = project.id
    if exception.status == ExceptionStatus.OPEN.value:
        exception.status = ExceptionStatus.IN_PROGRESS.value
    db.flush()
    return project
