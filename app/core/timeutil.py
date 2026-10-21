"""时间处理。

全库统一一条规则：**数据库里存的一律是「无时区的 UTC」**，对外序列化时补上 +00:00，
由前端负责换算成本地时间显示。

为什么是「无时区 UTC」而不是带时区的 datetime：SQLite 不保存 tzinfo，
带时区的值取出来会丢偏移量，反而制造"看起来有时区其实没有"的假象。
存 naive UTC + 出口补标记，是跨 SQLite/PostgreSQL 行为最一致的做法。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BeforeValidator, PlainSerializer


def utcnow() -> datetime:
    """当前 UTC 时间（naive）。所有模型的时间戳默认值都用它。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: object) -> Optional[datetime]:
    """入参归一化：带时区的转成 UTC 再去掉时区；不带时区的按 UTC 解释。"""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("不是合法的时间格式")
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _serialize_utc(value: Optional[datetime]) -> Optional[str]:
    """出参补上 +00:00，否则前端无法区分「UTC」和「本地时间」。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# 出参用：序列化成带 +00:00 的 ISO 8601
UtcDateTime = Annotated[
    datetime, PlainSerializer(_serialize_utc, return_type=Optional[str], when_used="json")
]

# 入参用：统一归一化成 naive UTC
UtcDateTimeIn = Annotated[datetime, BeforeValidator(to_utc_naive)]
