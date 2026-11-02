"""治理体系落地项目：只跟踪流程框架边界，不另建一条阶段楼梯。

与改善项目的区别：
- 它跟踪的是公司流程地图有没有划清，不是某一条流程怎么改；
- 复用 Project / ProjectStep，不新建一套项目引擎。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import StepStatus
from app.models.project import Project, ProjectStep

SETUP_STAGE_NAMES = {
    1: "框架边界",
}

# (stage_no, step_no, name, deliverable)
SETUP_STEP_DEFINITIONS: List[tuple[int, str, str, str]] = [
    (1, "1.1", "划清哪些工作进 L1–L3", "带上下级的流程地图"),
    (1, "1.2", "把一条 L3 对上 PCF", "PCF 对应"),
    (1, "1.3", "任命能改这张图的治理角色", "启用且有成员的治理角色"),
]


def next_setup_code(db: Session) -> str:
    prefix = f"SET-{date.today().year}-"
    existing = db.scalars(select(Project.code).where(Project.code.like(f"{prefix}%"))).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def seed_setup_steps(db: Session, project: Project) -> int:
    """生成框架边界的 3 个步骤；最后一步作为里程碑。"""
    last_per_stage = {}
    for stage_no, step_no, _name, _deliverable in SETUP_STEP_DEFINITIONS:
        last_per_stage[stage_no] = step_no
    milestones = set(last_per_stage.values())

    total = len(SETUP_STEP_DEFINITIONS) or 1
    span_days = 0
    if project.start_date and project.end_date:
        span_days = (project.end_date - project.start_date).days

    for index, (stage_no, step_no, name, deliverable) in enumerate(SETUP_STEP_DEFINITIONS):
        due = None
        if span_days > 0 and project.start_date:
            due = project.start_date + timedelta(days=round(span_days * (index + 1) / total))
        db.add(
            ProjectStep(
                project_id=project.id,
                stage_no=stage_no,
                step_no=step_no,
                name=name,
                status=StepStatus.PENDING.value,
                deliverable=deliverable,
                owner=project.owner,
                due_date=due,
                is_milestone=step_no in milestones,
            )
        )
    return len(SETUP_STEP_DEFINITIONS)
