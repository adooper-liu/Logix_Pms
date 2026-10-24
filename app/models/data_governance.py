"""数据治理最小集：数据域与数据流登记。

不替代 DAMA/主数据平台，只回答三个问题：
- 这个数据域谁负责、谁管质量；
- 数据从哪个系统来、主键是什么、多久提取一次；
- 有哪些质量规则、保留期与跨法人可见性约束。
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
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class DataDomain(Base):
    __tablename__ = "data_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    domain_type: Mapped[str] = mapped_column(
        String(24), default="OTHER", server_default="OTHER", index=True
    )
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_data_domain_org"),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_data_domain_owner"),
        nullable=True,
        index=True,
    )
    steward_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_data_domain_steward"),
        nullable=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    flows: Mapped[List["DataFlow"]] = relationship(
        "DataFlow", back_populates="domain", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_data_domain_type_active", "domain_type", "is_active"),)


class DataFlow(Base):
    __tablename__ = "data_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("data_domain.id", ondelete="CASCADE", name="fk_data_flow_domain"),
        index=True,
    )
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_data_flow_process"),
        nullable=True,
        index=True,
    )
    kpi_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kpi_definition.id", ondelete="SET NULL", name="fk_data_flow_kpi"),
        nullable=True,
        index=True,
    )

    source_system: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    target_system: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    frequency: Mapped[str] = mapped_column(
        String(16), default="DAILY", server_default="DAILY", index=True
    )
    primary_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    field_definitions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retention_period: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cross_legal_visibility: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    data_subject_rights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    domain: Mapped["DataDomain"] = relationship("DataDomain", back_populates="flows")
    process: Mapped[Optional["ProcessArch"]] = relationship("ProcessArch")  # noqa: F821
    kpi: Mapped[Optional["KpiDefinition"]] = relationship("KpiDefinition")  # noqa: F821

    __table_args__ = (Index("ix_data_flow_domain_active", "domain_id", "is_active"),)
