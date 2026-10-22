"""流程模型版本：草稿、评审、发布、回滚与差异。

设计边界：
- `process_node/process_edge` 只保存**已发布**模型，执行引擎只读它们；
- 设计器读当前草稿（没有草稿则读已发布模型）；
- 草稿保存不碰运行表，发布时才原子替换；
- 草稿可被覆盖，旧草稿删除；已发布版本保留用于历史和回滚。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessArch, ProcessEdge, ProcessModelVersion, ProcessNode
from app.models.user import User
from app.schemas.process import ProcessModelIn
from app.services import bpmn as bpmn_service

DRAFT = "DRAFT"
IN_REVIEW = "IN_REVIEW"
PUBLISHED = "PUBLISHED"
SUPERSEDED = "SUPERSEDED"

STATUS_LABELS = {
    DRAFT: "草稿",
    IN_REVIEW: "待评审",
    PUBLISHED: "已发布",
    SUPERSEDED: "已被替代",
}

NODE_FIELDS = (
    "node_key",
    "name",
    "node_type",
    "lane",
    "owner_role",
    "duration_minutes",
    "wait_minutes",
    "cost",
    "rework_rate",
    "approval_levels",
    "is_value_added",
    "sequence_order",
    "position_x",
    "position_y",
)
EDGE_FIELDS = ("source_key", "target_key", "label", "condition", "probability")


def _node_row(node: ProcessNode) -> dict:
    return {field: getattr(node, field) for field in NODE_FIELDS}


def _edge_row(edge: ProcessEdge) -> dict:
    return {field: getattr(edge, field) for field in EDGE_FIELDS}


def snapshot_from_live(db: Session, process_id: int) -> dict:
    nodes = db.scalars(
        select(ProcessNode)
        .where(ProcessNode.process_id == process_id)
        .order_by(ProcessNode.sequence_order, ProcessNode.id)
    ).all()
    edges = db.scalars(select(ProcessEdge).where(ProcessEdge.process_id == process_id)).all()
    return {
        "nodes": [_node_row(node) for node in nodes],
        "edges": [_edge_row(edge) for edge in edges],
    }


def snapshot_from_payload(payload: ProcessModelIn) -> dict:
    nodes = []
    for index, node in enumerate(payload.nodes, start=1):
        data = node.model_dump(mode="json")
        if not data.get("sequence_order"):
            data["sequence_order"] = index
        nodes.append(data)
    return {
        "nodes": nodes,
        "edges": [edge.model_dump(mode="json") for edge in payload.edges],
    }


def latest_version(db: Session, process_id: int) -> Optional[ProcessModelVersion]:
    return db.scalar(
        select(ProcessModelVersion)
        .where(ProcessModelVersion.process_id == process_id)
        .order_by(ProcessModelVersion.version.desc())
    )


def current_snapshot(db: Session, process_id: int) -> dict:
    version = latest_version(db, process_id)
    if version is not None:
        return version.snapshot or {"nodes": [], "edges": []}
    return snapshot_from_live(db, process_id)


def rows_from_snapshot(
    process_id: int, snapshot: dict
) -> Tuple[List[ProcessNode], List[ProcessEdge]]:
    nodes: List[ProcessNode] = []
    for index, raw in enumerate(snapshot.get("nodes") or [], start=1):
        node = ProcessNode(process_id=process_id, **raw)
        node.id = index
        nodes.append(node)
    edges: List[ProcessEdge] = []
    for index, raw in enumerate(snapshot.get("edges") or [], start=1):
        edge = ProcessEdge(process_id=process_id, **raw)
        edge.id = index
        edges.append(edge)
    return nodes, edges


def render_bpmn(process: ProcessArch, snapshot: dict) -> Optional[str]:
    nodes, edges = rows_from_snapshot(process.id, snapshot)
    if not nodes:
        return None
    return bpmn_service.export_bpmn(process, nodes, edges)


def ensure_baseline(db: Session, process: ProcessArch) -> Optional[ProcessModelVersion]:
    """老数据没有版本记录时，把当前已发布模型登记为基线版本。

    这样「历史版本」从第一天起就是完整的，草稿不会看起来像凭空出现的 v1。
    """
    latest = latest_version(db, process.id)
    if latest is not None:
        return latest
    snapshot = snapshot_from_live(db, process.id)
    if not snapshot.get("nodes"):
        return None
    baseline_version = process.published_model_version or process.model_version or 1
    row = ProcessModelVersion(
        process_id=process.id,
        version=baseline_version,
        status=PUBLISHED,
        snapshot=snapshot,
        bpmn_xml=render_bpmn(process, snapshot),
        change_note="现有模型基线",
        created_by_name="系统",
        published_at=process.model_updated_at or utcnow(),
    )
    db.add(row)
    process.published_model_version = baseline_version
    db.flush()
    return row


def save_draft(
    db: Session,
    process: ProcessArch,
    payload: ProcessModelIn,
    user: User,
    note: Optional[str] = None,
    bpmn_xml: Optional[str] = None,
    keep_bpmn: bool = False,
) -> ProcessModelVersion:
    ensure_baseline(db, process)
    latest = latest_version(db, process.id)
    if latest is not None and latest.status == IN_REVIEW:
        raise HTTPException(status_code=409, detail="当前草稿正在评审，不能修改；请先驳回")

    snapshot = snapshot_from_payload(payload)
    if latest is not None and latest.status == DRAFT:
        # 草稿是可变工作副本：重复保存只更新内容，不制造一串无意义的版本号
        latest.snapshot = snapshot
        if note:
            latest.change_note = note
        if bpmn_xml is not None:
            latest.bpmn_xml = bpmn_xml
        elif not (keep_bpmn and latest.bpmn_xml):
            latest.bpmn_xml = render_bpmn(process, snapshot)
        version = latest
    else:
        # 已发布后第一次编辑：版本号从已发布版本继续；发布前只保留一个草稿
        base = max(
            process.published_model_version or 0,
            latest.version if latest is not None else 0,
        )
        if bpmn_xml is not None:
            xml = bpmn_xml
        elif keep_bpmn and latest is not None and latest.bpmn_xml:
            xml = latest.bpmn_xml
        else:
            xml = render_bpmn(process, snapshot)
        version = ProcessModelVersion(
            process_id=process.id,
            version=base + 1,
            status=DRAFT,
            snapshot=snapshot,
            bpmn_xml=xml,
            change_note=note,
            created_by_id=user.id,
            created_by_name=user.display_name,
        )
        db.add(version)
    process.model_version = (process.model_version or 0) + 1
    process.model_updated_at = utcnow()
    db.flush()
    return version


def submit_review(
    db: Session, process: ProcessArch, user: User, note: Optional[str] = None
) -> ProcessModelVersion:
    version = latest_version(db, process.id)
    if version is None:
        raise HTTPException(status_code=404, detail="还没有可提交的草稿")
    if version.status != DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿可以提交评审")
    version.status = IN_REVIEW
    if note:
        version.change_note = note
    version.reviewed_at = None
    version.reviewed_by_id = None
    version.reviewed_by_name = None
    process.model_updated_at = utcnow()
    db.flush()
    return version


def reject_review(
    db: Session, process: ProcessArch, user: User, note: Optional[str] = None
) -> ProcessModelVersion:
    version = latest_version(db, process.id)
    if version is None or version.status != IN_REVIEW:
        raise HTTPException(status_code=409, detail="当前没有待评审的草稿")
    version.status = DRAFT
    version.reviewed_by_id = user.id
    version.reviewed_by_name = user.display_name
    version.reviewed_at = utcnow()
    if note:
        version.change_note = note
    db.flush()
    return version


def _apply_snapshot(db: Session, process_id: int, snapshot: dict) -> None:
    db.execute(delete(ProcessEdge).where(ProcessEdge.process_id == process_id))
    db.execute(delete(ProcessNode).where(ProcessNode.process_id == process_id))
    db.flush()
    for index, raw in enumerate(snapshot.get("nodes") or [], start=1):
        data = dict(raw)
        data["sequence_order"] = data.get("sequence_order") or index
        db.add(ProcessNode(process_id=process_id, **data))
    for raw in snapshot.get("edges") or []:
        db.add(ProcessEdge(process_id=process_id, **dict(raw)))
    db.flush()


def publish(
    db: Session,
    process: ProcessArch,
    user: User,
    version_id: Optional[int] = None,
    note: Optional[str] = None,
) -> ProcessModelVersion:
    version = (
        db.get(ProcessModelVersion, version_id)
        if version_id is not None
        else latest_version(db, process.id)
    )
    if version is None or version.process_id != process.id:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    if version.status not in (DRAFT, IN_REVIEW):
        raise HTTPException(status_code=409, detail="只有草稿或待评审版本可以发布")

    _apply_snapshot(db, process.id, version.snapshot or {})
    db.expire(process, ["nodes", "edges"])
    for row in db.scalars(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.status == PUBLISHED,
        )
    ).all():
        row.status = SUPERSEDED
    version.status = PUBLISHED
    if note:
        version.change_note = note
    version.published_by_id = user.id
    version.published_by_name = user.display_name
    version.published_at = utcnow()
    if version.reviewed_at is None:
        version.reviewed_by_id = user.id
        version.reviewed_by_name = user.display_name
        version.reviewed_at = utcnow()
    process.published_model_version = version.version
    process.model_updated_at = utcnow()
    db.flush()
    return version


def rollback(
    db: Session,
    process: ProcessArch,
    source: ProcessModelVersion,
    user: User,
    note: Optional[str] = None,
) -> ProcessModelVersion:
    if source.process_id != process.id:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    pending = db.scalar(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.status == IN_REVIEW,
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="当前有模型正在评审，不能回滚")
    for row in db.scalars(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.status == DRAFT,
        )
    ).all():
        db.delete(row)
    db.flush()
    base = max(process.published_model_version or 0, source.version)
    row = ProcessModelVersion(
        process_id=process.id,
        version=base + 1,
        status=DRAFT,
        snapshot=source.snapshot or {},
        bpmn_xml=source.bpmn_xml or render_bpmn(process, source.snapshot or {}),
        change_note=note or f"回滚自 v{source.version}",
        created_by_id=user.id,
        created_by_name=user.display_name,
    )
    db.add(row)
    process.model_version = (process.model_version or 0) + 1
    process.model_updated_at = utcnow()
    db.flush()
    return row


def diff_snapshots(before: dict, after: dict) -> dict:
    before_nodes = {n["node_key"]: n for n in before.get("nodes") or []}
    after_nodes = {n["node_key"]: n for n in after.get("nodes") or []}
    nodes_added = [
        {"node_key": key, "name": after_nodes[key].get("name")}
        for key in sorted(after_nodes.keys() - before_nodes.keys())
    ]
    nodes_removed = [
        {"node_key": key, "name": before_nodes[key].get("name")}
        for key in sorted(before_nodes.keys() - after_nodes.keys())
    ]
    nodes_changed = []
    for key in sorted(before_nodes.keys() & after_nodes.keys()):
        fields = [
            field
            for field in NODE_FIELDS
            if before_nodes[key].get(field) != after_nodes[key].get(field)
        ]
        if fields:
            nodes_changed.append(
                {
                    "node_key": key,
                    "name": after_nodes[key].get("name"),
                    "fields": fields,
                }
            )

    def edge_key(edge: dict) -> Tuple[str, str]:
        return edge.get("source_key"), edge.get("target_key")

    before_edges = {edge_key(e): e for e in before.get("edges") or []}
    after_edges = {edge_key(e): e for e in after.get("edges") or []}
    edges_added = [
        {"source_key": key[0], "target_key": key[1]}
        for key in sorted(after_edges.keys() - before_edges.keys())
    ]
    edges_removed = [
        {"source_key": key[0], "target_key": key[1]}
        for key in sorted(before_edges.keys() - after_edges.keys())
    ]
    edges_changed = []
    for key in sorted(before_edges.keys() & after_edges.keys()):
        fields = [
            field
            for field in EDGE_FIELDS
            if field not in ("source_key", "target_key")
            and before_edges[key].get(field) != after_edges[key].get(field)
        ]
        if fields:
            edges_changed.append(
                {
                    "source_key": key[0],
                    "target_key": key[1],
                    "fields": fields,
                }
            )
    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": nodes_changed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "edges_changed": edges_changed,
    }
