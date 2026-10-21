"""运营监控：KPI 雷达、时序、异常事件闭环。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, ManagerUser, WriteUser
from app.core.timeutil import utcnow
from app.models.enums import ExceptionSeverity, ExceptionStatus, KpiDimension, KpiDirection
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.schemas.common import DeleteResult, as_columns
from app.schemas.monitor import (
    ExceptionCreate,
    ExceptionOut,
    ExceptionSummary,
    ExceptionUpdate,
    KpiDefinitionCreate,
    KpiDefinitionOut,
    KpiRadarResponse,
    KpiRecordCreate,
    KpiRecordOut,
    KpiTrendPoint,
    KpiTrendSeries,
    RadarDimension,
)
from app.services import audit as audit_service

router = APIRouter(prefix="/monitor", tags=["运营监控"])

DIMENSION_LABELS = {
    KpiDimension.EFFICIENCY.value: "效率",
    KpiDimension.QUALITY.value: "质量",
    KpiDimension.COST.value: "成本",
    KpiDimension.FLEXIBILITY.value: "灵活性",
}

GOOD_THRESHOLD = 100.0
WATCH_THRESHOLD = 85.0


# ------------------------------------------------------------------ 工具函数


def _achievement(
    direction: str, value: Optional[float], target: Optional[float]
) -> Optional[float]:
    """达成率 %：越小越好的指标取反比。"""
    if value is None or target in (None, 0):
        return None
    if direction == KpiDirection.LOWER_BETTER.value:
        if value <= 0:
            return None
        return round(target / value * 100, 1)
    return round(value / target * 100, 1)


def _trend(records: List[KpiRecord]) -> Optional[str]:
    if len(records) < 2:
        return None
    delta = records[-1].value - records[-2].value
    if abs(delta) < 1e-9:
        return "FLAT"
    return "UP" if delta > 0 else "DOWN"


def _dimension_status(rate: float) -> str:
    if rate >= GOOD_THRESHOLD:
        return "GOOD"
    if rate >= WATCH_THRESHOLD:
        return "WATCH"
    return "RISK"


def _to_kpi_out(kpi: KpiDefinition) -> KpiDefinitionOut:
    records = sorted(kpi.records, key=lambda r: r.period)
    latest = records[-1].value if records else None
    return KpiDefinitionOut(
        id=kpi.id,
        code=kpi.code,
        name=kpi.name,
        dimension=kpi.dimension,
        direction=kpi.direction,
        unit=kpi.unit,
        target_value=kpi.target_value,
        baseline_value=kpi.baseline_value,
        description=kpi.description,
        process_id=kpi.process_id,
        owner=kpi.owner,
        is_active=kpi.is_active,
        latest_value=latest,
        achievement_rate=_achievement(kpi.direction, latest, kpi.target_value),
        trend=_trend(records),
    )


def _to_exception_out(e: ExceptionEvent) -> ExceptionOut:
    data = {c.name: getattr(e, c.name) for c in e.__table__.columns}
    data["is_overdue"] = bool(
        e.due_at is not None
        and e.due_at < utcnow()
        and e.status in (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
    )
    return ExceptionOut.model_validate(data)


# ------------------------------------------------------------------ KPI


@router.get("/kpi-radar", response_model=KpiRadarResponse, summary="四维度 KPI 雷达 + 时序")
def kpi_radar(db: DbSession, include_series: bool = True):
    kpis = db.scalars(select(KpiDefinition).where(KpiDefinition.is_active.is_(True))).all()

    buckets: Dict[str, List[float]] = {d.value: [] for d in KpiDimension}
    series: List[KpiTrendSeries] = []

    for kpi in kpis:
        out = _to_kpi_out(kpi)
        if out.achievement_rate is not None:
            buckets.setdefault(kpi.dimension, []).append(out.achievement_rate)
        if include_series:
            records = sorted(kpi.records, key=lambda r: r.period)
            series.append(
                KpiTrendSeries(
                    kpi_id=kpi.id,
                    code=kpi.code,
                    name=kpi.name,
                    dimension=kpi.dimension,
                    unit=kpi.unit,
                    target_value=kpi.target_value,
                    direction=kpi.direction,
                    points=[KpiTrendPoint(period=r.period, value=r.value) for r in records],
                )
            )

    dimensions: List[RadarDimension] = []
    for dim in KpiDimension:
        values = buckets.get(dim.value, [])
        rate = round(sum(values) / len(values), 1) if values else 0.0
        dimensions.append(
            RadarDimension(
                dimension=dim.value,
                label=DIMENSION_LABELS[dim.value],
                kpi_count=len(values),
                achievement_rate=rate,
                status=_dimension_status(rate) if values else "WATCH",
            )
        )

    scored = [d.achievement_rate for d in dimensions if d.kpi_count > 0]
    return KpiRadarResponse(
        overall_achievement=round(sum(scored) / len(scored), 1) if scored else 0.0,
        dimensions=dimensions,
        series=series,
    )


@router.get("/kpis", response_model=List[KpiDefinitionOut], summary="KPI 定义清单")
def list_kpis(
    db: DbSession,
    dimension: Optional[KpiDimension] = None,
    process_id: Optional[int] = None,
):
    stmt = select(KpiDefinition)
    if dimension is not None:
        stmt = stmt.where(KpiDefinition.dimension == dimension.value)
    if process_id is not None:
        stmt = stmt.where(KpiDefinition.process_id == process_id)
    rows = db.scalars(stmt.order_by(KpiDefinition.dimension, KpiDefinition.code)).all()
    return [_to_kpi_out(k) for k in rows]


@router.post(
    "/kpis",
    response_model=KpiDefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增 KPI 定义",
)
def create_kpi(payload: KpiDefinitionCreate, db: DbSession, user: ManagerUser):
    if db.scalar(select(KpiDefinition).where(KpiDefinition.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"KPI 编码 {payload.code} 已存在")
    obj = KpiDefinition(**as_columns(payload.model_dump()))
    db.add(obj)
    db.flush()
    audit_service.record(db, user, "CREATE", "kpi", obj.id, f"新增 KPI {obj.code} {obj.name}")
    db.commit()
    db.refresh(obj)
    return _to_kpi_out(obj)


@router.get("/kpis/{kpi_id}/records", response_model=List[KpiRecordOut], summary="KPI 时序数据")
def list_records(kpi_id: int, db: DbSession):
    if db.get(KpiDefinition, kpi_id) is None:
        raise HTTPException(status_code=404, detail="KPI 不存在")
    rows = db.scalars(
        select(KpiRecord).where(KpiRecord.kpi_id == kpi_id).order_by(KpiRecord.period)
    ).all()
    return [KpiRecordOut.model_validate(r) for r in rows]


@router.post(
    "/kpis/{kpi_id}/records",
    response_model=KpiRecordOut,
    status_code=status.HTTP_201_CREATED,
    summary="追加 KPI 数据点（同期同项目重复提交则覆盖）",
)
def add_record(kpi_id: int, payload: KpiRecordCreate, db: DbSession, user: ManagerUser):
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise HTTPException(status_code=404, detail="KPI 不存在")
    existing = db.scalar(
        select(KpiRecord).where(
            KpiRecord.kpi_id == kpi_id,
            KpiRecord.period == payload.period,
            KpiRecord.project_id == payload.project_id,
        )
    )
    if existing is not None:
        existing.value = payload.value
        existing.note = payload.note
        audit_service.record(
            db,
            user,
            "UPDATE",
            "kpi_record",
            existing.id,
            f"{kpi.code} {payload.period} 数据点改为 {payload.value}",
        )
        db.commit()
        db.refresh(existing)
        return KpiRecordOut.model_validate(existing)
    obj = KpiRecord(kpi_id=kpi_id, **as_columns(payload.model_dump()))
    db.add(obj)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "kpi_record",
        obj.id,
        f"{kpi.code} 新增 {payload.period} 数据点 {payload.value}",
    )
    db.commit()
    db.refresh(obj)
    return KpiRecordOut.model_validate(obj)


# ------------------------------------------------------------------ 异常事件


@router.get("/exceptions/summary", response_model=ExceptionSummary, summary="异常事件概览")
def exception_summary(db: DbSession):
    rows = db.scalars(select(ExceptionEvent)).all()
    open_rows = [
        e
        for e in rows
        if e.status in (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
    ]
    now = utcnow()
    return ExceptionSummary(
        total=len(rows),
        open=sum(1 for e in rows if e.status == ExceptionStatus.OPEN.value),
        in_progress=sum(1 for e in rows if e.status == ExceptionStatus.IN_PROGRESS.value),
        resolved=sum(1 for e in rows if e.status == ExceptionStatus.RESOLVED.value),
        closed=sum(1 for e in rows if e.status == ExceptionStatus.CLOSED.value),
        overdue=sum(1 for e in open_rows if e.due_at is not None and e.due_at < now),
        by_severity={
            sev.value: sum(1 for e in open_rows if e.severity == sev.value)
            for sev in ExceptionSeverity
        },
    )


@router.get("/exceptions", response_model=List[ExceptionOut], summary="异常事件列表")
def list_exceptions(
    db: DbSession,
    status_: Optional[ExceptionStatus] = Query(default=None, alias="status"),
    severity: Optional[ExceptionSeverity] = None,
    process_id: Optional[int] = None,
    project_id: Optional[int] = None,
    owner: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    stmt = select(ExceptionEvent)
    if status_ is not None:
        stmt = stmt.where(ExceptionEvent.status == status_.value)
    if severity is not None:
        stmt = stmt.where(ExceptionEvent.severity == severity.value)
    if process_id is not None:
        stmt = stmt.where(ExceptionEvent.process_id == process_id)
    if project_id is not None:
        stmt = stmt.where(ExceptionEvent.project_id == project_id)
    if owner:
        stmt = stmt.where(ExceptionEvent.owner.like(f"%{owner}%"))
    rows = db.scalars(stmt.order_by(ExceptionEvent.detected_at.desc()).limit(limit)).all()
    return [_to_exception_out(e) for e in rows]


@router.post(
    "/exceptions",
    response_model=ExceptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记异常事件",
)
def create_exception(payload: ExceptionCreate, db: DbSession, user: WriteUser):
    year = date.today().year
    prefix = f"EXC-{year}-"
    existing = db.scalars(
        select(ExceptionEvent.code).where(ExceptionEvent.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    obj = ExceptionEvent(code=f"{prefix}{seq + 1:03d}", **as_columns(payload.model_dump()))
    db.add(obj)
    db.flush()
    audit_service.record(
        db, user, "CREATE", "exception", obj.id, f"登记异常 {obj.code} {obj.title}"
    )
    db.commit()
    db.refresh(obj)
    return _to_exception_out(obj)


@router.get("/exceptions/{exception_id}", response_model=ExceptionOut, summary="异常事件详情")
def get_exception(exception_id: int, db: DbSession):
    obj = db.get(ExceptionEvent, exception_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="异常事件不存在")
    return _to_exception_out(obj)


@router.patch(
    "/exceptions/{exception_id}", response_model=ExceptionOut, summary="处理 / 关闭异常事件"
)
def update_exception(exception_id: int, payload: ExceptionUpdate, db: DbSession, user: WriteUser):
    obj = db.get(ExceptionEvent, exception_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="异常事件不存在")
    previous_status = obj.status

    data = as_columns(payload.model_dump(exclude_unset=True))
    for field, value in data.items():
        setattr(obj, field, value)

    if "status" in data:
        new_status = data["status"]
        if new_status == ExceptionStatus.RESOLVED.value and obj.resolved_at is None:
            obj.resolved_at = utcnow()
        if new_status == ExceptionStatus.CLOSED.value:
            obj.resolved_at = obj.resolved_at or utcnow()
            obj.closed_at = utcnow()
        elif new_status in (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value):
            # 重开意味着闭环结论被推翻，两个时间戳必须一起清掉，
            # 否则台账会出现「未闭环但已有闭环时间」的矛盾记录
            obj.resolved_at = None
            obj.closed_at = None
    audit_service.record(
        db,
        user,
        "UPDATE",
        "exception",
        obj.id,
        f"{obj.code} {previous_status} → {obj.status}",
    )
    db.commit()
    db.refresh(obj)
    return _to_exception_out(obj)


@router.delete("/exceptions/{exception_id}", response_model=DeleteResult, summary="删除异常事件")
def delete_exception(exception_id: int, db: DbSession, user: WriteUser):
    obj = db.get(ExceptionEvent, exception_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="异常事件不存在")
    audit_service.record(
        db, user, "DELETE", "exception", obj.id, f"删除异常 {obj.code} {obj.title}"
    )
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=1)
