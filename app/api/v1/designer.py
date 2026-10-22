"""流程设计器：泳道建模、指标测算、改善建议。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    ensure_can_edit_owned,
)
from app.models.process import ProcessArch, ProcessEdge, ProcessModelVersion, ProcessNode
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
    ProcessNodeOut,
    PublishModelRequest,
    ReviewModelRequest,
    RollbackModelRequest,
)
from app.services import audit as audit_service
from app.services import bpmn as bpmn_service
from app.services import designer
from app.services import process_model as model_service

router = APIRouter(tags=["流程设计器"])


def _version_out(row: ProcessModelVersion) -> ProcessModelVersionOut:
    snapshot = row.snapshot or {}
    return ProcessModelVersionOut(
        id=row.id,
        version=row.version,
        status=row.status,
        status_label=model_service.STATUS_LABELS.get(row.status, row.status),
        change_note=row.change_note,
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


@router.get(
    "/processes/{process_id}/bpmn",
    summary="导出 BPMN 2.0",
    response_class=Response,
)
def export_bpmn(process_id: int, db: DbSession):
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    nodes, edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
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
    model_payload = ProcessModelIn(
        nodes=parsed["nodes"], edges=parsed["edges"], expected_version=payload.expected_version
    )
    validation = designer.validate_model(model_payload.nodes, model_payload.edges)
    if validation["errors"]:
        raise HTTPException(status_code=400, detail="；".join(validation["errors"]))

    version = model_service.save_draft(db, process, model_payload, user, note="BPMN 导入")
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
    row = model_service.publish(db, process, user, note=payload.change_note)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"发布流程模型 {process.code}（v{row.version}）到运行时",
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
