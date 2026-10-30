"""运营监控：KPI 雷达、时序、异常事件闭环。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    apply_owner_update,
    ensure_can_edit_owned,
    resolve_owner,
)
from app.core.timeutil import utcnow
from app.models.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    KpiDimension,
    KpiDirection,
    KpiFrequency,
    KpiKind,
    Role,
)
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.schemas.common import DeleteResult, as_columns
from app.schemas.monitor import (
    ExceptionCreate,
    ExceptionOut,
    ExceptionSummary,
    ExceptionUpdate,
    ImprovementCandidateOut,
    KpiDefinitionCreate,
    KpiDefinitionOut,
    KpiDefinitionUpdate,
    KpiKindSummary,
    KpiMetaOut,
    KpiRadarResponse,
    KpiRecordCreate,
    KpiRecordOut,
    KpiTrendPoint,
    KpiTrendSeries,
    RadarDimension,
)
from app.schemas.project import ProjectDraftOut
from app.services import audit as audit_service
from app.services import improvement as improvement_service
from app.services import integrations as integration_service
from app.services import kpi as kpi_service
from app.services import notifications as notification_service

router = APIRouter(prefix="/monitor", tags=["运营监控"])

DIMENSION_LABELS = {
    KpiDimension.EFFICIENCY.value: "效率",
    KpiDimension.QUALITY.value: "质量",
    KpiDimension.COST.value: "成本",
    KpiDimension.FLEXIBILITY.value: "灵活性",
}

KIND_LABELS = {
    KpiKind.RESULT.value: "结果",
    KpiKind.PROCESS.value: "过程",
    KpiKind.HEALTH.value: "健康度",
}

FREQUENCY_LABELS = {
    KpiFrequency.DAILY.value: "每日",
    KpiFrequency.WEEKLY.value: "每周",
    KpiFrequency.MONTHLY.value: "每月",
    KpiFrequency.QUARTERLY.value: "每季",
    KpiFrequency.AD_HOC.value: "按需",
}

STATUS_LABELS = {
    "RED": "红",
    "YELLOW": "黄",
    "GREEN": "绿",
    "GRAY": "灰（未取数）",
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
            # 越小越好的指标实际值为 0（例如零缺陷/零客诉）就是达成目标，
            # 不能因为除法无意义就返回空值，否则雷达图会把最好的情况漏掉
            return 100.0
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
    records = kpi_service.ordered_records(kpi.records)
    latest = records[-1].value if records else None
    status = kpi_service.status_for(
        latest,
        kpi.direction,
        kpi.red_threshold,
        kpi.yellow_threshold,
        kpi.green_threshold,
    )
    return KpiDefinitionOut(
        id=kpi.id,
        code=kpi.code,
        name=kpi.name,
        dimension=kpi.dimension,
        kind=kpi.kind,
        kind_label=KIND_LABELS.get(kpi.kind, kpi.kind),
        direction=kpi.direction,
        unit=kpi.unit,
        target_value=kpi.target_value,
        baseline_value=kpi.baseline_value,
        description=kpi.description,
        formula=kpi.formula,
        numerator=kpi.numerator,
        denominator=kpi.denominator,
        granularity=kpi.granularity,
        frequency=kpi.frequency,
        frequency_label=FREQUENCY_LABELS.get(kpi.frequency, kpi.frequency),
        source_system=kpi.source_system,
        quality_rule=kpi.quality_rule,
        red_threshold=kpi.red_threshold,
        yellow_threshold=kpi.yellow_threshold,
        green_threshold=kpi.green_threshold,
        process_id=kpi.process_id,
        activity_id=kpi.activity_id,
        owner=kpi.owner,
        owner_user_id=kpi.owner_user_id,
        version=kpi.version,
        valid_from=kpi.valid_from,
        valid_to=kpi.valid_to,
        is_active=kpi.is_active,
        latest_value=latest,
        achievement_rate=_achievement(kpi.direction, latest, kpi.target_value),
        trend=_trend(records),
        status=status,
        status_label=STATUS_LABELS.get(status) if status else None,
    )


def _to_series(kpi: KpiDefinition) -> KpiTrendSeries:
    records = kpi_service.ordered_records(kpi.records)
    latest = records[-1].value if records else None
    status = kpi_service.status_for(
        latest,
        kpi.direction,
        kpi.red_threshold,
        kpi.yellow_threshold,
        kpi.green_threshold,
    )
    return KpiTrendSeries(
        kpi_id=kpi.id,
        code=kpi.code,
        name=kpi.name,
        dimension=kpi.dimension,
        kind=kpi.kind,
        kind_label=KIND_LABELS.get(kpi.kind, kpi.kind),
        unit=kpi.unit,
        target_value=kpi.target_value,
        direction=kpi.direction,
        frequency=kpi.frequency,
        granularity=kpi.granularity,
        status=status,
        status_label=STATUS_LABELS.get(status) if status else None,
        points=[KpiTrendPoint(period=r.period, value=r.value) for r in records],
    )


def _to_exception_out(e: ExceptionEvent) -> ExceptionOut:
    data = {c.name: getattr(e, c.name) for c in e.__table__.columns}
    data["is_overdue"] = bool(
        e.due_at is not None
        and e.due_at < utcnow()
        and e.status in (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
    )
    return ExceptionOut.model_validate(data)


def _exception_event(e: ExceptionEvent) -> dict:
    return {
        "exception_id": e.id,
        "code": e.code,
        "title": e.title,
        "severity": e.severity,
        "status": e.status,
        "process_id": e.process_id,
        "project_id": e.project_id,
        "owner_user_id": e.owner_user_id,
        "owner": e.owner,
        "due_at": e.due_at,
    }


# ------------------------------------------------------------------ KPI


@router.get("/kpi-radar", response_model=KpiRadarResponse, summary="四维度 KPI 雷达 + 时序")
def kpi_radar(db: DbSession, include_series: bool = True):
    kpis = db.scalars(select(KpiDefinition).where(KpiDefinition.is_active.is_(True))).all()

    buckets: Dict[str, List[float]] = {d.value: [] for d in KpiDimension}
    series: List[KpiTrendSeries] = []
    kind_stats: Dict[str, Dict[str, int]] = {
        kind.value: {"total": 0, "RED": 0, "YELLOW": 0, "GREEN": 0, "GRAY": 0} for kind in KpiKind
    }

    for kpi in kpis:
        out = _to_kpi_out(kpi)
        if out.achievement_rate is not None:
            buckets.setdefault(kpi.dimension, []).append(out.achievement_rate)
        stats = kind_stats.setdefault(
            kpi.kind, {"total": 0, "RED": 0, "YELLOW": 0, "GREEN": 0, "GRAY": 0}
        )
        stats["total"] += 1
        stats[out.status or "GRAY"] += 1
        if include_series:
            series.append(_to_series(kpi))

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

    by_kind = [
        KpiKindSummary(
            kind=kind,
            label=KIND_LABELS.get(kind, kind),
            kpi_count=stats["total"],
            red=stats["RED"],
            yellow=stats["YELLOW"],
            green=stats["GREEN"],
            gray=stats["GRAY"],
        )
        for kind, stats in kind_stats.items()
    ]

    scored = [d.achievement_rate for d in dimensions if d.kpi_count > 0]
    return KpiRadarResponse(
        overall_achievement=round(sum(scored) / len(scored), 1) if scored else 0.0,
        dimensions=dimensions,
        by_kind=by_kind,
        series=series,
    )


@router.get("/meta", response_model=KpiMetaOut, summary="KPI 枚举中文标签")
def kpi_meta():
    """中文标签由后端下发，前端不维护映射表。"""
    return KpiMetaOut(
        kind_labels=KIND_LABELS,
        frequency_labels=FREQUENCY_LABELS,
        status_labels=STATUS_LABELS,
        dimension_labels=DIMENSION_LABELS,
    )


@router.get("/kpis", response_model=List[KpiDefinitionOut], summary="KPI 定义清单")
def list_kpis(
    db: DbSession,
    dimension: Optional[KpiDimension] = None,
    kind: Optional[KpiKind] = None,
    frequency: Optional[KpiFrequency] = None,
    process_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    active_only: bool = False,
):
    stmt = select(KpiDefinition)
    if dimension is not None:
        stmt = stmt.where(KpiDefinition.dimension == dimension.value)
    if kind is not None:
        stmt = stmt.where(KpiDefinition.kind == kind.value)
    if frequency is not None:
        stmt = stmt.where(KpiDefinition.frequency == frequency.value)
    if process_id is not None:
        stmt = stmt.where(KpiDefinition.process_id == process_id)
    if activity_id is not None:
        stmt = stmt.where(KpiDefinition.activity_id == activity_id)
    if owner_user_id is not None:
        stmt = stmt.where(KpiDefinition.owner_user_id == owner_user_id)
    if active_only:
        stmt = stmt.where(KpiDefinition.is_active.is_(True))
    rows = db.scalars(stmt.order_by(KpiDefinition.dimension, KpiDefinition.code)).all()
    return [_to_kpi_out(k) for k in rows]


@router.get("/kpis/{kpi_id}", response_model=KpiDefinitionOut, summary="KPI 定义详情")
def get_kpi(kpi_id: int, db: DbSession):
    obj = db.get(KpiDefinition, kpi_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="KPI 不存在")
    return _to_kpi_out(obj)


@router.post(
    "/kpis",
    response_model=KpiDefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增 KPI 定义卡",
)
def create_kpi(payload: KpiDefinitionCreate, db: DbSession, user: ManagerUser):
    if db.scalar(select(KpiDefinition).where(KpiDefinition.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"KPI 编码 {payload.code} 已存在")
    try:
        kpi_service.validate_definition(payload.formula, payload.numerator, payload.denominator)
        kpi_service.validate_dates(payload.valid_from, payload.valid_to)
        kpi_service.validate_thresholds(
            payload.direction.value,
            payload.red_threshold,
            payload.yellow_threshold,
            payload.green_threshold,
        )
        kpi_service.validate_activity(db, payload.process_id, payload.activity_id)
        kpi_service.ensure_formula_consistency(
            db,
            name=payload.name,
            process_id=payload.process_id,
            formula=payload.formula,
        )
    except kpi_service.KpiDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = as_columns(payload.model_dump())
    data["owner_user_id"], data["owner"] = resolve_owner(db, payload.owner_user_id, payload.owner)
    data["version"] = 1
    obj = KpiDefinition(**data)
    db.add(obj)
    db.flush()
    audit_service.record(
        db, user, "CREATE", "kpi", obj.id, f"新增 KPI 定义卡 {obj.code} {obj.name} v1"
    )
    db.commit()
    db.refresh(obj)
    return _to_kpi_out(obj)


@router.patch("/kpis/{kpi_id}", response_model=KpiDefinitionOut, summary="修改 KPI 定义卡")
def update_kpi(kpi_id: int, payload: KpiDefinitionUpdate, db: DbSession, user: ManagerUser):
    obj = db.get(KpiDefinition, kpi_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="KPI 不存在")

    data = as_columns(payload.model_dump(exclude_unset=True))
    if "code" in data and data["code"] != obj.code:
        if db.scalar(select(KpiDefinition).where(KpiDefinition.code == data["code"])):
            raise HTTPException(status_code=409, detail=f"KPI 编码 {data['code']} 已存在")

    # 阈值/日期/活动要按「合并后」的值校验，否则局部更新会绕过规则
    direction = data.get("direction", obj.direction)
    red = data.get("red_threshold", obj.red_threshold)
    yellow = data.get("yellow_threshold", obj.yellow_threshold)
    green = data.get("green_threshold", obj.green_threshold)
    process_id = data["process_id"] if "process_id" in data else obj.process_id
    activity_id = data["activity_id"] if "activity_id" in data else obj.activity_id
    name = data.get("name", obj.name)
    formula = data.get("formula", obj.formula)
    valid_from = data["valid_from"] if "valid_from" in data else obj.valid_from
    valid_to = data["valid_to"] if "valid_to" in data else obj.valid_to
    try:
        kpi_service.validate_thresholds(direction, red, yellow, green)
        kpi_service.validate_dates(valid_from, valid_to)
        kpi_service.validate_activity(db, process_id, activity_id)
        kpi_service.ensure_formula_consistency(
            db,
            name=name,
            process_id=process_id,
            formula=formula,
            exclude_id=obj.id,
        )
    except kpi_service.KpiDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    apply_owner_update(db, data, obj.owner)
    fields = sorted(data)
    for field, value in data.items():
        setattr(obj, field, value)
    # 定义版本只在口径字段变更时递增；追加数据点走 /records，不影响版本
    obj.version = (obj.version or 1) + 1
    audit_service.record(
        db,
        user,
        "UPDATE",
        "kpi",
        obj.id,
        f"更新 KPI 定义卡 {obj.code} 到 v{obj.version}（{', '.join(fields)}）",
    )
    db.commit()
    db.refresh(obj)
    return _to_kpi_out(obj)


@router.get(
    "/improvement-candidates",
    response_model=List[ImprovementCandidateOut],
    summary="红/黄 KPI 改善候选（自动排除已有进行中项目）",
)
def improvement_candidates(db: DbSession, user: CurrentUser):
    return improvement_service.candidates(db)


@router.post(
    "/kpis/{kpi_id}/improvement-draft",
    response_model=ProjectDraftOut,
    status_code=status.HTTP_201_CREATED,
    summary="把红/黄 KPI 转成改善项目草稿",
)
def create_improvement_draft(kpi_id: int, db: DbSession, user: ManagerUser):
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise HTTPException(status_code=404, detail="KPI 不存在")
    try:
        project = improvement_service.draft_from_kpi(db, kpi, user)
    except improvement_service.ImprovementError as exc:
        code = 409 if "已有进行中" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "project",
        project.id,
        f"从 KPI {kpi.code} 生成改善项目 {project.code}",
    )
    db.commit()
    db.refresh(project)
    return ProjectDraftOut(
        id=project.id,
        code=project.code,
        name=project.name,
        process_id=project.process_id,
        source_kpi_id=project.source_kpi_id,
        status=project.status,
        status_label=improvement_service.PROJECT_STATUS_LABELS.get(project.status, project.status),
    )


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
    existed = db.scalar(
        select(KpiRecord.id).where(
            KpiRecord.kpi_id == kpi_id,
            KpiRecord.period == payload.period,
            (
                KpiRecord.project_id.is_(None)
                if payload.project_id is None
                else KpiRecord.project_id == payload.project_id
            ),
            or_(KpiRecord.note.is_(None), KpiRecord.note != kpi_service.EXECUTION_NOTE),
        )
    )
    obj = kpi_service.save_record(
        db,
        kpi,
        period=payload.period,
        value=payload.value,
        project_id=payload.project_id,
        note=payload.note,
    )
    audit_service.record(
        db,
        user,
        "UPDATE" if existed is not None else "CREATE",
        "kpi_record",
        obj.id,
        (
            f"{kpi.code} {payload.period} 数据点改为 {payload.value}"
            if existed is not None
            else f"{kpi.code} 新增 {payload.period} 数据点 {payload.value}"
        ),
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
    data = as_columns(payload.model_dump())
    data["owner_user_id"], data["owner"] = resolve_owner(
        db, data.get("owner_user_id"), data.get("owner")
    )
    # 流程 Owner 登记异常时挂在自己名下，与项目的归属规则保持一致
    if user.role == Role.OWNER.value:
        data["owner_user_id"] = user.id
        data["owner"] = user.display_name
    obj = ExceptionEvent(code=f"{prefix}{seq + 1:03d}", **data)
    db.add(obj)
    db.flush()
    if obj.owner_user_id is not None and obj.owner_user_id != user.id:
        notification_service.notify(
            db,
            obj.owner_user_id,
            "EXCEPTION_ASSIGNED",
            f"你被指派处理异常：{obj.title}",
            f"{obj.code} · 严重度 {obj.severity}",
            link="monitor",
            entity_type="exception",
            entity_id=obj.id,
        )
    integration_service.enqueue(db, "exception.created", _exception_event(obj))
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


@router.post(
    "/exceptions/{exception_id}/improvement-draft",
    response_model=ProjectDraftOut,
    status_code=status.HTTP_201_CREATED,
    summary="把未闭环异常转成改善项目草稿",
)
def create_exception_improvement_draft(exception_id: int, db: DbSession, user: WriteUser):
    obj = db.get(ExceptionEvent, exception_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="异常事件不存在")
    ensure_can_edit_owned(user, obj.owner_user_id, obj.owner)
    try:
        project = improvement_service.draft_from_exception(db, obj, user)
    except improvement_service.ImprovementError as exc:
        code = 409 if "已有进行中" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "project",
        project.id,
        f"从异常 {obj.code} 生成改善项目 {project.code}",
    )
    db.commit()
    db.refresh(project)
    return ProjectDraftOut(
        id=project.id,
        code=project.code,
        name=project.name,
        process_id=project.process_id,
        source_kpi_id=project.source_kpi_id,
        status=project.status,
        status_label=improvement_service.PROJECT_STATUS_LABELS.get(project.status, project.status),
    )


@router.patch(
    "/exceptions/{exception_id}", response_model=ExceptionOut, summary="处理 / 关闭异常事件"
)
def update_exception(exception_id: int, payload: ExceptionUpdate, db: DbSession, user: WriteUser):
    obj = db.get(ExceptionEvent, exception_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="异常事件不存在")
    ensure_can_edit_owned(user, obj.owner_user_id, obj.owner)
    previous_status = obj.status
    previous_owner_id = obj.owner_user_id

    data = as_columns(payload.model_dump(exclude_unset=True))
    if user.role == Role.OWNER.value:
        # 责任人不由 OWNER 自己变更
        data.pop("owner", None)
        data.pop("owner_user_id", None)
    else:
        apply_owner_update(db, data, obj.owner)
    for field, value in data.items():
        setattr(obj, field, value)
    if (
        obj.owner_user_id is not None
        and obj.owner_user_id != previous_owner_id
        and obj.owner_user_id != user.id
    ):
        notification_service.notify(
            db,
            obj.owner_user_id,
            "EXCEPTION_ASSIGNED",
            f"异常改派给你：{obj.title}",
            f"{obj.code} · 严重度 {obj.severity}",
            link="monitor",
            entity_type="exception",
            entity_id=obj.id,
        )

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
    integration_service.enqueue(db, "exception.updated", _exception_event(obj))
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
    ensure_can_edit_owned(user, obj.owner_user_id, obj.owner)
    audit_service.record(
        db, user, "DELETE", "exception", obj.id, f"删除异常 {obj.code} {obj.title}"
    )
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=1)
