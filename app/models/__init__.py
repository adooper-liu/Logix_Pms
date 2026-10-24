"""ORM 模型统一出口。

注意：导入顺序无关紧要，但必须全部被导入，否则 Base.metadata 不完整。
"""

from app.models.baseline import AssetBaseline
from app.models.benchmark import (
    BenchmarkCategory,
    BenchmarkFramework,
    BenchmarkMetric,
    ProcessBenchmarkMap,
)
from app.models.change import ProcessChangeRequest
from app.models.data_governance import DataDomain, DataFlow
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
    StepContract,
)
from app.models.enums import (
    AssetVariationPolicy,
    AuditAction,
    BaselineScope,
    ChangeImpactLevel,
    ChangeStatus,
    ChangeType,
    DataDomainType,
    DataFrequency,
    DeliverableStatus,
    DeliverableType,
    ExceptionSeverity,
    ExceptionStatus,
    GovernanceRoleType,
    ImprovementSource,
    InstanceStatus,
    KnowledgeType,
    KpiDimension,
    KpiDirection,
    Methodology,
    NodeType,
    OrgUnitType,
    ProcessDocumentCategory,
    ProcessState,
    ProjectStatus,
    RaciType,
    ReplicationStatus,
    Role,
    ScopeType,
    StepStatus,
    StrategyPeriod,
    StrategyStatus,
    TaskStatus,
    TemplateFormat,
    TemplateMode,
    ToolCategory,
    ToolLevel,
    WorkMeasurementSource,
    WorkMeasurementStatus,
)
from app.models.execution import (
    FormDefinition,
    IdempotencyRecord,
    NodeAssignment,
    ProcessExecutionConfig,
    ProcessInstance,
    ProcessRule,
    ProcessTask,
    ProcessTaskEvent,
    TaskWorklog,
)
from app.models.governance import GovernanceFinding
from app.models.integration import (
    InboundEvent,
    InboundWebhook,
    IntegrationDelivery,
    IntegrationEndpoint,
)
from app.models.knowledge import KnowledgeItem, KnowledgeTag
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.notification import Notification
from app.models.org import OrgUnit, Position
from app.models.process import NodeTool, ProcessArch, ProcessEdge, ProcessModelVersion, ProcessNode
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.sketch import Sketch
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.tool import Tool
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.models.user import AuditLog, User
from app.models.workload import CapacityCalendar, WorkMeasurementStandard

__all__ = [
    # 模型
    "ProcessArch",
    "ProcessModelVersion",
    "ProcessNode",
    "ProcessEdge",
    "NodeTool",
    "ProcessDocument",
    "ProcessDocumentVersion",
    "Project",
    "ProjectStep",
    "WorkflowTemplate",
    "Sketch",
    "Tool",
    "ToolTemplate",
    "ToolTemplateVersion",
    "TemplateUsage",
    "StepContract",
    "DeliverableDefinition",
    "DeliverableInstance",
    "DeliverableVersion",
    "KpiDefinition",
    "KpiRecord",
    "ExceptionEvent",
    "KnowledgeItem",
    "KnowledgeTag",
    "User",
    "AuditLog",
    "BenchmarkFramework",
    "BenchmarkCategory",
    "BenchmarkMetric",
    "ProcessBenchmarkMap",
    "AssetBaseline",
    "GovernanceFinding",
    "ProcessInstance",
    "ProcessTask",
    "ProcessTaskEvent",
    "TaskWorklog",
    "IdempotencyRecord",
    "FormDefinition",
    "ProcessRule",
    "ProcessExecutionConfig",
    "NodeAssignment",
    "Notification",
    "OrgUnit",
    "Position",
    "IntegrationEndpoint",
    "IntegrationDelivery",
    "InboundWebhook",
    "InboundEvent",
    "WorkMeasurementStandard",
    "CapacityCalendar",
    "StrategyObjective",
    "ObjectiveProcessLink",
    "ProcessChangeRequest",
    "GovernanceRole",
    "GovernanceRoleMember",
    "RaciAssignment",
    "DataDomain",
    "DataFlow",
    # 枚举
    "Methodology",
    "ProjectStatus",
    "ProcessState",
    "ProcessDocumentCategory",
    "ScopeType",
    "StepStatus",
    "InstanceStatus",
    "TaskStatus",
    "ToolCategory",
    "NodeType",
    "OrgUnitType",
    "KpiDimension",
    "KpiDirection",
    "ExceptionSeverity",
    "ExceptionStatus",
    "KnowledgeType",
    "Role",
    "AuditAction",
    "AssetVariationPolicy",
    "BaselineScope",
    "DeliverableType",
    "DeliverableStatus",
    "TemplateFormat",
    "TemplateMode",
    "ToolLevel",
    "WorkMeasurementSource",
    "WorkMeasurementStatus",
    "StrategyPeriod",
    "StrategyStatus",
    "ChangeType",
    "ChangeImpactLevel",
    "ChangeStatus",
    "ImprovementSource",
    "ReplicationStatus",
    "GovernanceRoleType",
    "RaciType",
    "DataDomainType",
    "DataFrequency",
]
