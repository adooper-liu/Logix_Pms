"""启动向导出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StartupActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None


class StartupEvidenceOut(BaseModel):
    """一条出门证据：值是多少、是否必需、当前是否满足。"""

    key: str
    label: str
    value: int
    required: bool
    met: bool


class StartupStepOut(BaseModel):
    key: str
    order: int
    title: str
    goal: str
    input: str
    output: str
    exit_criteria: str
    estimated: str = ""
    minimal: bool = True
    status: str
    status_label: str
    skipped: bool = False
    skip_reason: Optional[str] = None
    skipped_by: Optional[str] = None
    evidence: Dict[str, int] = {}
    evidence_items: List[StartupEvidenceOut] = []
    actions: List[StartupActionOut] = []
    next_hint: Optional[str] = None


class StartupStatusOut(BaseModel):
    total: int
    ready_count: int
    readiness_pct: float
    minimal_total: int
    minimal_ready_count: int
    minimal_readiness_pct: float
    skipped_count: int = 0
    next_step: Optional[str] = None
    next_minimal_step: Optional[str] = None
    steps: List[StartupStepOut] = []


class StartupSkipIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)
