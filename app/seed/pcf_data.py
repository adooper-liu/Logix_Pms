"""APQC PCF v8.0 生成数据加载器。

`data/pcf_v80.json` 由 `scripts/import_pcf.py` 从 APQC 官方 Excel 生成，
不要手工编辑；需要更新版本时重新运行脚本并提交产物。

数据以 PCF ID（`external_id`）为跨变体稳定键：
- `Hierarchy ID`（JSON 里的 `code`）会因行业元素插入而漂移，只用于展示；
- 中文名只覆盖 L1–L3；没有中文的节点 `name_zh` 为空，`name` 回落英文。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

DATA_FILE = Path(__file__).with_name("data") / "pcf_v80.json"


@lru_cache(maxsize=1)
def load_pcf_v80() -> Dict[str, Any]:
    """读取并缓存完整数据集；返回的 dict 不应被调用方修改。"""
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


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
