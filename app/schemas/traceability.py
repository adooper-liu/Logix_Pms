"""追溯矩阵只读契约：目标 / KPI → L3/L4 → 模型节点 → 资产版本 → 证据。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TraceKpiOut(BaseModel):
    id: int
    code: str
    name: str
    unit: Optional[str] = None
    direction: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    latest_value: Optional[float] = None
    latest_period: Optional[str] = None


class TraceAssetOut(BaseModel):
    document_id: int
    document_code: str
    document_title: str
    version_id: int
    version_label: str
    status: str
    status_label: str
    kind: Optional[str] = None
    kind_label: Optional[str] = None
    model_version: Optional[int] = None


class TraceClaimOut(BaseModel):
    id: int
    claim: str
    method: str
    method_label: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    samples: Optional[int] = None
    conflict_group: Optional[str] = None


class TraceRowOut(BaseModel):
    objective_id: Optional[int] = None
    objective_code: Optional[str] = None
    objective_name: Optional[str] = None
    kpi: Optional[TraceKpiOut] = None
    process_id: int
    process_code: str
    process_name: str
    process_level: int
    process_path: str
    activity_id: Optional[int] = None
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    model_version_id: Optional[int] = None
    model_version: Optional[int] = None
    node_keys: List[str] = []
    assets: List[TraceAssetOut] = []
    claims: List[TraceClaimOut] = []
    gaps: List[str] = []


class TraceOrphanOut(BaseModel):
    kind: str
    id: int
    code: str
    name: str
    reason: str


class TraceabilityOut(BaseModel):
    filters: Dict[str, Any] = {}
    total: int
    rows: List[TraceRowOut] = []
    orphans: List[TraceOrphanOut] = []
    summary: Dict[str, int] = {}
    truncated: bool = False
