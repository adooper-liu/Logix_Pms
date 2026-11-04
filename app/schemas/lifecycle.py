"""生命周期任务契约；目录和业务阶段状态分开。"""

from typing import Optional

from pydantic import BaseModel


class LifecycleTarget(BaseModel):
    view: str
    label: str
    params: dict[str, str] = {}


class LifecycleStage(BaseModel):
    key: str
    label: str
    task: str
    method_codes: list[str]
    artifact: str
    verification: str
    next_key: str
    target: LifecycleTarget
    requires_process: bool = False
    boundary: str


class LifecycleContext(BaseModel):
    process: Optional[dict] = None
    project: Optional[dict] = None


class LifecycleOut(BaseModel):
    stages: list[LifecycleStage]
    governance: LifecycleStage
    context: LifecycleContext
    method_labels: dict[str, str]
