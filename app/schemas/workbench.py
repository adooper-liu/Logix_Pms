"""原方法记录的建模、分析、设计作业契约。"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.tool_sheet import ToolSheetOut


class WorkRecordIn(BaseModel):
    kind: Literal["MODELING", "ANALYSIS", "DESIGN"]
    model_version_id: int = Field(ge=1)
    project_id: Optional[int] = Field(default=None, ge=1)
    source_kind: Literal["OBSERVED", "INTERVIEW", "ESTIMATE", "EXERCISE", "UNKNOWN"] = "UNKNOWN"
    customer_result: str = Field(min_length=1, max_length=1000)
    problem: str = Field(min_length=1, max_length=2000)
    findings: str = Field(default="", max_length=4000)
    evidence: str = Field(default="", max_length=4000)
    limitations: str = Field(default="", max_length=2000)
    next_action: str = Field(default="", max_length=2000)
    reviewer_user_id: int = Field(ge=1)
    due_date: Optional[date] = None
    upstream_sheet_id: Optional[int] = Field(default=None, ge=1)
    alternatives: str = Field(default="", max_length=4000)
    choice_reason: str = Field(default="", max_length=2000)
    controls: str = Field(default="", max_length=2000)
    validation: str = Field(default="", max_length=2000)
    rollback: str = Field(default="", max_length=2000)


class WorkReviewIn(BaseModel):
    decision: Literal["ACCEPT", "RETURN", "OBSERVE", "STOP"]
    evidence: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=0)


class WorkbenchOut(BaseModel):
    process_id: int
    can_create: bool = True
    records: list[ToolSheetOut]
    models: list[dict]
    kind_labels: dict
    source_labels: dict
    decision_labels: dict
    reviewers: list[dict]
    limitations: list[str]
