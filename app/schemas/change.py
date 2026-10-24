"""变更申请与影响分析出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import ChangeImpactLevel, ChangeType
from app.schemas.common import ORMModel

IMPACT_KEYS = ("people", "systems", "data", "permissions", "controls", "training", "kpis")


class ChangeImpact(BaseModel):
    people: Optional[str] = None
    systems: Optional[str] = None
    data: Optional[str] = None
    permissions: Optional[str] = None
    controls: Optional[str] = None
    training: Optional[str] = None
    kpis: Optional[str] = None


class ChangeRequestCreate(BaseModel):
    process_id: int
    title: str = Field(max_length=160)
    reason: Optional[str] = None
    scope: Optional[str] = None
    change_type: ChangeType = ChangeType.STRUCTURE
    impact_level: ChangeImpactLevel = ChangeImpactLevel.MINOR
    version_label: Optional[str] = Field(default=None, max_length=16)
    impact: ChangeImpact = ChangeImpact()
    test_evidence: Optional[str] = None
    rollback_plan: Optional[str] = None
    effective_date: Optional[date] = None
    emergency: bool = False


class ChangeRequestUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    reason: Optional[str] = None
    scope: Optional[str] = None
    change_type: Optional[ChangeType] = None
    impact_level: Optional[ChangeImpactLevel] = None
    version_label: Optional[str] = Field(default=None, max_length=16)
    impact: Optional[ChangeImpact] = None
    test_evidence: Optional[str] = None
    rollback_plan: Optional[str] = None
    effective_date: Optional[date] = None
    emergency: Optional[bool] = None


class ChangeDecisionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=200)


class ChangeVersionRef(BaseModel):
    id: int
    version: int
    status: str
    published_at: Optional[UtcDateTime] = None


class ChangeRequestOut(ORMModel):
    id: int
    code: str
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    title: str
    reason: Optional[str] = None
    scope: Optional[str] = None
    change_type: str
    change_type_label: str
    impact_level: str
    impact_level_label: str
    version_label: Optional[str] = None
    impact: Dict[str, Optional[str]] = {}
    test_evidence: Optional[str] = None
    rollback_plan: Optional[str] = None
    effective_date: Optional[date] = None
    emergency: bool = False
    status: str
    status_label: str
    decision_note: Optional[str] = None
    requested_by_id: Optional[int] = None
    requested_by_name: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[UtcDateTime] = None
    applied_at: Optional[UtcDateTime] = None
    linked_versions: List[ChangeVersionRef] = []
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ChangeMetaOut(BaseModel):
    change_type_labels: dict
    impact_level_labels: dict
    status_labels: dict
    impact_keys: List[str]
    impact_labels: dict
