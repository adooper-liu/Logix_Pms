"""流程设计器：泳道建模、指标测算、改善建议。"""

from __future__ import annotations

import copy
from typing import List

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    ensure_can_edit_owned,
)
from app.models.enums import ToolLevel
from app.models.org import Position
from app.models.process import (
    NodeTool,
    ProcessArch,
    ProcessEdge,
    ProcessModelVersion,
    ProcessNode,
)
from app.models.tool import Tool
from app.schemas.common import DeleteResult
from app.schemas.node_tool import NodeToolCreate, NodeToolOut
from app.schemas.process import (
    BpmnImportRequest,
    DesignAnalysis,
    DesignValidation,
    ProcessEdgeOut,
    ProcessModelDiffOut,
    ProcessModelIn,
    ProcessModelOut,
    ProcessModelVersionDetail,
    ProcessModelVersionOut,
    ProcessNodeMetricsUpdate,
    ProcessNodeOut,
    PublishModelRequest,
    ReviewModelRequest,
    RollbackModelRequest,
)
from app.schemas.simulation import SimulationOut, SimulationRequest
from app.services import audit as audit_service
from app.services import bpmn as bpmn_service
from app.services import change as change_service
from app.services import designer
from app.services import process_model as model_service
from app.services import simulation as simulation_service

router = APIRouter(tags=["流程设计器"])


def _version_out(row: ProcessModelVersion) -> ProcessModelVersionOut:
    snapshot = row.snapshot or {}
    return ProcessModelVersionOut(
        id=row.id,
        version=row.version,
        status=row.status,
        status_label=model_service.STATUS_LABELS.get(row.status, row.status),
        change_note=row.change_note,
        change_request_id=row.change_request_id,
        created_by_name=row.created_by_name,
        created_at=row.created_at,
        reviewed_by_name=row.reviewed_by_name,
        reviewed_at=row.reviewed_at,
        published_by_name=row.published_by_name,
        published_at=row.published_at,
        node_count=len(snapshot.get("nodes") or []),
        edge_count=len(snapshot.get("edges") or []),
    )


def _version_detail(row: ProcessModelVersion) -> ProcessModelVersionDetail:
    nodes, edges = model_service.rows_from_snapshot(row.process_id, row.snapshot or {})
    return ProcessModelVersionDetail(
        **_version_out(row).model_dump(),
        nodes=[ProcessNodeOut.model_validate(node) for node in nodes],
        edges=[ProcessEdgeOut.model_validate(edge) for edge in edges],
    )


def _load_model(db: DbSession, process_id: int) -> ProcessModelOut:
    process = db.get(ProcessArch, process_id)
    latest = model_service.latest_version(db, process_id)
    nodes, edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    if latest is not None:
        model_status = latest.status
    elif nodes:
        model_status = model_service.PUBLISHED
    else:
        model_status = None
    return ProcessModelOut(
        process_id=process_id,
        process_name=process.name if process else None,
        version=process.model_version if process else 0,
        draft_version=(
            latest.version
            if latest is not None
            else (
                (process.published_model_version or process.model_version)
                if process and nodes
                else 0
            )
        ),
        status=model_status,
        status_label=(
            model_service.STATUS_LABELS.get(model_status, model_status) if model_status else None
        ),
        version_id=latest.id if latest else None,
        published_version=(
            process.published_model_version
            or (process.model_version if nodes and latest is None else 0)
        )
        if process
        else 0,
        updated_at=process.model_updated_at if process else None,
        requires_change_request=bool(process and process.requires_change_request),
        nodes=[ProcessNodeOut.model_validate(n) for n in nodes],
        edges=[ProcessEdgeOut.model_validate(e) for e in edges],
    )


@router.get(
    "/processes/{process_id}/design", response_model=ProcessModelOut, summary="读取流程模型"
)
def get_design(process_id: int, db: DbSession):
    if db.get(ProcessArch, process_id) is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return _load_model(db, process_id)


