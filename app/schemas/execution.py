"""流程执行的出入参。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class ExecutableProcessOut(BaseModel):
    id: int
    code: str
    name: str
    level: int
    node_count: int
    model_version: int = 0


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
    status: str
    status_label: str
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    created_at: UtcDateTime
    claimed_at: Optional[UtcDateTime] = None
    due_at: Optional[UtcDateTime] = None
    completed_at: Optional[UtcDateTime] = None
    completed_by_name: Optional[str] = None
    form_data: Optional[Dict] = None
    form_schema: List[Dict] = []
    form_name: Optional[str] = None
    comment: Optional[str] = None
    next_options: List[NextOption] = []


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
    completed_at: Optional[UtcDateTime] = None
    task_count: int = 0
    open_task_count: int = 0


class InstanceDetail(BaseModel):
    instance: InstanceOut
    tasks: List[TaskOut] = []
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
    is_active: bool = True
    updated_at: Optional[UtcDateTime] = None
