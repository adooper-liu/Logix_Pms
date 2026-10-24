"""启动向导状态：从现有数据自动计算九步 readiness。

不新增业务表，也不维护第二套进度口径：
- 每个步骤的“是否就绪”由真实数据推导；
- 未就绪时给出下一步动作与跳转入口；
- 流程卡复用同一套判定。

唯一的写操作是人工“跳过”：它只记录“本轮不把现有数据作为就绪证据”，
不修改任何业务对象，也不与 24 步 / 9 阶段项目的步骤状态混用。
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
from app.models.startup import StartupStepSkip
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
from app.services import kpi as kpi_service
from app.services import process_document as document_service
from app.services import raci as raci_service
from app.services import workload as workload_service

STEP_DEFINITIONS: List[Dict] = [
    {
        "key": "scope",
        "title": "1. 范围与授权",
        "goal": "确定试点 L3、赞助人、流程 Owner、数据 Owner 与停止条件。",
        "input": "痛点、战略、法人/工厂范围、可用资源。",
        "output": "试点章程、Owner 名单、范围/非范围、停止条件。",
        "exit_criteria": "试点 L3 有 Owner；至少有一个治理角色；试点项目有赞助人。",
        "estimated": "2–3 天",
        "minimal": True,
        "actions": [
            {"label": "维护战略目标", "view": "strategy"},
            {"label": "组织与治理角色", "view": "orgs"},
        ],
        "next_hint": "先给试点 L3 指定 Owner，并在「组织与人员 → 治理角色」建至少一个治理角色。",
    },
    {
        "key": "strategy",
        "title": "2. 战略基线",
        "goal": "把年度经营目标翻译成试点流程可承接的目标与指标。",
        "input": "年度经营计划、必赢之战、客户/质量/成本目标。",
        "output": "目标卡、目标 → L1/L2/L3 → KPI 映射。",
        "exit_criteria": "目标有责任人与目标值，并已承接到具体流程。",
        "estimated": "2 天",
        "minimal": True,
        "actions": [{"label": "打开战略目标", "view": "strategy"}],
        "next_hint": "在「战略目标」创建年度目标，并用「承接」把它链到试点 L3 和 KPI。",
    },
    {
        "key": "architecture",
        "title": "3. 架构基线",
        "goal": "用 PCF 作为共同语言，建立 L1–L3 架构与对标映射。",
        "input": "PCF、现有流程清单、法人/工厂边界。",
        "output": "L1–L3 架构 V0.1、PCF 覆盖与差异映射。",
        "exit_criteria": "L1/L2/L3 均已有节点；试点 L3 已映射到 PCF。",
        "estimated": "3–5 天",
        "minimal": True,
        "actions": [
            {"label": "打开流程地图", "view": "map"},
            {"label": "查看 PCF 框架", "view": "pcf"},
        ],
        "next_hint": "在「企业流程地图」补全 L1–L3，并在「PCF 分类框架」完成试点流程的对标映射。",
    },
    {
        "key": "org_raci",
        "title": "4. 组织与权责",
        "goal": "把流程责任落实到岗位与治理角色，并明确唯一 A。",
        "input": "组织树、岗位、人员、关键决策/控制事项。",
        "output": "RACI 矩阵、角色成员。",
        "exit_criteria": "每个关键事项恰好一个 A；治理扫描无 RACI_INVALID。",
        "estimated": "2–3 天",
        "minimal": True,
        "actions": [
            {"label": "组织与治理角色", "view": "orgs"},
            {"label": "在设计器维护权责", "view": "designer"},
        ],
        "next_hint": "在流程设计器「权责」页为关键事项配置 A/R/C/I，确保每个事项唯一 A。",
    },
    {
        "key": "policy",
        "title": "5. 制度与授权",
        "goal": "把控制、权限和例外规则落成可执行、可审计的标准文件。",
        "input": "风险/合规要求、现有制度、授权边界。",
        "output": "制度/SOP 清单、适用范围、生效与废止安排。",
        "exit_criteria": "至少一份标准文件处于生效状态，并标明适用范围。",
        "estimated": "3–5 天",
        "minimal": False,
        "actions": [{"label": "打开交付物与模板库", "view": "deliverables"}],
        "next_hint": "在「交付物与模板库 → 流程标准文件」上传制度/SOP，并完成审批生效。",
    },
    {
        "key": "process_design",
        "title": "6. 流程与表单/工具",
        "goal": "把 L4 活动、控制点、表单与工具固化成可执行模型。",
        "input": "L3 架构、SIPOC、控制点、系统配置清单。",
        "output": "BPMN 模型、SOP、表单/规则、工具绑定。",
        "exit_criteria": "至少一条 L3 已发布模型，且表单/规则/工具至少有一项绑定。",
        "estimated": "5–10 天",
        "minimal": True,
        "actions": [
            {"label": "打开流程设计器", "view": "designer"},
            {"label": "打开工作流手册", "view": "workflow"},
        ],
        "next_hint": "在流程设计器完成 BPMN 与表单/工具绑定，再发布模型。",
    },
    {
        "key": "workload",
        "title": "7. 工作量与产能",
        "goal": "建立可信标准工时与产能基线，支撑排程与人员配置。",
        "input": "L4 活动、岗位、现场观测/抽样、可用工时。",
        "output": "标准工时卡、产能日历、负荷率。",
        "exit_criteria": "至少一条已验证标准工时和一条产能记录；未验证工时不进入成本口径。",
        "estimated": "5–10 天",
        "minimal": True,
        "actions": [
            {"label": "打开工作量", "view": "monitor", "hint": "运营监控 → 工作量"},
        ],
        "next_hint": "在「运营监控 → 工作量」登记标准工时并验证，再补当月产能。",
    },
    {
        "key": "performance",
        "title": "8. 绩效与监测",
        "goal": "用结果/过程/健康度指标验证流程是否偏离目标。",
        "input": "目标、基线、数据来源、统计频率。",
        "output": "KPI 定义卡、红黄绿状态、异常闭环。",
        "exit_criteria": "至少一张完整 KPI 卡（公式/阈值/责任人）且已有数据点。",
        "estimated": "30 天",
        "minimal": True,
        "actions": [{"label": "打开运营监控", "view": "monitor"}],
        "next_hint": "在「运营监控 → KPI 明细」补齐公式、红黄绿阈值与责任人，并录入数据点。",
    },
    {
        "key": "improvement",
        "title": "9. 改善、变更与运营复制",
        "goal": "把红黄 KPI 变成受控的改善项目与版本变更，并让经验持续复制。",
        "input": "红/黄 KPI、异常、根因、影响分析、运行数据与治理待办。",
        "output": "改善项目卡、变更单、V1.x 版本、月度复盘与复制资产包。",
        "exit_criteria": "至少一个改善项目已立项、一张变更单已应用，且无未闭环治理待办。",
        "estimated": "30–90 天/轮",
        "minimal": False,
        "actions": [
            {"label": "查看改善候选", "view": "monitor", "hint": "运营监控 → KPI 明细"},
            {"label": "项目组合", "view": "projects"},
            {"label": "变更申请", "view": "designer", "hint": "流程设计器 → 变更"},
            {"label": "治理概览", "view": "deliverables"},
            {"label": "流程卡", "view": "process_card"},
        ],
        "next_hint": "先处理治理待办，再在 KPI 明细点「转改善」；发布门禁流程走「设计器 → 变更」审批。",
    },
]

STEP_KEYS = {step["key"] for step in STEP_DEFINITIONS}

EVIDENCE_LABELS: Dict[str, str] = {
    "l3_with_owner": "有 Owner 的试点 L3",
    "governance_roles": "治理角色",
    "sponsor_projects": "有赞助人的试点项目",
    "objectives": "目标",
    "linked_objectives": "已承接目标",
    "objectives_with_owner": "有责任人与目标值的目标",
    "l1": "L1",
    "l2": "L2",
    "l3": "L3",
    "pcf_mapped_l3": "已映射 PCF 的 L3",
    "benchmark_maps": "PCF 对标映射",
    "positions": "岗位",
    "raci_matters": "RACI 事项",
    "invalid_processes": "RACI 不完整流程",
    "documents": "标准文件",
    "effective_documents": "已生效文件",
    "l3_published": "已发布 L3 模型",
    "bindings": "表单/规则/工具绑定",
    "forms": "表单",
    "rules": "规则",
    "node_tools": "工具绑定",
    "verified_standards": "已验证工时",
    "capacity_rows": "产能记录",
    "actual_worklogs": "实际工时记录",
    "kpi_cards": "完整 KPI 卡",
    "kpi_records": "KPI 数据点",
    "red_yellow": "红/黄 KPI",
    "improvement_projects": "改善项目",
    "applied_changes": "已应用变更",
    "open_findings": "未闭环治理待办",
    "knowledge_items": "知识条目",
    "kpi_records_30d": "近 30 天数据",
}

# 这些指标 0 才是好结果；其余指标 > 0 才算“已有证据”
ZERO_IS_GOOD = {"invalid_processes", "open_findings"}

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
    ],
    "architecture": [
        ("l1", True),
        ("l2", True),
        ("l3", True),
        ("pcf_mapped_l3", True),
        ("benchmark_maps", False),
    ],
    "org_raci": [
        ("positions", True),
        ("raci_matters", True),
        ("invalid_processes", True),
    ],
    "policy": [
        ("effective_documents", True),
        ("documents", False),
    ],
    "process_design": [
        ("l3_published", True),
        ("bindings", True),
        ("forms", False),
        ("rules", False),
        ("node_tools", False),
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
    "improvement": [
        ("improvement_projects", True),
        ("applied_changes", True),
        ("open_findings", True),
        ("knowledge_items", False),
        ("kpi_records_30d", False),
    ],
}


class StartupStepNotFound(ValueError):
    """步骤不存在或不在九步定义里。"""


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _met(key: str, value: int) -> bool:
    return value == 0 if key in ZERO_IS_GOOD else value > 0


def _status(started: bool, ready: bool, skipped: bool) -> Tuple[str, str]:
    if skipped:
        return "SKIPPED", "未验证（已跳过）"
    if ready:
        return "READY", "已就绪"
    if started:
        return "IN_PROGRESS", "进行中"
    return "NOT_STARTED", "未开始"


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
        periods = sorted(kpi.records, key=lambda row: row.period)
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
                minimal=definition["minimal"],
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
                    )
                    for item_key, required in items
                ],
                actions=[StartupActionOut(**action) for action in definition["actions"]],
                next_hint=None if ready or skip is not None else definition["next_hint"],
            )
        )

    ready_count = sum(1 for step in steps if step.status == "READY")
    minimal_steps = [step for step in steps if step.minimal]
    minimal_ready_count = sum(1 for step in minimal_steps if step.status == "READY")
    skipped_count = sum(1 for step in steps if step.status == "SKIPPED")
    next_step = next(
        (step.key for step in steps if step.status not in ("READY", "SKIPPED")),
        None,
    )
    next_minimal_step = next(
        (step.key for step in minimal_steps if step.status not in ("READY", "SKIPPED")),
        None,
    )
    return StartupStatusOut(
        total=len(steps),
        ready_count=ready_count,
        readiness_pct=round(ready_count * 100 / len(steps), 1) if steps else 0.0,
        minimal_total=len(minimal_steps),
        minimal_ready_count=minimal_ready_count,
        minimal_readiness_pct=(
            round(minimal_ready_count * 100 / len(minimal_steps), 1) if minimal_steps else 0.0
        ),
        skipped_count=skipped_count,
        next_step=next_step,
        next_minimal_step=next_minimal_step,
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