@router.put(
    "/processes/{process_id}/design", response_model=ProcessModelOut, summary="覆盖式保存流程模型"
)
def save_design(process_id: int, payload: ProcessModelIn, db: DbSession, user: WriteUser):
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)

    # 乐观并发控制：客户端提交它看到的版本号，不一致就拒绝
    if payload.expected_version is not None and payload.expected_version != process.model_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"流程模型已被他人修改（服务端 v{process.model_version}，"
                f"你提交的是 v{payload.expected_version}）。请刷新后重新编辑。"
            ),
        )

    keys = [n.node_key for n in payload.nodes]
    if len(keys) != len(set(keys)):
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        raise HTTPException(status_code=400, detail=f"node_key 重复：{', '.join(duplicates)}")

    known = set(keys)
    dangling = [e for e in payload.edges if e.source_key not in known or e.target_key not in known]
    if dangling:
        bad = ", ".join(f"{e.source_key}→{e.target_key}" for e in dangling[:3])
        raise HTTPException(status_code=400, detail=f"连线引用了不存在的节点：{bad}")

    validation = designer.validate_model(payload.nodes, payload.edges)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail="；".join(validation["errors"]))

    version = model_service.save_draft(db, process, payload, user)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"保存流程模型草稿 {process.code}：{len(payload.nodes)} 节点 / "
        f"{len(payload.edges)} 连线（v{version.version}）",
    )
    db.commit()

    return _load_model(db, process_id)


@router.patch(
    "/processes/{process_id}/design/nodes/{node_key}",
    response_model=ProcessModelOut,
    summary="更新草稿节点指标（不改变 BPMN 图形）",
)
def update_node_metrics(
    process_id: int,
    node_key: str,
    payload: ProcessNodeMetricsUpdate,
    db: DbSession,
    user: WriteUser,
):
    process = _require_process(db, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    if payload.expected_version is not None and payload.expected_version != process.model_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"流程模型已被他人修改（服务端 v{process.model_version}，"
                f"你提交的是 v{payload.expected_version}）。请刷新后重试。"
            ),
        )
    snapshot = copy.deepcopy(model_service.current_snapshot(db, process_id))
    nodes = snapshot.get("nodes") or []
    target = next((node for node in nodes if node.get("node_key") == node_key), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_key} 不存在")
    updates = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if updates.get("process_arch_id") is not None:
        activity = db.get(ProcessArch, updates["process_arch_id"])
        if activity is None or activity.level != 4 or activity.parent_id != process_id:
            raise HTTPException(
                status_code=400,
                detail="process_arch_id 必须是该流程下的 L4 活动",
            )
    if updates.get("owner_position_id") is not None:
        if db.get(Position, updates["owner_position_id"]) is None:
            raise HTTPException(status_code=400, detail="负责人岗位不存在")
    target.update(updates)

    model_payload = ProcessModelIn(
        nodes=nodes,
        edges=snapshot.get("edges") or [],
        expected_version=payload.expected_version,
    )
    validation = designer.validate_model(model_payload.nodes, model_payload.edges)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail="；".join(validation["errors"]))
    version = model_service.save_draft(
        db, process, model_payload, user, note="更新节点属性", keep_bpmn=True
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"更新节点属性 {process.code}/{node_key}（v{version.version}）",
    )
    db.commit()
    return _load_model(db, process_id)


@router.get(
    "/processes/{process_id}/bpmn",
    summary="导出 BPMN 2.0",
    response_class=Response,
)
def export_bpmn(process_id: int, db: DbSession):
    process = _require_process(db, process_id)
    snapshot = model_service.current_snapshot(db, process_id)
    latest = model_service.latest_version(db, process_id)
    if latest is not None and latest.bpmn_xml:
        try:
            xml = bpmn_service.sync_pms_extensions(latest.bpmn_xml, snapshot.get("nodes") or [])
        except HTTPException as exc:
            nodes, edges = model_service.rows_from_snapshot(process_id, snapshot)
            if not nodes:
                raise HTTPException(
                    status_code=400, detail="流程还没有建模，无法导出 BPMN"
                ) from exc
            xml = bpmn_service.export_bpmn(process, list(nodes), list(edges))
    else:
        nodes, edges = model_service.rows_from_snapshot(process_id, snapshot)
        if not nodes:
            raise HTTPException(status_code=400, detail="流程还没有建模，无法导出 BPMN")
        xml = bpmn_service.export_bpmn(process, list(nodes), list(edges))
    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{process.code}.bpmn"',
        },
    )


