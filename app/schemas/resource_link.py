"""活动引用既有资源契约。"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime

ResourceType = Literal[
    "FORM", "RULE", "DOCUMENT", "INTEGRATION", "TECH", "RPA", "EQUIPMENT", "MEASURE"
]


class ResourceLinkIn(BaseModel):
    activity_id: int = Field(ge=1)
    resource_type: ResourceType
    ref_id: Optional[int] = Field(default=None, ge=1)
    ref_key: Optional[str] = Field(default=None, max_length=128)
    org_scope: str = Field(default="GLOBAL", max_length=16)
    node_key: Optional[str] = Field(default=None, min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)


class ResourceLinkOut(BaseModel):
    id: int
    activity_id: int
    resource_type: str
    resource_type_label: str
    ref_id: Optional[int]
    ref_key: str
    org_scope: str
    node_key: Optional[str]
    note: Optional[str]
    is_active: bool
    source_valid: bool
    is_record_carrier: bool = False
    source_status: str
    source_label: str
    source_note: str
    created_at: UtcDateTime


class ResourceOptionOut(BaseModel):
    resource_type: str
    resource_type_label: str
    ref_id: int
    ref_key: str
    label: str


class ResourceOptionsOut(BaseModel):
    resource_type_labels: dict
    options: List[ResourceOptionOut]
