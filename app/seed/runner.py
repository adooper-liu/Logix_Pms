"""把 corpus / corpus_data 里的内容灌进数据库。

幂等性：默认只在库为空时灌；传 reset=True 则先清空再灌。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.models import AuthorizationException, AuthorizationRule
from app.models.benchmark import (
    BenchmarkCategory,
    BenchmarkFramework,
    BenchmarkMetric,
    ProcessBenchmarkMap,
)
from app.models.change import ProcessChangeRequest
from app.models.data_governance import DataDomain, DataFlow
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
    StepContract,
)
from app.models.enums import KnowledgeStatus, Role, TaskStatus, ToolStatus
from app.models.execution import (
    FormDefinition,
    IdempotencyRecord,
    NodeAssignment,
    ProcessExecutionConfig,
    ProcessInstance,
    ProcessRule,
    ProcessTask,
    ProcessTaskEvent,
    TaskWorklog,
)
from app.models.governance import GovernanceFinding
from app.models.integration import (
    InboundEvent,
    InboundWebhook,
    IntegrationDelivery,
    IntegrationEndpoint,
)
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeScenario,
    KnowledgeScenarioLink,
    KnowledgeTag,
    KnowledgeUsage,
    KnowledgeWorkflowLink,
)
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.notification import Notification
from app.models.org import OrgUnit, Position
from app.models.process import (
    NodeTool,
    ProcessArch,
    ProcessEdge,
    ProcessModelVersion,
    ProcessNode,
)
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.sketch import Sketch
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.tool import Tool, ToolScenarioLink
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.models.user import AuditLog, User
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.schemas.execution import InstanceStartRequest, TaskCompleteRequest
from app.seed import (
    authorization_data,
    benchmark_data,
    change_data,
    corpus,
    corpus_data,
    data_governance_data,
    deliverable_data,
    pcf_data,
    raci_data,
    strategy_data,
    tool_decision_data,
    workload_data,
)
from app.services import deliverable as deliverable_service
from app.services import execution as execution_service
from app.services import notifications as notification_service
from app.services import workload as workload_service
from app.services.workflow import recompute_progress, seed_project_steps

# 设计器画布上的排布参数
LANE_HEIGHT = 120
NODE_WIDTH = 170

# corpus 里所有时间字符串都按中国本地时间书写，入库前统一转成 UTC（库里只存 naive UTC）
CN_TZ = timezone(timedelta(hours=8))


def _parse_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """本地时间字符串 → naive UTC。"""
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ 各部分


def _owner_user_id(owner: Optional[str], user_ids: Dict[str, int]) -> Optional[int]:
    """把底稿里的 Owner 文本映射到演示账号。

    支持两种写法：与 display_name 完全一致（如「陈经理」），
    或「部门-姓名」后缀（如「采购部-陈经理」）。匹配不到就保持未绑定。
    """
    if not owner:
        return None
    if owner in user_ids:
        return user_ids[owner]
    for name, uid in user_ids.items():
        if owner.endswith("-" + name):
            return uid
    return None


def _seed_process_arch(
    db: Session,
    user_ids: Dict[str, int],
    org_name_ids: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    org_name_ids = org_name_ids or {}
    code_to_id: Dict[str, int] = {}
    # 先按 level 排序，保证父节点先入库
    for row in sorted(corpus.PROCESS_ARCH, key=lambda r: r["level"]):
        parent_code = row.get("parent")
        parent_id = code_to_id.get(parent_code) if parent_code else None
        if parent_code and parent_id is None:
            raise ValueError(
                f"流程 {row['code']} 的父节点 {parent_code} 尚未入库，检查 corpus 顺序"
            )
        obj = ProcessArch(
            code=row["code"],
            name=row["name"],
            level=row["level"],
            parent_id=parent_id,
            owner=row.get("owner"),
            owner_user_id=_owner_user_id(row.get("owner"), user_ids),
            department=row.get("department"),
            org_unit_id=org_name_ids.get(row.get("department") or ""),
            description=row.get("description"),
            strategic_importance=row.get("si", 3.0),
            pain_score=row.get("pain", 3.0),
            improvement_space=row.get("space", 3.0),
            health_score=row.get("health"),
            is_improvement_target=row.get("target", False),
            requires_change_request=row.get("requires_change_request", False),
        )
        db.add(obj)
        db.flush()
        code_to_id[row["code"]] = obj.id
    return code_to_id


def _seed_workflow(db: Session) -> None:
    for order, row in enumerate(corpus.WORKFLOW, start=1):
        db.add(
            WorkflowTemplate(
                stage_no=row["stage_no"],
                stage_name=corpus.WF_STAGE_NAMES[row["stage_no"]],
                stage_goal=corpus.WF_STAGE_GOALS[row["stage_no"]],
                step_no=row["step_no"],
                name=row["name"],
                action=row["action"],
                tools=row["tools"],
                deliverables=row["deliverables"],
                key_points=row["key_points"],
                sort_order=order,
                is_mandatory=True,
            )
        )


def _seed_knowledge_scenarios(db: Session) -> Dict[str, KnowledgeScenario]:
    """六个痛点场景是知识库和工具箱共用的字典。"""
    existing = {row.code: row for row in db.scalars(select(KnowledgeScenario)).all()}
    for order, (code, name, description) in enumerate(KNOWLEDGE_SCENARIOS, start=1):
        if code in existing:
            continue
        row = KnowledgeScenario(
            code=code,
            name=name,
            description=description,
            sort_order=order,
            is_active=True,
        )
        db.add(row)
        db.flush()
        existing[code] = row
    return existing


def _seed_tools(db: Session, user_ids: Optional[Dict[str, int]] = None) -> None:
    user_ids = user_ids or {}
    scenarios = {row.code: row for row in db.scalars(select(KnowledgeScenario)).all()}
    verified_at = _parse_dt("2026-09-20 10:00:00") or utcnow()
    for order, row in enumerate(corpus.TOOLS, start=1):
        extra = tool_decision_data.TOOL_DECISION_DATA.get(row["code"], {})
        tool = Tool(
            code=row["code"],
            name=row["name"],
            alias=row.get("alias"),
            category=row["category"],
            stage_no=row["stage_no"],
            purpose=row["purpose"],
            when_to_use=row["when_to_use"],
            steps=list(row["steps"]),
            template_ref=row.get("template_ref"),
            pitfalls=row.get("pitfalls"),
            difficulty=extra.get("difficulty", "MEDIUM"),
            typical_duration=extra.get("typical_duration"),
            prerequisites=extra.get("prerequisites"),
            not_applicable_when=extra.get("not_applicable_when"),
            verification_standard=extra.get("verification_standard"),
            owner_user_id=_owner_user_id(extra.get("owner"), user_ids),
            version=1,
            status=ToolStatus.VERIFIED.value if extra else ToolStatus.PUBLISHED.value,
            last_verified_at=verified_at if extra else None,
            review_due_at=(verified_at.date() + timedelta(days=365)) if extra else None,
            is_active=True,
            sort_order=order,
        )
        db.add(tool)
        db.flush()
        for code in extra.get("scenarios", ()):
            scenario = scenarios.get(code)
            if scenario is not None:
                db.add(ToolScenarioLink(tool_id=tool.id, scenario_id=scenario.id, weight=1.0))


def _seed_step_contracts(db: Session) -> None:
    """为 24 个标准步骤生成契约；每阶段最后一步是决策门。"""
    # SessionLocal 是 autoflush=False；先落库，否则下面的 select 看不到刚 add 的步骤
    db.flush()
    existing = set(db.scalars(select(WorkflowTemplate.step_no)).all())
    last_per_stage: Dict[int, str] = {}
    for row in corpus.WORKFLOW:
        last_per_stage[row["stage_no"]] = row["step_no"]

    previous: Optional[dict] = None
    for row in corpus.WORKFLOW:
        step_no = row["step_no"]
        # 输入用上一步的产出描述，保持「上游交付物 → 本步产出」的链条可读
        inputs = (
            f"上游交付物：{previous['deliverables']}"
            if previous
            else "公司战略、年度经营目标与现有制度文件"
        )
        if step_no in existing:
            db.add(
                StepContract(
                    step_no=step_no,
                    inputs=inputs,
                    tool_codes=deliverable_data.STEP_TOOL_CODES.get(step_no, []),
                    tool_levels=deliverable_data.STEP_TOOL_LEVELS.get(step_no, {}),
                    acceptance_criteria=deliverable_data.STAGE_ACCEPTANCE.get(row["stage_no"]),
                    owner_role=deliverable_data.STEP_OWNER_ROLES.get(step_no),
                    decision_gate=last_per_stage.get(row["stage_no"]) == step_no,
                )
            )
        previous = row


def backfill_step_contract_levels(db: Session) -> int:
    """升级已有库：只给还没有 tool_levels 的契约补标准使用要求，不覆盖人工配置。"""
    changed = 0
    for contract in db.scalars(select(StepContract)).all():
        if contract.tool_levels:
            continue
        levels = deliverable_data.STEP_TOOL_LEVELS.get(contract.step_no, {})
        if levels:
            contract.tool_levels = levels
            changed += 1
    db.flush()
    return changed


def _seed_deliverable_definitions(db: Session) -> None:
    db.flush()
    existing = set(db.scalars(select(WorkflowTemplate.step_no)).all())
    per_step_order: Dict[str, int] = {}
    for row in deliverable_data.DELIVERABLES:
        if row["step_no"] not in existing:
            continue
        order = per_step_order.get(row["step_no"], 0) + 1
        per_step_order[row["step_no"]] = order
        db.add(
            DeliverableDefinition(
                code=row["code"],
                name=row["name"],
                step_no=row["step_no"],
                type=row["type"],
                required=True,
                acceptance_criteria=deliverable_data.STAGE_ACCEPTANCE.get(
                    int(row["step_no"].split(".")[0])
                ),
                sort_order=order,
                is_active=True,
            )
        )


def _seed_projects(
    db: Session, code_to_id: Dict[str, int], user_ids: Dict[str, int]
) -> Dict[str, int]:
    ids: Dict[str, int] = {}
    for row in corpus_data.PROJECTS:
        baseline = row.get("baseline_value")
        target = row.get("target_value")
        improvement = None
        if baseline and target:
            improvement = round(abs(baseline - target) / abs(baseline) * 100, 1)
        obj = Project(
            code=row["code"],
            name=row["name"],
            methodology=row["methodology"],
            status=row["status"],
            current_stage=row["current_stage"],
            priority=row["priority"],
            process_id=code_to_id.get(row["process"]) if row.get("process") else None,
            owner=row["owner"],
            owner_user_id=_owner_user_id(row["owner"], user_ids),
            sponsor=row.get("sponsor"),
            department=row.get("department"),
            objective=row.get("objective"),
            scope=row.get("scope"),
            metric_name=row.get("metric_name"),
            baseline_value=baseline,
            target_value=target,
            current_value=row.get("current_value"),
            metric_unit=row.get("metric_unit"),
            improvement_pct=improvement,
            budget=row.get("budget", 0.0),
            actual_cost=row.get("actual_cost", 0.0),
            roi_estimate=row.get("roi_estimate"),
            start_date=_parse_date(row.get("start_date")),
            end_date=_parse_date(row.get("end_date")),
        )
        db.add(obj)
        db.flush()
        seed_project_steps(db, obj)
        db.flush()
        deliverable_service.sync_project_instances(db, obj)
        recompute_progress(db, obj)
        ids[row["code"]] = obj.id
    return ids


def _seed_benchmarks(
    db: Session, code_to_id: Dict[str, int], *, with_mappings: bool = True
) -> None:
    """SCOR 手写分类 + APQC PCF v8.0 三套变体、指标目录与流程映射。

    APQC 数据来自 `app/seed/data/pcf_v80.json`（由 scripts/import_pcf.py 生成），
    分类和映射都以 PCF ID（external_id）为稳定键。

    with_mappings=False 只灌框架、分类与指标，供生产环境使用：公司流程还没录入时
    不存在可映射的流程，等流程建好后再通过页面/API 维护映射。
    """
    frameworks: Dict[str, BenchmarkFramework] = {}
    for row in benchmark_data.BENCHMARK_FRAMEWORKS:
        framework = BenchmarkFramework(
            code=row["code"],
            name=row["name"],
            name_en=row.get("name_en"),
            version=row.get("version"),
            description=row.get("description"),
            sort_order=row.get("sort_order", 0),
        )
        db.add(framework)
        db.flush()
        frameworks[framework.code] = framework

    pcf_dataset = pcf_data.load_pcf_v80()
    for row in pcf_dataset["frameworks"]:
        base_code = row.get("base_framework_code")
        base = frameworks.get(base_code) if base_code else None
        framework = BenchmarkFramework(
            code=row["code"],
            name=row["name"],
            name_en=row.get("name_en"),
            version=row.get("version"),
            description=row.get("description"),
            sort_order=row.get("sort_order", 0),
            industry=row.get("industry"),
            is_primary=row.get("is_primary", False),
            base_framework_id=base.id if base else None,
            source_file=row.get("source_file"),
            generated_on=row.get("generated_on"),
            attribution=row.get("attribution"),
        )
        db.add(framework)
        db.flush()
        frameworks[framework.code] = framework

    # 两个解析表：SCOR 用 code，APQC 用 external_id（PCF ID）。
    categories_by_code: Dict[tuple[str, str], BenchmarkCategory] = {}
    categories_by_external: Dict[tuple[str, str], BenchmarkCategory] = {}

    for row in sorted(benchmark_data.BENCHMARK_CATEGORIES, key=lambda r: r["level"]):
        framework = frameworks.get(row["framework"])
        if framework is None:
            raise ValueError(f"对标分类 {row['code']} 引用了未知框架 {row['framework']}")
        parent_code = row.get("parent")
        parent = categories_by_code.get((row["framework"], parent_code)) if parent_code else None
        if parent_code and parent is None:
            raise ValueError(f"对标分类 {row['code']} 的父节点 {parent_code} 尚未入库，检查顺序")
        category = BenchmarkCategory(
            framework_id=framework.id,
            code=row["code"],
            name=row["name"],
            name_en=row.get("name_en"),
            level=row["level"],
            parent_id=parent.id if parent else None,
            sort_order=row.get("sort", 0),
        )
        db.add(category)
        db.flush()
        categories_by_code[(framework.code, category.code)] = category

    for pcf_framework in pcf_dataset["frameworks"]:
        framework = frameworks[pcf_framework["code"]]
        by_external: Dict[str, BenchmarkCategory] = {}
        for row in sorted(pcf_framework["categories"], key=lambda r: r["level"]):
            category = BenchmarkCategory(
                framework_id=framework.id,
                code=row["code"],
                name=row["name"],
                name_en=row.get("name_en"),
                name_zh=row.get("name_zh"),
                name_zh_source=row.get("name_zh_source"),
                external_id=row["external_id"],
                level=row["level"],
                description=row.get("description"),
                description_zh=row.get("description_zh"),
                metrics_available=row.get("metrics_available", False),
                difference_index=row.get("difference_index", 0),
                change_details=row.get("change_details"),
                sort_order=row.get("sort_order", 0),
            )
            db.add(category)
            by_external[row["external_id"]] = category
        db.flush()
        for row in pcf_framework["categories"]:
            parent_external = row.get("parent_external_id")
            if parent_external:
                by_external[row["external_id"]].parent_id = by_external[parent_external].id
        db.flush()
        categories_by_external.update(
            {
                (framework.code, external_id): category
                for external_id, category in by_external.items()
            }
        )
        categories_by_code.update(
            {(framework.code, category.code): category for category in by_external.values()}
        )

    if (db.scalar(select(func.count()).select_from(BenchmarkMetric)) or 0) == 0:
        db.add_all(
            [
                BenchmarkMetric(
                    external_id=row["external_id"],
                    metric_id=row["metric_id"],
                    metric_category=row.get("metric_category"),
                    name=row["name"],
                    formula=row.get("formula"),
                    unit=row.get("unit"),
                    source=row.get("source"),
                    name_zh=row.get("name_zh"),
                    formula_zh=row.get("formula_zh"),
                    unit_zh=row.get("unit_zh"),
                    category_label_zh=row.get("category_label_zh"),
                    translation_source=row.get("translation_source"),
                )
                for row in pcf_data.metric_rows()
            ]
        )
        db.flush()

    if not with_mappings:
        return

    def resolve_category(row: Dict[str, str]) -> Optional[BenchmarkCategory]:
        if row.get("external_id"):
            return categories_by_external.get((row["framework"], row["external_id"]))
        return categories_by_code.get((row["framework"], row["category"]))

    for row in benchmark_data.PROCESS_BENCHMARK_MAP:
        process_id = code_to_id.get(row["process"])
        category = resolve_category(row)
        if process_id is None:
            raise ValueError(f"对标映射引用了未知流程 {row['process']}")
        if category is None:
            key = row.get("external_id") or row.get("category")
            raise ValueError(f"对标映射引用了未知分类 {row['framework']} / {key}")
        db.add(
            ProcessBenchmarkMap(
                process_id=process_id,
                category_id=category.id,
                note=row.get("note"),
            )
        )

    # L4 活动默认继承所属 L3 的对标分类，避免每个活动都手写一条映射。
    # 已显式映射过的活动（如 L4-201…205）保持原样。
    process_rows = db.scalars(select(ProcessArch)).all()
    mapped_categories: Dict[int, List[int]] = {}
    for row in benchmark_data.PROCESS_BENCHMARK_MAP:
        process_id = code_to_id[row["process"]]
        category = resolve_category(row)
        if category is not None:
            mapped_categories.setdefault(process_id, []).append(category.id)
    for process in process_rows:
        if process.level != 4 or process.id in mapped_categories:
            continue
        for category_id in mapped_categories.get(process.parent_id, []):
            db.add(
                ProcessBenchmarkMap(
                    process_id=process.id,
                    category_id=category_id,
                    note="继承上级流程",
                )
            )


def _seed_kpis(db: Session, code_to_id: Dict[str, int], user_ids: Dict[str, int]) -> Dict[str, int]:
    periods = [date.fromisoformat(p) for p in corpus_data.KPI_PERIODS]
    ids: Dict[str, int] = {}
    for row in corpus_data.KPIS:
        card = corpus_data.KPI_DEFINITION_CARDS[row["code"]]
        owner_name = row.get("owner")
        kpi = KpiDefinition(
            code=row["code"],
            name=row["name"],
            dimension=row["dimension"],
            kind=card["kind"],
            direction=row["direction"],
            unit=row.get("unit"),
            target_value=row.get("target_value"),
            baseline_value=row.get("baseline_value"),
            description=row.get("description"),
            formula=card.get("formula"),
            numerator=card.get("numerator"),
            denominator=card.get("denominator"),
            granularity=card.get("granularity"),
            frequency=card["frequency"],
            source_system=card.get("source_system"),
            quality_rule=card.get("quality_rule"),
            red_threshold=card.get("red_threshold"),
            yellow_threshold=card.get("yellow_threshold"),
            green_threshold=card.get("green_threshold"),
            process_id=code_to_id.get(row["process"]) if row.get("process") else None,
            owner=owner_name,
            owner_user_id=_owner_user_id(owner_name, user_ids),
            version=1,
            valid_from=(date.fromisoformat(card["valid_from"]) if card.get("valid_from") else None),
            valid_to=date.fromisoformat(card["valid_to"]) if card.get("valid_to") else None,
            is_active=True,
        )
        db.add(kpi)
        db.flush()
        ids[row["code"]] = kpi.id
        for period, value in zip(periods, row["values"], strict=False):
            db.add(KpiRecord(kpi_id=kpi.id, period=period, value=float(value)))
    return ids


def _seed_strategy(
    db: Session,
    code_to_id: Dict[str, int],
    user_ids: Dict[str, int],
    kpi_ids: Dict[str, int],
) -> None:
    for row in strategy_data.STRATEGY_OBJECTIVES:
        owner_name = row.get("owner")
        objective = StrategyObjective(
            code=row["code"],
            name=row["name"],
            description=row.get("description"),
            year=row["year"],
            period=row["period"],
            baseline_value=row.get("baseline_value"),
            target_value=row.get("target_value"),
            unit=row.get("unit"),
            source_document=row.get("source_document"),
            owner=owner_name,
            owner_user_id=_owner_user_id(owner_name, user_ids),
            status=row.get("status", "ACTIVE"),
        )
        db.add(objective)
        db.flush()
        for link in row.get("links", []):
            process_id = code_to_id.get(link["process"])
            if not process_id:
                continue
            kpi_id = kpi_ids.get(link["kpi"]) if link.get("kpi") else None
            db.add(
                ObjectiveProcessLink(
                    objective_id=objective.id,
                    process_id=process_id,
                    kpi_id=kpi_id,
                    note=link.get("note"),
                )
            )
    db.flush()


def _seed_workload(
    db: Session,
    code_to_id: Dict[str, int],
    position_ids: Dict[str, int],
    org_ids: Dict[str, int],
    user_ids: Dict[str, int],
) -> None:
    verifier_id = user_ids.get("流程管理科")
    for row in workload_data.WORK_MEASUREMENT_STANDARDS:
        activity_id = code_to_id.get(row["activity"])
        position_id = position_ids.get(row["position"])
        if not activity_id or not position_id:
            continue
        verified = row["status"] == "VERIFIED"
        db.add(
            WorkMeasurementStandard(
                code=row["code"],
                name=row["name"],
                activity_id=activity_id,
                position_id=position_id,
                org_unit_id=org_ids.get(row["org"]) if row.get("org") else None,
                method_description=row.get("method"),
                source=row["source"],
                observed_minutes=row["observed_minutes"],
                rating_factor=row["rating_factor"],
                allowance_rate=row["allowance_rate"],
                standard_minutes=workload_service.compute_standard_minutes(
                    row["observed_minutes"], row["rating_factor"], row["allowance_rate"]
                ),
                sample_size=row["sample_size"],
                monthly_frequency=row["monthly_frequency"],
                status=row["status"],
                version=1,
                valid_from=(
                    date.fromisoformat(row["valid_from"]) if row.get("valid_from") else None
                ),
                valid_to=date.fromisoformat(row["valid_to"]) if row.get("valid_to") else None,
                note=row.get("note"),
                verified_by_id=verifier_id if verified else None,
                verified_at=utcnow() if verified else None,
                created_by_id=verifier_id,
            )
        )
    for row in workload_data.CAPACITY_CALENDAR:
        org_id = org_ids.get(row["org"])
        position_id = position_ids.get(row["position"])
        if not org_id or not position_id:
            continue
        db.add(
            CapacityCalendar(
                org_unit_id=org_id,
                position_id=position_id,
                period=date.fromisoformat(row["period"]),
                headcount=row["headcount"],
                available_hours_per_person=row["available_hours_per_person"],
                attendance_rate=row["attendance_rate"],
                equipment_availability=row["equipment_availability"],
                note=row.get("note"),
            )
        )
    db.flush()


def _seed_changes(db: Session, code_to_id: Dict[str, int], user_ids: Dict[str, int]) -> None:
    for row in change_data.CHANGE_REQUESTS:
        process_id = code_to_id.get(row["process"])
        if not process_id:
            continue
        requester = row.get("requested_by")
        db.add(
            ProcessChangeRequest(
                code=row["code"],
                process_id=process_id,
                title=row["title"],
                reason=row.get("reason"),
                scope=row.get("scope"),
                change_type=row.get("change_type", "STRUCTURE"),
                impact_level=row.get("impact_level", "MINOR"),
                version_label=row.get("version_label"),
                impact=row.get("impact") or {},
                test_evidence=row.get("test_evidence"),
                rollback_plan=row.get("rollback_plan"),
                effective_date=(
                    date.fromisoformat(row["effective_date"]) if row.get("effective_date") else None
                ),
                emergency=row.get("emergency", False),
                status=row.get("status", "DRAFT"),
                requested_by_id=_owner_user_id(requester, user_ids),
                requested_by_name=requester,
            )
        )
    db.flush()


def _seed_governance_roles(db: Session, user_ids: Dict[str, int]) -> Dict[str, int]:
    ids: Dict[str, int] = {}
    for row in raci_data.GOVERNANCE_ROLES:
        role = GovernanceRole(
            code=row["code"],
            name=row["name"],
            role_type=row["role_type"],
            description=row.get("description"),
            is_active=True,
        )
        db.add(role)
        db.flush()
        ids[row["code"]] = role.id
        for member in row.get("members", []):
            user_id = user_ids.get(member["user"])
            if not user_id:
                continue
            db.add(
                GovernanceRoleMember(
                    role_id=role.id,
                    user_id=user_id,
                    is_primary=member.get("is_primary", False),
                )
            )
    db.flush()
    return ids


def _seed_raci(db: Session, code_to_id: Dict[str, int], role_ids: Dict[str, int]) -> None:
    for row in raci_data.RACI_ASSIGNMENTS:
        process_id = code_to_id.get(row["process"])
        role_id = role_ids.get(row["role"])
        if not process_id or not role_id:
            continue
        db.add(
            RaciAssignment(
                process_id=process_id,
                matter=row["matter"],
                role_id=role_id,
                raci=row["raci"],
                note=row.get("note"),
            )
        )
    db.flush()


def _seed_authorization(
    db: Session,
    code_to_id: Dict[str, int],
    role_ids: Dict[str, int],
    user_ids: Dict[str, int],
) -> None:
    now = utcnow()
    for row in authorization_data.AUTHORIZATION_RULES:
        process_id = code_to_id.get(row["process"]) if row.get("process") else None
        db.add(
            AuthorizationRule(
                code=row["code"],
                title=row["title"],
                matter=row["matter"],
                process_id=process_id,
                category=row["category"],
                risk_level=row["risk_level"],
                amount_limit=row["amount_limit"],
                impact_scope=row.get("impact_scope"),
                reversibility=row.get("reversibility"),
                frequency=row.get("frequency"),
                approver_role_id=role_ids.get(row.get("approver_role")),
                approver_label=row.get("approver_label"),
                exception_path=row.get("exception_path"),
                evidence_required=row.get("evidence_required"),
                status=row["status"],
                version=1,
                owner_user_id=_owner_user_id(row.get("owner"), user_ids),
            )
        )
    db.flush()

    rules = {row.code: row.id for row in db.scalars(select(AuthorizationRule)).all()}
    for row in authorization_data.AUTHORIZATION_EXCEPTIONS:
        rule_id = rules.get(row["rule"])
        if not rule_id:
            continue
        decided = row["status"] != "REQUESTED"
        db.add(
            AuthorizationException(
                code=row["code"],
                rule_id=rule_id,
                process_id=code_to_id.get(row["process"]) if row.get("process") else None,
                title=row["title"],
                reason=row["reason"],
                scope=row.get("scope"),
                status=row["status"],
                requested_by_id=_owner_user_id(row.get("requested_by"), user_ids),
                requested_by_name=row.get("requested_by"),
                requested_at=now,
                decided_by_id=_owner_user_id(row.get("decided_by"), user_ids),
                decided_by_name=row.get("decided_by"),
                decided_at=now if decided else None,
                decision_note=row.get("decision_note"),
                expires_at=(
                    datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else None
                ),
            )
        )
    db.flush()


def _seed_data_governance(
    db: Session, code_to_id: Dict[str, int], user_ids: Dict[str, int]
) -> None:
    domain_ids: Dict[str, int] = {}
    for row in data_governance_data.DATA_DOMAINS:
        domain = DataDomain(
            code=row["code"],
            name=row["name"],
            domain_type=row["domain_type"],
            owner_user_id=_owner_user_id(row.get("owner"), user_ids),
            steward_user_id=_owner_user_id(row.get("steward"), user_ids),
            description=row.get("description"),
            is_active=True,
        )
        db.add(domain)
        db.flush()
        domain_ids[row["code"]] = domain.id
    for row in data_governance_data.DATA_FLOWS:
        domain_id = domain_ids.get(row["domain"])
        if not domain_id:
            continue
        db.add(
            DataFlow(
                code=row["code"],
                name=row["name"],
                domain_id=domain_id,
                process_id=code_to_id.get(row["process"]) if row.get("process") else None,
                source_system=row.get("source_system"),
                target_system=row.get("target_system"),
                frequency=row.get("frequency", "DAILY"),
                primary_key=row.get("primary_key"),
                field_definitions=row.get("field_definitions"),
                allowed_values=row.get("allowed_values"),
                quality_rule=row.get("quality_rule"),
                purpose=row.get("purpose"),
                retention_period=row.get("retention_period"),
                cross_legal_visibility=row.get("cross_legal_visibility"),
                data_subject_rights=row.get("data_subject_rights"),
                is_active=True,
            )
        )
    db.flush()


def _seed_exceptions(
    db: Session,
    code_to_id: Dict[str, int],
    project_ids: Dict[str, int],
    user_ids: Dict[str, int],
) -> None:
    for row in corpus_data.EXCEPTIONS:
        detected = _parse_dt(row.get("detected_at")) or utcnow()
        settled = _parse_dt(row.get("due_at")) or detected
        closed = row["status"] == "CLOSED"
        db.add(
            ExceptionEvent(
                code=row["code"],
                title=row["title"],
                description=row.get("description"),
                severity=row["severity"],
                status=row["status"],
                process_id=code_to_id.get(row["process"]) if row.get("process") else None,
                project_id=project_ids.get(row["project"]) if row.get("project") else None,
                owner=row.get("owner"),
                owner_user_id=_owner_user_id(row.get("owner"), user_ids),
                detected_at=detected,
                due_at=_parse_dt(row.get("due_at")),
                resolved_at=settled if row["status"] in ("RESOLVED", "CLOSED") else None,
                closed_at=settled if closed else None,
                root_cause=row.get("root_cause"),
                action_taken=row.get("action_taken"),
            )
        )


def _seed_forms_rules(db: Session, code_to_id: Dict[str, int]) -> None:
    """给采购需求提报配上运行时表单与一条自动分支规则。"""
    process_id = code_to_id.get("L3-032")
    if process_id is None:
        return
    db.add(
        FormDefinition(
            process_id=process_id,
            node_key="n1",
            name="需求发起",
            fields=[
                {"key": "applicant", "label": "申请人", "type": "text", "required": True},
                {
                    "key": "amount",
                    "label": "预计金额（元）",
                    "type": "number",
                    "required": True,
                    "min": 0,
                },
                {
                    "key": "description",
                    "label": "需求说明",
                    "type": "textarea",
                    "required": False,
                },
            ],
        )
    )
    db.add(
        FormDefinition(
            process_id=process_id,
            node_key="n4",
            name="需求审批",
            fields=[
                {
                    "key": "approved",
                    "label": "是否通过",
                    "type": "select",
                    "required": True,
                    "options": ["是", "否"],
                },
                {
                    "key": "comment",
                    "label": "审批意见",
                    "type": "textarea",
                    "required": False,
                },
            ],
        )
    )
    db.add(
        ProcessRule(
            process_id=process_id,
            node_key="n4",
            name="审批通过 → 采购计划生成",
            conditions=[{"field": "approved", "op": "eq", "value": "是"}],
            target_node_key="n5",
            priority=10,
        )
    )


def _seed_execution(
    db: Session,
    code_to_id: Dict[str, int],
    project_ids: Dict[str, int],
    user_ids: Dict[str, int],
) -> None:
    """灌两个演示实例：一个留待办（含已指派），一个在公共队列。"""
    admin = db.scalar(select(User).where(User.username == "admin"))
    if admin is None or not code_to_id:
        return
    db.flush()  # 设计器节点/连线可能还在会话里，先落库再快照

    # L3-032：完成前两步，留下第二阶段的待办并指派给陈经理
    process = db.get(ProcessArch, code_to_id["L3-032"])
    if process is not None:
        instance = execution_service.start_instance(
            db,
            process,
            admin,
            InstanceStartRequest(
                process_id=process.id,
                project_id=project_ids.get("PR-2026-018"),
                variables={"source": "seed", "batch": "2026-Q3"},
            ),
        )
        for _ in range(2):
            task = db.scalar(
                select(ProcessTask)
                .where(
                    ProcessTask.instance_id == instance.id,
                    ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
                )
                .order_by(ProcessTask.id)
            )
            if task is None:
                break
            execution_service.complete_task(
                db,
                task,
                admin,
                TaskCompleteRequest(
                    form_data={
                        "applicant": "种子演示",
                        "amount": 10000,
                        "description": "演示数据",
                    }
                    if task.node_key == "n1"
                    else None,
                    comment="种子演示：已处理",
                ),
            )
        open_task = db.scalar(
            select(ProcessTask)
            .where(
                ProcessTask.instance_id == instance.id,
                ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
            )
            .order_by(ProcessTask.id)
        )
        chen_id = user_ids.get("陈经理")
        if open_task is not None and chen_id is not None:
            execution_service.assign_task(db, open_task, chen_id)

    # L3-033：停在公共任务队列，演示认领
    process = db.get(ProcessArch, code_to_id["L3-033"])
    if process is not None:
        execution_service.start_instance(
            db,
            process,
            admin,
            InstanceStartRequest(
                process_id=process.id,
                variables={"source": "seed", "batch": "2026-Q3"},
            ),
        )


def _seed_integrations(db: Session) -> None:
    """放一个未启用的 ERP 示例端点，演示但不产生真实外发。"""
    db.add(
        IntegrationEndpoint(
            code="ERP-DEMO",
            name="ERP 事件接收（示例）",
            kind="ERP",
            url="https://erp.example.com/hooks/logix",
            secret="demo-secret-change-me",
            events=["instance.completed", "exception.created"],
            is_active=False,
        )
    )


def _seed_notifications(db: Session, user_ids: Dict[str, int]) -> None:
    """给陈经理生成两条演示通知：一条任务指派、一条异常超期。"""
    chen_id = user_ids.get("陈经理")
    if chen_id is None:
        return
    task = db.scalar(
        select(ProcessTask)
        .where(
            ProcessTask.assignee_user_id == chen_id,
            ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
        )
        .order_by(ProcessTask.id)
    )
    if task is not None:
        notification_service.notify(
            db,
            chen_id,
            "TASK_ASSIGNED",
            f"新任务：{task.name}",
            f"{task.instance.process_name}（{task.instance.code}）",
            link="execution",
            entity_type="process_task",
            entity_id=task.id,
        )
    admin_id = user_ids.get("系统管理员")
    if admin_id is not None:
        notification_service.notify(
            db,
            admin_id,
            "SYSTEM",
            "欢迎使用 Logix PMS",
            "演示数据已就绪：流程执行、表单规则与 BPMN 导入导出均可体验。",
            link="dashboard",
        )

    exception = db.scalar(select(ExceptionEvent).where(ExceptionEvent.code == "EXC-2026-001"))
    if exception is not None and exception.due_at and exception.due_at < utcnow():
        notification_service.notify(
            db,
            chen_id,
            "EXCEPTION_OVERDUE",
            f"异常已超期：{exception.title}",
            f"{exception.code} · 要求闭环时间 {exception.due_at:%Y-%m-%d %H:%M}",
            link="monitor",
            entity_type="exception",
            entity_id=exception.id,
        )


KNOWLEDGE_SCENARIOS = [
    ("FLOW", "流程混乱", "环节不清、重复交接、部门墙"),
    ("CYCLE", "周期太长", "等待多、节拍不稳、交付慢"),
    ("ERROR", "差错返工多", "反复出错、客诉、质量波动"),
    ("RACI", "责任不清", "多头负责、互相推诿、权责冲突"),
    ("COST", "成本过高", "浪费多、投入产出低"),
    ("STANDARD", "缺少标准", "靠经验、各做各的、无法复制"),
]

KNOWLEDGE_TOOL_SCENARIOS = {
    "BPR6": ("FLOW", "STANDARD"),
    "VSM": ("CYCLE", "COST"),
    "RACI": ("RACI", "FLOW"),
    "ADKAR": ("FLOW", "RACI"),
    "KAIZEN": ("COST", "CYCLE"),
    "PARETO": ("ERROR", "COST"),
    "PILOT": ("STANDARD", "FLOW"),
    "BALANCED-SCORE": ("STANDARD",),
    "FIVE-WHY": ("ERROR",),
    "FISHBONE": ("ERROR",),
    "DMAIC": ("ERROR", "CYCLE"),
}

# 工具的主阶段之外，知识在五阶段里的其他使用现场
KNOWLEDGE_TOOL_EXTRA_STAGES = {
    "BPR6": (1,),
    "RACI": (1,),
    "VSM": (3,),
    "PARETO": (3,),
    "PILOT": (1,),
    "KAIZEN": (4,),
    "BALANCED-SCORE": (5,),
}

KNOWLEDGE_VERIFIED_TOOLS = {"RACI", "VSM", "PARETO", "ADKAR"}
KNOWLEDGE_BEST_PRACTICE_TOOLS = {"RACI", "VSM", "ADKAR"}

KNOWLEDGE_USAGE_SEED = {
    "RACI": [
        ("EFFECTIVE", "采购流程权责梳理，多头负责问题消除", 18),
        ("EFFECTIVE", "审批链压缩到 3 层", 12),
        ("EFFECTIVE", "跨部门争议减少", 8),
        ("PARTIAL", "首次使用时 A 角色仍有争议", 3),
    ],
    "VSM": [
        ("EFFECTIVE", "轧制工段端到端周期下降 21%", 20),
        ("EFFECTIVE", "识别出 3 处主要等待", 10),
        ("PARTIAL", "现场观测样本偏少", 4),
    ],
    "PARETO": [
        ("EFFECTIVE", "定位出 78% 客诉集中在 3 类", 15),
        ("EFFECTIVE", "优先改善项从 12 个收敛到 3 个", 6),
    ],
    "ADKAR": [
        ("EFFECTIVE", "中层抵触明显下降", 14),
        ("PARTIAL", "沟通节奏需要按部门调整", 5),
    ],
}


def _seed_knowledge(db: Session, project_ids: Dict[str, int], user_ids: Dict[str, int]) -> None:
    scenarios = _seed_knowledge_scenarios(db)

    tool_stages = {
        code: stage for code, stage in db.execute(select(Tool.code, Tool.stage_no)).all()
    }
    admin_id = user_ids.get("系统管理员")
    verified_at = _parse_dt("2026-09-20 10:00:00") or utcnow()

    for row in corpus_data.KNOWLEDGE:
        tool_code = row.get("tool_code")
        item_type = "METHOD" if row["type"] == "BEST_PRACTICE" else row["type"]
        status = (
            KnowledgeStatus.ARCHIVED.value
            if item_type == "STANDARD"
            else KnowledgeStatus.VERIFIED.value
            if tool_code in KNOWLEDGE_VERIFIED_TOOLS
            else KnowledgeStatus.PUBLISHED.value
        )
        created = _parse_dt(row.get("created")) or _parse_dt("2026-09-01 09:00:00")
        item = KnowledgeItem(
            title=row["title"],
            type=item_type,
            status=status,
            methodology=row.get("methodology"),
            summary=row["summary"],
            content=row["content"],
            claim=row["summary"],
            applicable_when="；".join(row.get("tags", [])) or None,
            not_applicable_when="需要强制执行的制度条款请走制度中心；"
            "本条目是参考方法，不替代正式标准文件。",
            evidence_summary="演示数据：由流程管理科整理的历史使用记录。",
            version=1,
            owner_user_id=_owner_user_id(row.get("author"), user_ids),
            verified_by_user_id=admin_id if status == KnowledgeStatus.VERIFIED.value else None,
            last_verified_at=verified_at if status == KnowledgeStatus.VERIFIED.value else None,
            review_due_at=(verified_at.date() + timedelta(days=365))
            if status == KnowledgeStatus.VERIFIED.value
            else None,
            is_best_practice=tool_code in KNOWLEDGE_BEST_PRACTICE_TOOLS,
            promoted_at=verified_at if tool_code in KNOWLEDGE_BEST_PRACTICE_TOOLS else None,
            process_id=None,
            project_id=project_ids.get("PR-2026-018") if item_type == "CASE" else None,
            tool_code=tool_code,
            author=row.get("author"),
            download_count=row.get("download_count", 0),
            created_at=created,
            updated_at=created,
        )
        db.add(item)
        db.flush()

        seen = set()
        for tag in row.get("tags", []):
            tag = (tag or "").strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            db.add(KnowledgeTag(knowledge_id=item.id, tag=tag))

        for code in KNOWLEDGE_TOOL_SCENARIOS.get(tool_code or "", ()):
            db.add(
                KnowledgeScenarioLink(
                    knowledge_id=item.id,
                    scenario_id=scenarios[code].id,
                    weight=1.0,
                )
            )
        stage_no = tool_stages.get(tool_code or "")
        wanted_stages = set(KNOWLEDGE_TOOL_EXTRA_STAGES.get(tool_code or "", ()))
        if stage_no is not None:
            wanted_stages.add(stage_no)
        for wanted_stage in sorted(wanted_stages):
            db.add(
                KnowledgeWorkflowLink(
                    knowledge_id=item.id,
                    stage_no=wanted_stage,
                    step_no="",
                    is_primary=wanted_stage == stage_no,
                )
            )

        for outcome, note, days_ago in KNOWLEDGE_USAGE_SEED.get(tool_code or "", []):
            db.add(
                KnowledgeUsage(
                    knowledge_id=item.id,
                    project_id=project_ids.get("PR-2026-018"),
                    used_by_user_id=admin_id,
                    used_at=created + timedelta(days=days_ago),
                    outcome=outcome,
                    note=note,
                )
            )


def _seed_design_models(
    db: Session,
    code_to_id: Dict[str, int],
    position_ids: Optional[Dict[str, int]] = None,
) -> None:
    position_ids = position_ids or {}
    l4_by_parent_name = {
        (row.parent_id, row.name): row.id
        for row in db.scalars(select(ProcessArch).where(ProcessArch.level == 4)).all()
    }
    for process_code, model in corpus_data.DESIGN_MODELS.items():
        process_id = code_to_id.get(process_code)
        if process_id is None:
            continue

        lane_order: List[str] = []
        for node in model["nodes"]:
            if node["lane"] not in lane_order:
                lane_order.append(node["lane"])
        lane_index = {lane: i for i, lane in enumerate(lane_order)}

        for seq, node in enumerate(model["nodes"], start=1):
            row = lane_index[node["lane"]]
            db.add(
                ProcessNode(
                    process_id=process_id,
                    node_key=node["key"],
                    name=node["name"],
                    node_type=node["type"],
                    lane=node["lane"],
                    owner_role=node.get("owner"),
                    process_arch_id=l4_by_parent_name.get((process_id, node["name"])),
                    owner_position_id=position_ids.get(node.get("owner") or ""),
                    duration_minutes=float(node.get("dur", 0)),
                    wait_minutes=float(node.get("wait", 0)),
                    cost=float(node.get("cost", 0)),
                    rework_rate=float(node.get("rework", 0)),
                    approval_levels=int(node.get("levels", 0)),
                    is_value_added=bool(node.get("va", True)),
                    sequence_order=seq,
                    position_x=float(NODE_WIDTH * seq),
                    position_y=float(LANE_HEIGHT * row),
                )
            )
        for edge in model["edges"]:
            db.add(
                ProcessEdge(
                    process_id=process_id,
                    source_key=edge["src"],
                    target_key=edge["dst"],
                    label=edge.get("label"),
                    condition=edge.get("condition"),
                    probability=float(edge.get("p", 1.0)),
                )
            )


# ------------------------------------------------------------------ 入口


def _seed_org_units(db: Session) -> Dict[str, int]:
    """演示用组织树。生产不灌：组织编码由系统管理员通过 /org-units 维护。"""
    ids: Dict[str, int] = {}

    def add(code: str, name: str, org_type: str, parent: Optional[OrgUnit] = None) -> OrgUnit:
        org = OrgUnit(
            code=code,
            name=name,
            type=org_type,
            parent_id=parent.id if parent else None,
        )
        db.add(org)
        db.flush()
        org.path = (parent.path if parent else "/") + f"{org.id}/"
        db.flush()
        ids[code] = org.id
        return org

    group = add("GROUP-001", "集团总部", "GROUP")
    east = add("CO-EAST", "华东分公司", "COMPANY", group)
    add("CO-SOUTH", "华南分公司", "COMPANY", group)
    add("DEPT-EAST-MFG", "华东制造部", "DEPARTMENT", east)
    add("DEPT-EAST-QA", "华东质量部", "DEPARTMENT", east)
    # 与流程架构里的 department 名称对齐，便于组织口径汇总与回填
    add("DEPT-STR", "战略部", "DEPARTMENT", group)
    add("DEPT-RD", "研发中心", "DEPARTMENT", group)
    add("DEPT-PROC", "采购部", "DEPARTMENT", group)
    add("DEPT-FIN", "财务部", "DEPARTMENT", group)
    add("DEPT-MFG", "制造部", "DEPARTMENT", group)
    add("DEPT-SALES", "销售运营部", "DEPARTMENT", group)
    add("DEPT-CS", "客户服务中心", "DEPARTMENT", group)
    add("DEPT-FUNC", "职能中心", "DEPARTMENT", group)
    return ids


def _seed_positions(db: Session, org_ids: Dict[str, int]) -> Dict[str, int]:
    """从演示设计模型的负责人文本创建岗位，并挂到对应部门。"""
    org_of_position = {
        "采购计划员": "DEPT-PROC",
        "预算会计": "DEPT-FIN",
        "部门负责人": "DEPT-FUNC",
    }
    names = sorted(
        {
            node.get("owner")
            for model in corpus_data.DESIGN_MODELS.values()
            for node in model["nodes"]
            if node.get("owner")
        }
    )
    ids: Dict[str, int] = {}
    for index, name in enumerate(names, start=1):
        position = Position(
            code=f"POS-{index:03d}",
            name=name,
            org_unit_id=org_ids.get(org_of_position.get(name, "")),
            is_active=True,
        )
        db.add(position)
        db.flush()
        ids[name] = position.id
    return ids


def _seed_users(
    db: Session,
    org_ids: Optional[Dict[str, int]] = None,
    position_ids: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    org_ids = org_ids or {}
    position_ids = position_ids or {}
    demo_orgs = {
        "admin": "GROUP-001",
        "manager": "GROUP-001",
        "chen": "CO-EAST",
    }
    demo_positions = {"chen": "采购计划员"}
    for row in corpus_data.USERS:
        db.add(
            User(
                username=row["username"],
                display_name=row["display_name"],
                password_hash=hash_password(row["password"]),
                role=row["role"],
                department=row.get("department"),
                org_unit_id=org_ids.get(demo_orgs.get(row["username"], "")),
                position_id=position_ids.get(demo_positions.get(row["username"], "")),
            )
        )
    db.flush()
    return {u.display_name: u.id for u in db.scalars(select(User)).all()}


def _wipe(db: Session) -> None:
    """按外键依赖倒序清空。

    ProcessArch 自引用，按 L4→L1 逐层删，兼容开启了外键约束的 PostgreSQL。
    """
    for model in (
        DataFlow,
        DataDomain,
        RaciAssignment,
        GovernanceRoleMember,
        GovernanceRole,
        ObjectiveProcessLink,
        StrategyObjective,
        WorkMeasurementStandard,
        CapacityCalendar,
        GovernanceFinding,
        TemplateUsage,
        ToolTemplateVersion,
        ToolTemplate,
        ProcessDocumentVersion,
        ProcessDocument,
        DeliverableVersion,
        DeliverableInstance,
        DeliverableDefinition,
        StepContract,
        FormDefinition,
        ProcessRule,
        ProcessExecutionConfig,
        NodeAssignment,
        TaskWorklog,
        ProcessTask,
        ProcessInstance,
        ProcessTaskEvent,
        IdempotencyRecord,
        ProcessBenchmarkMap,
        BenchmarkMetric,
        ProcessModelVersion,
        ProcessChangeRequest,
        NodeTool,
        ProcessEdge,
        ProcessNode,
        ProjectStep,
        KpiRecord,
        ExceptionEvent,
        KnowledgeTag,
        KnowledgeItem,
        KpiDefinition,
        Sketch,
        Project,
        WorkflowTemplate,
        Tool,
        IntegrationDelivery,
        IntegrationEndpoint,
        InboundEvent,
        InboundWebhook,
        Notification,
        AuditLog,
        User,
        Position,
        OrgUnit,
    ):
        db.query(model).delete()
    for level in (4, 3, 2, 1):
        db.query(ProcessArch).filter(ProcessArch.level == level).delete()
    for level in (5, 4, 3, 2, 1):
        db.query(BenchmarkCategory).filter(BenchmarkCategory.level == level).delete()
    db.query(BenchmarkFramework).delete()
    db.commit()


def seed(db: Session, reset: bool = False) -> Dict[str, int]:
    if reset:
        _wipe(db)

    # 先建组织，再建岗位/用户：演示账号要挂到集团/分公司与岗位
    org_ids = _seed_org_units(db)
    org_name_ids = {org.name: org.id for org in db.scalars(select(OrgUnit)).all()}
    position_ids = _seed_positions(db, org_ids)
    user_ids = _seed_users(db, org_ids, position_ids)
    role_ids = _seed_governance_roles(db, user_ids)
    code_to_id = _seed_process_arch(db, user_ids, org_name_ids)
    _seed_raci(db, code_to_id, role_ids)
    _seed_authorization(db, code_to_id, role_ids, user_ids)
    _seed_data_governance(db, code_to_id, user_ids)
    _seed_workflow(db)
    _seed_knowledge_scenarios(db)
    _seed_tools(db, user_ids)
    _seed_step_contracts(db)
    _seed_deliverable_definitions(db)
    _seed_benchmarks(db, code_to_id)
    project_ids = _seed_projects(db, code_to_id, user_ids)
    kpi_ids = _seed_kpis(db, code_to_id, user_ids)
    _seed_workload(db, code_to_id, position_ids, org_ids, user_ids)
    _seed_strategy(db, code_to_id, user_ids, kpi_ids)
    _seed_exceptions(db, code_to_id, project_ids, user_ids)
    _seed_knowledge(db, project_ids, user_ids)
    _seed_design_models(db, code_to_id, position_ids)
    _seed_changes(db, code_to_id, user_ids)
    _seed_forms_rules(db, code_to_id)
    _seed_execution(db, code_to_id, project_ids, user_ids)
    _seed_notifications(db, user_ids)
    _seed_integrations(db)
    db.commit()

    return {
        "process_arch": db.scalar(select(func.count()).select_from(ProcessArch)) or 0,
        "workflow_steps": db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0,
        "tools": db.scalar(select(func.count()).select_from(Tool)) or 0,
        "step_contracts": db.scalar(select(func.count()).select_from(StepContract)) or 0,
        "deliverable_definitions": db.scalar(
            select(func.count()).select_from(DeliverableDefinition)
        )
        or 0,
        "deliverable_instances": db.scalar(select(func.count()).select_from(DeliverableInstance))
        or 0,
        "deliverable_versions": db.scalar(select(func.count()).select_from(DeliverableVersion))
        or 0,
        "projects": db.scalar(select(func.count()).select_from(Project)) or 0,
        "project_steps": db.scalar(select(func.count()).select_from(ProjectStep)) or 0,
        "kpis": db.scalar(select(func.count()).select_from(KpiDefinition)) or 0,
        "kpi_records": db.scalar(select(func.count()).select_from(KpiRecord)) or 0,
        "exceptions": db.scalar(select(func.count()).select_from(ExceptionEvent)) or 0,
        "knowledge": db.scalar(select(func.count()).select_from(KnowledgeItem)) or 0,
        "knowledge_tags": db.scalar(select(func.count()).select_from(KnowledgeTag)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "org_units": db.scalar(select(func.count()).select_from(OrgUnit)) or 0,
        "positions": db.scalar(select(func.count()).select_from(Position)) or 0,
        "process_nodes": db.scalar(select(func.count()).select_from(ProcessNode)) or 0,
        "process_edges": db.scalar(select(func.count()).select_from(ProcessEdge)) or 0,
        "process_instances": db.scalar(select(func.count()).select_from(ProcessInstance)) or 0,
        "process_tasks": db.scalar(select(func.count()).select_from(ProcessTask)) or 0,
        "form_definitions": db.scalar(select(func.count()).select_from(FormDefinition)) or 0,
        "process_rules": db.scalar(select(func.count()).select_from(ProcessRule)) or 0,
        "notifications": db.scalar(select(func.count()).select_from(Notification)) or 0,
        "integration_endpoints": db.scalar(select(func.count()).select_from(IntegrationEndpoint))
        or 0,
        "integration_deliveries": db.scalar(select(func.count()).select_from(IntegrationDelivery))
        or 0,
        "benchmark_frameworks": db.scalar(select(func.count()).select_from(BenchmarkFramework))
        or 0,
        "benchmark_categories": db.scalar(select(func.count()).select_from(BenchmarkCategory)) or 0,
        "benchmark_mappings": db.scalar(select(func.count()).select_from(ProcessBenchmarkMap)) or 0,
        "benchmark_metrics": db.scalar(select(func.count()).select_from(BenchmarkMetric)) or 0,
    }


def seed_if_empty(db: Session) -> Optional[Dict[str, int]]:
    """库里有流程数据或已有账号就跳过，避免每次启动重复灌。

    已有账号说明这个库已经初始化过：生产环境执行 bootstrap 后流程架构仍为空，
    此时不能再把演示流程/项目灌进来。需要重建演示库请显式 `--reset`。
    """
    existing = db.scalar(select(func.count()).select_from(ProcessArch)) or 0
    if existing:
        return None
    existing_users = db.scalar(select(func.count()).select_from(User)) or 0
    if existing_users:
        return None
    return seed(db, reset=False)


def seed_reference(db: Session) -> Dict[str, int]:
    """只灌生产需要的参考数据，不碰演示业务数据。

    - 24 步标准工作流模板
    - 33 个方法论工具
    - 步骤契约与交付物定义（标准侧，不含项目实例）
    - SCOR 与 APQC PCF v8.0（跨行业/消费品/消费电子）框架、分类与指标目录（不含流程映射）

    组织单元属于主数据，生产环境由管理员通过 `/org-units` 维护，不在这里灌。
    按表判空，可重复执行。
    """
    created = {
        "workflow_steps": 0,
        "tools": 0,
        "step_contracts": 0,
        "deliverable_definitions": 0,
        "step_contract_levels": 0,
        "benchmark_frameworks": 0,
        "benchmark_categories": 0,
        "benchmark_metrics": 0,
    }
    if (db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0) == 0:
        _seed_workflow(db)
        created["workflow_steps"] = len(corpus.WORKFLOW)
    if (db.scalar(select(func.count()).select_from(Tool)) or 0) == 0:
        _seed_knowledge_scenarios(db)
        _seed_tools(db)
        created["tools"] = len(corpus.TOOLS)
    if (db.scalar(select(func.count()).select_from(StepContract)) or 0) == 0:
        _seed_step_contracts(db)
        created["step_contracts"] = len(corpus.WORKFLOW)
    created["step_contract_levels"] = backfill_step_contract_levels(db)
    if (db.scalar(select(func.count()).select_from(DeliverableDefinition)) or 0) == 0:
        _seed_deliverable_definitions(db)
        created["deliverable_definitions"] = len(deliverable_data.DELIVERABLES)
    if (db.scalar(select(func.count()).select_from(BenchmarkFramework)) or 0) == 0:
        _seed_benchmarks(db, {}, with_mappings=False)
        pcf_dataset = pcf_data.load_pcf_v80()
        created["benchmark_frameworks"] = len(benchmark_data.BENCHMARK_FRAMEWORKS) + len(
            pcf_dataset["frameworks"]
        )
        created["benchmark_categories"] = len(benchmark_data.BENCHMARK_CATEGORIES) + sum(
            len(framework["categories"]) for framework in pcf_dataset["frameworks"]
        )
        created["benchmark_metrics"] = len(pcf_dataset["metrics"])
    db.commit()
    return created


def ensure_admin(
    db: Session,
    username: str,
    password: str,
    display_name: str,
    department: Optional[str] = None,
    reset_password: bool = False,
) -> Dict[str, object]:
    """创建首个管理员；已存在同名账号时默认不改口令。

    生产环境不应使用演示账号，所以这里由部署者显式提供用户名和口令。
    """
    username = username.strip()
    if len(username) < 3:
        raise ValueError("管理员用户名至少 3 个字符")
    if len(password) < 8:
        raise ValueError("管理员口令至少 8 个字符")

    user = db.scalar(select(User).where(User.username == username))
    if user is not None:
        if user.role != Role.ADMIN.value:
            raise ValueError(f"账号 {username} 已存在且不是管理员，拒绝覆盖")
        if reset_password:
            user.password_hash = hash_password(password)
            db.commit()
        return {
            "username": username,
            "created": False,
            "password_reset": bool(reset_password),
        }

    user = User(
        username=username,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=Role.ADMIN.value,
        department=department,
    )
    db.add(user)
    db.commit()
    return {"username": username, "created": True, "password_reset": False}


def bootstrap_production(
    db: Session,
    username: str,
    password: str,
    display_name: str,
    department: Optional[str] = None,
    include_reference: bool = True,
    reset_password: bool = False,
) -> Dict[str, object]:
    """生产初始化：参考数据 + 首个管理员，不灌任何演示业务数据。"""
    reference = seed_reference(db) if include_reference else {}
    admin = ensure_admin(
        db,
        username=username,
        password=password,
        display_name=display_name,
        department=department,
        reset_password=reset_password,
    )
    return {"reference": reference, "admin": admin}


def _benchmark_counts(db: Session) -> Dict[str, int]:
    return {
        "benchmark_frameworks": db.scalar(select(func.count()).select_from(BenchmarkFramework))
        or 0,
        "benchmark_categories": db.scalar(select(func.count()).select_from(BenchmarkCategory)) or 0,
        "benchmark_mappings": db.scalar(select(func.count()).select_from(ProcessBenchmarkMap)) or 0,
        "benchmark_metrics": db.scalar(select(func.count()).select_from(BenchmarkMetric)) or 0,
    }


def seed_benchmarks_if_empty(db: Session) -> Optional[Dict[str, int]]:
    """只灌对标框架数据；已有框架则跳过。用于存量库升级后的补灌。"""
    existing = db.scalar(select(func.count()).select_from(BenchmarkFramework)) or 0
    if existing:
        return None
    code_to_id = {p.code: p.id for p in db.scalars(select(ProcessArch)).all()}
    if not code_to_id:
        raise RuntimeError("流程架构为空，请先灌业务种子数据（python -m scripts.seed）")
    _seed_benchmarks(db, code_to_id)
    db.commit()
    return _benchmark_counts(db)


def reset_benchmarks(db: Session) -> Dict[str, int]:
    """只重建对标框架数据，不动业务数据。"""
    db.query(ProcessBenchmarkMap).delete()
    db.query(BenchmarkMetric).delete()
    for level in (5, 4, 3, 2, 1):
        db.query(BenchmarkCategory).filter(BenchmarkCategory.level == level).delete()
    db.query(BenchmarkFramework).delete()
    db.commit()
    code_to_id = {p.code: p.id for p in db.scalars(select(ProcessArch)).all()}
    if not code_to_id:
        raise RuntimeError("流程架构为空，请先灌业务种子数据（python -m scripts.seed）")
    _seed_benchmarks(db, code_to_id)
    db.commit()
    return _benchmark_counts(db)


def reset_and_seed(db: Session) -> Dict[str, int]:
    return seed(db, reset=True)
