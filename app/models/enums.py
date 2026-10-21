"""枚举定义。

统一用 str 混入，落库为可读字符串，便于直接查库和跨库迁移。
"""

from enum import Enum


class Methodology(str, Enum):
    """流程改善方法论。"""

    BPR = "BPR"  # 业务流程重组 —— 根本性、阶跃式
    BPI = "BPI"  # 业务流程优化 —— 渐进式、局部
    LEAN = "LEAN"  # 精益改善 —— 消除浪费、提升流动
    HYBRID = "HYBRID"  # 混合：架构层 BPR + 执行层 BPI + 操作层精益


class ProjectStatus(str, Enum):
    PLANNING = "PLANNING"  # 立项中
    ACTIVE = "ACTIVE"  # 执行中
    ON_HOLD = "ON_HOLD"  # 暂停
    CLOSED = "CLOSED"  # 已结项
    CANCELLED = "CANCELLED"  # 已取消


class ProcessState(str, Enum):
    """立项向导里对流程现状的判断，用于自动匹配方法论。"""

    SEVERE_OUTDATED = "SEVERE_OUTDATED"  # 严重过时、断裂、与战略脱节
    SOUND_BUT_INEFFICIENT = "SOUND_BUT_INEFFICIENT"  # 基本合理但效率不足、局部堵点
    SHOPFLOOR_WASTE = "SHOPFLOOR_WASTE"  # 现场/操作层浪费明显、波动大
    MIXED = "MIXED"  # 混合状态


class ScopeType(str, Enum):
    END_TO_END = "END_TO_END"  # 端到端跨职能
    LOCAL = "LOCAL"  # 单一部门内部
    SHOPFLOOR = "SHOPFLOOR"  # 现场/操作层


class StepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    SKIPPED = "SKIPPED"


class InstanceStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ToolCategory(str, Enum):
    DIAGNOSE = "DIAGNOSE"  # 诊断
    DESIGN = "DESIGN"  # 设计
    DEPLOY = "DEPLOY"  # 落地
    MONITOR = "MONITOR"  # 监控


class NodeType(str, Enum):
    START = "START"
    END = "END"
    TASK = "TASK"  # 作业
    APPROVAL = "APPROVAL"  # 审批
    WAIT = "WAIT"  # 等待/排队
    DECISION = "DECISION"  # 判断分支
    HANDOFF = "HANDOFF"  # 跨部门移交


class KpiDimension(str, Enum):
    EFFICIENCY = "EFFICIENCY"  # 效率
    QUALITY = "QUALITY"  # 质量
    COST = "COST"  # 成本
    FLEXIBILITY = "FLEXIBILITY"  # 灵活性


class KpiDirection(str, Enum):
    HIGHER_BETTER = "HIGHER_BETTER"  # 越大越好（如准时交付率）
    LOWER_BETTER = "LOWER_BETTER"  # 越小越好（如周期、差错率）


class ExceptionSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class KnowledgeType(str, Enum):
    CASE = "CASE"  # 案例
    TEMPLATE = "TEMPLATE"  # 模板
    BEST_PRACTICE = "BEST_PRACTICE"  # 最佳实践
    STANDARD = "STANDARD"  # 标准/制度


class Role(str, Enum):
    """用户角色。"""

    ADMIN = "ADMIN"  # 系统管理员：全部权限，含用户管理
    MANAGER = "MANAGER"  # 流程管理科：全部业务写权限
    OWNER = "OWNER"  # 流程 Owner：只能改自己名下的项目与流程模型
    VIEWER = "VIEWER"  # 只读


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
