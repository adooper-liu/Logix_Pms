"""原培训/控制复盘记录，不以签到替代操作。"""

from copy import deepcopy
from datetime import date

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.core.timeutil import utcnow
from app.models.adoption import ProcessTrainingRecord
from app.models.user import User
from app.services import audit, improvement_round


class OperationIn(BaseModel):
    expected_revision: int = Field(ge=0)
    model_version_id: int = Field(ge=1)
    round_id: int | None = None
    reviewer_user_id: int = Field(ge=1)
    scenario: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=3000)
    review_due: date


class ReviewIn(BaseModel):
    expected_revision: int = Field(ge=0)
    decision: str = Field(pattern="^(ACCEPT|RETURN)$")
    evidence: str = Field(min_length=1, max_length=2000)


def out(row):
    op = row.operation or {}
    review = op.get("review") or {}
    verified = (
        review.get("decision") == "ACCEPT" and op.get("review_due", "") >= date.today().isoformat()
    )
    return {
        "id": row.id,
        "process_id": row.process_id,
        "trainee_user_id": row.trainee_user_id,
        "topic": row.topic,
        "completed_on": row.completed_on,
        "revision": row.revision,
        "operation": row.operation,
        "operation_verified": verified,
        "state_label": "原版本操作已核验" if verified else "到场已登记，操作待核验",
    }


def require(db, user, ident):
    row = db.get(ProcessTrainingRecord, ident)
    if row is None:
        raise HTTPException(404, "培训记录不存在")
    if row.operation and row.operation.get("round_id"):
        improvement_round.require(db, user, row.process_id, row.operation["round_id"])
    return row


def save(db, user, ident, payload):
    row = require(db, user, ident)
    model = improvement_round.model(db, row.process_id, payload.model_version_id)
    if payload.round_id:
        round_row = improvement_round.require(db, user, row.process_id, payload.round_id)
        if model.id not in {
            round_row.asis_model_version_id,
            round_row.tobe_model_version_id,
            round_row.released_model_version_id,
        }:
            raise HTTPException(400, "操作模型不属于所选轮次固定角色")
    reviewer = db.get(User, payload.reviewer_user_id)
    if (
        reviewer is None
        or not reviewer.is_active
        or reviewer.role == "VIEWER"
        or reviewer.id in (user.id, row.trainee_user_id)
    ):
        raise HTTPException(400, "指定非编制者/学员的本人核验")
    data = payload.model_dump(mode="json", exclude={"expected_revision"})
    data.update(edited_by_id=user.id, model_hash=improvement_round.model_hash(model))
    if row.operation:
        old = deepcopy(row.operation)
        history = old.pop("history", [])
        data["history"] = [*history, old]
    changed = db.execute(
        update(ProcessTrainingRecord)
        .where(
            ProcessTrainingRecord.id == ident,
            ProcessTrainingRecord.revision == payload.expected_revision,
        )
        .values(operation=data, revision=payload.expected_revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "操作核验记录已变化")
    audit.record(
        db, user, "UPDATE", "process_training_record", ident, "修订操作场景/原版本依据（清原核验）"
    )
    db.commit()
    db.refresh(row)
    return out(row)


def review(db, user, ident, payload):
    row = require(db, user, ident)
    data = deepcopy(row.operation or {})
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "操作记录已变化")
    if data.get("reviewer_user_id") != user.id or user.id in (
        data.get("edited_by_id"),
        row.trainee_user_id,
    ):
        raise HTTPException(403, "仅指定独立本人可核验操作")
    if not payload.evidence.strip():
        raise HTTPException(400, "请附实际操作核验依据")
    data["review"] = {
        "decision": payload.decision,
        "evidence": payload.evidence,
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().isoformat() + "+00:00",
    }
    changed = db.execute(
        update(ProcessTrainingRecord)
        .where(
            ProcessTrainingRecord.id == ident,
            ProcessTrainingRecord.revision == payload.expected_revision,
        )
        .values(operation=data, revision=payload.expected_revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "操作记录已变化")
    audit.record(
        db,
        user,
        "UPDATE",
        "process_training_record",
        ident,
        "本人操作核验：" + payload.decision + "；" + payload.evidence,
    )
    db.commit()
    db.refresh(row)
    return out(row)
