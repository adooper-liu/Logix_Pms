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
from sqlalchemy import delete, func, select, update
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

PUBLISH_DIRECT = "direct"
PUBLISH_REVIEW_REQUIRED = "review_required"
PUBLISH_POLICY_LABELS = {
    PUBLISH_DIRECT: "直接发布（草稿可发）",
    PUBLISH_REVIEW_REQUIRED: "须先评审",
}
SELF_PUBLISH_REASON_MIN = 8
CHANGE_NOTE_MIN = 4

NODE_FIELDS = (
    "node_key",
    "name",
    "node_type",
    "lane",
    "owner_role",
    "description",
    "process_arch_id",
    "owner_position_id",
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
EDGE_FIELDS = (
    "source_key",
    "target_key",
    "label",
    "condition",
    "match_conditions",
    "probability",
    "description",
    "is_default",
)


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
    from app.services import forms as forms_service

    nodes = []
    for index, node in enumerate(payload.nodes, start=1):
        data = node.model_dump(mode="json")
        if not data.get("sequence_order"):
            data["sequence_order"] = index
        nodes.append(data)
    edges = []
    for edge in payload.edges:
        data = edge.model_dump(mode="json")
        raw_match = data.get("match_conditions")
        if raw_match:
            data["match_conditions"] = forms_service.normalize_conditions(list(raw_match))
        elif raw_match is not None:
            data["match_conditions"] = []
        edges.append(data)
    return {
        "nodes": nodes,
        "edges": edges,
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
        data = dict(raw)
        data.setdefault("is_default", False)
        edge = ProcessEdge(process_id=process_id, **data)
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


def lock_process(db, process):
    # 同一流程的冻结/原写入口使用同一行锁，SQLite亦通过UPDATE串行化。
    db.execute(
        update(ProcessArch)
        .where(ProcessArch.id == process.id)
        .values(model_version=ProcessArch.model_version),
        execution_options={"synchronize_session": False},
    )
    db.refresh(process)


PROVIDER_LABELS = {"LEGACY": "原轻量执行", "FLOWABLE": "Flowable沙箱"}


def validate_payload(payload, xml=None):
    from app.services import designer

    if payload.execution_provider == "FLOWABLE":
        from app.services.engine_bpmn import inspect_xml

        if not xml:
            raise HTTPException(400, "Flowable沙箱模型必须保存完整XML")
        checked = inspect_xml(xml)
        if {n.node_key: n.node_type.value for n in payload.nodes} != {
            n["node_key"]: n["node_type"] for n in checked["nodes"]
        } or {(e.source_key, e.target_key) for e in payload.edges} != {
            (e["source_key"], e["target_key"]) for e in checked["edges"]
        }:
            raise HTTPException(400, "治理投影与执行XML不一致")
    else:
        if any(n.node_type.value == "PARALLEL" for n in payload.nodes):
            raise HTTPException(400, "原轻量执行不支持并行网关")
        checked = designer.validate_model(payload.nodes, payload.edges)
        if checked["errors"]:
            raise HTTPException(400, "；".join(checked["errors"]))


def save_draft(
    db: Session,
    process: ProcessArch,
    payload: ProcessModelIn,
    user: User,
    note: Optional[str] = None,
    bpmn_xml: Optional[str] = None,
    keep_bpmn: bool = False,
) -> ProcessModelVersion:
    lock_process(db, process)
    ensure_baseline(db, process)
    latest = latest_version(db, process.id)
    bpmn_xml = bpmn_xml or payload.bpmn_xml
    if keep_bpmn and latest and latest.execution_provider == "FLOWABLE":
        payload.execution_provider = "FLOWABLE"
        bpmn_xml = bpmn_xml or latest.bpmn_xml
    validate_payload(payload, bpmn_xml)
    if latest is not None and latest.status == IN_REVIEW:
        raise HTTPException(status_code=409, detail="当前草稿正在评审，不能修改；请先驳回")

    snapshot = snapshot_from_payload(payload)
    if latest is not None and latest.status == DRAFT and latest.frozen_at is None:
        # 与freeze竞争时由数据库条件裁决，旧ORM缓存不能覆盖已固定正文/XML。
        values = {"snapshot": snapshot, "execution_provider": payload.execution_provider}
        if note:
            values["change_note"] = note
        if bpmn_xml is not None:
            values["bpmn_xml"] = bpmn_xml
        elif not (keep_bpmn and latest.bpmn_xml):
            values["bpmn_xml"] = render_bpmn(process, snapshot)
        result = db.execute(
            update(ProcessModelVersion)
            .where(
                ProcessModelVersion.id == latest.id,
                ProcessModelVersion.frozen_at.is_(None),
                ProcessModelVersion.status == DRAFT,
            )
            .values(**values),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount != 1:
            raise HTTPException(409, "原模型已固定或改变，请刷新后保存新工作版")
        db.expire(latest)
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
            execution_provider=payload.execution_provider,
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


def resolve_publish_policy(process: ProcessArch) -> str:
    policy = (process.publish_policy or PUBLISH_REVIEW_REQUIRED).strip()
    if policy not in PUBLISH_POLICY_LABELS:
        return PUBLISH_REVIEW_REQUIRED
    return policy


def _published_version_row(db: Session, process_id: int) -> Optional[ProcessModelVersion]:
    return db.scalar(
        select(ProcessModelVersion)
        .where(
            ProcessModelVersion.process_id == process_id,
            ProcessModelVersion.status == PUBLISHED,
        )
        .order_by(ProcessModelVersion.version.desc())
    )


def count_active_instances(db: Session, process_id: int) -> int:
    from app.models.enums import InstanceStatus
    from app.models.execution import ProcessInstance

    return (
        db.scalar(
            select(func.count())
            .select_from(ProcessInstance)
            .where(
                ProcessInstance.process_id == process_id,
                ProcessInstance.status.in_(
                    (
                        InstanceStatus.RUNNING.value,
                        InstanceStatus.SUSPENDED.value,
                    )
                ),
            )
        )
        or 0
    )


def build_publish_preview(db: Session, process: ProcessArch, user: User) -> dict:
    """Publish confirmation payload: policy, blockers, diff, active instances."""
    version = latest_version(db, process.id)
    policy = resolve_publish_policy(process)
    blockers: List[str] = []
    warnings: List[str] = []
    if version is None:
        blockers.append("还没有可发布的模型版本")
    else:
        if version.status not in (DRAFT, IN_REVIEW):
            blockers.append("当前版本不是草稿或待评审，无法发布")
        if policy == PUBLISH_REVIEW_REQUIRED and version.status == DRAFT:
            blockers.append("当前发布策略要求先「提交评审」，待评审后再发布")
        same_author = version.created_by_id is not None and version.created_by_id == user.id
        if same_author:
            warnings.append(
                "你是本草稿创建人：禁止自评自发，请换人发布，"
                "或填写豁免原因（不少于 " + str(SELF_PUBLISH_REASON_MIN) + " 字）"
            )
    active = count_active_instances(db, process.id)
    if active:
        warnings.append(
            f"当前有 {active} 个在途实例（运行中/已挂起）；发布只影响新实例，在途仍钉旧版快照"
        )
    published = _published_version_row(db, process.id)
    diff = {
        "nodes_added": [],
        "nodes_removed": [],
        "nodes_changed": [],
        "edges_added": [],
        "edges_removed": [],
        "edges_changed": [],
    }
    from_version = 0
    to_version = version.version if version else 0
    if version is not None and published is not None:
        from_version = published.version
        diff = diff_snapshots(published.snapshot or {}, version.snapshot or {})
    elif version is not None:
        diff = diff_snapshots({}, version.snapshot or {})

    return {
        "process_id": process.id,
        "process_code": process.code,
        "process_name": process.name,
        "publish_policy": policy,
        "publish_policy_label": PUBLISH_POLICY_LABELS[policy],
        "requires_change_request": bool(process.requires_change_request),
        "status": version.status if version else None,
        "status_label": (STATUS_LABELS.get(version.status, version.status) if version else None),
        "draft_version": version.version if version else 0,
        "version_id": version.id if version else None,
        "published_version": process.published_model_version or 0,
        "created_by_name": version.created_by_name if version else None,
        "same_author": bool(
            version and version.created_by_id is not None and version.created_by_id == user.id
        ),
        "active_instance_count": active,
        "change_note_required": True,
        "self_publish_reason_required": bool(
            version and version.created_by_id is not None and version.created_by_id == user.id
        ),
        "blockers": blockers,
        "warnings": warnings,
        "can_publish": not blockers,
        "diff": {
            "from_version": from_version,
            "to_version": to_version,
            **diff,
        },
    }


def publish(
    db: Session,
    process: ProcessArch,
    user: User,
    version_id: Optional[int] = None,
    note: Optional[str] = None,
    self_publish_reason: Optional[str] = None,
    *,
    bypass_policy: bool = False,
    bypass_author_check: bool = False,
) -> ProcessModelVersion:
    from app.services import binding_snapshot

    lock_process(db, process)
    version = (
        db.get(ProcessModelVersion, version_id)
        if version_id is not None
        else latest_version(db, process.id)
    )
    if version is None or version.process_id != process.id:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    if version.status not in (DRAFT, IN_REVIEW):
        raise HTTPException(
            status_code=409,
            detail="只有草稿或待评审版本可以发布",
        )

    policy = resolve_publish_policy(process)
    if not bypass_policy and policy == PUBLISH_REVIEW_REQUIRED and version.status != IN_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=("当前发布策略要求先提交评审；待评审后再由他人发布"),
        )

    note_text = (note or "").strip()
    if len(note_text) < CHANGE_NOTE_MIN:
        raise HTTPException(
            status_code=422,
            detail=(f"发布说明至少 {CHANGE_NOTE_MIN} 个字，便于审计追溯"),
        )

    same_author = version.created_by_id is not None and version.created_by_id == user.id
    if same_author and not bypass_author_check:
        reason = (self_publish_reason or "").strip()
        if len(reason) < SELF_PUBLISH_REASON_MIN:
            raise HTTPException(
                status_code=409,
                detail=(
                    "禁止同一人既创建草稿又发布。"
                    "请换评审人发布，"
                    f"或填写不少于 {SELF_PUBLISH_REASON_MIN} "
                    "字的豁免原因"
                ),
            )
        note_text = f"{note_text}｜自评自发豁免：{reason}"

    captured_bindings = binding_snapshot.capture(db, process, version)
    if version.binding_snapshot is not None:
        if captured_bindings["activities"] != version.binding_snapshot.get("activities", {}):
            raise HTTPException(409, "冻结绑定依据已变化，请创建新工作版后重新固定/发布")
    else:
        version.binding_snapshot = captured_bindings
    _apply_snapshot(db, process.id, version.snapshot or {})
    db.expire(process, ["nodes", "edges"])
    for row in db.scalars(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.status == PUBLISHED,
        )
    ).all():
        row.status = SUPERSEDED
    had_review = version.reviewed_at is not None
    version.status = PUBLISHED
    version.change_note = note_text
    version.published_by_id = user.id
    version.published_by_name = user.display_name
    version.published_at = utcnow()
    if not had_review and not same_author:
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
    lock_process(db, process)
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
            ProcessModelVersion.frozen_at.is_(None),
        )
    ).all():
        db.delete(row)
    db.flush()
    latest = latest_version(db, process.id)
    base = max(
        process.published_model_version or 0, source.version, latest.version if latest else 0
    )
    row = ProcessModelVersion(
        process_id=process.id,
        version=base + 1,
        status=DRAFT,
        execution_provider=source.execution_provider,
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
