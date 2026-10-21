"""流程设计器：泳道建模、指标测算、改善建议。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, WriteUser, ensure_can_edit_owned
from app.core.timeutil import utcnow
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.schemas.process import (
    DesignAnalysis,
    ProcessEdgeOut,
    ProcessModelIn,
    ProcessModelOut,
    ProcessNodeOut,
)
from app.services import audit as audit_service
from app.services import designer

router = APIRouter(tags=["流程设计器"])


def _load_model(db: DbSession, process_id: int) -> ProcessModelOut:
    process = db.get(ProcessArch, process_id)
    nodes = db.scalars(
        select(ProcessNode)
        .where(ProcessNode.process_id == process_id)
        .order_by(ProcessNode.sequence_order)
    ).all()
    edges = db.scalars(select(ProcessEdge).where(ProcessEdge.process_id == process_id)).all()
    return ProcessModelOut(
        process_id=process_id,
        process_name=process.name if process else None,
        version=process.model_version if process else 0,
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

    # 覆盖式保存：先清空再插入，前端一次提交整张图
    for node in db.scalars(select(ProcessNode).where(ProcessNode.process_id == process_id)).all():
        db.delete(node)
    for edge in db.scalars(select(ProcessEdge).where(ProcessEdge.process_id == process_id)).all():
        db.delete(edge)
    db.flush()

    for idx, node in enumerate(payload.nodes):
        db.add(
            ProcessNode(
                process_id=process_id,
                sequence_order=node.sequence_order or idx + 1,
                **node.model_dump(exclude={"sequence_order"}, mode="json"),
            )
        )
    for edge in payload.edges:
        db.add(ProcessEdge(process_id=process_id, **edge.model_dump(mode="json")))
    process.model_version = (process.model_version or 0) + 1
    process.model_updated_at = utcnow()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_design",
        process_id,
        f"保存流程模型 {process.code}：{len(payload.nodes)} 节点 / {len(payload.edges)} 连线"
        f"（v{process.model_version}）",
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
    nodes = db.scalars(select(ProcessNode).where(ProcessNode.process_id == process_id)).all()
    edges = db.scalars(select(ProcessEdge).where(ProcessEdge.process_id == process_id)).all()
    return designer.analyze(process_id, nodes, edges)


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
