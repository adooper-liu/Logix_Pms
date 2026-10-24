"""分级授权矩阵出入参。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import AuthorizationCategory
from app.schemas.common import ORMModel


class AuthorizationMetaOut(BaseModel):
    category_labels: Dict[str, str]
    status_labels: Dict[str, str]
    exception_status_labels: Dict[str, str]
    risk_labels: Dict[str, str]


class AuthorizationRuleCreate(BaseModel):
    title: str = Field(max_length=160)
    matter: str = Field(max_length=160)
    category: AuthorizationCategory
    process_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    risk_level: str = Field(default="MEDIUM", pattern="^(HIGH|MEDIUM|LOW)$")
    amount_limit: Optional[float] = Field(default=None, ge=0)
    impact_scope: Optional[str] = Field(default=None, max_length=160)
    reversibility: Optional[str] = Field(default=None, max_length=160)
    frequency: Optional[str] = Field(default=None, max_length=160)
    approver_role_id: Optional[int] = None
    approver_label: Optional[str] = Field(default=None, max_length=120)
    exception_path: Optional[str] = None
    evidence_required: Optional[str] = None
    document_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    owner_user_id: Optional[int] = None


class AuthorizationRuleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    matter: Optional[str] = Field(default=None, max_length=160)
    category: Optional[AuthorizationCategory] = None
    process_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    risk_level: Optional[str] = Field(default=None, pattern="^(HIGH|MEDIUM|LOW)$")
    amount_limit: Optional[float] = Field(default=None, ge=0)
    impact_scope: Optional[str] = Field(default=None, max_length=160)
    reversibility: Optional[str] = Field(default=None, max_length=160)
    frequency: Optional[str] = Field(default=None, max_length=160)
    approver_role_id: Optional[int] = None
    approver_label: Optional[str] = Field(default=None, max_length=120)
    exception_path: Optional[str] = None
    evidence_required: Optional[str] = None
    document_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    owner_user_id: Optional[int] = None


class AuthorizationRuleOut(ORMModel):
    id: int
    code: str
    title: str
    matter: str
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    category: str
    category_label: Optional[str] = None
    risk_level: str
    risk_level_label: Optional[str] = None
    amount_limit: Optional[float] = None
    impact_scope: Optional[str] = None
    reversibility: Optional[str] = None
    frequency: Optional[str] = None
    approver_role_id: Optional[int] = None
    approver_role_name: Optional[str] = None
    approver_label: Optional[str] = None
    exception_path: Optional[str] = None
    evidence_required: Optional[str] = None
    document_id: Optional[int] = None
    document_code: Optional[str] = None
    document_title: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    version: int
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class AuthorizationExceptionCreate(BaseModel):
    rule_id: int
    title: str = Field(max_length=200)
    reason: str = Field(min_length=1)
    process_id: Optional[int] = None
    scope: Optional[str] = None
    expires_at: Optional[datetime] = None


class AuthorizationDecisionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=400)


class AuthorizationExceptionOut(ORMModel):
    id: int
    code: str
    rule_id: int
    rule_code: Optional[str] = None
    rule_title: Optional[str] = None
    rule_category: Optional[str] = None
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    title: str
    reason: str
    scope: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    requested_by_id: Optional[int] = None
    requested_by_name: Optional[str] = None
    requested_at: UtcDateTime
    decided_by_id: Optional[int] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[UtcDateTime] = None
    decision_note: Optional[str] = None
    expires_at: Optional[UtcDateTime] = None
    created_at: UtcDateTime


class AuthorizationListOut(BaseModel):
    total: int
    items: List[AuthorizationRuleOut] = []
