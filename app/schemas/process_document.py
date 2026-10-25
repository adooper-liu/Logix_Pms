"""流程标准配套文件出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import (
    AssetVariationPolicy,
    DeliverableStatus,
    DocumentLevel,
    ProcessDocumentCategory,
)
from app.schemas.common import ORMModel


class ProcessDocumentVersionOut(ORMModel):
    id: int
    document_id: int
    version_label: str
    version_display: str
    status: str
    status_label: Optional[str] = None
    note: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    storage_backend: Optional[str] = None
    has_file: bool = False
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    preview_kind: Optional[str] = None
    base_version_id: Optional[int] = None
    source_deliverable_version_id: Optional[int] = None
    source_label: Optional[str] = Field(
        default=None, description="晋升来源，如「PR-2026-018 · DLV-2.1-01 · R2」"
    )
    source_base_version_id: Optional[int] = None
    source_base_version_display: Optional[str] = Field(
        default=None, description="变体依据的上游标准版本，如 v1.2"
    )
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[UtcDateTime] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    created_at: Optional[UtcDateTime] = None


class ProcessDocumentOut(ORMModel):
    id: int
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    node_key: Optional[str] = Field(default=None, description="关联的 BPMN 节点；NULL=流程级")
    code: str
    title: str
    category: str
    category_label: Optional[str] = None
    description: Optional[str] = None
    level: str = DocumentLevel.PROCESS.value
    level_label: Optional[str] = None
    legal_entity: Optional[str] = None
    plant: Optional[str] = None
    product_family: Optional[str] = None
    language: str = "zh-CN"
    control_points: Optional[str] = None
    exception_terms: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = Field(default=None, description="NULL 表示集团通用")
    scope_org_code: Optional[str] = None
    scope_org_name: Optional[str] = None
    scope_label: Optional[str] = None
    variation_policy: str = AssetVariationPolicy.PARAMETERIZED.value
    variation_policy_label: Optional[str] = None
    variant_of_document_id: Optional[int] = None
    variant_of_code: Optional[str] = None
    variant_base_version_id: Optional[int] = None
    variant_base_version_display: Optional[str] = None
    is_active: bool = True
    current_version_id: Optional[int] = None
    current_version: Optional[ProcessDocumentVersionOut] = None
    effective_version: Optional[ProcessDocumentVersionOut] = None
    version_count: int = 0
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class ProcessDocumentDetail(ProcessDocumentOut):
    versions: List[ProcessDocumentVersionOut] = []


class ProcessDocumentCreate(BaseModel):
    process_id: int
    node_key: Optional[str] = Field(default=None, max_length=64, description="关联活动节点")
    code: Optional[str] = Field(default=None, description="不传则自动生成 PD-<流程编码>-NN")
    title: str = Field(min_length=1, max_length=200)
    category: ProcessDocumentCategory = ProcessDocumentCategory.SOP
    description: Optional[str] = None
    level: DocumentLevel = DocumentLevel.PROCESS
    legal_entity: Optional[str] = Field(default=None, max_length=128)
    plant: Optional[str] = Field(default=None, max_length=128)
    product_family: Optional[str] = Field(default=None, max_length=128)
    language: str = Field(default="zh-CN", max_length=16)
    control_points: Optional[str] = None
    exception_terms: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = Field(default=None, description="NULL 表示集团通用")
    variation_policy: AssetVariationPolicy = AssetVariationPolicy.PARAMETERIZED
    variant_of_document_id: Optional[int] = Field(
        default=None, description="基于哪份上级/集团标准建立本地变体"
    )


class ProcessDocumentUpdate(BaseModel):
    node_key: Optional[str] = Field(default=None, max_length=64)
    title: Optional[str] = Field(default=None, max_length=200)
    category: Optional[ProcessDocumentCategory] = None
    description: Optional[str] = None
    level: Optional[DocumentLevel] = None
    legal_entity: Optional[str] = Field(default=None, max_length=128)
    plant: Optional[str] = Field(default=None, max_length=128)
    product_family: Optional[str] = Field(default=None, max_length=128)
    language: Optional[str] = Field(default=None, max_length=16)
    control_points: Optional[str] = None
    exception_terms: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    variation_policy: Optional[AssetVariationPolicy] = None
    is_active: Optional[bool] = None


class ProcessDocumentVersionTransition(BaseModel):
    status: DeliverableStatus
    note: Optional[str] = None


class DocumentCopyRequest(BaseModel):
    deliverable_instance_id: int
    title: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = None


class DocumentPromoteRequest(BaseModel):
    deliverable_version_id: int
    version_label: str = Field(pattern=r"^\d+\.\d+$", description="目标标准版本，如 3.3")
    note: Optional[str] = None


class ProcessDocumentMeta(BaseModel):
    category_labels: Dict[str, str]
    status_labels: Dict[str, str]
    transitions: Dict[str, List[str]]
    variation_policy_labels: Dict[str, str]
    level_labels: Dict[str, str] = {}


class EffectiveDocumentOut(BaseModel):
    """按组织 + 日期解析出的有效标准文件。"""

    document_id: int
    code: str
    title: str
    category: str
    category_label: Optional[str] = None
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    scope_label: str
    variation_policy: str
    variation_policy_label: str
    is_variant: bool = False
    base_document_id: Optional[int] = None
    base_document_code: Optional[str] = None
    base_version_display: Optional[str] = None
    inherited: bool = False
    source_org_code: Optional[str] = None
    source_org_name: Optional[str] = None
    version: ProcessDocumentVersionOut
    explanation: str


class DocumentFieldDiff(BaseModel):
    field: str
    label: str
    base_old: Optional[str] = None
    base_new: Optional[str] = None
    variant: Optional[str] = None


class VariantImpactOut(BaseModel):
    document_id: int
    code: str
    title: str
    org_unit_id: Optional[int] = None
    scope_label: Optional[str] = None
    variation_policy_label: Optional[str] = None
    current_version: Optional[ProcessDocumentVersionOut] = None
    base_old_version_display: Optional[str] = None
    base_new_version_display: Optional[str] = None
    status: str
    status_label: str
    requires_reapproval: bool = True
    changed_fields: List[DocumentFieldDiff] = []


class DeliverableReferenceOut(BaseModel):
    deliverable_version_id: int
    project_id: int
    project_code: Optional[str] = None
    definition_code: Optional[str] = None
    version_label: str
    status: str
    status_label: Optional[str] = None
    source_version_display: Optional[str] = None
    frozen: bool = True


class DocumentImpactOut(BaseModel):
    document_id: int
    code: str
    title: str
    base_effective_version: ProcessDocumentVersionOut
    variants: List[VariantImpactOut] = []
    project_references: List[DeliverableReferenceOut] = []


class DocumentRebaseRequest(BaseModel):
    base_version_id: int
    acknowledge_major: bool = Field(default=False, description="major 升级必须显式确认需要重新评估")
    note: Optional[str] = None
