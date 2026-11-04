"""薄轮次固定输入/追加动作的显式契约。"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.timeutil import UtcDateTime


class Window(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("窗口开始不能晚于结束")
        return self


class MetricInput(BaseModel):
    kpi_id: int = Field(ge=1)
    source_semantics: str = Field(min_length=1, max_length=1000)
    source_evidence: str = Field(min_length=1, max_length=2000)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    calendar: str = Field(min_length=1, max_length=500)
    filters: str = Field(default="", max_length=1000)
    exclusions: str = Field(default="", max_length=1000)


class SampleInput(BaseModel):
    record_id: int = Field(ge=1)
    source_evidence: str = Field(min_length=1, max_length=2000)
    quality_note: str = Field(min_length=1, max_length=1000)
    contract_hash: Optional[str] = Field(default=None, min_length=64, max_length=64)


class RoundDraft(BaseModel):
    project_id: Optional[int] = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=160)
    scope_note: str = Field(min_length=1, max_length=2000)
    asis_model_version_id: Optional[int] = Field(default=None, ge=1)
    baseline_window: Window
    metrics: list[MetricInput] = Field(min_length=1, max_length=10)
    baseline_samples: list[SampleInput] = Field(min_length=1, max_length=200)


class RoundPatch(RoundDraft):
    expected_revision: int = Field(ge=0)


class RevisionIn(BaseModel):
    expected_revision: int = Field(ge=0)


class BindIn(RevisionIn):
    reference_id: int = Field(ge=1)


class AcceptanceIn(RevisionIn):
    target: str = Field(min_length=1, max_length=2000)
    red_lines: str = Field(min_length=1, max_length=2000)
    observation_rule: str = Field(min_length=1, max_length=2000)
    reviewer_user_id: int = Field(ge=1)
    after_window: Window


class AfterIn(RevisionIn):
    samples: list[SampleInput] = Field(min_length=1, max_length=200)


class RoundOut(BaseModel):
    id: int
    process_id: int
    project_id: Optional[int]
    supersedes_id: Optional[int]
    revision: int
    name: str
    scope_note: str
    asis_model_version_id: Optional[int]
    tobe_model_version_id: Optional[int]
    released_model_version_id: Optional[int]
    metric_contracts: list[dict]
    baseline_window: dict
    baseline_samples: list[dict]
    acceptance_snapshot: Optional[dict]
    after_window: Optional[dict]
    after_samples: Optional[list[dict]]
    model_hashes: dict
    baseline_confirmed_at: Optional[UtcDateTime]
    acceptance_locked_at: Optional[UtcDateTime]
    created_at: UtcDateTime
    verification: list[dict]
    missing: list[str]
    basis_label: str
