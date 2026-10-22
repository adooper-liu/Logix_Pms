"""ORM 模型统一出口。

注意：导入顺序无关紧要，但必须全部被导入，否则 Base.metadata 不完整。
"""

from app.models.baseline import AssetBaseline
from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, ProcessBenchmarkMap
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
    DeliverableStatus,
    DeliverableType,
    ExceptionSeverity,
    ExceptionStatus,
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
    Role,
    ScopeType,
    StepStatus,
    TaskStatus,
    TemplateFormat,
    TemplateMode,
    ToolCategory,
    ToolLevel,
)
from app.models.execution import (
    FormDefinition,
    NodeAssignment,
    ProcessExecutionConfig,
    ProcessInstance,
    ProcessRule,
    ProcessTask,
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
from app.models.org import OrgUnit
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.tool import Tool
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.models.user import AuditLog, User

__all__ = [
    # 模型
    "ProcessArch",
    "ProcessNode",
    "ProcessEdge",
    "ProcessDocument",
    "ProcessDocumentVersion",
    "Project",
    "ProjectStep",
    "WorkflowTemplate",
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
    "ProcessBenchmarkMap",
    "AssetBaseline",
    "GovernanceFinding",
    "ProcessInstance",
    "ProcessTask",
    "FormDefinition",
    "ProcessRule",
    "ProcessExecutionConfig",
    "NodeAssignment",
    "Notification",
    "OrgUnit",
    "IntegrationEndpoint",
    "IntegrationDelivery",
    "InboundWebhook",
    "InboundEvent",
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
]
