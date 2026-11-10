"""经营绑定 P0 的只读响应；中文标签只在后端维护。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class BindingRefOut(BaseModel):
    kind: str
    id: Optional[int] = None
    label: str
    source: str
    source_label: str
    detail: Optional[str] = None


class BindingFacetOut(BaseModel):
    key: str
    label: str
    status: str
    status_label: str
    source: str
    source_label: str
    refs: List[BindingRefOut] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


class ActivityBindingOut(BaseModel):
    consistency: str = "PENDING_CONFIRM"
    consistency_label: str = "绑定待确认"
    activity_id: int
    activity_code: str
    activity_name: str
    node_keys: List[str]
    facets: List[BindingFacetOut]
    blockers: List[str] = Field(default_factory=list)


class NodeBindingOut(BaseModel):
    node_key: str
    node_name: str
    activity_ids: List[int]
    status: str
    status_label: str
    marker: str
    facets: List[BindingFacetOut]
    blockers: List[str] = Field(default_factory=list)


class ProcessBindingSummaryOut(BaseModel):
    process_id: int
    overall: str
    overall_label: str
    facets_ready: dict
    facets: List[BindingFacetOut]
    conflicts: List[str]
    counts: dict


class ActivityBindingsOut(BaseModel):
    consistency: str = "PENDING_CONFIRM"
    consistency_label: str = "绑定待确认"
    basis_model_version_id: Optional[int] = None
    process_id: int
    model_version_id: Optional[int] = None
    model_version: int
    summary: ProcessBindingSummaryOut
    activities: List[ActivityBindingOut]
    nodes: List[NodeBindingOut]
    limitations: List[str]