@router.post(
    "/processes/{process_id}/bpmn",
    response_model=ProcessModelOut,
    summary="导入 BPMN 2.0（替换设计模型）",
)
def import_bpmn(process_id: int, payload: BpmnImportRequest, db: DbSession, user: WriteUser):
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    if payload.expected_version is not None and payload.expected_version != process.model_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"流程模型已被他人修改（服务端 v{process.model_version}，"
                f"你提交的是 v{payload.expected_version}）。请刷新后重新导入。"
            ),
        )

    parsed = bpmn_service.import_bpmn(payload.xml)
    # bpmn-js 等外部编辑器不认识 PMS 的测算扩展时，可能把 pms:* 丢掉；
    # 对同 id 的节点/同起止的连线，用当前草稿里的 PMS 字段兜底，避免一次保存把指标清零。
    previous = model_service.current_snapshot(db, process_id)
    old_nodes = {node["node_key"]: node for node in previous.get("nodes") or []}
    old_edges = {
        (edge["source_key"], edge["target_key"]): edge for edge in previous.get("edges") or []
    }
    for node in parsed["nodes"]:
        old = old_nodes.get(node["node_key"])
        if not old:
            continue
        for field in (
            "duration_minutes",
            "wait_minutes",
            "cost",
            "rework_rate",
            "approval_levels",
            "is_value_added",
        ):
            node[field] = old.get(field, node[field])
        # 负责人/活动 ID 以快照为准：新属性栏通过 PATCH 写快照，画布里的旧
        # pms:ownerRole / 无活动扩展可能还没同步，不能反过来覆盖刚保存的值。
        if old:
            node["owner_role"] = old.get("owner_role")
            node["process_arch_id"] = old.get("process_arch_id")
            node["owner_position_id"] = old.get("owner_position_id")
    for edge in parsed["edges"]:
        explicit = edge.pop("_probability_explicit", False)
        old = old_edges.get((edge["source_key"], edge["target_key"]))
        if old and not explicit:
            edge["probability"] = old.get("probability", 1.0)

    model_payload = ProcessModelIn(
        nodes=parsed["nodes"], edges=parsed["edges"], expected_version=payload.expected_version
    )
    validation = designer.validate_model(model_payload.nodes, model_payload.edges)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail="；".join(validation["errors"]))

    version = model_service.save_draft(
        db,
        process,
        model_payload,
        user,
        note="BPMN 导入",
        bpmn_xml=payload.xml,
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"导入 BPMN 草稿 {process.code}：{len(parsed['nodes'])} 节点 / "
        f"{len(parsed['edges'])} 连线（v{version.version}）",
    )
    db.commit()
    return _load_model(db, process_id)


@router.post(
    "/processes/{process_id}/design/analyze",
    response_model=DesignAnalysis,
    summary="测算已保存的流程模型",
)
def analyze_saved(process_id: int, db: DbSession):
    if db.get(ProcessArch, process_id) is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    nodes, edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    return designer.analyze(process_id, nodes, edges)


@router.post(
    "/processes/{process_id}/design/validate",
    response_model=DesignValidation,
    summary="校验已保存的流程模型",
)
def validate_saved(process_id: int, db: DbSession):
    if db.get(ProcessArch, process_id) is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    nodes, edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    return designer.validate_model(nodes, edges)


def _require_process(db: DbSession, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return process


def _require_version(db: DbSession, process_id: int, version_id: int) -> ProcessModelVersion:
    row = db.get(ProcessModelVersion, version_id)
    if row is None or row.process_id != process_id:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    return row


@router.get(
    "/processes/{process_id}/design/versions",
    response_model=List[ProcessModelVersionOut],
    summary="模型版本历史",
)
def list_model_versions(process_id: int, db: DbSession, user: CurrentUser):
    _require_process(db, process_id)
    rows = db.scalars(
        select(ProcessModelVersion)
        .where(ProcessModelVersion.process_id == process_id)
        .order_by(ProcessModelVersion.version.desc())
    ).all()
    return [_version_out(row) for row in rows]


@router.get(
    "/processes/{process_id}/design/versions/{version_id}",
    response_model=ProcessModelVersionDetail,
    summary="模型版本详情",
)
def get_model_version(process_id: int, version_id: int, db: DbSession, user: CurrentUser):
    _require_process(db, process_id)
    return _version_detail(_require_version(db, process_id, version_id))


@router.post(
    "/processes/{process_id}/design/submit-review",
    response_model=ProcessModelVersionOut,
    summary="提交模型评审（Owner/Manager）",
)
def submit_model_review(
    process_id: int,
    payload: ReviewModelRequest,
    db: DbSession,
    user: WriteUser,
):
    process = _require_process(db, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    row = model_service.submit_review(db, process, user, payload.note)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"提交流程模型评审 {process.code}（v{row.version}）",
    )
    db.commit()
    return _version_out(row)


@router.post(
    "/processes/{process_id}/design/reject",
    response_model=ProcessModelVersionOut,
    summary="驳回模型评审（MANAGER+）",
)
def reject_model_review(
    process_id: int,
    payload: ReviewModelRequest,
    db: DbSession,
    user: ManagerUser,
):
    process = _require_process(db, process_id)
    row = model_service.reject_review(db, process, user, payload.note)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"驳回流程模型评审 {process.code}（v{row.version}）",
    )
    db.commit()
    return _version_out(row)


