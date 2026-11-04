"""八阶段管理导航：任务、方法、原产物及接收契约的单一定义。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.process import ProcessArch
from app.models.project import Project
from app.models.tool import Tool
from app.models.user import User
from app.services import org_access, process_classification

STAGES = [
    dict(
        key="strategy",
        label="战略对齐",
        task="明确客户结果、战略目标与流程承接。",
        method_codes=["OGSM", "SWOT", "GOAL-TREE"],
        artifact="原战略目标与目标—流程—指标关联",
        verification="核对目标、依据、责任、期限和可测口径；目标关联不证明战略因果。",
        next_key="architecture",
        target={"view": "strategy", "params": {}},
        requires_process=False,
        boundary="方法记录和目标草稿不等于业务批准。",
    ),
    dict(
        key="architecture",
        label="流程架构",
        task="核对三类型、层级、边界及跨流程交接。",
        method_codes=["SIPOC", "RACI"],
        artifact="原企业流程目录、分类依据及边界/交接记录",
        verification="由适用负责人确认分类、起止、客户、输入输出与交接；参照覆盖率不代替业务完整性。",
        next_key="modeling",
        target={"view": "pcf", "params": {}},
        requires_process=False,
        boundary="PCF是参照；企业实际目录经原入口到流程地图，不自动复制三套目录。",
    ),
    dict(
        key="modeling",
        label="建模",
        task="表达并确认所选流程的真实现状与例外路径。",
        method_codes=["BPMN", "SWIMLANE"],
        artifact="原流程模型版本及现场确认依据",
        verification="分别核技术表达、业务真实性和用途；保存不代表已发布或可执行。",
        next_key="analysis",
        target={"view": "designer", "params": {"tab": "model"}},
        requires_process=True,
        boundary="与设计共用一个设计器；本入口不自动创建或冻结As-Is版本。",
    ),
    dict(
        key="analysis",
        label="分析",
        task="从问题和可信样本确认损失、瓶颈与原因。",
        method_codes=["VSM", "FIVE-WHY", "FISHBONE", "PARETO", "PROCESS-MINING"],
        artifact="原分析记录、方法产物、样本与根因证据",
        verification="检查来源、范围、模型、口径和反证；无项目核验不冒用项目专属阶段门。",
        next_key="design",
        target={"view": "monitor", "params": {"tab": "analysis"}},
        requires_process=True,
        boundary="模型估算与实际样本分开；未实现的专业算法不能因模板存在而称可计算。",
    ),
    dict(
        key="design",
        label="设计",
        task="依据分析比较方案、保留控制并验证可实施性。",
        method_codes=["TOBE", "BPR6", "FMEA", "DECISION-MATRIX"],
        artifact="原方案模型版本、选择依据及变更/测试/回退记录",
        verification="核对根因—措施—指标机制、风险和接收条件；设计接收不等于上线或达标。",
        next_key="execution",
        target={"view": "designer", "params": {"tab": "model"}},
        requires_process=True,
        boundary="与建模共用原画布；不自动选择一个未来版本，不另建方案库。",
    ),
    dict(
        key="execution",
        label="执行",
        task="核对发布与运行配置，按真实业务办理任务。",
        method_codes=["GOLIVE", "ROLLBACK", "TRAINING-MATRIX"],
        artifact="原发布版本、运行配置、实例任务及处理记录",
        verification="按适用范围确认人员、表单、分派、时限与恢复准备；上线后另核真实运行。",
        next_key="monitoring",
        target={"view": "execution", "params": {"tab": "tasks"}},
        requires_process=True,
        boundary="当前轻量执行支持范围沿原实现；任务完成不推动改善项目阶段。",
    ),
    dict(
        key="monitoring",
        label="监控度量",
        task="按固定口径查看运行偏差并核对数据质量。",
        method_codes=["BALANCED-SCORE", "CONTROL-CHART", "MINING-CONT"],
        artifact="原KPI/工时/异常数据、来源及处置引用",
        verification="核对公式、取数、窗口、样本和质量，再判断结果与响应；缺数不报零风险。",
        next_key="improvement",
        target={"view": "dashboard", "params": {}},
        requires_process=True,
        boundary="总览仍进驾驶舱，再下钻指标/异常/分析；图表不自动证明运行有效。",
    ),
    dict(
        key="improvement",
        label="变革优化",
        task="选择必要改善、验证采用与效果，固化并持续复盘。",
        method_codes=["PDCA", "DMAIC", "ADKAR", "KAIZEN"],
        artifact="原改善项目、验收、标准/培训与复制记录",
        verification="前后口径与版本可比且有权核验；项目结项不等于改善达标。",
        next_key="strategy",
        target={"view": "projects", "params": {}},
        requires_process=True,
        boundary="原改善项目仍五阶段；无项目可先看问题和组合，不强迫创建项目。",
    ),
]
GOVERNANCE = dict(
    key="governance",
    label="贯穿治理",
    task="核对授权、责任、有效资产与原问题处置。",
    method_codes=["RACI"],
    artifact="原授权规则/例外、任命、受控资产与治理发现",
    verification="分别检查系统权限、业务授权、职责分离和证据；计数不证明组织已落实。",
    next_key="strategy",
    target={"view": "authorization", "params": {}},
    requires_process=False,
    boundary="贯穿八阶段，不编号为第九阶段，不另建任务或审批引擎。",
)


def catalog(db: Session, user: User, process_id=None, project_id=None) -> dict:
    process = None
    project = None
    if process_id is not None:
        process = db.get(ProcessArch, process_id)
        if process is None:
            raise HTTPException(404, "流程不存在")
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
        if process is None or project.process_id != process.id:
            raise HTTPException(422, "项目与所选流程不一致，请重新选择")
    context = {"process": None, "project": None}
    if process is not None:
        resolved = process_classification.resolve_all(list(db.scalars(select(ProcessArch)).all()))[
            process.id
        ]
        context["process"] = {
            "id": process.id,
            "code": process.code,
            "name": process.name,
            "level": process.level,
            **resolved,
        }
    if project is not None:
        context["project"] = {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "current_stage": project.current_stage,
        }
    page_labels = {
        "strategy": "战略目标",
        "pcf": "PCF分类参照",
        "designer": "流程设计器",
        "monitor": "流程分析",
        "execution": "流程执行",
        "dashboard": "运营驾驶舱",
        "projects": "流程项目组合",
        "authorization": "授权矩阵",
    }
    stages = [
        {**row, "target": {**row["target"], "label": page_labels[row["target"]["view"]]}}
        for row in STAGES
    ]
    governance = {
        **GOVERNANCE,
        "target": {**GOVERNANCE["target"], "label": page_labels["authorization"]},
    }
    codes = {code for row in STAGES + [GOVERNANCE] for code in row["method_codes"]}
    methods = {
        row.code: row.name for row in db.scalars(select(Tool).where(Tool.code.in_(codes))).all()
    }
    return {
        "stages": stages,
        "governance": governance,
        "context": context,
        "method_labels": methods,
    }
