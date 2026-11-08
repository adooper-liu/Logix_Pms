"""CSV 事件日志导入：解析、活动映射、实测指标与 LOGGED 证据。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget
from app.models.log_import import (
    LogComparisonReceipt,
    ProcessLogEvent,
    ProcessLogImport,
)
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.log_import import (
    ComparisonClaimReadinessOut,
    ComparisonReceiptOptionOut,
    LogActivityLabelOut,
    LogComparisonMetricOut,
    LogComparisonOut,
    LogComparisonReceiptIn,
    LogComparisonReceiptOut,
    LogComparisonWriteBackIn,
    LogComparisonWriteBackOption,
    LogComparisonWriteBackOptionsOut,
    LogComparisonWriteBackOut,
    LogImportOut,
)
from app.services import asset_graph as asset_service
from app.services import audit
from app.services import kpi as kpi_service

MAX_ROWS = 50000
MAX_BYTES = 20 * 1024 * 1024
MIN_COMPARISON_CASES = 5

_COLUMN_ALIASES = {
    "case_id": {"case_id", "caseid", "case", "工单号", "单据号", "实例", "案例"},
    "activity": {"activity", "活动", "步骤", "环节", "任务"},
    "timestamp": {"timestamp", "time", "occurred_at", "时间", "发生时间", "完成时间"},
    "resource": {"resource", "资源", "处理人", "人员", "角色"},
}
_REQUIRED = {"case_id", "activity", "timestamp"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_dt(value: str, row_no: int) -> datetime:
    text = (value or "").strip()
    if not text:
        raise HTTPException(400, f"第 {row_no} 行缺少时间。")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, f"第 {row_no} 行时间无法解析：{text}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_csv(data: bytes) -> Tuple[List[dict], datetime, datetime]:
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "CSV 文件超过 20MB 限制。")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV 需为 UTF-8 编码。") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV 没有表头。")
    header_map: Dict[str, str] = {}
    for original in reader.fieldnames:
        key = (original or "").strip().lower()
        for canonical, aliases in _COLUMN_ALIASES.items():
            if key in aliases:
                header_map[canonical] = original
                break
    missing = _REQUIRED - set(header_map)
    if missing:
        names = "、".join(sorted(missing))
        raise HTTPException(400, f"CSV 缺少必需列：{names}。")
    case_col = header_map["case_id"]
    activity_col = header_map["activity"]
    time_col = header_map["timestamp"]
    resource_col = header_map.get("resource")

    rows: List[dict] = []
    errors: List[str] = []
    for row_no, raw in enumerate(reader, start=2):
        case_id = (raw.get(case_col) or "").strip()
        activity = (raw.get(activity_col) or "").strip()
        if not case_id or not activity:
            errors.append(f"第 {row_no} 行缺少 case_id 或 activity")
            continue
        try:
            occurred_at = _parse_dt(raw.get(time_col) or "", row_no)
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue
        rows.append(
            {
                "case_id": case_id[:64],
                "activity_label": activity[:200],
                "occurred_at": occurred_at,
                "resource": ((raw.get(resource_col) or "").strip()[:64] or None)
                if resource_col
                else None,
            }
        )
        if len(rows) > MAX_ROWS:
            raise HTTPException(400, f"事件行数超过 {MAX_ROWS} 条限制。")
        if len(errors) >= 3:
            break
    if errors:
        raise HTTPException(400, "；".join(errors[:3]))
    if not rows:
        raise HTTPException(400, "CSV 没有有效事件行。")
    window_start = min(row["occurred_at"] for row in rows)
    window_end = max(row["occurred_at"] for row in rows)
    return rows, window_start, window_end


def _require_import(db: Session, process: ProcessArch, import_id: int) -> ProcessLogImport:
    row = db.get(ProcessLogImport, import_id)
    if row is None or row.process_id != process.id:
        raise HTTPException(404, "日志导入不存在。")
    return row


def _require_activity(db: Session, process: ProcessArch, activity_id: int) -> ProcessArch:
    activity = db.get(ProcessArch, activity_id)
    if activity is None or activity.level != 4 or activity.parent_id != process.id:
        raise HTTPException(400, "活动必须是该流程下的 L4 活动。")
    return activity


def _labels(
    db: Session, process: ProcessArch, import_row: ProcessLogImport
) -> List[LogActivityLabelOut]:
    rows = db.execute(
        select(ProcessLogEvent.activity_label, func.count(ProcessLogEvent.id))
        .where(ProcessLogEvent.import_id == import_row.id)
        .group_by(ProcessLogEvent.activity_label)
        .order_by(func.count(ProcessLogEvent.id).desc(), ProcessLogEvent.activity_label)
    ).all()
    mapping = import_row.mapping or {}
    activities = list(
        db.scalars(
            select(ProcessArch).where(
                ProcessArch.parent_id == process.id,
                ProcessArch.level == 4,
            )
        ).all()
    )
    by_id = {row.id: row for row in activities}
    by_name = {row.name.strip().lower(): row for row in activities}
    by_code = {row.code.strip().lower(): row for row in activities}
    history_rows = db.scalars(
        select(ProcessLogImport)
        .where(
            ProcessLogImport.process_id == process.id,
            ProcessLogImport.id != import_row.id,
            ProcessLogImport.status.in_(["MAPPED", "COMMITTED"]),
        )
        .order_by(ProcessLogImport.id.desc())
    ).all()
    history: Dict[str, int] = {}
    for row in history_rows:
        for label, activity_id in (row.mapping or {}).items():
            if activity_id and label not in history:
                history[label] = int(activity_id)

    result: List[LogActivityLabelOut] = []
    for label, count in rows:
        mapped_id = mapping.get(label)
        activity = by_id.get(int(mapped_id)) if mapped_id else None
        suggested = None
        reason = None
        if activity is None:
            exact = by_name.get(label.strip().lower()) or by_code.get(label.strip().lower())
            if exact is not None:
                suggested = exact
                reason = "名称/编码匹配"
            elif history.get(label) in by_id:
                suggested = by_id[history[label]]
                reason = "历史映射"
        result.append(
            LogActivityLabelOut(
                label=label,
                count=count,
                mapped_activity_id=activity.id if activity else None,
                mapped_activity_code=activity.code if activity else None,
                mapped_activity_name=activity.name if activity else None,
                suggested_activity_id=suggested.id if suggested else None,
                suggested_activity_code=suggested.code if suggested else None,
                suggested_activity_name=suggested.name if suggested else None,
                suggestion_reason=reason,
            )
        )
    return result


def _out(db: Session, process: ProcessArch, import_row: ProcessLogImport) -> LogImportOut:
    return LogImportOut(
        id=import_row.id,
        process_id=import_row.process_id,
        file_name=import_row.file_name,
        status=import_row.status,
        row_count=import_row.row_count,
        case_count=import_row.case_count,
        window_start=import_row.window_start,
        window_end=import_row.window_end,
        labels=_labels(db, process, import_row),
        metrics=import_row.metrics or {},
        claim_id=import_row.claim_id,
        created_at=import_row.created_at,
        committed_at=import_row.committed_at,
    )


def list_imports(db: Session, process: ProcessArch) -> List[LogImportOut]:
    rows = db.scalars(
        select(ProcessLogImport)
        .where(ProcessLogImport.process_id == process.id)
        .order_by(ProcessLogImport.id.desc())
    ).all()
    return [_out(db, process, row) for row in rows]


def get_import(db: Session, process: ProcessArch, import_id: int) -> LogImportOut:
    return _out(db, process, _require_import(db, process, import_id))


def create_import(
    db: Session, process: ProcessArch, user: User, file_name: str, data: bytes
) -> LogImportOut:
    rows, window_start, window_end = _parse_csv(data)
    version = asset_service.published_model(db, process)
    import_row = ProcessLogImport(
        process_id=process.id,
        model_version_id=version.id if version else None,
        file_name=(file_name or "events.csv")[:255],
        checksum=_sha256(data),
        row_count=len(rows),
        case_count=len({row["case_id"] for row in rows}),
        window_start=window_start,
        window_end=window_end,
        status="DRAFT",
        mapping={},
        created_by_id=user.id,
        created_by_name=user.display_name,
    )
    db.add(import_row)
    db.flush()
    for row in rows:
        db.add(ProcessLogEvent(import_id=import_row.id, **row))
    db.flush()
    audit.record(
        db,
        user,
        "CREATE",
        "process_log_import",
        import_row.id,
        f"{import_row.file_name}：{len(rows)} 事件 / {import_row.case_count} 单",
    )
    db.commit()
    db.refresh(import_row)
    return _out(db, process, import_row)


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0, "median": 0, "p90": 0, "min": 0, "max": 0}
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))
    return {
        "mean": round(statistics.mean(ordered), 2),
        "median": round(statistics.median(ordered), 2),
        "p90": round(ordered[index], 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
    }


def _compute_metrics(db: Session, import_row: ProcessLogImport) -> Dict[str, Any]:
    events = db.scalars(
        select(ProcessLogEvent)
        .where(ProcessLogEvent.import_id == import_row.id)
        .order_by(ProcessLogEvent.case_id, ProcessLogEvent.occurred_at, ProcessLogEvent.id)
    ).all()
    cases: Dict[str, List[ProcessLogEvent]] = {}
    for event in events:
        cases.setdefault(event.case_id, []).append(event)
    lead_times: List[float] = []
    variants: Dict[str, int] = {}
    activity_counts: Dict[str, int] = {}
    mapped_events = 0
    for _case_id, case_events in cases.items():
        if len(case_events) >= 2:
            lead_times.append(
                (case_events[-1].occurred_at - case_events[0].occurred_at).total_seconds() / 60
            )
        sequence = []
        for event in case_events:
            activity = (
                db.get(ProcessArch, event.mapped_activity_id) if event.mapped_activity_id else None
            )
            key = activity.code if activity else event.activity_label
            sequence.append(key)
            activity_counts[key] = activity_counts.get(key, 0) + 1
            if event.mapped_activity_id:
                mapped_events += 1
        variants[" → ".join(sequence)] = variants.get(" → ".join(sequence), 0) + 1
    top_variants = [
        {"sequence": sequence, "cases": count}
        for sequence, count in sorted(variants.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    return {
        "case_count": len(cases),
        "event_count": len(events),
        "mapped_events": mapped_events,
        "unmapped_events": len(events) - mapped_events,
        "mapping_coverage": round(mapped_events / len(events), 4) if events else 0,
        "lead_time_minutes": _stats(lead_times),
        "activity_counts": activity_counts,
        "variants": top_variants,
        "window_start": import_row.window_start.isoformat() if import_row.window_start else None,
        "window_end": import_row.window_end.isoformat() if import_row.window_end else None,
    }


def map_import(
    db: Session, process: ProcessArch, import_id: int, mapping: Dict[str, Optional[int]], user: User
) -> LogImportOut:
    import_row = _require_import(db, process, import_id)
    if import_row.status == "COMMITTED":
        raise HTTPException(400, "已提交的日志不能再改映射。")
    labels = set(
        db.scalars(
            select(ProcessLogEvent.activity_label).where(ProcessLogEvent.import_id == import_row.id)
        ).all()
    )
    unknown = set(mapping) - labels
    if unknown:
        raise HTTPException(400, f"未知活动标签：{'、'.join(sorted(unknown))}")
    db.execute(
        update(ProcessLogEvent)
        .where(ProcessLogEvent.import_id == import_row.id)
        .values(mapped_activity_id=None)
    )
    for label, activity_id in mapping.items():
        if activity_id is not None:
            _require_activity(db, process, activity_id)
        db.execute(
            update(ProcessLogEvent)
            .where(
                ProcessLogEvent.import_id == import_row.id,
                ProcessLogEvent.activity_label == label,
            )
            .values(mapped_activity_id=activity_id)
        )
    import_row.mapping = mapping
    import_row.status = "MAPPED"
    import_row.metrics = _compute_metrics(db, import_row)
    audit.record(
        db,
        user,
        "UPDATE",
        "process_log_import",
        import_row.id,
        f"活动映射 {len(mapping)} 项",
    )
    db.commit()
    db.refresh(import_row)
    return _out(db, process, import_row)


def commit_import(db: Session, process: ProcessArch, import_id: int, user: User) -> LogImportOut:
    import_row = _require_import(db, process, import_id)
    if import_row.status == "COMMITTED":
        return _out(db, process, import_row)
    if import_row.status != "MAPPED" or not import_row.metrics:
        raise HTTPException(400, "请先完成活动映射并计算指标。")
    metrics = import_row.metrics or {}
    if not metrics.get("mapped_events"):
        raise HTTPException(400, "没有任何事件映射到 L4 活动，不能提交为实测证据。")
    result_hash = hashlib.sha256(
        json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    stats = metrics.get("lead_time_minutes") or {}
    claim = EvidenceClaim(
        process_id=process.id,
        claim=(
            f"日志实测 · {import_row.file_name} · {metrics.get('case_count', 0)} 单"
            f" · 平均周期 {stats.get('mean', 0):.0f} 分钟"
        ),
        claim_type="TIME",
        source_type="LOG_IMPORT",
        source_id=import_row.id,
        source_version=import_row.checksum,
        source_hash=result_hash,
        method="LOGGED",
        samples=metrics.get("case_count", 0),
        window_start=import_row.window_start,
        window_end=import_row.window_end,
        coverage=metrics.get("mapping_coverage"),
        quality={
            "source": "CSV_LOG",
            "unmapped_events": metrics.get("unmapped_events", 0),
        },
        status="OPEN",
        query_ref={
            "import_id": import_row.id,
            "file_name": import_row.file_name,
            "mapping": import_row.mapping,
        },
        result_hash=result_hash,
        created_by_id=user.id,
        created_by_name=user.display_name,
    )
    db.add(claim)
    db.flush()
    db.add(
        EvidenceClaimTarget(
            claim_id=claim.id,
            target_type="PROCESS",
            target_id=process.id,
            model_version_id=import_row.model_version_id,
            field="lead_time",
            condition="ALL",
        )
    )
    import_row.status = "COMMITTED"
    import_row.claim_id = claim.id
    import_row.committed_at = utcnow()
    audit.record(
        db,
        user,
        "CREATE",
        "evidence_claim",
        claim.id,
        f"日志实测证据：{import_row.file_name}",
    )
    db.commit()
    db.refresh(import_row)
    return _out(db, process, import_row)


def _metric(before, after) -> LogComparisonMetricOut:
    b = float(before) if before is not None else None
    a = float(after) if after is not None else None
    delta = round(a - b, 2) if a is not None and b is not None else None
    pct = round((a - b) / b, 4) if delta is not None and b not in (None, 0) else None
    return LogComparisonMetricOut(before=b, after=a, delta=delta, delta_pct=pct)


def compare(db: Session, process: ProcessArch, before_id: int, after_id: int) -> LogComparisonOut:
    if before_id == after_id:
        raise HTTPException(400, "请选择两次不同的日志导入。")
    before = _require_import(db, process, before_id)
    after = _require_import(db, process, after_id)
    reasons: List[str] = []
    warnings: List[str] = []
    if before.status != "COMMITTED" or after.status != "COMMITTED":
        reasons.append("两次导入都需先提交为实测证据")
    if (before.mapping or {}) != (after.mapping or {}):
        reasons.append("两次导入的活动映射不同")
    if (
        before.model_version_id
        and after.model_version_id
        and before.model_version_id != after.model_version_id
    ):
        reasons.append("两次导入绑定的模型版本不同")

    before_metrics = before.metrics or {}
    after_metrics = after.metrics or {}
    if not before_metrics or not after_metrics:
        reasons.append("至少一次导入还没有计算指标")
    before_lead = before_metrics.get("lead_time_minutes") or {}
    after_lead = after_metrics.get("lead_time_minutes") or {}
    metrics = {
        "mean_lead_minutes": _metric(before_lead.get("mean"), after_lead.get("mean")),
        "median_lead_minutes": _metric(before_lead.get("median"), after_lead.get("median")),
        "p90_lead_minutes": _metric(before_lead.get("p90"), after_lead.get("p90")),
        "case_count": _metric(before_metrics.get("case_count"), after_metrics.get("case_count")),
        "event_count": _metric(before_metrics.get("event_count"), after_metrics.get("event_count")),
        "mapping_coverage": _metric(
            before_metrics.get("mapping_coverage"),
            after_metrics.get("mapping_coverage"),
        ),
    }
    case_counts = [
        value
        for value in (
            before_metrics.get("case_count"),
            after_metrics.get("case_count"),
        )
        if value is not None
    ]
    if case_counts and min(case_counts) < 5:
        warnings.append("样本量小于 5，只看方向，不支持达标结论")
    coverages = [
        value
        for value in (
            before_metrics.get("mapping_coverage"),
            after_metrics.get("mapping_coverage"),
        )
        if value is not None
    ]
    if coverages and min(coverages) < 0.9:
        warnings.append("至少一次映射覆盖不足 90%，对照可能偏差")
    if before.window_end and after.window_start and after.window_start < before.window_end:
        warnings.append("两次数据窗口重叠，前后对照可能混入同期样本")

    comparable = not reasons
    mean = metrics["mean_lead_minutes"]
    if mean.delta_pct is None:
        direction = "无法计算平均周期变化"
    elif mean.delta_pct < 0:
        direction = f"平均周期下降 {abs(mean.delta_pct):.1%}"
    elif mean.delta_pct > 0:
        direction = f"平均周期上升 {mean.delta_pct:.1%}"
    else:
        direction = "平均周期基本不变"
    if not comparable:
        conclusion = "不可比：" + "；".join(reasons)
    elif warnings:
        conclusion = (
            f"可比较；{direction}；但{'；'.join(warnings)}。这是描述性对照，不代表改善达标。"
        )
    else:
        conclusion = f"可比较；{direction}。这是描述性对照，不代表统计显著或改善达标。"
    return LogComparisonOut(
        process_id=process.id,
        before=_out(db, process, before),
        after=_out(db, process, after),
        comparable=comparable,
        reasons=reasons,
        warnings=warnings,
        metrics=metrics,
        variants={
            "before": before_metrics.get("variants", []),
            "after": after_metrics.get("variants", []),
        },
        conclusion=conclusion,
    )


def _sample_ok(comparison: LogComparisonOut) -> bool:
    case_counts = [
        value
        for value in (
            comparison.metrics["case_count"].before,
            comparison.metrics["case_count"].after,
        )
        if value is not None
    ]
    return bool(case_counts) and min(case_counts) >= MIN_COMPARISON_CASES


def _receipt_out(row: LogComparisonReceipt) -> LogComparisonReceiptOut:
    return LogComparisonReceiptOut(
        id=row.id,
        process_id=row.process_id,
        before_import_id=row.before_import_id,
        after_import_id=row.after_import_id,
        decision=row.decision,
        rationale=row.rationale,
        comparable=row.comparable,
        sample_ok=row.sample_ok,
        claim_allowed=row.claim_allowed,
        metrics=row.metrics or {},
        conclusion=row.conclusion,
        accepted_by_name=row.accepted_by_name,
        accepted_at=row.accepted_at,
        created_at=row.created_at,
    )


def create_receipt(
    db: Session,
    process: ProcessArch,
    user: User,
    payload: LogComparisonReceiptIn,
) -> LogComparisonReceiptOut:
    comparison = compare(db, process, payload.before_id, payload.after_id)
    if payload.decision == "ACCEPT" and not comparison.comparable:
        raise HTTPException(400, "不可比的对照不能接收。")
    rationale = payload.rationale.strip()
    if not rationale:
        raise HTTPException(400, "请填写接收/退回依据。")
    sample_ok = _sample_ok(comparison)
    claim_allowed = payload.decision == "ACCEPT" and comparison.comparable and sample_ok
    row = LogComparisonReceipt(
        process_id=process.id,
        before_import_id=payload.before_id,
        after_import_id=payload.after_id,
        decision=payload.decision,
        rationale=rationale,
        comparable=comparison.comparable,
        sample_ok=sample_ok,
        claim_allowed=claim_allowed,
        metrics={
            "metrics": {key: value.model_dump() for key, value in comparison.metrics.items()},
            "variants": comparison.variants,
            "warnings": comparison.warnings,
        },
        conclusion=comparison.conclusion,
        accepted_by_id=user.id,
        accepted_by_name=user.display_name,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        user,
        "CREATE",
        "log_comparison_receipt",
        row.id,
        f"{payload.decision}：{comparison.conclusion[:160]}",
    )
    db.commit()
    db.refresh(row)
    return _receipt_out(row)


def list_receipts(
    db: Session, process: ProcessArch, before_id: int, after_id: int
) -> List[LogComparisonReceiptOut]:
    _require_import(db, process, before_id)
    _require_import(db, process, after_id)
    rows = db.scalars(
        select(LogComparisonReceipt)
        .where(
            LogComparisonReceipt.process_id == process.id,
            LogComparisonReceipt.before_import_id == before_id,
            LogComparisonReceipt.after_import_id == after_id,
        )
        .order_by(LogComparisonReceipt.id.desc())
    ).all()
    return [_receipt_out(row) for row in rows]


def _readiness(
    comparison: LogComparisonOut,
    receipts: List[LogComparisonReceiptOut],
) -> ComparisonClaimReadinessOut:
    latest = receipts[0] if receipts else None
    reasons: List[str] = []
    if not comparison.comparable:
        reasons.extend(comparison.reasons)
    if not _sample_ok(comparison):
        reasons.append(f"前后样本量不足 {MIN_COMPARISON_CASES} 单")
    if latest is None:
        reasons.append("尚未接收对照结论")
    elif latest.decision != "ACCEPT":
        reasons.append("对照结论未被接收")
    return ComparisonClaimReadinessOut(
        process_id=comparison.process_id,
        before_import_id=comparison.before.id,
        after_import_id=comparison.after.id,
        claim_allowed=not reasons,
        reasons=reasons,
        latest_receipt=latest,
    )


def claim_readiness(
    db: Session, process: ProcessArch, before_id: int, after_id: int
) -> ComparisonClaimReadinessOut:
    return _readiness(
        compare(db, process, before_id, after_id), list_receipts(db, process, before_id, after_id)
    )


def _duration_kpis(db: Session, process: ProcessArch) -> List[KpiDefinition]:
    rows = db.scalars(
        select(KpiDefinition)
        .where(
            KpiDefinition.process_id == process.id,
            KpiDefinition.is_active.is_(True),
            KpiDefinition.activity_id.is_(None),
            KpiDefinition.frequency == "MONTHLY",
        )
        .order_by(KpiDefinition.code)
    ).all()
    return [row for row in rows if kpi_service.minutes_to_unit(1.0, row.unit) is not None]


def write_back_options(
    db: Session, process: ProcessArch, before_id: int, after_id: int
) -> LogComparisonWriteBackOptionsOut:
    comparison = compare(db, process, before_id, after_id)
    readiness = _readiness(comparison, list_receipts(db, process, before_id, after_id))
    after = _require_import(db, process, after_id)
    mean = comparison.metrics["mean_lead_minutes"].after
    period = after.window_end.date().replace(day=1) if after.window_end else None
    kpis: List[LogComparisonWriteBackOption] = []
    if mean is not None and period is not None:
        for kpi in _duration_kpis(db, process):
            observed = kpi_service.minutes_to_unit(mean, kpi.unit)
            if observed is None:
                continue
            kpis.append(
                LogComparisonWriteBackOption(
                    kpi_id=kpi.id,
                    code=kpi.code,
                    name=kpi.name,
                    unit=kpi.unit,
                    direction=kpi.direction,
                    baseline_value=kpi.baseline_value,
                    target_value=kpi.target_value,
                    observed_value=observed,
                    observed_period=period,
                )
            )
    return LogComparisonWriteBackOptionsOut(
        process_id=process.id,
        before_import_id=before_id,
        after_import_id=after_id,
        claim_allowed=readiness.claim_allowed,
        reasons=readiness.reasons,
        latest_receipt_id=readiness.latest_receipt.id if readiness.latest_receipt else None,
        kpis=kpis,
        note=(
            "只写回月频、流程级、时长单位的 KPI；基线取改善后平均周期，"
            "目标值必须由人明确填写，不能由实测值自动顶替。"
        ),
    )


def claimable_receipts(db: Session, process: ProcessArch) -> List[ComparisonReceiptOptionOut]:
    """每个对照对只取最新一条结论；只返回当前仍满足改善宣称门禁的接收记录。"""
    rows = db.scalars(
        select(LogComparisonReceipt)
        .where(LogComparisonReceipt.process_id == process.id)
        .order_by(LogComparisonReceipt.id.desc())
    ).all()
    seen = set()
    result: List[ComparisonReceiptOptionOut] = []
    for row in rows:
        pair = (row.before_import_id, row.after_import_id)
        if pair in seen:
            continue
        seen.add(pair)
        if row.decision != "ACCEPT":
            continue
        try:
            comparison = compare(db, process, row.before_import_id, row.after_import_id)
            readiness = _readiness(
                comparison, list_receipts(db, process, row.before_import_id, row.after_import_id)
            )
        except HTTPException:
            continue
        if (
            not readiness.claim_allowed
            or readiness.latest_receipt is None
            or readiness.latest_receipt.id != row.id
        ):
            continue
        mean = comparison.metrics["mean_lead_minutes"]
        cases = comparison.metrics["case_count"]
        result.append(
            ComparisonReceiptOptionOut(
                receipt_id=row.id,
                before_import_id=row.before_import_id,
                after_import_id=row.after_import_id,
                before_file_name=comparison.before.file_name,
                after_file_name=comparison.after.file_name,
                mean_before=mean.before,
                mean_after=mean.after,
                delta_pct=mean.delta_pct,
                case_count_before=int(cases.before) if cases.before is not None else None,
                case_count_after=int(cases.after) if cases.after is not None else None,
                accepted_by_name=row.accepted_by_name,
                accepted_at=row.accepted_at,
            )
        )
        if len(result) >= 50:
            break
    return result


def _records_for_period(db: Session, kpi_id: int, period) -> List[KpiRecord]:
    return list(
        db.scalars(
            select(KpiRecord).where(
                KpiRecord.kpi_id == kpi_id,
                KpiRecord.period == period,
                KpiRecord.project_id.is_(None),
            )
        ).all()
    )


def write_back(
    db: Session,
    process: ProcessArch,
    user: User,
    payload: LogComparisonWriteBackIn,
) -> LogComparisonWriteBackOut:
    comparison = compare(db, process, payload.before_id, payload.after_id)
    readiness = _readiness(
        comparison, list_receipts(db, process, payload.before_id, payload.after_id)
    )
    receipt = readiness.latest_receipt
    if not readiness.claim_allowed or receipt is None:
        raise HTTPException(
            409,
            {
                "message": "对照尚未达到可写回条件",
                "reasons": readiness.reasons,
            },
        )
    rationale = payload.rationale.strip()
    if not rationale:
        raise HTTPException(400, "请填写写回依据。")
    kpi = db.get(KpiDefinition, payload.kpi_id)
    if kpi is None or kpi.process_id != process.id or not kpi.is_active:
        raise HTTPException(400, "指标不属于本流程或已停用。")
    if kpi.activity_id is not None:
        raise HTTPException(400, "只写回流程级 KPI，活动级指标请先归并到流程口径。")
    if kpi.frequency != "MONTHLY":
        raise HTTPException(400, "只写回月频 KPI；其它频率请按月汇总后再登记。")
    mean = comparison.metrics["mean_lead_minutes"].after
    observed = kpi_service.minutes_to_unit(mean, kpi.unit) if mean is not None else None
    if observed is None:
        raise HTTPException(400, "该 KPI 的单位不是时长口径，不能写回日志周期。")
    if payload.target_value is not None and not math.isfinite(payload.target_value):
        raise HTTPException(400, "目标值必须是有限数字。")
    after = _require_import(db, process, payload.after_id)
    before = _require_import(db, process, payload.before_id)
    if after.window_end is None:
        raise HTTPException(400, "改善后导入缺少数据窗口，不能确定写回期间。")
    if after.window_start is None or (
        after.window_start.year,
        after.window_start.month,
    ) != (after.window_end.year, after.window_end.month):
        raise HTTPException(409, "改善后数据窗口跨月，不能写成单一月度数据点。")
    period = after.window_end.date().replace(day=1)

    records = _records_for_period(db, kpi.id, period)
    if any((row.provenance or {}).get("source_kind") != "LOG_COMPARISON" for row in records):
        raise HTTPException(409, "该期间已有正式数据点，不能覆盖。")
    existing = next(
        (row for row in records if (row.provenance or {}).get("source_kind") == "LOG_COMPARISON"),
        None,
    )

    version_before = kpi.version or 1
    baseline_before = kpi.baseline_value
    target_before = kpi.target_value
    changed = False
    if payload.update_baseline and baseline_before != observed:
        kpi.baseline_value = observed
        changed = True
    if payload.target_value is not None and target_before != payload.target_value:
        kpi.target_value = payload.target_value
        changed = True
    if changed:
        kpi.version = version_before + 1

    provenance = {
        "source_kind": "LOG_COMPARISON",
        "quality": "VALID",
        "measurement_hash": kpi_service.measurement_hash(kpi),
        "evidence": rationale,
        "comparison_receipt_id": receipt.id,
        "before_import_id": before.id,
        "after_import_id": after.id,
        "before_claim_id": before.claim_id,
        "after_claim_id": after.claim_id,
        "before_case_count": (before.metrics or {}).get("case_count"),
        "after_case_count": (after.metrics or {}).get("case_count"),
        "mapping_coverage": (after.metrics or {}).get("mapping_coverage"),
        "window_start": after.window_start.isoformat() if after.window_start else None,
        "window_end": after.window_end.isoformat(),
        "model_version_id": after.model_version_id,
        "compared_metric": "mean_lead_minutes",
        "metrics": {key: value.model_dump() for key, value in comparison.metrics.items()},
        "warnings": comparison.warnings,
        "conclusion": comparison.conclusion,
        "kpi_version_before": version_before,
        "kpi_version_after": kpi.version,
    }

    repeated = (
        existing is not None
        and not changed
        and existing.value == observed
        and (existing.provenance or {}).get("comparison_receipt_id") == receipt.id
    )
    if repeated:
        record = existing
    else:
        record = kpi_service.save_record(
            db,
            kpi,
            period=period,
            value=observed,
            project_id=None,
            note=f"日志对照 #{receipt.id}",
            provenance=provenance,
        )
        audit.record(
            db,
            user,
            "UPDATE",
            "kpi",
            kpi.id,
            json.dumps(
                {
                    "message": f"日志对照写回 KPI {kpi.code} v{kpi.version}",
                    "baseline_before": baseline_before,
                    "baseline_after": kpi.baseline_value,
                    "target_before": target_before,
                    "target_after": kpi.target_value,
                    "receipt_id": receipt.id,
                    "period": period.isoformat(),
                    "value": observed,
                    "rationale": rationale,
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        db.commit()
        db.refresh(kpi)
        db.refresh(record)

    return LogComparisonWriteBackOut(
        process_id=process.id,
        before_import_id=payload.before_id,
        after_import_id=payload.after_id,
        receipt_id=receipt.id,
        kpi_id=kpi.id,
        kpi_code=kpi.code,
        kpi_unit=kpi.unit,
        kpi_version_before=version_before,
        kpi_version_after=kpi.version or version_before,
        baseline_before=baseline_before,
        baseline_after=kpi.baseline_value,
        target_before=target_before,
        target_after=kpi.target_value,
        record_id=record.id,
        record_period=record.period,
        record_value=record.value,
        record_revision=record.revision,
        claim_allowed=True,
        sample_ok=receipt.sample_ok,
    )
