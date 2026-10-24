"""分级授权矩阵服务：规则生命周期、例外审批与启动证据计数。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.authorization import AuthorizationException, AuthorizationRule
from app.models.enums import (
    AuthorizationCategory,
    AuthorizationExceptionStatus,
    AuthorizationStatus,
)
from app.models.org import OrgUnit
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument
from app.models.raci import GovernanceRole
from app.models.user import User
from app.schemas.authorization import (
    AuthorizationExceptionOut,
    AuthorizationRuleOut,
)
from app.schemas.common import as_columns


class AuthorizationError(ValueError):
    pass


CATEGORY_LABELS: Dict[str, str] = {
    AuthorizationCategory.A.value: "A 类 · 集团治理委员会",
    AuthorizationCategory.B.value: "B 类 · 单元负责人 + BPM",
    AuthorizationCategory.C.value: "C 类 · 工厂负责人",
    AuthorizationCategory.D.value: "D 类 · 岗位按标准执行",
}

CATEGORY_APPROVER_HINT: Dict[str, str] = {
    AuthorizationCategory.A.value: "集团治理委员会",
    AuthorizationCategory.B.value: "单元负责人 + BPM 办公室",
    AuthorizationCategory.C.value: "工厂负责人",
    AuthorizationCategory.D.value: "岗位/班组按标准执行",
}

STATUS_LABELS: Dict[str, str] = {
    AuthorizationStatus.DRAFT.value: "草稿",
    AuthorizationStatus.EFFECTIVE.value: "已生效",
    AuthorizationStatus.RETIRED.value: "已停用",
}

EXCEPTION_STATUS_LABELS: Dict[str, str] = {
    AuthorizationExceptionStatus.REQUESTED.value: "待审批",
    AuthorizationExceptionStatus.APPROVED.value: "已批准",
    AuthorizationExceptionStatus.REJECTED.value: "已驳回",
    AuthorizationExceptionStatus.CLOSED.value: "已关闭",
}

RISK_LABELS: Dict[str, str] = {
    "HIGH": "高",
    "MEDIUM": "中",
    "LOW": "低",
}


def _next_code(db: Session, model, prefix: str) -> str:
    existing = db.scalars(select(model.code).where(model.code.like(f"{prefix}%"))).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def next_rule_code(db: Session) -> str:
    return _next_code(db, AuthorizationRule, f"AUTH-{date.today().year}-")


def next_exception_code(db: Session) -> str:
    return _next_code(db, AuthorizationException, f"AEX-{date.today().year}-")


def require_rule(db: Session, rule_id: int) -> AuthorizationRule:
    row = db.get(AuthorizationRule, rule_id)
    if row is None:
        raise AuthorizationError(f"授权规则 {rule_id} 不存在")
    return row


def require_exception(db: Session, exception_id: int) -> AuthorizationException:
    row = db.get(AuthorizationException, exception_id)
    if row is None:
        raise AuthorizationError(f"例外记录 {exception_id} 不存在")
    return row


def _check_refs(db: Session, data: dict) -> None:
    process_id = data.get("process_id")
    if process_id is not None and db.get(ProcessArch, process_id) is None:
        raise AuthorizationError("关联流程不存在")
    org_unit_id = data.get("org_unit_id")
    if org_unit_id is not None and db.get(OrgUnit, org_unit_id) is None:
        raise AuthorizationError("适用范围组织不存在")
    role_id = data.get("approver_role_id")
    if role_id is not None and db.get(GovernanceRole, role_id) is None:
        raise AuthorizationError("审批角色不存在")
    document_id = data.get("document_id")
    if document_id is not None and db.get(ProcessDocument, document_id) is None:
        raise AuthorizationError("关联制度文件不存在")
    owner_user_id = data.get("owner_user_id")
    if owner_user_id is not None and db.get(User, owner_user_id) is None:
        raise AuthorizationError("规则负责人不存在")
    valid_from = data.get("valid_from")
    valid_to = data.get("valid_to")
    if valid_from and valid_to and valid_from > valid_to:
        raise AuthorizationError("生效日期不能晚于失效日期")


def _validate_effective(row: AuthorizationRule) -> None:
    missing = []
    if not (row.title or "").strip():
        missing.append("规则名称")
    if not (row.matter or "").strip():
        missing.append("关键事项")
    if not row.category:
        missing.append("授权类别")
    if not row.approver_role_id and not (row.approver_label or "").strip():
        missing.append("审批角色")
    if not (row.exception_path or "").strip():
        missing.append("例外路径")
    if not (row.evidence_required or "").strip():
        missing.append("审批证据")
    if missing:
        raise AuthorizationError("规则生效前必须补齐：" + "、".join(missing))


def rule_out(db: Session, row: AuthorizationRule) -> AuthorizationRuleOut:
    process = db.get(ProcessArch, row.process_id) if row.process_id else None
    org_unit = db.get(OrgUnit, row.org_unit_id) if row.org_unit_id else None
    role = db.get(GovernanceRole, row.approver_role_id) if row.approver_role_id else None
    document = db.get(ProcessDocument, row.document_id) if row.document_id else None
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    return AuthorizationRuleOut(
        id=row.id,
        code=row.code,
        title=row.title,
        matter=row.matter,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        org_unit_id=row.org_unit_id,
        org_unit_name=org_unit.name if org_unit else None,
        category=row.category,
        category_label=CATEGORY_LABELS.get(row.category, row.category),
        risk_level=row.risk_level,
        risk_level_label=RISK_LABELS.get(row.risk_level, row.risk_level),
        amount_limit=float(row.amount_limit) if row.amount_limit is not None else None,
        impact_scope=row.impact_scope,
        reversibility=row.reversibility,
        frequency=row.frequency,
        approver_role_id=row.approver_role_id,
        approver_role_name=role.name if role else None,
        approver_label=row.approver_label,
        exception_path=row.exception_path,
        evidence_required=row.evidence_required,
        document_id=row.document_id,
        document_code=document.code if document else None,
        document_title=document.title if document else None,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        version=row.version,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        owner_user_id=row.owner_user_id,
        owner_name=owner.display_name if owner else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def exception_out(db: Session, row: AuthorizationException) -> AuthorizationExceptionOut:
    rule = db.get(AuthorizationRule, row.rule_id)
    process = db.get(ProcessArch, row.process_id) if row.process_id else None
    return AuthorizationExceptionOut(
        id=row.id,
        code=row.code,
        rule_id=row.rule_id,
        rule_code=rule.code if rule else None,
        rule_title=rule.title if rule else None,
        rule_category=rule.category if rule else None,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        title=row.title,
        reason=row.reason,
        scope=row.scope,
        status=row.status,
        status_label=EXCEPTION_STATUS_LABELS.get(row.status, row.status),
        requested_by_id=row.requested_by_id,
        requested_by_name=row.requested_by_name,
        requested_at=row.requested_at,
        decided_by_id=row.decided_by_id,
        decided_by_name=row.decided_by_name,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


def create_rule(db: Session, payload, user: User) -> AuthorizationRule:
    data = as_columns(payload.model_dump())
    _check_refs(db, data)
    row = AuthorizationRule(
        code=next_rule_code(db),
        title=data["title"],
        matter=data["matter"],
        process_id=data.get("process_id"),
        org_unit_id=data.get("org_unit_id"),
        category=data["category"],
        risk_level=data.get("risk_level", "MEDIUM"),
        amount_limit=data.get("amount_limit"),
        impact_scope=data.get("impact_scope"),
        reversibility=data.get("reversibility"),
        frequency=data.get("frequency"),
        approver_role_id=data.get("approver_role_id"),
        approver_label=data.get("approver_label"),
        exception_path=data.get("exception_path"),
        evidence_required=data.get("evidence_required"),
        document_id=data.get("document_id"),
        status=AuthorizationStatus.DRAFT.value,
        version=1,
        valid_from=data.get("valid_from"),
        valid_to=data.get("valid_to"),
        owner_user_id=data.get("owner_user_id") or user.id,
    )
    db.add(row)
    db.flush()
    return row


def update_rule(db: Session, row: AuthorizationRule, payload) -> AuthorizationRule:
    if row.status == AuthorizationStatus.RETIRED.value:
        raise AuthorizationError("已停用的规则不能修改，请新建版本")
    data = as_columns(payload.model_dump(exclude_unset=True))
    merged = {
        "process_id": data.get("process_id", row.process_id),
        "org_unit_id": data.get("org_unit_id", row.org_unit_id),
        "approver_role_id": data.get("approver_role_id", row.approver_role_id),
        "document_id": data.get("document_id", row.document_id),
        "owner_user_id": data.get("owner_user_id", row.owner_user_id),
        "valid_from": data.get("valid_from", row.valid_from),
        "valid_to": data.get("valid_to", row.valid_to),
    }
    _check_refs(db, merged)
    was_effective = row.status == AuthorizationStatus.EFFECTIVE.value
    for field, value in data.items():
        setattr(row, field, value)
    if was_effective:
        # 口径变更必须重新走生效，旧结论不能悄悄继续用
        row.status = AuthorizationStatus.DRAFT.value
        row.version = (row.version or 1) + 1
    db.flush()
    return row


def activate_rule(db: Session, row: AuthorizationRule) -> AuthorizationRule:
    if row.status == AuthorizationStatus.RETIRED.value:
        raise AuthorizationError("已停用的规则不能重新生效，请新建规则")
    _validate_effective(row)
    row.status = AuthorizationStatus.EFFECTIVE.value
    db.flush()
    return row


def retire_rule(db: Session, row: AuthorizationRule) -> AuthorizationRule:
    row.status = AuthorizationStatus.RETIRED.value
    db.flush()
    return row


def delete_rule(db: Session, row: AuthorizationRule) -> None:
    if row.status != AuthorizationStatus.DRAFT.value:
        raise AuthorizationError("只有草稿规则可以删除；已生效规则请先停用")
    db.delete(row)
    db.flush()


def create_exception(db: Session, payload, user: User) -> AuthorizationException:
    rule = require_rule(db, payload.rule_id)
    if rule.status == AuthorizationStatus.RETIRED.value:
        raise AuthorizationError("规则已停用，不能再申请例外")
    row = AuthorizationException(
        code=next_exception_code(db),
        rule_id=rule.id,
        process_id=payload.process_id or rule.process_id,
        title=payload.title,
        reason=payload.reason,
        scope=payload.scope,
        status=AuthorizationExceptionStatus.REQUESTED.value,
        requested_by_id=user.id,
        requested_by_name=user.display_name,
        requested_at=utcnow(),
        expires_at=payload.expires_at,
    )
    db.add(row)
    db.flush()
    return row


def decide_exception(
    db: Session,
    row: AuthorizationException,
    user: User,
    approved: bool,
    note: Optional[str],
) -> AuthorizationException:
    if row.status != AuthorizationExceptionStatus.REQUESTED.value:
        raise AuthorizationError("只有待审批的例外可以处理")
    if not approved and not (note or "").strip():
        raise AuthorizationError("驳回例外时必须填写原因")
    row.status = (
        AuthorizationExceptionStatus.APPROVED.value
        if approved
        else AuthorizationExceptionStatus.REJECTED.value
    )
    row.decided_by_id = user.id
    row.decided_by_name = user.display_name
    row.decided_at = utcnow()
    row.decision_note = (note or "").strip() or None
    db.flush()
    return row


def close_exception(
    db: Session, row: AuthorizationException, user: User, note: Optional[str]
) -> AuthorizationException:
    if row.status != AuthorizationExceptionStatus.APPROVED.value:
        raise AuthorizationError("只有已批准的例外可以关闭")
    row.status = AuthorizationExceptionStatus.CLOSED.value
    row.decided_by_id = user.id
    row.decided_by_name = user.display_name
    row.decided_at = utcnow()
    if note:
        row.decision_note = note.strip()
    db.flush()
    return row


def effective_rule_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuthorizationRule)
            .where(AuthorizationRule.status == AuthorizationStatus.EFFECTIVE.value)
        )
        or 0
    )


def open_exception_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuthorizationException)
            .where(
                AuthorizationException.status.in_(
                    [
                        AuthorizationExceptionStatus.REQUESTED.value,
                        AuthorizationExceptionStatus.APPROVED.value,
                    ]
                )
            )
        )
        or 0
    )


def list_rules(
    db: Session,
    process_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> List[AuthorizationRule]:
    stmt = select(AuthorizationRule)
    if process_id is not None:
        stmt = stmt.where(AuthorizationRule.process_id == process_id)
    if org_unit_id is not None:
        stmt = stmt.where(AuthorizationRule.org_unit_id == org_unit_id)
    if category:
        stmt = stmt.where(AuthorizationRule.category == category)
    if status:
        stmt = stmt.where(AuthorizationRule.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            AuthorizationRule.title.like(like)
            | AuthorizationRule.matter.like(like)
            | AuthorizationRule.code.like(like)
        )
    return list(db.scalars(stmt.order_by(AuthorizationRule.id.desc())).all())


def list_exceptions(
    db: Session,
    rule_id: Optional[int] = None,
    process_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[AuthorizationException]:
    stmt = select(AuthorizationException)
    if rule_id is not None:
        stmt = stmt.where(AuthorizationException.rule_id == rule_id)
    if process_id is not None:
        stmt = stmt.where(AuthorizationException.process_id == process_id)
    if status:
        stmt = stmt.where(AuthorizationException.status == status)
    return list(db.scalars(stmt.order_by(AuthorizationException.id.desc())).all())
