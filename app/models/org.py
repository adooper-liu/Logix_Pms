"""组织单元：集团 → 公司/分公司 → 工厂 → 部门。

标准文件与工具模板用 `org_unit_id` 标范围：
- NULL = 集团通用，所有组织可见；
- 非空 = 该组织及其下级可见，上级组织的标准对下级自动继承。

编码由系统内 ADMIN 维护；后续要接 ERP/HR 时，把同步放在这一层即可。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class OrgUnit(Base):
    __tablename__ = "org_unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16), index=True)  # OrgUnitType
    # 祖先路径，如 /1/3/；用于展示与后续的快速范围查询
    path: Mapped[str] = mapped_column(String(255), default="/", index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    children: Mapped[List["OrgUnit"]] = relationship(
        "OrgUnit",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="OrgUnit.code",
    )
    parent: Mapped[Optional["OrgUnit"]] = relationship(
        "OrgUnit", back_populates="children", remote_side="OrgUnit.id"
    )

    __table_args__ = (Index("ix_org_unit_parent_type", "parent_id", "type"),)
