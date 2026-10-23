"""对标框架域模型：SCOR / APQC PCF 标准分类与流程映射。

设计要点：公司自有流程架构（process_arch）保持唯一，不复制成两套树。
对标框架以独立分类树存在，通过 `process_benchmark_map` 做多对多映射——
同一个流程可以同时映射到 SCOR 和 APQC，切换框架只是换一棵参照树。
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

    # APQC PCF v8.0 变体元数据：行业、主框架、来源与署名。
    industry: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    base_framework_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "benchmark_framework.id",
            ondelete="SET NULL",
            name="fk_benchmark_framework_base",
        ),
        nullable=True,
        index=True,
    )
    source_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    generated_on: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    base_framework: Mapped[Optional["BenchmarkFramework"]] = relationship(
        "BenchmarkFramework", remote_side="BenchmarkFramework.id"
    )

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
    # 稳定的外部键：APQC 的 PCF ID。跨版本/行业变体关联必须用它，
    # 不能用 code（Hierarchy ID），后者会因行业元素插入而漂移。
    external_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # 中文原名；没有中文译名时为空，展示层回落 name_en。
    name_zh: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    level: Mapped[int] = mapped_column(Integer, index=True)  # 1..5
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("benchmark_category.id", ondelete="CASCADE"), nullable=True, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics_available: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    difference_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    change_details: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
        UniqueConstraint(
            "framework_id", "external_id", name="uq_benchmark_category_framework_external"
        ),
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


class BenchmarkMetric(Base):
    """APQC 指标目录，按 PCF ID 关联流程元素。

    同一元素会出现在跨行业/消费品/消费电子多个变体里，因此不挂
    `category_id`，而是用跨变体稳定的 `external_id`；查询时与
    `benchmark_category.external_id` 对齐即可。
    """

    __tablename__ = "benchmark_metric"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(32), index=True)  # PCF ID
    metric_id: Mapped[str] = mapped_column(String(32), index=True)
    metric_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    formula: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("external_id", "metric_id", name="uq_benchmark_metric_element_metric"),
        Index("ix_benchmark_metric_external_metric", "external_id", "metric_id"),
    )
