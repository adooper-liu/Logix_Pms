"""把译文里引用的活动名统一成分类树里的正式译名。

为什么需要
----------
APQC 官方原文用直双引号引用活动名（perform the process "manage sales orders"），
中文侧指标名用弯引号「“”」、口径与定义用直角引号「「」」。同一件事在树里和指标名里
必须只有一个说法，否则用户在界面上看到两套译名。

实测问题：指标名里出现了「执行一般会计」，而树里该活动的正式译名是官方中文
「执行总账会计」——同一活动两种说法，共 28 处。

判定规则
--------
1. **英文锚定**：只有英文原文能对上分类树里的单个活动时才动手。
   英文引用的是 APQC 自有简称（"manage customer requests/inquiries"）或把多个活动
   并进一个引号串（"provide sourcing governance and perform category management"）时，
   树里本来就没有对应节点，一律不动。
2. **官方优先**：规范译名取自 `pcf_data.canonical_category_names()`，
   官方中文整理版（L1–L3）优先于覆盖层参考译文。
3. **按内容认领**：先用「中文引号内容 == 某活动的规范译名」认领，剩下的才按同一条
   指标内部的顺序兜底。纯位置配对历史上曾把 11 个活动名互相错换，错位比漏译更危险。
4. **不越界**：中文引号内容若本身就是**另一个**活动的规范译名，说明配对存疑，
   只报告不改，由人判断。

用法
----
    python scripts/pcf_zh_align.py            # 对齐并写回覆盖层
    python scripts/pcf_zh_align.py --dry-run  # 只报告，不写文件
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

DATA_DIR = ROOT / "app" / "seed" / "data"
OVERLAY_PATH = DATA_DIR / "pcf_v80_zh.json"

# 官方原文用直双引号引用活动名
EN_QUOTED = re.compile(r'"([^"]{2,90})"')
# 中文侧：指标名用弯引号，口径/定义用直角引号（可带 PCF 编号）
ZH_CURLY = re.compile(r"“([^”]{2,90})”")
ZH_CORNER = re.compile(r"「([^」]{1,90})」(?:\[(\d+)\])?")


def _lcs_len(a: str, b: str) -> int:
    """最长公共子序列长度，用来判断两个中文片段有多像。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            cur.append(prev[j] + 1 if ca == cb else max(cur[j], prev[j + 1]))
        prev = cur
    return prev[-1]


def _similarity(a: str, b: str) -> float:
    """相似度：LCS 长度 / 较长一方长度。"""
    longer = max(len(a), len(b))
    return _lcs_len(a, b) / longer if longer else 0.0


def _norm(text: str) -> str:
    """比对活动名时归一化纯排版差异。

    官方中文整理版里全角/半角括号混用（实测 12 条全角、7 条半角，如
    「处理应收账款(AR)」），本系统译文统一用全角。这属于排版口径，不是译法差异。
    """
    return text.replace("（", "(").replace("）", ")").replace("　", "").replace(" ", "")


def _to_fullwidth_parens(text: str) -> str:
    """写回译文时用全角括号：本系统译文的统一排版口径。"""
    return text.replace("(", "（").replace(")", "）")


def _canonical_maps() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """返回 (英文 → 规范中文, 规范中文 → 英文, PCF ID → 规范中文)。"""
    dataset = pcf_data._load_dataset()
    by_id = pcf_data.canonical_category_names()
    en_of: Dict[str, str] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            en_of.setdefault(row["external_id"], (row.get("name_en") or "").strip())

    en_to_zh: Dict[str, str] = {}
    zh_to_en: Dict[str, str] = {}
    for external_id, zh in by_id.items():
        en = en_of.get(external_id, "")
        if not en:
            continue
        en_to_zh.setdefault(en.lower(), zh)
        zh_to_en.setdefault(zh, en.lower())
        # 归一化后的索引：官方译名的括号全半角与译文可能不一致
        zh_to_en.setdefault(_norm(zh), en.lower())
    return en_to_zh, zh_to_en, by_id


def _pair_spans(
    en_spans: List[str], zh_spans: List[str], zh_to_en: Dict[str, str]
) -> Dict[int, str]:
    """把中文引号片段与英文引号片段配对，返回 {中文下标: 英文}。

    先按内容认领（中文内容就是某活动的规范译名），剩下的按同一条指标内的顺序兜底。
    """
    pairs: Dict[int, str] = {}
    used_en: set[str] = set()
    for idx, zh in enumerate(zh_spans):
        en = zh_to_en.get(zh) or zh_to_en.get(_norm(zh))
        if en and en in en_spans and en not in used_en:
            pairs[idx] = en
            used_en.add(en)

    rest_idx = [i for i in range(len(zh_spans)) if i not in pairs]
    rest_en = [e for e in en_spans if e not in used_en]
    # 长度可以不等：英文是多个活动合成一个引号串时，中文引号数天然对不上
    for idx, en in zip(rest_idx, rest_en, strict=False):
        pairs[idx] = en
    return pairs


