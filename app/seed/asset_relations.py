"""把历史 `process_node.process_arch_id` 回填为 REALIZES 关系。

只用于演示/测试种子；生产历史数据由 Alembic 迁移回填。幂等，可重复执行。
"""

from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.asset_graph import NodeActivityLink
from app.models.process import ProcessModelVersion, ProcessNode


def backfill_node_activity_links(db: Session) -> int:
    existing = {
        (row.process_id, row.node_key, row.activity_id)
        for row in db.scalars(
            select(NodeActivityLink).where(NodeActivityLink.relation == "REALIZES")
        ).all()
    }
    version_cache: Dict[int, Optional[int]] = {}
    created = 0
    for node in db.scalars(
        select(ProcessNode).where(ProcessNode.process_arch_id.is_not(None))
    ).all():
        key = (node.process_id, node.node_key, node.process_arch_id)
        if key in existing:
            continue
        if node.process_id not in version_cache:
            version_cache[node.process_id] = db.scalar(
                select(ProcessModelVersion.id)
                .where(
                    ProcessModelVersion.process_id == node.process_id,
                    ProcessModelVersion.status == "PUBLISHED",
                )
                .order_by(ProcessModelVersion.version.desc())
            )
        db.add(
            NodeActivityLink(
                model_version_id=version_cache[node.process_id],
                process_id=node.process_id,
                node_key=node.node_key,
                activity_id=node.process_arch_id,
                relation="REALIZES",
                path_condition="ALL",
                coverage=1.0,
                confirmed_by_name="系统回填",
                confirmed_at=utcnow(),
            )
        )
        existing.add(key)
        created += 1
    db.flush()
    return created
