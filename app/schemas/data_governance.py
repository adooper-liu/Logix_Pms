"""数据治理出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import DataDomainType, DataFrequency
from app.schemas.common import ORMModel


class DataDomainCreate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: str = Field(max_length=120)
    domain_type: DataDomainType = DataDomainType.OTHER
    org_unit_id: Optional[int] = None
    owner_user_id: Optional[int] = Field(
        default=None, description="数据所有者；不传则按 owner 姓名尝试绑定"
    )
    owner: Optional[str] = Field(default=None, max_length=64)
    steward_user_id: Optional[int] = None
    steward: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    is_active: bool = True


class DataDomainUpdate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: Optional[str] = Field(default=None, max_length=120)
    domain_type: Optional[DataDomainType] = None
    org_unit_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = None
    steward_user_id: Optional[int] = None
    steward: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DataDomainOut(ORMModel):
    id: int
    code: str
    name: str
    domain_type: str
    domain_type_label: str
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    steward_user_id: Optional[int] = None
    steward_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    flow_count: int = 0
    created_at: UtcDateTime
    updated_at: UtcDateTime


class DataFlowCreate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: str = Field(max_length=160)
    domain_id: int
    process_id: Optional[int] = None
    kpi_id: Optional[int] = None
    source_system: Optional[str] = Field(default=None, max_length=80)
    target_system: Optional[str] = Field(default=None, max_length=80)
    frequency: DataFrequency = DataFrequency.DAILY
    primary_key: Optional[str] = Field(default=None, max_length=120)
    field_definitions: Optional[str] = None
    allowed_values: Optional[str] = None
    quality_rule: Optional[str] = None
    purpose: Optional[str] = None
    retention_period: Optional[str] = Field(default=None, max_length=64)
    cross_legal_visibility: Optional[str] = Field(default=None, max_length=160)
    data_subject_rights: Optional[str] = None
    is_active: bool = True


class DataFlowUpdate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: Optional[str] = Field(default=None, max_length=160)
    domain_id: Optional[int] = None
    process_id: Optional[int] = None
    kpi_id: Optional[int] = None
    source_system: Optional[str] = None
    target_system: Optional[str] = None
    frequency: Optional[DataFrequency] = None
    primary_key: Optional[str] = None
    field_definitions: Optional[str] = None
    allowed_values: Optional[str] = None
    quality_rule: Optional[str] = None
    purpose: Optional[str] = None
    retention_period: Optional[str] = None
    cross_legal_visibility: Optional[str] = None
    data_subject_rights: Optional[str] = None
    is_active: Optional[bool] = None


class DataFlowOut(ORMModel):
    id: int
    code: str
    name: str
    domain_id: int
    domain_name: Optional[str] = None
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    kpi_id: Optional[int] = None
    kpi_code: Optional[str] = None
    kpi_name: Optional[str] = None
    source_system: Optional[str] = None
    target_system: Optional[str] = None
    frequency: str
    frequency_label: str
    primary_key: Optional[str] = None
    field_definitions: Optional[str] = None
    allowed_values: Optional[str] = None
    quality_rule: Optional[str] = None
    purpose: Optional[str] = None
    retention_period: Optional[str] = None
    cross_legal_visibility: Optional[str] = None
    data_subject_rights: Optional[str] = None
    is_active: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime


class DataGovernanceMetaOut(BaseModel):
    domain_type_labels: dict
    frequency_labels: dict


class DataGovernanceSummaryOut(BaseModel):
    domains: int = 0
    flows: int = 0
    domains_without_owner: int = 0
    flows_without_quality_rule: int = 0
    flows_without_source: int = 0
    flows_without_primary_key: int = 0


class DataGovernancePage(BaseModel):
    domains: List[DataDomainOut] = []
    flows: List[DataFlowOut] = []
