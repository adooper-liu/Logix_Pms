"""启动向导出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class StartupActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None
    action: Optional[str] = None


class StartupEvidenceOut(BaseModel):
    """一条出门证据：值是多少、是否必需、当前是否满足、点开落到哪一页。"""

    key: str
    label: str
    value: int
    required: bool
    met: bool
    view: str
    view_params: Dict[str, str] = Field(default_factory=dict)


class StartupStepOut(BaseModel):
    key: str
    order: int
    title: str
    goal: str
    input: str
    output: str
    exit_criteria: str
    estimated: str = ""
    pilot: bool = True  # 是否属于「首次上线」范围（前 8 阶段）；第 9 阶段不阻塞首次上线
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
    pilot_total: int
    pilot_ready_count: int
    pilot_readiness_pct: float
    skipped_count: int = 0
    next_step: Optional[str] = None
    next_pilot_step: Optional[str] = None
    pilot_gate_open: bool = False
    pilot_confirmed: bool = False
    pilot_confirmed_by: Optional[str] = None
    pilot_confirmed_at: Optional[UtcDateTime] = None
    pilot_confirm_note: Optional[str] = None
    pilot_stale: bool = False
    pilot_missing_steps: List[str] = []
    # 单流程落地汇总（B）：不替代九阶段能力门，只回答「有多少条路径在跑」
    path_count: int = 0
    path_completed_count: int = 0
    path_avg_layer: float = 0.0
    steps: List[StartupStepOut] = []


class StartupPilotConfirmIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=400)


class StartupSkipIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)
