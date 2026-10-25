"""步骤契约与交付物出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import DeliverableStatus, DeliverableType, ToolLevel
from app.schemas.common import ORMModel
from app.schemas.knowledge import KnowledgeRecommendationOut
from app.schemas.tool_template import ToolTemplateOut

# ---------------------------------------------------------------- 步骤契约


class ToolRefOut(BaseModel):
    code: str
    name: str
    category: str
    category_label: Optional[str] = None
    stage_no: int
    level: str = ToolLevel.RECOMMENDED.value
    level_label: Optional[str] = None


class DeliverableDefinitionOut(ORMModel):
    id: int
    code: str
    name: str
    step_no: str
    type: str
    type_label: Optional[str] = None
    required: bool
    template_ref: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class DeliverableDefinitionCreate(BaseModel):
    step_no: str = Field(description="所属标准步骤，如 2.1")
    code: Optional[str] = Field(default=None, description="不传则自动生成 DLV-<step>-NN")
    name: str = Field(max_length=160)
    type: DeliverableType = DeliverableType.DOCUMENT
    required: bool = True
    template_ref: Optional[str] = Field(default=None, max_length=200)
    acceptance_criteria: Optional[str] = None
    sort_order: int = 0


class DeliverableDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    type: Optional[DeliverableType] = None
    required: Optional[bool] = None
    template_ref: Optional[str] = Field(default=None, max_length=200)
    acceptance_criteria: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class StepContractUpdate(BaseModel):
    inputs: Optional[str] = None
    tool_codes: Optional[List[str]] = Field(
        default=None, description="引用工具箱里的 Tool.code；不存在的编码会被拒绝"
    )
    tool_levels: Optional[Dict[str, ToolLevel]] = Field(
        default=None, description="每个工具的使用要求：REQUIRED / RECOMMENDED / OPTIONAL"
    )
    acceptance_criteria: Optional[str] = None
    owner_role: Optional[str] = Field(default=None, max_length=64)
    decision_gate: Optional[bool] = None


class StepContractOut(BaseModel):
    step_no: str
    step_name: str
    stage_no: int
    inputs: Optional[str] = None
    tool_codes: List[str] = []
    tool_levels: Dict[str, str] = {}
    tools: List[ToolRefOut] = []
    acceptance_criteria: Optional[str] = None
    owner_role: Optional[str] = None
    decision_gate: bool = False
    deliverables: List[DeliverableDefinitionOut] = []
    updated_at: Optional[UtcDateTime] = None


class RecommendedToolOut(BaseModel):
    code: str
    name: str
    category: str
    category_label: Optional[str] = None
    stage_no: int
    level: str
    level_label: str
    templates: List[ToolTemplateOut] = []

    why: Optional[str] = Field(default=None, description="这个工具解决什么问题")
    verification_standard: Optional[str] = Field(default=None, description="怎么判断用对了")
    difficulty: str = "MEDIUM"
    difficulty_label: Optional[str] = None
    typical_duration: Optional[str] = None


class StepRecommendationOut(BaseModel):
    step_no: str
    step_name: str
    stage_no: int
    tools: List[RecommendedToolOut] = []
    deliverable_templates: List[ToolTemplateOut] = Field(
        default=[], description="绑定到本步骤交付物、但工具不在契约工具清单里的模板"
    )
    knowledge: List[KnowledgeRecommendationOut] = Field(
        default=[], description="挂到本步骤/阶段的知识推荐"
    )


# ---------------------------------------------------------------- 交付物版本


class DeliverableVersionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = None
    file_ref: Optional[str] = Field(
        default=None,
        max_length=500,
        description="文件位置（共享盘/文档系统）。二进制上传与对象存储尚未接入",
    )
    file_name: Optional[str] = Field(default=None, max_length=255)
    mime_type: Optional[str] = Field(default=None, max_length=128)
    size_bytes: Optional[int] = Field(default=None, ge=0)
    checksum: Optional[str] = Field(
        default=None, pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256，十六进制"
    )
    base_version_id: Optional[int] = None
    source_document_version_id: Optional[int] = Field(
        default=None, description="基于哪一版流程标准文件产出；必须是已生效版本"
    )
    valid_from: Optional[date] = None


class DeliverableVersionOut(ORMModel):
    id: int
    instance_id: int
    version_no: int
    version_label: str
    status: str
    status_label: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    file_ref: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    storage_backend: Optional[str] = None
    has_file: bool = False
    download_url: Optional[str] = Field(
        default=None, description="已上传文件时的下载地址；外部引用只有 file_ref"
    )
    author: Optional[str] = None
    reviewer: Optional[str] = None
    approver: Optional[str] = None
    approved_at: Optional[UtcDateTime] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    base_version_id: Optional[int] = None
    source_template_version_id: Optional[int] = Field(
        default=None, description="由哪个工具模板版本复制/生成而来"
    )
    source_document_version_id: Optional[int] = Field(
        default=None, description="依据哪一版流程标准文件产出"
    )
    source_document_label: Optional[str] = Field(
        default=None, description="如「PD-L3-032-01 v2.0」"
    )
    created_at: Optional[UtcDateTime] = None


class DeliverableVersionTransition(BaseModel):
    status: DeliverableStatus
    note: Optional[str] = None


# ---------------------------------------------------------------- 交付物实例


class DeliverableInstanceOut(ORMModel):
    id: int
    project_id: int
    project_code: Optional[str] = None
    process_id: Optional[int] = None
    project_step_id: int
    step_no: str
    step_name: str
    definition_id: int
    definition_code: str
    definition_name: str
    type: str
    type_label: Optional[str] = None
    required: bool
    acceptance_criteria: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    current_version_id: Optional[int] = None
    current_version: Optional[DeliverableVersionOut] = None
    version_count: int = 0
    updated_at: Optional[UtcDateTime] = None


class DeliverableInstanceDetail(DeliverableInstanceOut):
    versions: List[DeliverableVersionOut] = []


class DeliverableInstanceUpdate(BaseModel):
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None


class DeliverableSummary(BaseModel):
    total: int
    required_total: int
    effective: int
    in_review: int
    draft: int
    missing: int
    required_missing: int
    completeness_pct: float = Field(description="已生效交付物 / 全部交付物")
    by_status: Dict[str, int] = {}
    status_labels: Dict[str, str] = {}


class DeliverableSyncResult(BaseModel):
    created: int
    total: int


class DeliverableMeta(BaseModel):
    type_labels: Dict[str, str]
    status_labels: Dict[str, str]
    transitions: Dict[str, List[str]]
