"""通用响应结构。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def as_columns(data: Dict[str, Any]) -> Dict[str, Any]:
    """把 Pydantic 的 Python 值转成可直接赋给 ORM 列的形式。

    只拆枚举（StrEnum 子类），**保留 date/datetime 对象本身**——
    绝不能对含日期字段的 payload 用 model_dump(mode="json")，
    那会把日期变成字符串再塞进 Date 列，读取时类型就不一致了。
    """
    return {key: (value.value if isinstance(value, Enum) else value) for key, value in data.items()}


class ORMModel(BaseModel):
    """所有出参模型的基类，允许从 ORM 对象直接构造。"""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    total: int = Field(description="符合条件的总条数")
    page: int = 1
    page_size: int = 20
    items: List[T] = []


class Message(BaseModel):
    detail: str
    id: Optional[int] = None


class DeleteResult(BaseModel):
    deleted: int
