"""APQC PCF 中文覆盖层审计。

`pcf_zh.py` 管的是「译文能不能进覆盖层」；本脚本管的是**进了覆盖层之后一致吗**。
10,000+ 条并行翻译靠人眼看不住，这几条是硬门禁：

1. **同英文 → 多译文**：同一条英文在不同切片里必须译法一致；
2. **交叉引用一致**：定义/口径正文里的「译名[PCF ID]」必须与该 ID 的活动名译文**逐字一致**；
3. **标点口径**：活动名/指标名只用顿号「、」分隔并列项，其余标点禁用；
   定义与口径是中文正文，必须有句号、不能用半角标点；
4. **术语表遵从**：名称类译文的英文若命中术语表词条，中文必须用术语表译法；
5. **活动名引用一致**：指标名/口径里引用的活动名，必须与分类树里的正式译名一致。
   这条**以英文原文为锚**——只有英文能对上树里单个活动时才判错；
   英文是 APQC 简称或多个活动合并的短语时，树里本来就没有对应节点，只作提示。

用法：

    python scripts/pcf_zh_audit.py            # 人看
    python scripts/pcf_zh_audit.py --strict   # 有问题就退出码 1（CI 用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.seed import pcf_data  # noqa: E402

DATA_DIR = ROOT / "app" / "seed" / "data"
OVERLAY_PATH = DATA_DIR / "pcf_v80_zh.json"
GLOSSARY_PATH = DATA_DIR / "pcf_zh_glossary.json"

CJK = re.compile(r"[\u4e00-\u9fff]")
# 官方 1347 条中文译名里只出现过顿号，其余标点 0 次。
# 全角括号「（）」放行：它是限定注释的必要结构（如「（当前报告期）」「（天）」）。
LABEL_BANNED = set("，。；：！？「」")
METRIC_LABEL_BANNED = set("，。；！？「」")
HALFWIDTH_PUNCT = set(",;:.!?")

CROSS_REF = re.compile(r"「([^」]{1,90})」\[(\d+)\]")
# 官方原文用直双引号引用活动名；中文侧指标名用弯引号、口径用直角引号。
EN_QUOTED = re.compile(r'"([^"]{2,90})"')
ZH_QUOTED_CURLY = re.compile(r"“([^”]{2,90})”")
ZH_QUOTED_CORNER = re.compile(r"「([^」]{2,90})」")

# 数字字面量（0.000000001 / .000000001 / 1,000）里的半角标点必须保留，先摘出来再检查。
# 千分位必须严格是 3 位一组，否则 IF(...=0,0,...) 这种「参数分隔逗号」会被误当成数字保护掉。
NUM_LITERAL = re.compile(r"(?<![\d.])\.\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
# 域名/网址里的点不是标点：官方原文有 "(your company name.com)" 这类占位写法
DOMAIN_LITERAL = re.compile(r"[\w\u4e00-\u9fff-]*\.[A-Za-z]{2,}")
HALFWIDTH_PUNCT = set(",;:.!?()")


def _strip_numbers(text: str) -> str:
    """摘掉数字字面量与域名，剩下才是要检查标点的正文。"""
    return DOMAIN_LITERAL.sub("#", NUM_LITERAL.sub("#", text))


def strip_official_paren_names(text: str, canonical_values) -> str:
    """摘掉官方译名本身，让它们的半角括号不被当成标点违规。

    APQC 官方中文整理版有 7 条译名带半角括号（如「处理应收账款(AR)」）。
    译文引用活动名必须逐字照抄官方写法，所以这些括号要放行。
    """
    names = [zh for zh in canonical_values if "(" in zh or ")" in zh]
    if not names:
        return text
    pattern = re.compile("|".join(re.escape(name) for name in names))
    return pattern.sub("#", text)


def _norm_for_compare(text: str) -> str:
    """比对活动名时归一化纯排版差异。

    官方中文整理版里全角/半角括号混用（实测 12 条全角、7 条半角，如
    「处理应收账款(AR)」），而本系统译文统一用全角。这属于排版口径，不是译法差异。
    """
    return text.replace("（", "(").replace("）", ")").replace("　", "").replace(" ", "")


# 术语表里收录的、值得强制检查的多词词条
MIN_TERM_LEN = 4


def _load(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _unique_categories(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            result.setdefault(row["external_id"], row)
    return result


def _unique_metrics(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for row in dataset.get("metrics", []):
        key = pcf_data.metric_overlay_key(row["external_id"], row["metric_id"])
        result.setdefault(key, row)
    return result


def audit() -> Tuple[List[str], List[str]]:
    """返回 (错误列表, 提示列表)。错误必须修，提示可以接受。"""
    overlay = _load(OVERLAY_PATH)
    glossary = _load(GLOSSARY_PATH)
    dataset = pcf_data.load_pcf_v80()
    categories = _unique_categories(dataset)
    metrics = _unique_metrics(dataset)

    errors: List[str] = []
    hints: List[str] = []

    # ---- 规范名表：官方 L1–L3 > 覆盖层 ----
    canonical: Dict[str, str] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            zh = row.get("name_zh")
            if zh:
                canonical.setdefault(row["external_id"], zh)
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("name_zh")
        if zh:
            canonical.setdefault(external_id, zh)

    # ---- 1. 同英文 → 多译文（分类名 / 指标名分开比对）----
    en_to_zh: Dict[str, Dict[str, Dict[str, List[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("name_zh")
        row = categories.get(external_id)
        if not zh or row is None:
            continue
        en_to_zh["category"][row.get("name_en") or ""][zh].append(external_id)
    for key, patch in (overlay.get("metrics") or {}).items():
        zh = patch.get("name_zh")
        row = metrics.get(key)
        if not zh or row is None:
            continue
        en_to_zh["metric"][row.get("name") or ""][zh].append(key)

    for scope, table in en_to_zh.items():
        for en, variants in table.items():
            if not en or len(variants) < 2:
                continue
            detail = "；".join(f"{zh}（{len(ids)} 条）" for zh, ids in variants.items())
            errors.append(f"[{scope}] 同一英文出现多种译法：{en[:60]} → {detail}")

    # ---- 2. 交叉引用一致 ----
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("description_zh")
        if not zh:
            continue
        for quoted, ref in CROSS_REF.findall(zh):
            want = canonical.get(ref)
            if want and want != quoted:
                errors.append(
                    f"[定义 {external_id}] 交叉引用 [{ref}] 写的是「{quoted}」，应为「{want}」"
                )
    for key, patch in (overlay.get("metrics") or {}).items():
        zh = patch.get("formula_zh")
        if not zh:
            continue
        for quoted, ref in CROSS_REF.findall(zh):
            want = canonical.get(ref)
            if want and want != quoted:
                errors.append(f"[口径 {key}] 交叉引用 [{ref}] 写的是「{quoted}」，应为「{want}」")

    # ---- 3. 标点口径 ----
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("name_zh")
        if not zh:
            continue
        bad = sorted(set(ch for ch in zh if ch in LABEL_BANNED))
        if bad:
            errors.append(f"[活动名 {external_id}] 用了禁用标点 {bad}：{zh[:50]}")
    for key, patch in (overlay.get("metrics") or {}).items():
        zh = patch.get("name_zh")
        if not zh:
            continue
        bad = sorted(set(ch for ch in zh if ch in METRIC_LABEL_BANNED))
        if bad:
            errors.append(f"[指标名 {key}] 用了禁用标点 {bad}：{zh[:50]}")

    # ---- 4. 半角标点（数字字面量里的除外）----
    canonical_names = list(canonical.values())
    for external_id, patch in (overlay.get("categories") or {}).items():
        for field in ("name_zh", "description_zh"):
            zh = patch.get(field)
            if not zh:
                continue
            stripped = _strip_numbers(strip_official_paren_names(zh, canonical_names))
            bad = sorted(set(ch for ch in stripped if ch in HALFWIDTH_PUNCT))
            if bad:
                errors.append(f"[分类 {external_id}.{field}] 混用了半角标点 {bad}：{zh[:50]}")
    for key, patch in (overlay.get("metrics") or {}).items():
        for field in ("name_zh", "formula_zh"):
            zh = patch.get(field)
            if not zh:
                continue
            stripped = _strip_numbers(strip_official_paren_names(zh, canonical_names))
            bad = sorted(set(ch for ch in stripped if ch in HALFWIDTH_PUNCT))
            if bad:
                errors.append(f"[指标 {key}.{field}] 混用了半角标点 {bad}：{zh[:50]}")

    # ---- 5. 引用的活动名必须与树里的正式译名一致（以英文原文为锚）----
    # 官方原文用直双引号引用活动名：perform the process "manage sales orders" ...
    # 中文侧指标名用弯引号「“”」、口径用直角引号「「」」。
    #
    # 只在「英文原文能对上分类树里的单个活动」时才判错。英文引用的是 APQC
    # 自有简称（"manage customer requests/inquiries"）或把多个活动并进一个引号串
    # （"provide sourcing governance and perform category management"）时，
    # 树里本来就没有对应节点，拿中文去比对只会全判成误报。
    tree_en_to_zh: Dict[str, str] = {}
    for external_id, zh in canonical.items():
        row = categories.get(external_id)
        if row is None:
            continue
        en = (row.get("name_en") or "").strip().lower()
        if en:
            tree_en_to_zh.setdefault(en, zh)

    unknown_refs: Dict[str, int] = defaultdict(int)
    for key, patch in (overlay.get("metrics") or {}).items():
        row = metrics.get(key)
        if row is None:
            continue
        for zh_field, en_field in (("name_zh", "name"), ("formula_zh", "formula")):
            zh = patch.get(zh_field)
            if not zh:
                continue
            en_spans = EN_QUOTED.findall(row.get(en_field) or "")
            if not en_spans:
                continue
            zh_spans = ZH_QUOTED_CURLY.findall(zh) + ZH_QUOTED_CORNER.findall(zh)
            for en_span in en_spans:
                want = tree_en_to_zh.get(en_span.strip().lower())
                if want is None:
                    unknown_refs[en_span.strip()] += 1
                    continue
                if not any(_norm_for_compare(want) in _norm_for_compare(span) for span in zh_spans):
                    errors.append(
                        f"[指标 {key}.{zh_field}] 引用活动「{en_span}」的正式译名是「{want}」，译文里没出现"
                    )
    for en_span, count in sorted(unknown_refs.items(), key=lambda kv: -kv[1]):
        hints.append(
            f"[引用] 英文引用的「{en_span}」在分类树里没有对应活动（{count} 处），只作提示"
        )

    # ---- 6. 正文标点与事实保真 ----
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("description_zh")
        if not zh:
            continue
        if not zh.rstrip().endswith(("。", "！", "？")):
            hints.append(f"[定义 {external_id}] 结尾没有句号")
    for key, patch in (overlay.get("metrics") or {}).items():
        zh = patch.get("formula_zh")
        if not zh:
            continue
        if not zh.rstrip().endswith(("。", "！", "？")):
            hints.append(f"[口径 {key}] 结尾没有句号")

    # ---- 5. 术语表遵从（只查名称类，定义正文允许意译）----
    terms = [
        (term, label)
        for term, label in list(glossary.get("nouns", {}).items())
        + list(glossary.get("verbs", {}).items())
        if len(term) >= MIN_TERM_LEN and " " in term
    ]
    for external_id, patch in (overlay.get("categories") or {}).items():
        zh = patch.get("name_zh")
        row = categories.get(external_id)
        if not zh or row is None:
            continue
        en = (row.get("name_en") or "").lower()
        for term, label in terms:
            if term in en and label not in zh:
                hints.append(
                    f"[活动名 {external_id}] 英文含「{term}」但中文未用术语表译法「{label}」"
                )
                break
    for key, patch in (overlay.get("metrics") or {}).items():
        zh = patch.get("name_zh")
        row = metrics.get(key)
        if not zh or row is None:
            continue
        en = (row.get("name") or "").lower()
        for term, label in terms:
            if term in en and label not in zh:
                hints.append(f"[指标名 {key}] 英文含「{term}」但中文未用术语表译法「{label}」")
                break

    # ---- 6. 基础健康度 ----
    for external_id, patch in (overlay.get("categories") or {}).items():
        if external_id not in categories:
            errors.append(f"[孤儿] 分类 {external_id} 不在数据集里")
        for field, value in patch.items():
            if not value:
                errors.append(f"[空值] 分类 {external_id}.{field}")
            elif not CJK.search(value):
                errors.append(f"[无中文] 分类 {external_id}.{field}={value!r}")
    for key, patch in (overlay.get("metrics") or {}).items():
        if key not in metrics:
            errors.append(f"[孤儿] 指标 {key} 不在数据集里")
        for field, value in patch.items():
            if not value:
                errors.append(f"[空值] 指标 {key}.{field}")
            elif not CJK.search(value):
                errors.append(f"[无中文] 指标 {key}.{field}={value!r}")

    return errors, hints


def main() -> int:
    parser = argparse.ArgumentParser(description="APQC PCF 中文覆盖层审计")
    parser.add_argument("--strict", action="store_true", help="有错误就返回 1")
    args = parser.parse_args()

    errors, hints = audit()
    stats = pcf_data.chinese_coverage(pcf_data.load_pcf_v80())

    print("覆盖层覆盖率：")
    for key in ("categories", "definitions", "metrics", "formulas", "units"):
        count_key = f"{key}_with_zh"
        if count_key in stats:
            print(f"  {key:>16}: {stats[count_key]:>5} / {stats.get(key, '-')}")

    print(f"\n错误 {len(errors)} 项，提示 {len(hints)} 项")
    if errors:
        print("\n---- 错误（必须修）----")
        for item in errors[:60]:
            print("  ", item)
        if len(errors) > 60:
            print(f"   ... 其余 {len(errors) - 60} 项省略")
    if hints:
        print("\n---- 提示（可接受）----")
        for item in hints[:30]:
            print("  ", item)
        if len(hints) > 30:
            print(f"   ... 其余 {len(hints) - 30} 项省略")

    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
