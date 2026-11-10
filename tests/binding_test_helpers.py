"""合成角色必须能按原归位规则明确落到岗位。"""

from uuid import uuid4

from sqlalchemy import delete, select

from app.models.raci import GovernanceRole, GovernanceRoleMember
from app.models.user import User


def position_role(db, position_id):
    suffix = uuid4().hex[:8]
    role = GovernanceRole(code="TESTROLE-" + suffix, name="合成有效角色", is_active=True)
    user = User(
        username="test-role-" + suffix,
        display_name="合成成员",
        password_hash="not-a-login",
        position_id=position_id,
    )
    db.add_all([role, user])
    db.flush()
    db.add(GovernanceRoleMember(role_id=role.id, user_id=user.id))
    db.flush()
    return role, user


def remove_position_roles(db, position_ids):
    user_ids = list(
        db.scalars(
            select(User.id).where(
                User.position_id.in_(position_ids), User.username.like("test-role-%")
            )
        )
    )
    role_ids = list(
        db.scalars(
            select(GovernanceRoleMember.role_id).where(GovernanceRoleMember.user_id.in_(user_ids))
        )
    )
    db.execute(delete(GovernanceRoleMember).where(GovernanceRoleMember.role_id.in_(role_ids)))
    db.execute(delete(User).where(User.id.in_(user_ids)))
    db.execute(delete(GovernanceRole).where(GovernanceRole.id.in_(role_ids)))
