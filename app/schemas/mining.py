"""过程挖掘出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class MiningHandoffOut(BaseModel):
    from_name: str
    to_name: str
    avg_wait_minutes: float
    case_count: int


class MiningVariantOut(BaseModel):
    node_keys: List[str] = []
    node_names: List[str] = []
    instance_count: int = 0
    share_pct: float = 0
    avg_cycle_minutes: Optional[float] = None
    avg_actual_minutes: Optional[float] = None
    avg_wait_minutes: Optional[float] = None
    source: str = "INSTANCE"
    source_label: str = "实例"


class MiningOut(BaseModel):
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    # 纳入变体的事例数，等于各变体次数之和。不含还没有已完成任务的实例。
    instance_total: int = 0
    unsequenced_instances: int = 0
    variant_count: int = 0
    variants: List[MiningVariantOut] = []
    handoffs: List[MiningHandoffOut] = []
