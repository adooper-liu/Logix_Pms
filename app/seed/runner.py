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
from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, ProcessBenchmarkMap
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
    StepContract,
)
from app.models.enums import Role, TaskStatus
from app.models.execution import (
    FormDefinition,
    NodeAssignment,
    ProcessExecutionConfig,
    ProcessInstance,
    ProcessRule,
    ProcessTask,
)
from app.models.governance import GovernanceFinding
from app.models.integration import (
    InboundEvent,
    InboundWebhook,
    IntegrationDelivery,
    IntegrationEndpoint,
)
from app.models.knowledge import KnowledgeItem, KnowledgeTag
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.notification import Notification
from app.models.org import OrgUnit
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.tool import Tool
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.models.user import AuditLog, User
from app.schemas.execution import InstanceStartRequest, TaskCompleteRequest
from app.seed import benchmark_data, corpus, corpus_data, deliverable_data
from app.services import deliverable as deliverable_service
from app.services import execution as execution_service
from app.services import notifications as notification_service
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


def _seed_process_arch(db: Session, user_ids: Dict[str, int]) -> Dict[str, int]:
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
            description=row.get("description"),
            strategic_importance=row.get("si", 3.0),
            pain_score=row.get("pain", 3.0),
            improvement_space=row.get("space", 3.0),
            health_score=row.get("health"),
            is_improvement_target=row.get("target", False),
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


def _seed_tools(db: Session) -> None:
    for order, row in enumerate(corpus.TOOLS, start=1):
        db.add(
            Tool(
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
                sort_order=order,
            )
        )


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
    """对标框架、标准分类树与流程映射。

    with_mappings=False 只灌框架与分类，供生产环境使用：公司流程还没录入时
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

    categories: Dict[str, Dict[str, BenchmarkCategory]] = {}
    for row in sorted(benchmark_data.BENCHMARK_CATEGORIES, key=lambda r: r["level"]):
        framework = frameworks.get(row["framework"])
        if framework is None:
            raise ValueError(f"对标分类 {row['code']} 引用了未知框架 {row['framework']}")
        parent_code = row.get("parent")
        parent = categories.get(row["framework"], {}).get(parent_code) if parent_code else None
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
        categories.setdefault(framework.code, {})[category.code] = category

    if not with_mappings:
        return

    for row in benchmark_data.PROCESS_BENCHMARK_MAP:
        process_id = code_to_id.get(row["process"])
        category = categories.get(row["framework"], {}).get(row["category"])
        if process_id is None:
            raise ValueError(f"对标映射引用了未知流程 {row['process']}")
        if category is None:
            raise ValueError(f"对标映射引用了未知分类 {row['framework']} / {row['category']}")
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
        category = categories[row["framework"]][row["category"]]
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


def _seed_kpis(db: Session, code_to_id: Dict[str, int]) -> None:
    periods = [date.fromisoformat(p) for p in corpus_data.KPI_PERIODS]
    for row in corpus_data.KPIS:
        kpi = KpiDefinition(
            code=row["code"],
            name=row["name"],
            dimension=row["dimension"],
            direction=row["direction"],
            unit=row.get("unit"),
            target_value=row.get("target_value"),
            baseline_value=row.get("baseline_value"),
            description=row.get("description"),
            process_id=code_to_id.get(row["process"]) if row.get("process") else None,
            owner=row.get("owner"),
            is_active=True,
        )
        db.add(kpi)
        db.flush()
        for period, value in zip(periods, row["values"], strict=False):
            db.add(KpiRecord(kpi_id=kpi.id, period=period, value=float(value)))


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


def _seed_knowledge(db: Session, project_ids: Dict[str, int]) -> None:
    for row in corpus_data.KNOWLEDGE:
        item = KnowledgeItem(
            title=row["title"],
            type=row["type"],
            methodology=row.get("methodology"),
            summary=row["summary"],
            content=row["content"],
            process_id=None,
            project_id=project_ids.get("PR-2026-018") if row["type"] == "CASE" else None,
            tool_code=row.get("tool_code"),
            author=row.get("author"),
            download_count=row.get("download_count", 0),
            created_at=_parse_dt(row.get("created")) or _parse_dt("2026-09-01 09:00:00"),
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


def _seed_design_models(db: Session, code_to_id: Dict[str, int]) -> None:
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
    return ids


def _seed_users(db: Session, org_ids: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    org_ids = org_ids or {}
    demo_orgs = {
        "admin": "GROUP-001",
        "manager": "GROUP-001",
        "chen": "CO-EAST",
    }
    for row in corpus_data.USERS:
        db.add(
            User(
                username=row["username"],
                display_name=row["display_name"],
                password_hash=hash_password(row["password"]),
                role=row["role"],
                department=row.get("department"),
                org_unit_id=org_ids.get(demo_orgs.get(row["username"], "")),
            )
        )
    db.flush()
    return {u.display_name: u.id for u in db.scalars(select(User)).all()}


def _wipe(db: Session) -> None:
    """按外键依赖倒序清空。

    ProcessArch 自引用，按 L4→L1 逐层删，兼容开启了外键约束的 PostgreSQL。
    """
    for model in (
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
        ProcessTask,
        ProcessInstance,
        ProcessBenchmarkMap,
        ProcessEdge,
        ProcessNode,
        ProjectStep,
        KpiRecord,
        ExceptionEvent,
        KnowledgeTag,
        KnowledgeItem,
        KpiDefinition,
        Project,
        WorkflowTemplate,
        Tool,
        IntegrationDelivery,
        IntegrationEndpoint,
        InboundEvent,
        InboundWebhook,
        Notification,
        AuditLog,
        OrgUnit,
        User,
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

    # 先建组织，再建用户：演示账号要挂到集团/分公司
    org_ids = _seed_org_units(db)
    user_ids = _seed_users(db, org_ids)
    code_to_id = _seed_process_arch(db, user_ids)
    _seed_workflow(db)
    _seed_tools(db)
    _seed_step_contracts(db)
    _seed_deliverable_definitions(db)
    _seed_benchmarks(db, code_to_id)
    project_ids = _seed_projects(db, code_to_id, user_ids)
    _seed_kpis(db, code_to_id)
    _seed_exceptions(db, code_to_id, project_ids, user_ids)
    _seed_knowledge(db, project_ids)
    _seed_design_models(db, code_to_id)
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
    - SCOR / APQC PCF 框架与分类（不含流程映射）

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
    }
    if (db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0) == 0:
        _seed_workflow(db)
        created["workflow_steps"] = len(corpus.WORKFLOW)
    if (db.scalar(select(func.count()).select_from(Tool)) or 0) == 0:
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
        created["benchmark_frameworks"] = len(benchmark_data.BENCHMARK_FRAMEWORKS)
        created["benchmark_categories"] = len(benchmark_data.BENCHMARK_CATEGORIES)
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
