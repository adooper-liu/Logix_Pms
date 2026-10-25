"""工作量服务：标准工时卡、产能日历与「标准 vs 实际」汇总。

口径约定：
- 标准工时 = 观测时间 × 评定系数 × (1 + 宽放率)；
- 月度需求工时 = 标准工时 × 计划频次；
- 可用工时 = 人数 × 人均可用小时 × 60 × 出勤率 × 设备可用率；
- 只有 VERIFIED 的标准进入利用率与成本口径，ESTIMATE 一律不进入；
- 标准工时只作为能力基线，不用于个人排名、扣罚或奖金分配。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.timeutil import utcnow
from app.models.enums import WorkMeasurementSource, WorkMeasurementStatus
from app.models.execution import ProcessTask, TaskWorklog
from app.models.org import OrgUnit, Position
from app.models.process import ProcessArch
from app.models.process_task import ProcessTaskDefinition
from app.models.user import User
from app.models.workload import (
    CapacityCalendar,
    WorkMeasurementObservation,
    WorkMeasurementStandard,
)
from app.schemas.workload import (
    CapacityCalendarOut,
    WorkloadActualRow,
    WorkloadCapacityRow,
    WorkloadStandardRow,
    WorkloadSummaryOut,
    WorkloadTotals,
    WorkMeasurementObservationOut,
    WorkMeasurementStandardOut,
)

BOUNDARY_NOTE = (
    "标准工时只作为能力基线，用于产能、周期、成本与改善收益；"
    "不用于个人排名、扣罚或奖金分配。只有已验证工时会进入产能口径。"
)

SOURCE_LABELS = {
    WorkMeasurementSource.TIME_STUDY.value: "时间研究",
    WorkMeasurementSource.WORK_SAMPLING.value: "工作抽样",
    WorkMeasurementSource.PREDETERMINED.value: "预定时间",
    WorkMeasurementSource.ESTIMATE.value: "估算（未验证）",
}

STATUS_LABELS = {
    WorkMeasurementStatus.DRAFT.value: "草稿",
    WorkMeasurementStatus.IN_REVIEW.value: "待审核",
    WorkMeasurementStatus.VERIFIED.value: "已验证",
    WorkMeasurementStatus.RETIRED.value: "已停用",
}

# 时间研究工作流的最低有效样本数；旧的手工标准仍可按 sample_size 验证
MIN_OBSERVATIONS = 5

MEASUREMENT_FIELDS = {
    "activity_id",
    "task_id",
    "position_id",
    "org_unit_id",
    "method_description",
    "source",
    "observed_minutes",
    "rating_factor",
    "allowance_rate",
    "sample_size",
    "monthly_frequency",
    "valid_from",
    "valid_to",
}


class WorkloadError(ValueError):
    """工作量规则拒绝；API 层转成 400/409。"""


def normalize_period(period: Optional[date] = None) -> date:
    """把任意日期归一到所在月的 1 号。"""
    value = period or date.today()
    return value.replace(day=1)


def month_bounds(period: Optional[date] = None) -> tuple[date, date]:
    start = normalize_period(period)
    end = date(start.year + (1 if start.month == 12 else 0), start.month % 12 + 1, 1)
    return start, end


def compute_standard_minutes(observed: float, rating: float, allowance: float) -> float:
    return round(float(observed) * float(rating) * (1 + float(allowance)), 2)


def next_standard_code(db: Session) -> str:
    prefix = f"WS-{date.today().year}-"
    existing = db.scalars(
        select(WorkMeasurementStandard.code).where(WorkMeasurementStandard.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def require_standard(db: Session, standard_id: int) -> WorkMeasurementStandard:
    row = db.get(WorkMeasurementStandard, standard_id)
    if row is None:
        raise WorkloadError(f"标准工时 {standard_id} 不存在")
    return row


def require_capacity(db: Session, capacity_id: int) -> CapacityCalendar:
    row = db.get(CapacityCalendar, capacity_id)
    if row is None:
        raise WorkloadError(f"产能记录 {capacity_id} 不存在")
    return row


def _validate_activity(db: Session, activity_id: int) -> None:
    activity = db.get(ProcessArch, activity_id)
    if activity is None:
        raise WorkloadError(f"活动 {activity_id} 不存在")
    if activity.level != 4:
        raise WorkloadError("标准工时必须绑定 L4 活动")


def _validate_position_org(db: Session, position_id: int, org_unit_id: Optional[int]) -> Position:
    position = db.get(Position, position_id)
    if position is None:
        raise WorkloadError(f"岗位 {position_id} 不存在")
    if org_unit_id is not None:
        if db.get(OrgUnit, org_unit_id) is None:
            raise WorkloadError(f"组织 {org_unit_id} 不存在")
        if position.org_unit_id is not None and position.org_unit_id != org_unit_id:
            raise WorkloadError("岗位不属于所选组织")
    return position


def validate_standard(db: Session, data: Dict) -> None:
    _validate_activity(db, data["activity_id"])
    task_id = data.get("task_id")
    if task_id is not None:
        task = db.get(ProcessTaskDefinition, task_id)
        if task is None:
            raise WorkloadError(f"L5 任务 {task_id} 不存在")
        if task.activity_id != data["activity_id"]:
            raise WorkloadError("L5 任务必须属于所选 L4 活动")
    _validate_position_org(db, data["position_id"], data.get("org_unit_id"))
    valid_from = data.get("valid_from")
    valid_to = data.get("valid_to")
    if valid_from and valid_to and valid_from > valid_to:
        raise WorkloadError("生效日期不能晚于失效日期")
    if data.get("source") == WorkMeasurementSource.ESTIMATE.value:
        # 估算可以保存，但不能被当成已验证标准使用
        return
    if data.get("observed_minutes", 0) <= 0:
        raise WorkloadError("观测时间必须大于 0")
    if data.get("rating_factor", 1) <= 0:
        raise WorkloadError("评定系数必须大于 0")
    if not (0 <= data.get("allowance_rate", 0) <= 1):
        raise WorkloadError("宽放率必须在 0–1 之间")


def create_standard(db: Session, data: Dict, user: User) -> WorkMeasurementStandard:
    data = dict(data)
    if not data.get("code"):
        data["code"] = next_standard_code(db)
    validate_standard(db, data)
    if db.scalar(
        select(WorkMeasurementStandard).where(WorkMeasurementStandard.code == data["code"])
    ):
        raise WorkloadError(f"标准工时编码 {data['code']} 已存在")
    data["standard_minutes"] = compute_standard_minutes(
        data["observed_minutes"], data["rating_factor"], data["allowance_rate"]
    )
    data["version"] = 1
    data["created_by_id"] = user.id
    row = WorkMeasurementStandard(**data)
    db.add(row)
    db.flush()
    return row


def update_standard(
    db: Session, row: WorkMeasurementStandard, data: Dict, user: User
) -> WorkMeasurementStandard:
    data = dict(data)
    if "code" in data and data["code"] != row.code:
        if db.scalar(
            select(WorkMeasurementStandard).where(
                WorkMeasurementStandard.code == data["code"],
                WorkMeasurementStandard.id != row.id,
            )
        ):
            raise WorkloadError(f"标准工时编码 {data['code']} 已存在")
    has_observations = bool(
        db.scalar(
            select(func.count())
            .select_from(WorkMeasurementObservation)
            .where(WorkMeasurementObservation.standard_id == row.id)
        )
    )
    if has_observations and {"observed_minutes", "sample_size"} & set(data):
        raise WorkloadError("已有观测记录，均值和样本量由观测记录自动计算")
    merged = {field: data.get(field, getattr(row, field)) for field in MEASUREMENT_FIELDS}
    validate_standard(db, merged)
    changed = any(field in data for field in MEASUREMENT_FIELDS)
    for field, value in data.items():
        setattr(row, field, value)
    if changed:
        row.standard_minutes = compute_standard_minutes(
            row.observed_minutes, row.rating_factor, row.allowance_rate
        )
        row.version = (row.version or 1) + 1
        # 已验证/待审核的标准一旦改口径就必须重新验证，避免旧结论悄悄失效
        if row.status in (
            WorkMeasurementStatus.VERIFIED.value,
            WorkMeasurementStatus.IN_REVIEW.value,
        ):
            row.status = WorkMeasurementStatus.DRAFT.value
            row.verified_by_id = None
            row.verified_at = None
            row.reviewed_by_id = None
            row.reviewed_at = None
            row.review_note = None
    db.flush()
    return row


def observation_out(db: Session, row: WorkMeasurementObservation) -> WorkMeasurementObservationOut:
    observer = db.get(User, row.observer_user_id) if row.observer_user_id else None
    return WorkMeasurementObservationOut(
        id=row.id,
        standard_id=row.standard_id,
        sequence=row.sequence,
        observed_minutes=row.observed_minutes,
        observed_at=row.observed_at,
        observer_user_id=row.observer_user_id,
        observer_name=observer.display_name if observer else None,
        note=row.note,
        created_at=row.created_at,
    )


def list_observations(db: Session, standard_id: int) -> List[WorkMeasurementObservation]:
    return list(
        db.scalars(
            select(WorkMeasurementObservation)
            .where(WorkMeasurementObservation.standard_id == standard_id)
            .order_by(WorkMeasurementObservation.sequence)
        ).all()
    )


def _recompute_from_observations(db: Session, row: WorkMeasurementStandard) -> None:
    observations = list_observations(db, row.id)
    row.sample_size = len(observations)
    if not observations:
        return
    row.observed_minutes = round(
        sum(item.observed_minutes for item in observations) / len(observations), 4
    )
    row.standard_minutes = compute_standard_minutes(
        row.observed_minutes, row.rating_factor, row.allowance_rate
    )


def _reset_for_new_evidence(row: WorkMeasurementStandard) -> None:
    """样本或口径变化后，旧的验证/评审结论必须失效。"""
    if row.status in (
        WorkMeasurementStatus.VERIFIED.value,
        WorkMeasurementStatus.IN_REVIEW.value,
    ):
        row.status = WorkMeasurementStatus.DRAFT.value
        row.version = (row.version or 1) + 1
        row.verified_by_id = None
        row.verified_at = None
        row.reviewed_by_id = None
        row.reviewed_at = None
        row.review_note = None


def add_observation(
    db: Session,
    row: WorkMeasurementStandard,
    payload,
    user: User,
) -> WorkMeasurementObservation:
    if row.status == WorkMeasurementStatus.RETIRED.value:
        raise WorkloadError("已停用的标准工时不能新增观测记录")
    sequence = (
        db.scalar(
            select(func.max(WorkMeasurementObservation.sequence)).where(
                WorkMeasurementObservation.standard_id == row.id
            )
        )
        or 0
    ) + 1
    observation = WorkMeasurementObservation(
        standard_id=row.id,
        sequence=sequence,
        observed_minutes=payload.observed_minutes,
        observed_at=payload.observed_at or utcnow(),
        observer_user_id=user.id,
        note=payload.note,
    )
    db.add(observation)
    _reset_for_new_evidence(row)
    db.flush()
    _recompute_from_observations(db, row)
    db.flush()
    return observation


def delete_observation(db: Session, row: WorkMeasurementStandard, observation_id: int) -> None:
    observation = db.get(WorkMeasurementObservation, observation_id)
    if observation is None or observation.standard_id != row.id:
        raise WorkloadError("观测记录不存在")
    db.delete(observation)
    _reset_for_new_evidence(row)
    db.flush()
    _recompute_from_observations(db, row)
    db.flush()


def submit_review(db: Session, row: WorkMeasurementStandard) -> None:
    if row.status == WorkMeasurementStatus.IN_REVIEW.value:
        return
    if row.status != WorkMeasurementStatus.DRAFT.value:
        raise WorkloadError("只有草稿状态的标准工时可以提交评审")
    if row.source == WorkMeasurementSource.ESTIMATE.value:
        raise WorkloadError("估算工时不走评审，也不能标记为已验证")
    if not (row.method_description or "").strip():
        raise WorkloadError("请先填写方法说明，再提交评审")
    if row.sample_size < MIN_OBSERVATIONS:
        raise WorkloadError(f"有效样本不足：至少需要 {MIN_OBSERVATIONS} 条观测或样本")
    row.status = WorkMeasurementStatus.IN_REVIEW.value
    row.verified_by_id = None
    row.verified_at = None
    row.reviewed_by_id = None
    row.reviewed_at = None
    row.review_note = None
    db.flush()


def review_standard(
    db: Session,
    row: WorkMeasurementStandard,
    user: User,
    approved: bool,
    note: Optional[str],
) -> None:
    if row.status != WorkMeasurementStatus.IN_REVIEW.value:
        raise WorkloadError("只有待审核的标准工时可以评审")
    if not approved and not (note or "").strip():
        raise WorkloadError("退回时必须填写原因")
    row.reviewed_by_id = user.id
    row.reviewed_at = utcnow()
    row.review_note = (note or "").strip() or None
    if approved:
        row.status = WorkMeasurementStatus.VERIFIED.value
        row.verified_by_id = user.id
        row.verified_at = utcnow()
    else:
        row.status = WorkMeasurementStatus.DRAFT.value
        row.verified_by_id = None
        row.verified_at = None
    db.flush()


def verify_standard(db: Session, row: WorkMeasurementStandard, user: User) -> None:
    if row.source == WorkMeasurementSource.ESTIMATE.value:
        raise WorkloadError("估算工时不经验证，不能标记为已验证")
    if row.sample_size <= 0:
        raise WorkloadError("样本量为 0，不能验证")
    if not (row.method_description or "").strip():
        raise WorkloadError("请先填写方法说明，再验证标准工时")
    row.status = WorkMeasurementStatus.VERIFIED.value
    row.verified_by_id = user.id
    row.verified_at = utcnow()


def retire_standard(db: Session, row: WorkMeasurementStandard) -> None:
    row.status = WorkMeasurementStatus.RETIRED.value
    db.flush()


def standard_out(db: Session, row: WorkMeasurementStandard) -> WorkMeasurementStandardOut:
    activity = db.get(ProcessArch, row.activity_id)
    position = db.get(Position, row.position_id)
    org_unit = db.get(OrgUnit, row.org_unit_id) if row.org_unit_id else None
    verified_by = db.get(User, row.verified_by_id) if row.verified_by_id else None
    reviewed_by = db.get(User, row.reviewed_by_id) if row.reviewed_by_id else None
    observation_count = int(
        db.scalar(
            select(func.count())
            .select_from(WorkMeasurementObservation)
            .where(WorkMeasurementObservation.standard_id == row.id)
        )
        or 0
    )
    return WorkMeasurementStandardOut(
        id=row.id,
        code=row.code,
        name=row.name,
        activity_id=row.activity_id,
        activity_code=activity.code if activity else None,
        activity_name=activity.name if activity else None,
        task_id=row.task_id,
        task_code=row.task.code if row.task else None,
        task_name=row.task.name if row.task else None,
        position_id=row.position_id,
        position_name=position.name if position else None,
        org_unit_id=row.org_unit_id,
        org_unit_name=org_unit.name if org_unit else None,
        method_description=row.method_description,
        source=row.source,
        source_label=SOURCE_LABELS.get(row.source, row.source),
        observed_minutes=row.observed_minutes,
        rating_factor=row.rating_factor,
        allowance_rate=row.allowance_rate,
        standard_minutes=row.standard_minutes,
        sample_size=row.sample_size,
        monthly_frequency=row.monthly_frequency,
        demand_minutes=round(row.standard_minutes * row.monthly_frequency, 2),
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        version=row.version,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        note=row.note,
        verified_by_id=row.verified_by_id,
        verified_by_name=verified_by.display_name if verified_by else None,
        verified_at=row.verified_at,
        observation_count=observation_count,
        reviewed_by_id=row.reviewed_by_id,
        reviewed_by_name=reviewed_by.display_name if reviewed_by else None,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
        created_at=row.created_at,
    )


def list_standards(
    db: Session,
    *,
    activity_id: Optional[int] = None,
    position_id: Optional[int] = None,
    status: Optional[str] = None,
    include_retired: bool = False,
) -> List[WorkMeasurementStandardOut]:
    stmt = select(WorkMeasurementStandard)
    if activity_id is not None:
        stmt = stmt.where(WorkMeasurementStandard.activity_id == activity_id)
    if position_id is not None:
        stmt = stmt.where(WorkMeasurementStandard.position_id == position_id)
    if status is not None:
        stmt = stmt.where(WorkMeasurementStandard.status == status)
    elif not include_retired:
        stmt = stmt.where(WorkMeasurementStandard.status != WorkMeasurementStatus.RETIRED.value)
    rows = db.scalars(
        stmt.order_by(WorkMeasurementStandard.activity_id, WorkMeasurementStandard.code)
    ).all()
    return [standard_out(db, row) for row in rows]


def capacity_out(db: Session, row: CapacityCalendar) -> CapacityCalendarOut:
    org_unit = db.get(OrgUnit, row.org_unit_id)
    position = db.get(Position, row.position_id)
    available = (
        row.headcount
        * row.available_hours_per_person
        * 60
        * row.attendance_rate
        * row.equipment_availability
    )
    return CapacityCalendarOut(
        id=row.id,
        org_unit_id=row.org_unit_id,
        org_unit_name=org_unit.name if org_unit else None,
        position_id=row.position_id,
        position_name=position.name if position else None,
        period=row.period,
        headcount=row.headcount,
        available_hours_per_person=row.available_hours_per_person,
        attendance_rate=row.attendance_rate,
        equipment_availability=row.equipment_availability,
        available_minutes=round(available, 2),
        note=row.note,
        created_at=row.created_at,
    )


def create_capacity(db: Session, data: Dict) -> CapacityCalendar:
    data = dict(data)
    data["period"] = normalize_period(data["period"])
    _validate_position_org(db, data["position_id"], data["org_unit_id"])
    existing = db.scalar(
        select(CapacityCalendar).where(
            CapacityCalendar.org_unit_id == data["org_unit_id"],
            CapacityCalendar.position_id == data["position_id"],
            CapacityCalendar.period == data["period"],
        )
    )
    if existing is not None:
        raise WorkloadError("该组织/岗位/期间已有产能记录，请直接修改")
    row = CapacityCalendar(**data)
    db.add(row)
    db.flush()
    return row


def update_capacity(db: Session, row: CapacityCalendar, data: Dict) -> CapacityCalendar:
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def list_capacity(
    db: Session, period: Optional[date] = None, org_unit_id: Optional[int] = None
) -> List[CapacityCalendarOut]:
    stmt = select(CapacityCalendar)
    if period is not None:
        stmt = stmt.where(CapacityCalendar.period == normalize_period(period))
    if org_unit_id is not None:
        stmt = stmt.where(CapacityCalendar.org_unit_id == org_unit_id)
    rows = db.scalars(
        stmt.order_by(CapacityCalendar.period.desc(), CapacityCalendar.org_unit_id)
    ).all()
    return [capacity_out(db, row) for row in rows]


def _effective_org(row: WorkMeasurementStandard, position: Optional[Position]) -> Optional[int]:
    return row.org_unit_id or (position.org_unit_id if position else None)


def summary(db: Session, period: Optional[date] = None) -> WorkloadSummaryOut:
    start, end = month_bounds(period)

    standards = db.scalars(
        select(WorkMeasurementStandard)
        .options(
            joinedload(WorkMeasurementStandard.activity),
            selectinload(WorkMeasurementStandard.reviewed_by),
        )
        .where(
            WorkMeasurementStandard.status != WorkMeasurementStatus.RETIRED.value,
            (WorkMeasurementStandard.valid_from.is_(None))
            | (WorkMeasurementStandard.valid_from < end),
            (WorkMeasurementStandard.valid_to.is_(None))
            | (WorkMeasurementStandard.valid_to >= start),
        )
    ).all()
    observation_counts = dict(
        db.execute(
            select(
                WorkMeasurementObservation.standard_id,
                func.count(),
            )
            .where(WorkMeasurementObservation.standard_id.in_([row.id for row in standards]))
            .group_by(WorkMeasurementObservation.standard_id)
        ).all()
    )
    standard_rows = [
        WorkloadStandardRow(
            standard_id=row.id,
            code=row.code,
            name=row.name,
            activity_id=row.activity_id,
            activity_code=row.activity.code if row.activity else None,
            activity_name=row.activity.name if row.activity else None,
            position_id=row.position_id,
            position_name=row.position.name if row.position else None,
            standard_minutes=row.standard_minutes,
            monthly_frequency=row.monthly_frequency,
            demand_minutes=round(row.standard_minutes * row.monthly_frequency, 2),
            sample_size=row.sample_size,
            observation_count=observation_counts.get(row.id, 0),
            observed_minutes=row.observed_minutes,
            review_note=row.review_note,
            reviewed_by_name=(row.reviewed_by.display_name if row.reviewed_by else None),
            status=row.status,
            status_label=STATUS_LABELS.get(row.status, row.status),
            source=row.source,
            source_label=SOURCE_LABELS.get(row.source, row.source),
            included=row.status == WorkMeasurementStatus.VERIFIED.value,
        )
        for row in standards
    ]
    verified = [row for row in standards if row.status == WorkMeasurementStatus.VERIFIED.value]

    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.min)
    actual_rows_raw = db.execute(
        select(
            ProcessTask.activity_id,
            User.position_id,
            func.count(func.distinct(TaskWorklog.task_id)),
            func.coalesce(func.sum(TaskWorklog.effort_minutes), 0.0),
        )
        .join(ProcessTask, ProcessTask.id == TaskWorklog.task_id)
        .outerjoin(User, User.id == TaskWorklog.user_id)
        .where(TaskWorklog.created_at >= start_dt, TaskWorklog.created_at < end_dt)
        .group_by(ProcessTask.activity_id, User.position_id)
    ).all()
    activity_ids = {row[0] for row in actual_rows_raw if row[0] is not None}
    position_ids = {row[1] for row in actual_rows_raw if row[1] is not None}
    activities = (
        {
            row.id: row
            for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(activity_ids)))
        }
        if activity_ids
        else {}
    )
    positions = (
        {row.id: row for row in db.scalars(select(Position).where(Position.id.in_(position_ids)))}
        if position_ids
        else {}
    )
    actual_rows = [
        WorkloadActualRow(
            activity_id=activity_id,
            activity_code=activities[activity_id].code if activity_id in activities else None,
            activity_name=activities[activity_id].name if activity_id in activities else None,
            position_id=position_id,
            position_name=positions[position_id].name if position_id in positions else None,
            task_count=int(task_count or 0),
            effort_minutes=round(float(effort or 0), 2),
        )
        for activity_id, position_id, task_count, effort in actual_rows_raw
    ]

    capacity_rows_raw = db.scalars(
        select(CapacityCalendar).where(CapacityCalendar.period == start)
    ).all()
    capacity_rows: List[WorkloadCapacityRow] = []
    for capacity in capacity_rows_raw:
        demand = 0.0
        for row in verified:
            position = db.get(Position, row.position_id)
            if row.position_id != capacity.position_id:
                continue
            if _effective_org(row, position) != capacity.org_unit_id:
                continue
            demand += row.standard_minutes * row.monthly_frequency
        available = (
            capacity.headcount
            * capacity.available_hours_per_person
            * 60
            * capacity.attendance_rate
            * capacity.equipment_availability
        )
        capacity_rows.append(
            WorkloadCapacityRow(
                capacity_id=capacity.id,
                org_unit_id=capacity.org_unit_id,
                org_unit_name=capacity.org_unit.name if capacity.org_unit else None,
                position_id=capacity.position_id,
                position_name=capacity.position.name if capacity.position else None,
                period=capacity.period,
                headcount=capacity.headcount,
                available_minutes=round(available, 2),
                demand_minutes=round(demand, 2),
                gap_minutes=round(demand - available, 2),
                utilization=round(demand / available, 4) if available > 0 else None,
            )
        )

    demand_total = round(sum(row.demand_minutes for row in standard_rows if row.included), 2)
    available_total = round(sum(row.available_minutes for row in capacity_rows), 2)
    actual_total = round(sum(row.effort_minutes for row in actual_rows), 2)
    return WorkloadSummaryOut(
        period=start,
        standards=standard_rows,
        actual=actual_rows,
        capacity=capacity_rows,
        totals=WorkloadTotals(
            demand_minutes=demand_total,
            available_minutes=available_total,
            actual_minutes=actual_total,
            utilization=(round(demand_total / available_total, 4) if available_total > 0 else None),
        ),
    )
