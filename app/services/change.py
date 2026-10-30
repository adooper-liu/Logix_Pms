"""变更单服务：状态机、影响分析校验与发布门禁。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.change import ProcessChangeRequest
from app.models.enums import ChangeImpactLevel, ChangeStatus, ChangeType
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.user import User
from app.schemas.change import ChangeRequestOut, ChangeVersionRef

CHANGE_TYPE_LABELS = {
    ChangeType.STRUCTURE.value: "流程结构",
    ChangeType.KPI.value: "KPI / 指标",
    ChangeType.FORM_RULE.value: "表单 / 规则",
    ChangeType.POLICY.value: "制度 / 权限",
    ChangeType.OTHER.value: "其他",
}

IMPACT_LEVEL_LABELS = {
    ChangeImpactLevel.MAJOR.value: "重大",
    ChangeImpactLevel.MINOR.value: "一般",
    ChangeImpactLevel.PATCH.value: "修订",
}

STATUS_LABELS = {
    ChangeStatus.DRAFT.value: "草稿",
    ChangeStatus.SUBMITTED.value: "待审批",
    ChangeStatus.APPROVED.value: "已批准",
    ChangeStatus.REJECTED.value: "已驳回",
    ChangeStatus.APPLIED.value: "已应用",
    ChangeStatus.CANCELLED.value: "已取消",
}

IMPACT_KEYS = ("people", "systems", "data", "permissions", "controls", "training", "kpis")

IMPACT_LABELS = {
    "people": "人员影响",
    "systems": "系统影响",
    "data": "数据影响",
    "permissions": "权限影响",
    "controls": "控制影响",
    "training": "培训影响",
    "kpis": "指标影响",
}


class ChangeError(ValueError):
    """变更单规则拒绝；API 层转成 400/409。"""


def next_code(db: Session) -> str:
    prefix = f"CR-{date.today().year}-"
    existing = db.scalars(
        select(ProcessChangeRequest.code).where(ProcessChangeRequest.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def require_change(db: Session, change_id: int) -> ProcessChangeRequest:
    row = db.get(ProcessChangeRequest, change_id)
    if row is None:
        raise ChangeError(f"变更申请 {change_id} 不存在")
    return row


def validate_impact(row: ProcessChangeRequest) -> None:
    """重大变更必须有完整影响分析、测试证据和回退方案。"""
    if row.impact_level == ChangeImpactLevel.MAJOR.value:
        impact = row.impact or {}
        missing = [key for key in IMPACT_KEYS if not (impact.get(key) or "").strip()]
        if missing:
            raise ChangeError(
                "重大变更必须填写完整影响分析："
                + "、".join(missing)
                + "（人员/系统/数据/权限/控制/培训/KPI）"
            )
        if not (row.test_evidence or "").strip():
            raise ChangeError("重大变更必须填写测试证据")
        if not (row.rollback_plan or "").strip():
            raise ChangeError("重大变更必须填写回退方案")
    elif row.impact_level == ChangeImpactLevel.MINOR.value:
        if not (row.rollback_plan or "").strip():
            raise ChangeError("一般变更必须填写回退方案")


def create_change(db: Session, data: Dict, user: User) -> ProcessChangeRequest:
    data = dict(data)
    if not data.get("code"):
        data["code"] = next_code(db)
    process = db.get(ProcessArch, data["process_id"])
    if process is None:
        raise ChangeError(f"流程 {data['process_id']} 不存在")
    data["status"] = ChangeStatus.DRAFT.value
    data["requested_by_id"] = user.id
    data["requested_by_name"] = user.display_name
    row = ProcessChangeRequest(**data)
    db.add(row)
    db.flush()
    return row


def update_change(db: Session, row: ProcessChangeRequest, data: Dict) -> ProcessChangeRequest:
    if row.status != ChangeStatus.DRAFT.value:
        raise ChangeError("只有草稿状态的变更申请可以修改")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def submit_change(db: Session, row: ProcessChangeRequest) -> None:
    if row.status != ChangeStatus.DRAFT.value:
        raise ChangeError("只有草稿可以提交审批")
    validate_impact(row)
    row.status = ChangeStatus.SUBMITTED.value
    db.flush()


def approve_change(
    db: Session, row: ProcessChangeRequest, user: User, note: Optional[str] = None
) -> None:
    if row.status != ChangeStatus.SUBMITTED.value:
        raise ChangeError("只有待审批的变更申请可以批准")
    row.status = ChangeStatus.APPROVED.value
    row.approved_by_id = user.id
    row.approved_by_name = user.display_name
    row.approved_at = utcnow()
    if note:
        row.decision_note = note
    db.flush()


def reject_change(
    db: Session, row: ProcessChangeRequest, user: User, note: Optional[str] = None
) -> None:
    if row.status != ChangeStatus.SUBMITTED.value:
        raise ChangeError("只有待审批的变更申请可以驳回")
    row.status = ChangeStatus.REJECTED.value
    row.approved_by_id = user.id
    row.approved_by_name = user.display_name
    row.approved_at = utcnow()
    row.decision_note = note
    db.flush()


def cancel_change(db: Session, row: ProcessChangeRequest) -> None:
    if row.status in (
        ChangeStatus.APPLIED.value,
        ChangeStatus.REJECTED.value,
        ChangeStatus.CANCELLED.value,
    ):
        raise ChangeError("已应用/已驳回/已取消的变更申请不能再次取消")
    row.status = ChangeStatus.CANCELLED.value
    db.flush()


def mark_applied(db: Session, row: ProcessChangeRequest) -> None:
    if row.status != ChangeStatus.APPROVED.value:
        raise ChangeError("只有已批准的变更申请可以应用到发布")
    row.status = ChangeStatus.APPLIED.value
    row.applied_at = utcnow()
    db.flush()


def change_out(db: Session, row: ProcessChangeRequest) -> ChangeRequestOut:
    process = db.get(ProcessArch, row.process_id)
    versions = db.scalars(
        select(ProcessModelVersion)
        .where(ProcessModelVersion.change_request_id == row.id)
        .order_by(ProcessModelVersion.version)
    ).all()
    return ChangeRequestOut(
        id=row.id,
        code=row.code,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        title=row.title,
        reason=row.reason,
        scope=row.scope,
        change_type=row.change_type,
        change_type_label=CHANGE_TYPE_LABELS.get(row.change_type, row.change_type),
        impact_level=row.impact_level,
        impact_level_label=IMPACT_LEVEL_LABELS.get(row.impact_level, row.impact_level),
        version_label=row.version_label,
        impact=row.impact or {},
        test_evidence=row.test_evidence,
        rollback_plan=row.rollback_plan,
        effective_date=row.effective_date,
        emergency=row.emergency,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        decision_note=row.decision_note,
        requested_by_id=row.requested_by_id,
        requested_by_name=row.requested_by_name,
        approved_by_id=row.approved_by_id,
        approved_by_name=row.approved_by_name,
        approved_at=row.approved_at,
        applied_at=row.applied_at,
        linked_versions=[
            ChangeVersionRef(
                id=version.id,
                version=version.version,
                status=version.status,
                published_at=version.published_at,
            )
            for version in versions
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_changes(
    db: Session,
    *,
    process_id: Optional[int] = None,
    status: Optional[str] = None,
    year: Optional[int] = None,
) -> List[ChangeRequestOut]:
    stmt = select(ProcessChangeRequest)
    if process_id is not None:
        stmt = stmt.where(ProcessChangeRequest.process_id == process_id)
    if status is not None:
        stmt = stmt.where(ProcessChangeRequest.status == status)
    if year is not None:
        stmt = stmt.where(extract("year", ProcessChangeRequest.created_at) == year)
    rows = db.scalars(
        stmt.order_by(ProcessChangeRequest.created_at.desc(), ProcessChangeRequest.id.desc())
    ).all()
    return [change_out(db, row) for row in rows]


def latest_approved_request(db: Session, process_id: int) -> Optional[ProcessChangeRequest]:
    """该流程最新一张已批准、尚未应用的变更申请。"""
    return db.scalar(
        select(ProcessChangeRequest)
        .where(
            ProcessChangeRequest.process_id == process_id,
            ProcessChangeRequest.status == ChangeStatus.APPROVED.value,
        )
        .order_by(ProcessChangeRequest.approved_at.desc(), ProcessChangeRequest.id.desc())
    )


def approved_for_process(db: Session, process_id: int) -> Optional[ChangeRequestOut]:
    """发布门禁使用：该流程最新一张已批准的变更申请。"""
    row = latest_approved_request(db, process_id)
    return change_out(db, row) if row else None


def require_approved(db: Session, process_id: int, change_request_id: int) -> ProcessChangeRequest:
    row = require_change(db, change_request_id)
    if row.process_id != process_id:
        raise ChangeError("变更申请不属于该流程")
    if row.status != ChangeStatus.APPROVED.value:
        raise ChangeError("变更申请尚未批准，不能用于发布")
    return row
