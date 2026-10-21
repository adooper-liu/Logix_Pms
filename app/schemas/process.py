"""流程地图 / 流程设计器 出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import NodeType
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- 流程架构


class ProcessArchBase(BaseModel):
    code: str = Field(max_length=32, description="流程编码，如 L2-0601")
    name: str = Field(max_length=128)
    level: int = Field(ge=1, le=4, description="1 价值链 / 2 流程类别 / 3 流程 / 4 活动")
    parent_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = Field(
        default=None, description="归属账号 id，权限判断以它为准；不传则按 owner 姓名尝试绑定"
    )
    department: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None

    strategic_importance: float = Field(default=3.0, ge=0, le=5)
    pain_score: float = Field(default=3.0, ge=0, le=5)
    improvement_space: float = Field(default=3.0, ge=0, le=5)
    health_score: Optional[float] = Field(default=None, ge=0, le=100)
    is_improvement_target: bool = False


class ProcessArchCreate(ProcessArchBase):
    pass


class ProcessArchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    department: Optional[str] = None
    description: Optional[str] = None
    strategic_importance: Optional[float] = Field(default=None, ge=0, le=5)
    pain_score: Optional[float] = Field(default=None, ge=0, le=5)
    improvement_space: Optional[float] = Field(default=None, ge=0, le=5)
    health_score: Optional[float] = Field(default=None, ge=0, le=100)
    is_improvement_target: Optional[bool] = None


class ProcessArchOut(ORMModel):
    id: int
    code: str
    name: str
    level: int
    parent_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    department: Optional[str] = None
    description: Optional[str] = None
    strategic_importance: float
    pain_score: float
    improvement_space: float
    health_score: Optional[float] = None
    is_improvement_target: bool
    priority_score: float = Field(default=0, description="战略重要性 × 痛点 × 改善空间")
    heat_level: str = Field(
        default="LOW", description="CRITICAL / HIGH / MEDIUM / LOW，由后端统一判定"
    )


class ProcessArchTree(ProcessArchOut):
    children: List["ProcessArchTree"] = []


ProcessArchTree.model_rebuild()


class HeatmapItem(BaseModel):
    """流程热力条：用于地图上标记"哪里最该改善"。"""

    id: int
    code: str
    name: str
    level: int
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    health_score: Optional[float] = None
    pain_score: float
    strategic_importance: float
    improvement_space: float
    priority_score: float
    project_count: int = 0
    heat_level: str = Field(description="CRITICAL / HIGH / MEDIUM / LOW")


# ---------------------------------------------------------------- 流程设计器


class ProcessNodeIn(BaseModel):
    node_key: str = Field(max_length=64, description="流程内唯一键，连线用它引用")
    name: str = Field(max_length=128)
    node_type: NodeType = NodeType.TASK
    lane: str = Field(default="主流程", max_length=64, description="泳道 = 部门/角色")
    owner_role: Optional[str] = Field(default=None, max_length=64)

    duration_minutes: float = Field(default=0, ge=0, description="作业时间(分钟)")
    wait_minutes: float = Field(default=0, ge=0, description="等待/排队时间(分钟)")
    cost: float = Field(default=0, ge=0)
    rework_rate: float = Field(default=0, ge=0, le=1)
    approval_levels: int = Field(default=0, ge=0, le=10)
    is_value_added: bool = True

    sequence_order: int = 0
    position_x: float = 0
    position_y: float = 0


class ProcessNodeOut(ORMModel):
    id: int
    node_key: str
    name: str
    node_type: str
    lane: str
    owner_role: Optional[str] = None
    duration_minutes: float
    wait_minutes: float
    cost: float
    rework_rate: float
    approval_levels: int
    is_value_added: bool
    sequence_order: int
    position_x: float
    position_y: float


class ProcessEdgeIn(BaseModel):
    source_key: str = Field(max_length=64)
    target_key: str = Field(max_length=64)
    label: Optional[str] = Field(default=None, max_length=64)
    condition: Optional[str] = Field(default=None, max_length=128)
    probability: float = Field(default=1.0, ge=0, le=1)


class ProcessEdgeOut(ORMModel):
    id: int
    source_key: str
    target_key: str
    label: Optional[str] = None
    condition: Optional[str] = None
    probability: float


class ProcessModelIn(BaseModel):
    """覆盖式保存整个流程模型（先删后插），前端一次提交整张图。"""

    nodes: List[ProcessNodeIn]
    edges: List[ProcessEdgeIn] = []
    expected_version: Optional[int] = Field(
        default=None,
        description="客户端拿到的版本号。传了且与服务端不一致时返回 409，防止覆盖别人的修改",
    )


class ProcessModelOut(BaseModel):
    process_id: int
    process_name: Optional[str] = None
    version: int = 0
    updated_at: Optional[UtcDateTime] = None
    nodes: List[ProcessNodeOut] = []
    edges: List[ProcessEdgeOut] = []


class NodeMetric(BaseModel):
    node_key: str
    name: str
    lane: str
    node_type: str
    lead_minutes: float = Field(description="单次执行的作业+等待时长")
    value_minutes: float = Field(description="单次执行的增值作业时长")
    wait_share: float = Field(description="该节点等待时间占自身单次时长的比")
    visit_count: float = Field(description="期望执行次数（含返工重复）")
    weighted_minutes: float = Field(description="对端到端周期的期望贡献 = 执行次数 × 单次时长")
    is_bottleneck: bool = False


class Suggestion(BaseModel):
    code: str = Field(description="规则编码，便于前端做图标/颜色映射")
    severity: str = Field(description="HIGH / MEDIUM / LOW")
    title: str
    detail: str
    related_nodes: List[str] = []
    suggested_tool: Optional[str] = Field(default=None, description="建议调用的工具箱 code")


class DesignMetrics(BaseModel):
    node_count: int
    lane_count: int
    handoff_count: int = Field(description="跨泳道移交次数")
    approval_node_count: int
    total_approval_levels: int

    lead_time_minutes: float = Field(
        description="期望端到端周期。按流转概率与返工概率求期望值，已计入分支与回路"
    )
    linear_lead_time_minutes: float = Field(
        description="线性合计（把每个节点各算一次的旧口径），用于对比期望值的偏差"
    )
    has_branch_or_loop: bool = Field(default=False, description="模型里是否存在分支或回路")
    diverged: bool = Field(default=False, description="模型存在无法退出的环路，测算结果不可信")

    process_time_minutes: float = Field(description="期望作业时间")
    value_added_minutes: float = Field(description="期望增值作业时间")
    wait_minutes: float = Field(description="期望等待时间")
    wait_ratio: float = Field(description="等待占比")

    pce: float = Field(description="流程周期效率 = 增值时间 / 期望端到端周期")
    rework_loss_minutes: float = Field(description="返工造成的额外周期（含等待）")
    rework_work_minutes: float = Field(description="返工造成的额外作业时间（用于折算人力）")
    unit_cost: float = Field(description="单个流程实例的期望执行成本")

    fte_days_saved_per_month: Optional[float] = Field(
        default=None, description="按假设单量折算的可释放人天（仅返工作业时间口径）"
    )


class DesignAnalysis(BaseModel):
    process_id: int
    metrics: DesignMetrics
    nodes: List[NodeMetric]
    suggestions: List[Suggestion]
    recommended_methodology: str = Field(description="基于测算结果给出的方法论建议")
