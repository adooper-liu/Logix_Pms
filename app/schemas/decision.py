"""决策表出入参。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class DecisionInputSpec(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    label: Optional[str] = None
    type: str = Field(default="string", pattern="^(string|number|boolean)$")


class DecisionOutputSpec(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    label: Optional[str] = None
    type: str = Field(default="string", pattern="^(string|number|boolean)$")


class DecisionRuleIn(BaseModel):
    conditions: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}


class DecisionTableCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]{2,48}$")
    name: str = Field(min_length=1, max_length=160)
    process_id: Optional[int] = None
    node_key: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    hit_policy: str = Field(default="FIRST", pattern="^(FIRST|COLLECT)$")
    inputs: List[DecisionInputSpec] = []
    outputs: List[DecisionOutputSpec] = []
    rules: List[DecisionRuleIn] = []


class DecisionTableUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    process_id: Optional[int] = None
    node_key: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    hit_policy: Optional[str] = Field(default=None, pattern="^(FIRST|COLLECT)$")
    inputs: Optional[List[DecisionInputSpec]] = None
    outputs: Optional[List[DecisionOutputSpec]] = None
    rules: Optional[List[DecisionRuleIn]] = None
    is_active: Optional[bool] = None


class DecisionTableOut(ORMModel):
    id: int
    code: str
    name: str
    process_id: Optional[int] = None
    node_key: Optional[str] = None
    description: Optional[str] = None
    hit_policy: str
    inputs: List[Dict] = []
    outputs: List[Dict] = []
    rules: List[Dict] = []
    version: int = 1
    is_active: bool = True
    updated_at: Optional[UtcDateTime] = None


class DecisionEvaluateIn(BaseModel):
    inputs: Dict[str, Any] = {}


class DecisionEvaluateOut(BaseModel):
    code: str
    hit_policy: str
    matched: bool
    matched_count: int = 0
    outputs: Dict[str, Any] = {}
    matched_rules: List[Dict[str, Any]] = []
