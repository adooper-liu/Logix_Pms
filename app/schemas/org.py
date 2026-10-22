"""组织单元出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import OrgUnitType
from app.schemas.common import ORMModel


class OrgUnitOut(ORMModel):
    id: int
    parent_id: Optional[int] = None
    code: str
    name: str
    type: str
    type_label: Optional[str] = None
    path: str = "/"
    description: Optional[str] = None
    is_active: bool = True
    child_count: int = 0


class OrgUnitTree(OrgUnitOut):
    children: List["OrgUnitTree"] = []


OrgUnitTree.model_rebuild()


class OrgUnitCreate(BaseModel):
    parent_id: Optional[int] = None
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    type: OrgUnitType = OrgUnitType.COMPANY
    description: Optional[str] = None


class OrgUnitUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    type: Optional[OrgUnitType] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrgUnitMeta(BaseModel):
    type_labels: Dict[str, str]
