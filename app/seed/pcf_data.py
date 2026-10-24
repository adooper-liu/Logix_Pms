"""APQC PCF v8.0 生成数据加载器。

`data/pcf_v80.json` 由 `scripts/import_pcf.py` 从 APQC 官方 Excel 生成，
不要手工编辑；需要更新版本时重新运行脚本并提交产物。

`data/pcf_v80_zh.json` 是**中文参考译文覆盖层**，人工维护，与官方数据分离：
- 官方数据重导不会覆盖它（它在运行时合并，不写回官方 JSON）；
- 译文为自建参考译文，**非 APQC 官方**，界面必须标注来源。

数据以 PCF ID（`external_id`）为跨变体稳定键：
- `Hierarchy ID`（JSON 里的 `code`）会因行业元素插入而漂移，只用于展示；
- 中文名只覆盖 L1–L3（来自官方中文整理版）；L4/L5 由覆盖层补齐；
- 指标按 (PCF ID, Metric ID) 去重，译文也按同一键定位。
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_FILE = Path(__file__).with_name("data") / "pcf_v80.json"
ZH_OVERLAY_FILE = Path(__file__).with_name("data") / "pcf_v80_zh.json"

# 覆盖层里一个指标条目的键：PCF ID 与 Metric ID 用 | 连接
METRIC_KEY_SEP = "|"


@lru_cache(maxsize=1)
def _load_dataset() -> Dict[str, Any]:
    """读取并缓存官方数据集；返回的 dict 不应被调用方修改。"""
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_zh_overlay() -> Dict[str, Any]:
    """读取中文参考译文覆盖层。

    覆盖层是可选的：文件不存在时返回空字典，系统照常运行（只是没有中文）。
    """
    if not ZH_OVERLAY_FILE.exists():
        return {}
    with ZH_OVERLAY_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def metric_overlay_key(external_id: str, metric_id: str) -> str:
    """指标条目的覆盖层键。"""
    return f"{external_id}{METRIC_KEY_SEP}{metric_id}"


# 译文来源标记
SOURCE_APQC_CN = "APQC_CN"  # 来自 APQC 中文整理版
SOURCE_REFERENCE = "REFERENCE"  # 本系统自建参考译文（非官方）


def _apply_category_translations(dataset: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    """把覆盖层里的分类中文名与中文定义写回分类行。"""
    entries = overlay.get("categories") or {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            # 数据集里已有的 name_zh 来自 APQC 中文整理版（L1–L3）
            if row.get("name_zh"):
                row["name_zh_source"] = SOURCE_APQC_CN
            patch = entries.get(row.get("external_id"))
            if not patch:
                continue
            # 覆盖层优先：它是人工审校的参考译文，官方中文整理版只在覆盖层缺该字段时兜底
            if patch.get("name_zh"):
                row["name_zh"] = patch["name_zh"]
                # name 是展示名：有中文就用中文，与 L1–L3 的既有口径一致
                row["name"] = patch["name_zh"]
                row["name_zh_source"] = SOURCE_REFERENCE
            if patch.get("description_zh"):
                row["description_zh"] = patch["description_zh"]


def _apply_metric_translations(dataset: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    """把覆盖层里的指标中文写回指标行；单位与分类走全局映射表。"""
    entries = overlay.get("metrics") or {}
    units = overlay.get("units") or {}
    categories = overlay.get("metric_categories") or {}
    if not (entries or units or categories):
        return
    for row in dataset.get("metrics", []):
        patch = entries.get(
            metric_overlay_key(row.get("external_id", ""), row.get("metric_id", ""))
        )
        if patch:
            if patch.get("name_zh"):
                row["name_zh"] = patch["name_zh"]
            if patch.get("formula_zh"):
                row["formula_zh"] = patch["formula_zh"]
            if patch.get("unit_zh"):
                row["unit_zh"] = patch["unit_zh"]
            if patch.get("category_label_zh"):
                row["category_label_zh"] = patch["category_label_zh"]
        # 单位与指标分类是枚举级取值，全局映射一次即可，不必逐条重复
        unit = row.get("unit")
        if unit and unit in units:
            row.setdefault("unit_zh", units[unit])
        metric_category = row.get("metric_category")
        if metric_category and metric_category in categories:
            row.setdefault("category_label_zh", categories[metric_category])
        # 指标译文一律是本系统自建参考译文
        if any(
            row.get(field) for field in ("name_zh", "formula_zh", "unit_zh", "category_label_zh")
        ):
            row["translation_source"] = SOURCE_REFERENCE


def chinese_coverage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """统计中文覆盖率，供导入报告与回归测试使用。"""
    categories = 0
    categories_with_zh = 0
    definitions = 0
    definitions_with_zh = 0
    seen: Dict[str, Dict[str, Any]] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            key = row.get("external_id")
            if key in seen:
                continue
            seen[key] = row
    for row in seen.values():
        categories += 1
        if row.get("name_zh"):
            categories_with_zh += 1
        if row.get("description"):
            definitions += 1
            if row.get("description_zh"):
                definitions_with_zh += 1

    metrics = dataset.get("metrics", [])
    metrics_with_zh = sum(1 for row in metrics if row.get("name_zh"))
    formulas_with_zh = sum(1 for row in metrics if row.get("formula_zh"))
    units_with_zh = sum(1 for row in metrics if row.get("unit_zh"))

    def pct(part: int, whole: int) -> float:
        return round(part * 100 / whole, 2) if whole else 0.0

    return {
        "categories": categories,
        "categories_with_zh": categories_with_zh,
        "categories_pct": pct(categories_with_zh, categories),
        "definitions": definitions,
        "definitions_with_zh": definitions_with_zh,
        "definitions_pct": pct(definitions_with_zh, definitions),
        "metrics": len(metrics),
        "metrics_with_zh": metrics_with_zh,
        "metrics_pct": pct(metrics_with_zh, len(metrics)),
        "formulas_with_zh": formulas_with_zh,
        "formulas_pct": pct(formulas_with_zh, len(metrics)),
        "units_with_zh": units_with_zh,
        "units_pct": pct(units_with_zh, len(metrics)),
    }


@lru_cache(maxsize=1)
def load_pcf_v80() -> Dict[str, Any]:
    """读取官方数据集并合并中文参考译文覆盖层；返回的 dict 不应被调用方修改。"""
    # 必须复制后再合并：`_load_dataset()` 是进程级缓存，合并是原地改写，
    # 直接改会把缓存污染成「已合并」状态，之后再读原始数据就会拿到译文版本。
    dataset = copy.deepcopy(_load_dataset())
    overlay = load_zh_overlay()
    if overlay:
        _apply_category_translations(dataset, overlay)
        _apply_metric_translations(dataset, overlay)
    return dataset


def canonical_category_names() -> Dict[str, str]:
    """分类节点的规范中文名：官方中文整理版优先，其次覆盖层参考译文。

    官方译名优先是项目硬规则。覆盖层与官方目前零重叠，但优先级必须显式写死，
    否则以后官方补录中文时会被覆盖层悄悄盖掉。
    """
    dataset = _load_dataset()
    overlay = load_zh_overlay()
    result: Dict[str, str] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            zh = row.get("name_zh")
            if zh:
                result.setdefault(row["external_id"], zh)
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("name_zh")
        if zh:
            result.setdefault(external_id, zh)
    return result


def framework_codes() -> List[str]:
    return [item["code"] for item in load_pcf_v80()["frameworks"]]


def framework(code: str) -> Dict[str, Any]:
    for item in load_pcf_v80()["frameworks"]:
        if item["code"] == code:
            return item
    raise KeyError(f"PCF 数据集中没有框架 {code}")


def category_rows(code: str) -> List[Dict[str, Any]]:
    return framework(code)["categories"]


def metric_rows() -> List[Dict[str, Any]]:
    return load_pcf_v80()["metrics"]


def overlay_provenance() -> Optional[Dict[str, Any]]:
    """覆盖层的来源说明；界面用它标注「参考译文（非官方）」。"""
    return load_zh_overlay().get("provenance")
