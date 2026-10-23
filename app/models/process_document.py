"""流程标准配套文件：挂在 L1–L4 流程节点上的 SOP / 表单 / 检查表。

这是 as-designed 层：
- 文档归属流程节点，版本长期有效、可复审；
- 项目交付物是 as-built 层，只保存这次项目的实例，并记录来源文档版本；
- 项目成果要变成标准，走「晋升」生成新的草稿版本，再按同一套审批状态机生效。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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


class ProcessDocument(Base):
    """一条流程节点下的标准文件（逻辑对象，版本在子表）。"""

    __tablename__ = "process_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(24), index=True)  # ProcessDocumentCategory
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 可选的活动级绑定：NULL = 流程级标准；非空 = 仅针对该 BPMN 节点
    node_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # NULL = 集团通用；非空 = 该组织及其下级可见，上级自动继承
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_process_document_org_unit"),
        nullable=True,
        index=True,
    )
    # 变体策略：LOCKED 不允许本地变体；LOCAL_ONLY 只对所属组织可见
    variation_policy: Mapped[str] = mapped_column(
        String(16), default="PARAMETERIZED", server_default="PARAMETERIZED", index=True
    )
    # 本地变体指向它依据的上级/集团标准文件
    variant_of_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_document.id",
            ondelete="SET NULL",
            name="fk_process_document_variant_of",
        ),
        nullable=True,
        index=True,
    )
    # 变体建立时依据的标准版本；不做外键，避免 document ↔ version 建表环
    variant_base_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 当前修订版指针；刻意不加外键，理由同 deliverable_instance
    current_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    process: Mapped["ProcessArch"] = relationship("ProcessArch")  # noqa: F821
    org_unit: Mapped[Optional["OrgUnit"]] = relationship("OrgUnit")  # noqa: F821
    versions: Mapped[List["ProcessDocumentVersion"]] = relationship(
        "ProcessDocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ProcessDocumentVersion.id",
    )

    __table_args__ = (
        Index("ix_process_document_process_category", "process_id", "category"),
        Index("ix_process_document_process_node", "process_id", "node_key"),
    )


class ProcessDocumentVersion(Base):
    """标准文件版本：`v3.2` + 生效日期，状态机与交付物版本一致。"""

    __tablename__ = "process_document_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("process_document.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(20))  # major.minor，展示为 v3.2
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_backend: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    base_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_document_version.id", ondelete="SET NULL"), nullable=True
    )
    # 晋升来源：某项目交付物版本。刻意不加外键，避免 deliverable_version ↔
    # process_document_version 两张表互相引用形成建表环。
    source_deliverable_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )
    # 变体版本依据的上游标准版本；变基生成新草稿时记录，审批生效后回写文档指针
    source_base_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )

    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped["ProcessDocument"] = relationship("ProcessDocument", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("document_id", "version_label", name="uq_process_document_version_label"),
    )
