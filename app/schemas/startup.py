"""启动向导出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class StartupActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None


class StartupStepOut(BaseModel):
    key: str
    order: int
    title: str
    goal: str
    input: str
    output: str
    exit_criteria: str
    status: str
    status_label: str
    evidence: Dict[str, int] = {}
    actions: List[StartupActionOut] = []
    next_hint: Optional[str] = None


class StartupStatusOut(BaseModel):
    total: int
    ready_count: int
    readiness_pct: float
    next_step: Optional[str] = None
    steps: List[StartupStepOut] = []
