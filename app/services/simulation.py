"""路径模拟：基于模型快照枚举路径并汇总概率/周期/成本。

这不是离散事件仿真，也不改变运行时；只回答「按当前模型和概率，
可能走哪些路径、期望周期和成本是多少」。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.process import ProcessEdge, ProcessNode
from app.schemas.simulation import SimulationOut, SimulationPathOut

MAX_DEPTH = 40


class SimulationError(ValueError):
    pass


def _weights(edges: List[ProcessEdge]) -> List[float]:
    if not edges:
        return []
    explicit = [edge.probability if edge.probability is not None else 1.0 for edge in edges]
    if all(abs(value - 1.0) < 1e-9 for value in explicit):
        # 没有配置概率时，按出边均分；有默认分支时默认分支兜底
        default_index = next(
            (index for index, edge in enumerate(edges) if getattr(edge, "is_default", False)),
            None,
        )
        if default_index is not None:
            return [1.0 if index == default_index else 0.0 for index in range(len(edges))]
        return [1.0 / len(edges)] * len(edges)
    total = sum(explicit)
    if total <= 0:
        return [1.0 / len(edges)] * len(edges)
    if total < 1.0:
        default_index = next(
            (index for index, edge in enumerate(edges) if getattr(edge, "is_default", False)),
            0,
        )
        explicit[default_index] += 1.0 - total
        total = 1.0
    return [value / total for value in explicit]


def simulate(
    nodes: List[ProcessNode],
    edges: List[ProcessEdge],
    start_node_key: Optional[str] = None,
    max_paths: int = 50,
) -> SimulationOut:
    node_map = {node.node_key: node for node in nodes}
    if not node_map:
        raise SimulationError("流程还是空的，无法模拟")
    if start_node_key:
        if start_node_key not in node_map:
            raise SimulationError(f"起点 {start_node_key} 不存在")
        starts = [start_node_key]
    else:
        starts = [
            node.node_key
            for node in sorted(nodes, key=lambda row: row.sequence_order)
            if node.node_type == "START"
        ]
        if not starts:
            starts = [
                node.node_key for node in sorted(nodes, key=lambda row: row.sequence_order)[:1]
            ]
    outgoing: Dict[str, List[ProcessEdge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source_key, []).append(edge)

    paths: List[Tuple[float, List[str], float, float, float]] = []

    def walk(
        node_key: str,
        probability: float,
        path: List[str],
        duration: float,
        wait: float,
        cost: float,
        depth: int,
    ) -> None:
        node = node_map.get(node_key)
        if node is None or depth > MAX_DEPTH:
            return
        current_path = path + [node_key]
        duration += node.duration_minutes or 0
        wait += node.wait_minutes or 0
        cost += node.cost or 0
        next_edges = outgoing.get(node_key, [])
        if node.node_type == "END" or not next_edges:
            paths.append((probability, current_path, duration, wait, cost))
            return
        weights = _weights(next_edges)
        for edge, weight in zip(next_edges, weights, strict=False):
            if weight <= 0:
                continue
            if edge.target_key in current_path:
                # 回路：保留一条到当前节点的路径，避免无限展开
                paths.append(
                    (probability * weight, current_path + [edge.target_key], duration, wait, cost)
                )
                continue
            walk(
                edge.target_key,
                probability * weight,
                current_path,
                duration,
                wait,
                cost,
                depth + 1,
            )

    for start in starts:
        walk(start, 1.0 / len(starts), [], 0.0, 0.0, 0.0, 0)

    paths.sort(key=lambda row: (-row[0], row[2]))
    top = paths[:max_paths]
    rows = [
        SimulationPathOut(
            probability=round(probability, 6),
            node_keys=path,
            node_names=[node_map[key].name if key in node_map else key for key in path],
            cycle_minutes=round(duration + wait, 2),
            work_minutes=round(duration, 2),
            wait_minutes=round(wait, 2),
            cost=round(cost, 2),
        )
        for probability, path, duration, wait, cost in top
    ]
    total_probability = sum(row.probability for row in rows)
    expected_cycle = (
        sum(row.probability * row.cycle_minutes for row in rows) / total_probability
        if total_probability
        else 0.0
    )
    expected_cost = (
        sum(row.probability * row.cost for row in rows) / total_probability
        if total_probability
        else 0.0
    )
    return SimulationOut(
        start_node_keys=starts,
        path_count=len(paths),
        returned=len(rows),
        total_probability=round(total_probability, 6),
        expected_cycle_minutes=round(expected_cycle, 2),
        expected_cost=round(expected_cost, 2),
        paths=rows,
    )
