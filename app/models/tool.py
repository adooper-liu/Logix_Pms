"""方法论工具箱模型。"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tool(Base):
    """一个可落地的流程工具，含 5 步标准操作。"""

    __tablename__ = "tool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    alias: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)  # 英文名/别名

    category: Mapped[str] = mapped_column(
        String(16), index=True
    )  # DIAGNOSE / DESIGN / DEPLOY / MONITOR
    stage_no: Mapped[int] = mapped_column(Integer, index=True)  # 主要适用阶段 1–5

    purpose: Mapped[str] = mapped_column(Text)  # 解决什么问题
    when_to_use: Mapped[str] = mapped_column(Text)  # 什么场景选它
    steps: Mapped[Any] = mapped_column(JSON)  # ["步骤1", ...] 5 步
    template_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 模板/表格指引
    pitfalls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 常见误用

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
