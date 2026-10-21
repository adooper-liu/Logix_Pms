"""用户与审计相关的出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import Role
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: int
    username: str
    display_name: str
    role: str
    department: Optional[str] = None
    is_active: bool
    last_login_at: Optional[UtcDateTime] = None
    created_at: Optional[UtcDateTime] = None


class LoginResponse(BaseModel):
    token: str
    expires_at: int = Field(description="Unix 时间戳（秒）")
    user: UserOut


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: Role = Role.VIEWER
    department: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[Role] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class AuditOut(ORMModel):
    id: int
    username: str
    display_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    summary: Optional[str] = None
    created_at: UtcDateTime


class AuditPage(BaseModel):
    total: int
    items: List[AuditOut] = []