@router.post(
    "/processes/{process_id}/design/publish",
    response_model=ProcessModelOut,
    summary="发布模型到运行时（MANAGER+）",
)
def publish_model(
    process_id: int,
    payload: PublishModelRequest,
    db: DbSession,
    user: ManagerUser,
):
    process = _require_process(db, process_id)
    if payload.expected_version is not None and payload.expected_version != process.model_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"流程模型已被他人修改（服务端 v{process.model_version}，"
                f"你提交的是 v{payload.expected_version}）。请刷新后再发布。"
            ),
        )
    change_row = None
    if payload.change_request_id is not None:
        try:
            change_row = change_service.require_approved(db, process_id, payload.change_request_id)
        except change_service.ChangeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif process.requires_change_request:
        raise HTTPException(
            status_code=409,
            detail=("该流程启用了变更门禁：请先在「变更」页创建并批准变更申请，再带着变更单发布"),
        )
    row = model_service.publish(db, process, user, note=payload.change_note)
    if change_row is not None:
        row.change_request_id = change_row.id
        change_service.mark_applied(db, change_row)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"发布流程模型 {process.code}（v{row.version}）到运行时"
        + (f"，变更单 {change_row.code}" if change_row else ""),
    )
    db.commit()
    return _load_model(db, process_id)


@router.post(
    "/processes/{process_id}/design/versions/{version_id}/rollback",
    response_model=ProcessModelOut,
    summary="从历史版本创建草稿（Owner/Manager）",
)
def rollback_model(
    process_id: int,
    version_id: int,
    payload: RollbackModelRequest,
    db: DbSession,
    user: WriteUser,
):
    process = _require_process(db, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    source = _require_version(db, process_id, version_id)
    row = model_service.rollback(db, process, source, user, payload.note)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"回滚流程模型 {process.code}：v{source.version} → 新草稿 v{row.version}",
    )
    db.commit()
    return _load_model(db, process_id)


@router.post(
    "/processes/{process_id}/design/versions/{version_id}/publish-rollback",
    response_model=ProcessModelOut,
    summary="回滚到历史版本并立即发布（Manager）",
)
def publish_rollback(
    process_id: int,
    version_id: int,
    payload: RollbackModelRequest,
    db: DbSession,
    user: ManagerUser,
):
    process = _require_process(db, process_id)
    change_row = None
    if process.requires_change_request:
        change_row = change_service.latest_approved_request(db, process_id)
        if change_row is None:
            raise HTTPException(
                status_code=409,
                detail="该流程启用了变更门禁：回滚发布也必须先有一张已批准的变更申请",
            )
    source = _require_version(db, process_id, version_id)
    row = model_service.rollback(
        db, process, source, user, payload.note or f"回滚并发布自 v{source.version}"
    )
    row = model_service.publish(db, process, user, row.id, note=row.change_note)
    if change_row is not None:
        row.change_request_id = change_row.id
        change_service.mark_applied(db, change_row)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"回滚并发布流程模型 {process.code}：v{source.version} → v{row.version}",
    )
    db.commit()
    return _load_model(db, process_id)


@router.get(
    "/processes/{process_id}/design/diff",
    response_model=ProcessModelDiffOut,
    summary="比较两个模型版本",
)
def diff_model_versions(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    from_version_id: int = Query(..., description="基准版本 id"),
    to_version_id: int = Query(..., description="目标版本 id"),
):
    _require_process(db, process_id)
    before = _require_version(db, process_id, from_version_id)
    after = _require_version(db, process_id, to_version_id)
    result = model_service.diff_snapshots(before.snapshot or {}, after.snapshot or {})
    return ProcessModelDiffOut(
        from_version=before.version,
        to_version=after.version,
        **result,
    )


@router.post(
    "/processes/{process_id}/design/simulate",
    response_model=SimulationOut,
    summary="按当前模型枚举路径并汇总概率/周期/成本",
)
def simulate_design(process_id: int, payload: SimulationRequest, db: DbSession):
    if db.get(ProcessArch, process_id) is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    nodes, edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    try:
        return simulation_service.simulate(
            nodes, edges, start_node_key=payload.start_node_key, max_paths=payload.max_paths
        )
    except simulation_service.SimulationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/design/validate",
    response_model=DesignValidation,
    summary="校验前端提交的模型（不落库）",
)
def validate_inline(payload: ProcessModelIn):
    return designer.validate_model(payload.nodes, payload.edges)


