"""薄轮次的同流程原引用、冻结快照和可重试追加。"""

import hashlib
import json
import math
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select, update

from app.api.deps import ensure_can_edit_owned
from app.core.timeutil import utcnow
from app.models.improvement_round import ProcessImprovementRound as Round
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.project import Project
from app.models.user import User
from app.schemas.improvement_round import MetricInput, RoundOut, SampleInput, Window
from app.services import audit, idempotency, org_access

CONCLUSIONS = {
    "DATA_READY": "资料就绪",
    "GO_LIVE_READY": "上线就绪",
    "RUN_EFFECTIVE": "运行有效",
    "IMPROVEMENT_MET": "改善达标",
}
KPI_FIELDS = (
    "code",
    "name",
    "version",
    "formula",
    "numerator",
    "denominator",
    "unit",
    "granularity",
    "frequency",
    "source_system",
    "data_flow_id",
    "inbound_webhook_id",
    "quality_rule",
    "process_id",
    "activity_id",
    "measurement",
    "direction",
    "target_value",
    "red_threshold",
    "yellow_threshold",
    "green_threshold",
)


def digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False).encode()
    ).hexdigest()


def process(db, pid, user, write=False):
    row = db.get(ProcessArch, pid)
    if row is None:
        raise HTTPException(404, "流程不存在")
    if row.level < 3 or (row.is_draft and write):
        raise HTTPException(400, "轮次只能属于已纳入目录的L3/L4流程")
    if write:
        ensure_can_edit_owned(user, row.owner_user_id, row.owner)
    return row


