"""填写工具模板的出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

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
    source_note: str = ""


class SheetFieldOut(BaseModel):
    key: str
    label: str
    value: str


class ToolSheetCreate(BaseModel):
    process_id: int
    project_id: Optional[int] = None
    step_no: Optional[str] = Field(default=None, max_length=8)
    values: Dict[str, str] = Field(default_factory=dict)
    make_objectives: bool = False


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