@router.post(
    "/design/analyze",
    response_model=DesignAnalysis,
    status_code=status.HTTP_200_OK,
    summary="边改边算：不落库直接测算前端提交的模型",
)
def analyze_inline(payload: ProcessModelIn):
    nodes: List[ProcessNode] = []
    for idx, n in enumerate(payload.nodes):
        node = ProcessNode(**n.model_dump(mode="json"))
        node.id = idx + 1
        if not node.sequence_order:
            node.sequence_order = idx + 1
        nodes.append(node)
    edges = [ProcessEdge(**e.model_dump(mode="json")) for e in payload.edges]
    return designer.analyze(0, nodes, edges)


# ---------------------------------------------------------------- 活动级工具绑定

TOOL_LEVEL_LABELS = {
    ToolLevel.REQUIRED.value: "必需",
    ToolLevel.RECOMMENDED.value: "推荐",
    ToolLevel.OPTIONAL.value: "可选",
}


def _require_design_node(db: DbSession, process_id: int, node_key: str):
    process = _require_process(db, process_id)
    nodes, _edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    if not any(node.node_key == node_key for node in nodes):
        raise HTTPException(status_code=404, detail=f"节点 {node_key} 不存在于该流程")
    return process


def _node_tool_out(row: NodeTool) -> NodeToolOut:
    return NodeToolOut(
        id=row.id,
        process_id=row.process_id,
        node_key=row.node_key,
        tool_code=row.tool_code,
        tool_name=row.tool_name,
        level=row.level,
        level_label=TOOL_LEVEL_LABELS.get(row.level, row.level),
        note=row.note,
    )


@router.get(
    "/processes/{process_id}/design/nodes/{node_key}/tools",
    response_model=List[NodeToolOut],
    summary="节点推荐工具绑定",
)
def list_node_tools(process_id: int, node_key: str, db: DbSession, user: CurrentUser):
    _require_design_node(db, process_id, node_key)
    rows = db.scalars(
        select(NodeTool)
        .options(joinedload(NodeTool.tool))
        .where(NodeTool.process_id == process_id, NodeTool.node_key == node_key)
        .order_by(NodeTool.id)
    ).all()
    return [_node_tool_out(row) for row in rows]


@router.post(
    "/processes/{process_id}/design/nodes/{node_key}/tools",
    response_model=NodeToolOut,
    status_code=status.HTTP_201_CREATED,
    summary="为节点绑定工具（Owner/Manager）",
)
def add_node_tool(
    process_id: int,
    node_key: str,
    payload: NodeToolCreate,
    db: DbSession,
    user: WriteUser,
):
    process = _require_design_node(db, process_id, node_key)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    tool = db.scalar(select(Tool).where(Tool.code == payload.tool_code))
    if tool is None:
        raise HTTPException(status_code=400, detail=f"工具 {payload.tool_code} 不存在")
    existing = db.scalar(
        select(NodeTool).where(
            NodeTool.process_id == process_id,
            NodeTool.node_key == node_key,
            NodeTool.tool_code == payload.tool_code,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该工具已经绑定到这个节点")
    row = NodeTool(
        process_id=process_id,
        node_key=node_key,
        tool_code=payload.tool_code,
        level=payload.level.value,
        note=payload.note,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "node_tool",
        row.id,
        f"节点工具绑定 {process.code}/{node_key} → {payload.tool_code}（{payload.level.value}）",
    )
    db.commit()
    db.refresh(row)
    return _node_tool_out(row)


@router.delete(
    "/processes/{process_id}/design/nodes/{node_key}/tools/{tool_code}",
    response_model=DeleteResult,
    summary="解除节点工具绑定（Owner/Manager）",
)
def delete_node_tool(
    process_id: int,
    node_key: str,
    tool_code: str,
    db: DbSession,
    user: WriteUser,
):
    process = _require_design_node(db, process_id, node_key)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    row = db.scalar(
        select(NodeTool).where(
            NodeTool.process_id == process_id,
            NodeTool.node_key == node_key,
            NodeTool.tool_code == tool_code,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="该节点没有绑定这个工具")
    db.delete(row)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "node_tool",
        None,
        f"解除节点工具绑定 {process.code}/{node_key} → {tool_code}",
    )
    db.commit()
    return DeleteResult(deleted=1)
