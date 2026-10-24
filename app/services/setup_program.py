"""治理体系落地项目：九阶段启动模板。

与 24 步改善项目的区别：
- 它管理的是“体系怎么建起来”，不是“某条流程怎么改”；
- 阶段对应附件 SOP 的 0–8 阶段；
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
    1: "立项定界",
    2: "战略与现状基线",
    3: "流程架构设计",
    4: "制度与授权设计",
    5: "流程/表单/工具设计",
    6: "工作量测量",
    7: "试运行与绩效监测",
    8: "评审与固化",
    9: "改善与复制",
}

# (stage_no, step_no, name, deliverable)
SETUP_STEP_DEFINITIONS: List[tuple[int, str, str, str]] = [
    (1, "1.1", "签署试点章程", "试点章程（范围/非范围/停止条件）"),
    (1, "1.2", "确定试点边界与资源", "范围清单、资源承诺"),
    (1, "1.3", "任命流程 Owner 与数据 Owner", "Owner 名单与联系方式"),
    (2, "2.1", "访谈与流程走查", "访谈记录、现状流程"),
    (2, "2.2", "数据盘点与基线", "基线报告、数据口径说明"),
    (2, "2.3", "形成现状基线报告", "可复核的基线报告"),
    (3, "3.1", "裁剪 PCF 并建立 L1–L3", "L1–L3 架构 V0.1"),
    (3, "3.2", "建立目标—流程—KPI 映射", "目标映射卡"),
    (3, "3.3", "治理委员会评审架构", "架构评审纪要"),
    (4, "4.1", "识别红线与控制点", "风险与控制清单"),
    (4, "4.2", "设计授权矩阵与例外规则", "授权矩阵 V0.1"),
    (4, "4.3", "风险/法务/内控审查", "审查意见与整改记录"),
    (5, "5.1", "绘制 SIPOC 与端到端泳道", "SIPOC、泳道图"),
    (5, "5.2", "设计表单、工具与控制点", "L4 文件包、字段字典"),
    (5, "5.3", "L3 所有者批准 L4 文件包", "批准的 SOP/表单/工具"),
    (6, "6.1", "作业分解与现场观测", "工时观测表、有效样本"),
    (6, "6.2", "宽放与样本评审", "评定/宽放审核记录"),
    (6, "6.3", "发布标准工时卡", "标准工时卡 V0.1"),
    (7, "7.1", "小范围试运行", "试运行记录、异常清单"),
    (7, "7.2", "建立 KPI 看板与异常管理", "KPI 卡、异常台账"),
    (7, "7.3", "形成试运行报告", "试运行报告"),
    (8, "8.1", "门禁评审", "门禁检查清单与结论"),
    (8, "8.2", "培训、权限配置与归档", "培训记录、权限清单"),
    (8, "8.3", "发布 V1.0", "V1.0 发布包"),
    (9, "9.1", "运行 PDCA/DMAIC 改善", "改善项目卡与验证证据"),
    (9, "9.2", "复制适用性评估", "复制评估报告"),
    (9, "9.3", "形成复制资产包", "复制资产包与 FAQ"),
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
    """生成 9 阶段 27 个步骤；每阶段最后一步作为里程碑。"""
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
