"""对标框架：分类树、覆盖率与流程映射的组装逻辑。"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.benchmark import (
    BenchmarkCategory,
    BenchmarkFramework,
    BenchmarkMetric,
    ProcessBenchmarkMap,
)
from app.models.process import ProcessArch
from app.schemas.benchmark import (
    BenchmarkCategoryOut,
    BenchmarkFrameworkOut,
    BenchmarkMappingOut,
    BenchmarkMetricOut,
    CategoryMetricsOut,
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
        category_external_id=category.external_id,
        category_name=category.name,
        category_level=category.level,
        framework_code=framework.code,
        framework_name=framework.name,
        note=mapping.note,
        created_at=mapping.created_at,
    )


# ------------------------------------------------------------------ 框架清单


def _lineage_ids(framework: BenchmarkFramework, by_id: Dict[int, BenchmarkFramework]) -> Set[int]:
    """框架自身 + 它的基础框架链；行业变体因此继承主框架的已建映射。"""
    ids = {framework.id}
    current = framework
    while current.base_framework_id:
        parent = by_id.get(current.base_framework_id)
        if parent is None or parent.id in ids:
            break
        ids.add(parent.id)
        current = parent
    return ids


def _mapped_process_counts(db: Session, frameworks: List[BenchmarkFramework]) -> Dict[int, int]:
    """按框架统计已映射流程数；行业变体按 PCF ID 继承基础框架的映射。"""
    rows = db.execute(
        select(BenchmarkCategory.id, BenchmarkCategory.framework_id, BenchmarkCategory.external_id)
    ).all()
    category_meta = {row[0]: (row[1], row[2]) for row in rows}
    external_index = {(row[1], row[2]): row[0] for row in rows if row[2] is not None}
    by_id = {f.id: f for f in frameworks}
    lineages = {f.id: _lineage_ids(f, by_id) for f in frameworks}
    covered: Dict[int, Set[int]] = {f.id: set() for f in frameworks}
    mappings = db.execute(
        select(ProcessBenchmarkMap.process_id, ProcessBenchmarkMap.category_id)
    ).all()
    for process_id, category_id in mappings:
        source_framework_id, external_id = category_meta[category_id]
        covered[source_framework_id].add(process_id)
        for framework in frameworks:
            if (
                source_framework_id in lineages[framework.id]
                and external_id is not None
                and (framework.id, external_id) in external_index
            ):
                covered[framework.id].add(process_id)
    return {framework_id: len(process_ids) for framework_id, process_ids in covered.items()}


def _categories_with_inherited_mappings(
    db: Session, framework: BenchmarkFramework
) -> List[tuple[int, BenchmarkCategory]]:
    """返回 (流程 id, 分类) 列表；行业变体按 PCF ID 解析主框架的映射。

    例：流程映射到跨行业版的 4.2（10216），消费电子版中同一 PCF ID 的
    分类也会被视为已映射，不需要为每个变体重复维护同一份映射。
    """
    categories = db.scalars(
        select(BenchmarkCategory).where(BenchmarkCategory.framework_id == framework.id)
    ).all()
    by_external = {c.external_id: c for c in categories if c.external_id}
    scope_ids = {framework.id}
    if framework.base_framework_id:
        scope_ids.add(framework.base_framework_id)
    rows = db.execute(
        select(ProcessBenchmarkMap.process_id, BenchmarkCategory)
        .join(BenchmarkCategory, ProcessBenchmarkMap.category_id == BenchmarkCategory.id)
        .where(BenchmarkCategory.framework_id.in_(scope_ids))
    ).all()
    result: List[tuple[int, BenchmarkCategory]] = []
    for process_id, category in rows:
        if category.framework_id == framework.id:
            result.append((process_id, category))
            continue
        mapped = by_external.get(category.external_id)
        if mapped is not None:
            result.append((process_id, mapped))
    return result


def framework_catalog(db: Session) -> List[BenchmarkFrameworkOut]:
    frameworks = db.scalars(
        select(BenchmarkFramework).order_by(BenchmarkFramework.sort_order, BenchmarkFramework.id)
    ).all()
    code_by_id = {f.id: f.code for f in frameworks}
    category_counts = dict(
        db.execute(
            select(BenchmarkCategory.framework_id, func.count(BenchmarkCategory.id)).group_by(
                BenchmarkCategory.framework_id
            )
        ).all()
    )
    mapped_counts = _mapped_process_counts(db, frameworks)
    return [
        BenchmarkFrameworkOut(
            id=f.id,
            code=f.code,
            name=f.name,
            name_en=f.name_en,
            version=f.version,
            description=f.description,
            industry=f.industry,
            is_primary=f.is_primary,
            base_framework_code=code_by_id.get(f.base_framework_id),
            generated_on=f.generated_on,
            attribution=f.attribution,
            is_active=f.is_active,
            category_count=category_counts.get(f.id, 0),
            mapped_process_count=mapped_counts.get(f.id, 0),
        )
        for f in frameworks
    ]


# ------------------------------------------------------------------ 分类树


def category_tree(
    db: Session, framework: BenchmarkFramework, max_level: int = 5
) -> List[BenchmarkCategoryOut]:
    categories = db.scalars(
        select(BenchmarkCategory)
        .where(BenchmarkCategory.framework_id == framework.id)
        .order_by(BenchmarkCategory.level, BenchmarkCategory.sort_order, BenchmarkCategory.code)
    ).all()
    metric_counts = dict(
        db.execute(
            select(BenchmarkMetric.external_id, func.count(BenchmarkMetric.id)).group_by(
                BenchmarkMetric.external_id
            )
        ).all()
    )
    by_id = {c.id: c for c in categories}
    children_of: Dict[Optional[int], List[BenchmarkCategory]] = {}
    for category in categories:
        children_of.setdefault(category.parent_id, []).append(category)

    direct: Dict[int, Set[int]] = {c.id: set() for c in categories}
    subtree: Dict[int, Set[int]] = {c.id: set() for c in categories}
    for process_id, category in _categories_with_inherited_mappings(db, framework):
        direct[category.id].add(process_id)
        node = by_id.get(category.id)
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
            name_zh=category.name_zh,
            name_zh_source=category.name_zh_source,
            external_id=category.external_id,
            level=category.level,
            parent_id=category.parent_id,
            description=category.description,
            description_zh=category.description_zh,
            metrics_available=category.metrics_available,
            metric_count=metric_counts.get(category.external_id, 0),
            difference_index=category.difference_index,
            change_details=category.change_details,
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
    all_processes = db.scalars(
        select(ProcessArch).where(ProcessArch.is_draft.is_(False)).order_by(ProcessArch.code)
    ).all()
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
    metric_counts = dict(
        db.execute(
            select(BenchmarkMetric.external_id, func.count(BenchmarkMetric.id)).group_by(
                BenchmarkMetric.external_id
            )
        ).all()
    )

    mapped_categories: Dict[int, List[BenchmarkCategory]] = {}
    for process_id, category in _categories_with_inherited_mappings(db, framework):
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
            name_zh=category.name_zh,
            name_zh_source=category.name_zh_source,
            external_id=category.external_id,
            level=category.level,
            description=category.description,
            description_zh=category.description_zh,
            metric_count=metric_counts.get(category.external_id, 0),
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


# ------------------------------------------------------------------ 指标目录


def category_metrics(db: Session, category: BenchmarkCategory) -> CategoryMetricsOut:
    """读取某个分类元素的指标。

    指标表按 PCF ID 存储而不是按 category_id，因此同一元素在跨行业版和
    行业版里看到的是同一份指标；旧版 SCOR 分类没有 external_id，返回空列表。
    """
    rows: List[BenchmarkMetric] = []
    if category.external_id:
        rows = list(
            db.scalars(
                select(BenchmarkMetric)
                .where(BenchmarkMetric.external_id == category.external_id)
                .order_by(BenchmarkMetric.metric_id)
            ).all()
        )
    return CategoryMetricsOut(
        category_id=category.id,
        code=category.code,
        name=category.name,
        name_en=category.name_en,
        name_zh=category.name_zh,
        external_id=category.external_id,
        metrics=[
            BenchmarkMetricOut(
                id=row.id,
                external_id=row.external_id,
                metric_id=row.metric_id,
                metric_category=row.metric_category,
                name=row.name,
                formula=row.formula,
                unit=row.unit,
                source=row.source,
                name_zh=row.name_zh,
                formula_zh=row.formula_zh,
                unit_zh=row.unit_zh,
                category_label_zh=row.category_label_zh,
                translation_source=row.translation_source,
            )
            for row in rows
        ],
    )
