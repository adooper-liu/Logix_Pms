"""流程执行的出入参。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import Role
from app.schemas.compensation import CompensationRecordOut


class ExecutableProcessOut(BaseModel):
    id: int
    code: str
    name: str
    level: int
    node_count: int
    model_version: int = 0


class AssigneeOut(BaseModel):
    id: int
    display_name: str
    role: str
    role_label: Optional[str] = None
    department: Optional[str] = None
    org_unit_name: Optional[str] = None


class ExecutionConfigOut(BaseModel):
    process_id: int
    default_task_due_hours: Optional[int] = None
    default_escalation_hours: Optional[int] = None
    default_escalation_user_id: Optional[int] = None
    default_escalation_user_name: Optional[str] = None
    updated_at: Optional[UtcDateTime] = None


class ExecutionConfigUpdate(BaseModel):
    default_task_due_hours: Optional[int] = Field(
        default=None, ge=0, le=8760, description="新任务时限（小时）；null 表示不设时限"
    )
    default_escalation_hours: Optional[int] = Field(
        default=None, ge=0, le=8760, description="到期后再过多少小时升级；null 表示不升级"
    )
    default_escalation_user_id: Optional[int] = Field(
        default=None, description="默认升级处理人；null 表示不自动升级"
    )


class NodeAssignmentOut(BaseModel):
    process_id: int
    node_key: str
    name: str
    node_type: str
    lane: Optional[str] = None
    owner_role: Optional[str] = None
    role: Optional[str] = None
    role_label: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    default_assignee_user_id: Optional[int] = None
    default_assignee_name: Optional[str] = None
    due_hours: Optional[int] = None
    escalation_hours: Optional[int] = None
    escalation_user_id: Optional[int] = None
    escalation_user_name: Optional[str] = None


class NodeAssignmentUpdate(BaseModel):
    process_id: int
    node_key: str
    role: Optional[Role] = None
    org_unit_id: Optional[int] = None
    default_assignee_user_id: Optional[int] = None
    due_hours: Optional[int] = Field(default=None, ge=0, le=8760)
    escalation_hours: Optional[int] = Field(default=None, ge=0, le=8760)
    escalation_user_id: Optional[int] = None


class EscalationScanResult(BaseModel):
    scanned: int = 0
    escalated: int = 0
    skipped: int = 0
    task_ids: List[int] = []


class NextOption(BaseModel):
    node_key: str
    name: str
    label: Optional[str] = None
    condition: Optional[str] = None
    probability: float = 1.0


class TaskOut(BaseModel):
    id: int
    instance_id: int
    instance_code: str
    process_id: Optional[int] = None
    process_name: str
    node_key: str
    name: str
    task_type: str
    task_type_label: str
    lane: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_role_code: Optional[str] = None
    candidate_org_unit_id: Optional[int] = None
    status: str
    status_label: str
    instance_status: Optional[str] = None
    instance_status_label: Optional[str] = None
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    created_at: UtcDateTime
    claimed_at: Optional[UtcDateTime] = None
    due_at: Optional[UtcDateTime] = None
    escalated_at: Optional[UtcDateTime] = None
    escalated_to_user_id: Optional[int] = None
    escalated_to_name: Optional[str] = None
    completed_at: Optional[UtcDateTime] = None
    completed_by_name: Optional[str] = None
    form_data: Optional[Dict] = None
    form_schema: List[Dict] = []
    form_name: Optional[str] = None
    comment: Optional[str] = None
    standard_minutes: float = Field(default=0, description="节点标准作业时间（设计值）")
    actual_minutes: float = Field(default=0, description="已登记的实际工时合计")
    next_options: List[NextOption] = []


class TaskEventOut(BaseModel):
    id: int
    task_id: int
    event_type: str
    event_label: str
    from_status: Optional[str] = None
    from_status_label: Optional[str] = None
    to_status: Optional[str] = None
    to_status_label: Optional[str] = None
    actor_name: Optional[str] = None
    detail: Dict = {}
    created_at: UtcDateTime


class InstanceOut(BaseModel):
    id: int
    code: str
    process_id: Optional[int] = None
    process_name: str
    project_id: Optional[int] = None
    status: str
    status_label: str
    current_node_key: Optional[str] = None
    current_node_name: Optional[str] = None
    definition_version: int = 0
    started_by_name: Optional[str] = None
    started_at: UtcDateTime
    suspended_at: Optional[UtcDateTime] = None
    suspend_reason: Optional[str] = None
    completed_at: Optional[UtcDateTime] = None
    archived_at: Optional[UtcDateTime] = None
    task_count: int = 0
    open_task_count: int = 0


class InstanceSuspendRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class InstanceDetail(BaseModel):
    instance: InstanceOut
    tasks: List[TaskOut] = []
    compensations: List[CompensationRecordOut] = []
    configuration: Optional[Dict] = None
    variables: Optional[Dict] = None


class InstanceStartRequest(BaseModel):
    process_id: int
    project_id: Optional[int] = None
    variables: Optional[Dict] = None
    assignments: Optional[Dict[str, int]] = Field(
        default=None, description="可选：按节点 key 指定处理人 user_id；不传则进入公共任务队列"
    )


class TaskCompleteRequest(BaseModel):
    form_data: Optional[Dict] = None
    variables: Optional[Dict] = Field(default=None, description="合并进实例变量")
    next_node_key: Optional[str] = Field(
        default=None, description="节点有多条出边时必填，指定下一节点"
    )
    comment: Optional[str] = None
    effort_minutes: Optional[float] = Field(
        default=None,
        ge=0,
        le=10080,
        description="本次实际工时（分钟）；填写后会生成一条 HANDLE 工时记录",
    )


class WorklogCreate(BaseModel):
    work_type: str = Field(default="HANDLE", max_length=16)
    effort_minutes: Optional[float] = Field(default=None, ge=0, le=10080)
    started_at: Optional[UtcDateTime] = None
    ended_at: Optional[UtcDateTime] = None
    note: Optional[str] = Field(default=None, max_length=200)


class WorklogOut(BaseModel):
    id: int
    task_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    work_type: str
    work_type_label: str
    started_at: Optional[UtcDateTime] = None
    ended_at: Optional[UtcDateTime] = None
    effort_minutes: float
    note: Optional[str] = None
    created_at: UtcDateTime


class WorkloadSummaryRow(BaseModel):
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    task_count: int = 0
    effort_minutes: float = 0


class WorkloadSummary(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    total_minutes: float = 0
    rows: List[WorkloadSummaryRow] = []


class TaskAssignRequest(BaseModel):
    assignee_user_id: Optional[int] = Field(
        default=None, description="传 null 表示退回公共任务队列"
    )


# ---------------------------------------------------------------- 表单定义


class FormDefinitionCreate(BaseModel):
    process_id: int
    node_key: str = Field(default="", max_length=64, description="空字符串表示流程默认表单")
    name: str = Field(max_length=128)
    fields: List[Dict] = Field(
        default_factory=list,
        description="字段列表，如 {key,label,type,required,options,min,max}",
    )
    is_active: bool = True


class FormDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    fields: Optional[List[Dict]] = None
    is_active: Optional[bool] = None


class FormDefinitionOut(BaseModel):
    id: int
    process_id: int
    node_key: str
    name: str
    fields: List[Dict] = []
    version: int = 1
    is_active: bool = True
    updated_at: Optional[UtcDateTime] = None


# ---------------------------------------------------------------- 分支规则


class RuleCondition(BaseModel):
    field: str
    op: str = Field(
        default="eq",
        description="eq/ne/gt/gte/lt/lte/in/contains/truthy/falsy",
    )
    value: Any = None


class ProcessRuleCreate(BaseModel):
    process_id: int
    node_key: str = Field(max_length=64)
    name: str = Field(max_length=128)
    conditions: List[RuleCondition] = Field(default_factory=list)
    target_node_key: str = Field(max_length=64)
    priority: int = 100
    is_active: bool = True


class ProcessRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    conditions: Optional[List[RuleCondition]] = None
    target_node_key: Optional[str] = Field(default=None, max_length=64)
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class ProcessRuleOut(BaseModel):
    id: int
    process_id: int
    node_key: str
    name: str
    conditions: List[Dict] = []
    target_node_key: str
    priority: int
    version: int = 1
    is_active: bool = True
    updated_at: Optional[UtcDateTime] = None
