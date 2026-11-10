"""流程资产生产关系：查询、写入、就绪度计算、证据覆盖。

本服务不生成资产。它回答三个问题：这条流程现在能产出什么、还缺什么、下一步做什么，
并提供关系与证据的受控写入。生成器不在这里。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

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
from app.models.user import User
from app.schemas.asset_graph import (
    ActivityRelationOut,
    ArchitectureMapOut,
    ArchitectureNodeOut,
    AssetReadinessOut,
    EdgeHandoffOut,
    EvidenceAdjudicationOut,
    EvidenceClaimListOut,
    EvidenceClaimOut,
    EvidenceClaimTargetOut,
    NodeActivityLinkOut,
    ReadinessBlockerOut,
    UnmodeledActivityOut,
)
from app.services import org_access

NODE_RELATIONS = {"REALIZES", "PART_OF", "CONTROLS"}
ACTIVITY_RELATIONS = {"PART_OF", "DECOMPOSES", "TRIGGERS", "SERVES"}
HANDOFF_TYPES = {"HANDOFF", "NO_HANDOFF"}
CLAIM_TYPES = {"EXISTENCE", "SEQUENCE", "TIME", "CONTROL", "ROLE", "RULE", "OUTCOME"}
METHODS = {"OBSERVED", "DOCUMENTED", "STATED", "ESTIMATED", "LOGGED", "UNKNOWN"}
CLAIM_STATUSES = {"OPEN", "SUPPORTED", "CONFLICTED", "ADJUDICATED", "EXPIRED"}
ACTIVITY_NODE_TYPES = {"TASK", "APPROVAL"}
NON_ACTIVITY_NODES = {"START", "END", "WAIT", "DECISION", "PARALLEL", "HANDOFF"}

LABELS = {
    "claim_type": {
        "EXISTENCE": "是否存在",
        "SEQUENCE": "顺序",
        "TIME": "时间",
        "CONTROL": "控制",
        "ROLE": "责任",
        "RULE": "规则",
        "OUTCOME": "结果",
    },
    "method": {
        "OBSERVED": "现场观测",
        "DOCUMENTED": "制度文本",
        "STATED": "访谈陈述",
        "ESTIMATED": "估算",
        "LOGGED": "系统日志",
        "UNKNOWN": "来源待核",
    },
    "status": {
        "OPEN": "待核",
        "SUPPORTED": "已支持",
        "CONFLICTED": "冲突",
        "ADJUDICATED": "已裁决",
        "EXPIRED": "已过期",
    },
}


def require_process(db: Session, user: User, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None or process.is_draft:
        raise HTTPException(404, "流程不存在或仍为草稿")
    if process.level != 3:
        raise HTTPException(400, "资产包与架构关系只支持 L3 流程")
    org_access.ensure_visible(db, user, process.org_unit_id)
    return process


def published_model(db: Session, process: ProcessArch) -> Optional[ProcessModelVersion]:
    if process.published_model_version:
        row = db.scalar(
            select(ProcessModelVersion).where(
                ProcessModelVersion.process_id == process.id,
                ProcessModelVersion.version == process.published_model_version,
                ProcessModelVersion.status == "PUBLISHED",
            )
        )
        if row is not None:
            return row
    return db.scalar(
        select(ProcessModelVersion)
        .where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.status == "PUBLISHED",
        )
        .order_by(ProcessModelVersion.version.desc())
    )


def _version_info(
    db: Session, process: ProcessArch
) -> Tuple[Optional[int], int, str, bool, List[str]]:
    row = published_model(db, process)
    if row is not None:
        return row.id, row.version, row.status, True, []
    version = int(process.published_model_version or process.model_version or 0)
    return (
        None,
        version,
        "UNVERSIONED",
        False,
        ["没有已发布的模型版本；当前按运行中的模型展示，生成资产前必须在设计器发布。"],
    )


def _version_filter(model_version_id: Optional[int]):
    """有版本时允许历史回填行（model_version_id 为空）；无版本时看全部。"""
    if model_version_id is None:
        return None
    return or_(
        NodeActivityLink.model_version_id == model_version_id,
        NodeActivityLink.model_version_id.is_(None),
    )


def _activity_map(db: Session, ids: Set[int]) -> Dict[int, ProcessArch]:
    if not ids:
        return {}
    return {
        row.id: row for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(ids))).all()
    }


def _link_out(link: NodeActivityLink, activity: Optional[ProcessArch]) -> NodeActivityLinkOut:
    return NodeActivityLinkOut(
        id=link.id,
        node_key=link.node_key,
        activity_id=link.activity_id,
        activity_code=activity.code if activity else None,
        activity_name=activity.name if activity else None,
        relation=link.relation,
        path_condition=link.path_condition,
        coverage=link.coverage,
        confirmed_by_name=link.confirmed_by_name,
        confirmed_at=link.confirmed_at,
        note=link.note,
    )


def _legacy_link(node: ProcessNode, activity: ProcessArch) -> NodeActivityLinkOut:
    """只用于兼容旧设计器的 process_arch_id；权威关系仍以 node_activity_link 为准。"""
    return NodeActivityLinkOut(
        id=0,
        node_key=node.node_key,
        activity_id=activity.id,
        activity_code=activity.code,
        activity_name=activity.name,
        relation="REALIZES",
        path_condition="ALL",
        coverage=1.0,
        note="兼容主活动指针，尚未在关系表确认",
        legacy=True,
    )


def architecture_map(db: Session, process: ProcessArch) -> ArchitectureMapOut:
    version_id, version_no, status, versioned, warnings = _version_info(db, process)
    nodes = list(
        db.scalars(
            select(ProcessNode)
            .where(ProcessNode.process_id == process.id)
            .order_by(ProcessNode.sequence_order, ProcessNode.id)
        ).all()
    )
    stmt = select(NodeActivityLink).where(NodeActivityLink.process_id == process.id)
    filter_clause = _version_filter(version_id)
    if filter_clause is not None:
        stmt = stmt.where(filter_clause)
    links = list(db.scalars(stmt.order_by(NodeActivityLink.id)).all())

    activity_ids = {link.activity_id for link in links}
    activity_ids.update(node.process_arch_id for node in nodes if node.process_arch_id)
    activities = _activity_map(db, activity_ids)

    links_by_node: Dict[str, List[NodeActivityLinkOut]] = {}
    links_out: List[NodeActivityLinkOut] = []
    for link in links:
        out = _link_out(link, activities.get(link.activity_id))
        links_by_node.setdefault(link.node_key, []).append(out)
        links_out.append(out)

    # 兼容旧设计器：只写了 process_arch_id、还没进关系表的节点，按 REALIZES 读取，
    # 但显式标 legacy，不假装它已经在关系表里确认过。
    legacy_count = 0
    for node in nodes:
        if not node.process_arch_id or node.node_type in NON_ACTIVITY_NODES:
            continue
        existing = links_by_node.get(node.node_key, [])
        if any(link.relation in {"REALIZES", "PART_OF"} for link in existing):
            continue
        activity = activities.get(node.process_arch_id)
        if activity is None:
            continue
        legacy = _legacy_link(node, activity)
        links_by_node.setdefault(node.node_key, []).append(legacy)
        links_out.append(legacy)
        legacy_count += 1
    if legacy_count:
        warnings.append(
            f"有 {legacy_count} 个节点只设置了兼容主活动指针；请在架构关系表确认后重新生成。"
        )

    nodes_out = [
        ArchitectureNodeOut(
            id=node.id,
            node_key=node.node_key,
            name=node.name,
            node_type=node.node_type,
            lane=node.lane,
            owner_role=node.owner_role,
            sequence_order=node.sequence_order,
            links=links_by_node.get(node.node_key, []),
        )
        for node in nodes
    ]

    rel_stmt = select(ActivityRelation).where(ActivityRelation.process_id == process.id)
    if version_id is not None:
        rel_stmt = rel_stmt.where(
            or_(
                ActivityRelation.model_version_id == version_id,
                ActivityRelation.model_version_id.is_(None),
            )
        )
    relations = list(db.scalars(rel_stmt.order_by(ActivityRelation.id)).all())
    relation_activity_ids = {row.source_activity_id for row in relations} | {
        row.target_activity_id for row in relations
    }
    relation_activities = _activity_map(db, relation_activity_ids)

    handoff_stmt = select(EdgeHandoffLink).where(EdgeHandoffLink.process_id == process.id)
    if version_id is not None:
        handoff_stmt = handoff_stmt.where(
            or_(
                EdgeHandoffLink.model_version_id == version_id,
                EdgeHandoffLink.model_version_id.is_(None),
            )
        )
    handoffs = list(db.scalars(handoff_stmt.order_by(EdgeHandoffLink.id)).all())

    unmodeled_stmt = select(UnmodeledActivity).where(UnmodeledActivity.process_id == process.id)
    if version_id is not None:
        unmodeled_stmt = unmodeled_stmt.where(
            or_(
                UnmodeledActivity.model_version_id == version_id,
                UnmodeledActivity.model_version_id.is_(None),
            )
        )
    unmodeled = list(db.scalars(unmodeled_stmt.order_by(UnmodeledActivity.id)).all())
    unmodeled_activities = _activity_map(db, {row.activity_id for row in unmodeled})

    if any(link.model_version_id is None for link in links):
        warnings.append("存在未绑定模型版本的历史关系；模型升版后需要重新确认。")
    if unmodeled:
        warnings.append(
            f"有 {len(unmodeled)} 个活动登记为未建模，生成资产时会进入「线下活动」章节。"
        )

    return ArchitectureMapOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=version_id,
        model_version=version_no,
        model_status=status,
        versioned=versioned,
        nodes=nodes_out,
        links=links_out,
        activity_relations=[
            ActivityRelationOut(
                id=row.id,
                source_activity_id=row.source_activity_id,
                source_code=relation_activities.get(row.source_activity_id).code
                if relation_activities.get(row.source_activity_id)
                else None,
                source_name=relation_activities.get(row.source_activity_id).name
                if relation_activities.get(row.source_activity_id)
                else None,
                target_activity_id=row.target_activity_id,
                target_code=relation_activities.get(row.target_activity_id).code
                if relation_activities.get(row.target_activity_id)
                else None,
                target_name=relation_activities.get(row.target_activity_id).name
                if relation_activities.get(row.target_activity_id)
                else None,
                relation=row.relation,
                confirmed_by_name=row.confirmed_by_name,
                confirmed_at=row.confirmed_at,
            )
            for row in relations
        ],
        handoffs=[
            EdgeHandoffOut(
                id=row.id,
                edge_key=row.edge_key,
                from_activity_id=row.from_activity_id,
                to_activity_id=row.to_activity_id,
                handoff_type=row.handoff_type,
                confirmed_by_name=row.confirmed_by_name,
                confirmed_at=row.confirmed_at,
            )
            for row in handoffs
        ],
        unmodeled=[
            UnmodeledActivityOut(
                id=row.id,
                activity_id=row.activity_id,
                activity_code=unmodeled_activities.get(row.activity_id).code
                if unmodeled_activities.get(row.activity_id)
                else None,
                activity_name=unmodeled_activities.get(row.activity_id).name
                if unmodeled_activities.get(row.activity_id)
                else None,
                reason=row.reason,
                source_ref=row.source_ref,
                confirmed_by_name=row.confirmed_by_name,
            )
            for row in unmodeled
        ],
        warnings=warnings,
    )


def _target_label(
    db: Session, target: EvidenceClaimTarget, cache: Dict[Tuple[str, int], str]
) -> str:
    key = (target.target_type, target.target_id)
    if key in cache:
        return cache[key]
    label = f"{target.target_type}:{target.target_id}"
    if target.target_type in {"ACTIVITY", "TIME_FIELD"}:
        row = db.get(ProcessArch, target.target_id)
        if row is not None:
            label = f"{row.code} {row.name}"
    elif target.target_type == "NODE":
        row = db.get(ProcessNode, target.target_id)
        if row is not None:
            label = f"{row.node_key} {row.name}"
    elif target.target_type == "EDGE":
        row = db.get(ProcessEdge, target.target_id)
        if row is not None:
            label = f"{row.source_key}→{row.target_key}"
    elif target.target_type == "PROCESS":
        row = db.get(ProcessArch, target.target_id)
        if row is not None:
            label = f"{row.code} {row.name}"
    elif target.target_type == "KPI":
        row = db.get(KpiDefinition, target.target_id)
        if row is not None:
            label = f"{row.code} {row.name}"
    elif target.target_type == "RULE":
        row = db.get(ProcessRule, target.target_id)
        if row is not None:
            label = f"{row.node_key} {row.name}"
    cache[key] = label
    return label


def evidence_claims(db: Session, process: ProcessArch) -> EvidenceClaimListOut:
    claims = list(
        db.scalars(
            select(EvidenceClaim)
            .where(EvidenceClaim.process_id == process.id)
            .options(selectinload(EvidenceClaim.targets))
            .order_by(EvidenceClaim.created_at.desc(), EvidenceClaim.id.desc())
        ).all()
    )
    groups = {claim.conflict_group for claim in claims if claim.conflict_group}
    adjudications = (
        list(
            db.scalars(
                select(EvidenceAdjudication)
                .where(EvidenceAdjudication.conflict_group.in_(groups))
                .order_by(EvidenceAdjudication.decided_at.desc(), EvidenceAdjudication.id.desc())
            ).all()
        )
        if groups
        else []
    )
    by_group: Dict[str, List[EvidenceAdjudication]] = {}
    for row in adjudications:
        by_group.setdefault(row.conflict_group, []).append(row)

    target_cache: Dict[Tuple[str, int], str] = {}
    claims_out: List[EvidenceClaimOut] = []
    for claim in claims:
        claims_out.append(
            EvidenceClaimOut(
                id=claim.id,
                claim=claim.claim,
                claim_type=claim.claim_type,
                source_type=claim.source_type,
                source_id=claim.source_id,
                source_version=claim.source_version,
                source_hash=claim.source_hash,
                method=claim.method,
                samples=claim.samples,
                window_start=claim.window_start,
                window_end=claim.window_end,
                coverage=claim.coverage,
                quality=claim.quality or {},
                conflict_group=claim.conflict_group,
                status=claim.status,
                valid_from=claim.valid_from,
                valid_to=claim.valid_to,
                query_ref=claim.query_ref,
                result_hash=claim.result_hash,
                created_by_name=claim.created_by_name,
                created_at=claim.created_at,
                targets=[
                    EvidenceClaimTargetOut(
                        id=target.id,
                        target_type=target.target_type,
                        target_id=target.target_id,
                        model_version_id=target.model_version_id,
                        field=target.field,
                        condition=target.condition,
                        target_code=db.get(ProcessArch, target.target_id).code
                        if target.target_type in {"ACTIVITY", "TIME_FIELD"}
                        and db.get(ProcessArch, target.target_id)
                        else None,
                        target_name=db.get(ProcessArch, target.target_id).name
                        if target.target_type in {"ACTIVITY", "TIME_FIELD"}
                        and db.get(ProcessArch, target.target_id)
                        else _target_label(db, target, target_cache),
                    )
                    for target in claim.targets
                ],
                adjudications=[
                    EvidenceAdjudicationOut(
                        id=row.id,
                        conflict_group=row.conflict_group,
                        decision=row.decision,
                        rationale=row.rationale,
                        decided_by_name=row.decided_by_name,
                        decided_at=row.decided_at,
                        authority_ref=row.authority_ref,
                    )
                    for row in by_group.get(claim.conflict_group or "", [])
                ],
            )
        )

    conflicts = sorted(
        {
            claim.conflict_group
            for claim in claims
            if claim.conflict_group
            and claim.status in {"CONFLICTED", "OPEN"}
            and claim.conflict_group not in by_group
        }
    )
    unknown = _unknown_targets(db, process, claims)
    return EvidenceClaimListOut(
        process_id=process.id,
        claims=claims_out,
        conflicts=conflicts,
        unknown_targets=unknown,
        labels=LABELS,
    )


def _unknown_targets(db: Session, process: ProcessArch, claims: List[EvidenceClaim]) -> List[str]:
    """没有主张覆盖的活动/节点。只算活动级，不逐字段，避免伪造覆盖。"""
    covered_activities: Set[int] = set()
    covered_nodes: Set[int] = set()
    for claim in claims:
        for target in claim.targets:
            if target.target_type in {"ACTIVITY", "TIME_FIELD"}:
                covered_activities.add(target.target_id)
            elif target.target_type == "NODE":
                covered_nodes.add(target.target_id)

    links = list(
        db.scalars(
            select(NodeActivityLink).where(
                NodeActivityLink.process_id == process.id,
                NodeActivityLink.relation.in_({"REALIZES", "PART_OF"}),
            )
        ).all()
    )
    node_activity = {link.node_key: link.activity_id for link in links}

    result: List[str] = []
    for node in db.scalars(select(ProcessNode).where(ProcessNode.process_id == process.id)).all():
        if node.node_type in NON_ACTIVITY_NODES:
            continue
        activity_id = node.process_arch_id or node_activity.get(node.node_key)
        if node.id not in covered_nodes and (
            activity_id is None or activity_id not in covered_activities
        ):
            result.append(f"NODE:{node.node_key} {node.name}")

    for row in db.scalars(
        select(UnmodeledActivity).where(UnmodeledActivity.process_id == process.id)
    ).all():
        if row.activity_id in covered_activities:
            continue
        activity = db.get(ProcessArch, row.activity_id)
        label = f"{activity.code} {activity.name}" if activity else str(row.activity_id)
        result.append(f"ACTIVITY:{label}")
    return result


def readiness(db: Session, process: ProcessArch, user: Optional[User] = None) -> AssetReadinessOut:
    version_id, version_no, status, versioned, warnings = _version_info(db, process)
    nodes = list(
        db.scalars(
            select(ProcessNode)
            .where(ProcessNode.process_id == process.id)
            .order_by(ProcessNode.sequence_order, ProcessNode.id)
        ).all()
    )
    links_stmt = select(NodeActivityLink).where(NodeActivityLink.process_id == process.id)
    filter_clause = _version_filter(version_id)
    if filter_clause is not None:
        links_stmt = links_stmt.where(filter_clause)
    links = list(db.scalars(links_stmt).all())

    links_by_node: Dict[str, List[NodeActivityLink]] = {}
    for link in links:
        links_by_node.setdefault(link.node_key, []).append(link)

    activity_nodes = [node for node in nodes if node.node_type in ACTIVITY_NODE_TYPES]
    decision_nodes = [node for node in nodes if node.node_type == "DECISION"]

    from app.services import binding_readiness

    binding = binding_readiness.activity_bindings(db, process.id, user, model_version_id=version_id)
    gate = binding_readiness.binding_gate(
        db, process.id, user, profile="PERFORMANCE", model_version_id=version_id
    )
    by_key = {n.node_key: n for n in binding.nodes}

    def ready_facet(node, key):
        bound = by_key.get(node.node_key)
        return bool(
            bound
            and not bound.blockers
            and any(f.key == key and f.status == "READY" for f in bound.facets)
        )

    mapped = [
        node
        for node in activity_nodes
        if node.node_key in by_key and not by_key[node.node_key].blockers
    ]
    owner_ready = [node for node in activity_nodes if ready_facet(node, "TEAM")]
    carrier_ready = [node for node in activity_nodes if ready_facet(node, "RESOURCE")]
    rule_keys = set(
        db.scalars(
            select(ProcessRule.node_key).where(
                ProcessRule.process_id == process.id, ProcessRule.is_active.is_(True)
            )
        )
    )
    rule_ready = [node for node in decision_nodes if node.node_key in rule_keys]
    legacy_nodes = [
        node
        for node in activity_nodes
        if node.process_arch_id
        and not any(
            link.relation in {"REALIZES", "PART_OF"}
            for link in links_by_node.get(node.node_key, [])
        )
    ]

    claims = list(
        db.scalars(
            select(EvidenceClaim)
            .where(EvidenceClaim.process_id == process.id)
            .options(selectinload(EvidenceClaim.targets))
        ).all()
    )
    today = utcnow().date()
    expired = [claim for claim in claims if claim.valid_to is not None and claim.valid_to < today]
    conflicted = [claim for claim in claims if claim.status == "CONFLICTED"]
    groups = {claim.conflict_group for claim in claims if claim.conflict_group}
    adjudicated = (
        {
            row.conflict_group
            for row in db.scalars(
                select(EvidenceAdjudication).where(EvidenceAdjudication.conflict_group.in_(groups))
            ).all()
        }
        if groups
        else set()
    )
    unresolved_groups = sorted(
        {
            claim.conflict_group
            for claim in claims
            if claim.conflict_group
            and claim.status in {"CONFLICTED", "OPEN"}
            and claim.conflict_group not in adjudicated
        }
    )

    blockers: List[ReadinessBlockerOut] = []
    if not versioned:
        blockers.append(
            ReadinessBlockerOut(
                code="MODEL_NOT_VERSIONED",
                message="没有已发布的模型版本；请先在流程设计器发布。",
            )
        )
    blockers.extend(gate.blockers)
    unresolved_claims = [
        claim
        for claim in conflicted
        if not claim.conflict_group or claim.conflict_group not in adjudicated
    ]
    if unresolved_groups or unresolved_claims:
        blockers.append(
            ReadinessBlockerOut(
                code="EVIDENCE_CONFLICT",
                message="存在未裁决的证据冲突；草稿可生成，但不允许生效。",
                targets=unresolved_groups or [str(claim.id) for claim in unresolved_claims],
            )
        )
    if expired:
        blockers.append(
            ReadinessBlockerOut(
                code="EVIDENCE_EXPIRED",
                message=f"{len(expired)} 条证据已过期；请续证或重新采集。",
                targets=[f"claim:{claim.id}" for claim in expired],
            )
        )

    hard_codes = {"MODEL_NOT_VERSIONED", "NODE_ACTIVITY_UNMAPPED"}
    can_generate_draft = versioned and not any(item.code in hard_codes for item in blockers)
    can_submit_review = not blockers

    next_action = blockers[0].message if blockers else "可以生成资产包草稿并提交评审。"

    if not versioned:
        warnings.append("模型未版本化：当前就绪度基于运行中的节点，不能作为正式生成依据。")
    if any(link.model_version_id is None for link in links):
        warnings.append("存在未绑定模型版本的历史关系；模型升版后需要重新确认。")
    if legacy_nodes:
        warnings.append(
            f"{len(legacy_nodes)} 个活动只设置了兼容主活动指针；请在架构关系表确认后重新生成。"
        )
    if not claims:
        warnings.append("还没有证据主张；范围/设计可继续，但定量结论不可用。")

    return AssetReadinessOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=version_id,
        model_version=version_no,
        model_status=status,
        versioned=versioned,
        metrics={
            "activity_nodes": len(activity_nodes),
            "mapped_activities": len(mapped),
            "owner_ready": len(owner_ready),
            "carrier_ready": len(carrier_ready),
            "decision_nodes": len(decision_nodes),
            "rule_ready": len(rule_ready),
            "control_links": sum(1 for link in links if link.relation == "CONTROLS"),
            "claims_total": len(claims),
            "claims_conflicted": len(conflicted),
            "claims_expired": len(expired),
        },
        blockers=blockers,
        warnings=warnings,
        can_generate_draft=can_generate_draft,
        can_submit_review=can_submit_review,
        next_action=next_action,
    )
