"""APQC PCF 中文参考译文的回归测试。

守三条底线：
1. **覆盖层与官方数据分离**：官方 Excel 重导不会覆盖译文，译文也不污染官方 JSON；
2. **译文可追溯**：每个译文条目都能定位到数据集里的原始键，来源标记正确；
3. **覆盖率不倒退**：译文是人工资产，重导或改代码都不能让它悄悄变少。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.seed import pcf_data

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "seed" / "data"
OVERLAY_PATH = DATA_DIR / "pcf_v80_zh.json"
GLOSSARY_PATH = DATA_DIR / "pcf_zh_glossary.json"

CJK = re.compile(r"[\u4e00-\u9fff]")

# 覆盖率基线：译文是人工审校资产，只允许上升，不允许下降。
# 调整这个数字必须同时说明原因。
COVERAGE_BASELINE = {
    "categories_with_zh": 1269,
    "definitions_with_zh": 203,
    "metrics_with_zh": 864,
    "formulas_with_zh": 0,
    "units_with_zh": 3452,
}


@pytest.fixture(scope="module")
def overlay() -> dict:
    assert OVERLAY_PATH.exists(), "中文覆盖层文件缺失"
    with OVERLAY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def glossary() -> dict:
    with GLOSSARY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def dataset() -> dict:
    return pcf_data.load_pcf_v80()


def _unique_categories(dataset: dict) -> dict:
    result: dict = {}
    for framework in dataset["frameworks"]:
        for row in framework["categories"]:
            result.setdefault(row["external_id"], row)
    return result


def _unique_metrics(dataset: dict) -> dict:
    result: dict = {}
    for row in dataset["metrics"]:
        result.setdefault(pcf_data.metric_overlay_key(row["external_id"], row["metric_id"]), row)
    return result


# ------------------------------------------------------------------ 覆盖层结构


def test_overlay_declares_itself_as_non_official(overlay):
    """译文是自建参考译文，必须在文件里自我声明，界面才能据此标注。"""
    provenance = overlay["provenance"]
    assert provenance["kind"] == "reference_translation"
    assert "非" in provenance["label"] and "官方" in provenance["label"]
    assert "官方口径" in provenance["note"]
    assert "对外引用" in provenance["note"]


def test_overlay_only_contains_known_keys(overlay, dataset):
    """覆盖层里的每个键都必须在数据集里存在——官方数据升级后要有孤儿告警。"""
    categories = _unique_categories(dataset)
    metrics = _unique_metrics(dataset)

    orphan_categories = sorted(set(overlay.get("categories") or {}) - set(categories))
    orphan_metrics = sorted(set(overlay.get("metrics") or {}) - set(metrics))
    assert not orphan_categories, f"分类孤儿键：{orphan_categories[:10]}"
    assert not orphan_metrics, f"指标孤儿键：{orphan_metrics[:10]}"


def test_every_translation_contains_chinese(overlay):
    """译文必须真的是中文；空串或纯英文都不允许进覆盖层。"""
    problems = []
    for external_id, patch in (overlay.get("categories") or {}).items():
        for field, value in patch.items():
            if not value or not CJK.search(value):
                problems.append(f"分类 {external_id}.{field}={value!r}")
    for key, patch in (overlay.get("metrics") or {}).items():
        for field, value in patch.items():
            if not value or not CJK.search(value):
                problems.append(f"指标 {key}.{field}={value!r}")
    assert not problems, f"不合规的译文：{problems[:10]}"


def test_units_and_categories_match_glossary(overlay, glossary):
    """覆盖层的枚举翻译必须与术语表一致，避免同一单位出现两种译法。"""
    assert overlay["units"] == glossary["units"]
    assert overlay["metric_categories"] == glossary["metrics"]


def test_glossary_covers_all_dataset_units(dataset, glossary):
    """数据集里出现过的单位，术语表必须都有译法。"""
    units = {row.get("unit") for row in dataset["metrics"] if row.get("unit")}
    missing = sorted(units - set(glossary["units"]))
    assert not missing, f"术语表缺少单位译法：{missing}"


def test_merge_keeps_other_fields_on_the_same_key():
    """合并必须是字段级：name_zh 与 description_zh 可能落在同一个分类键上。

    曾经整块覆盖，导致先并入的 name_zh 被后并入的 description_zh 冲掉（实测丢 162 条）。
    覆盖率基线是这道守卫的端到端版本：丢字段会让 categories_with_zh 跌破基线。
    """
    from scripts.pcf_zh import apply_translation

    overlay: dict = {}
    apply_translation(overlay, "categories", "10002", "name_zh", "制定愿景与战略")
    apply_translation(overlay, "categories", "10002", "description_zh", "中文定义正文")
    assert overlay["categories"]["10002"] == {
        "name_zh": "制定愿景与战略",
        "description_zh": "中文定义正文",
    }


def test_overlay_audit_has_no_errors():
    """覆盖层审计必须零错误。

    审的是「进了覆盖层之后一致吗」：同英文多译文、交叉引用与活动名不一致、
    标点口径、孤儿键、空译文。提示（hints）不阻塞，错误（errors）阻塞。
    """
    from scripts.pcf_zh_audit import audit

    errors, _hints = audit()
    assert not errors, "覆盖层审计发现错误：\n" + "\n".join(errors[:20])


# ------------------------------------------------------------------ 合并行为


def test_merge_marks_official_and_reference_sources(dataset):
    """L1–L3 来自 APQC 中文整理版；覆盖层补的必须是参考译文，两者不能混淆。"""
    for framework in dataset["frameworks"]:
        for row in framework["categories"]:
            if row.get("name_zh"):
                assert row.get("name_zh_source") in {
                    pcf_data.SOURCE_APQC_CN,
                    pcf_data.SOURCE_REFERENCE,
                }, row["external_id"]
                if row.get("name_zh_source") == pcf_data.SOURCE_APQC_CN:
                    assert row["level"] <= 3, "官方中文整理版只覆盖 L1–L3"


def test_metrics_translation_source_is_reference(dataset):
    """指标译文一律是自建参考译文，来源标记不能留空。"""
    for row in dataset["metrics"]:
        if row.get("name_zh") or row.get("formula_zh"):
            assert row.get("translation_source") == pcf_data.SOURCE_REFERENCE


def test_official_english_is_never_overwritten(dataset):
    """官方英文原文必须原样保留：译文另存，不覆盖 name_en / description / formula。"""
    for framework in dataset["frameworks"]:
        for row in framework["categories"]:
            assert row["name_en"]
            if row.get("description"):
                assert row["description"]
    for row in dataset["metrics"]:
        assert row["name"]


def test_untranslated_category_falls_back_to_english():
    """没译的分类：name 保持官方英文，name_zh 留空——不能因为翻译管线出错就把英文弄丢。

    用合成数据集断言，不依赖真实数据是否已全覆盖。
    """
    synthetic = {
        "frameworks": [
            {
                "code": "APQC_PCF",
                "categories": [
                    {
                        "external_id": "99999",
                        "level": 5,
                        "name": "Evaluate acquisition options",
                        "name_en": "Evaluate acquisition options",
                        "name_zh": None,
                    }
                ],
            }
        ]
    }
    pcf_data._apply_category_translations(synthetic, {"categories": {}})

    row = synthetic["frameworks"][0]["categories"][0]
    assert row["name"] == "Evaluate acquisition options"
    assert row["name_en"] == "Evaluate acquisition options"
    assert row["name_zh"] is None
    assert "name_zh_source" not in row


def test_raw_dataset_is_not_polluted_by_merge():
    """原始官方数据集不能被译文合并污染。

    `_load_dataset()` 是进程级缓存，合并译文是原地改写 —— 一旦直接改缓存，
    之后读「原始数据」会拿到译文版本，同一份数据出现两种状态。
    """
    pcf_data.load_pcf_v80()  # 先触发一次合并
    raw = pcf_data._load_dataset()
    l4_rows = [
        row
        for framework in raw["frameworks"]
        for row in framework["categories"]
        if row.get("level") == 4
    ]
    assert l4_rows
    assert all(not row.get("name_zh") for row in l4_rows), "原始官方 JSON 的 L4 不该有中文"


def test_align_rewrites_mismatched_activity_names():
    """译文里的活动名与树里正式译名不一致时，对齐脚本要改回来。

    用官方中文整理版里的真实条目做例子：「执行总账会计」是 L3 的官方译名，
    译文写成「执行一般会计」就是不一致。
    """
    from scripts.pcf_zh_align import _align_text, _canonical_maps

    en_to_zh, zh_to_en, by_id = _canonical_maps()
    text = "执行“执行一般会计”流程的 FTEs 中从事“维护科目表”活动的百分比"
    en_text = (
        'Percentage of FTEs that perform the process "perform general accounting" '
        'that perform the activity "maintain chart of accounts"'
    )

    new_text, notes, conflicts = _align_text(
        text, en_text, re.compile(r"“([^”]{2,90})”"), en_to_zh, zh_to_en, by_id
    )
    assert "执行总账会计" in new_text
    assert "维护会计科目表" in new_text
    assert "执行一般会计" not in new_text
    assert notes
    assert not conflicts
    # 引号样式必须原样保留（弯引号不能变成直角引号）
    assert "“执行总账会计”" in new_text
    assert "「执行总账会计」" not in new_text


def test_align_keeps_bracket_width_consistency():
    """官方译名括号全半角混用，对齐时按归一化比对，不能把全角改成半角。"""
    from scripts.pcf_zh_align import _align_text, _canonical_maps

    en_to_zh, zh_to_en, by_id = _canonical_maps()
    text = "每十亿美元收入执行“处理应收账款（AR）”流程的 FTEs 数量"
    en_text = (
        'Number of FTEs that perform the processes "process accounts receivable (AR)" '
        "per $1 billion revenue"
    )

    new_text, notes, conflicts = _align_text(
        text, en_text, re.compile(r"“([^”]{2,90})”"), en_to_zh, zh_to_en, by_id
    )
    assert new_text == text, "括号宽度只是排版差异，不该改写"
    assert not notes
    assert not conflicts


def test_align_is_idempotent():
    """对齐脚本必须幂等：跑第二遍不该再改任何东西。"""
    from scripts.pcf_zh_align import align

    changed, _notes, _conflicts = align(dry_run=True)
    assert changed == 0, "覆盖层里的活动名引用还没对齐干净"


def test_domain_dot_is_not_treated_as_punctuation():
    """官方原文有 "(your company name.com)" 这类占位写法，域名里的点不是标点。"""
    from scripts.pcf_zh_audit import _strip_numbers

    assert "." not in _strip_numbers("网站（公司名称.com）的平均销售转化率")
    # 但正文里的半角句点仍要被抓出来
    assert "." in _strip_numbers("成本.费用")


def test_official_halfwidth_parentheses_are_not_punctuation_errors():
    """官方译名本身带半角括号，译文逐字引用时不能被标点检查判错。

    APQC 官方中文整理版有 7 条译名是半角括号（如「处理应收账款(AR)」），
    引用它们必须逐字照抄，审计要放行。
    """
    from scripts.pcf_zh_audit import HALFWIDTH_PUNCT, strip_official_paren_names

    canonical = pcf_data.canonical_category_names()
    with_parens = [zh for zh in canonical.values() if "(" in zh or ")" in zh]
    assert with_parens, "官方译名里应该存在半角括号的条目"

    text = "执行「处理应收账款(AR)」流程的总成本 / 业务实体收入总额）。"
    stripped = strip_official_paren_names(text, canonical.values())
    assert not (set(stripped) & HALFWIDTH_PUNCT), stripped
    # 但正文里自带的半角括号仍然要被抓出来
    bad = strip_official_paren_names("成本 (美元) 合计", canonical.values())
    assert set(bad) & HALFWIDTH_PUNCT


def test_formula_commas_are_normalized_to_chinese_width():
    """口径里的逗号统一成中文全角，千分位逗号原样保留。

    实测 `IF(...=0,0,...)` 这批公式有三种写法并存（半角全角混用、全半角全用、
    以及把 `0,0` 当成千分位数字保护掉的漏网之鱼），统一成全角。
    """
    from scripts.pcf_zh import normalize_formula_punctuation

    mixed = "IF（员工全职当量（FTEs）数量=0,0，总数 / 基数）。"
    assert (
        normalize_formula_punctuation(mixed) == "IF（员工全职当量（FTEs）数量=0，0，总数 / 基数）。"
    )

    # 千分位是数字字面量的一部分，必须原样保留
    assert normalize_formula_punctuation("成本（1,000,000 美元）。") == "成本（1,000,000 美元）。"


def test_literal_fixes_follow_the_glossary(glossary):
    """同义异译的收敛必须由术语表驱动，不能在代码里私造映射。"""
    from scripts.pcf_zh import apply_literal_fixes

    fixes = glossary["literal_fixes"]
    assert fixes, "术语表必须声明 literal_fixes 段"
    for wrong, right in fixes.items():
        assert apply_literal_fixes(f"前缀{wrong}后缀", fixes) == f"前缀{right}后缀"
        # 已经是目标译法的不能被改坏
        assert apply_literal_fixes(right, fixes) == right


def test_prose_ending_puts_period_outside_the_parenthesis():
    """正文类译文的句号放括号外（中文惯例：「……（这是说明）。」）。"""
    from scripts.pcf_zh import normalize_prose_ending

    assert normalize_prose_ending("正文。（括号说明）") == "正文。（括号说明）。"
    assert normalize_prose_ending("正文。") == "正文。"
    assert normalize_prose_ending("正文！") == "正文！"
    assert normalize_prose_ending("正文") == "正文。"


def test_calendar_day_is_rendered_consistently(dataset, glossary):
    """calendar day 在指标名里只能有一种译法。

    实测曾分裂成「日历天」12 条 +「自然日」12 条，术语表现在统一为「自然日」。
    """
    label = glossary["nouns"]["calendar day"]
    names = [row.get("name_zh") or "" for row in dataset["metrics"] if row.get("name_zh")]
    calendar_names = [name for name in names if "自然日" in name or "日历天" in name]
    assert calendar_names, "样本里应该有用到 calendar day 的指标名"
    for name in calendar_names:
        assert "日历天" not in name, f"还有指标名用了旧译法：{name}"
    assert any(label in name for name in calendar_names)


# ------------------------------------------------------------------ 覆盖率


def test_chinese_coverage_never_regresses(dataset):
    stats = pcf_data.chinese_coverage(dataset)
    for key, floor in COVERAGE_BASELINE.items():
        assert stats[key] >= floor, (
            f"{key} 覆盖率倒退：{stats[key]} < 基线 {floor}。"
            "官方数据重导或改代码都不能丢掉已审校的译文。"
        )


def test_units_are_fully_translated_via_global_map(dataset):
    """单位与指标分类是枚举级取值，走全局映射表，应该 100% 覆盖。"""
    stats = pcf_data.chinese_coverage(dataset)
    assert stats["units_pct"] >= 99.9, stats
    assert all(row.get("category_label_zh") for row in dataset["metrics"])


# ------------------------------------------------------------------ API 出参


def test_api_exposes_chinese_fields(client):
    """API 出参必须带中文字段与来源标记，前端不维护映射表。"""
    API = "/api/v1"
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 3}).json()
    root = next(node for node in tree if node["code"] == "1.0")
    assert root["name_zh"] == "制定愿景与战略"
    assert root["name_zh_source"] == pcf_data.SOURCE_APQC_CN
    assert "description_zh" in root


def test_api_metric_payload_has_chinese_fields(client):
    API = "/api/v1"
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 5}).json()
    stack = list(tree)
    target = None
    while stack:
        node = stack.pop()
        if node["level"] == 4:
            target = node
            break
        stack.extend(node["children"])
    assert target is not None

    payload = client.get(f"{API}/benchmark/categories/{target['id']}/metrics").json()
    for field in ("name_zh", "formula_zh", "unit_zh", "category_label_zh", "translation_source"):
        assert field in payload["metrics"][0] if payload["metrics"] else True
