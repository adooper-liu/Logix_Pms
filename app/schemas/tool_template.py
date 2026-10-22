"""工具预制模板出入参。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import DeliverableStatus, TemplateFormat, TemplateMode
from app.schemas.common import ORMModel


class PlaceholderSpec(BaseModel):
    """模板占位符声明；source 用点路径指向实例上下文，如 project.name。"""

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=64)
    source: str = Field(min_length=1, max_length=64)
    required: bool = False
    format: Optional[str] = Field(default=None, max_length=32)


class PlaceholderValue(PlaceholderSpec):
    value: Optional[str] = None
    missing: bool = False


class ToolTemplateVersionCreate(BaseModel):
    version_label: str = Field(pattern=r"^\d+\.\d+\.\d+$", description="语义化版本，如 1.0.0")
    note: Optional[str] = None
    placeholders: List[PlaceholderSpec] = []
    valid_from: Optional[date] = None
    base_version_id: Optional[int] = None


class ToolTemplateVersionOut(ORMModel):
    id: int
    template_id: int
    version_label: str
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
    placeholders: List[PlaceholderSpec] = []
    base_version_id: Optional[int] = None
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[UtcDateTime] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    created_at: Optional[UtcDateTime] = None


class ToolTemplateCreate(BaseModel):
    tool_code: str = Field(min_length=1, max_length=32)
    code: Optional[str] = Field(default=None, description="不传则自动生成 TPL-<tool>-NN")
    name: str = Field(min_length=1, max_length=160)
    format: TemplateFormat
    description: Optional[str] = None
    instructions: Optional[str] = None
    deliverable_definition_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = Field(default=None, description="NULL 表示集团通用")
    review_date: Optional[date] = None
    is_default: bool = False


class ToolTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None
    instructions: Optional[str] = None
    deliverable_definition_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    review_date: Optional[date] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class ToolTemplateOut(ORMModel):
    id: int
    tool_code: str
    tool_name: Optional[str] = None
    stage_no: Optional[int] = None
    code: str
    name: str
    format: str
    format_label: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    deliverable_definition_id: Optional[int] = None
    deliverable_definition_name: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    scope_org_code: Optional[str] = None
    scope_org_name: Optional[str] = None
    scope_label: Optional[str] = None
    review_date: Optional[date] = None
    review_overdue: bool = False
    is_default: bool = False
    is_active: bool = True
    current_version_id: Optional[int] = None
    current_version: Optional[ToolTemplateVersionOut] = None
    effective_version: Optional[ToolTemplateVersionOut] = None
    version_count: int = 0
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class ToolTemplateDetail(ToolTemplateOut):
    versions: List[ToolTemplateVersionOut] = []


class ToolTemplateVersionTransition(BaseModel):
    status: DeliverableStatus
    note: Optional[str] = None


class TemplateUseRequest(BaseModel):
    mode: TemplateMode = TemplateMode.LINK
    project_id: Optional[int] = None
    deliverable_instance_id: Optional[int] = None
    note: Optional[str] = None


class TemplateCopyRequest(BaseModel):
    deliverable_instance_id: int
    title: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = None


class TemplateUsageOut(ORMModel):
    id: int
    template_id: int
    template_code: Optional[str] = None
    template_version_id: int
    version_label: Optional[str] = None
    mode: str
    mode_label: Optional[str] = None
    project_id: Optional[int] = None
    project_code: Optional[str] = None
    deliverable_instance_id: Optional[int] = None
    deliverable_version_id: Optional[int] = None
    created_by: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[UtcDateTime] = None


class TemplateContext(BaseModel):
    context: Dict[str, Any] = {}
    placeholders: List[PlaceholderValue] = []
    missing_required: List[str] = []


class TemplateMeta(BaseModel):
    format_labels: Dict[str, str]
    status_labels: Dict[str, str]
    mode_labels: Dict[str, str]
    transitions: Dict[str, List[str]]
