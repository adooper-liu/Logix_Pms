"""过程挖掘：从执行任务序列还原路径变体与耗时。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.execution import ProcessInstance
from app.models.process import ProcessArch
from app.schemas.mining import MiningOut, MiningVariantOut


def variants(db: Session, process_id: int, limit: int = 20) -> MiningOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ValueError("流程不存在")
    instances = list(
        db.scalars(
            select(ProcessInstance)
            .options(selectinload(ProcessInstance.tasks))
            .where(ProcessInstance.process_id == process_id)
            .order_by(ProcessInstance.started_at.desc())
            .limit(500)
        ).all()
    )
    grouped: Dict[tuple, List[ProcessInstance]] = defaultdict(list)
    for instance in instances:
        tasks = sorted(instance.tasks, key=lambda row: (row.created_at, row.id))
        sequence = tuple(task.node_key for task in tasks if task.status == "COMPLETED")
        if not sequence:
            continue
        grouped[sequence].append(instance)

    rows: List[MiningVariantOut] = []
    total = len(instances)
    for sequence, members in grouped.items():
        durations = [
            (item.completed_at - item.started_at).total_seconds() / 60
            for item in members
            if item.completed_at and item.started_at
        ]
        actual = [sum(task.actual_minutes or 0 for task in item.tasks) for item in members]
        rows.append(
            MiningVariantOut(
                node_keys=list(sequence),
                node_names=[
                    next(
                        (task.name for task in item.tasks if task.node_key == key),
                        key,
                    )
                    for key in sequence
                    for item in members[:1]
                ],
                instance_count=len(members),
                share_pct=round(len(members) / total * 100, 1) if total else 0.0,
                avg_cycle_minutes=round(sum(durations) / len(durations), 1) if durations else None,
                avg_actual_minutes=round(sum(actual) / len(actual), 1) if actual else None,
            )
        )
    rows.sort(key=lambda row: (-row.instance_count, row.node_keys))
    return MiningOut(
        process_id=process_id,
        process_code=process.code,
        process_name=process.name,
        instance_total=total,
        variant_count=len(rows),
        variants=rows[:limit],
    )
