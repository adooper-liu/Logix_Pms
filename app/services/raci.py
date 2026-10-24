"""治理角色与 RACI 服务：角色成员、唯一 A 校验与流程权责矩阵。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import GovernanceRoleType, RaciType
from app.models.org import OrgUnit
from app.models.process import ProcessArch
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import User
from app.schemas.raci import (
    GovernanceMemberOut,
    GovernanceRoleOut,
    RaciMatterOut,
    RaciOut,
    RaciProcessOut,
)

ROLE_TYPE_LABELS = {
    GovernanceRoleType.COMMITTEE.value: "集团流程治理委员会",
    GovernanceRoleType.ENTERPRISE_OWNER.value: "集团端到端流程所有者",
    GovernanceRoleType.UNIT_OWNER.value: "业务单元/工厂流程所有者",
    GovernanceRoleType.STEWARD.value: "流程管理员/管家",
    GovernanceRoleType.BPM_OFFICE.value: "BPM/卓越运营办公室",
    GovernanceRoleType.DATA_OWNER.value: "数据所有者/管家",
    GovernanceRoleType.RISK_LEGAL.value: "风险/法务/财务/内控",
    GovernanceRoleType.OTHER.value: "其他",
}

RACI_LABELS = {
    RaciType.A.value: "A 唯一负责",
    RaciType.R.value: "R 执行",
    RaciType.C.value: "C 咨询",
    RaciType.I.value: "I 知会",
}


class RaciError(ValueError):
    """治理角色/RACI 规则拒绝；API 层转成 400/409。"""


def next_role_code(db: Session) -> str:
    existing = db.scalars(select(GovernanceRole.code).where(GovernanceRole.code.like("GR-%"))).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"GR-{seq + 1:03d}"


def require_role(db: Session, role_id: int) -> GovernanceRole:
    row = db.get(GovernanceRole, role_id)
    if row is None:
        raise RaciError(f"治理角色 {role_id} 不存在")
    return row


def require_process(db: Session, process_id: int) -> ProcessArch:
    row = db.get(ProcessArch, process_id)
    if row is None:
        raise RaciError(f"流程 {process_id} 不存在")
    return row


def member_out(member: GovernanceRoleMember) -> GovernanceMemberOut:
    user = member.user
    return GovernanceMemberOut(
        id=member.id,
        user_id=member.user_id,
        user_name=user.display_name if user else None,
        role_label=user.role_label if user else None,
        is_primary=member.is_primary,
    )


def role_out(db: Session, row: GovernanceRole) -> GovernanceRoleOut:
    org = db.get(OrgUnit, row.org_unit_id) if row.org_unit_id else None
    members = [member_out(member) for member in row.members]
    return GovernanceRoleOut(
        id=row.id,
        code=row.code,
        name=row.name,
        role_type=row.role_type,
        role_type_label=ROLE_TYPE_LABELS.get(row.role_type, row.role_type),
        org_unit_id=row.org_unit_id,
        org_unit_name=org.name if org else None,
        description=row.description,
        is_active=row.is_active,
        members=members,
        member_count=len(members),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_roles(
    db: Session, *, active_only: bool = False, role_type: Optional[str] = None
) -> List[GovernanceRoleOut]:
    stmt = select(GovernanceRole).options(
        selectinload(GovernanceRole.members).joinedload(GovernanceRoleMember.user)
    )
    if active_only:
        stmt = stmt.where(GovernanceRole.is_active.is_(True))
    if role_type is not None:
        stmt = stmt.where(GovernanceRole.role_type == role_type)
    rows = db.scalars(stmt.order_by(GovernanceRole.code)).all()
    return [role_out(db, row) for row in rows]


def create_role(db: Session, data: Dict) -> GovernanceRole:
    data = dict(data)
    if not data.get("code"):
        data["code"] = next_role_code(db)
    if db.scalar(select(GovernanceRole).where(GovernanceRole.code == data["code"])):
        raise RaciError(f"治理角色编码 {data['code']} 已存在")
    row = GovernanceRole(**data)
    db.add(row)
    db.flush()
    return row


def update_role(db: Session, row: GovernanceRole, data: Dict) -> GovernanceRole:
    data = dict(data)
    if "code" in data and data["code"] != row.code:
        if db.scalar(
            select(GovernanceRole).where(
                GovernanceRole.code == data["code"], GovernanceRole.id != row.id
            )
        ):
            raise RaciError(f"治理角色编码 {data['code']} 已存在")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def delete_role(db: Session, row: GovernanceRole) -> None:
    used = db.scalar(
        select(func.count()).select_from(RaciAssignment).where(RaciAssignment.role_id == row.id)
    )
    if used:
        raise RaciError(f"角色仍被 {used} 条 RACI 使用，请先解除或停用")
    db.delete(row)
    db.flush()


def add_member(
    db: Session, role: GovernanceRole, user_id: int, is_primary: bool = False
) -> GovernanceRoleMember:
    if db.get(User, user_id) is None:
        raise RaciError(f"用户 {user_id} 不存在")
    existing = db.scalar(
        select(GovernanceRoleMember).where(
            GovernanceRoleMember.role_id == role.id,
            GovernanceRoleMember.user_id == user_id,
        )
    )
    if existing is not None:
        raise RaciError("该用户已在角色中")
    if is_primary:
        for member in db.scalars(
            select(GovernanceRoleMember).where(GovernanceRoleMember.role_id == role.id)
        ).all():
            member.is_primary = False
    row = GovernanceRoleMember(role_id=role.id, user_id=user_id, is_primary=is_primary)
    db.add(row)
    db.flush()
    return row


def remove_member(db: Session, role: GovernanceRole, member_id: int) -> None:
    member = db.get(GovernanceRoleMember, member_id)
    if member is None or member.role_id != role.id:
        raise RaciError(f"角色成员 {member_id} 不存在")
    db.delete(member)
    db.flush()


def raci_out(db: Session, row: RaciAssignment) -> RaciOut:
    role = db.get(GovernanceRole, row.role_id)
    return RaciOut(
        id=row.id,
        process_id=row.process_id,
        matter=row.matter,
        role_id=row.role_id,
        role_name=role.name if role else None,
        role_type_label=(ROLE_TYPE_LABELS.get(role.role_type, role.role_type) if role else None),
        raci=row.raci,
        raci_label=RACI_LABELS.get(row.raci, row.raci),
        note=row.note,
    )


def process_raci(db: Session, process_id: int) -> RaciProcessOut:
    process = require_process(db, process_id)
    rows = db.scalars(
        select(RaciAssignment)
        .where(RaciAssignment.process_id == process_id)
        .order_by(RaciAssignment.matter, RaciAssignment.id)
    ).all()
    grouped: Dict[str, List[RaciOut]] = {}
    for row in rows:
        grouped.setdefault(row.matter, []).append(raci_out(db, row))
    matters: List[RaciMatterOut] = []
    errors: List[str] = []
    for matter, entries in grouped.items():
        accountable = [entry for entry in entries if entry.raci == RaciType.A.value]
        if not accountable:
            errors.append(f"「{matter}」没有 A（唯一负责）")
        elif len(accountable) > 1:
            errors.append(f"「{matter}」有 {len(accountable)} 个 A，必须唯一")
        matters.append(
            RaciMatterOut(
                matter=matter,
                entries=entries,
                has_accountable=len(accountable) == 1,
            )
        )
    return RaciProcessOut(
        process_id=process_id,
        process_code=process.code,
        process_name=process.name,
        matters=matters,
        valid=not errors,
        errors=errors,
    )


def upsert_raci(db: Session, data: Dict) -> RaciAssignment:
    process = require_process(db, data["process_id"])
    role = require_role(db, data["role_id"])
    matter = (data.get("matter") or "").strip()
    if not matter:
        raise RaciError("事项不能为空")
    raci = data.get("raci")
    if raci not in {item.value for item in RaciType}:
        raise RaciError("RACI 只能是 A/R/C/I")

    if raci == RaciType.A.value:
        existing_a = db.scalar(
            select(RaciAssignment).where(
                RaciAssignment.process_id == process.id,
                RaciAssignment.matter == matter,
                RaciAssignment.raci == RaciType.A.value,
                RaciAssignment.role_id != role.id,
            )
        )
        if existing_a is not None:
            other = db.get(GovernanceRole, existing_a.role_id)
            raise RaciError(
                f"「{matter}」已有 A：{other.name if other else existing_a.role_id}，"
                "同一事项只能有一个 A"
            )

    row = db.scalar(
        select(RaciAssignment).where(
            RaciAssignment.process_id == process.id,
            RaciAssignment.matter == matter,
            RaciAssignment.role_id == role.id,
        )
    )
    if row is None:
        row = RaciAssignment(
            process_id=process.id,
            matter=matter,
            role_id=role.id,
            raci=raci,
            note=data.get("note"),
        )
        db.add(row)
    else:
        row.raci = raci
        row.note = data.get("note")
    db.flush()
    return row


def remove_raci(db: Session, row: RaciAssignment) -> None:
    db.delete(row)
    db.flush()


def invalid_processes(db: Session) -> List[RaciProcessOut]:
    process_ids = db.scalars(select(RaciAssignment.process_id).distinct()).all()
    invalid: List[RaciProcessOut] = []
    for process_id in process_ids:
        try:
            result = process_raci(db, process_id)
        except RaciError:
            # 流程已删除但 SQLite 测试库未强制外键时可能留下孤儿 RACI；
            # 启动状态只统计仍然存在的流程。
            continue
        if not result.valid:
            invalid.append(result)
    return invalid
