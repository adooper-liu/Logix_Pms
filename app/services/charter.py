"""原流程章程的客户结果、原证据引用及修订保护。"""

import json
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.startup import ProcessCharter
from app.models.user import User
from app.schemas.startup import CharterContextOut, CharterOut
from app.services import audit, org_access, process_scope, strategy

TEXT_FIELDS = ("purpose", "starts_at", "ends_at", "in_scope", "out_of_scope", "stop_condition")


def require_process(db, process_id):
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(404, "流程不存在")
    if process.level != 3:
        raise HTTPException(400, "范围说明只能挂在L3上")
    return process


def document_ref(db, user, version_id, process_ids, *, retained=False):
    if version_id is None:
        return
    version = db.get(ProcessDocumentVersion, version_id)
    document = db.get(ProcessDocument, version.document_id) if version else None
    if document is None:
        raise HTTPException(404, "标准版本不存在")
    org_access.ensure_visible(db, user, document.org_unit_id)
    if document.process_id not in process_ids:
        raise HTTPException(400, "标准版本不属于本流程或其上级范围")
    today = date.today()
    if not retained and (
        version.status != "EFFECTIVE"
        or not document.is_active
        or (version.valid_from and version.valid_from > today)
        or (version.valid_to and version.valid_to < today)
    ):
        raise HTTPException(400, "请选择有效期内已生效的原标准版本")


def context(db: Session, process_id: int, user=None) -> CharterContextOut:
    process = require_process(db, process_id)
    row = db.scalar(select(ProcessCharter).where(ProcessCharter.process_id == process_id))
    stale = False
    if row:
        for key in ("mandate_version_id", "resource_version_id"):
            vid = (row.details or {}).get(key)
            if not vid:
                continue
            version = db.get(ProcessDocumentVersion, vid)
            document = db.get(ProcessDocument, version.document_id) if version else None
            if user and document:
                org_access.ensure_visible(db, user, document.org_unit_id)
            today = date.today()
            stale = (
                stale
                or not version
                or not document
                or not document.is_active
                or version.status != "EFFECTIVE"
                or bool(version.valid_to and version.valid_to < today)
                or bool(version.valid_from and version.valid_from > today)
            )
    return CharterContextOut(
        process_id=process_id,
        process_code=process.code,
        owner_user_id=process.owner_user_id,
        owner=process.owner,
        charter=CharterOut(
            **{key: getattr(row, key) for key in ("process_id", *TEXT_FIELDS, "sponsor_user_id")}
        )
        if row
        else None,
        details=row.details or {} if row else {},
        revision=row.revision if row else 0,
        reference_label="原固定依据待复核" if stale else "原引用已固定（不证明授权充分）",
        verification_label="已记录核验依据（未代替授权批准）"
        if row and (row.details or {}).get("verification_evidence")
        else "未记录核验依据",
    )


def save(db: Session, user: User, payload, *, legacy=False):
    process = require_process(db, payload.process_id)
    if process.owner_user_id is None:
        raise HTTPException(400, "先给这条L3指定负责人")
    sponsor = db.get(User, payload.sponsor_user_id)
    if sponsor is None or not sponsor.is_active:
        raise HTTPException(400, "发起人不存在或已停用")
    fields = {key: getattr(payload, key).strip() for key in TEXT_FIELDS}
    if not all(fields.values()):
        raise HTTPException(400, "范围说明的每一项都要写上")
    row = db.scalar(select(ProcessCharter).where(ProcessCharter.process_id == process.id))
    before = context(db, process.id).model_dump(mode="json")
    revision = row.revision if row else 0
    expected = revision if legacy else payload.expected_revision
    if expected != revision:
        raise HTTPException(409, "范围说明已更新，请刷新后重试")
    details = (
        (row.details or {} if row else {}) if legacy else payload.details.model_dump(mode="json")
    )
    if not legacy:
        objective_id = details.get("objective_id")
        if objective_id and objective_id not in {
            item.id for item in strategy.objectives_for_process(db, process.id)
        }:
            raise HTTPException(400, "目标尚未通过原承接关系关联本流程或其上级")
        ids = process_scope.ancestor_ids(db, process.id)
        for key in ("mandate_version_id", "resource_version_id"):
            retained = bool(row and (row.details or {}).get(key) == details.get(key))
            document_ref(db, user, details.get(key), ids, retained=retained)
    values = {
        **fields,
        "sponsor_user_id": sponsor.id,
        "details": details,
        "revision": revision + 1,
        "updated_at": utcnow(),
    }
    if row:
        result = db.execute(
            update(ProcessCharter)
            .where(ProcessCharter.id == row.id, ProcessCharter.revision == expected)
            .values(**values)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "范围说明已更新，请刷新后重试")
        db.expire(row)
    else:
        db.add(ProcessCharter(process_id=process.id, **values))
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "范围说明已由其他请求创建，请刷新后重试") from exc
    after = context(db, process.id).model_dump(mode="json")
    audit.record(
        db,
        user,
        "UPDATE",
        "process_charter",
        process.id,
        json.dumps({"before": before, "after": after}, ensure_ascii=False),
    )
    db.commit()
    return context(db, process.id)
