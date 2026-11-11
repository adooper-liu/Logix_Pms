"""流程资产生产关系的只读契约：架构关系、证据主张、生成就绪度。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NodeActivityLinkOut(BaseModel):
    id: int
    node_key: str
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    relation: str
    path_condition: str
    coverage: float
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    note: Optional[str] = None
    legacy: bool = Field(
        default=False,
        description="true = 仅来自 process_node.process_arch_id 的兼容指针，尚未在关系表确认",
    )


class ArchitectureNodeOut(BaseModel):
    id: int
    node_key: str
    name: str
    node_type: str
    lane: str
    owner_role: Optional[str] = None
    sequence_order: int
    links: List[NodeActivityLinkOut] = []


class ActivityRelationOut(BaseModel):
    id: int
    source_activity_id: int
    source_code: Optional[str] = None
    source_name: Optional[str] = None
    target_activity_id: int
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    relation: str
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None


class EdgeHandoffOut(BaseModel):
    id: int
    edge_key: str
    from_activity_id: Optional[int] = None
    to_activity_id: Optional[int] = None
    handoff_type: str
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None


class UnmodeledActivityOut(BaseModel):
    id: int
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    reason: str
    source_ref: Optional[str] = None
    confirmed_by_name: Optional[str] = None


class ArchitectureMapOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    versioned: bool
    nodes: List[ArchitectureNodeOut] = []
    links: List[NodeActivityLinkOut] = []
    activity_relations: List[ActivityRelationOut] = []
    handoffs: List[EdgeHandoffOut] = []
    unmodeled: List[UnmodeledActivityOut] = []
    warnings: List[str] = []


class EvidenceClaimTargetOut(BaseModel):
    id: int
    target_type: str
    target_id: int
    model_version_id: Optional[int] = None
    field: Optional[str] = None
    condition: str
    target_code: Optional[str] = None
    target_name: Optional[str] = None


class EvidenceAdjudicationOut(BaseModel):
    id: int
    conflict_group: str
    decision: str
    rationale: str
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    authority_ref: Optional[str] = None


class EvidenceClaimOut(BaseModel):
    id: int
    claim: str
    claim_type: str
    source_type: str
    source_id: Optional[int] = None
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    method: str
    samples: Optional[int] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    coverage: Optional[float] = None
    quality: Dict[str, Any] = {}
    conflict_group: Optional[str] = None
    status: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    query_ref: Optional[Dict[str, Any]] = None
    result_hash: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    targets: List[EvidenceClaimTargetOut] = []
    adjudications: List[EvidenceAdjudicationOut] = []


class EvidenceClaimListOut(BaseModel):
    process_id: int
    claims: List[EvidenceClaimOut] = []
    conflicts: List[str] = Field(default=[], description="存在未裁决冲突的 conflict_group")
    unknown_targets: List[str] = Field(default=[], description="没有任何主张覆盖的目标")
    labels: Dict[str, Dict[str, str]] = {}


class ReadinessBlockerOut(BaseModel):
    code: str
    message: str
    targets: List[str] = []


class AssetReadinessOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    versioned: bool
    metrics: Dict[str, int] = {}
    blockers: List[ReadinessBlockerOut] = []
    warnings: List[str] = []
    can_generate_draft: bool
    can_submit_review: bool
    next_action: str


class AssetPackagePreviewOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    can_generate: bool
    blockers: List[ReadinessBlockerOut] = []
    warnings: List[str] = []
    manifest: Dict[str, Any] = {}
    preview_html: str
    content_hash: str


class AssetPackageOut(BaseModel):
    kind: str = "ASSET_PACKAGE"
    document_id: int
    document_code: str
    document_title: str
    version_id: int
    version_label: str
    status: str
    status_label: str
    manifest: Dict[str, Any] = {}
    preview_html: Optional[str] = None
    content_hash: Optional[str] = None
    download_url: Optional[str] = None
    pdf_available: bool = False
    pdf_url: Optional[str] = None


class AssetPackageTransitionIn(BaseModel):
    status: Literal["DRAFT", "IN_REVIEW", "APPROVED", "EFFECTIVE", "RETIRED"]
    note: Optional[str] = Field(default=None, max_length=200)


class AssetComponentImpactItem(BaseModel):
    document_id: int
    document_code: str
    document_title: str
    version_id: int
    version_label: str
    version_status: str
    version_status_label: str
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    component_type: str
    component_type_label: str
    component_ref_id: Optional[int] = None
    activity_id: Optional[int] = None
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    source_hash: Optional[str] = None
    created_at: Optional[datetime] = None


class AssetImpactOut(BaseModel):
    query: Dict[str, Any] = {}
    total: int
    items: List[AssetComponentImpactItem] = []
    labels: Dict[str, str] = {}


# ------------------------------------------------------------------ 写入契约


class NodeActivityLinkIn(BaseModel):
    node_key: str = Field(max_length=64)
    activity_id: int = Field(ge=1)
    relation: Literal["REALIZES", "PART_OF", "CONTROLS"] = "REALIZES"
    path_condition: Literal["STANDARD", "EXCEPTION", "ALL"] = "ALL"
    coverage: float = Field(default=1.0, ge=0, le=1)
    note: Optional[str] = None


class ActivityRelationIn(BaseModel):
    source_activity_id: int = Field(ge=1)
    target_activity_id: int = Field(ge=1)
    relation: Literal["PART_OF", "DECOMPOSES", "TRIGGERS", "SERVES"]
    note: Optional[str] = None


class EdgeHandoffIn(BaseModel):
    edge_key: str = Field(min_length=3, max_length=160)
    from_activity_id: Optional[int] = Field(default=None, ge=1)
    to_activity_id: Optional[int] = Field(default=None, ge=1)
    handoff_type: Literal["HANDOFF", "NO_HANDOFF"] = "HANDOFF"
    note: Optional[str] = None


class UnmodeledActivityIn(BaseModel):
    activity_id: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    source_ref: Optional[str] = Field(default=None, max_length=200)


class EvidenceClaimTargetIn(BaseModel):
    target_type: Literal["ACTIVITY", "NODE", "EDGE", "TIME_FIELD", "KPI", "RULE", "PROCESS"]
    target_id: int = Field(ge=1)
    model_version_id: Optional[int] = Field(default=None, ge=1)
    field: Optional[str] = Field(default=None, max_length=32)
    condition: Literal["STANDARD", "EXCEPTION", "ALL"] = "ALL"


class EvidenceClaimIn(BaseModel):
    claim: str = Field(min_length=1, max_length=2000)
    claim_type: Literal["EXISTENCE", "SEQUENCE", "TIME", "CONTROL", "ROLE", "RULE", "OUTCOME"]
    source_type: Literal["TOOL_SHEET", "DOCUMENT_VERSION"]
    source_id: int = Field(ge=1)
    source_version: Optional[str] = Field(default=None, max_length=64)
    source_hash: Optional[str] = Field(default=None, max_length=64)
    method: Literal["OBSERVED", "DOCUMENTED", "STATED", "ESTIMATED", "LOGGED", "UNKNOWN"]
    samples: Optional[int] = Field(default=None, ge=0)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    coverage: Optional[float] = Field(default=None, ge=0, le=1)
    quality: Dict[str, Any] = {}
    conflict_group: Optional[str] = Field(default=None, max_length=32)
    # 录入时只允许 OPEN / CONFLICTED；SUPPORTED / ADJUDICATED / EXPIRED 由核验或裁决流程设置。
    status: Literal["OPEN", "CONFLICTED"] = "OPEN"
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    query_ref: Optional[Dict[str, Any]] = None
    result_hash: Optional[str] = Field(default=None, max_length=64)
    targets: List[EvidenceClaimTargetIn] = Field(min_length=1)


class EvidenceAdjudicationIn(BaseModel):
    decision: Literal[
        "ACCEPT_DOCUMENT", "ACCEPT_OBSERVED", "ACCEPT_STATED", "KEEP_CONFLICT", "OTHER"
    ]
    rationale: str = Field(min_length=1, max_length=2000)
    authority_ref: Optional[str] = Field(default=None, max_length=128)
