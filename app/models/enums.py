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


class ProjectType(str, Enum):
    IMPROVEMENT = "IMPROVEMENT"  # 流程改善项目（24 步）
    GOVERNANCE_SETUP = "GOVERNANCE_SETUP"  # 治理体系落地项目（9 阶段）


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
    SUSPENDED = "SUSPENDED"
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


class KpiKind(str, Enum):
    """KPI 定义卡的结果分类（与四维度正交）。

    结果 = 客户/经营结果，过程 = 流程执行信号，健康度 = 治理与数据质量门槛。
    """

    RESULT = "RESULT"
    PROCESS = "PROCESS"
    HEALTH = "HEALTH"


class KpiFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    AD_HOC = "AD_HOC"


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
    DOWNLOAD = "DOWNLOAD"


class DeliverableType(str, Enum):
    """交付物形态。决定前端用什么方式预览/填写，不用文件扩展名判断。"""

    DOCUMENT = "DOCUMENT"  # 方案、制度、SOP
    FORM = "FORM"  # 表单模板
    DIAGRAM = "DIAGRAM"  # 流程图、价值流图、地图
    REPORT = "REPORT"  # 分析/评审报告
    DATA = "DATA"  # 清单、台账、指标表
    DECISION = "DECISION"  # 决策记录、选定方案


class DeliverableStatus(str, Enum):
    """交付物/模板版本状态。

    实例没有版本时是 MISSING；有版本时状态由 service 统一推导。
    版本只追加不覆盖：`DRAFT → IN_REVIEW → APPROVED → EFFECTIVE → SUPERSEDED`，
    任何状态都可以 `RETIRED`（作废），但作废后不能再恢复为现行版。
    """

    MISSING = "MISSING"
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    EFFECTIVE = "EFFECTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class TemplateFormat(str, Enum):
    """工具模板的载体格式。在线模板没有文件，其余格式带文件。"""

    XLSX = "XLSX"
    DOCX = "DOCX"
    PPTX = "PPTX"
    BPMN = "BPMN"
    ONLINE = "ONLINE"
    PDF = "PDF"
    CSV = "CSV"


class TemplateMode(str, Enum):
    """模板调用方式；GENERATE（服务端填充）尚未实现。"""

    DOWNLOAD = "DOWNLOAD"  # 下载副本
    ONLINE = "ONLINE"  # 基于在线模板创建交付物
    GENERATE = "GENERATE"  # 服务端占位符填充
    LINK = "LINK"  # 只读引用查看


class ToolLevel(str, Enum):
    """步骤契约里工具的使用要求。"""

    REQUIRED = "REQUIRED"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"


class WorkMeasurementSource(str, Enum):
    """标准工时的取得方法；不同方法证据强度不同。"""

    TIME_STUDY = "TIME_STUDY"  # 时间研究（秒表/录像）
    WORK_SAMPLING = "WORK_SAMPLING"  # 工作抽样
    PREDETERMINED = "PREDETERMINED"  # 预定时间系统
    ESTIMATE = "ESTIMATE"  # 估算，未经验证


class WorkMeasurementStatus(str, Enum):
    """标准工时状态；只有 VERIFIED 能进入产能与成本口径。"""

    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    RETIRED = "RETIRED"


class StrategyPeriod(str, Enum):
    ANNUAL = "ANNUAL"
    H1 = "H1"
    H2 = "H2"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


class StrategyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChangeType(str, Enum):
    STRUCTURE = "STRUCTURE"
    KPI = "KPI"
    FORM_RULE = "FORM_RULE"
    POLICY = "POLICY"
    OTHER = "OTHER"


class ChangeImpactLevel(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    PATCH = "PATCH"


class ChangeStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"


class ImprovementSource(str, Enum):
    MANUAL = "MANUAL"
    KPI_THRESHOLD = "KPI_THRESHOLD"
    AUDIT_FINDING = "AUDIT_FINDING"
    CUSTOMER_COMPLAINT = "CUSTOMER_COMPLAINT"
    EMPLOYEE_SUGGESTION = "EMPLOYEE_SUGGESTION"
    BENCHMARK_GAP = "BENCHMARK_GAP"
    OTHER = "OTHER"


class ReplicationStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PILOT = "PILOT"
    REPLICATED = "REPLICATED"
    REJECTED = "REJECTED"


class GovernanceRoleType(str, Enum):
    """治理角色类型；与系统权限角色（ADMIN/MANAGER/OWNER）正交。"""

    COMMITTEE = "COMMITTEE"  # 集团流程治理委员会
    ENTERPRISE_OWNER = "ENTERPRISE_OWNER"  # 集团端到端流程所有者
    UNIT_OWNER = "UNIT_OWNER"  # 业务单元/工厂流程所有者
    STEWARD = "STEWARD"  # 流程管理员/管家
    BPM_OFFICE = "BPM_OFFICE"  # BPM / 卓越运营办公室
    DATA_OWNER = "DATA_OWNER"  # 数据所有者/管家
    RISK_LEGAL = "RISK_LEGAL"  # 风险、法务、财务、内控
    OTHER = "OTHER"


class RaciType(str, Enum):
    A = "A"  # 唯一负责
    R = "R"  # 执行
    C = "C"  # 咨询
    I = "I"  # 知会  # noqa: E741


class DataDomainType(str, Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    MATERIAL = "MATERIAL"
    PROJECT = "PROJECT"
    ASSET = "ASSET"
    ORG = "ORG"
    LEGAL = "LEGAL"
    PLANT = "PLANT"
    COST_CENTER = "COST_CENTER"
    KPI = "KPI"
    PROCESS = "PROCESS"
    OTHER = "OTHER"


class DataFrequency(str, Enum):
    REAL_TIME = "REAL_TIME"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    AD_HOC = "AD_HOC"


class ProcessDocumentCategory(str, Enum):
    """流程标准配套文件的分类。"""

    SOP = "SOP"
    FORM = "FORM"
    CHECKLIST = "CHECKLIST"
    TEMPLATE = "TEMPLATE"
    POLICY = "POLICY"
    OTHER = "OTHER"


class OrgUnitType(str, Enum):
    """组织单元类型。编码由系统内维护，后续可接 ERP/HR 同步。"""

    GROUP = "GROUP"  # 集团
    COMPANY = "COMPANY"  # 公司/分公司
    PLANT = "PLANT"  # 工厂
    DEPARTMENT = "DEPARTMENT"  # 部门


class AssetVariationPolicy(str, Enum):
    """流程标准文件/模板的变体策略。

    LOCKED：集团强制，不允许本地变体；
    PARAMETERIZED / EXTENDABLE / OPTIONAL：允许本地变体；
    LOCAL_ONLY：只对所属组织可见，不向下级继承。
    """

    LOCKED = "LOCKED"
    PARAMETERIZED = "PARAMETERIZED"
    EXTENDABLE = "EXTENDABLE"
    OPTIONAL = "OPTIONAL"
    LOCAL_ONLY = "LOCAL_ONLY"


class BaselineScope(str, Enum):
    """基线覆盖范围。"""

    ALL = "ALL"
    PROCESS = "PROCESS"
    ORG = "ORG"
