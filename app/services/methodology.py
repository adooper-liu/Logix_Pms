"""立项向导：根据流程现状与改善目标，自动匹配 BPR / BPI / 精益 / 混合。

规则来源是方法论选择矩阵：
    严重过时、断裂、与战略脱节  → 目标 ≥50%  → BPR
    基本合理但效率不足、局部堵点 → 10–30%   → BPI
    现场/操作层浪费明显、波动大  → 持续流动 → 精益
    混合状态                     → 先 BPR 定架构，再 BPI/精益细化 → HYBRID
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Methodology, ProcessState, ScopeType
from app.models.tool import Tool
from app.schemas.project import (
    MethodologyRecommendation,
    MethodologyRecommendRequest,
    PhasePlanItem,
    ToolRef,
)

# 各方法论推荐调用的工具链（按 诊断 → 设计 → 落地 顺序）
TOOLCHAINS: Dict[str, List[str]] = {
    Methodology.BPR.value: [
        "SIPOC",
        "SWIMLANE",
        "VSM",
        "FIVE-WHY",
        "BPR6",
        "TOBE",
        "RACI",
        "FMEA",
        "DECISION-MATRIX",
        "ADKAR",
        "STAKEHOLDER",
        "GOLIVE",
    ],
    Methodology.BPI.value: [
        "PARETO",
        "FIVE-WHY",
        "SWIMLANE",
        "BPMN",
        "RACI",
        "KANBAN",
        "PILOT",
        "TRAINING-MATRIX",
        "GOLIVE",
    ],
    Methodology.LEAN.value: [
        "VSM",
        "QUEUE-MODEL",
        "LEAN7",
        "KANBAN",
        "TOBE",
        "PILOT",
        "KAIZEN",
        "CONTROL-CHART",
    ],
    Methodology.HYBRID.value: [
        "SIPOC",
        "VSM",
        "FIVE-WHY",
        "BPR6",
        "TOBE",
        "RACI",
        "LEAN7",
        "KANBAN",
        "FMEA",
        "ADKAR",
        "PILOT",
        "TRAINING-MATRIX",
    ],
}

BASE_METHODOLOGY: Dict[str, Methodology] = {
    ProcessState.SEVERE_OUTDATED.value: Methodology.BPR,
    ProcessState.SOUND_BUT_INEFFICIENT.value: Methodology.BPI,
    ProcessState.SHOPFLOOR_WASTE.value: Methodology.LEAN,
    ProcessState.MIXED.value: Methodology.HYBRID,
}

METHODOLOGY_LABEL = {
    Methodology.BPR.value: "BPR 业务流程重组（阶跃式）",
    Methodology.BPI.value: "BPI 业务流程优化（渐进式）",
    Methodology.LEAN.value: "精益改善（消除浪费）",
    Methodology.HYBRID.value: "混合模式（BPR 定架构 + BPI/精益细化）",
}


def _resolve_codes(db: Session, codes: List[str]) -> List[ToolRef]:
    if not codes:
        return []
    rows = db.scalars(select(Tool).where(Tool.code.in_(codes))).all()
    by_code = {row.code: row for row in rows}
    refs: List[ToolRef] = []
    for code in codes:  # 保持工具链预设顺序，而不是数据库返回顺序
        row = by_code.get(code)
        if row is not None:
            refs.append(
                ToolRef(code=row.code, name=row.name, category=row.category, stage_no=row.stage_no)
            )
    return refs


def recommend(db: Session, req: MethodologyRecommendRequest) -> MethodologyRecommendation:
    rationale: List[str] = []
    risks: List[str] = []
    confidence = 0.62

    methodology = BASE_METHODOLOGY.get(req.process_state.value, Methodology.BPI)
    rationale.append(
        f"流程现状判定为「{_state_label(req.process_state)}」，方法论矩阵的首选是 "
        f"{METHODOLOGY_LABEL[methodology.value]}。"
    )

    # ---- 目标改善幅度校正（阶跃 vs 渐进）
    if req.target_improvement_pct >= 50:
        if methodology is Methodology.LEAN:
            methodology = Methodology.HYBRID
            rationale.append(
                f"目标改善幅度 {req.target_improvement_pct:.0f}% 已属阶跃式（≥50%），"
                "单靠现场精益难以达成，升级为混合模式：先用 BPR 重设端到端架构，再用精益做实操层。"
            )
        elif methodology is Methodology.BPI:
            methodology = Methodology.BPR
            rationale.append(
                f"目标改善幅度 {req.target_improvement_pct:.0f}% 超出渐进优化的能力区间（BPI 通常 10–30%），"
                "上调为 BPR。"
            )
        else:
            rationale.append(
                f"目标改善幅度 {req.target_improvement_pct:.0f}%，属于阶跃式目标，与 BPR 的定位一致。"
            )
        confidence += 0.12
    elif req.target_improvement_pct < 10:
        rationale.append(
            f"目标改善幅度仅 {req.target_improvement_pct:.0f}%，偏低——若流程现状确实严重，"
            "建议重新校准目标，避免「大问题用小方案」。"
        )
        risks.append("目标幅度过小，可能无法覆盖变革投入，需重新评估立项必要性。")
        confidence -= 0.1
    else:
        confidence += 0.05

    # 现状严重但目标太低 → 明确预警
    if req.process_state is ProcessState.SEVERE_OUTDATED and req.target_improvement_pct < 30:
        risks.append(
            "现状判定为「严重过时」但目标低于 30%：以现有流程框架做局部改善，大概率改善后仍然过时。"
        )
        confidence -= 0.08

    # ---- 范围校正
    if req.scope is ScopeType.END_TO_END and methodology is Methodology.LEAN:
        methodology = Methodology.HYBRID
        rationale.append("范围是端到端跨职能，涉及组织与权责，精益不足以覆盖，调整为混合模式。")
        confidence += 0.03
    elif req.scope is ScopeType.END_TO_END:
        rationale.append(
            "范围为端到端跨职能，需要以流程 Owner 机制做端到端负责，符合结构性变革的适用条件。"
        )
        confidence += 0.05
    elif req.scope is ScopeType.LOCAL and methodology is Methodology.BPR:
        rationale.append(
            "范围为单部门内部——BPR 通常需要跨职能授权，若无法突破部门边界，实际落地会退化为 BPI。"
        )
        risks.append("BPR 在部门内部难以推进，建议提升立项层级或改用 BPI。")
        confidence -= 0.07
    elif req.scope is ScopeType.SHOPFLOOR and methodology is not Methodology.LEAN:
        rationale.append("范围聚焦现场操作层，精益工具（VSM / 看板 / 单件流）是性价比最高的选择。")

    # ---- 组织与数据条件
    if req.involves_org_change:
        rationale.append(
            "涉及组织/权责调整，必须同步设计 RACI 与流程 Owner 机制，变革管理全程介入。"
        )
        if methodology is Methodology.BPI:
            risks.append("BPI 常被误当作「不动的组织的手术」，涉及权责调整时应升级为 BPR。")
            confidence -= 0.05
        elif methodology in (Methodology.BPR, Methodology.HYBRID):
            confidence += 0.05
    if not req.data_available:
        risks.append(
            "缺少流程数据/日志：诊断阶段应先用时间观测或流程挖掘补齐基线数据，"
            "否则「改善了多少」无法验收。"
        )
        confidence -= 0.05
    else:
        rationale.append("具备流程数据基础，可支撑量化诊断与改善前后对比验收。")
        confidence += 0.05

    # ---- 周期可行性
    if req.duration_target_months < 6 and methodology in (Methodology.BPR, Methodology.HYBRID):
        risks.append(
            f"计划周期 {req.duration_target_months} 个月：BPR 类项目通常需要 6–18 个月，"
            "建议把「试点出成果」设为里程碑，而非全量上线。"
        )
        confidence -= 0.05

    # ---- 阶段配比建议
    if methodology is Methodology.HYBRID:
        phase_plan = [
            PhasePlanItem(
                layer="架构层",
                action="用 BPR 重设端到端流程架构与流程 Owner，先定「做什么、谁负责」",
            ),
            PhasePlanItem(
                layer="执行层", action="用 BPI 简化审批、合并环节、标准化表单，把新架构落到可执行"
            ),
            PhasePlanItem(
                layer="操作层", action="用精益工具（看板 / 单件流 / Poka-Yoke）消除现场浪费与波动"
            ),
        ]
    elif methodology is Methodology.BPR:
        phase_plan = [
            PhasePlanItem(
                layer="架构层", action="端到端整合、决策点下沉、并行化、去中介化，从零重设 To-Be"
            ),
            PhasePlanItem(
                layer="执行层", action="配套组织、IT、KPI、制度同步调整，形成可执行交付物"
            ),
            PhasePlanItem(layer="操作层", action="试点跑通后分批推广，用系统权限固化新流程"),
        ]
    elif methodology is Methodology.BPI:
        phase_plan = [
            PhasePlanItem(
                layer="执行层", action="聚焦瓶颈环节：简化审批层级、合并重复录入、标准化表单"
            ),
            PhasePlanItem(layer="操作层", action="RPA / 系统自动化替代人工搬运，压缩非增值时间"),
            PhasePlanItem(layer="架构层", action="保持现有流程框架不变，仅在确有断点时做局部调整"),
        ]
    else:
        phase_plan = [
            PhasePlanItem(layer="操作层", action="5S / 标准化作业 / 看板拉动，先把现场波动压下来"),
            PhasePlanItem(
                layer="执行层", action="用 VSM 找浪费，用 SMED / 单件流缩短换型与周转时间"
            ),
            PhasePlanItem(
                layer="架构层", action="建立 Kaizen 机制与流程 KPI，让改善成为常态而非项目"
            ),
        ]

    alternatives = [
        m
        for m in (Methodology.BPR, Methodology.BPI, Methodology.LEAN, Methodology.HYBRID)
        if m is not methodology
    ]

    confidence = max(0.05, min(0.95, round(confidence, 2)))
    headline = f"建议采用 {METHODOLOGY_LABEL[methodology.value]}（置信度 {confidence:.0%}）"

    return MethodologyRecommendation(
        methodology=methodology,
        confidence=confidence,
        headline=headline,
        rationale=rationale,
        phase_plan=phase_plan,
        recommended_tools=_resolve_codes(db, TOOLCHAINS.get(methodology.value, [])),
        risks=risks or ["未识别到显著风险，按标准五阶段推进即可。"],
        alternatives=alternatives,
    )


def _state_label(state: ProcessState) -> str:
    return {
        ProcessState.SEVERE_OUTDATED: "流程严重过时、断裂，与战略脱节",
        ProcessState.SOUND_BUT_INEFFICIENT: "流程基本合理但效率不足，存在局部堵点",
        ProcessState.SHOPFLOOR_WASTE: "现场/操作层浪费明显、波动大",
        ProcessState.MIXED: "混合状态",
    }[state]


def pick_methodology_by_metrics(
    pce: float,
    handoff_count: int,
    rework_share: float,
    wait_ratio: float,
) -> Tuple[Methodology, str]:
    """流程设计器测算完之后反推方法论，返回 (方法论, 一句话理由)。

    rework_share = 返工损失时间 / 作业时间，衡量返工占总工作量的比重。
    """
    if pce < 0.15 and handoff_count >= 3:
        return (
            Methodology.BPR,
            f"周期效率 PCE 仅 {pce:.1%} 且跨部门移交 {handoff_count} 次，属于结构性断裂，"
            "局部优化无法解决，建议 BPR 重设端到端流程。",
        )
    if rework_share >= 0.15:
        return (
            Methodology.LEAN,
            f"返工损失占作业时间的 {rework_share:.0%}，属于典型的质量波动浪费，"
            "建议用精益 + DMAIC 从源头消除，而非压缩环节时间。",
        )
    if wait_ratio > 0.6:
        return (
            Methodology.LEAN,
            f"等待占比高达 {wait_ratio:.0%}，问题集中在排队与流动而非环节本身，"
            "建议用精益拉动 / 看板改善流动。",
        )
    if pce < 0.35:
        return (
            Methodology.BPI,
            f"流程框架基本成立（PCE {pce:.1%}），瓶颈是局部效率，建议 BPI 渐进优化。",
        )
    return Methodology.BPI, f"流程整体健康（PCE {pce:.1%}），按 BPI 节奏做持续微调即可。"
