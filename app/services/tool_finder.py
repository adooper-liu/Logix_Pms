"""「按问题找工具」：把一句大白话问题映射到最合适的流程工具。

打分策略：
  1. 人工整理的同义词表命中 —— 权重最高（3.0），覆盖行业口语；
  2. 工具的名称/别名/用途/适用场景文本被问题中的词命中 —— 权重 1.0；
  3. 工具所在阶段与用户指定阶段一致 —— 加 0.5。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.models.tool import Tool
from app.services.text_match import tokens

# 口语问题 → 工具 code。一个词可以指向多个工具，命中即加分。
SYNONYMS: Dict[str, Sequence[str]] = {
    "审批": ["RACI", "BPR6", "TOBE", "BPMN"],
    "签批": ["RACI", "BPR6"],
    "流程长": ["VSM", "TOBE", "QUEUE-MODEL"],
    "周期": ["VSM", "QUEUE-MODEL", "TOBE", "BPR6"],
    "慢": ["VSM", "QUEUE-MODEL", "BPR6"],
    "交付": ["VSM", "QUEUE-MODEL", "TOBE"],
    "等待": ["QUEUE-MODEL", "VSM", "LEAN7"],
    "排队": ["QUEUE-MODEL", "LEAN7"],
    "积压": ["LEAN7", "KANBAN", "QUEUE-MODEL"],
    "库存": ["LEAN7", "KANBAN"],
    "返工": ["FIVE-WHY", "FISHBONE", "DMAIC", "LEAN7"],
    "质量": ["FIVE-WHY", "FISHBONE", "DMAIC", "CONTROL-CHART"],
    "差错": ["FIVE-WHY", "CONTROL-CHART", "DMAIC"],
    "客诉": ["CJM", "FIVE-WHY", "FISHBONE"],
    "客户投诉": ["CJM", "FIVE-WHY", "FISHBONE"],
    "体验": ["CJM", "DESIGN-THINKING"],
    "跨部门": ["SWIMLANE", "SIPOC", "RACI", "BPR6"],
    "部门墙": ["SWIMLANE", "BPR6", "RACI"],
    "扯皮": ["RACI", "SWIMLANE"],
    "责任": ["RACI", "SWIMLANE"],
    "权责": ["RACI"],
    "数据": ["PROCESS-MINING", "BI-DASHBOARD", "PARETO"],
    "日志": ["PROCESS-MINING"],
    "系统": ["PROCESS-MINING", "BPMN", "BI-DASHBOARD"],
    "自动化": ["BPMN", "LEAN7", "TOBE"],
    "变革": ["ADKAR", "STAKEHOLDER", "COMM-PLAN"],
    "抵触": ["ADKAR", "STAKEHOLDER", "COMM-PLAN"],
    "推不动": ["ADKAR", "STAKEHOLDER"],
    "推行": ["ADKAR", "PILOT", "TRAINING-MATRIX"],
    "试点": ["PILOT", "ROLLBACK"],
    "培训": ["TRAINING-MATRIX"],
    "上线": ["GOLIVE", "ROLLBACK", "TRAINING-MATRIX"],
    "风险": ["FMEA", "ROLLBACK"],
    "方案": ["DECISION-MATRIX", "TOBE", "FMEA"],
    "选型": ["DECISION-MATRIX"],
    "监控": ["CONTROL-CHART", "BI-DASHBOARD", "BALANCED-SCORE"],
    "预警": ["CONTROL-CHART", "BI-DASHBOARD"],
    "指标": ["BALANCED-SCORE", "CONTROL-CHART", "BI-DASHBOARD"],
    "KPI": ["BALANCED-SCORE", "BI-DASHBOARD"],
    "改善": ["PDCA", "DMAIC", "KAIZEN"],
    "持续": ["PDCA", "KAIZEN"],
    "浪费": ["LEAN7", "VSM"],
    "换型": ["LEAN7", "KANBAN"],
    "标准化": ["BPMN", "GOLIVE", "TRAINING-MATRIX"],
    "痛点": ["FISHBONE", "FIVE-WHY", "PARETO"],
    "原因": ["FIVE-WHY", "FISHBONE"],
    "根因": ["FIVE-WHY", "FISHBONE"],
    "瓶颈": ["QUEUE-MODEL", "PARETO", "VSM"],
    "优先级": ["PARETO", "DECISION-MATRIX"],
    "经验": ["KB"],
    "沉淀": ["KB"],
    "复盘": ["PDCA", "KB"],
}

HINT = (
    "匹配结果按得分排序。建议一次只解决问题最突出的那一条，"
    "选 1–2 个工具深用，而不是把工具清单全上一遍。"
)


def score_text(tool: Tool, problem: str, stage_no: Optional[int] = None) -> Tuple[float, List[str]]:
    """按同义词 + 工具自身文本 + 阶段给单个工具打文本分。

    供 `tool_finder.match()` 和问题驱动的 `tool_match` 共用，避免两套分词/同义词逻辑。
    """
    text = problem.strip()
    score = 0.0
    matched_on: List[str] = []

    if text:
        lower = text.lower()
        for word, codes in SYNONYMS.items():
            if word and (word in text or word.lower() in lower):
                if tool.code in codes:
                    score += 3.0
                    matched_on.append(word)

        haystack = " ".join(
            filter(
                None,
                [
                    tool.name,
                    tool.alias or "",
                    tool.purpose,
                    tool.when_to_use,
                    tool.pitfalls or "",
                ],
            )
        )
        for token in tokens(text):
            if token and token in haystack:
                score += 1.0
                matched_on.append(token)

    if stage_no is not None and tool.stage_no == stage_no:
        score += 0.5

    return score, sorted(set(matched_on), key=matched_on.index)


def match(
    tools: Sequence[Tool], problem: str, stage_no: Optional[int] = None
) -> List[Tuple[Tool, float, List[str]]]:
    hits: List[Tuple[Tool, float, List[str]]] = []
    for tool in tools:
        score, matched_on = score_text(tool, problem, stage_no)
        if score > 0:
            hits.append((tool, round(score, 2), matched_on))

    hits.sort(key=lambda item: (-item[1], item[0].sort_order))
    return hits[:8]
