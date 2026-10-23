"""从标准分类树（APQC PCF）生成企业流程架构草稿。

设计边界：

- 只写 `process_arch`（L1–L4），不碰设计器节点、执行实例与 KPI；
- 生成物 `is_draft=True`，确认后才算正式流程；
- 以 `(source_framework_code, source_external_id)` 为幂等键，重复执行只补缺失；
- 企业已有的同名节点优先复用，不覆盖人工维护的名称/负责人/指标。

选择口径：勾选 L1/L2 会展开其下全部 L3（可选 L4）；勾选 L3 生成该流程及其
L4 活动；勾选 L4 会补齐它的 L3 与上级链条。PCF 的 L5 任务不进入企业架构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkCategory, BenchmarkFramework
from app.models.process import ProcessArch
from app.schemas.process import (
    PcfDraftItem,
    PcfDraftPreview,
    PcfDraftRequest,
    PcfDraftResult,
)

MAX_LEVEL = 4  # ProcessArch 只到 L4


@dataclass
class _PlanNode:
    category: BenchmarkCategory
    state: str  # CREATE / REUSE
    process_id: Optional[int] = None


@dataclass
class _Plan:
    framework: BenchmarkFramework
    nodes: List[_PlanNode] = field(default_factory=list)
    by_external: Dict[str, BenchmarkCategory] = field(default_factory=dict)
    by_id: Dict[int, BenchmarkCategory] = field(default_factory=dict)


def _framework(db: Session, code: str) -> BenchmarkFramework:
    framework = db.scalar(select(BenchmarkFramework).where(BenchmarkFramework.code == code))
    if framework is None:
        raise HTTPException(status_code=404, detail=f"对标框架 {code} 不存在")
    return framework


def _load_tree(
    db: Session, framework: BenchmarkFramework
) -> Tuple[
    Dict[str, BenchmarkCategory], Dict[int, BenchmarkCategory], Dict[int, List[BenchmarkCategory]]
]:
    categories = db.scalars(
        select(BenchmarkCategory).where(BenchmarkCategory.framework_id == framework.id)
    ).all()
    by_external = {row.external_id: row for row in categories if row.external_id}
    if not by_external:
        raise HTTPException(
            status_code=400,
            detail="该框架没有可生成的 PCF 分类（缺少 external_id）",
        )
    by_id = {row.id: row for row in categories}
    children: Dict[int, List[BenchmarkCategory]] = {}
    for row in categories:
        children.setdefault(row.parent_id, []).append(row)
    return by_external, by_id, children


def _descendants(
    category: BenchmarkCategory,
    children: Dict[int, List[BenchmarkCategory]],
    max_level: int,
):
    stack = list(children.get(category.id, []))
    while stack:
        node = stack.pop()
        if node.level > max_level:
            continue
        yield node
        if node.level < max_level:
            stack.extend(children.get(node.id, []))


def _targets(
    external_ids: List[str],
    by_external: Dict[str, BenchmarkCategory],
    children: Dict[int, List[BenchmarkCategory]],
    include_activities: bool,
) -> Set[str]:
    """把任意层级的勾选展开成需要生成的 L3/L4 元素。"""
    target_level = MAX_LEVEL if include_activities else 3
    targets: Set[str] = set()
    for external_id in external_ids:
        category = by_external.get(external_id)
        if category is None:
            raise HTTPException(status_code=400, detail=f"分类 {external_id} 不存在")
        if category.level <= 2:
            for node in _descendants(category, children, target_level):
                if node.level == 3 or (include_activities and node.level == 4):
                    targets.add(node.external_id)
        elif category.level == 3:
            targets.add(category.external_id)
            if include_activities:
                for node in _descendants(category, children, MAX_LEVEL):
                    if node.level == 4:
                        targets.add(node.external_id)
        elif category.level == 4:
            targets.add(category.external_id)
        # L5 任务不进入企业流程架构
    if not targets:
        raise HTTPException(status_code=400, detail="所选分类下没有可生成的 L3/L4 元素")
    return targets


def _with_ancestors(
    targets: Set[str],
    by_external: Dict[str, BenchmarkCategory],
    by_id: Dict[int, BenchmarkCategory],
) -> Set[str]:
    needed = set(targets)
    for external_id in list(targets):
        node = by_external[external_id]
        while node.parent_id:
            parent = by_id.get(node.parent_id)
            if parent is None or not parent.external_id:
                break
            needed.add(parent.external_id)
            node = parent
    return needed


def _existing_indexes(
    db: Session,
) -> Tuple[Dict[Tuple[str, str], ProcessArch], Dict[Tuple, List[ProcessArch]]]:
    rows = db.scalars(select(ProcessArch)).all()
    by_source = {
        (row.source_framework_code, row.source_external_id): row
        for row in rows
        if row.source_framework_code and row.source_external_id
    }
    by_parent_name: Dict[Tuple[Optional[int], int, str], List[ProcessArch]] = {}
    for row in rows:
        by_parent_name.setdefault((row.parent_id, row.level, row.name), []).append(row)
    return by_source, by_parent_name


def _plan(db: Session, framework: BenchmarkFramework, request: PcfDraftRequest) -> _Plan:
    by_external, by_id, children = _load_tree(db, framework)
    needed = _with_ancestors(
        _targets(request.external_ids, by_external, children, request.include_activities),
        by_external,
        by_id,
    )
    ordered = sorted(
        (by_external[external_id] for external_id in needed),
        key=lambda category: (category.level, category.code),
    )

    by_source, by_parent_name = _existing_indexes(db)
    company_by_external: Dict[str, int] = {}
    plan = _Plan(framework=framework, by_external=by_external, by_id=by_id)

    for category in ordered:
        parent_external = by_id[category.parent_id].external_id if category.parent_id else None
        parent_company_id = company_by_external.get(parent_external) if parent_external else None
        existing = by_source.get((framework.code, category.external_id))
        # 只有父节点已确定（根节点或已复用节点）时才按名称匹配；
        # 父节点是新建的，不可能已经存在同名子节点。
        if existing is None and (parent_external is None or parent_external in company_by_external):
            candidates = by_parent_name.get((parent_company_id, category.level, category.name), [])
            if len(candidates) == 1:
                existing = candidates[0]
        if existing is not None:
            plan.nodes.append(_PlanNode(category=category, state="REUSE", process_id=existing.id))
            company_by_external[category.external_id] = existing.id
        else:
            plan.nodes.append(_PlanNode(category=category, state="CREATE"))
    return plan


def _items(plan: _Plan) -> List[PcfDraftItem]:
    return [
        PcfDraftItem(
            external_id=node.category.external_id,
            pcf_code=node.category.code,
            name=node.category.name,
            name_en=node.category.name_en,
            level=node.category.level,
            state=node.state,
            process_id=node.process_id,
        )
        for node in plan.nodes
    ]


def _counts(plan: _Plan) -> Tuple[int, int, Dict[str, Dict[str, int]]]:
    create = sum(1 for node in plan.nodes if node.state == "CREATE")
    reuse = sum(1 for node in plan.nodes if node.state == "REUSE")
    by_level: Dict[str, Dict[str, int]] = {}
    for node in plan.nodes:
        bucket = by_level.setdefault(str(node.category.level), {"create": 0, "reuse": 0})
        bucket["create" if node.state == "CREATE" else "reuse"] += 1
    return create, reuse, by_level


def preview_draft(db: Session, request: PcfDraftRequest) -> PcfDraftPreview:
    framework = _framework(db, request.framework_code)
    plan = _plan(db, framework, request)
    create, reuse, by_level = _counts(plan)
    return PcfDraftPreview(
        framework_code=framework.code,
        framework_name=framework.name,
        framework_version=framework.version,
        create_count=create,
        reuse_count=reuse,
        by_level=by_level,
        items=_items(plan),
    )


def generate(db: Session, request: PcfDraftRequest) -> PcfDraftResult:
    framework = _framework(db, request.framework_code)
    return generate_draft(db, framework, request)


def _description(framework: BenchmarkFramework, category: BenchmarkCategory) -> str:
    header = (
        f"APQC PCF {framework.version or ''} · {category.code} {category.name_en or ''}".strip()
    )
    return f"{header}\n{category.description}" if category.description else header


def _unique_code(codes: Set[str], external_id: str) -> str:
    base = f"PCF{external_id}"[:28]
    candidate = base
    suffix = 1
    while candidate in codes:
        candidate = f"{base}-{suffix}"
        suffix += 1
    codes.add(candidate)
    return candidate


def generate_draft(
    db: Session, framework: BenchmarkFramework, request: PcfDraftRequest
) -> PcfDraftResult:
    plan = _plan(db, framework, request)
    company_by_external: Dict[str, int] = {}
    created_ids: List[int] = []
    codes = set(db.scalars(select(ProcessArch.code)).all())

    # 按层级批量创建：父节点 ID 在上一级 flush 后即可用，避免逐行 flush。
    for level in range(1, MAX_LEVEL + 1):
        pending: List[Tuple[_PlanNode, ProcessArch]] = []
        for node in (item for item in plan.nodes if item.category.level == level):
            category = node.category
            parent_external = (
                plan.by_id[category.parent_id].external_id if category.parent_id else None
            )
            parent_company_id = (
                company_by_external.get(parent_external) if parent_external else None
            )
            if node.state == "REUSE" and node.process_id is not None:
                company_by_external[category.external_id] = node.process_id
                existing = db.get(ProcessArch, node.process_id)
                # 复用的人工节点补上来源，后续重复生成才能稳定命中。
                if existing is not None and not existing.source_external_id:
                    existing.source_framework_code = framework.code
                    existing.source_external_id = category.external_id
                continue
            if parent_external and parent_company_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"分类 {category.external_id} 的父节点尚未生成，请检查选择范围",
                )
            row = ProcessArch(
                code=_unique_code(codes, category.external_id),
                name=category.name,
                level=category.level,
                parent_id=parent_company_id,
                description=_description(framework, category),
                is_draft=True,
                source_framework_code=framework.code,
                source_external_id=category.external_id,
            )
            db.add(row)
            pending.append((node, row))
        if pending:
            db.flush()
            for node, row in pending:
                node.process_id = row.id
                company_by_external[node.category.external_id] = row.id
                created_ids.append(row.id)

    db.flush()
    create, reuse, by_level = _counts(plan)
    return PcfDraftResult(
        framework_code=framework.code,
        framework_name=framework.name,
        framework_version=framework.version,
        create_count=create,
        reuse_count=reuse,
        by_level=by_level,
        items=_items(plan),
        created_process_ids=created_ids,
    )


def promote_drafts(db: Session, process_ids: List[int]) -> int:
    """把草稿转成正式流程；已经是正式的节点保持原样。"""
    rows = db.scalars(select(ProcessArch).where(ProcessArch.id.in_(process_ids))).all()
    updated = 0
    for row in rows:
        if row.is_draft:
            row.is_draft = False
            updated += 1
    db.flush()
    return updated
