"""Process operating contract API schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class OperatingGateOut(BaseModel):
    key: str
    status: str
    applicability: str
    rigor: str
    evidence_grades: List[str] = []


class ProcessOperatingSummaryOut(BaseModel):
    process_id: int
    cycle_id: Optional[int] = None
    gates: List[OperatingGateOut] = []
    blocking_gates: List[str] = []
    unverified_evidence: List[str] = []
    next_action: str
    can_enter_pilot: bool = False
    sample_only: bool = True
