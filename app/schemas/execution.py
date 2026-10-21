"""流程执行的出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

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
