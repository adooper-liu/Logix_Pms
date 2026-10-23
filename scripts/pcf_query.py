"""APQC PCF 分类树的查询工具。

用法：

    python scripts/pcf_query.py --sql                 # 查看递归 SQL（可直接贴到 psql）
    python scripts/pcf_query.py                       # 打印主框架完整 L1–L5 树
    python scripts/pcf_query.py --level 3             # 只看 L3 流程
    python scripts/pcf_query.py --keyword 采购        # 按中英文名/编码/PCF ID 搜索
    python scripts/pcf_query.py --metrics             # 只看有指标的元素
    python scripts/pcf_query.py --json > pcf.json     # 导出 JSON
    python scripts/pcf_query.py --csv > pcf.csv       # 导出 CSV
    python scripts/pcf_query.py --metrics-for 10216   # 查看某元素的指标明细

输出中的 `PCF ID` 是跨版本稳定键；`Hierarchy ID`（如 4.2.1）只用于阅读定位。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import func, select  # noqa: E402

import app.models  # noqa: F401,E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.benchmark import (  # noqa: E402
    BenchmarkCategory,
    BenchmarkFramework,
    BenchmarkMetric,
    ProcessBenchmarkMap,
)

RECURSIVE_SQL = """WITH RECURSIVE pcf_tree AS (
  SELECT c.id, c.framework_id, c.parent_id, c.level, c.code, c.external_id,
         c.name, c.name_zh, c.name_en, c.description, c.metrics_available,
         c.code AS path_code, c.name AS path_name
  FROM benchmark_category c
  WHERE c.parent_id IS NULL
  UNION ALL
  SELECT c.id, c.framework_id, c.parent_id, c.level, c.code, c.external_id,
         c.name, c.name_zh, c.name_en, c.description, c.metrics_available,
         t.path_code || ' > ' || c.code,
         t.path_name || ' > ' || c.name
  FROM benchmark_category c
  JOIN pcf_tree t ON c.parent_id = t.id
)
SELECT f.code AS framework, t.level, t.code AS hierarchy_id,
       t.external_id AS pcf_id, t.name_zh, t.name_en, t.description,
       t.metrics_available,
       (SELECT COUNT(*) FROM benchmark_metric m
         WHERE m.external_id = t.external_id) AS metric_count,
       (SELECT COUNT(DISTINCT pbm.process_id) FROM process_benchmark_map pbm
         WHERE pbm.category_id = t.id) AS mapped_process_count,
       t.path_code, t.path_name
