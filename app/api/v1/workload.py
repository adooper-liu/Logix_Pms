"""工作量与产能接口：标准工时卡、产能日历、标准 vs 实际汇总。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.enums import WorkMeasurementStatus
from app.schemas.common import DeleteResult, as_columns
from app.schemas.workload import (
    CapacityCalendarCreate,
    CapacityCalendarOut,
    CapacityCalendarUpdate,
    WorkloadMetaOut,
    WorkloadSummaryOut,
    WorkMeasurementObservationCreate,
    WorkMeasurementObservationOut,
    WorkMeasurementReviewIn,
    WorkMeasurementStandardCreate,
    WorkMeasurementStandardOut,
    WorkMeasurementStandardUpdate,
)
from app.services import audit as audit_service
from app.services import workload as workload_service

router = APIRouter(prefix="/workload", tags=["工作量与产能"])


@router.get("/meta", response_model=WorkloadMetaOut, summary="标准工时枚举中文标签")
def workload_meta():
    return WorkloadMetaOut(
        source_labels=workload_service.SOURCE_LABELS,
        status_labels=workload_service.STATUS_LABELS,
        boundary_note=workload_service.BOUNDARY_NOTE,
    )


@router.get(
    "/standards",
    response_model=List[WorkMeasurementStandardOut],
    summary="标准工时卡清单",
)
def list_standards(
    db: DbSession,
    user: CurrentUser,
    activity_id: Optional[int] = None,
    position_id: Optional[int] = None,
    status_: Optional[WorkMeasurementStatus] = Query(default=None, alias="status"),
    include_retired: bool = False,
):
    return workload_service.list_standards(
        db,
        activity_id=activity_id,
        position_id=position_id,
        status=status_.value if status_ else None,
        include_retired=include_retired,
    )


@router.get(
    "/standards/{standard_id}",
    response_model=WorkMeasurementStandardOut,
    summary="标准工时卡详情",
)
def get_standard(standard_id: int, db: DbSession, user: CurrentUser):
    row = workload_service.require_standard(db, standard_id)
    return workload_service.standard_out(db, row)


@router.post(
    "/standards",
    response_model=WorkMeasurementStandardOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增标准工时卡（草稿）",
)
def create_standard(payload: WorkMeasurementStandardCreate, db: DbSession, user: ManagerUser):
    try:
        row = workload_service.create_standard(db, as_columns(payload.model_dump()), user)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "work_measurement_standard",
        row.id,
        f"新增标准工时 {row.code}：{row.name} {row.standard_minutes} 分钟/次",
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.patch(
    "/standards/{standard_id}",
    response_model=WorkMeasurementStandardOut,
    summary="修改标准工时卡（口径变更自动升版并回到草稿）",
)
def update_standard(
    standard_id: int,
    payload: WorkMeasurementStandardUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = workload_service.require_standard(db, standard_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    try:
        workload_service.update_standard(db, row, data, user)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "work_measurement_standard",
        row.id,
        f"修改标准工时 {row.code} 到 v{row.version}，状态 {row.status}",
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.post(
    "/standards/{standard_id}/verify",
    response_model=WorkMeasurementStandardOut,
    summary="验证标准工时（只有已验证标准进入产能口径）",
)
def verify_standard(standard_id: int, db: DbSession, user: ManagerUser):
    row = workload_service.require_standard(db, standard_id)
    try:
        workload_service.verify_standard(db, row, user)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "work_measurement_standard",
        row.id,
        f"验证标准工时 {row.code} v{row.version}",
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.get(
    "/standards/{standard_id}/observations",
    response_model=List[WorkMeasurementObservationOut],
    summary="标准工时的现场观测记录",
)
def list_observations(standard_id: int, db: DbSession, user: CurrentUser):
    workload_service.require_standard(db, standard_id)
    return [
        workload_service.observation_out(db, row)
        for row in workload_service.list_observations(db, standard_id)
    ]


@router.post(
    "/standards/{standard_id}/observations",
    response_model=WorkMeasurementObservationOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增观测记录（均值和样本量自动回算，MANAGER+）",
)
def add_observation(
    standard_id: int,
    payload: WorkMeasurementObservationCreate,
    db: DbSession,
    user: ManagerUser,
):
    row = workload_service.require_standard(db, standard_id)
    try:
        observation = workload_service.add_observation(db, row, payload, user)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "work_measurement_observation",
        observation.id,
        f"新增观测记录：{row.code} 第 {observation.sequence} 条"
        f"（均值 {row.observed_minutes} 分，样本 {row.sample_size}）",
    )
    db.commit()
    db.refresh(observation)
    return workload_service.observation_out(db, observation)


@router.delete(
    "/standards/{standard_id}/observations/{observation_id}",
    response_model=DeleteResult,
    summary="删除观测记录（均值和样本量自动回算，MANAGER+）",
)
def delete_observation(standard_id: int, observation_id: int, db: DbSession, user: ManagerUser):
    row = workload_service.require_standard(db, standard_id)
    try:
        workload_service.delete_observation(db, row, observation_id)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "DELETE",
        "work_measurement_observation",
        observation_id,
        f"删除观测记录：{row.code}（均值 {row.observed_minutes} 分，样本 {row.sample_size}）",
    )
    db.commit()
    return DeleteResult(deleted=1)


@router.post(
    "/standards/{standard_id}/submit-review",
    response_model=WorkMeasurementStandardOut,
    summary="提交标准工时评审（至少 5 条有效样本，MANAGER+）",
)
def submit_review(standard_id: int, db: DbSession, user: ManagerUser):
    row = workload_service.require_standard(db, standard_id)
    try:
        workload_service.submit_review(db, row)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "work_measurement_standard",
        row.id,
        f"提交标准工时评审 {row.code} v{row.version}（样本 {row.sample_size}）",
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.post(
    "/standards/{standard_id}/review",
    response_model=WorkMeasurementStandardOut,
    summary="审核标准工时（通过 / 退回，MANAGER+）",
)
def review_standard(
    standard_id: int,
    payload: WorkMeasurementReviewIn,
    db: DbSession,
    user: ManagerUser,
):
    row = workload_service.require_standard(db, standard_id)
    try:
        workload_service.review_standard(db, row, user, payload.approved, payload.note)
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    decision = "通过" if payload.approved else "退回"
    audit_service.record(
        db,
        user,
        "UPDATE",
        "work_measurement_standard",
        row.id,
        f"审核标准工时 {row.code} v{row.version}：{decision}"
        + (f"（{payload.note}）" if payload.note else ""),
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.post(
    "/standards/{standard_id}/retire",
    response_model=WorkMeasurementStandardOut,
    summary="停用标准工时",
)
def retire_standard(standard_id: int, db: DbSession, user: ManagerUser):
    row = workload_service.require_standard(db, standard_id)
    workload_service.retire_standard(db, row)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "work_measurement_standard",
        row.id,
        f"停用标准工时 {row.code}",
    )
    db.commit()
    db.refresh(row)
    return workload_service.standard_out(db, row)


@router.get(
    "/capacity",
    response_model=List[CapacityCalendarOut],
    summary="产能日历",
)
def list_capacity(
    db: DbSession,
    user: CurrentUser,
    period: Optional[date] = None,
    org_unit_id: Optional[int] = None,
):
    return workload_service.list_capacity(db, period=period, org_unit_id=org_unit_id)


@router.post(
    "/capacity",
    response_model=CapacityCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记产能（组织 × 岗位 × 期间）",
)
def create_capacity(payload: CapacityCalendarCreate, db: DbSession, user: ManagerUser):
    try:
        row = workload_service.create_capacity(db, as_columns(payload.model_dump()))
    except workload_service.WorkloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "capacity_calendar",
        row.id,
        f"登记产能 {row.period} 组织 {row.org_unit_id} 岗位 {row.position_id}",
    )
    db.commit()
    db.refresh(row)
    return workload_service.capacity_out(db, row)


@router.patch(
    "/capacity/{capacity_id}",
    response_model=CapacityCalendarOut,
    summary="修改产能",
)
def update_capacity(
    capacity_id: int,
    payload: CapacityCalendarUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = workload_service.require_capacity(db, capacity_id)
    workload_service.update_capacity(db, row, as_columns(payload.model_dump(exclude_unset=True)))
    audit_service.record(
        db,
        user,
        "UPDATE",
        "capacity_calendar",
        row.id,
        f"修改产能 {row.period} 组织 {row.org_unit_id} 岗位 {row.position_id}",
    )
    db.commit()
    db.refresh(row)
    return workload_service.capacity_out(db, row)


@router.get(
    "/summary",
    response_model=WorkloadSummaryOut,
    summary="工作量汇总：标准需求 / 实际工时 / 产能利用率",
    description=(
        "标准工时只作为能力基线，用于产能、周期、成本与改善收益；"
        "不用于个人排名、扣罚或奖金分配。只有已验证工时会进入产能口径。"
    ),
)
def workload_summary(
    db: DbSession,
    user: CurrentUser,
    period: Optional[date] = Query(default=None, description="所看月份内任意日期，归一到 1 号"),
):
    return workload_service.summary(db, period=period)
