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
from app.models.knowledge import KnowledgeItem, KnowledgeTag
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.tool import Tool
from app.models.user import AuditLog, User
from app.seed import benchmark_data, corpus, corpus_data
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
        recompute_progress(db, obj)
        ids[row["code"]] = obj.id
    return ids


def _seed_benchmarks(db: Session, code_to_id: Dict[str, int]) -> None:
    """对标框架、标准分类树与流程映射。"""
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


def _seed_exceptions(db: Session, code_to_id: Dict[str, int], project_ids: Dict[str, int]) -> None:
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
                detected_at=detected,
                due_at=_parse_dt(row.get("due_at")),
                resolved_at=settled if row["status"] in ("RESOLVED", "CLOSED") else None,
                closed_at=settled if closed else None,
                root_cause=row.get("root_cause"),
                action_taken=row.get("action_taken"),
            )
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


def _seed_users(db: Session) -> Dict[str, int]:
    for row in corpus_data.USERS:
        db.add(
            User(
                username=row["username"],
                display_name=row["display_name"],
                password_hash=hash_password(row["password"]),
                role=row["role"],
                department=row.get("department"),
            )
        )
    db.flush()
    return {u.display_name: u.id for u in db.scalars(select(User)).all()}


def _wipe(db: Session) -> None:
    """按外键依赖倒序清空。

    ProcessArch 自引用，按 L4→L1 逐层删，兼容开启了外键约束的 PostgreSQL。
    """
    for model in (
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
        AuditLog,
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

    # 先建用户：流程与项目的 owner_user_id 要在灌数据时解析
    user_ids = _seed_users(db)
    code_to_id = _seed_process_arch(db, user_ids)
    _seed_workflow(db)
    _seed_tools(db)
    _seed_benchmarks(db, code_to_id)
    project_ids = _seed_projects(db, code_to_id, user_ids)
    _seed_kpis(db, code_to_id)
    _seed_exceptions(db, code_to_id, project_ids)
    _seed_knowledge(db, project_ids)
    _seed_design_models(db, code_to_id)
    db.commit()

    return {
        "process_arch": db.scalar(select(func.count()).select_from(ProcessArch)) or 0,
        "workflow_steps": db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0,
        "tools": db.scalar(select(func.count()).select_from(Tool)) or 0,
        "projects": db.scalar(select(func.count()).select_from(Project)) or 0,
        "project_steps": db.scalar(select(func.count()).select_from(ProjectStep)) or 0,
        "kpis": db.scalar(select(func.count()).select_from(KpiDefinition)) or 0,
        "kpi_records": db.scalar(select(func.count()).select_from(KpiRecord)) or 0,
        "exceptions": db.scalar(select(func.count()).select_from(ExceptionEvent)) or 0,
        "knowledge": db.scalar(select(func.count()).select_from(KnowledgeItem)) or 0,
        "knowledge_tags": db.scalar(select(func.count()).select_from(KnowledgeTag)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "process_nodes": db.scalar(select(func.count()).select_from(ProcessNode)) or 0,
        "process_edges": db.scalar(select(func.count()).select_from(ProcessEdge)) or 0,
        "benchmark_frameworks": db.scalar(select(func.count()).select_from(BenchmarkFramework))
        or 0,
        "benchmark_categories": db.scalar(select(func.count()).select_from(BenchmarkCategory)) or 0,
        "benchmark_mappings": db.scalar(select(func.count()).select_from(ProcessBenchmarkMap)) or 0,
    }


def seed_if_empty(db: Session) -> Optional[Dict[str, int]]:
    """库里有流程数据就跳过，避免每次启动重复灌。"""
    existing = db.scalar(select(func.count()).select_from(ProcessArch)) or 0
    if existing:
        return None
    return seed(db, reset=False)


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
