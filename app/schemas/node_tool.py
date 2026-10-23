"""活动级工具绑定出入参。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ToolLevel
from app.schemas.common import ORMModel


class NodeToolCreate(BaseModel):
    tool_code: str = Field(min_length=1, max_length=32)
    level: ToolLevel = ToolLevel.RECOMMENDED
    note: Optional[str] = Field(default=None, max_length=200)


class NodeToolOut(ORMModel):
    id: int
    process_id: int
    node_key: str
    tool_code: str
    tool_name: Optional[str] = None
    level: str
    level_label: Optional[str] = None
    note: Optional[str] = None
