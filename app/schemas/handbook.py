"""员工手册：主体、作业条目、固定依据及双层门禁。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.binding_readiness import BindingGateOut


class HandbookPreviewIn(BaseModel):
    scope: Literal["POSITION", "ROLE"]
    subject_id: int = Field(ge=1)


class HandbookCompileIn(HandbookPreviewIn):
    expected_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class HandbookPreviewOut(BaseModel):
    kind: str = "HANDBOOK"
    rule_version: str = "handbook/v1"
    subject: dict
    entries: list[dict]
    collaboration: list[dict]
    gaps: list[dict]
    binding_gates: list[BindingGateOut]
    can_compile: bool
    can_submit_review: bool
    input_hash: str
    content_hash: str
    preview_html: str
    manifest: dict
    limitations: list[str]


class HandbookSourceRequest(BaseModel):
    document_id: int = Field(ge=1)
    version_id: int = Field(ge=1)
    handbook_version_id: Optional[int] = Field(default=None, ge=1)
