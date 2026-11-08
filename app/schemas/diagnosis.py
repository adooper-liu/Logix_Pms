"""诊断证据包契约：来源画像、用途就绪度、模型估算与未决项。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.schemas.asset_graph import ReadinessBlockerOut


class DiagnosisSourceProfileOut(BaseModel):
    claims_total: int = 0
    claims_active: int = 0
    methods: Dict[str, int] = {}
    activity_count: int = 0
    covered_activities: int = 0
    observed_time_claims: int = 0


class DiagnosisUseOut(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str


class DiagnosisReadinessOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    versioned: bool
    metrics: Dict[str, Any] = {}
    source_profile: DiagnosisSourceProfileOut
    uses: List[DiagnosisUseOut] = []
    blockers: List[ReadinessBlockerOut] = []
    warnings: List[str] = []
    can_compile: bool
    next_action: str


class DiagnosisPreviewOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    model_version_id: Optional[int] = None
    model_version: int
    model_status: str
    can_compile: bool
    metrics: Dict[str, Any] = {}
    source_profile: DiagnosisSourceProfileOut
    uses: List[DiagnosisUseOut] = []
    blockers: List[ReadinessBlockerOut] = []
    warnings: List[str] = []
    manifest: Dict[str, Any] = {}
    preview_html: str
    content_hash: str


class DiagnosisInputOut(BaseModel):
    key: str
    label: str
    required: bool
    ready: bool
    detail: str


class DiagnosisR1ReadinessOut(DiagnosisReadinessOut):
    inputs: List[DiagnosisInputOut] = []
    missing_inputs: List[str] = []
    can_compile_draft: bool
    can_submit_review: bool


class DiagnosisR1PreviewOut(DiagnosisPreviewOut):
    inputs: List[DiagnosisInputOut] = []
    missing_inputs: List[str] = []
    can_submit_review: bool
