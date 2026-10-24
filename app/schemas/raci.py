"""治理角色与 RACI 出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import GovernanceRoleType, RaciType
from app.schemas.common import ORMModel


class GovernanceMemberOut(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    role_label: Optional[str] = None
    is_primary: bool = False


class GovernanceRoleCreate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    name: str = Field(max_length=120)
    role_type: GovernanceRoleType = GovernanceRoleType.OTHER
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool = True


class GovernanceRoleUpdate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    name: Optional[str] = Field(default=None, max_length=120)
    role_type: Optional[GovernanceRoleType] = None
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GovernanceMemberCreate(BaseModel):
    user_id: int
    is_primary: bool = False


class GovernanceRoleOut(ORMModel):
    id: int
    code: str
    name: str
    role_type: str
    role_type_label: str
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    members: List[GovernanceMemberOut] = []
    member_count: int = 0
    created_at: UtcDateTime
    updated_at: UtcDateTime


class RaciCreate(BaseModel):
    process_id: int
    matter: str = Field(max_length=120)
    role_id: int
    raci: RaciType
    note: Optional[str] = Field(default=None, max_length=200)


class RaciOut(BaseModel):
    id: int
    process_id: int
    matter: str
    role_id: int
    role_name: Optional[str] = None
    role_type_label: Optional[str] = None
    raci: str
    raci_label: str
    note: Optional[str] = None


class RaciMatterOut(BaseModel):
    matter: str
    entries: List[RaciOut] = []
    has_accountable: bool = False


class RaciProcessOut(BaseModel):
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    matters: List[RaciMatterOut] = []
    valid: bool = True
    errors: List[str] = []


class RaciMetaOut(BaseModel):
    role_type_labels: dict
    raci_labels: dict
