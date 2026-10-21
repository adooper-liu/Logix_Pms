"""对标框架：分类树、覆盖率与流程映射的组装逻辑。"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, ProcessBenchmarkMap
from app.models.process import ProcessArch
from app.schemas.benchmark import (
    BenchmarkCategoryOut,
    BenchmarkFrameworkOut,
    BenchmarkMappingOut,
    CoverageCategoryOut,
    FrameworkCoverageOut,
    ProcessBenchmarkOut,
    ProcessRef,
)


def _process_ref(p: ProcessArch) -> ProcessRef:
    return ProcessRef(id=p.id, code=p.code, name=p.name, level=p.level)


def mapping_out(
    mapping: ProcessBenchmarkMap,
    process: ProcessArch,
    category: BenchmarkCategory,
    framework: BenchmarkFramework,
) -> BenchmarkMappingOut:
    return BenchmarkMappingOut(
        id=mapping.id,
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        category_id=category.id,
        category_code=category.code,
        category_name=category.name,
        category_level=category.level,
        framework_code=framework.code,
        framework_name=framework.name,
        note=mapping.note,
        created_at=mapping.created_at,
    )


# ------------------------------------------------------------------ 框架清单


def framework_catalog(db: Session) -> List[BenchmarkFrameworkOut]:
    frameworks = db.scalars(
        select(BenchmarkFramework).order_by(BenchmarkFramework.sort_order, BenchmarkFramework.id)
    ).all()
    category_counts = dict(
        db.execute(
            select(BenchmarkCategory.framework_id, func.count(BenchmarkCategory.id)).group_by(
                BenchmarkCategory.framework_id
            )
        ).all()
    )
    mapped_counts = dict(
        db.execute(
            select(
                BenchmarkCategory.framework_id,
                func.count(func.distinct(ProcessBenchmarkMap.process_id)),
            )
            .join(BenchmarkCategory, ProcessBenchmarkMap.category_id == BenchmarkCategory.id)
            .group_by(BenchmarkCategory.framework_id)
        ).all()
    )
    return [
        BenchmarkFrameworkOut(
            id=f.id,
            code=f.code,
            name=f.name,
            name_en=f.name_en,
            version=f.version,
            description=f.description,
            is_active=f.is_active,
            category_count=category_counts.get(f.id, 0),
            mapped_process_count=mapped_counts.get(f.id, 0),
        )
        for f in frameworks
    ]


# ------------------------------------------------------------------ 分类树


def category_tree(
    db: Session, framework: BenchmarkFramework, max_level: int = 4
) -> List[BenchmarkCategoryOut]:
    categories = db.scalars(
        select(BenchmarkCategory)
        .where(BenchmarkCategory.framework_id == framework.id)
        .order_by(BenchmarkCategory.level, BenchmarkCategory.sort_order, BenchmarkCategory.code)
    ).all()
    by_id = {c.id: c for c in categories}
    children_of: Dict[Optional[int], List[BenchmarkCategory]] = {}
    for category in categories:
        children_of.setdefault(category.parent_id, []).append(category)

    direct: Dict[int, Set[int]] = {c.id: set() for c in categories}
    subtree: Dict[int, Set[int]] = {c.id: set() for c in categories}
    mappings = db.execute(
        select(ProcessBenchmarkMap.process_id, ProcessBenchmarkMap.category_id)
        .join(BenchmarkCategory, ProcessBenchmarkMap.category_id == BenchmarkCategory.id)
        .where(BenchmarkCategory.framework_id == framework.id)
    ).all()
    for process_id, category_id in mappings:
        direct[category_id].add(process_id)
        node = by_id.get(category_id)
        while node is not None:
            subtree[node.id].add(process_id)
            node = by_id.get(node.parent_id)

    def build(category: BenchmarkCategory) -> BenchmarkCategoryOut:
        children = [
            build(child) for child in children_of.get(category.id, []) if child.level <= max_level
        ]
        return BenchmarkCategoryOut(
            id=category.id,
            code=category.code,
            name=category.name,
            name_en=category.name_en,
            level=category.level,
            parent_id=category.parent_id,
            description=category.description,
            mapped_process_count=len(direct.get(category.id, ())),
            subtree_mapped_process_count=len(subtree.get(category.id, ())),
            children=children,
        )

    return [build(c) for c in children_of.get(None, []) if c.level <= max_level]


# ------------------------------------------------------------------ 覆盖率


def coverage(
    db: Session, framework: BenchmarkFramework, process_level: int = 3
) -> FrameworkCoverageOut:
    """统计某层流程的框架覆盖情况。

    判定口径：一个流程只要**自身或任一后代**映射到该框架，就算被覆盖。
    这样同一份映射可以在 L1/L2/L3 任一层看覆盖率，不会出现「下层映射了、
    上层却显示 0%」的假象。
    """
    all_processes = db.scalars(select(ProcessArch).order_by(ProcessArch.code)).all()
    by_id = {p.id: p for p in all_processes}
    children_of: Dict[Optional[int], List[ProcessArch]] = {}
    for p in all_processes:
        children_of.setdefault(p.parent_id, []).append(p)

    def descendants(process: ProcessArch) -> Set[int]:
        stack = [process]
        ids: Set[int] = set()
        while stack:
            current = stack.pop()
            ids.add(current.id)
            stack.extend(children_of.get(current.id, []))
        return ids

    categories = db.scalars(
        select(BenchmarkCategory).where(BenchmarkCategory.framework_id == framework.id)
    ).all()
    category_by_id = {c.id: c for c in categories}
    top_ids = {c.id for c in categories if c.level == 1}

    mapped_categories: Dict[int, List[BenchmarkCategory]] = {}
    for process_id, category in db.execute(
        select(ProcessBenchmarkMap.process_id, BenchmarkCategory)
        .join(BenchmarkCategory, ProcessBenchmarkMap.category_id == BenchmarkCategory.id)
        .where(BenchmarkCategory.framework_id == framework.id)
    ).all():
        mapped_categories.setdefault(process_id, []).append(category)

    target_processes = [p for p in all_processes if p.level == process_level]
    by_top: Dict[int, Set[int]] = {top_id: set() for top_id in top_ids}
    covered_ids: Set[int] = set()
    for process in target_processes:
        touched: Dict[int, BenchmarkCategory] = {}
        for pid in descendants(process):
            for category in mapped_categories.get(pid, []):
                touched[category.id] = category
        if not touched:
            continue
        covered_ids.add(process.id)
        for category in touched.values():
            node: Optional[BenchmarkCategory] = category
            while node is not None and node.id not in top_ids:
                node = category_by_id.get(node.parent_id)
            if node is not None:
                by_top[node.id].add(process.id)

    top_categories = sorted(
        (category_by_id[top_id] for top_id in top_ids),
        key=lambda c: (c.sort_order, c.code),
    )
    by_category = [
        CoverageCategoryOut(
            category_id=category.id,
            code=category.code,
            name=category.name,
            name_en=category.name_en,
            level=category.level,
            mapped_count=len(by_top[category.id]),
            processes=[
                _process_ref(by_id[pid])
                for pid in sorted(by_top[category.id], key=lambda i: by_id[i].code)
            ],
        )
        for category in top_categories
    ]

    total = len(target_processes)
    return FrameworkCoverageOut(
        framework_code=framework.code,
        framework_name=framework.name,
        framework_version=framework.version,
        process_level=process_level,
        total_processes=total,
        mapped_processes=len(covered_ids),
        coverage_rate=round(len(covered_ids) / total, 4) if total else 0.0,
        by_top_category=by_category,
        unmapped_processes=[_process_ref(p) for p in target_processes if p.id not in covered_ids],
    )


# ------------------------------------------------------------------ 流程侧映射


def process_mappings(db: Session, process: ProcessArch) -> ProcessBenchmarkOut:
    rows = db.execute(
        select(ProcessBenchmarkMap, BenchmarkCategory, BenchmarkFramework)
        .join(BenchmarkCategory, ProcessBenchmarkMap.category_id == BenchmarkCategory.id)
        .join(BenchmarkFramework, BenchmarkCategory.framework_id == BenchmarkFramework.id)
        .where(ProcessBenchmarkMap.process_id == process.id)
        .order_by(
            BenchmarkFramework.sort_order,
            BenchmarkCategory.level,
            BenchmarkCategory.sort_order,
            BenchmarkCategory.code,
        )
    ).all()
    return ProcessBenchmarkOut(
        process=_process_ref(process),
        mappings=[mapping_out(m, process, c, f) for m, c, f in rows],
    )
