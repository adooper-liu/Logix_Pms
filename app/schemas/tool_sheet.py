"""填写工具模板的出入参。"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class SheetFieldSpec(BaseModel):
    key: str
    label: str
    required: bool = False
    multiline: bool = False
    kind: str = "text"
    options: List[str] = []


class SheetFormOut(BaseModel):
    tool_code: str
    tool_name: str
    writes: str
    allow_keep: bool = False
    fields: List[SheetFieldSpec]
    template_code: Optional[str] = None
    template_name: Optional[str] = None
    template_version: Optional[str] = None
    template_version_id: Optional[int] = None
    source_note: str = ""


class SheetFieldOut(BaseModel):
    key: str
    label: str
    value: str


class HandoffIn(BaseModel):
    receiver_process_id: int = Field(ge=1)
    provider_user_id: int = Field(ge=1)
    receiver_user_id: int = Field(ge=1)
    quality: str = Field(min_length=1, max_length=2000)
    timing: str = Field(min_length=1, max_length=1000)
    exception_path: str = Field(min_length=1, max_length=2000)
    standard_version_id: Optional[int] = Field(default=None, ge=1)


class HandoffConfirm(BaseModel):
    side: Literal["provider", "receiver"]
    decision: Literal["ACCEPT", "REJECT"]
    evidence: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=0)


class ToolSheetCreate(BaseModel):
    process_id: int
    project_id: Optional[int] = None
    step_no: Optional[str] = Field(default=None, max_length=8)
    values: Dict[str, str] = Field(default_factory=dict)
    make_objectives: bool = False
    template_version_id: Optional[int] = Field(default=None, ge=1)
    handoff: Optional[HandoffIn] = None


class ToolSheetOut(BaseModel):
    id: int
    tool_code: str
    tool_name: str
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    project_id: Optional[int] = None
    objective_id: Optional[int] = None
    objective_codes: List[str] = []
    step_no: Optional[str] = None
    title: str
    fields: List[SheetFieldOut] = []
    created_by: Optional[str] = None
    created_at: Optional[UtcDateTime] = None
    template_version_id: Optional[int] = None
    handoff: Optional[dict] = None
    revision: int = 0
    confirmation_label: str = "未记录横向交接"
    work_context: Optional[dict] = None
    review: Optional[dict] = None
    review_label: str = "未记录作业核验"
