"""岗位主数据出入参。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PositionOut(ORMModel):
    id: int
    code: str
    name: str
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class PositionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool = True


class PositionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
