"""流程资产生产关系：ArchiMate-lite 架构关系 + 主张级证据。

设计边界：

- 架构关系是**治理断言**，不是配置。每条关系记录确认人、确认时间与模型版本。
- 节点与活动是**多对多**。`ProcessNode.process_arch_id` 只保留为主活动指针，
  供既有设计器/执行代码兼容；新代码以 `node_activity_link` 为唯一权威来源。
- 证据按**主张**记录，不按节点逐字段记录。一条主张带范围（targets），
  元素默认继承；冲突与例外才单独登记。
- 本模块只定义数据，不在这里计算就绪度或生成资产。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class NodeActivityLink(Base):
    """节点 ↔ 活动。多对多，带关系语义与路径条件。"""

    __tablename__ = "node_activity_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL = 历史回填行，尚未绑定到具体模型版本；服务层会显式提示。
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="CASCADE",
            name="fk_node_activity_link_model_version",
        ),
        nullable=True,
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_node_activity_link_process"),
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(64))
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_node_activity_link_activity"),
        index=True,
    )
    # REALIZES / PART_OF / CONTROLS
    relation: Mapped[str] = mapped_column(String(16), default="REALIZES", index=True)
    # STANDARD / EXCEPTION / ALL
    path_condition: Mapped[str] = mapped_column(String(16), default="ALL")
    coverage: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_node_activity_link_confirmed_by"),
        nullable=True,
    )
    confirmed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    activity: Mapped["ProcessArch"] = relationship(  # noqa: F821
        "ProcessArch", foreign_keys=[activity_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "model_version_id",
            "node_key",
            "activity_id",
            "relation",
            "path_condition",
            name="uq_node_activity_link",
        ),
        Index("ix_node_activity_link_process_node", "process_id", "node_key"),
    )


class ActivityRelation(Base):
    """活动 ↔ 活动：PART_OF / DECOMPOSES / TRIGGERS / SERVES。"""

    __tablename__ = "activity_relation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="CASCADE",
            name="fk_activity_relation_model_version",
        ),
        nullable=True,
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_activity_relation_process"),
        index=True,
    )
    source_activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_activity_relation_source"),
        index=True,
    )
    target_activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_activity_relation_target"),
        index=True,
    )
    relation: Mapped[str] = mapped_column(String(16), index=True)
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_activity_relation_confirmed_by"),
        nullable=True,
    )
    confirmed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "model_version_id",
            "source_activity_id",
            "target_activity_id",
            "relation",
            name="uq_activity_relation",
        ),
    )


class EdgeHandoffLink(Base):
    """连线 ↔ 交接。显式登记 HANDOFF 或 NO_HANDOFF，避免跨部门交接被漏掉。"""

    __tablename__ = "edge_handoff_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="CASCADE",
            name="fk_edge_handoff_link_model_version",
        ),
        nullable=True,
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_edge_handoff_link_process"),
        index=True,
    )
    # 用 source->target 作为稳定键；不引用进程内会变化的 edge.id
    edge_key: Mapped[str] = mapped_column(String(160))
    from_activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_edge_handoff_from"),
        nullable=True,
        index=True,
    )
    to_activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_edge_handoff_to"),
        nullable=True,
        index=True,
    )
    handoff_type: Mapped[str] = mapped_column(String(16), default="HANDOFF")
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_edge_handoff_confirmed_by"),
        nullable=True,
    )
    confirmed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("model_version_id", "edge_key", name="uq_edge_handoff_link"),
    )


class UnmodeledActivity(Base):
    """存在于架构、但没有出现在模型里的活动（电话、邮件、线下签字等）。"""

    __tablename__ = "unmodeled_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="CASCADE",
            name="fk_unmodeled_activity_model_version",
        ),
        nullable=True,
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_unmodeled_activity_process"),
        index=True,
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_unmodeled_activity_activity"),
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_unmodeled_activity_confirmed_by"),
        nullable=True,
    )
    confirmed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("model_version_id", "activity_id", name="uq_unmodeled_activity"),
    )


class EvidenceClaim(Base):
    """一条可检验主张，带来源、方法、样本、窗口、有效期与冲突组。"""

    __tablename__ = "evidence_claim"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_evidence_claim_process"),
        index=True,
    )
    claim: Mapped[str] = mapped_column(Text)
    # EXISTENCE / SEQUENCE / TIME / CONTROL / ROLE / RULE / OUTCOME
    claim_type: Mapped[str] = mapped_column(String(16), index=True)
    # TOOL_SHEET / DOCUMENT_VERSION（v1）；OBSERVATION / LOG_QUERY 后置
    source_type: Mapped[str] = mapped_column(String(24), index=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # OBSERVED / DOCUMENTED / STATED / ESTIMATED / LOGGED / UNKNOWN
    method: Mapped[str] = mapped_column(String(16), index=True)
    samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality: Mapped[Any] = mapped_column(JSON, default=dict)
    conflict_group: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # OPEN / SUPPORTED / CONFLICTED / ADJUDICATED / EXPIRED
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # 日志证据的查询与结果 hash，保证可复算；文档/工具表证据可为空
    query_ref: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_evidence_claim_created_by"),
        nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    targets: Mapped[List["EvidenceClaimTarget"]] = relationship(
        "EvidenceClaimTarget",
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="EvidenceClaimTarget.id",
    )

    __table_args__ = (Index("ix_evidence_claim_process_status", "process_id", "status"),)


class EvidenceClaimTarget(Base):
    """主张覆盖的目标；支持活动、节点、边、时间字段、KPI、规则。"""

    __tablename__ = "evidence_claim_target"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_claim.id", ondelete="CASCADE", name="fk_evidence_target_claim"),
        index=True,
    )
    # ACTIVITY / NODE / EDGE / TIME_FIELD / KPI / RULE
    target_type: Mapped[str] = mapped_column(String(16), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="CASCADE",
            name="fk_evidence_target_model_version",
        ),
        nullable=True,
        index=True,
    )
    field: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # STANDARD / EXCEPTION / ALL
    condition: Mapped[str] = mapped_column(String(16), default="ALL")

    claim: Mapped["EvidenceClaim"] = relationship("EvidenceClaim", back_populates="targets")

    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "target_type",
            "target_id",
            "model_version_id",
            "field",
            "condition",
            name="uq_evidence_claim_target",
        ),
    )


class EvidenceAdjudication(Base):
    """冲突组裁决：保留决定、理由、权限与时间，不覆盖原主张。"""

    __tablename__ = "evidence_adjudication"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conflict_group: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_evidence_adjudication_user"),
        nullable=True,
    )
    decided_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    authority_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
