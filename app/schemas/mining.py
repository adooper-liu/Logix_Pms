"""过程挖掘出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class MiningVariantOut(BaseModel):
    node_keys: List[str] = []
    node_names: List[str] = []
    instance_count: int = 0
    share_pct: float = 0
    avg_cycle_minutes: Optional[float] = None
    avg_actual_minutes: Optional[float] = None


class MiningOut(BaseModel):
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    instance_total: int = 0
    variant_count: int = 0
    variants: List[MiningVariantOut] = []
