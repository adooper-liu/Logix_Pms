"""过程挖掘：从执行任务序列和记入的外部日志还原路径变体与耗时。

外部日志是人写进本系统的行。这里不连接 ERP 或 OA 去拉日志。
活动名称能对上模型节点名时，和实例用同一个节点键，避免同一条走法拆成两种变体。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.adoption import ProcessEventLog
from app.models.execution import ProcessInstance
from app.models.process import ProcessArch, ProcessNode
from app.schemas.mining import MiningHandoffOut, MiningOut, MiningVariantOut

SOURCE_LABELS = {
    "INSTANCE": "实例",
    "LOG": "手记日志",
    "MIXED": "实例和手记日志",
}


class _SeqMember:
    def __init__(
        self,
        names: Dict[str, str],
        cycle: Optional[float],
        actual: Optional[float],
        source: str,
        waits: List[Tuple[str, str, float]],
    ):
        self.names = names
        self.cycle = cycle
        self.actual = actual
        self.source = source
        self.waits = waits


def completed_variant_count(db: Session, process_id: int) -> int:
    """已完成任务序列里的路径变体数。流程不存在时返回 0。"""
    try:
        return variants(db, process_id, limit=1).variant_count
    except ValueError:
        return 0


def _task_stamp(task):
    return task.completed_at or task.created_at


def _case_wait(cycle: Optional[float], actual: Optional[float]) -> Optional[float]:
    if cycle is None or actual is None:
        return None
    gap = cycle - actual
    return gap if gap >= 0 else None


def _handoff_waits(tasks) -> List[Tuple[str, str, float]]:
    waits: List[Tuple[str, str, float]] = []
    ordered = [task for task in tasks if task.completed_at is not None]
    for index in range(1, len(ordered)):
        prev = ordered[index - 1]
        nxt = ordered[index]
        gap = (nxt.completed_at - prev.completed_at).total_seconds() / 60
        wait = gap - float(nxt.actual_minutes or 0)
        if wait > 0:
            waits.append((prev.name, nxt.name, wait))
    return waits


def variants(db: Session, process_id: int, limit: int = 20) -> MiningOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ValueError("流程不存在")
    nodes = list(db.scalars(select(ProcessNode).where(ProcessNode.process_id == process_id)).all())
    name_to_key = {node.name: node.node_key for node in nodes}
    key_to_name = {node.node_key: node.name for node in nodes}

    instances = list(
        db.scalars(
            select(ProcessInstance)
            .options(selectinload(ProcessInstance.tasks))
            .where(ProcessInstance.process_id == process_id)
            .order_by(ProcessInstance.started_at.desc())
            .limit(500)
        ).all()
    )
    grouped: Dict[tuple, List[_SeqMember]] = defaultdict(list)
    handoff_bucket: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    unsequenced = 0
    for instance in instances:
        tasks = sorted(
            (task for task in instance.tasks if task.status == "COMPLETED"),
            key=lambda row: (_task_stamp(row), row.id),
        )
        sequence = tuple(task.node_key for task in tasks)
        if not sequence:
            unsequenced += 1
            continue
        names = {task.node_key: task.name for task in tasks}
        cycle = None
        if instance.completed_at and instance.started_at:
            cycle = (instance.completed_at - instance.started_at).total_seconds() / 60
        actual_minutes = sum(task.actual_minutes or 0 for task in tasks)
        waits = _handoff_waits(tasks)
        for from_name, to_name, minutes in waits:
            handoff_bucket[(from_name, to_name)].append(minutes)
        grouped[sequence].append(_SeqMember(names, cycle, float(actual_minutes), "INSTANCE", waits))

    logs = list(
        db.scalars(select(ProcessEventLog).where(ProcessEventLog.process_id == process_id)).all()
    )
    by_case: Dict[str, List[ProcessEventLog]] = defaultdict(list)
    for row in logs:
        by_case[row.case_key].append(row)
    for events in by_case.values():
        events.sort(key=lambda row: (row.occurred_at, row.id))
        keys: List[str] = []
        names: Dict[str, str] = {}
        for row in events:
            activity = (row.activity_name or "").strip()
            if not activity:
                continue
            key = name_to_key.get(activity) or f"log:{activity}"
            keys.append(key)
            names[key] = key_to_name.get(key, activity)
        if not keys:
            continue
        grouped[tuple(keys)].append(_SeqMember(names, None, None, "LOG", []))

    rows: List[MiningVariantOut] = []
    total = sum(len(members) for members in grouped.values())
    for sequence, members in grouped.items():
        durations = [item.cycle for item in members if item.cycle is not None]
        actual = [item.actual for item in members if item.actual is not None]
        case_waits = [
            gap for item in members if (gap := _case_wait(item.cycle, item.actual)) is not None
        ]
        names: Dict[str, str] = {}
        for item in members:
            if item.source == "INSTANCE":
                names.update(item.names)
        for item in members:
            for key, value in item.names.items():
                names.setdefault(key, value)
        from_instances = sum(1 for item in members if item.source == "INSTANCE")
        from_logs = sum(1 for item in members if item.source == "LOG")
        if from_instances and from_logs:
            source = "MIXED"
        elif from_logs:
            source = "LOG"
        else:
            source = "INSTANCE"
        rows.append(
            MiningVariantOut(
                node_keys=list(sequence),
                node_names=[names.get(key, key) for key in sequence],
                instance_count=len(members),
                share_pct=round(len(members) / total * 100, 1) if total else 0.0,
                avg_cycle_minutes=round(sum(durations) / len(durations), 1) if durations else None,
                avg_actual_minutes=round(sum(actual) / len(actual), 1) if actual else None,
                avg_wait_minutes=round(sum(case_waits) / len(case_waits), 1)
                if case_waits
                else None,
                source=source,
                source_label=SOURCE_LABELS[source],
            )
        )
    rows.sort(key=lambda row: (-row.instance_count, row.node_keys))
    handoffs = [
        MiningHandoffOut(
            from_name=pair[0],
            to_name=pair[1],
            avg_wait_minutes=round(sum(values) / len(values), 1),
            case_count=len(values),
        )
        for pair, values in handoff_bucket.items()
    ]
    handoffs.sort(key=lambda row: (-row.avg_wait_minutes, -row.case_count, row.from_name))
    return MiningOut(
        process_id=process_id,
        process_code=process.code,
        process_name=process.name,
        instance_total=total,
        unsequenced_instances=unsequenced,
        variant_count=len(rows),
        variants=rows[:limit],
        handoffs=handoffs[:5],
    )
