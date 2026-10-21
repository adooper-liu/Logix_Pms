"""标准工作流的实例化与项目进度回算。

放在 service 层，供「新建项目」接口与「种子数据灌库」共用，避免两处逻辑漂移。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.enums import ProjectStatus, StepStatus
from app.models.project import Project, ProjectStep, WorkflowTemplate

STAGE_NAMES: Dict[int, str] = {
    1: "识别与优先级排序",
    2: "诊断与根因分析",
    3: "方案设计与选择",
    4: "试点与推广落地",
    5: "运营监控与持续改进",
}


def seed_project_steps(db: Session, project: Project) -> int:
    """按标准工作流模板为项目生成 24 个步骤实例。

    已推进到的阶段之前的步骤直接标记为 DONE，让看板上的进度一眼可信。
    每个阶段的最后一步标为里程碑，并按项目计划窗口把 due_date 铺开——
    这样甘特图开箱就有数据，不用等人手工填。
    """
    templates = db.scalars(
        select(WorkflowTemplate).order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)
    ).all()
    # 已结项的项目，全部步骤视为完成
    finished = project.status == ProjectStatus.CLOSED.value
    now = utcnow()

    # 每个阶段的最后一步 = 该阶段的决策门（循环结束时留下的是最后一条）
    last_per_stage: Dict[int, str] = {}
    for tpl in templates:
        last_per_stage[tpl.stage_no] = tpl.step_no
    milestone_steps = set(last_per_stage.values())

    total = len(templates) or 1
    span_days = 0
    if project.start_date and project.end_date:
        span_days = (project.end_date - project.start_date).days

    created = 0
    for idx, tpl in enumerate(templates):
        done = finished or tpl.stage_no < project.current_stage
        due = None
        if span_days > 0:
            offset = round(span_days * (idx + 1) / total)
            due = project.start_date + timedelta(days=offset)
        db.add(
            ProjectStep(
                project_id=project.id,
                stage_no=tpl.stage_no,
                step_no=tpl.step_no,
                name=tpl.name,
                status=StepStatus.DONE.value if done else StepStatus.PENDING.value,
                deliverable=tpl.deliverables,
                owner=project.owner,
                due_date=due,
                is_milestone=tpl.step_no in milestone_steps,
                completed_at=now if done else None,
            )
        )
        created += 1
    return created


def recompute_progress(db: Session, project: Project) -> float:
    """按已完成步骤占比回算项目整体进度，并处理阶段推进与结项。"""
    steps: List[ProjectStep] = db.scalars(
        select(ProjectStep).where(ProjectStep.project_id == project.id)
    ).all()
    if not steps:
        project.progress = 0.0
        return 0.0

    done = sum(1 for s in steps if s.status == StepStatus.DONE.value)
    project.progress = round(done / len(steps) * 100, 1)

    # 连续推进：当前阶段全部完成就进入下一阶段
    while project.current_stage < 5:
        stage_steps = [s for s in steps if s.stage_no == project.current_stage]
        if stage_steps and all(s.status == StepStatus.DONE.value for s in stage_steps):
            project.current_stage += 1
        else:
            break

    if project.progress >= 100.0:
        project.status = ProjectStatus.CLOSED.value
    db.flush()
    return project.progress


def count_templates(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0
