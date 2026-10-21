"""流程知识库模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class KnowledgeItem(Base):
    """案例 / 模板 / 最佳实践 / 标准制度。"""

    __tablename__ = "knowledge_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[str] = mapped_column(
        String(16), index=True
    )  # CASE / TEMPLATE / BEST_PRACTICE / STANDARD
    methodology: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)

    summary: Mapped[str] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text)

    # 关联对象，便于"从项目沉淀到知识库"
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    tool_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    author: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tag_rows: Mapped[List["KnowledgeTag"]] = relationship(
        "KnowledgeTag",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="KnowledgeTag.id",
    )

    @property
    def tags(self) -> List[str]:
        """标签以关联表为唯一事实来源，这里只是给序列化用的投影。"""
        return [t.tag for t in self.tag_rows]


class KnowledgeTag(Base):
    """知识条目的标签。

    刻意做成关联表而不是 JSON 列：JSON 的包含查询在不同数据库上行为不一致，
    之前的实现被迫在「取出分页结果之后」在内存里过滤，导致筛选结果和 total
    都会随 page_size 变化。规范化之后，筛选和计数都回到 SQL 层，跨库也一致。
    """

    __tablename__ = "knowledge_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_item.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[str] = mapped_column(String(32), index=True)

    item: Mapped["KnowledgeItem"] = relationship("KnowledgeItem", back_populates="tag_rows")

    __table_args__ = (Index("ix_knowledge_tag_item_tag", "knowledge_id", "tag", unique=True),)
