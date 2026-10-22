"""资产基线与差异审计出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import BaselineScope
from app.schemas.common import ORMModel


class BaselineItem(BaseModel):
    kind: str  # document / template
    id: int
    code: str
    title: str
    version_id: int
    version_display: str
    status: Optional[str] = None
    checksum: Optional[str] = None
    scope_label: Optional[str] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    type_label: Optional[str] = Field(default=None, description="标准文件为变体策略，模板为格式")
    definition_code: Optional[str] = None


class BaselineOut(ORMModel):
    id: int
    code: str
    name: str
    scope: str
    scope_label: Optional[str] = None
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    note: Optional[str] = None
    item_count: int = 0
    created_by: Optional[str] = None
    created_at: Optional[UtcDateTime] = None


class BaselineDetail(BaselineOut):
    items: List[BaselineItem] = []


class BaselineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scope: BaselineScope = BaselineScope.ALL
    process_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    note: Optional[str] = None


class BaselineDiffItem(BaseModel):
    kind: str
    id: int
    code: str
    title: str
    status: str  # UNCHANGED / CHANGED / ADDED / REMOVED
    status_label: str
    old_version_display: Optional[str] = None
    new_version_display: Optional[str] = None
    scope_label: Optional[str] = None


class BaselineDiff(BaseModel):
    baseline_id: int
    baseline_code: str
    baseline_name: str
    counts: Dict[str, int]
    items: List[BaselineDiffItem] = []


class BaselineMeta(BaseModel):
    scope_labels: Dict[str, str]
    diff_status_labels: Dict[str, str]


class GovernanceStaleVariant(BaseModel):
    document_id: int
    code: str
    title: str
    scope_label: Optional[str] = None
    base_code: Optional[str] = None
    base_now: Optional[str] = None
    base_latest: Optional[str] = None
    status_label: str


class GovernanceFrozenItem(BaseModel):
    deliverable_version_id: int
    project_code: Optional[str] = None
    definition_code: Optional[str] = None
    version_label: str
    source_display: Optional[str] = None
    latest_display: Optional[str] = None


class GovernanceSummary(BaseModel):
    documents_total: int = 0
    documents_effective: int = 0
    documents_without_effective: int = 0
    variants_total: int = 0
    variants_stale: int = 0
    templates_total: int = 0
    templates_effective: int = 0
    template_usage_30d: int = 0
    baselines_total: int = 0
    latest_baseline_code: Optional[str] = None
    latest_baseline_name: Optional[str] = None
    latest_baseline_at: Optional[UtcDateTime] = None
    latest_diff: Dict[str, int] = {}
    processes_total: int = 0
    processes_covered: int = 0
    process_coverage_pct: float = 0.0
    frozen_references: int = 0
    open_findings: int = 0
    findings_by_type: Dict[str, int] = {}
    stale_variants: List[GovernanceStaleVariant] = []
    frozen_items: List[GovernanceFrozenItem] = []


class FindingOut(ORMModel):
    id: int
    type: str
    type_label: Optional[str] = None
    severity: str
    severity_label: Optional[str] = None
    entity_type: str
    entity_id: int
    title: str
    detail: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    detected_at: Optional[UtcDateTime] = None
    last_seen_at: Optional[UtcDateTime] = None
    resolved_at: Optional[UtcDateTime] = None


class FindingUpdate(BaseModel):
    status: str = Field(pattern=r"^(OPEN|IGNORED)$", description="OPEN 重新打开 / IGNORED 忽略")


class AuditScanResult(BaseModel):
    scanned: int = 0
    created: int = 0
    updated: int = 0
    ignored: int = 0
    resolved: int = 0
    notified: int = 0
