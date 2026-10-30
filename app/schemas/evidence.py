"""项目判断证据链出入参。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel

EvidenceLevel = Literal["L1", "L2", "L3", "L4", "L5"]
EvidenceType = Literal[
    "OBSERVATION",
    "SYSTEM_LOG",
    "BUSINESS_RESULT",
    "INTERVIEW",
    "DOCUMENT",
    "INDUSTRY_BENCHMARK",
]
EvidenceVerdict = Literal["PENDING", "CONFIRMED", "REJECTED", "INCONCLUSIVE"]


class ProjectEvidenceClaimCreate(BaseModel):
    claim: str = Field(min_length=1, max_length=4000)
    counterevidence: str = Field(min_length=1, max_length=4000)
    evidence_level: EvidenceLevel
    evidence_type: EvidenceType
    gate_condition_id: Optional[int] = Field(
        default=None, description="关联的阶段门条件；根因门只认绑定到该条件的证据"
    )
    source_description: str = Field(min_length=1, max_length=4000)
    source_url: Optional[str] = Field(default=None, max_length=500)
    sample_scope: str = Field(min_length=1, max_length=4000)
    finding: str = Field(min_length=1, max_length=4000)

    @field_validator(
        "claim",
        "counterevidence",
        "source_description",
        "sample_scope",
        "finding",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("该字段不能为空")
        return normalized


class ProjectEvidenceClaimDecision(BaseModel):
    verdict: EvidenceVerdict
    decision_note: Optional[str] = Field(default=None, max_length=4000)


class ProjectEvidenceClaimOut(ORMModel):
    id: int
    project_id: int
    claim: str
    counterevidence: str
    evidence_level: str
    evidence_level_label: str
    evidence_type: str
    evidence_type_label: str
    gate_condition_id: Optional[int] = None
    source_description: str
    source_url: Optional[str] = None
    sample_scope: str
    finding: str
    verdict: str
    verdict_label: str
    decision_note: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_by: Optional[str] = None
    decided_by_user_id: Optional[int] = None
    decided_by: Optional[str] = None
    created_at: UtcDateTime
    decided_at: Optional[UtcDateTime] = None


class EvidenceClaimMetaOut(BaseModel):
    evidence_level_labels: dict[str, str]
    evidence_type_labels: dict[str, str]
    verdict_labels: dict[str, str]
