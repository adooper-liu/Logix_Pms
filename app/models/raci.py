"""治理角色与 RACI：把“谁负责、谁执行、谁咨询、谁知会”变成结构化数据。

与系统权限角色（ADMIN/MANAGER/OWNER）分开：
- 系统角色决定“能不能改”；
- 治理角色决定“对哪个流程/事项承担什么责任”。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class GovernanceRole(Base):
    __tablename__ = "governance_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role_type: Mapped[str] = mapped_column(
        String(24), default="OTHER", server_default="OTHER", index=True
    )
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_governance_role_org"),
        nullable=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    members: Mapped[List["GovernanceRoleMember"]] = relationship(
        "GovernanceRoleMember",
        back_populates="role",
        cascade="all, delete-orphan",
        order_by="GovernanceRoleMember.id",
    )

    __table_args__ = (Index("ix_governance_role_type_active", "role_type", "is_active"),)


class GovernanceRoleMember(Base):
    __tablename__ = "governance_role_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("governance_role.id", ondelete="CASCADE", name="fk_role_member_role"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE", name="fk_role_member_user"),
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    role: Mapped["GovernanceRole"] = relationship("GovernanceRole", back_populates="members")
    user: Mapped["User"] = relationship("User")  # noqa: F821

    __table_args__ = (UniqueConstraint("role_id", "user_id", name="uq_role_member_role_user"),)


class RaciAssignment(Base):
    """事项 × 治理角色 × A/R/C/I；同一事项只允许一个 A。"""

    __tablename__ = "raci_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_raci_process"),
        index=True,
    )
    matter: Mapped[str] = mapped_column(String(120), index=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("governance_role.id", ondelete="CASCADE", name="fk_raci_role"),
        index=True,
    )
    raci: Mapped[str] = mapped_column(String(1))
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    process: Mapped["ProcessArch"] = relationship("ProcessArch")  # noqa: F821
    role: Mapped["GovernanceRole"] = relationship("GovernanceRole")

    __table_args__ = (
        UniqueConstraint("process_id", "matter", "role_id", name="uq_raci_process_matter_role"),
        Index("ix_raci_process_matter", "process_id", "matter"),
    )
