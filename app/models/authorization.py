"""分级授权矩阵：A/B/C/D 规则与例外台账。

规则回答“谁有权批、按什么维度分级、留什么证据、例外怎么走”；
例外记录回答“这一次为什么破例、谁批的、什么时候失效”。
两者都不替代流程/制度文件，只把授权从 PDF 变成可查询、可审计的数据。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class AuthorizationRule(Base):
    __tablename__ = "authorization_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    matter: Mapped[str] = mapped_column(String(160), index=True)

    # NULL = 集团/组织通用规则；非空 = 只适用于该流程
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_auth_rule_process"),
        nullable=True,
        index=True,
    )
    # NULL = 集团通用；非空 = 只适用于该组织及其下级
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_auth_rule_org"),
        nullable=True,
        index=True,
    )

    category: Mapped[str] = mapped_column(String(4), index=True)  # AuthorizationCategory
    risk_level: Mapped[str] = mapped_column(String(16), default="MEDIUM", server_default="MEDIUM")
    amount_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    impact_scope: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    reversibility: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    frequency: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)

    # 审批角色优先用治理角色主数据；没有对应角色时保留文本标签
    approver_role_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("governance_role.id", ondelete="SET NULL", name="fk_auth_rule_role"),
        nullable=True,
        index=True,
    )
    approver_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    exception_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_required: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 规则依据的制度/SOP；制度文件仍是版本化对象，这里只做引用
    document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_document.id", ondelete="SET NULL", name="fk_auth_rule_document"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT", server_default="DRAFT", index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_auth_rule_owner"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_authorization_rule_status_category", "status", "category"),)


class AuthorizationException(Base):
    __tablename__ = "authorization_exception"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("authorization_rule.id", ondelete="CASCADE", name="fk_auth_exception_rule"),
        index=True,
    )
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_auth_exception_process"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default="REQUESTED", server_default="REQUESTED", index=True
    )
    requested_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_auth_exception_requested_by"),
        nullable=True,
    )
    requested_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    decided_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_auth_exception_decided_by"),
        nullable=True,
    )
    decided_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
