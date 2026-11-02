"""开始使用：只回答公司流程地图的框架边界有没有划清。

单条流程的起止、活动、工时、指标和发布不在这里数，去十层核对。
这里没有 1 到 N 的阶段楼梯，也没有「前若干步齐了才能首次上线」。
人工“跳过”仍可记下，但不构成另一条进度。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.timeutil import utcnow
from app.models.authorization import AuthorizationRule
from app.models.benchmark import ProcessBenchmarkMap
from app.models.change import ProcessChangeRequest
from app.models.enums import AuthorizationStatus, ChangeStatus, WorkMeasurementStatus
from app.models.execution import FormDefinition, ProcessRule, TaskWorklog
from app.models.governance import GovernanceFinding
from app.models.knowledge import KnowledgeItem
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.startup import ProcessCharter, StartupPilotConfirm, StartupStepSkip
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.schemas.startup import (
    StartupActionOut,
    StartupEvidenceOut,
    StartupPointOut,
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
        "key": "framework",
        "title": "流程框架边界",
        "goal": "公司这张流程地图的边界：哪些工作进图，上下级怎么挂，谁能改图。",
        "points": [
            {
                "label": "生命周期",
                "text": "战略对齐、流程架构、建模、分析、设计、执行、监控度量、变革优化、治理。"
                "流程架构用 APQC 的分类，分类不是先后。建模到监控在「把一条流程建好」。",
            },
            {"label": "地图", "text": "至少一条 L3 同时有 L1、L2 上级，并对上 PCF。"},
            {"label": "改图的人", "text": "至少一个治理角色启用且有成员。"},
        ],
        "input": "流程地图上的 L1、L2、L3 与 PCF 对应，以及有成员的治理角色。",
        "output": "至少一条同时具备上级并对上 PCF 的 L3；至少一个有成员的治理角色。",
        "exit_criteria": "地图和改图的人都齐。",
        "estimated": "",
        "pilot": False,
        "actions": [
            {"label": "去建流程地图", "view": "map"},
            {"label": "1+3+10 建架构", "view": "map", "action": "start.guidedPcf"},
            {"label": "去对上 PCF", "view": "map", "view_params": {"benchmark": "1"}},
            {
                "label": "去任命治理角色",
                "view": "orgs",
                "view_params": {"tab": "governance"},
            },
        ],
        "next_hint": "某一条流程从哪开始、到哪结束，去十层核对写。",
    },
]

STEP_KEYS = {step["key"] for step in STEP_DEFINITIONS}

EVIDENCE_LABELS: Dict[str, str] = {
    "process_charters": "写全起止和范围的 L3",
    "l3_with_owner": "L3 已绑定负责人",
    "governance_roles": "有成员且启用的治理角色",
    "objective_complete": "同一条目标具备责任人、目标值和基线",
    "rpa_runs": "已记下并挂了集成端点的机器人运行",
    "process_cases": "已登记的案例",
    "technology_uses": "已登记的区块链、人工智能或物联网用途",
    "mining_variants": "已挖出的路径变体",
    "rpa_bots": "已登记的机器人",
    "training_records": "已登记的培训到场",
    "complete_objectives": "同一条目标具备责任人、目标值、基线和流程",
    "sponsor_projects": "挂了流程且写了发起人的项目",
    "objectives": "在用的年度目标",
    "linked_objectives": "目标已挂到流程",
    "objectives_with_owner": "目标有责任人和目标值",
    "objectives_with_baseline": "目标有现状基线",
    "anchored_l3": "有 L1/L2 上级且对上 PCF 的 L3",
    "l1": "L1 节点",
    "l2": "L2 节点",
    "l3": "L3 节点",
    "pcf_mapped_l3": "已对应 PCF 分类的 L3",
    "benchmark_maps": "PCF 对标映射",
    "positions": "岗位主数据",
    "raci_matters": "关键事项的 RACI",
    "invalid_processes": "权责冲突（应为 0）",
    "documents": "制度或作业指导书",
    "effective_documents": "已生效的制度或作业指导书",
    "effective_authorization_rules": "写了审批人、例外路径和证据的生效规则",
    "open_authorization_exceptions": "未关闭的授权例外",
    "l4": "L4 活动",
    "l3_published": "已发布模型的 L3",
    "bindings": "表单、规则与方法工具合计",
    "forms": "表单",
    "rules": "规则",
    "node_tools": "方法工具绑定（设计证据，可选）",
    "verified_standards": "已验证的标准工时",
    "capacity_rows": "当月产能记录",
    "actual_worklogs": "实际工时记录",
    "kpi_monitored": "有公式、阈值、责任人和数据点的 KPI",
    "kpi_cards": "有公式、目标值和红黄绿阈值的 KPI",
    "kpi_records": "KPI 数据点",
    "red_yellow": "红/黄指标",
    "improvement_projects": "KPI 越线转来的改善项目",
    "applied_changes": "已应用的变更单",
    "open_findings": "未关闭的治理待办",
    "knowledge_items": "知识条目",
    "kpi_records_30d": "近 30 天的 KPI 数据点",
}

# 这些指标 0 才是好结果；其余指标 > 0 才算“已有证据”
ZERO_IS_GOOD = {
    "invalid_processes",
    "open_findings",
    "open_authorization_exceptions",
}

# (evidence key, 是否必需)。必需项全部满足才算 READY；可选项只用于“建议补充”。
EVIDENCE_ITEMS: Dict[str, List[Tuple[str, bool]]] = {
    "framework": [
        ("anchored_l3", True),
        ("l1", True),
        ("l2", True),
        ("l3", True),
        ("pcf_mapped_l3", True),
        ("governance_roles", True),
    ],
}

# 计数点开后落到的页面。参数只打开该页里已经有的页签。
EVIDENCE_DESTINATIONS: Dict[str, Tuple[str, Dict[str, str]]] = {
    "process_charters": ("pilot", {}),
    "l3_with_owner": ("map", {"owners": "l3"}),
    "complete_objectives": ("strategy", {}),
    "anchored_l3": ("map", {"benchmark": "1"}),
    "governance_roles": ("orgs", {"tab": "governance"}),
    "objective_complete": ("strategy", {}),
    "rpa_runs": ("pilot", {}),
    "process_cases": ("pilot", {}),
    "technology_uses": ("pilot", {}),
    "mining_variants": ("monitor", {"tab": "mining"}),
    "rpa_bots": ("pilot", {}),
    "training_records": ("pilot", {}),
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
    "l4": ("map", {}),
    "l3_published": ("designer", {"tab": "model"}),
    "kpi_monitored": ("monitor", {"tab": "kpi"}),
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
    """步骤不存在或不在框架边界定义里。"""


class PilotGateError(ValueError):
    """首次上线门禁未通过；missing 是仍未就绪的阶段标题。"""

    def __init__(self, missing: List[str]):
        self.missing = missing
        super().__init__("首次上线条件未满足：" + "、".join(missing))


PILOT_KEY = "PILOT_GO_LIVE"

_CHARTER_TEXT = (
    "purpose",
    "starts_at",
    "ends_at",
    "in_scope",
    "out_of_scope",
    "stop_condition",
)


class CharterError(ValueError):
    """范围说明写得不完整，或挂错了流程。"""


def _filled(value: Optional[str]) -> bool:
    return bool((value or "").strip())


def _complete_charter_count(db: Session) -> int:
    rows = db.execute(
        select(ProcessCharter, ProcessArch).join(
            ProcessArch, ProcessArch.id == ProcessCharter.process_id
        )
    ).all()
    count = 0
    for charter, process in rows:
        if process.level != 3 or process.owner_user_id is None:
            continue
        if charter.sponsor_user_id is None:
            continue
        if all(_filled(getattr(charter, name)) for name in _CHARTER_TEXT):
            count += 1
    return count


def _complete_authorization_count(db: Session) -> int:
    rules = db.scalars(
        select(AuthorizationRule).where(
            AuthorizationRule.status == AuthorizationStatus.EFFECTIVE.value
        )
    ).all()
    count = 0
    for rule in rules:
        approver = rule.approver_role_id is not None or _filled(rule.approver_label)
        if approver and _filled(rule.exception_path) and _filled(rule.evidence_required):
            count += 1
    return count


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


def _kpi_card_stats(db: Session) -> Tuple[int, int, int, int]:
    kpis = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True))
    ).all()
    cards = 0
    records = 0
    red_yellow = 0
    monitored = 0
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
        if has_card and periods and kpi.owner_user_id is not None:
            monitored += 1
        if not periods:
            continue
        status, _label, _kind = kpi_service.presentation(db, kpi, periods[-1].value)
        if status in ("RED", "YELLOW"):
            red_yellow += 1
    return cards, records, red_yellow, monitored


def _collect_evidence(db: Session) -> Dict[str, int]:
    """一次性收集证据计数。开始使用只用其中的框架边界项。"""
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
        select(func.count(func.distinct(GovernanceRole.id)))
        .select_from(GovernanceRole)
        .join(GovernanceRoleMember, GovernanceRoleMember.role_id == GovernanceRole.id)
        .where(GovernanceRole.is_active.is_(True)),
    )
    process_charters = _complete_charter_count(db)
    complete_objectives = _count(
        db,
        select(func.count(func.distinct(StrategyObjective.id)))
        .select_from(StrategyObjective)
        .join(ObjectiveProcessLink, ObjectiveProcessLink.objective_id == StrategyObjective.id)
        .where(
            StrategyObjective.status == "ACTIVE",
            StrategyObjective.owner_user_id.is_not(None),
            StrategyObjective.target_value.is_not(None),
            StrategyObjective.baseline_value.is_not(None),
        ),
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
    l3_node = aliased(ProcessArch)
    l2_node = aliased(ProcessArch)
    l1_node = aliased(ProcessArch)
    anchored_l3 = _count(
        db,
        select(func.count(func.distinct(l3_node.id)))
        .select_from(l3_node)
        .join(l2_node, l3_node.parent_id == l2_node.id)
        .join(l1_node, l2_node.parent_id == l1_node.id)
        .join(ProcessBenchmarkMap, ProcessBenchmarkMap.process_id == l3_node.id)
        .where(l3_node.level == 3, l2_node.level == 2, l1_node.level == 1),
    )
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
    effective_authorization_rules = _complete_authorization_count(db)
    open_authorization_exceptions = authorization_service.open_exception_count(db)
    l4 = _count(db, select(func.count()).select_from(ProcessArch).where(ProcessArch.level == 4))
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
    kpi_cards, kpi_records, red_yellow, kpi_monitored = _kpi_card_stats(db)
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
        "process_charters": process_charters,
        "l3_with_owner": l3_with_owner,
        "governance_roles": governance_roles,
        "complete_objectives": complete_objectives,
        "sponsor_projects": sponsor_projects,
        "objectives": objectives,
        "linked_objectives": linked_objectives,
        "objectives_with_owner": objectives_with_owner,
        "objectives_with_baseline": objectives_with_baseline,
        "anchored_l3": anchored_l3,
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
        "l4": l4,
        "l3_published": l3_published,
        "bindings": forms + rules + node_tools,
        "forms": forms,
        "rules": rules,
        "node_tools": node_tools,
        "verified_standards": verified_standards,
        "capacity_rows": capacity_rows,
        "actual_worklogs": worklogs,
        "kpi_monitored": kpi_monitored,
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
                points=[StartupPointOut(**point) for point in definition.get("points", [])],
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
    # 没有「首次上线」阶段列表时，门永远关着。空列表不能变成 0 >= 0。
    pilot_gate_open = bool(pilot_steps) and pilot_ready_count >= len(pilot_steps)
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


def charter_options(db: Session) -> dict:
    """第 1 阶段表单：L3、可选发起人、已经写过的范围说明。"""
    processes = db.scalars(
        select(ProcessArch).where(ProcessArch.level == 3).order_by(ProcessArch.code)
    ).all()
    users = db.scalars(select(User).order_by(User.display_name)).all()
    charters = db.scalars(select(ProcessCharter).order_by(ProcessCharter.id)).all()
    return {
        "processes": [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "has_owner": row.owner_user_id is not None,
            }
            for row in processes
        ],
        "users": [{"id": row.id, "display_name": row.display_name} for row in users],
        "charters": [
            {
                "process_id": row.process_id,
                "purpose": row.purpose,
                "starts_at": row.starts_at,
                "ends_at": row.ends_at,
                "in_scope": row.in_scope,
                "out_of_scope": row.out_of_scope,
                "stop_condition": row.stop_condition,
                "sponsor_user_id": row.sponsor_user_id,
            }
            for row in charters
        ],
    }


def save_charter(db: Session, user: User, payload) -> StartupStatusOut:
    """写入或更新一条 L3 的范围说明。负责人必须已经在流程地图上。"""
    process = db.get(ProcessArch, payload.process_id)
    if process is None or process.level != 3:
        raise CharterError("范围说明只能挂在 L3 上")
    if process.owner_user_id is None:
        raise CharterError("先给这条 L3 指定负责人，再写范围说明")
    sponsor = db.get(User, payload.sponsor_user_id)
    if sponsor is None:
        raise CharterError("发起人不存在")
    row = db.scalar(select(ProcessCharter).where(ProcessCharter.process_id == process.id))
    if row is None:
        row = ProcessCharter(process_id=process.id)
        db.add(row)
    fields = {
        "purpose": payload.purpose,
        "starts_at": payload.starts_at,
        "ends_at": payload.ends_at,
        "in_scope": payload.in_scope,
        "out_of_scope": payload.out_of_scope,
        "stop_condition": payload.stop_condition,
    }
    if not all(_filled(value) for value in fields.values()):
        raise CharterError("范围说明的每一项都要写上")
    row.purpose = fields["purpose"].strip()
    row.starts_at = fields["starts_at"].strip()
    row.ends_at = fields["ends_at"].strip()
    row.in_scope = fields["in_scope"].strip()
    row.out_of_scope = fields["out_of_scope"].strip()
    row.stop_condition = fields["stop_condition"].strip()
    row.sponsor_user_id = sponsor.id
    row.updated_at = utcnow()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_charter",
        process.id,
        f"写入范围说明 {process.code}",
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
