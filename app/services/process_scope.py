"""流程层级范围判断：标准文件挂在 L1–L4 节点上，项目挂在具体节点上。

规则：项目可以使用「自己所在节点 + 所有祖先节点」的标准文件；
项目未关联流程时不做范围限制（由使用者显式选择，但晋升必须先关联流程）。
"""

from __future__ import annotations

from typing import Optional, Set

from sqlalchemy.orm import Session

from app.models.process import ProcessArch


def ancestor_ids(db: Session, process_id: Optional[int]) -> Set[int]:
    ids: Set[int] = set()
    current_id = process_id
    guard = 0
    while current_id and guard < 16:
        node = db.get(ProcessArch, current_id)
        if node is None:
            break
        ids.add(node.id)
        current_id = node.parent_id
        guard += 1
    return ids


def is_document_applicable(
    db: Session, document_process_id: int, project_process_id: Optional[int]
) -> bool:
    if project_process_id is None:
        return True
    return document_process_id in ancestor_ids(db, project_process_id)
