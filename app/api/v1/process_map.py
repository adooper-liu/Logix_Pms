"""流程地图：L1–L4 架构树、流程清单、热力图。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, ManagerUser
from app.models.knowledge import KnowledgeItem
from app.models.monitor import ExceptionEvent, KpiDefinition
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.project import Project
from app.schemas.common import DeleteResult
from app.schemas.process import (
    HeatmapItem,
    ProcessArchCreate,
    ProcessArchOut,
    ProcessArchTree,
    ProcessArchUpdate,
)
from app.services import audit as audit_service

router = APIRouter(prefix="/process-map", tags=["流程地图"])

# 热度阈值。综合得分 = 战略重要性 × 痛点严重度 × 改善空间，取值区间 0–125，
# 所以阈值要按这个量级定，否则会出现「全是紧急」——那就等于没有区分度。
HEAT_CRITICAL = 80.0
HEAT_HIGH = 55.0
HEAT_MEDIUM = 30.0
HEALTH_CRITICAL = 50.0  # 健康度低于此值直接判紧急
HEALTH_POOR = 65.0  # 低于此值至少判「高」


def _heat_level(p: ProcessArch) -> str:
    health = p.health_score
    if p.priority_score >= HEAT_CRITICAL or (health is not None and health < HEALTH_CRITICAL):
        return "CRITICAL"
    if p.priority_score >= HEAT_HIGH or (health is not None and health < HEALTH_POOR):
        return "HIGH"
    if p.priority_score >= HEAT_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _to_out(p: ProcessArch) -> ProcessArchOut:
    return ProcessArchOut(
        id=p.id,
        code=p.code,
        name=p.name,
        level=p.level,
        parent_id=p.parent_id,
        owner=p.owner,
        department=p.department,
        description=p.description,
        strategic_importance=p.strategic_importance,
        pain_score=p.pain_score,
        improvement_space=p.improvement_space,
        health_score=p.health_score,
        is_improvement_target=p.is_improvement_target,
        priority_score=p.priority_score,
        heat_level=_heat_level(p),
    )


@router.get("/tree", response_model=List[ProcessArchTree], summary="流程架构树（L1→L4 逐级下钻）")
def get_tree(
    db: DbSession,
    root_code: Optional[str] = Query(
        default=None, description="从某个 L1 编码开始，不传则返回全部顶层"
    ),
    max_level: int = Query(default=4, ge=1, le=4),
    improvement_only: bool = Query(default=False, description="只看待改善的流程"),
):
    rows = db.scalars(select(ProcessArch).order_by(ProcessArch.code)).all()
    if improvement_only:
        rows = [r for r in rows if r.is_improvement_target]
    by_parent: dict = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)

    def build(node: ProcessArch) -> ProcessArchTree:
        children: List[ProcessArchTree] = []
        if node.level < max_level:
            children = [build(c) for c in by_parent.get(node.id, [])]
        base = _to_out(node)
        return ProcessArchTree(**base.model_dump(), children=children)

    if root_code:
        roots = [r for r in rows if r.code == root_code]
        if not roots:
            raise HTTPException(status_code=404, detail=f"未找到编码为 {root_code} 的流程")
    else:
        top_ids = {r.id for r in rows}
        roots = [r for r in rows if r.parent_id is None or r.parent_id not in top_ids]
    return [build(r) for r in roots]


@router.get("/flat", response_model=List[ProcessArchOut], summary="流程清单（扁平）")
def list_processes(
    db: DbSession,
    level: Optional[int] = Query(default=None, ge=1, le=4),
    parent_id: Optional[int] = None,
    keyword: Optional[str] = None,
    improvement_only: bool = False,
):
    stmt = select(ProcessArch)
    if level is not None:
        stmt = stmt.where(ProcessArch.level == level)
    if parent_id is not None:
        stmt = stmt.where(ProcessArch.parent_id == parent_id)
    if improvement_only:
        stmt = stmt.where(ProcessArch.is_improvement_target.is_(True))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                ProcessArch.name.like(like),
                ProcessArch.code.like(like),
                ProcessArch.owner.like(like),
            )
        )
    rows = db.scalars(stmt.order_by(ProcessArch.code)).all()
    return [_to_out(r) for r in rows]


@router.get("/heatmap", response_model=List[HeatmapItem], summary="改善优先级热力图")
def heatmap(
    db: DbSession,
    level: int = Query(default=3, ge=1, le=4, description="默认看 L3 流程层"),
    limit: int = Query(default=20, ge=1, le=100),
):
    rows = db.scalars(select(ProcessArch).where(ProcessArch.level == level)).all()
    project_counts = dict(
        db.execute(
            select(Project.process_id, func.count(Project.id))
            .where(Project.process_id.is_not(None))
            .group_by(Project.process_id)
        ).all()
    )
    items = [
        HeatmapItem(
            id=p.id,
            code=p.code,
            name=p.name,
            level=p.level,
            owner=p.owner,
            health_score=p.health_score,
            pain_score=p.pain_score,
            strategic_importance=p.strategic_importance,
            improvement_space=p.improvement_space,
            priority_score=p.priority_score,
            project_count=project_counts.get(p.id, 0),
            heat_level=_heat_level(p),
        )
        for p in rows
    ]
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items.sort(key=lambda i: (rank[i.heat_level], -i.priority_score))
    return items[:limit]


@router.get("/{process_id}", response_model=ProcessArchOut, summary="流程详情")
def get_process(process_id: int, db: DbSession):
    p = db.get(ProcessArch, process_id)
    if p is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return _to_out(p)


@router.post(
    "", response_model=ProcessArchOut, status_code=status.HTTP_201_CREATED, summary="新增流程节点"
)
def create_process(payload: ProcessArchCreate, db: DbSession, user: ManagerUser):
    if db.scalar(select(ProcessArch).where(ProcessArch.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"流程编码 {payload.code} 已存在")
    if payload.parent_id is not None and db.get(ProcessArch, payload.parent_id) is None:
        raise HTTPException(status_code=400, detail="parent_id 指向的流程不存在")
    obj = ProcessArch(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit_service.record(db, user, "CREATE", "process", obj.id, f"新增流程 {obj.code} {obj.name}")
    db.commit()
    db.refresh(obj)
    return _to_out(obj)


@router.patch("/{process_id}", response_model=ProcessArchOut, summary="更新流程节点")
def update_process(process_id: int, payload: ProcessArchUpdate, db: DbSession, user: ManagerUser):
    obj = db.get(ProcessArch, process_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    changed = list(payload.model_dump(exclude_unset=True).keys())
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process",
        obj.id,
        f"更新流程 {obj.code} 的 {', '.join(changed) if changed else '（无变更）'}",
    )
    db.commit()
    db.refresh(obj)
    return _to_out(obj)


@router.delete("/{process_id}", response_model=DeleteResult, summary="删除流程节点（含下级）")
def delete_process(process_id: int, db: DbSession, user: ManagerUser):
    obj = db.get(ProcessArch, process_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    code, name = obj.code, obj.name

    # 收集自己和全部下级流程的 id
    rows = db.scalars(select(ProcessArch)).all()
    by_parent: dict = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    ids = []
    stack = [obj]
    while stack:
        current = stack.pop()
        ids.append(current.id)
        stack.extend(by_parent.get(current.id, []))

    # 显式清理依赖数据。不能指望数据库级联：SQLite 默认不强制外键，
    # 而 SQLAlchemy 的 ORM 级联只覆盖有 relationship 的对象（这里没有）。
    # 否则会留下孤儿节点——一旦新流程复用了同一个 id，就会「继承」别人的模型。
    db.query(ProcessNode).filter(ProcessNode.process_id.in_(ids)).delete(synchronize_session=False)
    db.query(ProcessEdge).filter(ProcessEdge.process_id.in_(ids)).delete(synchronize_session=False)
    # 下级流程本体交给 ORM 的 children 级联删除，避免和已加载的会话对象打架

    # 引用型数据置空，而不是跟着删掉
    db.query(KpiDefinition).filter(KpiDefinition.process_id.in_(ids)).update(
        {KpiDefinition.process_id: None}, synchronize_session=False
    )
    db.query(ExceptionEvent).filter(ExceptionEvent.process_id.in_(ids)).update(
        {ExceptionEvent.process_id: None}, synchronize_session=False
    )
    db.query(KnowledgeItem).filter(KnowledgeItem.process_id.in_(ids)).update(
        {KnowledgeItem.process_id: None}, synchronize_session=False
    )

    audit_service.record(
        db, user, "DELETE", "process", process_id, f"删除流程 {code} {name}（含下级）"
    )
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=len(ids))
