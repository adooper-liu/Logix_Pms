"""流程设计器：按图求期望值的指标测算 + 改善建议。

## 为什么不是简单求和

早期实现是 `lead_time = Σ(每个节点的作业+等待)`，等于假设「所有节点各执行一次、按顺序跑完」。
这对有分支或回路的流程是错的：

- 有驳回回路 → 期望周期被**低估**（回路里的节点会被多次执行）
- 有并行分支 → 会被**高估**（两条分支被同时计入）

所以这里改成按流转概率求期望值。

## 两种返工，一套算法

模型里有两种返工，语义不同但都进入同一个计算：

1. **节点级返工率** `rework_rate`：该活动自身有 r 的概率需要重做。
   等价于一个自环，期望执行次数 = 1 / (1 - r)。
2. **路径级回路**：连线上的 `probability` / `condition` 表达「驳回后回到某一步」。

前者乘在节点时长上，后者体现在进入次数上，最终统一汇总为期望值。
`rework_loss` 则由「含返工」与「不含返工」两种口径相减得出，口径唯一。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set, Tuple

from app.models.enums import Methodology, NodeType
from app.models.process import ProcessEdge, ProcessNode
from app.schemas.process import DesignAnalysis, DesignMetrics, NodeMetric, Suggestion
from app.services.methodology import pick_methodology_by_metrics

# 测算假设：用于把"分钟"翻译成管理层听得懂的"人天"
ASSUMED_MONTHLY_VOLUME = 1000  # 月均单量
MINUTES_PER_FTE_DAY = 480  # 每人天有效工时

# 建议规则阈值，集中在此便于按公司实际校准
PCE_LOW = 0.15
WAIT_RATIO_HIGH = 0.50
HANDOFF_HIGH = 3
REWORK_HIGH = 0.10
APPROVAL_LEVELS_HIGH = 3
NODE_LEAD_OUTLIER = 1.5

REWORK_CAP = 0.95  # 返工率上限，避免 1.0 时除零发散
SOLVER_MAX_ITER = 500
SOLVER_TOL = 1e-9
SOLVER_CAP = 1e6  # 期望值超过这个量级视为发散


def _effective_levels(node: ProcessNode) -> int:
    if node.approval_levels > 0:
        return node.approval_levels
    return 1 if node.node_type == NodeType.APPROVAL.value else 0


def _ordered(nodes: Sequence[ProcessNode]) -> List[ProcessNode]:
    return sorted(nodes, key=lambda n: (n.sequence_order, n.id or 0))


def _rework_multiplier(rate: float) -> float:
    """返工率 r → 期望执行次数 1/(1-r)。"""
    r = min(max(float(rate or 0.0), 0.0), REWORK_CAP)
    return 1.0 / (1.0 - r)


# ------------------------------------------------------------------ 图求解


def _outgoing(
    nodes: Dict[str, ProcessNode],
    edges: Sequence[ProcessEdge],
    drop: Set[Tuple[str, str]] | None = None,
) -> Dict[str, List[Tuple[str, float]]]:
    """按源节点归并出边，并把概率归一化。

    约定：某节点出边概率之和不为 1 时按**相对权重**归一化。
    需要表达「流程在此终止」时，请显式连到 END 节点。
    """
    drop = drop or set()
    raw: Dict[str, List[Tuple[str, float]]] = {k: [] for k in nodes}
    for e in edges:
        if e.source_key not in nodes or e.target_key not in nodes:
            continue
        if (e.source_key, e.target_key) in drop:
            continue
        raw[e.source_key].append((e.target_key, max(0.0, float(e.probability))))

    out: Dict[str, List[Tuple[str, float]]] = {}
    for key, pairs in raw.items():
        total = sum(p for _, p in pairs)
        out[key] = [(dst, p / total) for dst, p in pairs] if total > 0 else []
    return out


def _sources(
    keys: Sequence[str], edges: Sequence[ProcessEdge], nodes: Dict[str, ProcessNode]
) -> Set[str]:
    """流程入口。

    两条规则取并集：
    1. 显式标成 START 的节点（即使它被驳回回路指回来，也仍然是入口）；
    2. 没有任何入边的节点（用户还没标 START 时的兜底）。

    END 节点永远不会被当作入口。
    """
    incoming = {k: 0 for k in keys}
    for e in edges:
        if e.source_key in nodes and e.target_key in incoming:
            incoming[e.target_key] += 1

    sources = {k for k in keys if incoming[k] == 0 and nodes[k].node_type != NodeType.END.value}
    sources |= {k for k in keys if nodes[k].node_type == NodeType.START.value}
    return sources


def _solve_entries(
    keys: Sequence[str],
    sources: Set[str],
    out: Dict[str, List[Tuple[str, float]]],
) -> Tuple[Dict[str, float], bool]:
    """求每个节点的期望进入次数。

    解 A[v] = b[v] + Σ_w A[w]·p(w→v)，b 为入口标记。
    用值迭代求解：收敛的前提是回路返回概率的乘积 < 1；
    若模型存在「无法退出的环路」，值会发散，此时返回 False 交给上层兜底。
    """
    base = {k: (1.0 if k in sources else 0.0) for k in keys}
    current = dict(base)

    for _ in range(SOLVER_MAX_ITER):
        nxt = dict(base)
        for key in keys:
            amount = current.get(key, 0.0)
            if amount == 0.0:
                continue
            for dst, p in out.get(key, ()):
                if dst in nxt:
                    nxt[dst] += amount * p
        delta = max((abs(nxt[k] - current[k]) for k in keys), default=0.0)
        current = nxt
        if any(v > SOLVER_CAP for v in current.values()):
            return current, False
        if delta <= SOLVER_TOL:
            return current, True
    return current, False


def _find_back_edges(
    keys: Sequence[str], out: Dict[str, List[Tuple[str, float]]]
) -> Set[Tuple[str, str]]:
    """DFS 找出所有回边（指向当前递归栈上节点的边），即构成环路的边。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in keys}
    back: Set[Tuple[str, str]] = set()

    for root in keys:
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        stack: List[Tuple[str, object]] = [(root, iter(out.get(root, ())))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for dst, _p in it:  # type: ignore[union-attr]
                if dst not in color:
                    continue
                if color[dst] == GRAY:
                    back.add((node, dst))
                elif color[dst] == WHITE:
                    color[dst] = GRAY
                    stack.append((dst, iter(out.get(dst, ()))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
    return back


@dataclass
class _Aggregate:
    lead: float = 0.0
    process: float = 0.0
    value_added: float = 0.0
    wait: float = 0.0
    cost: float = 0.0
    per_node: Dict[str, Dict[str, float]] = field(default_factory=dict)


def _aggregate(
    nodes: Dict[str, ProcessNode],
    entries: Dict[str, float],
    apply_rework: bool,
) -> _Aggregate:
    agg = _Aggregate()
    for key, node in nodes.items():
        mult = _rework_multiplier(node.rework_rate) if apply_rework else 1.0
        n_entries = entries.get(key, 0.0)
        work = node.duration_minutes * mult * n_entries
        idle = node.wait_minutes * mult * n_entries
        agg.per_node[key] = {
            "entries": n_entries,
            "visits": n_entries * mult,
            "lead": work + idle,
            "process": work,
            "wait": idle,
        }
        agg.lead += work + idle
        agg.process += work
        agg.wait += idle
        if node.is_value_added:
            # 增值时间只算「一次通过」：返工是同一个步骤的重复执行，
            # 按精益的定义属于浪费，不能计进增值时间——否则 PCE 会虚高。
            agg.value_added += node.duration_minutes * n_entries
        # 成本与时间同口径：返工意味着同一动作要再做一次，成本也要重复计
        agg.cost += node.cost * mult * n_entries
    return agg


# ------------------------------------------------------------------ 主流程


def analyze(
    process_id: int,
    nodes: Sequence[ProcessNode],
    edges: Sequence[ProcessEdge] = (),
) -> DesignAnalysis:
    if not nodes:
        return DesignAnalysis(
            process_id=process_id,
            metrics=_empty_metrics(),
            nodes=[],
            suggestions=[
                Suggestion(
                    code="EMPTY_MODEL",
                    severity="LOW",
                    title="流程还是空的",
                    detail="先在画布上把 As-Is 流程画出来（含作业时间、等待时间与流转连线），系统才能做周期测算。",
                    suggested_tool="SWIMLANE",
                )
            ],
            recommended_methodology=Methodology.BPI.value,
        )

    ordered = _ordered(nodes)
    by_key: Dict[str, ProcessNode] = {n.node_key: n for n in ordered}
    keys = [n.node_key for n in ordered]

    out_full = _outgoing(by_key, edges)
    sources = _sources(keys, edges, by_key)
    # 没有任何入口 → 所有节点都不可达，算出来的全是 0，必须当成错误而不是结果
    no_entry = not sources
    entries, converged = _solve_entries(keys, sources, out_full)
    full = _aggregate(by_key, entries, apply_rework=True)

    back_edges = _find_back_edges(keys, out_full)
    out_clean = _outgoing(by_key, edges, drop=back_edges)
    entries_clean, _ = _solve_entries(keys, sources, out_clean)
    clean = _aggregate(by_key, entries_clean, apply_rework=False)

    has_branch_or_loop = bool(back_edges) or any(len(v) > 1 for v in out_full.values())

    if not converged or no_entry:
        # 环路无法退出（例如 A→B→A 且两边概率都是 1）时期望值发散；
        # 没有入口时则全是 0。两种情况都退回「每个节点各算一次」的线性口径，
        # 并在建议里明确标注结果不可信——绝不拿一个假数字冒充期望值。
        entries = {k: 1.0 for k in keys}
        full = _aggregate(by_key, entries, apply_rework=False)
        clean = full

    lead = full.lead
    process_time = full.process
    value_added = full.value_added
    wait_total = full.wait
    unit_cost = full.cost
    per_node = full.per_node

    rework_loss = max(0.0, lead - clean.lead)
    rework_work = max(0.0, process_time - clean.process)

    linear_lead = sum(n.duration_minutes + n.wait_minutes for n in ordered)
    wait_ratio = wait_total / lead if lead > 0 else 0.0
    pce = value_added / lead if lead > 0 else 0.0
    rework_share = rework_work / process_time if process_time > 0 else 0.0

    lanes = {n.lane for n in ordered}
    approval_nodes = [n for n in ordered if n.node_type == NodeType.APPROVAL.value]
    total_approval_levels = sum(_effective_levels(n) for n in ordered)
    handoff_count = _count_handoffs(ordered, edges)

    # ---- 节点级指标
    reachable = [k for k in keys if per_node[k]["entries"] > 0]
    mean_weighted = (
        (sum(per_node[k]["lead"] for k in reachable) / len(reachable)) if reachable else 0.0
    )

    node_metrics: List[NodeMetric] = []
    for n in ordered:
        info = per_node[n.node_key]
        node_lead = n.duration_minutes + n.wait_minutes
        node_wait_share = n.wait_minutes / node_lead if node_lead > 0 else 0.0
        is_bottleneck = (
            (mean_weighted > 0 and info["lead"] >= mean_weighted * NODE_LEAD_OUTLIER)
            or (
                n.node_type == NodeType.APPROVAL.value
                and _effective_levels(n) >= APPROVAL_LEVELS_HIGH
            )
            or n.rework_rate >= REWORK_HIGH
        )
        node_metrics.append(
            NodeMetric(
                node_key=n.node_key,
                name=n.name,
                lane=n.lane,
                node_type=n.node_type,
                lead_minutes=round(node_lead, 1),
                value_minutes=round(n.duration_minutes if n.is_value_added else 0.0, 1),
                wait_share=round(node_wait_share, 4),
                visit_count=round(info["visits"], 3),
                weighted_minutes=round(info["lead"], 1),
                is_bottleneck=is_bottleneck,
            )
        )

    metrics = DesignMetrics(
        node_count=len(ordered),
        lane_count=len(lanes),
        handoff_count=handoff_count,
        approval_node_count=len(approval_nodes),
        total_approval_levels=total_approval_levels,
        lead_time_minutes=round(lead, 1),
        linear_lead_time_minutes=round(linear_lead, 1),
        has_branch_or_loop=has_branch_or_loop,
        diverged=(not converged) or no_entry,
        process_time_minutes=round(process_time, 1),
        value_added_minutes=round(value_added, 1),
        wait_minutes=round(wait_total, 1),
        wait_ratio=round(wait_ratio, 4),
        pce=round(pce, 4),
        rework_loss_minutes=round(rework_loss, 1),
        rework_work_minutes=round(rework_work, 1),
        unit_cost=round(unit_cost, 2),
        fte_days_saved_per_month=round(
            rework_work * ASSUMED_MONTHLY_VOLUME / MINUTES_PER_FTE_DAY, 1
        ),
    )

    suggestions = _build_suggestions(
        ordered,
        node_metrics,
        metrics,
        rework_share,
        edges,
        back_edges=back_edges,
        unreachable=[k for k in keys if per_node[k]["entries"] <= 0],
        diverged=not converged,
        no_entry=no_entry,
    )
    methodology, _reason = pick_methodology_by_metrics(pce, handoff_count, rework_share, wait_ratio)

    return DesignAnalysis(
        process_id=process_id,
        metrics=metrics,
        nodes=node_metrics,
        suggestions=suggestions,
        recommended_methodology=methodology.value,
    )


def _empty_metrics() -> DesignMetrics:
    return DesignMetrics(
        node_count=0,
        lane_count=0,
        handoff_count=0,
        approval_node_count=0,
        total_approval_levels=0,
        lead_time_minutes=0,
        linear_lead_time_minutes=0,
        has_branch_or_loop=False,
        diverged=False,
        process_time_minutes=0,
        value_added_minutes=0,
        wait_minutes=0,
        wait_ratio=0,
        pce=0,
        rework_loss_minutes=0,
        rework_work_minutes=0,
        unit_cost=0,
        fte_days_saved_per_month=0,
    )


def _count_handoffs(nodes: Sequence[ProcessNode], edges: Sequence[ProcessEdge]) -> int:
    """跨泳道移交次数：优先用连线推导，没有连线时退化为按顺序看泳道切换。"""
    lane_of = {n.node_key: n.lane for n in nodes}
    if edges:
        return sum(
            1
            for e in edges
            if lane_of.get(e.source_key) is not None
            and lane_of.get(e.target_key) is not None
            and lane_of[e.source_key] != lane_of[e.target_key]
        )
    ordered = _ordered(nodes)
    return sum(1 for a, b in zip(ordered, ordered[1:], strict=False) if a.lane != b.lane)


# ------------------------------------------------------------------ 建议


def _build_suggestions(
    ordered: Sequence[ProcessNode],
    node_metrics: Sequence[NodeMetric],
    m: DesignMetrics,
    rework_share: float,
    edges: Sequence[ProcessEdge] = (),
    back_edges: Set[Tuple[str, str]] = frozenset(),
    unreachable: Sequence[str] = (),
    diverged: bool = False,
    no_entry: bool = False,
) -> List[Suggestion]:
    out: List[Suggestion] = []
    bottlenecks = sorted(
        (n for n in node_metrics if n.is_bottleneck), key=lambda n: n.weighted_minutes, reverse=True
    )

    if no_entry:
        out.append(
            Suggestion(
                code="NO_ENTRY",
                severity="HIGH",
                title="找不到流程入口，测算结果不可信",
                detail=(
                    "所有节点都有入边、也没有任何节点被标为「开始」，系统无法确定流程从哪里开始。"
                    "请把一个节点设为「开始」类型，或检查是否多画了一条回路。"
                    "当前已退回「每个节点各算一次」的粗略口径。"
                ),
                suggested_tool="SWIMLANE",
            )
        )
    elif diverged:
        out.append(
            Suggestion(
                code="DIVERGED",
                severity="HIGH",
                title="流程存在无法退出的环路，测算结果不可信",
                detail=(
                    "模型里有环路没有出口（例如 A→B→A 且两边概率都是 100%），"
                    "理论周期是无穷大。当前已退回「每个节点各算一次」的粗略口径，"
                    "请检查连线上的概率与终止节点。"
                ),
                suggested_tool="TOBE",
            )
        )

    if unreachable:
        names = [n.name for n in ordered if n.node_key in set(unreachable)]
        out.append(
            Suggestion(
                code="UNREACHABLE_NODES",
                severity="MEDIUM",
                title=f"{len(unreachable)} 个节点与流程入口断开",
                detail=(
                    "以下节点没有任何入边、也不是流程入口，正常业务中永远不会被执行："
                    + "、".join(names[:6])
                    + "。它们不计入周期测算，但会让模型看起来比实际复杂。请补连线或删除。"
                ),
                related_nodes=list(unreachable),
                suggested_tool="SWIMLANE",
            )
        )

    # 1. 周期效率过低
    if m.pce < PCE_LOW:
        out.append(
            Suggestion(
                code="LOW_PCE",
                severity="HIGH",
                title=f"流程周期效率仅 {m.pce:.1%}",
                detail=(
                    f"期望端到端周期 {m.lead_time_minutes:.0f} 分钟中，真正的增值作业只有 "
                    f"{m.value_added_minutes:.0f} 分钟。行业基准里 PCE 低于 15% 属于典型"
                    "「等待型流程」，压缩局部作业时间收益有限，应优先重设流转路径。"
                ),
                suggested_tool="BPR6",
            )
        )

    # 2. 等待主导
    if m.wait_ratio >= WAIT_RATIO_HIGH:
        wait_nodes = sorted(node_metrics, key=lambda n: n.weighted_minutes, reverse=True)[:3]
        out.append(
            Suggestion(
                code="WAIT_DOMINANT",
                severity="HIGH",
                title=f"等待占端到端周期的 {m.wait_ratio:.0%}",
                detail=(
                    f"期望等待 {m.wait_minutes:.0f} 分钟。等待通常来自串行排产、批次排队与审批滞留，"
                    "把可并行的环节改为并行、把推式改为拉动式，是收益最快的一步。"
                ),
                related_nodes=[n.node_key for n in wait_nodes],
                suggested_tool="QUEUE-MODEL",
            )
        )

    # 3. 审批层级过多
    if m.total_approval_levels > APPROVAL_LEVELS_HIGH:
        approval_keys = [n.node_key for n in ordered if _effective_levels(n) > 0]
        out.append(
            Suggestion(
                code="TOO_MANY_APPROVALS",
                severity="HIGH",
                title=f"全流程累计 {m.total_approval_levels} 层审批",
                detail=(
                    "审批层级是纯非增值活动。建议按金额/风险分级授权：低风险事项决策点下沉到一线，"
                    "高风险事项保留但合并层级，同时用 RACI 明确「谁批准」而不是「谁都知道一下」。"
                ),
                related_nodes=approval_keys,
                suggested_tool="RACI",
            )
        )

    # 4. 返工（节点级返工率 + 路径回路，统一口径）
    if m.rework_loss_minutes > 0:
        rework_nodes = [n for n in ordered if n.rework_rate >= REWORK_HIGH]
        loop_desc = ""
        if back_edges:
            names = {n.node_key: n.name for n in ordered}
            loop_desc = (
                "；此外还有 "
                + str(len(back_edges))
                + " 条回路（"
                + "、".join(f"{names.get(a, a)}→{names.get(b, b)}" for a, b in list(back_edges)[:3])
                + "）"
            )
        out.append(
            Suggestion(
                code="REWORK_LOSS",
                severity="HIGH" if rework_share >= 0.15 else "MEDIUM",
                title=f"返工让周期多出 {m.rework_loss_minutes:.0f} 分钟（占期望周期的 "
                f"{m.rework_loss_minutes / m.lead_time_minutes:.0%}）",
                detail=(
                    f"返工带来的额外作业时间为 {m.rework_work_minutes:.0f} 分钟，"
                    f"占作业时间的 {rework_share:.0%}{loop_desc}。"
                    "返工是重复劳动的浪费，压缩环节时间解决不了问题。"
                    "应先做根因分析（5 Why / 鱼骨图），再从源头加防错（Poka-Yoke）或前置检查点。"
                ),
                related_nodes=[n.node_key for n in rework_nodes],
                suggested_tool="FIVE-WHY",
            )
        )

    # 5. 跨部门移交过多
    if m.handoff_count > HANDOFF_HIGH:
        out.append(
            Suggestion(
                code="MANY_HANDOFFS",
                severity="MEDIUM",
                title=f"跨泳道移交 {m.handoff_count} 次，涉及 {m.lane_count} 个部门/角色",
                detail=(
                    "每次移交都会带来信息丢失与责任真空。可考虑把端到端串成一个流程团队"
                    "（流程 Owner 制），或把相邻的跨部门环节合并由同一角色完成。"
                ),
                suggested_tool="SWIMLANE",
            )
        )

    # 6. 串行可并行
    parallel_pairs = _find_parallel_candidates(ordered, edges)
    if parallel_pairs:
        out.append(
            Suggestion(
                code="SERIAL_TO_PARALLEL",
                severity="MEDIUM",
                title=f"发现 {len(parallel_pairs)} 组可并行化的串行环节",
                detail=(
                    "以下相邻环节分属不同部门、且之间没有强依赖或判断分支，目前却是先后串行："
                    + "；".join(f"{a_name} → {b_name}" for _, a_name, _, b_name in parallel_pairs)
                    + "。改为并行可同时缩短周期，但需先确认双方资源是否具备并行处理能力。"
                ),
                related_nodes=[k for pair in parallel_pairs for k in (pair[0], pair[2])],
                suggested_tool="TOBE",
            )
        )

    # 7. 非增值作业占比过高
    task_nodes = [
        n for n in ordered if n.node_type in (NodeType.TASK.value, NodeType.HANDOFF.value)
    ]
    if task_nodes:
        non_va = [n for n in task_nodes if not n.is_value_added]
        if len(non_va) / len(task_nodes) >= 0.3:
            out.append(
                Suggestion(
                    code="NON_VALUE_ADDED_TASKS",
                    severity="MEDIUM",
                    title=f"{len(non_va)}/{len(task_nodes)} 个作业节点被标记为非增值",
                    detail=(
                        "按精益七大浪费对照：搬运、等待、过度加工、库存、动作、不良、过量生产。"
                        "逐个问「删掉这个环节，客户能感知到差别吗」，感知不到的就应删除或自动化。"
                    ),
                    related_nodes=[n.node_key for n in non_va],
                    suggested_tool="LEAN7",
                )
            )

    # 8. 权责不清
    no_owner = [n for n in ordered if not (n.owner_role or "").strip()]
    if no_owner:
        out.append(
            Suggestion(
                code="MISSING_OWNER",
                severity="LOW",
                title=f"{len(no_owner)} 个节点未指定负责人角色",
                detail="没有明确责任人的节点，在实际执行中会成为「三不管」地带，也是异常高发点。",
                related_nodes=[n.node_key for n in no_owner],
                suggested_tool="RACI",
            )
        )

    # 9. 单点高成本
    if m.unit_cost > 0:
        costly = sorted(ordered, key=lambda n: n.cost, reverse=True)[:1]
        if costly and costly[0].cost / m.unit_cost >= 0.4 and len(ordered) > 2:
            out.append(
                Suggestion(
                    code="COST_CONCENTRATION",
                    severity="LOW",
                    title=f"单节点占了 {costly[0].cost / m.unit_cost:.0%} 的执行成本",
                    detail=(
                        f"「{costly[0].name}」是成本集中点，改善这里的杠杆最大——"
                        "但先确认它是必要成本还是历史遗留。"
                    ),
                    related_nodes=[costly[0].node_key],
                    suggested_tool="DECISION-MATRIX",
                )
            )

    if not out:
        out.append(
            Suggestion(
                code="HEALTHY",
                severity="LOW",
                title="未发现结构性改善点",
                detail=(
                    f"当前 PCE {m.pce:.1%}、等待占比 {m.wait_ratio:.0%}、移交 {m.handoff_count} 次，"
                    "指标处于合理区间。建议转入运营监控，按 KPI 触发下一轮改善。"
                ),
                suggested_tool="CONTROL-CHART",
            )
        )

    # 瓶颈清单：按对期望周期的贡献排序
    if bottlenecks:
        top = bottlenecks[0]
        out.append(
            Suggestion(
                code="BOTTLENECK",
                severity="MEDIUM",
                title=f"瓶颈节点：{top.name}（贡献 {top.weighted_minutes:.0f} 分钟）",
                detail=(
                    f"共识别 {len(bottlenecks)} 个瓶颈/异常节点："
                    + "、".join(f"{n.name}({n.weighted_minutes:.0f}min)" for n in bottlenecks[:5])
                    + "。这里按「执行次数 × 单次时长」排序，而不是单次时长——"
                    "一个被反复执行的短环节，可能比一次性的长环节更值得改。"
                ),
                related_nodes=[n.node_key for n in bottlenecks],
                suggested_tool="QUEUE-MODEL",
            )
        )

    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(out, key=lambda s: severity_rank.get(s.severity, 3))


def _find_parallel_candidates(
    ordered: Sequence[ProcessNode], edges: Sequence[ProcessEdge] = ()
) -> List[Tuple[str, str, str, str]]:
    """找出「可以并行、但目前串行」的相邻环节。

    返回 (源key, 源名, 目标key, 目标名)。

    有连线时以连线为准——比按顺序猜准得多，也能自动排除「驳回」这类分支边
    （它们带条件或发生概率小于 1，本来就不该被并行化讨论）。
    没有连线时退化为按声明顺序看相邻跨泳道作业节点。
    """
    pairs: List[Tuple[str, str, str, str]] = []

    if edges:
        by_key = {n.node_key: n for n in ordered}
        for e in edges:
            a, b = by_key.get(e.source_key), by_key.get(e.target_key)
            if a is None or b is None:
                continue
            if a.node_type != NodeType.TASK.value or b.node_type != NodeType.TASK.value:
                continue
            if a.lane == b.lane:
                continue
            if e.condition or e.probability < 1.0:
                continue
            pairs.append((a.node_key, a.name, b.node_key, b.name))
        return pairs[:5]

    for a, b in zip(ordered, ordered[1:], strict=False):
        both_task = a.node_type == NodeType.TASK.value and b.node_type == NodeType.TASK.value
        cross_lane = a.lane != b.lane
        no_gate = a.duration_minutes > 0 and b.duration_minutes > 0
        if both_task and cross_lane and no_gate:
            pairs.append((a.node_key, a.name, b.node_key, b.name))
    return pairs[:5]
