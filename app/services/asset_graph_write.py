"""架构关系与证据主张的受控写入。

读写分离：`asset_graph.py` 只做查询/就绪度，本模块负责写入与校验。
写入前置条件统一为「已有已发布模型版本」，避免把关系挂在可变草稿上。
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional, Set, Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.asset_graph import (
    ActivityRelation,
    EdgeHandoffLink,
    EvidenceAdjudication,
    EvidenceClaim,
    EvidenceClaimTarget,
    NodeActivityLink,
    UnmodeledActivity,
)
from app.models.execution import ProcessRule
from app.models.monitor import KpiDefinition
from app.models.process import ProcessArch, ProcessEdge, ProcessModelVersion, ProcessNode
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.tool_sheet import ToolSheet
from app.models.user import User
from app.schemas.asset_graph import (
    ActivityRelationIn,
    ActivityRelationOut,
    EdgeHandoffIn,
    EdgeHandoffOut,
    EvidenceAdjudicationIn,
    EvidenceAdjudicationOut,
    EvidenceClaimIn,
    EvidenceClaimOut,
    EvidenceClaimTargetIn,
    NodeActivityLinkIn,
    NodeActivityLinkOut,
    UnmodeledActivityIn,
    UnmodeledActivityOut,
)
from app.services import audit, process_scope
from app.services.asset_graph import evidence_claims, published_model


def _require_versioned_model(db: Session, process: ProcessArch) -> ProcessModelVersion:
    version = published_model(db, process)
    if version is None:
        raise HTTPException(409, "请先在设计器发布 To-Be 模型版本，再登记关系或证据。")
    return version


def _require_activity(db: Session, process: ProcessArch, activity_id: int) -> ProcessArch:
    activity = db.get(ProcessArch, activity_id)
    if activity is None or activity.level != 4 or activity.parent_id != process.id:
        raise HTTPException(400, "活动必须是该流程下的 L4 活动。")
    return activity


def _require_node(db: Session, process: ProcessArch, node_key: str) -> ProcessNode:
    node = db.scalar(
        select(ProcessNode).where(
            ProcessNode.process_id == process.id,
            ProcessNode.node_key == node_key,
        )
    )
    if node is None:
        raise HTTPException(404, f"节点 {node_key} 不存在。")
    return node


def _normalize_edge_key(edge_key: str) -> str:
    return edge_key.replace("→", "->").replace(" ", "")


def _require_edge(db: Session, process: ProcessArch, edge_key: str) -> ProcessEdge:
    normalized = _normalize_edge_key(edge_key)
    if "->" not in normalized:
        raise HTTPException(400, "连线键必须是「源节点->目标节点」。")
    source_key, target_key = normalized.split("->", 1)
    edge = db.scalar(
        select(ProcessEdge).where(
            ProcessEdge.process_id == process.id,
            ProcessEdge.source_key == source_key,
            ProcessEdge.target_key == target_key,
        )
    )
    if edge is None:
        raise HTTPException(404, f"连线 {normalized} 不存在。")
    return edge


def _hash_json(value) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_source(
    db: Session, process: ProcessArch, payload: EvidenceClaimIn
) -> Tuple[str, str, str]:
    """返回 (source_version, source_hash, source_label)。"""
    if payload.source_type == "TOOL_SHEET":
        sheet = db.get(ToolSheet, payload.source_id)
        if sheet is None or sheet.process_id != process.id:
            raise HTTPException(400, "工具表来源不属于该流程。")
        source_version = payload.source_version or f"revision:{sheet.revision}"
        source_hash = payload.source_hash or _hash_json(
            {
                "type": "TOOL_SHEET",
                "id": sheet.id,
                "revision": sheet.revision,
                "tool_code": sheet.tool_code,
                "template_version_id": sheet.template_version_id,
                "fields": sheet.fields,
            }
        )
        return source_version, source_hash, f"工具表 #{sheet.id}"

    version = db.get(ProcessDocumentVersion, payload.source_id)
    if version is None:
        raise HTTPException(404, "制度版本不存在。")
    document = db.get(ProcessDocument, version.document_id)
    if document is None or not process_scope.is_document_applicable(
        db, document.process_id, process.id
    ):
        raise HTTPException(400, "制度版本不属于该流程的适用范围。")
    if version.status != "EFFECTIVE":
        raise HTTPException(400, "只能引用已生效的制度版本作为证据。")
    source_version = payload.source_version or version.version_label
    source_hash = payload.source_hash or _hash_json(
        {
            "type": "DOCUMENT_VERSION",
            "id": version.id,
            "document_id": version.document_id,
            "version_label": version.version_label,
            "status": version.status,
            "checksum": version.checksum,
        }
    )
    return source_version, source_hash, f"制度 {document.code} {version.version_label}"


def _validate_target(
    db: Session, process: ProcessArch, target: EvidenceClaimTargetIn, model_version_id: int
) -> Optional[int]:
    """校验目标归属；返回最终 model_version_id（节点/边强制绑定当前版本）。"""
    if target.model_version_id is not None and target.model_version_id != model_version_id:
        raise HTTPException(400, "证据目标绑定的模型版本与当前已发布版本不一致。")

    if target.target_type == "PROCESS":
        if target.target_id != process.id:
            raise HTTPException(400, "流程级目标必须指向当前流程。")
        return model_version_id

    if target.target_type == "ACTIVITY":
        if target.field:
            raise HTTPException(400, "活动级目标不应指定 field；时间字段请用 TIME_FIELD。")
        _require_activity(db, process, target.target_id)
        return model_version_id

    if target.target_type == "TIME_FIELD":
        if not target.field:
            raise HTTPException(400, "TIME_FIELD 必须指定 field，例如 wait 或 duration。")
        _require_activity(db, process, target.target_id)
        return model_version_id

    if target.target_type == "NODE":
        node = db.get(ProcessNode, target.target_id)
        if node is None or node.process_id != process.id:
            raise HTTPException(400, "节点目标不属于该流程。")
        return model_version_id

    if target.target_type == "EDGE":
        edge = db.get(ProcessEdge, target.target_id)
        if edge is None or edge.process_id != process.id:
            raise HTTPException(400, "连线目标不属于该流程。")
        return model_version_id

    if target.target_type == "KPI":
        kpi = db.get(KpiDefinition, target.target_id)
        if kpi is None or (kpi.process_id is not None and kpi.process_id != process.id):
            raise HTTPException(400, "KPI 目标不属于该流程。")
        return None

    if target.target_type == "RULE":
        rule = db.get(ProcessRule, target.target_id)
        if rule is None or rule.process_id != process.id:
            raise HTTPException(400, "规则目标不属于该流程。")
        return None

    raise HTTPException(400, "不支持的目标类型。")


def _link_out(row: NodeActivityLink, activity: ProcessArch) -> NodeActivityLinkOut:
    return NodeActivityLinkOut(
        id=row.id,
        node_key=row.node_key,
        activity_id=row.activity_id,
        activity_code=activity.code,
        activity_name=activity.name,
        relation=row.relation,
        path_condition=row.path_condition,
        coverage=row.coverage,
        confirmed_by_name=row.confirmed_by_name,
        confirmed_at=row.confirmed_at,
        note=row.note,
    )


def upsert_node_activity_link(
    db: Session, process: ProcessArch, payload: NodeActivityLinkIn, user: User
) -> NodeActivityLinkOut:
    version = _require_versioned_model(db, process)
    node = _require_node(db, process, payload.node_key)
    activity = _require_activity(db, process, payload.activity_id)
    if payload.relation in {"REALIZES", "PART_OF"} and node.node_type in {"START", "END"}:
        raise HTTPException(400, "开始/结束节点不能登记实现或组成关系；如需控制点请用 CONTROLS。")
    row = db.scalar(
        select(NodeActivityLink)
        .where(
            or_(
                NodeActivityLink.model_version_id == version.id,
                NodeActivityLink.model_version_id.is_(None),
            ),
            NodeActivityLink.node_key == payload.node_key,
            NodeActivityLink.activity_id == payload.activity_id,
            NodeActivityLink.relation == payload.relation,
            NodeActivityLink.path_condition == payload.path_condition,
        )
        .order_by(NodeActivityLink.id)
    )
    action = "UPDATE"
    if row is None:
        row = NodeActivityLink(
            model_version_id=version.id,
            process_id=process.id,
            node_key=payload.node_key,
            activity_id=payload.activity_id,
            relation=payload.relation,
            path_condition=payload.path_condition,
            coverage=payload.coverage,
            note=payload.note,
            confirmed_by_id=user.id,
            confirmed_by_name=user.display_name,
            confirmed_at=utcnow(),
        )
        db.add(row)
        action = "CREATE"
    else:
        if row.model_version_id is None:
            row.model_version_id = version.id
        row.coverage = payload.coverage
        row.note = payload.note
        row.confirmed_by_id = user.id
        row.confirmed_by_name = user.display_name
        row.confirmed_at = utcnow()
    db.flush()

    # 兼容既有设计器/执行读取的主活动指针；权威关系仍是本表。
    if (
        payload.relation == "REALIZES"
        and payload.path_condition in {"STANDARD", "ALL"}
        and node.process_arch_id is None
    ):
        node.process_arch_id = activity.id

    audit.record(
        db,
        user,
        action,
        "node_activity_link",
        row.id,
        f"{payload.node_key} {payload.relation} {activity.code}",
    )
    db.commit()
    db.refresh(row)
    return _link_out(row, activity)


def upsert_activity_relation(
    db: Session, process: ProcessArch, payload: ActivityRelationIn, user: User
) -> ActivityRelationOut:
    version = _require_versioned_model(db, process)
    source = _require_activity(db, process, payload.source_activity_id)
    target = _require_activity(db, process, payload.target_activity_id)
    if source.id == target.id:
        raise HTTPException(400, "活动关系的源和目标不能相同。")
    row = db.scalar(
        select(ActivityRelation).where(
            ActivityRelation.model_version_id == version.id,
            ActivityRelation.source_activity_id == source.id,
            ActivityRelation.target_activity_id == target.id,
            ActivityRelation.relation == payload.relation,
        )
    )
    action = "UPDATE"
    if row is None:
        row = ActivityRelation(
            model_version_id=version.id,
            process_id=process.id,
            source_activity_id=source.id,
            target_activity_id=target.id,
            relation=payload.relation,
            note=payload.note,
            confirmed_by_id=user.id,
            confirmed_by_name=user.display_name,
            confirmed_at=utcnow(),
        )
        db.add(row)
        action = "CREATE"
    else:
        row.note = payload.note
        row.confirmed_by_id = user.id
        row.confirmed_by_name = user.display_name
        row.confirmed_at = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        action,
        "activity_relation",
        row.id,
        f"{source.code} {payload.relation} {target.code}",
    )
    db.commit()
    db.refresh(row)
    return ActivityRelationOut(
        id=row.id,
        source_activity_id=source.id,
        source_code=source.code,
        source_name=source.name,
        target_activity_id=target.id,
        target_code=target.code,
        target_name=target.name,
        relation=row.relation,
        confirmed_by_name=row.confirmed_by_name,
        confirmed_at=row.confirmed_at,
    )


def upsert_edge_handoff(
    db: Session, process: ProcessArch, payload: EdgeHandoffIn, user: User
) -> EdgeHandoffOut:
    version = _require_versioned_model(db, process)
    edge_key = _normalize_edge_key(payload.edge_key)
    _require_edge(db, process, edge_key)
    if payload.from_activity_id is not None:
        _require_activity(db, process, payload.from_activity_id)
    if payload.to_activity_id is not None:
        _require_activity(db, process, payload.to_activity_id)
    row = db.scalar(
        select(EdgeHandoffLink).where(
            EdgeHandoffLink.model_version_id == version.id,
            EdgeHandoffLink.edge_key == edge_key,
        )
    )
    action = "UPDATE"
    if row is None:
        row = EdgeHandoffLink(
            model_version_id=version.id,
            process_id=process.id,
            edge_key=edge_key,
            from_activity_id=payload.from_activity_id,
            to_activity_id=payload.to_activity_id,
            handoff_type=payload.handoff_type,
            note=payload.note,
            confirmed_by_id=user.id,
            confirmed_by_name=user.display_name,
            confirmed_at=utcnow(),
        )
        db.add(row)
        action = "CREATE"
    else:
        row.from_activity_id = payload.from_activity_id
        row.to_activity_id = payload.to_activity_id
        row.handoff_type = payload.handoff_type
        row.note = payload.note
        row.confirmed_by_id = user.id
        row.confirmed_by_name = user.display_name
        row.confirmed_at = utcnow()
    db.flush()
    audit.record(db, user, action, "edge_handoff_link", row.id, f"{edge_key} {row.handoff_type}")
    db.commit()
    db.refresh(row)
    return EdgeHandoffOut(
        id=row.id,
        edge_key=row.edge_key,
        from_activity_id=row.from_activity_id,
        to_activity_id=row.to_activity_id,
        handoff_type=row.handoff_type,
        confirmed_by_name=row.confirmed_by_name,
        confirmed_at=row.confirmed_at,
    )


def upsert_unmodeled_activity(
    db: Session, process: ProcessArch, payload: UnmodeledActivityIn, user: User
) -> UnmodeledActivityOut:
    version = _require_versioned_model(db, process)
    activity = _require_activity(db, process, payload.activity_id)
    row = db.scalar(
        select(UnmodeledActivity).where(
            UnmodeledActivity.model_version_id == version.id,
            UnmodeledActivity.activity_id == activity.id,
        )
    )
    action = "UPDATE"
    if row is None:
        row = UnmodeledActivity(
            model_version_id=version.id,
            process_id=process.id,
            activity_id=activity.id,
            reason=payload.reason,
            source_ref=payload.source_ref,
            confirmed_by_id=user.id,
            confirmed_by_name=user.display_name,
            confirmed_at=utcnow(),
        )
        db.add(row)
        action = "CREATE"
    else:
        row.reason = payload.reason
        row.source_ref = payload.source_ref
        row.confirmed_by_id = user.id
        row.confirmed_by_name = user.display_name
        row.confirmed_at = utcnow()
    db.flush()
    audit.record(db, user, action, "unmodeled_activity", row.id, activity.code)
    db.commit()
    db.refresh(row)
    return UnmodeledActivityOut(
        id=row.id,
        activity_id=activity.id,
        activity_code=activity.code,
        activity_name=activity.name,
        reason=row.reason,
        source_ref=row.source_ref,
        confirmed_by_name=row.confirmed_by_name,
    )


def create_evidence_claim(
    db: Session, process: ProcessArch, payload: EvidenceClaimIn, user: User
) -> EvidenceClaimOut:
    version = _require_versioned_model(db, process)
    if payload.window_start and payload.window_end and payload.window_end < payload.window_start:
        raise HTTPException(400, "证据窗口结束时间不能早于开始时间。")
    if payload.valid_from and payload.valid_to and payload.valid_to < payload.valid_from:
        raise HTTPException(400, "证据有效期结束不能早于开始。")
    if payload.status == "CONFLICTED" and not payload.conflict_group:
        raise HTTPException(400, "冲突主张必须给出 conflict_group，才能被裁决。")

    source_version, source_hash, _label = _require_source(db, process, payload)
    seen: Set[Tuple[str, int, str, str]] = set()
    targets: list[tuple[EvidenceClaimTargetIn, Optional[int]]] = []
    for target in payload.targets:
        key = (target.target_type, target.target_id, target.field or "", target.condition)
        if key in seen:
            raise HTTPException(400, "同一主张里存在重复目标。")
        seen.add(key)
        targets.append((target, _validate_target(db, process, target, version.id)))

    claim = EvidenceClaim(
        process_id=process.id,
        claim=payload.claim.strip(),
        claim_type=payload.claim_type,
        source_type=payload.source_type,
        source_id=payload.source_id,
        source_version=source_version,
        source_hash=source_hash,
        method=payload.method,
        samples=payload.samples,
        window_start=payload.window_start,
        window_end=payload.window_end,
        coverage=payload.coverage,
        quality=payload.quality,
        conflict_group=payload.conflict_group,
        status=payload.status,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        query_ref=payload.query_ref,
        result_hash=payload.result_hash,
        created_by_id=user.id,
        created_by_name=user.display_name,
    )
    db.add(claim)
    db.flush()
    for target, model_version_id in targets:
        db.add(
            EvidenceClaimTarget(
                claim_id=claim.id,
                target_type=target.target_type,
                target_id=target.target_id,
                model_version_id=model_version_id,
                field=target.field,
                condition=target.condition,
            )
        )
    db.flush()
    audit.record(db, user, "CREATE", "evidence_claim", claim.id, claim.claim[:160])
    db.commit()
    db.refresh(claim)
    result = evidence_claims(db, process)
    for item in result.claims:
        if item.id == claim.id:
            return item
    raise HTTPException(500, "证据主张已写入，但读取失败；请刷新后重试。")


def adjudicate_claim(
    db: Session,
    process: ProcessArch,
    claim_id: int,
    payload: EvidenceAdjudicationIn,
    user: User,
) -> EvidenceAdjudicationOut:
    claim = db.get(EvidenceClaim, claim_id)
    if claim is None or claim.process_id != process.id:
        raise HTTPException(404, "证据主张不存在。")
    if not claim.conflict_group:
        raise HTTPException(400, "该主张没有冲突组，不需要裁决。")
    row = EvidenceAdjudication(
        conflict_group=claim.conflict_group,
        decision=payload.decision,
        rationale=payload.rationale.strip(),
        decided_by_id=user.id,
        decided_by_name=user.display_name,
        decided_at=utcnow(),
        authority_ref=payload.authority_ref,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        user,
        "CREATE",
        "evidence_adjudication",
        row.id,
        f"{claim.conflict_group} {payload.decision}",
    )
    db.commit()
    db.refresh(row)
    return EvidenceAdjudicationOut(
        id=row.id,
        conflict_group=row.conflict_group,
        decision=row.decision,
        rationale=row.rationale,
        decided_by_name=row.decided_by_name,
        decided_at=row.decided_at,
        authority_ref=row.authority_ref,
    )


# ------------------------------------------------------------------ 撤销


def _not_found(label: str) -> HTTPException:
    return HTTPException(404, f"{label}不存在或不属于该流程。")


def delete_node_activity_link(db: Session, process: ProcessArch, link_id: int, user: User) -> int:
    row = db.get(NodeActivityLink, link_id)
    if row is None or row.process_id != process.id:
        raise _not_found("节点↔活动关系")
    node = db.scalar(
        select(ProcessNode).where(
            ProcessNode.process_id == process.id,
            ProcessNode.node_key == row.node_key,
        )
    )
    activity = db.get(ProcessArch, row.activity_id)
    if node is not None and row.relation == "REALIZES" and node.process_arch_id == row.activity_id:
        # 关系表是权威来源；撤销实现关系时同步清掉兼容指针，避免“删了还显示已映射”。
        node.process_arch_id = None
    summary = f"{row.node_key} {row.relation} {activity.code if activity else row.activity_id}"
    db.delete(row)
    audit.record(db, user, "DELETE", "node_activity_link", link_id, summary)
    db.commit()
    return link_id


def delete_activity_relation(
    db: Session, process: ProcessArch, relation_id: int, user: User
) -> int:
    row = db.get(ActivityRelation, relation_id)
    if row is None or row.process_id != process.id:
        raise _not_found("活动关系")
    source = db.get(ProcessArch, row.source_activity_id)
    target = db.get(ProcessArch, row.target_activity_id)
    summary = (
        f"{source.code if source else row.source_activity_id} {row.relation} "
        f"{target.code if target else row.target_activity_id}"
    )
    db.delete(row)
    audit.record(db, user, "DELETE", "activity_relation", relation_id, summary)
    db.commit()
    return relation_id


def delete_edge_handoff(db: Session, process: ProcessArch, handoff_id: int, user: User) -> int:
    row = db.get(EdgeHandoffLink, handoff_id)
    if row is None or row.process_id != process.id:
        raise _not_found("连线交接")
    db.delete(row)
    audit.record(db, user, "DELETE", "edge_handoff_link", handoff_id, row.edge_key)
    db.commit()
    return handoff_id


def delete_unmodeled_activity(
    db: Session, process: ProcessArch, unmodeled_id: int, user: User
) -> int:
    row = db.get(UnmodeledActivity, unmodeled_id)
    if row is None or row.process_id != process.id:
        raise _not_found("未建模活动")
    activity = db.get(ProcessArch, row.activity_id)
    db.delete(row)
    audit.record(
        db,
        user,
        "DELETE",
        "unmodeled_activity",
        unmodeled_id,
        activity.code if activity else row.activity_id,
    )
    db.commit()
    return unmodeled_id
