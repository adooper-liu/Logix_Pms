"""KPI 定义卡规则：口径完整性、阈值语义与活动绑定。

这些规则放在服务层，API 只管出入参与审计；这样定义卡的校验可以被
种子、导入脚本和后续的 KPI 治理扫描复用。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import InstanceStatus, KpiDirection, ProjectStatus
from app.models.execution import ProcessInstance
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.project import Project
from app.services import process_scope


class KpiDefinitionError(ValueError):
    """KPI 定义卡规则拒绝；API 层转成 400/409。"""


STATUS_LABELS = {
    "RED": "红",
    "YELLOW": "黄",
    "GREEN": "绿",
    "GRAY": "灰（未取数）",
}


def validate_definition(
    formula: Optional[str], numerator: Optional[str], denominator: Optional[str]
) -> None:
    """新建 KPI 必须写清口径：公式，或分子 + 分母。"""
    if (formula or "").strip():
        return
    if (numerator or "").strip() and (denominator or "").strip():
        return
    raise KpiDefinitionError("请填写计算公式，或同时填写分子与分母")


def validate_dates(valid_from: Optional[date], valid_to: Optional[date]) -> None:
    if valid_from and valid_to and valid_from > valid_to:
        raise KpiDefinitionError("生效日期不能晚于失效日期")


def validate_thresholds(
    direction: str,
    red: Optional[float],
    yellow: Optional[float],
    green: Optional[float],
) -> None:
    """红/黄/绿三条线必须同进同退，且顺序与指标方向一致。

    HIGHER_BETTER：red ≤ yellow ≤ green（越低越差）；
    LOWER_BETTER ：red ≥ yellow ≥ green（越高越差）。
    """
    values = [red, yellow, green]
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise KpiDefinitionError("红/黄/绿阈值必须同时填写或同时留空")
    if direction == KpiDirection.HIGHER_BETTER.value:
        if not (red <= yellow <= green):
            raise KpiDefinitionError("越大越好的指标必须满足：红线 ≤ 黄线 ≤ 绿线")
    elif not (red >= yellow >= green):
        raise KpiDefinitionError("越小越好的指标必须满足：红线 ≥ 黄线 ≥ 绿线")


def status_for(
    value: Optional[float],
    direction: str,
    red: Optional[float],
    yellow: Optional[float],
    green: Optional[float],
) -> str:
    """按定义卡阈值判定 RED / YELLOW / GREEN。

    没有数据点或阈值未填全时返回 GRAY（未取数），而不是空值：
    灰色本身就是“等待上游/缺数据”的可视信号。
    """
    if value is None or any(threshold is None for threshold in (red, yellow, green)):
        return "GRAY"
    if direction == KpiDirection.HIGHER_BETTER.value:
        if value < red:
            return "RED"
        if value >= green:
            return "GREEN"
        return "YELLOW"
    if value > red:
        return "RED"
    if value <= green:
        return "GREEN"
    return "YELLOW"


def validate_activity(
    db: Session,
    process_id: Optional[int],
    activity_id: Optional[int],
) -> None:
    """活动必须是 L4，且同时指定流程时必须在流程子树内。"""
    if activity_id is None:
        return
    activity = db.get(ProcessArch, activity_id)
    if activity is None:
        raise KpiDefinitionError(f"活动 {activity_id} 不存在")
    if activity.level != 4:
        raise KpiDefinitionError("activity_id 必须指向 L4 活动")
    if process_id is not None and process_id not in process_scope.ancestor_ids(db, activity_id):
        raise KpiDefinitionError("所选活动不属于该流程")


def ensure_formula_consistency(
    db: Session,
    *,
    name: str,
    process_id: Optional[int],
    formula: Optional[str],
    exclude_id: Optional[int] = None,
) -> None:
    """同一流程下，同名 KPI 不允许出现两种公式。

    这是“同名异义”的硬门禁：只要两条定义都写了公式且不同，就拒绝。
    没有写公式的旧数据不参与判断，避免历史数据阻塞维护。
    """
    normalized = (name or "").strip()
    incoming = (formula or "").strip()
    if not normalized or not incoming:
        return
    rows = db.scalars(
        select(KpiDefinition).where(
            KpiDefinition.process_id == process_id,
            KpiDefinition.name == normalized,
        )
    ).all()
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        existing = (row.formula or "").strip()
        if existing and existing != incoming:
            raise KpiDefinitionError(
                f"同名 KPI「{normalized}」已存在不同公式（{row.code}）；"
                "请改用不同的指标名，或统一口径后再保存"
            )


# 时长单位折成秒。项目上的「min」和指标上的「分钟」是同一个口径。
_UNIT_SECONDS = {
    "天": 86400.0,
    "日": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
    "小时": 3600.0,
    "时": 3600.0,
    "h": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "分钟": 60.0,
    "分": 60.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
}
_UNIT_CANON = {86400.0: "day", 3600.0: "hour", 60.0: "minute"}
# 点一下就完成的实例不进入月均，避免测试点击覆盖正式数据点。
MIN_CYCLE_SECONDS = 60.0
EXECUTION_NOTE = "流程执行月均周期"
_OPEN_PROJECT = (
    ProjectStatus.PLANNING.value,
    ProjectStatus.ACTIVE.value,
    ProjectStatus.ON_HOLD.value,
)


def ordered_records(records: Sequence[KpiRecord]) -> list[KpiRecord]:
    """全系统只按（期间，id）取最新一条，避免同一期有两条时各页面各取一条。"""
    return sorted(records, key=lambda row: (row.period, row.id or 0))


def latest_of(records: Sequence[KpiRecord]) -> Optional[KpiRecord]:
    ordered = ordered_records(records)
    return ordered[-1] if ordered else None


def latest_value(db: Session, kpi_id: int) -> Optional[float]:
    row = db.scalar(
        select(KpiRecord)
        .where(KpiRecord.kpi_id == kpi_id)
        .order_by(KpiRecord.period.desc(), KpiRecord.id.desc())
    )
    return None if row is None else float(row.value)


def _unit_key(unit: Optional[str]) -> str:
    key = (unit or "").strip()
    seconds = _UNIT_SECONDS.get(key, _UNIT_SECONDS.get(key.lower()))
    if seconds is None:
        return key.lower()
    return _UNIT_CANON[seconds]


def _duration_seconds(unit: Optional[str]) -> Optional[float]:
    key = (unit or "").strip()
    return _UNIT_SECONDS.get(key, _UNIT_SECONDS.get(key.lower()))


def _resolve_kpi(db: Session, project: Project) -> Optional[KpiDefinition]:
    if project.source_kpi_id is not None:
        return db.get(KpiDefinition, project.source_kpi_id)
    if project.process_id is None or not (project.metric_unit or "").strip():
        return None
    rows = db.scalars(
        select(KpiDefinition).where(
            KpiDefinition.process_id == project.process_id,
            KpiDefinition.is_active.is_(True),
        )
    ).all()
    matched = [row for row in rows if _unit_key(row.unit) == _unit_key(project.metric_unit)]
    if len(matched) == 1:
        return matched[0]
    return None


def align_project(db: Session, project: Project) -> None:
    """项目当前值等于来源 KPI 的最新数据点。没有唯一来源时保持原值。"""
    if project.status not in _OPEN_PROJECT:
        return
    kpi = _resolve_kpi(db, project)
    if kpi is None:
        return
    value = latest_value(db, kpi.id)
    if value is None:
        return
    project.source_kpi_id = kpi.id
    project.current_value = value


def align_open_projects(db: Session) -> None:
    rows = db.scalars(select(Project).where(Project.status.in_(_OPEN_PROJECT))).all()
    for row in rows:
        align_project(db, row)
    db.flush()


def save_record(
    db: Session,
    kpi: KpiDefinition,
    *,
    period: date,
    value: float,
    project_id: Optional[int],
    note: Optional[str],
) -> KpiRecord:
    """写入指标数据点，并让挂着这条指标的项目当前值跟着变。"""
    project_cond = (
        KpiRecord.project_id.is_(None) if project_id is None else KpiRecord.project_id == project_id
    )
    existing = db.scalar(
        select(KpiRecord).where(
            KpiRecord.kpi_id == kpi.id,
            KpiRecord.period == period,
            project_cond,
            or_(KpiRecord.note.is_(None), KpiRecord.note != EXECUTION_NOTE),
        )
    )
    if existing is None:
        existing = KpiRecord(
            kpi_id=kpi.id,
            period=period,
            value=value,
            project_id=project_id,
            note=note,
        )
        db.add(existing)
    else:
        existing.value = value
        existing.note = note
    db.flush()
    align_open_projects(db)
    return existing


def _month_start(moment: datetime) -> date:
    return moment.date().replace(day=1)


def _next_month(day: date) -> date:
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1)
    return day.replace(month=day.month + 1)


def record_completed_instance(db: Session, instance: ProcessInstance) -> None:
    """已完成实例的历时，回写到该流程上单位为时长的 KPI，按月取平均。"""
    if instance.completed_at is None or instance.started_at is None or instance.process_id is None:
        return
    elapsed = (instance.completed_at - instance.started_at).total_seconds()
    if elapsed < MIN_CYCLE_SECONDS:
        return
    kpis = [
        row
        for row in db.scalars(
            select(KpiDefinition).where(
                KpiDefinition.process_id == instance.process_id,
                KpiDefinition.is_active.is_(True),
            )
        ).all()
        if _duration_seconds(row.unit) is not None
    ]
    if not kpis:
        return
    period = _month_start(instance.completed_at)
    start = datetime.combine(period, time.min)
    end = datetime.combine(_next_month(period), time.min)
    instances = db.scalars(
        select(ProcessInstance).where(
            ProcessInstance.process_id == instance.process_id,
            ProcessInstance.status == InstanceStatus.COMPLETED.value,
            ProcessInstance.completed_at >= start,
            ProcessInstance.completed_at < end,
            ProcessInstance.started_at.is_not(None),
        )
    ).all()
    samples = [
        (row.completed_at - row.started_at).total_seconds()
        for row in instances
        if row.completed_at is not None
        and row.started_at is not None
        and (row.completed_at - row.started_at).total_seconds() >= MIN_CYCLE_SECONDS
    ]
    if not samples:
        return
    for kpi in kpis:
        scale = _duration_seconds(kpi.unit)
        if not scale:
            continue
        value = round(sum(sample / scale for sample in samples) / len(samples), 2)
        existing = db.scalar(
            select(KpiRecord).where(
                KpiRecord.kpi_id == kpi.id,
                KpiRecord.period == period,
                KpiRecord.project_id.is_(None),
                KpiRecord.note == EXECUTION_NOTE,
            )
        )
        if existing is None:
            db.add(
                KpiRecord(
                    kpi_id=kpi.id,
                    period=period,
                    value=value,
                    project_id=None,
                    note=EXECUTION_NOTE,
                )
            )
        else:
            existing.value = value
        db.flush()
    align_open_projects(db)