def _align_text(
    text: str,
    en_text: str,
    zh_pattern: re.Pattern[str],
    en_to_zh: Dict[str, str],
    zh_to_en: Dict[str, str],
    by_id: Dict[str, str],
) -> Tuple[str, List[str], List[str]]:
    """对齐一段中文正文里的活动名引用。

    返回 (新文本, 改写说明, 存疑说明)。
    """
    notes: List[str] = []
    conflicts: List[str] = []
    en_spans = [e.strip().lower() for e in EN_QUOTED.findall(en_text)]
    if not en_spans:
        return text, notes, conflicts

    matches = list(zh_pattern.finditer(text))
    if not matches:
        return text, notes, conflicts

    # 带 PCF 编号的引用最可靠：直接按编号取规范译名
    new_text = text
    for match in reversed(matches):
        quoted = match.group(1)
        ref = match.group(2) if match.re.groups >= 2 else None
        if not ref:
            continue
        want = by_id.get(ref)
        if want and want != quoted:
            notes.append(f"{quoted} → {want}（按 PCF ID {ref}）")
            new_text = new_text[: match.start()] + f"「{want}」[{ref}]" + new_text[match.end() :]

    # 重新扫一遍：带编号的已经改好，剩下的是自由引用的片段
    matches = list(zh_pattern.finditer(new_text))
    zh_spans = [m.group(1) for m in matches]
    free_idx = [i for i, m in enumerate(matches) if not (m.re.groups >= 2 and m.group(2))]
    free_spans = [zh_spans[i] for i in free_idx]
    if not free_spans:
        return new_text, notes, conflicts

    pairs = _pair_spans(en_spans, free_spans, zh_to_en)
    replacements: Dict[int, str] = {}
    for local_idx, en in pairs.items():
        want = en_to_zh.get(en)
        if not want:
            continue
        current = free_spans[local_idx]
        # 括号全半角只是排版差异，不是译法差异
        if _norm(want) == _norm(current) or _norm(want) in _norm(current):
            continue
        other = zh_to_en.get(current) or zh_to_en.get(_norm(current))
        if other and other != en:
            conflicts.append(
                f"「{current}」疑为「{other}」的正式译名，与英文引用「{en}」对不上，未改"
            )
            continue
        replacements[free_idx[local_idx]] = _to_fullwidth_parens(want)
        notes.append(f"{current} → {want}（英文 {en}）")

    if not replacements:
        return new_text, notes, conflicts

    out: List[str] = []
    cursor = 0
    for i, match in enumerate(matches):
        out.append(new_text[cursor : match.start()])
        inner = match.group(1)
        quoted = replacements.get(i, inner)
        # 只换引号里的内文，引号样式与编号原样保留
        out.append(match.group(0).replace(inner, quoted, 1))
        cursor = match.end()
    out.append(new_text[cursor:])
    return "".join(out), notes, conflicts


def align(dry_run: bool = False) -> Tuple[int, List[str], List[str]]:
    """对齐覆盖层里的活动名引用，返回 (改写条数, 改写说明, 存疑说明)。"""
    en_to_zh, zh_to_en, by_id = _canonical_maps()
    overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))

    dataset = pcf_data._load_dataset()
    metric_rows: Dict[str, Dict[str, Any]] = {}
    for row in dataset.get("metrics", []):
        key = pcf_data.metric_overlay_key(row.get("external_id", ""), row.get("metric_id", ""))
        metric_rows.setdefault(key, row)
    category_rows: Dict[str, Dict[str, Any]] = {}
    for framework in dataset.get("frameworks", []):
        for row in framework.get("categories", []):
            category_rows.setdefault(row["external_id"], row)

    notes: List[str] = []
    conflicts: List[str] = []
    changed = 0

    for key, patch in (overlay.get("metrics") or {}).items():
        row = metric_rows.get(key)
        if row is None:
            continue
        for zh_field, en_field, pattern in (
            ("name_zh", "name", ZH_CURLY),
            ("formula_zh", "formula", ZH_CORNER),
        ):
            text = patch.get(zh_field)
            if not text:
                continue
            new_text, item_notes, item_conflicts = _align_text(
                text, row.get(en_field) or "", pattern, en_to_zh, zh_to_en, by_id
            )
            conflicts.extend(f"[指标 {key}.{zh_field}] {item}" for item in item_conflicts)
            if new_text != text:
                patch[zh_field] = new_text
                changed += 1
                notes.extend(f"[指标 {key}.{zh_field}] {item}" for item in item_notes)

    for external_id, patch in (overlay.get("categories") or {}).items():
        row = category_rows.get(external_id)
        if row is None:
            continue
        text = patch.get("description_zh")
        if not text:
            continue
        new_text, item_notes, item_conflicts = _align_text(
            text, row.get("description") or "", ZH_CORNER, en_to_zh, zh_to_en, by_id
        )
        conflicts.extend(f"[定义 {external_id}] {item}" for item in item_conflicts)
        if new_text != text:
            patch["description_zh"] = new_text
            changed += 1
            notes.extend(f"[定义 {external_id}] {item}" for item in item_notes)

    if changed and not dry_run:
        with OVERLAY_PATH.open("w", encoding="utf-8") as handle:
            json.dump(overlay, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")

    return changed, notes, conflicts


def main() -> int:
    parser = argparse.ArgumentParser(description="把译文里的活动名引用对齐到分类树正式译名")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    args = parser.parse_args()

    changed, notes, conflicts = align(dry_run=args.dry_run)
    print(f"对齐活动名引用：改写 {changed} 条，改写明细 {len(notes)} 处")
    for note in notes[:80]:
        print("  ", note)
    if len(notes) > 80:
        print(f"   ... 其余 {len(notes) - 80} 项省略")
    if conflicts:
        print(f"\n存疑 {len(conflicts)} 处（未改，需人工判断）：")
        for item in conflicts[:40]:
            print("  ", item)
        if len(conflicts) > 40:
            print(f"   ... 其余 {len(conflicts) - 40} 项省略")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
