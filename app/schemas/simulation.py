"""路径模拟出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    start_node_key: Optional[str] = Field(default=None, max_length=64)
    max_paths: int = Field(default=50, ge=1, le=200)


class SimulationPathOut(BaseModel):
    probability: float
    node_keys: List[str] = []
    node_names: List[str] = []
    cycle_minutes: float = 0
    work_minutes: float = 0
    wait_minutes: float = 0
    cost: float = 0


class SimulationOut(BaseModel):
    start_node_keys: List[str] = []
    path_count: int = 0
    returned: int = 0
    total_probability: float = 0
    expected_cycle_minutes: float = 0
    expected_cost: float = 0
    paths: List[SimulationPathOut] = []
