"""原执行配置的准备约定与本人确认，不替代业务授权/运行有效。"""

from typing import Literal

from pydantic import BaseModel, Field


class ReadinessRequirement(BaseModel):
    mode: Literal["REQUIRED", "NOT_APPLICABLE"]
    reason: str = Field(default="", max_length=1000)


class ReadinessIn(BaseModel):
    expected_revision: int = Field(ge=0)
    reviewer_user_id: int = Field(ge=1)
    requirements: dict[str, ReadinessRequirement]
    node_requirements: dict[str, dict[str, ReadinessRequirement]] = Field(default_factory=dict)
    evidence: str = Field(min_length=1, max_length=4000)
    rollback_note: str = Field(min_length=1, max_length=2000)


class ReadinessConfirm(BaseModel):
    expected_revision: int = Field(ge=0)
    decision: Literal["ACCEPT", "RETURN"]
    evidence: str = Field(min_length=1, max_length=2000)


class ReadinessOut(BaseModel):
    process_id: int
    published_model_version_id: int | None = None
    revision: int = 0
    readiness: dict | None = None
    confirmed: bool = False
    state_label: str
    missing: list[str]
    fingerprint: str
    limitations: list[str]
    reviewers: list[dict]
    facts: dict[str, bool]
    nodes: list[dict]
    requirement_labels: dict[str, str]
    mode_labels: dict[str, str]
    decision_labels: dict[str, str]