FROM pcf_tree t
JOIN benchmark_framework f ON f.id = t.framework_id
WHERE f.code = :framework_code
ORDER BY t.level, t.path_code;
"""

METRICS_SQL = """SELECT m.metric_id, m.name, m.metric_category, m.formula, m.unit
FROM benchmark_metric m
WHERE m.external_id = :pcf_id
ORDER BY m.metric_id;
"""


def _framework(db, code: str) -> BenchmarkFramework:
    framework = db.scalar(select(BenchmarkFramework).where(BenchmarkFramework.code == code))
    if framework is None:
        codes = list(db.scalars(select(BenchmarkFramework.code).order_by(BenchmarkFramework.code)))
        raise SystemExit(f"框架 {code} 不存在；可用框架：{', '.join(codes)}")
    return framework


def _hkey(code: str) -> tuple:
    """Hierarchy ID 的自然排序键：4.2 排在 4.10 前面。"""
    return tuple(int(part) if part.isdigit() else 0 for part in str(code).split("."))


def _load(db, framework: BenchmarkFramework) -> List[Dict]:
    metric_counts = dict(
        db.execute(
            select(BenchmarkMetric.external_id, func.count(BenchmarkMetric.id)).group_by(
                BenchmarkMetric.external_id
            )
        ).all()
    )
    mapped_counts = dict(
        db.execute(
            select(
                ProcessBenchmarkMap.category_id, func.count(ProcessBenchmarkMap.process_id)
            ).group_by(ProcessBenchmarkMap.category_id)
        ).all()
    )
    rows = db.scalars(
        select(BenchmarkCategory)
        .where(BenchmarkCategory.framework_id == framework.id)
        .order_by(BenchmarkCategory.level, BenchmarkCategory.code)
    ).all()
    return sorted(
        [
            {
                "id": row.id,
                "parent_id": row.parent_id,
                "level": row.level,
                "hierarchy_id": row.code,
                "pcf_id": row.external_id,
                "name": row.name,
                "name_zh": row.name_zh,
                "name_en": row.name_en,
                "description": row.description,
                "metrics_available": row.metrics_available,
                "metric_count": metric_counts.get(row.external_id, 0),
                "mapped_process_count": mapped_counts.get(row.id, 0),
            }
            for row in rows
        ],
        key=lambda item: (item["level"], _hkey(item["hierarchy_id"])),
    )


def _matches(row: Dict, keyword: str) -> bool:
    text = " ".join(
        str(row.get(key) or "") for key in ("hierarchy_id", "pcf_id", "name", "name_zh", "name_en")
    ).lower()
    return keyword.lower() in text


def _path(row: Dict, by_id: Dict[int, Dict]) -> str:
    names = []
    current = row
    while current:
        names.unshift(current.get("name_zh") or current.get("name") or "")
        current = by_id.get(current.get("parent_id"))
    return " › ".join(names)


def _print_tree(
    rows: List[Dict], *, keyword: str = "", level: Optional[int] = None, metrics_only: bool = False
) -> None:
    by_parent: Dict[Optional[int], List[Dict]] = {}
    for row in rows:
        by_parent.setdefault(row["parent_id"], []).append(row)
    for children in by_parent.values():
        children.sort(key=lambda item: _hkey(item["hierarchy_id"]))

    shown = 0

    def walk(parent_id: Optional[int], depth: int) -> None:
        nonlocal shown
        for row in by_parent.get(parent_id, []):
            leaf_match = (
                (not keyword or _matches(row, keyword))
                and (level is None or row["level"] == level)
                and (not metrics_only or row["metric_count"] > 0)
            )
            # 搜索时保留匹配节点的祖先路径
            subtree_match = keyword and any(
                _matches(child, keyword) for child in _all_descendants(row, by_parent)
            )
            if leaf_match or subtree_match:
                if leaf_match:
                    shown += 1
                    metrics = f" · 指标 {row['metric_count']}" if row["metric_count"] else ""
                    mapped = (
                        f" · 映射 {row['mapped_process_count']}"
                        if row["mapped_process_count"]
                        else ""
                    )
                    en = row["name_en"] or ""
                    print(
                        f"{'  ' * depth}L{row['level']} {row['hierarchy_id']} "
                        f"{row['name_zh'] or row['name']}"
                        + (f" | {en}" if en and en != row["name"] else "")
                        + f"  [PCF {row['pcf_id'] or '—'}]{metrics}{mapped}"
                    )
                walk(row["id"], depth + 1)
            else:
                walk(row["id"], depth + 1)

    walk(None, 0)
    if not shown:
        print("没有匹配的元素。")
    else:
        print(f"\n共显示 {shown} 个元素。")


def _all_descendants(row: Dict, by_parent: Dict[Optional[int], List[Dict]]) -> Iterable[Dict]:
    stack = list(by_parent.get(row["id"], []))
    while stack:
        current = stack.pop()
        yield current
        stack.extend(by_parent.get(current["id"], []))


def _print_metrics(db, pcf_id: str) -> None:
    rows = db.execute(
        select(
            BenchmarkMetric.metric_id,
            BenchmarkMetric.name,
            BenchmarkMetric.metric_category,
            BenchmarkMetric.formula,
            BenchmarkMetric.unit,
        )
        .where(BenchmarkMetric.external_id == pcf_id)
        .order_by(BenchmarkMetric.metric_id)
    ).all()
    if not rows:
        print(f"PCF ID {pcf_id} 没有配置指标。")
        return
    print(f"PCF ID {pcf_id} 的指标（{len(rows)} 条）：")
    for metric_id, name, category, formula, unit in rows:
        print(f"  {metric_id}  {name}")
        if category:
            print(f"      类别：{category}")
        if formula:
            print(f"      公式：{formula}")
        if unit:
            print(f"      单位：{unit}")


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 APQC PCF 分类树")
    parser.add_argument("--framework", default="APQC_PCF", help="框架编码，默认 APQC_PCF")
    parser.add_argument("--level", type=int, choices=range(1, 6), help="只看某一层（1–5）")
    parser.add_argument("--keyword", default="", help="按编码/PCF ID/中英文名搜索")
    parser.add_argument("--metrics", action="store_true", help="只看配置了指标的元素")
    parser.add_argument("--metrics-for", metavar="PCF_ID", help="查看某个元素的指标明细")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--csv", action="store_true", help="输出 CSV")
    parser.add_argument("--sql", action="store_true", help="输出递归 SQL 与指标 SQL")
    args = parser.parse_args()

    if args.sql:
        print("-- 完整层级（含路径、指标数、公司流程映射数）")
        print(RECURSIVE_SQL)
        print("-- 指标明细")
        print(METRICS_SQL)
        return 0

    with SessionLocal() as db:
        framework = _framework(db, args.framework)
        if args.metrics_for:
            _print_metrics(db, args.metrics_for)
            return 0
        rows = _load(db, framework)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        if args.csv:
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=[
                    "level",
                    "hierarchy_id",
                    "pcf_id",
                    "name_zh",
                    "name_en",
                    "metric_count",
                    "mapped_process_count",
                    "description",
                ],
            )
            writer.writeheader()
            by_id = {row["id"]: row for row in rows}
            for row in rows:
                if args.level is not None and row["level"] != args.level:
                    continue
                if args.keyword and not _matches(row, args.keyword):
                    continue
                if args.metrics and not row["metric_count"]:
                    continue
                writer.writerow(
                    {
                        **{key: row[key] for key in writer.fieldnames},
                        "description": (
                            f"{_path(row, by_id)}: {row['description']}"
                            if row["description"]
                            else _path(row, by_id)
                        ),
                    }
                )
            return 0
        _print_tree(rows, keyword=args.keyword, level=args.level, metrics_only=args.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
