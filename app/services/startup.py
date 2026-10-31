"""启动向导状态：从现有数据自动计算九步 readiness。

这是治理体系落地的唯一阶段口径：
- 每个步骤的“是否就绪”由真实数据推导；
- 治理体系落地项目的 current_stage 直接使用 open stage，不按步骤勾选另推进；
- 改善项目的五阶段仍走阶段门，不读这里的公司级计数。

“首次上线”范围 = S0–S7（8 步，含制度与授权）；S8 改善闭环不阻塞首次上线。
默认首页以 pilot_ready_count 是否达到 pilot_total 为切换门槛。

人工“跳过”只记录“本轮不把现有数据作为就绪证据”，不修改业务对象。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.benchmark import ProcessBenchmarkMap
from app.models.change import ProcessChangeRequest
from app.models.enums import ChangeStatus, WorkMeasurementStatus
from app.models.execution import FormDefinition, ProcessRule, TaskWorklog
from app.models.governance import GovernanceFinding
from app.models.knowledge import KnowledgeItem
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.startup import StartupPilotConfirm, StartupStepSkip
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.schemas.startup import (
    StartupActionOut,
    StartupEvidenceOut,
    StartupStatusOut,
    StartupStepOut,
)
from app.services import audit as audit_service
from app.services import authorization as authorization_service
from app.services import kpi as kpi_service
from app.services import process_document as document_service
from app.services import raci as raci_service
from app.services import workload as workload_service

STEP_DEFINITIONS: List[Dict] = [
    {
        "key": "scope",
        "title": "1. 立项定界",
        "goal": "先别铺开：选一条痛点明确、跨岗位或跨组织、能算清结果的流程，"
        "定一个负责人和一个发起人。",
        "input": "痛点、战略、法人/工厂范围、可用的人和时间。",
        "output": "一页试点章程、负责人/发起人名单、范围与非范围、停止条件。",
        "exit_criteria": "至少一条 L3 已绑定负责人；至少一个治理角色；有发起人。",
        "estimated": "1–2 周",
        "pilot": True,
        "actions": [
            {"label": "去定目标", "view": "strategy"},
            {"label": "去任命角色", "view": "orgs"},
            {"label": "去建试点项目", "view": "projects"},
        ],
        "next_hint": "先在「流程地图」选一条 L3，给它指定负责人；"
        "再到「组织与人员 → 治理角色」确认谁对结果负责。",
    },
    {
        "key": "strategy",
        "title": "2. 战略与现状基线",
        "goal": "说清楚为什么做、承接哪条经营目标、现在基线是多少；"
        "用少量指标衡量，不追求一次定全。",
        "input": "年度经营计划、现状数据、访谈和流程走查记录。",
        "output": "目标卡、现状基线、目标—流程—指标映射。",
        "exit_criteria": "目标有责任人和目标值，有现状基线，并且已经挂到这条流程上。",
        "estimated": "2–4 周",
        "pilot": True,
        "actions": [{"label": "去定目标和基线", "view": "strategy"}],
        "next_hint": "在「战略目标」建一条年度目标，填目标值和现状基线，再挂到试点流程上。",
    },
    {
        "key": "architecture",
        "title": "3. 流程架构设计",
        "goal": "用同一套分类语言把这条流程放进 L1–L3 地图，标出边界、上下游，"
        "并让每个关键事项只有一个负责人。",
        "input": "PCF 分类、现有流程清单、组织边界、关键决策事项。",
        "output": "L1–L3 架构、PCF 映射、RACI 矩阵。",
        "exit_criteria": "L1/L2/L3 都有节点；试点流程能对应到 PCF 分类；每个关键事项恰好一个 A。",
        "estimated": "3–5 周",
        "pilot": True,
        "actions": [
            {"label": "去建流程地图", "view": "map"},
            {"label": "1+3+10 建架构", "view": "map", "action": "start.guidedPcf"},
            {"label": "去看 PCF", "view": "pcf"},
            {"label": "去配权责", "view": "designer"},
        ],
        "next_hint": "在「企业流程地图」补 L1–L3，在「PCF 分类框架」做对标映射，"
        "在「流程设计器 → 权责」保证每个事项唯一 A。",
    },
    {
        "key": "policy",
        "title": "4. 制度与授权设计",
        "goal": "定清楚哪些事必须按制度、谁有权批、例外找谁；规则要能查到人、金额/风险和证据。",
        "input": "风险/合规要求、现有制度、金额/风险阈值、例外场景。",
        "output": "制度/SOP、A/B/C/D 授权规则、例外路径和审批证据。",
        "exit_criteria": "至少一份生效的制度/SOP；至少一条生效的授权规则，"
        "写清审批人、例外路径和审批证据。",
        "estimated": "2–4 周",
        "pilot": True,
        "actions": [
            {"label": "去上传制度", "view": "deliverables"},
            {"label": "去定审批规则", "view": "authorization"},
        ],
        "next_hint": "先上传一份能生效的 SOP，再到「授权矩阵」按 A/B/C/D 建规则，"
        "写清审批人、例外路径和证据。",
    },
    {
        "key": "process_design",
        "title": "5. 流程/表单/工具设计",
        "goal": "把流程拆成岗位看得懂的步骤，写清楚输入、输出、角色、控制点，"
        "以及配套的表单和工具。",
        "input": "SIPOC、泳道图、控制点、系统配置和表单字段。",
        "output": "L4 步骤/SOP、表单、规则、工具绑定。",
        "exit_criteria": "至少一份表单，并且表单/规则/工具至少绑定一项。",
        "estimated": "3–6 周",
        "pilot": True,
        "actions": [
            {"label": "去画流程", "view": "designer"},
            {"label": "去看方法手册", "view": "workflow"},
        ],
        "next_hint": "在流程设计器把 L4 步骤、表单、规则和工具串起来；先小范围能用，再求全。",
    },
    {
        "key": "workload",
        "title": "6. 工作量测量",
        "goal": "先定方法，再现场观测、评定、宽放和审核；标准工时只做能力基线，不用来扣个人。",
        "input": "作业分解、现场观测/抽样、岗位和可用工时。",
        "output": "标准工时卡、能力负荷表。",
        "exit_criteria": "至少一条已验证的标准工时；至少一条当月产能记录。",
        "estimated": "4–8 周",
        "pilot": True,
        "actions": [
            {"label": "去登记工时", "view": "monitor", "hint": "运营监控 → 工作量"},
        ],
        "next_hint": "先稳定方法，再做 5 次以上观测；在「运营监控 → 工作量」录工时、验证，"
        "并补当月产能。",
    },
    {
        "key": "performance",
        "title": "7. 试运行与绩效监测",
        "goal": "小范围试运行，建立 2–5 个结果/过程/健康度指标，让红黄灯和异常有人处理、能闭环。",
        "input": "试运行记录、指标数据、异常台账、客户/下游反馈。",
        "output": "KPI 卡、红黄绿阈值、异常台账、试运行报告。",
        "exit_criteria": "至少一张完整 KPI 卡（公式、阈值、责任人）并且有数据点。",
        "estimated": "4–8 周",
        "pilot": True,
        "actions": [{"label": "去看 KPI 和异常", "view": "monitor"}],
        "next_hint": "在「运营监控 → KPI 明细」补齐公式、红黄绿阈值和责任人，"
        "至少录入一个数据点；异常要有人闭环。",
    },
    {
        "key": "review_release",
        "title": "8. 评审与固化",
        "goal": "门禁评审：模型、制度、培训、权限都到位后发布 V1.0；旧版归档，回退方案写清楚。",
        "input": "评审记录、培训记录、权限配置、回退方案。",
        "output": "V1.0 发布包、培训记录、权限清单、回退方案。",
        "exit_criteria": "至少一条 L3 已发布模型，并且有生效的制度/SOP 支撑发布。",
        "estimated": "2–4 周",
        "pilot": True,
        "actions": [
            {"label": "去发布模型", "view": "designer"},
            {"label": "去看制度版本", "view": "deliverables"},
        ],
        "next_hint": "在流程设计器完成校验并发布；把 SOP 生效、培训和权限记录补齐，再发 V1.0。",
    },
    {
        "key": "improvement",
        "title": "9. 改善与复制",
        "goal": "问题走同一条改善链：看现场→找根因→试办法→验结果→改标准→教全员；"
        "把好方法复制到相似组织。",
        "input": "红黄指标、异常、根因、改善验证结果、复制条件。",
        "output": "改善项目卡、变更单、新版本、复制资产包和知识条目。",
        "exit_criteria": "至少一个改善项目、一张已应用变更单，且没有未闭环的治理待办。",
        "estimated": "每轮 8–12 周",
        "pilot": False,
        "actions": [
            {"label": "从红黄指标转改善", "view": "monitor"},
            {"label": "看改善项目", "view": "projects"},
            {"label": "去提变更", "view": "designer"},
            {"label": "看治理待办", "view": "deliverables"},
            {"label": "看流程卡", "view": "process_card"},
        ],
        "next_hint": "先处理未闭环治理待办，再从红黄 KPI 转改善项目；"
        "改完走变更单，发布新版本并沉淀知识。",
    },
]

STEP_KEYS = {step["key"] for step in STEP_DEFINITIONS}

EVIDENCE_LABELS: Dict[str, str] = {
    "l3_with_owner": "L3 已绑定负责人",
    "governance_roles": "治理角色",
    "sponsor_projects": "有发起人的试点项目",
    "objectives": "年度目标",
    "linked_objectives": "目标已挂到流程",
    "objectives_with_owner": "目标有责任人和目标值",
    "objectives_with_baseline": "目标有现状基线",
    "l1": "L1 节点",
    "l2": "L2 节点",
    "l3": "L3 节点",
    "pcf_mapped_l3": "已对应 PCF 分类的 L3",
    "benchmark_maps": "PCF 对标映射",
    "positions": "岗位主数据",
    "raci_matters": "关键事项的 RACI",
    "invalid_processes": "权责冲突（应为 0）",
    "documents": "制度/SOP 文件",
    "effective_documents": "已生效的制度/SOP",
    "effective_authorization_rules": "已生效的授权规则",
    "open_authorization_exceptions": "未闭环的授权例外",
    "l3_published": "已发布的流程模型",
    "bindings": "表单/规则/工具绑定",
    "forms": "表单",
    "rules": "规则",
    "node_tools": "工具绑定",
    "verified_standards": "已验证的标准工时",
    "capacity_rows": "当月产能记录",
    "actual_worklogs": "实际工时记录",
    "kpi_cards": "完整的 KPI 卡",
    "kpi_records": "KPI 数据点",
    "red_yellow": "红/黄指标",
    "improvement_projects": "改善项目",
    "applied_changes": "已应用的变更",
    "open_findings": "未闭环治理待办",
    "knowledge_items": "知识条目",
    "kpi_records_30d": "近 30 天数据",
}

# 这些指标 0 才是好结果；其余指标 > 0 才算“已有证据”
ZERO_IS_GOOD = {"invalid_processes", "open_findings", "open_authorization_exceptions"}

# (evidence key, 是否必需)。必需项全部满足才算 READY；可选项只用于“建议补充”。
EVIDENCE_ITEMS: Dict[str, List[Tuple[str, bool]]] = {
    "scope": [
        ("l3_with_owner", True),
        ("governance_roles", True),
        ("sponsor_projects", False),
    ],
    "strategy": [
        ("objectives", True),
        ("linked_objectives", True),
        ("objectives_with_owner", True),
        ("objectives_with_baseline", True),
    ],
    "architecture": [
        ("l1", True),
        ("l2", True),
        ("l3", True),
        ("pcf_mapped_l3", True),
        ("benchmark_maps", False),
        ("positions", True),
        ("raci_matters", True),
        ("invalid_processes", True),
    ],
    "policy": [
        ("effective_documents", True),
        ("effective_authorization_rules", True),
        ("documents", False),
        ("open_authorization_exceptions", False),
    ],
    "process_design": [
        ("forms", True),
        ("bindings", True),
        ("rules", False),
        ("node_tools", False),
        ("l3_published", False),
    ],
    "workload": [
        ("verified_standards", True),
        ("capacity_rows", True),
        ("actual_worklogs", False),
    ],
    "performance": [
        ("kpi_cards", True),
        ("kpi_records", True),
        ("red_yellow", False),
    ],
    "review_release": [
        ("l3_published", True),
        ("effective_documents", True),
    ],
    "improvement": [
        ("improvement_projects", True),
        ("applied_changes", True),
        ("open_findings", True),
        ("knowledge_items", False),
        ("kpi_records_30d", False),
    ],
}

# 计数点开后落到的页面。参数只打开该页里已经有的页签。
EVIDENCE_DESTINATIONS: Dict[str, Tuple[str, Dict[str, str]]] = {
    "l3_with_owner": ("map", {"owners": "l3"}),
    "governance_roles": ("orgs", {"tab": "governance"}),
    "sponsor_projects": ("projects", {}),
    "objectives": ("strategy", {}),
    "linked_objectives": ("strategy", {}),
    "objectives_with_owner": ("strategy", {}),
    "objectives_with_baseline": ("strategy", {}),
    "l1": ("map", {}),
    "l2": ("map", {}),
    "l3": ("map", {}),
    "pcf_mapped_l3": ("map", {"benchmark": "1"}),
    "benchmark_maps": ("map", {"benchmark": "1"}),
    "positions": ("orgs", {"tab": "position"}),
    "raci_matters": ("designer", {"tab": "raci"}),
    "invalid_processes": ("designer", {"tab": "raci"}),
    "documents": ("deliverables", {"tab": "document"}),
    "effective_documents": ("deliverables", {"tab": "document"}),
    "effective_authorization_rules": ("authorization", {}),
    "open_authorization_exceptions": ("authorization", {"pane": "exceptions"}),
    "l3_published": ("designer", {"tab": "model"}),
    "bindings": ("execution", {"tab": "config", "focus": "forms"}),
    "forms": ("execution", {"tab": "config", "focus": "forms"}),
    "rules": ("execution", {"tab": "config", "focus": "forms"}),
    "node_tools": ("designer", {"tab": "model"}),
    "verified_standards": ("monitor", {"tab": "workload"}),
    "capacity_rows": ("monitor", {"tab": "workload"}),
    "actual_worklogs": ("monitor", {"tab": "workload"}),
    "kpi_cards": ("monitor", {"tab": "kpi"}),
    "kpi_records": ("monitor", {"tab": "kpi"}),
    "red_yellow": ("monitor", {"tab": "kpi"}),
    "improvement_projects": ("projects", {}),
    "applied_changes": ("designer", {"tab": "change"}),
    "open_findings": ("deliverables", {"tab": "baseline", "focus": "findings"}),
    "knowledge_items": ("toolbox", {"section": "resources"}),
    "kpi_records_30d": ("monitor", {"tab": "kpi"}),
}


class StartupStepNotFound(ValueError):
    """步骤不存在或不在九步定义里。"""


class PilotGateError(ValueError):
    """首次上线门禁未通过；missing 是仍未就绪的阶段标题。"""

    def __init__(self, missing: List[str]):
        self.missing = missing
        super().__init__("首次上线条件未满足：" + "、".join(missing))


PILOT_KEY = "PILOT_GO_LIVE"


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _met(key: str, value: int) -> bool:
    return value == 0 if key in ZERO_IS_GOOD else value > 0


def evidence_snapshot(db: Session) -> Dict[str, int]:
    """开始使用专用：全公司能力计数（公司会不会做）。

    单流程落地计数见 process_evidence.collect，二者不得混用。
    """
    return _collect_evidence(db)


def evidence_met(key: str, value: int) -> bool:
    return _met(key, value)


def governance_position(db: Session) -> tuple[int, float]:
    """治理落地的当前阶段与进度，和启动页用同一组证据。

    当前阶段 = 第一个未就绪且未跳过的阶段（从 1 计）。
    全部就绪时停在最后一阶段，进度为 100。
    """
    evidence = _collect_evidence(db)
    skips = _skip_map(db)
    ready = 0
    open_stage: Optional[int] = None
    total = len(STEP_DEFINITIONS) or 1
    for index, definition in enumerate(STEP_DEFINITIONS, start=1):
        key = definition["key"]
        items = EVIDENCE_ITEMS[key]
        met = all(_met(item_key, evidence[item_key]) for item_key, required in items if required)
        if met:
            ready += 1
        if open_stage is None and not met and skips.get(key) is None:
            open_stage = index
    if open_stage is None:
        open_stage = len(STEP_DEFINITIONS) or 1
    return open_stage, round(ready / total * 100, 1)


def apply_governance_stages(db: Session) -> None:
    """把所有进行中的治理落地项目阶段写成上面的同一个数。"""
    from app.models.enums import ProjectStatus, ProjectType
    from app.models.project import Project

    stage, progress = governance_position(db)
    rows = db.scalars(
        select(Project).where(
            Project.project_type == ProjectType.GOVERNANCE_SETUP.value,
            Project.status.in_(
                (
                    ProjectStatus.PLANNING.value,
                    ProjectStatus.ACTIVE.value,
                    ProjectStatus.ON_HOLD.value,
                )
            ),
        )
    ).all()
    for row in rows:
        row.current_stage = stage
        row.progress = progress
    db.flush()


def _status(started: bool, ready: bool, skipped: bool) -> Tuple[str, str]:
    if skipped:
        return "SKIPPED", "这次先不做（未验证）"
    if ready:
        return "READY", "已具备"
    if started:
        return "IN_PROGRESS", "进行中"
    return "NOT_STARTED", "还没开始"


def _kpi_card_stats(db: Session) -> Tuple[int, int, int]:
    kpis = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True))
    ).all()
    cards = 0
    records = 0
    red_yellow = 0
    for kpi in kpis:
        has_card = bool(
            (kpi.formula or "").strip()
            and kpi.target_value is not None
            and kpi.red_threshold is not None
            and kpi.yellow_threshold is not None
            and kpi.green_threshold is not None
        )
        if has_card:
            cards += 1
        periods = kpi_service.ordered_records(kpi.records)
        records += len(periods)
        if not periods:
            continue
        status = kpi_service.status_for(
            periods[-1].value,
            kpi.direction,
            kpi.red_threshold,
            kpi.yellow_threshold,
            kpi.green_threshold,
        )
        if status in ("RED", "YELLOW"):
            red_yellow += 1
    return cards, records, red_yellow


def _collect_evidence(db: Session) -> Dict[str, int]:
    """一次性收集九步用到的全部证据计数。"""
    today = date.today()
    month_start = workload_service.normalize_period(today)
    last_30 = today - timedelta(days=30)

    l3_with_owner = _count(
        db,
        select(func.count())
        .select_from(ProcessArch)
        .where(ProcessArch.level == 3, ProcessArch.owner_user_id.is_not(None)),
    )
    governance_roles = _count(
        db,
        select(func.count()).select_from(GovernanceRole).where(GovernanceRole.is_active.is_(True)),
    )
    sponsor_projects = _count(
        db,
        select(func.count())
        .select_from(Project)
        .where(
            Project.process_id.is_not(None),
            Project.sponsor.is_not(None),
            Project.sponsor != "",
        ),
    )
    objectives = _count(
        db,
        select(func.count())
        .select_from(StrategyObjective)
        .where(StrategyObjective.status == "ACTIVE"),
    )
    linked_objectives = _count(
        db,
        select(func.count(func.distinct(ObjectiveProcessLink.objective_id))).select_from(
            ObjectiveProcessLink
        ),
    )
    objectives_with_owner = _count(
        db,
        select(func.count())
        .select_from(StrategyObjective)
        .where(
            StrategyObjective.status == "ACTIVE",
            StrategyObjective.owner_user_id.is_not(None),
            StrategyObjective.target_value.is_not(None),
        ),
    )
    objectives_with_baseline = _count(
        db,
        select(func.count())
        .select_from(StrategyObjective)
        .where(
            StrategyObjective.status == "ACTIVE",
            StrategyObjective.baseline_value.is_not(None),
        ),
    )
    l1 = _count(db, select(func.count()).select_from(ProcessArch).where(ProcessArch.level == 1))
    l2 = _count(db, select(func.count()).select_from(ProcessArch).where(ProcessArch.level == 2))
    l3 = _count(db, select(func.count()).select_from(ProcessArch).where(ProcessArch.level == 3))
    benchmark_maps = _count(db, select(func.count()).select_from(ProcessBenchmarkMap))
    pcf_mapped_l3 = _count(
        db,
        select(func.count(func.distinct(ProcessBenchmarkMap.process_id)))
        .select_from(ProcessBenchmarkMap)
        .join(ProcessArch, ProcessArch.id == ProcessBenchmarkMap.process_id)
        .where(ProcessArch.level == 3),
    )
    positions = _count(db, select(func.count()).select_from(Position))
    raci_matters = _count(
        db,
        select(func.count()).select_from(
            select(RaciAssignment.process_id, RaciAssignment.matter).distinct().subquery()
        ),
    )
    invalid_raci = len(raci_service.invalid_processes(db))
    documents = _count(
        db,
        select(func.count())
        .select_from(ProcessDocument)
        .where(ProcessDocument.is_active.is_(True)),
    )
    effective_documents = sum(
        1
        for document in db.scalars(
            select(ProcessDocument)
            .options(selectinload(ProcessDocument.versions))
            .where(ProcessDocument.is_active.is_(True))
        ).all()
        if document_service.effective_version_on(document) is not None
    )
    effective_authorization_rules = authorization_service.effective_rule_count(db)
    open_authorization_exceptions = authorization_service.open_exception_count(db)
    l3_published = _count(
        db,
        select(func.count())
        .select_from(ProcessArch)
        .where(ProcessArch.level == 3, ProcessArch.published_model_version > 0),
    )
    forms = _count(db, select(func.count()).select_from(FormDefinition))
    rules = _count(db, select(func.count()).select_from(ProcessRule))
    node_tools = _count(db, select(func.count()).select_from(NodeTool))
    verified_standards = _count(
        db,
        select(func.count())
        .select_from(WorkMeasurementStandard)
        .where(WorkMeasurementStandard.status == WorkMeasurementStatus.VERIFIED.value),
    )
    capacity_rows = _count(
        db,
        select(func.count())
        .select_from(CapacityCalendar)
        .where(CapacityCalendar.period == month_start),
    )
    worklogs = _count(db, select(func.count()).select_from(TaskWorklog))
    kpi_cards, kpi_records, red_yellow = _kpi_card_stats(db)
    improvements = _count(
        db,
        select(func.count()).select_from(Project).where(Project.source == "KPI_THRESHOLD"),
    )
    applied_changes = _count(
        db,
        select(func.count())
        .select_from(ProcessChangeRequest)
        .where(ProcessChangeRequest.status == ChangeStatus.APPLIED.value),
    )
    open_findings = _count(
        db,
        select(func.count())
        .select_from(GovernanceFinding)
        .where(GovernanceFinding.status == "OPEN"),
    )
    knowledge = _count(db, select(func.count()).select_from(KnowledgeItem))
    recent_records = _count(
        db,
        select(func.count()).select_from(KpiRecord).where(KpiRecord.period >= last_30),
    )

    return {
        "l3_with_owner": l3_with_owner,
        "governance_roles": governance_roles,
        "sponsor_projects": sponsor_projects,
        "objectives": objectives,
        "linked_objectives": linked_objectives,
        "objectives_with_owner": objectives_with_owner,
        "objectives_with_baseline": objectives_with_baseline,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "pcf_mapped_l3": pcf_mapped_l3,
        "benchmark_maps": benchmark_maps,
        "positions": positions,
        "raci_matters": raci_matters,
        "invalid_processes": invalid_raci,
        "documents": documents,
        "effective_documents": effective_documents,
        "effective_authorization_rules": effective_authorization_rules,
        "open_authorization_exceptions": open_authorization_exceptions,
        "l3_published": l3_published,
        "bindings": forms + rules + node_tools,
        "forms": forms,
        "rules": rules,
        "node_tools": node_tools,
        "verified_standards": verified_standards,
        "capacity_rows": capacity_rows,
        "actual_worklogs": worklogs,
        "kpi_cards": kpi_cards,
        "kpi_records": kpi_records,
        "red_yellow": red_yellow,
        "improvement_projects": improvements,
        "applied_changes": applied_changes,
        "open_findings": open_findings,
        "knowledge_items": knowledge,
        "kpi_records_30d": recent_records,
    }


def _skip_map(db: Session) -> Dict[str, StartupStepSkip]:
    return {row.step_key: row for row in db.scalars(select(StartupStepSkip)).all()}


def status(db: Session) -> StartupStatusOut:
    evidence = _collect_evidence(db)
    skips = _skip_map(db)
    skipped_users = {
        row.skipped_by_user_id: db.get(User, row.skipped_by_user_id)
        for row in skips.values()
        if row.skipped_by_user_id is not None
    }

    steps: List[StartupStepOut] = []
    for index, definition in enumerate(STEP_DEFINITIONS):
        key = definition["key"]
        items = EVIDENCE_ITEMS[key]
        started = any(_met(item_key, evidence[item_key]) for item_key, _ in items)
        ready = all(_met(item_key, evidence[item_key]) for item_key, required in items if required)
        skip = skips.get(key)
        state, label = _status(started, ready, skip is not None)
        skipped_user = skipped_users.get(skip.skipped_by_user_id) if skip else None
        steps.append(
            StartupStepOut(
                key=key,
                order=index,
                title=definition["title"],
                goal=definition["goal"],
                input=definition["input"],
                output=definition["output"],
                exit_criteria=definition["exit_criteria"],
                estimated=definition["estimated"],
                pilot=definition["pilot"],
                status=state,
                status_label=label,
                skipped=skip is not None,
                skip_reason=skip.reason if skip else None,
                skipped_by=skipped_user.display_name if skipped_user else None,
                evidence=evidence,
                evidence_items=[
                    StartupEvidenceOut(
                        key=item_key,
                        label=EVIDENCE_LABELS[item_key],
                        value=evidence[item_key],
                        required=required,
                        met=_met(item_key, evidence[item_key]),
                        view=EVIDENCE_DESTINATIONS[item_key][0],
                        view_params=EVIDENCE_DESTINATIONS[item_key][1],
                    )
                    for item_key, required in items
                ],
                actions=[StartupActionOut(**action) for action in definition["actions"]],
                next_hint=None if ready or skip is not None else definition["next_hint"],
            )
        )

    ready_count = sum(1 for step in steps if step.status == "READY")
    pilot_steps = [step for step in steps if step.pilot]
    pilot_ready_count = sum(1 for step in pilot_steps if step.status == "READY")
    skipped_count = sum(1 for step in steps if step.status == "SKIPPED")
    next_step = next(
        (step.key for step in steps if step.status not in ("READY", "SKIPPED")),
        None,
    )
    next_pilot_step = next(
        (step.key for step in pilot_steps if step.status not in ("READY", "SKIPPED")),
        None,
    )
    pilot_gate_open = pilot_ready_count >= len(pilot_steps)
    pilot_missing_steps = [step.title for step in pilot_steps if step.status != "READY"]
    confirm = db.scalar(select(StartupPilotConfirm).where(StartupPilotConfirm.key == PILOT_KEY))
    confirmed_by = (
        db.get(User, confirm.confirmed_by_user_id)
        if confirm and confirm.confirmed_by_user_id
        else None
    )
    from app.models.enums import PilotPathStatus
    from app.models.pilot import PilotPath

    path_rows = db.scalars(select(PilotPath)).all()
    path_count = len(path_rows)
    path_completed_count = sum(
        1 for row in path_rows if row.status == PilotPathStatus.COMPLETED.value
    )
    path_avg_layer = (
        round(sum(row.current_layer for row in path_rows) / path_count, 1) if path_count else 0.0
    )

    return StartupStatusOut(
        total=len(steps),
        ready_count=ready_count,
        readiness_pct=round(ready_count * 100 / len(steps), 1) if steps else 0.0,
        pilot_total=len(pilot_steps),
        pilot_ready_count=pilot_ready_count,
        pilot_readiness_pct=(
            round(pilot_ready_count * 100 / len(pilot_steps), 1) if pilot_steps else 0.0
        ),
        skipped_count=skipped_count,
        next_step=next_step,
        next_pilot_step=next_pilot_step,
        pilot_gate_open=pilot_gate_open,
        pilot_confirmed=confirm is not None,
        pilot_confirmed_by=confirmed_by.display_name if confirmed_by else None,
        pilot_confirmed_at=confirm.confirmed_at if confirm else None,
        pilot_confirm_note=confirm.note if confirm else None,
        pilot_stale=confirm is not None and not pilot_gate_open,
        pilot_missing_steps=pilot_missing_steps,
        path_count=path_count,
        path_completed_count=path_completed_count,
        path_avg_layer=path_avg_layer,
        steps=steps,
    )


def skip_step(db: Session, step_key: str, reason: Optional[str], user: User) -> StartupStatusOut:
    """把一步标记为“本轮不验证”，返回最新状态。"""
    if step_key not in STEP_KEYS:
        raise StartupStepNotFound(f"启动步骤 {step_key} 不存在")
    row = db.scalar(select(StartupStepSkip).where(StartupStepSkip.step_key == step_key))
    if row is None:
        row = StartupStepSkip(step_key=step_key)
        db.add(row)
    row.reason = (reason or "").strip() or None
    row.skipped_by_user_id = user.id
    row.created_at = utcnow()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "startup_step",
        None,
        f"跳过启动步骤 {step_key}（标记未验证）：{row.reason or '未填写原因'}",
    )
    db.commit()
    return status(db)


def unskip_step(db: Session, step_key: str, user: User) -> StartupStatusOut:
    """取消跳过，恢复为按数据自动判定。"""
    if step_key not in STEP_KEYS:
        raise StartupStepNotFound(f"启动步骤 {step_key} 不存在")
    row = db.scalar(select(StartupStepSkip).where(StartupStepSkip.step_key == step_key))
    if row is not None:
        db.delete(row)
        audit_service.record(
            db,
            user,
            "UPDATE",
            "startup_step",
            None,
            f"取消跳过启动步骤 {step_key}",
        )
        db.commit()
    return status(db)


def confirm_pilot(db: Session, user: User, note: Optional[str]) -> StartupStatusOut:
    """首次上线确认：只有 S0–S7 全部就绪才允许落库。"""
    current = status(db)
    if not current.pilot_gate_open:
        raise PilotGateError(current.pilot_missing_steps)
    row = db.scalar(select(StartupPilotConfirm).where(StartupPilotConfirm.key == PILOT_KEY))
    if row is None:
        row = StartupPilotConfirm(key=PILOT_KEY)
        db.add(row)
    row.confirmed_by_user_id = user.id
    row.confirmed_at = utcnow()
    row.note = (note or "").strip() or None
    row.evidence_snapshot = {
        "pilot_ready_count": current.pilot_ready_count,
        "pilot_total": current.pilot_total,
        "steps": [
            {"key": step.key, "title": step.title, "status": step.status} for step in current.steps
        ],
    }
    audit_service.record(
        db,
        user,
        "UPDATE",
        "startup_pilot",
        None,
        f"确认首次上线：{current.pilot_ready_count}/{current.pilot_total} 阶段就绪",
    )
    db.commit()
    return status(db)


def revoke_pilot(db: Session, user: User) -> StartupStatusOut:
    """撤销首次上线确认；下一次登录会回到启动页。"""
    row = db.scalar(select(StartupPilotConfirm).where(StartupPilotConfirm.key == PILOT_KEY))
    if row is not None:
        db.delete(row)
        audit_service.record(db, user, "UPDATE", "startup_pilot", None, "撤销首次上线确认")
        db.commit()
    return status(db)
