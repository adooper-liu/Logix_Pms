"""工具在生命周期上的位置，以及它和系统里已有页面的关系。

库里的四类（诊断 / 设计 / 落地 / 监控）不改。页面按阶段分段，
避免把战略和未来态算进同一个「设计」。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# key, 标签, 阶段号
SEGMENTS: List[Tuple[str, str, int]] = [
    ("strategy", "战略", 1),
    ("analysis", "分析", 2),
    ("design", "设计", 3),
    ("change", "变革", 4),
    ("performance", "绩效", 5),
    ("improve", "改进", 5),
    ("asset", "知识资产", 5),
]

_SEGMENT = {key: (key, label, stage) for key, label, stage in SEGMENTS}


def _place(
    segment: str,
    *,
    view: str = "",
    params: Dict[str, str] | None = None,
    page_label: str = "",
    note: str,
    computes: bool = False,
) -> dict:
    key, label, stage = _SEGMENT[segment]
    return {
        "segment": key,
        "label": label,
        "stage_no": stage,
        "view": view,
        "params": dict(params or {}),
        "page_label": page_label,
        "note": note,
        "computes": computes,
    }


# 每一份工具只登记一次。没有计算页的，view 留空，note 写明系统不替它算。
PLACES: Dict[str, dict] = {
    "OGSM": _place(
        "strategy",
        view="strategy",
        page_label="战略目标",
        note="填写后写成一条战略目标，并挂到所选流程。地图上的三个分数不在这里改。",
        computes=True,
    ),
    "SWOT": _place(
        "strategy",
        view="strategy",
        page_label="战略目标",
        note="四格先挂在流程上。勾选「留下」后，每一行写成一条战略目标。",
        computes=True,
    ),
    "GOAL-TREE": _place(
        "strategy",
        view="strategy",
        page_label="战略目标",
        note="顶端要赢的结果写成一条战略目标，拆开的几条写在说明里。",
        computes=True,
    ),
    "SIPOC": _place(
        "analysis",
        note="起止和供应方写在这张表上，挂到流程。系统没有单独的 SIPOC 画布。",
    ),
    "SWIMLANE": _place(
        "analysis",
        view="designer",
        params={"tab": "model"},
        page_label="流程设计器",
        note="泳道画在流程设计器里。这里记下这次怎么分的道。",
        computes=True,
    ),
    "VSM": _place(
        "analysis",
        view="monitor",
        params={"tab": "analysis", "topic": "value"},
        page_label="流程分析 · 价值流",
        note="每一步的作业和等待在流程分析里看。这里记下这次判断。",
        computes=True,
    ),
    "FIVE-WHY": _place(
        "analysis",
        view="monitor",
        params={"tab": "analysis", "topic": "cause"},
        page_label="流程分析 · 根因",
        note="根因卡在流程分析。这里把这次追问写下来。",
        computes=True,
    ),
    "FISHBONE": _place(
        "analysis",
        view="monitor",
        params={"tab": "analysis", "topic": "cause"},
        page_label="流程分析 · 根因",
        note="鱼骨图在这里只是方法说明。系统不画鱼骨，也不按类别汇总原因。根因仍看流程分析里的那张卡。",
        computes=False,
    ),
    "PARETO": _place(
        "analysis",
        note="帕累托在这里只是方法说明。系统不另算二八分布。",
    ),
    "PROCESS-MINING": _place(
        "analysis",
        view="monitor",
        params={"tab": "mining"},
        page_label="过程挖掘",
        note="变体、和模型走法的差异在过程挖掘。这里不另挖一遍。",
        computes=True,
    ),
    "CJM": _place(
        "analysis",
        note="客户旅程在这里只是方法说明。系统没有旅程画布。",
    ),
    "QUEUE-MODEL": _place(
        "analysis",
        view="monitor",
        params={"tab": "analysis", "topic": "bottleneck"},
        page_label="流程分析 · 瓶颈",
        note="瓶颈页标出等待长的步骤。排队公式不在系统里计算。",
        computes=False,
    ),
    "BPR6": _place(
        "design",
        note="六条原则写在这张表上。系统不另做原则打分。",
    ),
    "TOBE": _place(
        "design",
        view="designer",
        params={"tab": "model"},
        page_label="流程设计器",
        note="未来态画在流程设计器。这里记下这次留下什么。",
        computes=True,
    ),
    "RACI": _place(
        "design",
        view="designer",
        params={"tab": "raci"},
        page_label="流程设计器 · 权责",
        note="权责矩阵在设计器。它不给任务派执行人，执行人在流程执行的运行配置里。",
        computes=True,
    ),
    "FMEA": _place(
        "design",
        note="失效模式写在这张表上。系统不另算风险优先数。",
    ),
    "DECISION-MATRIX": _place(
        "design",
        note="备选和留下的那一个挂在流程上。权重不在页面上自动相乘。",
    ),
    "LEAN7": _place(
        "design",
        note="七种浪费是对照清单。系统不按活动名称把等待自动判成浪费。",
    ),
    "KANBAN": _place(
        "design",
        note="看板在这里只是方法说明。系统没有看板运行页。",
    ),
    "DESIGN-THINKING": _place(
        "design",
        note="工作坊的结论写在这张表上，挂到流程。",
    ),
    "BPMN": _place(
        "design",
        view="designer",
        params={"tab": "model"},
        page_label="流程设计器",
        note="这条流程的图在流程设计器。设计器可以按分支概率走一遍，这里没有仿真引擎。"
        "判断和退回在流程分析的规则与上下文。",
        computes=True,
    ),
    "ADKAR": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="变革要让人跟上的五步写在这张表上，并挂到流程。项目组合页可以再打开这一份。",
    ),
    "STAKEHOLDER": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="相关方怎么对待这次改动，写在这张表上，并挂到流程。",
    ),
    "TRAINING-MATRIX": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="谁要会什么，写在这张表上。到场记录在十层核对，不在这张表里自动生成。",
    ),
    "PILOT": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="试点范围和成功标准写在这张表上，并挂到流程。",
    ),
    "COMM-PLAN": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="对谁说什么，写在这张表上，并挂到流程。",
    ),
    "GOLIVE": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="上线前要核对的事项写在这张表上，并挂到流程。",
    ),
    "ROLLBACK": _place(
        "change",
        view="projects",
        page_label="流程项目组合",
        note="退回条件写在这张表上。变更单上的回退说明仍在设计器的变更里。",
    ),
    "BALANCED-SCORE": _place(
        "performance",
        view="monitor",
        params={"tab": "kpi"},
        page_label="KPI",
        note="红黄绿在 KPI 页。这里只记下这张卡怎么选指标，不另做一套计分。",
        computes=True,
    ),
    "BI-DASHBOARD": _place(
        "performance",
        view="monitor",
        params={"tab": "kpi"},
        page_label="KPI",
        note="仪表盘在这里只是方法说明。系统不另接一套商业智能，数看 KPI 页。",
        computes=False,
    ),
    "CONTROL-CHART": _place(
        "performance",
        view="monitor",
        params={"tab": "kpi"},
        page_label="KPI",
        note="控制图在这里只是方法说明。系统不算控制限。红黄绿在 KPI 页。",
        computes=False,
    ),
    "MINING-CONT": _place(
        "performance",
        view="monitor",
        params={"tab": "mining"},
        page_label="过程挖掘",
        note="持续看的就是过程挖掘页上的变体，不是另一条挖掘。",
        computes=True,
    ),
    "PDCA": _place(
        "improve",
        view="projects",
        page_label="流程项目组合",
        note="改进的一轮计划写在这张表上，并挂到流程。系统不另开试验轮次。",
    ),
    "DMAIC": _place(
        "improve",
        view="projects",
        page_label="流程项目组合",
        note="五个阶段的结论写在这张表上。系统不做试验设计。",
    ),
    "KAIZEN": _place(
        "improve",
        view="projects",
        page_label="流程项目组合",
        note="改善周的议题和结果写在这张表上。系统没有改善周看板。",
    ),
    "KB": _place(
        "asset",
        view="toolbox",
        params={"section": "resources"},
        page_label="全部资源",
        note="知识库是案例和模板，不是一种分析方法。条目在本页的全部资源里。",
        computes=False,
    ),
}


def segment_for(code: str, stage_no: int = 0) -> Tuple[str, str, int]:
    row = PLACES.get(code)
    if row:
        return row["segment"], row["label"], row["stage_no"]
    for key, label, stage in SEGMENTS:
        if stage == stage_no and key in {"analysis", "design", "change", "strategy"}:
            return key, label, stage
    return "asset", "知识资产", stage_no or 5


def place_for(code: str) -> dict:
    row = PLACES.get(code)
    if row is None:
        key, label, stage = segment_for(code)
        return {
            "segment": key,
            "label": label,
            "stage_no": stage,
            "view": "",
            "params": {},
            "page_label": "",
            "note": "填写后挂到所选流程。系统没有单独的计算页。",
            "computes": False,
        }
    return {
        "segment": row["segment"],
        "label": row["label"],
        "stage_no": row["stage_no"],
        "view": row["view"],
        "params": dict(row["params"]),
        "page_label": row["page_label"],
        "note": row["note"],
        "computes": row["computes"],
    }


def segments_out() -> List[dict]:
    return [{"key": key, "label": label, "stage_no": stage} for key, label, stage in SEGMENTS]
