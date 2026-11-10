"""活动四绑定只读查询：不补建基线、不更新原对象、不作为发布门禁。"""

from collections import defaultdict
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.adoption import ProcessTrainingRecord
from app.models.asset_graph import EvidenceClaim, NodeActivityLink
from app.models.execution import FormDefinition, ProcessRule
from app.models.monitor import KpiDefinition
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch, ProcessNode
from app.models.process_document import ProcessDocument
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.models.workload import WorkMeasurementStandard
from app.schemas.binding_readiness import (
    ActivityBindingOut,
    ActivityBindingsOut,
    BindingFacetOut,
    BindingRefOut,
    NodeBindingOut,
    ProcessBindingSummaryOut,
)
from app.services import org_access, process_model
from app.services.process_document import effective_version_on, visible_conditions

FACETS = {"GOAL": "定目标", "TEAM": "搭班子", "RESOURCE": "配资源", "METHOD": "智慧与绩效"}
STATUSES = {"READY": "齐全", "PARTIAL": "部分就绪", "MISSING": "缺失", "CONFLICT": "冲突"}
SOURCES = {
    "DIRECT": "直接绑定",
    "INHERITED": "继承 / 未到活动",
    "PROCESS": "流程事项 / 未到活动",
    "MIXED": "直接与继承",
    "NONE": "无来源",
}


def _ref(kind, row, source="DIRECT", detail=None):
    return BindingRefOut(
        kind=kind,
        id=row.id,
        label=getattr(row, "name", None)
        or getattr(row, "title", None)
        or getattr(row, "matter", kind),
        source=source,
        source_label=SOURCES[source],
        detail=detail,
    )


def _facet(key, refs, ready=False, gaps=None, conflict=False):
    sources = {ref.source for ref in refs}
    source = next(iter(sources)) if len(sources) == 1 else ("MIXED" if sources else "NONE")
    status = "CONFLICT" if conflict else "READY" if ready else "PARTIAL" if refs else "MISSING"
    return BindingFacetOut(
        key=key,
        label=FACETS[key],
        status=status,
        status_label=STATUSES[status],
        source=source,
        source_label=SOURCES[source],
        refs=refs,
        gaps=gaps or [],
    )


def _overall(facets):
    statuses = {item.status for item in facets}
    if "CONFLICT" in statuses:
        return "CONFLICT"
    if statuses == {"READY"}:
        return "READY"
    if not statuses or statuses == {"MISSING"}:
        return "MISSING"
    return "PARTIAL"


def _in_date(row, day):
    return (row.valid_from is None or row.valid_from <= day) and (
        row.valid_to is None or row.valid_to >= day
    )


def _team_facet(related, activity_id, racis, positions):
    keys = {node.node_key for node in related}
    relevant = [
        row
        for row in racis
        if row.activity_id == activity_id or row.activity_id is None and row.node_key in keys
    ]
    inherited = [row for row in racis if row.activity_id is None and not row.node_key]
    refs = [
        _ref("POSITION", positions[node.owner_position_id])
        for node in related
        if node.owner_position_id in positions
    ]
    refs += [
        BindingRefOut(
            kind="ROLE_TEXT",
            label=node.owner_role,
            source="DIRECT",
            source_label=SOURCES["DIRECT"],
            detail="文本角色，尚未归位到岗位",
        )
        for node in related
        if node.owner_role and not node.owner_position_id
    ]
    refs += [_ref("RACI", row, "DIRECT", f"{row.raci} · {row.scope_key}") for row in relevant]
    refs += [
        _ref("RACI", row, "PROCESS", f"{row.raci} · 流程事项，非活动责任") for row in inherited
    ]
    by_scope = defaultdict(list)
    for row in relevant:
        if row.raci == "A":
            by_scope[row.scope_key].append(row)
    conflict = any(len(rows) > 1 for rows in by_scope.values())
    activity_a = by_scope.get(f"ACTIVITY:{activity_id}", [])
    ready = (
        bool(related)
        and not conflict
        and all(
            node.owner_position_id in positions
            and (len(by_scope.get("NODE:" + node.node_key, [])) == 1 or len(activity_a) == 1)
            for node in related
        )
    )
    return _facet(
        "TEAM",
        refs,
        ready,
        [] if ready else ["缺活动/节点唯一 RACI-A 或有效负责人岗位；流程事项不能代替"],
        conflict=conflict,
    )


