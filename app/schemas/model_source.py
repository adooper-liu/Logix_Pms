"""As-Is 来源画像契约：方法覆盖、活动缺口与用途就绪度。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from app.schemas.diagnosis import DiagnosisUseOut


class ActivitySourceCoverageOut(BaseModel):
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    methods: List[str] = []
    claim_ids: List[int] = []
    covered: bool = False


class ModelSourceProfileOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    versioned: bool
    claims_total: int
    claims_active: int
    methods: Dict[str, int] = {}
    source_types: Dict[str, int] = {}
    activity_count: int
    covered_activities: int
    observed_time_claims: int
    activities: List[ActivitySourceCoverageOut] = []
    gaps: List[str] = []
    uses: List[DiagnosisUseOut] = []
    warnings: List[str] = []
    next_action: str
