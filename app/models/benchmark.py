"""对标框架域模型：SCOR / APQC PCF 标准分类与流程映射。

设计要点：公司自有流程架构（process_arch）保持唯一，不复制成两套树。
对标框架以独立分类树存在，通过 `process_benchmark_map` 做多对多映射——
同一个流程可以同时映射到 SCOR 和 APQC，切换框架只是换一棵参照树。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class BenchmarkFramework(Base):
    """对标框架（SCOR / APQC PCF，后续可扩展其他框架）。"""

    __tablename__ = "benchmark_framework"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[List["BenchmarkCategory"]] = relationship(
        "BenchmarkCategory",
        back_populates="framework",
        cascade="all, delete-orphan",
        order_by="BenchmarkCategory.level, BenchmarkCategory.sort_order, BenchmarkCategory.code",
    )


class BenchmarkCategory(Base):
    """标准框架的 L1–L5 分类节点，编码与官方框架保持一致。"""

    __tablename__ = "benchmark_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    framework_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_framework.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    level: Mapped[int] = mapped_column(Integer, index=True)  # 1..5
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("benchmark_category.id", ondelete="CASCADE"), nullable=True, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    framework: Mapped["BenchmarkFramework"] = relationship(
        "BenchmarkFramework", back_populates="categories"
    )
    children: Mapped[List["BenchmarkCategory"]] = relationship(
        "BenchmarkCategory",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="BenchmarkCategory.sort_order, BenchmarkCategory.code",
    )
    parent: Mapped[Optional["BenchmarkCategory"]] = relationship(
        "BenchmarkCategory", back_populates="children", remote_side="BenchmarkCategory.id"
    )

    __table_args__ = (
        UniqueConstraint("framework_id", "code", name="uq_benchmark_category_framework_code"),
        Index("ix_benchmark_category_framework_level", "framework_id", "level"),
    )


class ProcessBenchmarkMap(Base):
    """公司流程 → 标准分类的映射（多对多，按框架区分）。"""

    __tablename__ = "process_benchmark_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_category.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("process_id", "category_id", name="uq_process_benchmark_map"),
    )
