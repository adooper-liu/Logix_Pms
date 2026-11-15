from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class AssignmentUpdate(BaseModel):
    expected_model_version_id: int
    role: Optional[str] = Field(default=None, max_length=16)
    org_unit_id: Optional[int] = None
    default_assignee_user_id: Optional[int] = None
    approver_user_id: Optional[int] = None
    backup_assignee_user_id: Optional[int] = None
    escalation_user_id: Optional[int] = None
    due_hours: Optional[int] = Field(default=None, ge=0)
    escalation_hours: Optional[int] = Field(default=None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class OwnerUpdate(BaseModel):
    expected_model_version_id: int
    owner_user_id: int


class AccountabilityUpdate(BaseModel):
    expected_model_version_id: int
    role_id: int


class AcceptanceCreate(BaseModel):
    model_version_id: int
    node_key: Optional[str] = Field(default=None, max_length=64)
    scope: str = Field(max_length=24)
    subject_user_id: int
    valid_until: Optional[date] = None
    evidence_note: Optional[str] = None


class ReadinessItem(BaseModel):
    code: str
    message: str
    severity: str = "BLOCKER"


class ActivityReadiness(BaseModel):
    node_key: str
    activity_id: Optional[int] = None
    activity_code: Optional[str] = None
    status: str
    evidence_grade: str
    blockers: list[ReadinessItem] = []
    warnings: list[ReadinessItem] = []


class Gate5ReadinessOut(BaseModel):
    process_id: int
    process_code: str
    model_version_id: Optional[int] = None
    model_version: Optional[int] = None
    status: str
    evidence_grade: str
    process_owner: dict
    activities: list[ActivityReadiness] = []
    blockers: list[ReadinessItem] = []
    warnings: list[ReadinessItem] = []
    next_actions: list[str] = []
    configuration_writable: bool = False
    business_accepted: bool = False