def require(db, user, pid, rid, write=False):
    process(db, pid, user, write)
    row = db.get(Round, rid)
    if row is None or row.process_id != pid:
        raise HTTPException(404, "本流程轮次不存在")
    if row.project_id:
        project = db.get(Project, row.project_id)
        if project is None:
            raise HTTPException(404, "轮次项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
    for sample in (row.baseline_samples or []) + (row.after_samples or []):
        if sample.get("project_id"):
            project = db.get(Project, sample["project_id"])
            if project:
                org_access.ensure_visible(db, user, project.org_unit_id)
    return row


def model(db, pid, ident, published=False):
    row = db.get(ProcessModelVersion, ident) if ident else None
    if row is None or row.process_id != pid:
        raise HTTPException(400, "请选择本流程原模型版本")
    if published:
        if row.published_at is None or row.status not in ("PUBLISHED", "SUPERSEDED"):
            raise HTTPException(400, "所选版本没有真实发布记录")
    elif row.frozen_at is None and row.published_at is None:
        raise HTTPException(400, "原模型尚未固定")
    return row


def model_hash(row):
    return digest({"snapshot": row.snapshot, "xml": row.bpmn_xml})


def contracts(db, pid, inputs):
    if len({x.kpi_id for x in inputs}) != len(inputs):
        raise HTTPException(400, "同一指标不能重复定义口径")
    result = []
    for spec in inputs:
        kpi = db.get(KpiDefinition, spec.kpi_id)
        if kpi is None or kpi.process_id != pid or not kpi.is_active:
            raise HTTPException(400, "指标不属于本流程或已停用")
        if not (kpi.formula or (kpi.numerator and kpi.denominator)):
            raise HTTPException(400, "指标原定义缺少公式/分子分母")
        if not all(
            getattr(spec, key).strip()
            for key in ("source_semantics", "source_evidence", "calendar")
        ):
            raise HTTPException(400, "请明确来源语义、原依据和日历")
        try:
            ZoneInfo(spec.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(400, "时区无效") from exc
        item = {key: getattr(kpi, key) for key in KPI_FIELDS}
        for value in item.values():
            if isinstance(value, float) and not math.isfinite(value):
                raise HTTPException(400, "口径数值必须有限")
        item.update(spec.model_dump())
        item["contract_key"] = "kpi:" + str(kpi.id)
        item["hash"] = digest(item)
        result.append(item)
    return result


def samples(db, user, row, inputs, window, role, model_id, metric_contracts):
    ids = [x.record_id for x in inputs]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "同侧样本不得重复")
    opposite = row.baseline_samples if role == "AFTER" else []
    if set(ids) & {x["record_id"] for x in opposite}:
        raise HTTPException(400, "同一原样本不能同时作前后对照")
    by_kpi = {x["kpi_id"]: x for x in metric_contracts}
    result = []
    for spec in inputs:
        record = db.get(KpiRecord, spec.record_id)
        if record is None or record.kpi_id not in by_kpi:
            raise HTTPException(400, "样本不属于本轮指标")
        kpi = db.get(KpiDefinition, record.kpi_id)
        if kpi is None or kpi.process_id != row.process_id:
            raise HTTPException(400, "样本指标流程身份已变化")
        if record.project_id:
            project = db.get(Project, record.project_id)
            if project is None:
                raise HTTPException(404, "样本项目不存在")
            org_access.ensure_visible(db, user, project.org_unit_id)
            if row.project_id != record.project_id:
                raise HTTPException(400, "样本项目与本轮不一致")
        if not window.start <= record.period <= window.end:
            raise HTTPException(400, "样本期间超出本侧窗口")
        if not math.isfinite(record.value):
            raise HTTPException(400, "样本数值必须有限")
        contract = by_kpi[record.kpi_id]
        if role == "AFTER" and spec.contract_hash != contract["hash"]:
            raise HTTPException(400, "后侧样本口径hash不一致")
        if not spec.source_evidence.strip() or not spec.quality_note.strip():
            raise HTTPException(400, "请补原来源和质量核对说明")
        provenance = record.provenance or {}
        identity_basis = "人工核对来源声明（原KPI记录无直接模型身份）"
        if provenance.get("source_kind") == "EXECUTION_ELAPSED":
            from app.services.kpi import measurement_hash, record_quality

            if record_quality(kpi, record) != "VALID":
                raise HTTPException(400, "运行样本质量或身份未满足正式对照条件")
            if (
                provenance.get("model_version_id") != model_id
                or provenance.get("project_id") != row.project_id
            ):
                raise HTTPException(400, "运行样本模型/项目与本侧不一致")
            if role == "AFTER" and provenance.get("round_id") != row.id:
                raise HTTPException(400, "运行样本轮次与本轮不一致")
            if provenance.get("measurement_hash") != measurement_hash(kpi) or any(
                contract.get(key) != getattr(kpi, key)
                for key in (
                    "measurement",
                    "formula",
                    "unit",
                    "process_id",
                    "activity_id",
                    "frequency",
                )
            ):
                raise HTTPException(400, "运行样本与冻结测量约定不一致")
            if (
                provenance.get("window_start", "")[:10] < window.start.isoformat()
                or provenance.get("window_end", "")[:10]
                > (window.end + __import__("datetime").timedelta(days=1)).isoformat()
            ):
                raise HTTPException(400, "运行样本实际窗口超出本侧范围")
            identity_basis = "原实例固定身份与测量来源"
        result.append(
            {
                "record_id": record.id,
                "kpi_id": record.kpi_id,
                "project_id": record.project_id,
                "period": record.period.isoformat(),
                "value": record.value,
                "note": record.note,
                "role": role,
                "model_version_id": model_id,
                "contract_hash": contract["hash"],
                "source_evidence": spec.source_evidence,
                "quality_note": spec.quality_note,
                "identity_basis": identity_basis,
                "provenance": provenance,
                "record_revision": record.revision,
            }
        )
    if {x["kpi_id"] for x in result} != set(by_kpi):
        raise HTTPException(400, "每项冻结口径都需本侧原样本")
    return result


def out(row):
    from sqlalchemy.orm import object_session

    from app.services.round_outcome import projections

    db = object_session(row)
    missing = []
    if not row.baseline_confirmed_at:
        missing.append("前侧依据尚未固定")
    if not row.project_id:
        missing.append("尚未关联项目（前置诊断可无项目）")
    if not row.released_model_version_id:
        missing.append("未固定真实发布版本")
    if not row.acceptance_locked_at:
        missing.append("验收约定未锁定")
    if not row.after_samples:
        missing.append("后侧样本未固定")
    fields = {
        key: getattr(row, key)
        for key in RoundOut.model_fields
        if key not in ("verification", "missing", "basis_label")
    }
    return RoundOut(
        **fields,
        missing=missing,
        basis_label="前侧已固定" if row.baseline_confirmed_at else "前侧草稿（未确认）",
        verification=projections(db, row),
    )


def cas(db, row, expected, values):
    if row.revision != expected:
        raise HTTPException(409, "轮次已更新，请刷新后重试")
    result = db.execute(
        update(Round)
        .where(Round.id == row.id, Round.revision == expected)
        .values(**values, revision=expected + 1, updated_at=utcnow()),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise HTTPException(409, "轮次已更新，请刷新后重试")
    db.expire(row)


def create(db, user, pid, payload, supersedes=None):
    process(db, pid, user, True)
    if not payload.name.strip() or not payload.scope_note.strip():
        raise HTTPException(400, "请写明轮次名称和业务范围")
    version = (
        model(db, pid, payload.asis_model_version_id) if payload.asis_model_version_id else None
    )
    metric = contracts(db, pid, payload.metrics)
    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
        if project.process_id != pid or project.project_type != "IMPROVEMENT":
            raise HTTPException(400, "请选择同流程改善项目")
    row = Round(
        project_id=payload.project_id,
        process_id=pid,
        name=payload.name.strip(),
        scope_note=payload.scope_note.strip(),
        asis_model_version_id=version.id if version else None,
        metric_contracts=metric,
        baseline_window=payload.baseline_window.model_dump(mode="json"),
        baseline_samples=[],
        model_hashes={"asis": model_hash(version)} if version else {},
        created_by_id=user.id,
        supersedes_id=supersedes,
    )
    row.baseline_samples = samples(
        db,
        user,
        row,
        payload.baseline_samples,
        payload.baseline_window,
        "BASELINE",
        row.asis_model_version_id,
        metric,
    )
    db.add(row)
    db.flush()
    return row


def patch(db, user, row, payload):
    if payload.project_id != row.project_id:
        raise HTTPException(400, "草稿不可通过全量编辑偷换项目，请使用显式绑定")
    if row.baseline_confirmed_at:
        raise HTTPException(409, "前侧已固定，请创建新修订")
    version = (
        model(db, row.process_id, payload.asis_model_version_id)
        if payload.asis_model_version_id
        else None
    )
    metric = contracts(db, row.process_id, payload.metrics)
    sample = samples(
        db,
        user,
        row,
        payload.baseline_samples,
        payload.baseline_window,
        "BASELINE",
        payload.asis_model_version_id,
        metric,
    )
    cas(
        db,
        row,
        payload.expected_revision,
        {
            "name": payload.name,
            "scope_note": payload.scope_note,
            "asis_model_version_id": payload.asis_model_version_id,
            "metric_contracts": metric,
            "baseline_window": payload.baseline_window.model_dump(mode="json"),
            "baseline_samples": sample,
            "model_hashes": {"asis": model_hash(version)} if version else {},
        },
    )
    return row


def lock_baseline(db, user, row, payload):
    if row.baseline_confirmed_at:
        raise HTTPException(409, "前侧已经固定")
    version = model(db, row.process_id, row.asis_model_version_id)
    metric = contracts(
        db, row.process_id, [MetricInput.model_validate(x) for x in row.metric_contracts]
    )
    sample = samples(
        db,
        user,
        row,
        [SampleInput.model_validate(x) for x in row.baseline_samples],
        Window.model_validate(row.baseline_window),
        "BASELINE",
        version.id,
        metric,
    )
    if digest(metric) != digest(row.metric_contracts) or digest(sample) != digest(
        row.baseline_samples
    ):
        raise HTTPException(409, "原口径或样本已变化，请刷新并保存新草稿后重新确认")
    cas(
        db,
        row,
        payload.expected_revision,
        {
            "metric_contracts": metric,
            "baseline_samples": sample,
            "model_hashes": {"asis": model_hash(version)},
            "baseline_confirmed_at": utcnow(),
            "baseline_confirmed_by_id": user.id,
        },
    )
    return row


def revise(db, user, row, payload):
    from app.schemas.improvement_round import RoundDraft

    if row.revision != payload.expected_revision:
        raise HTTPException(409, "轮次已更新，请刷新")
    if row.after_samples:
        raise HTTPException(
            409, "已有后侧结果，不能以新修订重设本轮约定；请新建有独立窗口的后续轮次"
        )
    # 修订与后侧/追加共用原行CAS，旧会话不可绕过revision校验。
    cas(db, row, payload.expected_revision, {})
    data = RoundDraft(
        project_id=row.project_id,
        name=row.name + "（修订）",
        scope_note=row.scope_note,
        asis_model_version_id=row.asis_model_version_id,
        metrics=[MetricInput.model_validate(x) for x in row.metric_contracts],
        baseline_window=row.baseline_window,
        baseline_samples=[SampleInput.model_validate(x) for x in row.baseline_samples],
    )
    new = create(db, user, row.process_id, data, supersedes=row.id)
    new.project_id = row.project_id
    return new


def append(db, user, row, action, payload):
    if not row.baseline_confirmed_at:
        raise HTTPException(400, "请先固定前侧依据")
    values = {}
    if action == "bind-project":
        if row.project_id:
            raise HTTPException(409, "项目已经固定")
        project = db.get(Project, payload.reference_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
        if project.process_id != row.process_id or project.project_type != "IMPROVEMENT":
            raise HTTPException(400, "请选择同流程改善项目")
        values = {"project_id": project.id}
    elif action in ("bind-design", "bind-published"):
        field = "tobe_model_version_id" if action == "bind-design" else "released_model_version_id"
        if getattr(row, field):
            raise HTTPException(409, "该用途模型已经固定")
        version = model(
            db, row.process_id, payload.reference_id, published=action == "bind-published"
        )
        if (
            action == "bind-published"
            and row.after_window
            and version.published_at.date() > date.fromisoformat(row.after_window["start"])
        ):
            raise HTTPException(400, "实际发布时间晚于后侧窗口开始，不能作为该期上线模型")
        values = {
            field: version.id,
            "model_hashes": {**row.model_hashes, field: model_hash(version)},
        }
    elif action == "lock-acceptance":
        if row.acceptance_locked_at:
            raise HTTPException(409, "验收约定已锁定，不能原位覆盖")
        reviewer = db.get(User, payload.reviewer_user_id)
        if reviewer is None or not reviewer.is_active:
            raise HTTPException(400, "审核者不存在或已停用")
        if (
            payload.after_window.start <= date.today()
            or payload.after_window.start <= date.fromisoformat(row.baseline_window["end"])
        ):
            raise HTTPException(400, "后侧窗口须在锁定后开始且不与前侧重叠")
        if not all(
            getattr(payload, key).strip() for key in ("target", "red_lines", "observation_rule")
        ):
            raise HTTPException(400, "目标、红线和观察规则不可为空")
        values = {
            "acceptance_snapshot": payload.model_dump(
                mode="json", exclude={"expected_revision", "after_window"}
            ),
            "after_window": payload.after_window.model_dump(mode="json"),
            "acceptance_locked_at": utcnow(),
            "acceptance_locked_by_id": user.id,
        }
    elif action == "capture-after":
        if not row.acceptance_locked_at or not row.released_model_version_id:
            raise HTTPException(400, "请先固定真实发布版本和后侧观察前约定")
        if row.after_samples:
            raise HTTPException(409, "后侧样本已固定，不可覆盖")
        window = Window.model_validate(row.after_window)
        published = model(db, row.process_id, row.released_model_version_id, published=True)
        if published.published_at.date() > window.start:
            raise HTTPException(400, "原版本发布时间与后侧窗口矛盾")
        if window.end >= date.today():
            raise HTTPException(400, "后侧观察窗口尚未结束")
        values = {
            "after_samples": samples(
                db,
                user,
                row,
                payload.samples,
                window,
                "AFTER",
                row.released_model_version_id,
                row.metric_contracts,
            )
        }
    else:
        raise HTTPException(404, "轮次动作不存在")
    cas(db, row, payload.expected_revision, values)
    return row


def lock_reference(db, kind, ident):
    cls, column = (
        (ProcessArch, ProcessArch.model_version)
        if kind == "process"
        else (Project, Project.priority)
    )
    result = db.execute(
        update(cls).where(cls.id == ident).values({column.key: column}),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise HTTPException(404, "原引用对象不存在或已删除")
    obj = db.get(cls, ident)
    if obj:
        db.refresh(obj)


def command_scope(user_id, pid, rid, action):
    return "rnd." + digest([user_id, pid, rid, action])[:28]


def execute(db, user, pid, rid, action, payload, key=None):
    process(db, pid, user, True)
    lock_reference(db, "process", pid)
    project_id = (
        payload.reference_id if action == "bind-project" else getattr(payload, "project_id", None)
    )
    if project_id:
        lock_reference(db, "project", project_id)
    row = require(db, user, pid, rid, True) if rid else None
    process(db, pid, user, True)
    token = idempotency.begin(
        db, command_scope(user.id, pid, rid or 0, action), key, idempotency.request_hash(payload)
    )
    if token and token.status == "SUCCESS":
        previous = RoundOut.model_validate(token.response)
        require(db, user, pid, previous.id)
        return previous
    if action == "create":
        result = create(db, user, pid, payload)
    elif action == "patch":
        result = patch(db, user, row, payload)
    elif action == "lock-baseline":
        result = lock_baseline(db, user, row, payload)
    elif action == "revise":
        result = revise(db, user, row, payload)
    else:
        result = append(db, user, row, action, payload)
    response = out(result)
    audit.record(
        db,
        user,
        "UPDATE" if rid else "CREATE",
        "improvement_round",
        result.id,
        f"{action} revision={result.revision}；{result.name}",
    )
    idempotency.finish(token, response.model_dump(mode="json"))
    db.commit()
    return response


def list_rounds(db, user, pid):
    process(db, pid, user)
    result = []
    for row in db.scalars(
        select(Round).where(Round.process_id == pid).order_by(Round.id.desc())
    ).all():
        try:
            require(db, user, pid, row.id)
            result.append(out(row))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return result


def guard_delete(db, kind, ids):
    ids = set(ids)
    if kind in ("process", "project"):
        for ident in sorted(ids):
            lock_reference(db, kind, ident)
    for row in db.scalars(select(Round)).all():
        protected = (
            (kind == "process" and row.process_id in ids)
            or (kind == "project" and row.project_id in ids)
            or (
                kind == "model"
                and bool(
                    ids
                    & {
                        row.asis_model_version_id,
                        row.tobe_model_version_id,
                        row.released_model_version_id,
                    }
                )
            )
            or (kind == "kpi" and any(x["kpi_id"] in ids for x in row.metric_contracts))
        )
        if protected:
            raise HTTPException(409, "对象被薄轮次固定引用保护，请归档而非删除")
