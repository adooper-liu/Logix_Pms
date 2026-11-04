"""启动向导出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class StartupActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None
    action: Optional[str] = None
    view_params: Dict[str, str] = Field(default_factory=dict)


class StartupEvidenceOut(BaseModel):
    """一条出门证据：值是多少、是否必需、当前是否满足、点开落到哪一页。"""

    key: str
    label: str
    value: int
    required: bool
    met: bool
    view: str
    view_params: Dict[str, str] = Field(default_factory=dict)


class StartupPointOut(BaseModel):
    """框架边界上的一条要点：短标题在左，说明在右。"""

    label: str
    text: str


class StartupStepOut(BaseModel):
    key: str
    order: int
    title: str
    goal: str
    input: str
    output: str
    exit_criteria: str
    points: List[StartupPointOut] = []
    estimated: str = ""
    pilot: bool = False  # 保留字段。框架边界不再有「首次上线」阶段列表。
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
    # 单流程落地汇总：只回答有多少条十层路径在跑
    path_count: int = 0
    path_completed_count: int = 0
    path_avg_layer: float = 0.0
    steps: List[StartupStepOut] = []


class StartupPilotConfirmIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=400)


class StartupSkipIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class CharterIn(BaseModel):
    process_id: int
    purpose: str = Field(min_length=1, max_length=500)
    starts_at: str = Field(min_length=1, max_length=200)
    ends_at: str = Field(min_length=1, max_length=200)
    in_scope: str = Field(min_length=1, max_length=500)
    out_of_scope: str = Field(min_length=1, max_length=500)
    stop_condition: str = Field(min_length=1, max_length=500)
    sponsor_user_id: int


class CharterOut(BaseModel):
    process_id: int
    purpose: str
    starts_at: str
    ends_at: str
    in_scope: str
    out_of_scope: str
    stop_condition: str
    sponsor_user_id: int


class CharterDetails(BaseModel):
    customer: Optional[str] = Field(default=None, max_length=500)
    customer_result: Optional[str] = Field(default=None, max_length=1000)
    objective_id: Optional[int] = Field(default=None, ge=1)
    mandate_version_id: Optional[int] = Field(default=None, ge=1)
    resource_version_id: Optional[int] = Field(default=None, ge=1)
    resource_commitment: Optional[str] = Field(default=None, max_length=2000)
    review_due: Optional[date] = None
    verification_evidence: Optional[str] = Field(default=None, max_length=2000)


class CharterUpdate(CharterIn):
    expected_revision: int = Field(ge=0)
    details: CharterDetails = Field(default_factory=CharterDetails)


class CharterContextOut(BaseModel):
    process_id: int
    process_code: str
    owner_user_id: Optional[int] = None
    owner: Optional[str] = None
    charter: Optional[CharterOut] = None
    details: CharterDetails = Field(default_factory=CharterDetails)
    revision: int = 0
    verification_label: str = "未记录核验依据"
    reference_label: str = "原引用未核定"


class CharterProcessOption(BaseModel):
    id: int
    code: str
    name: str
    has_owner: bool


class CharterUserOption(BaseModel):
    id: int
    display_name: str


class CharterOptionsOut(BaseModel):
    processes: List[CharterProcessOption]
    users: List[CharterUserOption]
    charters: List[CharterOut]
