"""岗位责任书编译契约。"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.binding_readiness import BindingGateOut
from app.schemas.position_coverage import CoverageGapOut


class JobDescriptionPreviewIn(BaseModel):
    period: Optional[date] = None


class JobDescriptionCompileIn(JobDescriptionPreviewIn):
    expected_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class JobDescriptionPreviewOut(BaseModel):
    kind: str = "JOB_DESCRIPTION"
    rule_version: str = "job-description/v1"
    position: dict
    period: date
    sections: list[dict]
    preview_html: str
    content_hash: str
    input_hash: str
    manifest: dict
    gaps: list[CoverageGapOut]
    can_compile: bool
    can_submit_review: bool
    binding_gates: list[BindingGateOut] = Field(default_factory=list)
    limitations: list[str]