def activity_bindings(
    db: Session, process_id: int, user: Optional[User] = None
) -> ActivityBindingsOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(404, "流程不存在")
    if process.level not in {3, 4}:
        raise HTTPException(400, "绑定核对只支持 L3 流程或 L4 活动设计模型")
    # 流程架构/设计图是公司级可读；具体原来源按各领域组织规则过滤。
    day = utcnow().date()
    # latest_version/current_snapshot 均纯读；禁止 ensure_baseline/get_design 的隐式写入。
    version = process_model.latest_version(db, process_id)
    snapshot = version.snapshot if version else process_model.current_snapshot(db, process_id)
    nodes, _edges = process_model.rows_from_snapshot(process_id, snapshot or {})
    nodes = [
        node for node in nodes if node.node_type in {"TASK", "APPROVAL", "DECISION", "HANDOFF"}
    ]
    activities = list(
        db.scalars(
            select(ProcessArch)
            .where(
                ProcessArch.level == 4,
                ProcessArch.parent_id == process_id,
                ProcessArch.is_draft.is_(False),
            )
            .order_by(ProcessArch.code)
        ).all()
    )
    if process.level == 4 and not process.is_draft:
        activities = [process]
    activity_map = {row.id: row for row in activities}
    activity_ids = set(activity_map)
    links = list(
        db.scalars(
            select(NodeActivityLink).where(
                NodeActivityLink.process_id == process_id,
                or_(
                    NodeActivityLink.model_version_id == version.id if version else False,
                    NodeActivityLink.model_version_id.is_(None),
                ),
            )
        ).all()
    )
    by_node = defaultdict(list)
    controls = defaultdict(list)
    for link in links:
        if link.relation in {"REALIZES", "PART_OF"}:
            by_node[link.node_key].append(link)
        elif link.relation == "CONTROLS" and link.activity_id in activity_ids:
            controls[link.activity_id].append(link)
    mapped = defaultdict(list)
    node_ids = {}
    conflicts = {}
    for node in nodes:
        relations = by_node[node.node_key]
        ids = (
            sorted({row.activity_id for row in relations})
            if relations
            else ([node.process_arch_id] if node.process_arch_id else [])
        )
        bad = any(ident not in activity_ids for ident in ids)
        conflicts[node.node_key] = ["活动映射不属于当前流程或活动仍为草稿"] if bad else []
        # 有权威关系时不退回兼容指针，即使关系本身无效。
        node_ids[node.node_key] = [ident for ident in ids if ident in activity_ids]
        for ident in node_ids[node.node_key]:
            mapped[ident].append(node)

    def rows(cls, *conditions):
        return list(db.scalars(select(cls).where(*conditions)).all())

    kpis = rows(
        KpiDefinition,
        KpiDefinition.is_active.is_(True),
        or_(KpiDefinition.process_id == process_id, KpiDefinition.activity_id.in_(activity_ids)),
    )
    kpis = [row for row in kpis if _in_date(row, day)]
    positions_stmt = select(Position).where(Position.is_active.is_(True))
    if user:
        positions_stmt = org_access.restrict(positions_stmt, db, user, Position.org_unit_id)
    positions = {row.id: row for row in db.scalars(positions_stmt).all()}
    raci_stmt = (
        select(RaciAssignment)
        .join(GovernanceRole)
        .where(RaciAssignment.process_id == process_id, GovernanceRole.is_active.is_(True))
    )
    if user:
        raci_stmt = org_access.restrict(raci_stmt, db, user, GovernanceRole.org_unit_id)
    racis = list(db.scalars(raci_stmt).all())
    standards_stmt = select(WorkMeasurementStandard).where(
        WorkMeasurementStandard.activity_id.in_(activity_ids),
        WorkMeasurementStandard.status == "VERIFIED",
    )
    if user:
        standards_stmt = org_access.restrict(
            standards_stmt, db, user, WorkMeasurementStandard.org_unit_id
        )
    standards = [
        row
        for row in db.scalars(standards_stmt).all()
        if _in_date(row, day) and row.task_id is None
    ]
    forms = rows(
        FormDefinition, FormDefinition.process_id == process_id, FormDefinition.is_active.is_(True)
    )
    rules = rows(ProcessRule, ProcessRule.process_id == process_id, ProcessRule.is_active.is_(True))
    docs_stmt = (
        select(ProcessDocument)
        .options(selectinload(ProcessDocument.versions))
        .where(
            ProcessDocument.is_active.is_(True),
            ProcessDocument.process_id.in_(activity_ids | {process_id}),
        )
    )
    condition = visible_conditions(db, process.org_unit_id)
    if condition is not None:
        docs_stmt = docs_stmt.where(condition)
    if user and not org_access.unrestricted(user):
        condition = visible_conditions(db, user.org_unit_id)
        docs_stmt = (
            docs_stmt.where(condition)
            if condition is not None
            else docs_stmt.where(ProcessDocument.org_unit_id.is_(None))
        )
    documents = [(row, effective_version_on(row, day)) for row in db.scalars(docs_stmt).all()]
    documents = [(row, ver) for row, ver in documents if ver is not None]
    claims = list(
        db.scalars(
            select(EvidenceClaim)
            .options(selectinload(EvidenceClaim.targets))
            .where(EvidenceClaim.process_id == process_id)
        ).all()
    )
    visible_claims = []
    # NODE证据使用持久化主键；快照rows_from_snapshot的顺序ID不是证据身份。
    live_node_keys = {
        row.id: row.node_key
        for row in db.scalars(select(ProcessNode).where(ProcessNode.process_id == process_id)).all()
    }
    from app.services import evidence_source

    for claim in claims:
        if not _in_date(claim, day) or claim.status == "EXPIRED":
            continue
        if evidence_source.resolve(db, process, claim, user) is not None:
            visible_claims.append(claim)
    tools = rows(NodeTool, NodeTool.process_id == process_id)
    from app.services import resource_link

    linked_resources = resource_link.list_links(db, process, user) if process.level == 3 else []
    training = rows(ProcessTrainingRecord, ProcessTrainingRecord.process_id == process_id)
    # 目标的祖先承接沿原主数据，不按名称匹配。
    ancestors = {process_id}
    parent_id = process.parent_id
    while parent_id and parent_id not in ancestors:
        ancestors.add(parent_id)
        parent = db.get(ProcessArch, parent_id)
        parent_id = parent.parent_id if parent else None
    objectives = list(
        db.execute(
            select(ObjectiveProcessLink, StrategyObjective)
            .join(StrategyObjective)
            .where(
                ObjectiveProcessLink.process_id.in_(ancestors | activity_ids),
                StrategyObjective.status == "ACTIVE",
            )
        ).all()
    )

    activity_out = []
    for activity in activities:
        related = mapped[activity.id]
        keys = {node.node_key for node in related}
        direct_kpis = [
            row
            for row in kpis
            if row.activity_id == activity.id and row.process_id in {None, process_id}
        ]
        inherited_kpis = [
            row for row in kpis if row.process_id == process_id and row.activity_id is None
        ]
        refs = [_ref("KPI", row) for row in direct_kpis]
        refs += [_ref("KPI", row, "INHERITED") for row in inherited_kpis]
        refs += [
            _ref("OBJECTIVE", obj, "DIRECT" if link.process_id == activity.id else "INHERITED")
            for link, obj in objectives
            if link.process_id in ancestors | {activity.id}
        ]
        goal_ready = bool(direct_kpis) and all(
            row.target_value is not None
            and row.measurement
            and row.direction in {"LOWER_BETTER", "HIGHER_BETTER"}
            for row in direct_kpis
        )
        goal = _facet(
            "GOAL",
            refs,
            goal_ready,
            [] if goal_ready else ["缺活动级完整 KPI（目标值、口径与方向）"],
        )

        team = _team_facet(related, activity.id, racis, positions)

        applicable_standards = [
            row
            for row in standards
            if row.activity_id == activity.id
            and row.position_id in positions
            and any(node.owner_position_id == row.position_id for node in related)
        ]
        refs = [
            _ref("WORK_STANDARD", row, detail=f"已验证标准工时 {row.standard_minutes} 分钟")
            for row in applicable_standards
        ]
        refs += [
            BindingRefOut(
                kind="DESIGN_ESTIMATE",
                label=node.name,
                source="DIRECT",
                source_label=SOURCES["DIRECT"],
                detail=f"设计估计 {node.duration_minutes} 分钟，非验证工时",
            )
            for node in related
            if (node.duration_minutes or 0) > 0
        ]
        specific_forms = [row for row in forms if row.node_key in keys]
        default_forms = [row for row in forms if not row.node_key]
        refs += [_ref("FORM", row) for row in specific_forms]
        refs += [_ref("FORM", row, "INHERITED") for row in default_forms]
        carriers = [
            (doc, ver)
            for doc, ver in documents
            if doc.category in {"FORM", "CHECKLIST"}
            and (
                doc.process_id == activity.id
                and not doc.node_key
                or doc.process_id == process_id
                and doc.node_key in keys
            )
        ]
        refs += [_ref("DOCUMENT", doc, detail=f"v{ver.version_label}") for doc, ver in carriers]
        refs += [
            _ref("DOCUMENT", doc, "INHERITED", f"生效 v{ver.version_label}")
            for doc, ver in documents
            if doc.process_id == process_id
            and not doc.node_key
            and doc.category in {"FORM", "CHECKLIST"}
        ]
        node_rules = [row for row in rules if row.node_key in keys]
        refs += [_ref("RULE", row) for row in node_rules]
        activity_resources = [row for row in linked_resources if row.activity_id == activity.id]
        valid_resources = [row for row in activity_resources if row.source_valid]
        refs += [
            BindingRefOut(
                kind="RESOURCE_LINK",
                id=row.id,
                label=row.source_label,
                source="DIRECT",
                source_label=SOURCES["DIRECT"],
                detail=f"{row.resource_type_label} · {row.ref_key} · {row.source_note}",
            )
            for row in valid_resources
        ]
        linked_forms = {
            row.node_key for row in valid_resources if row.resource_type == "FORM" and row.node_key
        }
        linked_carrier = any(row.is_record_carrier and not row.node_key for row in valid_resources)
        covered = (
            {row.node_key for row in specific_forms}
            | {doc.node_key for doc, _ in carriers}
            | linked_forms
        )
        has_carrier = bool(related) and (
            keys <= covered
            or linked_carrier
            or any(doc.process_id == activity.id for doc, _ in carriers)
        )
        has_rules = all(
            node.node_type != "DECISION" or any(row.node_key == node.node_key for row in node_rules)
            for node in related
        )
        # 设计估计可显示但不冒充已验证工时，缺省0也不算显式估计。
        standards_by_position = {row.position_id for row in applicable_standards}
        time_ready = bool(related) and all(
            node.owner_position_id in standards_by_position for node in related
        )
        resource_ready = time_ready and has_carrier and has_rules
        gaps = []
        if not time_ready:
            gaps.append("缺适用岗位的已验证活动标准工时；设计估计单列")
        if not has_carrier:
            gaps.append("缺节点专属表单或活动记录载体；默认表单仅继承")
        if not has_rules:
            gaps.append("判断节点缺启用规则")
        stale_resources = [row for row in activity_resources if not row.source_valid]
        if stale_resources:
            gaps.append(f"{len(stale_resources)} 条原资源引用已失效，须回原来源核对")
        resource = _facet("RESOURCE", refs, resource_ready and not stale_resources, gaps)

        direct_docs = [
            (doc, ver)
            for doc, ver in documents
            if doc.category in {"SOP", "POLICY"}
            and (
                doc.process_id == activity.id
                and not doc.node_key
                or doc.process_id == process_id
                and doc.node_key in keys
            )
        ]
        inherited_docs = [
            (doc, ver)
            for doc, ver in documents
            if doc.category in {"SOP", "POLICY"}
            and doc.process_id == process_id
            and not doc.node_key
        ]
        refs = [
            _ref("DOCUMENT", doc, detail=f"生效 v{ver.version_label}") for doc, ver in direct_docs
        ]
        refs += [
            _ref("DOCUMENT", doc, "INHERITED", f"生效 v{ver.version_label}")
            for doc, ver in inherited_docs
        ]
        refs += [_ref("TOOL", row, detail=row.tool_code) for row in tools if row.node_key in keys]
        # 培训只汇总流程级主题，不输出人员身份或把签到当能力。
        if training:
            refs.append(
                BindingRefOut(
                    kind="TRAINING",
                    label=f"流程级培训 {len(training)} 条",
                    source="INHERITED",
                    source_label=SOURCES["INHERITED"],
                    detail="记录存在不等于操作能力已验证",
                )
            )
        activity_claims = [
            claim
            for claim in visible_claims
            if any(
                (
                    target.target_type in {"ACTIVITY", "TIME_FIELD"}
                    and target.target_id == activity.id
                    or target.target_type == "NODE"
                    and live_node_keys.get(target.target_id) in keys
                )
                and (
                    target.model_version_id is None
                    or (version and target.model_version_id == version.id)
                )
                for target in claim.targets
            )
        ]
        refs += [
            BindingRefOut(
                kind="EVIDENCE",
                id=claim.id,
                label=claim.claim,
                source="DIRECT",
                source_label=SOURCES["DIRECT"],
                detail=f"证据主张 · {claim.method} · {claim.status}（不代表业务效果核验）",
            )
            for claim in activity_claims
        ]
        refs += [
            _ref("CONTROL", link, detail=f"控制节点 {link.node_key}")
            for link in controls[activity.id]
            if any(node.node_key == link.node_key for node in nodes)
        ]
        evidence_ready = any(
            claim.claim_type == "CONTROL" and claim.status in {"SUPPORTED", "ADJUDICATED"}
            for claim in activity_claims
        )
        control_ready = (
            any(doc.control_points for doc, _ in direct_docs)
            or evidence_ready
            or any(
                link.node_key in {node.node_key for node in nodes} for link in controls[activity.id]
            )
        )
        method_ready = bool(direct_docs) and control_ready
        method = _facet(
            "METHOD",
            refs,
            method_ready,
            [] if method_ready else ["缺活动生效标准及控制点 / 证据要求"],
            conflict=any(claim.status == "CONFLICTED" for claim in activity_claims),
        )
        activity_out.append(
            ActivityBindingOut(
                activity_id=activity.id,
                activity_code=activity.code,
                activity_name=activity.name,
                node_keys=sorted(keys),
                facets=[goal, team, resource, method],
                blockers=[] if related else ["活动尚未由当前模型节点实现"],
            )
        )

    by_activity = {row.activity_id: row for row in activity_out}
    node_out = []
    for node in nodes:
        ids = node_ids[node.node_key]
        facets = []
        for key in FACETS:
            parts = (
                [_team_facet([node], ident, racis, positions) for ident in ids]
                if key == "TEAM"
                else [next(f for f in by_activity[ident].facets if f.key == key) for ident in ids]
            )
            refs = [ref for part in parts for ref in part.refs]
            gaps = list(dict.fromkeys(gap for part in parts for gap in part.gaps))
            facet = _facet(
                key,
                refs,
                bool(parts) and all(part.status == "READY" for part in parts),
                gaps,
                conflict=any(part.status == "CONFLICT" for part in parts),
            )
            facets.append(facet)
        blockers = conflicts[node.node_key] or ([] if ids else ["节点未映射到本流程 L4 活动"])
        status = "CONFLICT" if conflicts[node.node_key] else _overall(facets)
        marker = (
            "green"
            if status == "READY" and not blockers
            else "red"
            if status == "MISSING"
            else "yellow"
        )
        node_out.append(
            NodeBindingOut(
                node_key=node.node_key,
                node_name=node.name,
                activity_ids=ids,
                status=status,
                status_label=STATUSES[status],
                marker=marker,
                facets=facets,
                blockers=blockers,
            )
        )
    all_facets = [facet for row in activity_out for facet in row.facets]
    conflict_list = [
        f"{node.node_key}: {item}"
        for node in node_out
        if node.status == "CONFLICT"
        for item in node.blockers
    ]
    overall = "CONFLICT" if conflict_list else _overall(all_facets)
    summary_facets = []
    for key in FACETS:
        parts = [facet for facet in all_facets if facet.key == key]
        summary_facets.append(
            _facet(
                key,
                [],
                bool(parts) and all(f.status == "READY" for f in parts),
                list(dict.fromkeys(gap for part in parts for gap in part.gaps)),
                conflict=any(part.status == "CONFLICT" for part in parts),
            )
        )
        status = _overall(parts)
        summary_facets[-1].status = status
        summary_facets[-1].status_label = STATUSES[status]
    summary = ProcessBindingSummaryOut(
        process_id=process_id,
        overall=overall,
        overall_label=STATUSES[overall],
        facets_ready={
            key: sum(f.status == "READY" and f.key == key for f in all_facets) for key in FACETS
        },
        facets=summary_facets,
        conflicts=conflict_list,
        counts={
            "activities": len(activity_out),
            "nodes": len(node_out),
            "unmapped_nodes": sum(not node.activity_ids for node in node_out),
            "unmodeled_activities": sum(not row.node_keys for row in activity_out),
        },
    )
    from app.models.process import ProcessModelVersion
    from app.services import binding_snapshot

    current_bindings = binding_snapshot.capture(db, process, version)
    basis = (
        version
        if version and version.binding_snapshot is not None
        else db.scalar(
            select(ProcessModelVersion)
            .where(
                ProcessModelVersion.process_id == process_id,
                ProcessModelVersion.status == "PUBLISHED",
            )
            .order_by(ProcessModelVersion.version.desc())
        )
    )
    basis_snapshot = basis.binding_snapshot if basis else None
    consistency = binding_snapshot.compare(current_bindings, basis_snapshot)
    for item in activity_out:
        aid = str(item.activity_id)
        current_activity = {
            "model_version_id": current_bindings["model_version_id"],
            "activities": {aid: current_bindings["activities"][aid]},
        }
        original_activity = (
            {
                "model_version_id": basis_snapshot["model_version_id"],
                "activities": {aid: basis_snapshot["activities"][aid]},
            }
            if basis_snapshot and aid in basis_snapshot.get("activities", {})
            else None
        )
        item.consistency = binding_snapshot.compare(current_activity, original_activity)
        item.consistency_label = binding_snapshot.LABELS[item.consistency]
    return ActivityBindingsOut(
        consistency=consistency,
        consistency_label=binding_snapshot.LABELS[consistency],
        basis_model_version_id=basis.id if basis else None,
        process_id=process_id,
        model_version_id=version.id if version else None,
        model_version=version.version if version else int(process.model_version or 0),
        summary=summary,
        activities=activity_out,
        nodes=node_out,
        limitations=[
            "只读结构核对，不代表授权充分、资源到位或业务绩效达标。",
            "活动级唯一 A 只核绑定结构；不替代组织有权政策与职责分离核验。",
            "按当前已保存设计模型核对；未保存修改不纳入。设计估计不等于已验证工时。",
            "绑定齐全不直接改变执行上线或资产评审门禁；冻结依据变更需新工作版。",
        ],
    )


def process_bindings(
    db: Session, process_id: int, user: Optional[User] = None
) -> ProcessBindingSummaryOut:
    return activity_bindings(db, process_id, user).summary
