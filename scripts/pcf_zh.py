"""APQC PCF 中文参考译文的覆盖层工具。

覆盖层 `app/seed/data/pcf_v80_zh.json` 是人工维护的产物，官方数据集
`app/seed/data/pcf_v80.json` 由 `scripts/import_pcf.py` 生成，两者分离：
重导官方 Excel 不会覆盖译文。

用法：

    python scripts/pcf_zh.py coverage            # 统计中文覆盖率
    python scripts/pcf_zh.py validate            # 校验覆盖层完整性（键存在、译文非空且含中文）
    python scripts/pcf_zh.py orphans              # 列出覆盖层里数据集已不存在的键（应为空）
    python scripts/pcf_zh.py export --kind category_names --start 0 --count 200 --out slice.json
    python scripts/pcf_zh.py export --kind metric_formulas --start 0 --count 200 --out slice.json
    python scripts/pcf_zh.py merge --file slice_zh.json          # 把译文片段并回覆盖层
    python scripts/pcf_zh.py merge-dir --dir <目录>              # 批量并回一个目录下的全部片段
    python scripts/pcf_zh.py normalize                           # 归一化口径译文的标点

`export` 产出待译片段（英文原文 + 术语表指针），`merge` 校验后并回覆盖层。
`--kind` 取值：category_names / category_descriptions / metric_names / metric_formulas。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.seed import pcf_data  # noqa: E402

DATASET_PATH = ROOT / "app" / "seed" / "data" / "pcf_v80.json"
OVERLAY_PATH = ROOT / "app" / "seed" / "data" / "pcf_v80_zh.json"
GLOSSARY_PATH = ROOT / "app" / "seed" / "data" / "pcf_zh_glossary.json"

CJK = re.compile(r"[\u4e00-\u9fff]")

KINDS = {
    "category_names": ("categories", "name_zh"),
    "category_descriptions": ("categories", "description_zh"),
    "metric_names": ("metrics", "name_zh"),
    "metric_formulas": ("metrics", "formula_zh"),
}


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def _dataset() -> Dict[str, Any]:
    return pcf_data.load_pcf_v80()


def _unique_categories() -> Dict[str, Dict[str, Any]]:
    """按 external_id 去重的分类节点（三个变体共用同一套 PCF ID）。"""
    result: Dict[str, Dict[str, Any]] = {}
    for framework in _dataset().get("frameworks", []):
        for row in framework.get("categories", []):
            result.setdefault(row["external_id"], row)
    return result


def _unique_metrics() -> Dict[str, Dict[str, Any]]:
    """按 (external_id, metric_id) 去重的指标条目。"""
    result: Dict[str, Dict[str, Any]] = {}
    for row in _dataset().get("metrics", []):
        key = pcf_data.metric_overlay_key(row["external_id"], row["metric_id"])
        result.setdefault(key, row)
    return result


# ------------------------------------------------------------------ 覆盖率


def cmd_coverage(_args: argparse.Namespace) -> int:
    stats = pcf_data.chinese_coverage(_dataset())
    for key, value in stats.items():
        print(f"  {key:>24}: {value}")
    return 0


# ------------------------------------------------------------------ 校验


def _overlay() -> Dict[str, Any]:
    if not OVERLAY_PATH.exists():
        return {}
    return _load_json(OVERLAY_PATH)


def _glossary() -> Dict[str, Any]:
    """读术语表。术语表是统一译法的唯一权威。"""
    if not GLOSSARY_PATH.exists():
        return {}
    return _load_json(GLOSSARY_PATH)


def cmd_validate(_args: argparse.Namespace) -> int:
    overlay = _overlay()
    categories = _unique_categories()
    metrics = _unique_metrics()
    problems: List[str] = []

    for external_id, patch in (overlay.get("categories") or {}).items():
        if external_id not in categories:
            problems.append(f"分类 {external_id} 在数据集中不存在（官方数据已更新？）")
            continue
        for field, value in patch.items():
            if not value:
                problems.append(f"分类 {external_id}.{field} 为空")
            elif not CJK.search(value):
                problems.append(f"分类 {external_id}.{field} 不含中文：{value!r}")

    for key, patch in (overlay.get("metrics") or {}).items():
        if key not in metrics:
            problems.append(f"指标 {key} 在数据集中不存在（官方数据已更新？）")
            continue
        for field, value in patch.items():
            if not value:
                problems.append(f"指标 {key}.{field} 为空")
            elif not CJK.search(value):
                problems.append(f"指标 {key}.{field} 不含中文：{value!r}")

    for unit, label in (overlay.get("units") or {}).items():
        if not CJK.search(label):
            problems.append(f"单位 {unit} 的中文不含中文：{label!r}")

    if problems:
        print(f"覆盖层有 {len(problems)} 个问题：")
        for item in problems[:60]:
            print(f"  - {item}")
        return 1
    print("覆盖层校验通过。")
    return 0


# ------------------------------------------------------------------ 孤儿键


def cmd_orphans(_args: argparse.Namespace) -> int:
    overlay = _overlay()
    categories = _unique_categories()
    metrics = _unique_metrics()
    orphan_categories = sorted(set(overlay.get("categories") or {}) - set(categories))
    orphan_metrics = sorted(set(overlay.get("metrics") or {}) - set(metrics))
    print(f"分类孤儿键：{len(orphan_categories)}")
    for key in orphan_categories[:30]:
        print(f"  - {key}")
    print(f"指标孤儿键：{len(orphan_metrics)}")
    for key in orphan_metrics[:30]:
        print(f"  - {key}")
    return 1 if (orphan_categories or orphan_metrics) else 0


# ------------------------------------------------------------------ 切片导出


def _slice_items(kind: str) -> List[Dict[str, Any]]:
    section, field = KINDS[kind]
    if section == "categories":
        items = []
        for external_id, row in _unique_categories().items():
            source = row.get(field.replace("_zh", "")) or ""
            if not source:
                continue
            if kind == "category_names" and row.get("name_zh"):
                continue  # 官方中文整理版已覆盖
            if kind == "category_descriptions" and row.get("description_zh"):
                continue
            items.append(
                {
                    "key": external_id,
                    "external_id": external_id,
                    "level": row.get("level"),
                    "name_en": row.get("name_en"),
                    "text_en": source,
                }
            )
        return items

    items = []
    for key, row in _unique_metrics().items():
        source = row.get(field.replace("_zh", "")) or ""
        if not source:
            continue
        if row.get(field):
            continue
        items.append(
            {
                "key": key,
                "external_id": row.get("external_id"),
                "metric_id": row.get("metric_id"),
                "metric_category": row.get("metric_category"),
                "name_en": row.get("name"),
                "text_en": source,
            }
        )
    return items


def cmd_export(args: argparse.Namespace) -> int:
    items = _slice_items(args.kind)
    window = items[args.start : args.start + args.count]
    payload = {
        "kind": args.kind,
        "section": KINDS[args.kind][0],
        "field": KINDS[args.kind][1],
        "total": len(items),
        "start": args.start,
        "count": len(window),
        "glossary": str(GLOSSARY_PATH.relative_to(ROOT)).replace("\\", "/"),
        "rules": [
            "译文必须与术语表一致；术语表里有对应译法的一律照用。",
            "L4/L5 活动名保持「动词+宾语」结构，不要加解释、不要加标点。",
            "指标口径是口径描述，保留全部数字、单位、期间等事实，不要意译或省略。",
            "译文必须含中文；不要输出英文；不要输出解释文字。",
        ],
        "items": window,
    }
    _save_json(Path(args.out), payload)
    print(f"已导出 {len(window)} 条（{args.kind}，共 {len(items)} 条）→ {args.out}")
    return 0


# ------------------------------------------------------------------ 合并


def _section_field(payload: Dict[str, Any]) -> Tuple[str, str]:
    """从切片载荷解析落位（section, field）。

    `export` 产出的切片带 `section`/`field`；早期用 split 脚本切出的切片只有 `kind`，
    这里按 kind 兜底，避免整批译文并不回去。
    """
    section = payload.get("section")
    field = payload.get("field")
    if section and field:
        return section, field
    kind = payload.get("kind")
    if kind in KINDS:
        return KINDS[kind]
    raise KeyError(f"切片缺少 section/field，且 kind={kind!r} 无法识别")


def apply_translation(
    overlay: Dict[str, Any], section: str, key: str, field: str, value: str
) -> None:
    """字段级合并单条译文。

    同一个分类可能同时出现在 name_zh 与 description_zh 两种切片里，
    整块覆盖会把先并入的字段冲掉（实测丢 162 条），所以这里只写本次要落的字段。
    """
    overlay.setdefault(section, {}).setdefault(key, {})[field] = value


def cmd_merge(args: argparse.Namespace) -> int:
    source = Path(args.file)
    payload = _load_json(source)
    section, field = _section_field(payload)
    expected = {item["key"] for item in payload["items"]}

    translated = _load_json(Path(args.translated))
    problems: List[str] = []
    for key in expected:
        if key not in translated:
            problems.append(f"缺少译文：{key}")
    for key in translated:
        if key not in expected:
            problems.append(f"多余译文（不在切片里）：{key}")
    for key, value in translated.items():
        if not isinstance(value, dict) or not value.get(field):
            problems.append(f"{key} 的 {field} 为空或格式错误")
        elif not CJK.search(value[field]):
            problems.append(f"{key} 的 {field} 不含中文：{value[field]!r}")

    if problems:
        print(f"译文片段有 {len(problems)} 个问题，拒绝合并：")
        for item in problems[:40]:
            print(f"  - {item}")
        return 1

    overlay = _overlay()
    for key, value in translated.items():
        apply_translation(overlay, section, key, field, value[field])
    _save_json(OVERLAY_PATH, overlay)
    print(f"已并入 {len(translated)} 条 → {OVERLAY_PATH}")
    return 0


# ------------------------------------------------------------------ 批量合并


def cmd_merge_dir(args: argparse.Namespace) -> int:
    """把一个目录下所有 worker 产出的译文片段一次性并回覆盖层。

    每个 `zh_*.json` 必须对应同目录下同名的 `s_*.json` 切片文件，
    切片里的 section/field 决定译文落到覆盖层的哪个位置。
    """
    work_dir = Path(args.dir)
    overlay = _overlay()
    problems: List[str] = []
    merged = 0

    for translated_path in sorted(work_dir.glob("zh_*.json")):
        slice_path = work_dir / ("s_" + translated_path.name[len("zh_") :])
        if not slice_path.exists():
            problems.append(f"{translated_path.name} 找不到对应切片 {slice_path.name}")
            continue
        payload = _load_json(slice_path)
        section, field = _section_field(payload)
        expected = {item["key"] for item in payload["items"]}

        try:
            translated = _load_json(translated_path)
        except json.JSONDecodeError as exc:
            # 译文文件还没写完（worker 正在产出）：跳过，等它写完再合并。
            # 只有「文件完整但内容不合格」才是硬错误。
            print(f"  跳过 {translated_path.name}（文件尚未写完：{exc}）")
            continue

        missing = expected - set(translated)
        extra = set(translated) - expected
        if missing:
            problems.append(
                f"{translated_path.name} 缺 {len(missing)} 条（例：{sorted(missing)[:3]}）"
            )
        if extra:
            problems.append(f"{translated_path.name} 多 {len(extra)} 条（例：{sorted(extra)[:3]}）")
        for key in sorted(expected & set(translated)):
            value = translated[key]
            if not isinstance(value, dict) or not value.get(field):
                problems.append(f"{translated_path.name} {key} 的 {field} 为空或格式错误")
            elif not CJK.search(value[field]):
                problems.append(f"{translated_path.name} {key} 的 {field} 不含中文")

        if missing or extra:
            continue
        for key, value in translated.items():
            apply_translation(overlay, section, key, field, value[field])
        merged += len(translated)
        print(f"  合并 {translated_path.name}: {len(translated)} 条")

    if problems:
        print(f"有 {len(problems)} 个问题，未写入覆盖层：")
        for item in problems[:40]:
            print(f"  - {item}")
        return 1

    _save_json(OVERLAY_PATH, overlay)
    print(f"已并入 {merged} 条 → {OVERLAY_PATH}")
    # 合并进来的原文可能半角全角逗号混用，落库前先归一化
    normalized = normalize_overlay(overlay)
    if normalized:
        _save_json(OVERLAY_PATH, overlay)
        print(f"归一化标点：改动 {normalized} 处")
    return 0


# ------------------------------------------------------------------ 标点归一化

# 千分位逗号：1,000 / 1,000,000
THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+")


def normalize_formula_punctuation(text: str) -> str:
    """公式口径里的逗号统一成中文全角（千分位除外）。

    口径是**中文正文**（术语表规则 9）：正常用中文标点，句末句号。
    实测发现同一批 `IF(...=0,0,...)` 公式有三种写法并存：半角全角混用、
    全半角全用、还有个把 `0,0` 当成千分位数字保护的漏网之鱼。
    这里统一成全角，与其它 9 条纯中文标点的公式口径一致。

    数字字面量内部的千分位逗号必须原样保留（1,000）。
    """
    protected: Dict[str, str] = {}

    def _stash(match: re.Match[str]) -> str:
        token = f"\x00{len(protected)}\x00"
        protected[token] = match.group(0)
        return token

    result = THOUSANDS.sub(_stash, text).replace(",", "，")
    for token, value in protected.items():
        result = result.replace(token, value)
    return result


def normalize_label_punctuation(text: str) -> str:
    """名称类标签里的全角逗号换成顿号。

    术语表规则 13：活动名 / 指标名是短标签，不用句读，只允许顿号「、」分隔并列项。
    标签里出现的全角逗号基本都是并列项之间的分隔，直接换成顿号即可合法。
    """
    return text.replace("，", "、")


def apply_literal_fixes(text: str, fixes: Dict[str, str]) -> str:
    """按术语表的 `literal_fixes` 段统一同义异译。

    术语表是唯一权威：这里只做术语表写明的字面量替换，不自行发明译法。
    """
    for wrong, right in fixes.items():
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def normalize_prose_ending(text: str) -> str:
    """正文类译文补上句末句号。

    中文惯例：句末括号的句号放在括号**外**——「……（这是说明）。」而不是「……（这是说明。）」。
    """
    stripped = text.rstrip()
    if not stripped or stripped.endswith(("。", "！", "？")):
        return text
    if stripped.endswith(("）", ")")):
        return stripped + "。"
    return stripped + "。"


def normalize_overlay(overlay: Dict[str, Any]) -> int:
    """归一化覆盖层里的标点与术语，返回改动条数。

    按字段分两类（术语表规则 9 / 13）：
    - **名称类**（活动名 / 指标名）是短标签：全角逗号换成顿号；
    - **正文类**（定义 / 口径）是中文正文：逗号用全角，句末补句号。
    """
    fixes = _glossary().get("literal_fixes") or {}
    changed = 0
    for section, fields in (
        ("categories", ("name_zh", "description_zh")),
        ("metrics", ("name_zh", "formula_zh")),
    ):
        for patch in (overlay.get(section) or {}).values():
            for field in fields:
                text = patch.get(field)
                if not text:
                    continue
                normalized = apply_literal_fixes(text, fixes)
                if field == "name_zh":
                    normalized = normalize_label_punctuation(normalized)
                else:
                    normalized = normalize_prose_ending(normalized)
                    if field == "formula_zh":
                        normalized = normalize_formula_punctuation(normalized)
                if normalized != text:
                    patch[field] = normalized
                    changed += 1
    return changed


def cmd_normalize(_args: argparse.Namespace) -> int:
    """单独跑一次标点归一化（merge-dir 结束时会自动跑）。"""
    overlay = _overlay()
    changed = normalize_overlay(overlay)
    if changed:
        _save_json(OVERLAY_PATH, overlay)
    print(f"标点归一化：改动 {changed} 处")
    return 0


# ------------------------------------------------------------------ 入口


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APQC PCF 中文参考译文覆盖层工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("coverage", help="统计中文覆盖率").set_defaults(func=cmd_coverage)
    sub.add_parser("validate", help="校验覆盖层完整性").set_defaults(func=cmd_validate)
    sub.add_parser("orphans", help="列出覆盖层里的孤儿键").set_defaults(func=cmd_orphans)

    export = sub.add_parser("export", help="导出待译切片")
    export.add_argument("--kind", required=True, choices=sorted(KINDS))
    export.add_argument("--start", type=int, default=0)
    export.add_argument("--count", type=int, default=200)
    export.add_argument("--out", required=True)
    export.set_defaults(func=cmd_export)

    merge = sub.add_parser("merge", help="把译文片段并回覆盖层")
    merge.add_argument("--file", required=True, help="export 产出的切片文件")
    merge.add_argument("--translated", required=True, help="译文 JSON：{key: {field: 值}}")
    merge.set_defaults(func=cmd_merge)

    merge_dir = sub.add_parser("merge-dir", help="批量并回一个目录下的全部译文片段")
    merge_dir.add_argument("--dir", required=True, help="存放 s_*.json 与 zh_*.json 的目录")
    merge_dir.set_defaults(func=cmd_merge_dir)

    sub.add_parser("normalize", help="归一化口径译文的标点").set_defaults(func=cmd_normalize)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
