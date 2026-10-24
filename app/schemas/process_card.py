"""流程卡：一条流程的跨模块聚合视图。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CardProcessOut(BaseModel):
    id: int
    code: str
    name: str
    level: int
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    department: Optional[str] = None
    health_score: Optional[float] = None


class CardChainItem(BaseModel):
    id: int
    code: str
    name: str
    level: int


class CardObjectiveOut(BaseModel):
    id: int
    code: str
    name: str
    year: int
    target_value: Optional[float] = None
    unit: Optional[str] = None
    status_label: Optional[str] = None


class CardRaciEntryOut(BaseModel):
    raci: str
    raci_label: str
    role_name: Optional[str] = None
    role_type_label: Optional[str] = None


class CardRaciMatterOut(BaseModel):
    matter: str
    has_accountable: bool = False
    entries: List[CardRaciEntryOut] = []


class CardDocumentOut(BaseModel):
    id: int
    code: str
    title: str
    category: str
    category_label: Optional[str] = None
    version_label: Optional[str] = None
    status_label: Optional[str] = None


class CardModelOut(BaseModel):
    status: Optional[str] = None
    status_label: Optional[str] = None
    version: int = 0
    node_count: int = 0
    edge_count: int = 0
    form_count: int = 0
    rule_count: int = 0
    tool_count: int = 0


class CardWorkloadOut(BaseModel):
    verified_standards: int = 0
    demand_hours: float = 0
    actual_hours: float = 0
    capacity_hours: float = 0
    utilization: Optional[float] = None


class CardKpiOut(BaseModel):
    id: int
    code: str
    name: str
    latest_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    status_label: Optional[str] = None


class CardChangeOut(BaseModel):
    id: int
    code: str
    title: str
    status_label: Optional[str] = None
    impact_level_label: Optional[str] = None


class CardImprovementOut(BaseModel):
    id: int
    code: str
    name: str
    status_label: Optional[str] = None
    progress: float = 0
    source_label: Optional[str] = None


class CardFindingOut(BaseModel):
    id: int
    type: str
    type_label: Optional[str] = None
    severity: str
    title: str


class ProcessCardOut(BaseModel):
    process: CardProcessOut
    chain: List[CardChainItem] = []
    objectives: List[CardObjectiveOut] = []
    raci: List[CardRaciMatterOut] = []
    documents: List[CardDocumentOut] = []
    model: CardModelOut = CardModelOut()
    workload: CardWorkloadOut = CardWorkloadOut()
    kpis: List[CardKpiOut] = []
    changes: List[CardChangeOut] = []
    improvements: List[CardImprovementOut] = []
    findings: List[CardFindingOut] = []
    readiness: dict = {}
