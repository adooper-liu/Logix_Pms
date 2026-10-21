"""对标框架：框架清单、标准分类树、覆盖率与流程映射。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, ManagerUser
from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, ProcessBenchmarkMap
from app.models.process import ProcessArch
from app.schemas.benchmark import (
    BenchmarkCategoryOut,
    BenchmarkFrameworkOut,
    BenchmarkMappingCreate,
    BenchmarkMappingOut,
    FrameworkCoverageOut,
    ProcessBenchmarkOut,
)
from app.schemas.common import DeleteResult
from app.services import audit as audit_service
from app.services import benchmark as benchmark_service

router = APIRouter(prefix="/benchmark", tags=["对标框架"])


def _get_framework(db: DbSession, code: str) -> BenchmarkFramework:
    framework = db.scalar(select(BenchmarkFramework).where(BenchmarkFramework.code == code))
    if framework is None:
        raise HTTPException(status_code=404, detail=f"对标框架 {code} 不存在")
    return framework


@router.get("/frameworks", response_model=List[BenchmarkFrameworkOut], summary="对标框架清单")
def list_frameworks(db: DbSession):
    return benchmark_service.framework_catalog(db)


@router.get(
    "/frameworks/{code}/tree",
    response_model=List[BenchmarkCategoryOut],
    summary="标准分类树（SCOR / APQC PCF）",
)
def get_category_tree(
    code: str,
    db: DbSession,
    max_level: int = Query(default=4, ge=1, le=5),
):
    framework = _get_framework(db, code)
    return benchmark_service.category_tree(db, framework, max_level=max_level)


@router.get(
    "/frameworks/{code}/coverage",
    response_model=FrameworkCoverageOut,
    summary="对标覆盖率：公司某层流程在各标准分类下的分布",
)
def get_coverage(
    code: str,
    db: DbSession,
    process_level: int = Query(default=3, ge=1, le=4, description="被统计的公司流程层级"),
):
    framework = _get_framework(db, code)
    return benchmark_service.coverage(db, framework, process_level=process_level)


@router.get(
    "/processes/{process_id}/mappings",
    response_model=ProcessBenchmarkOut,
    summary="单个流程在所有框架下的对标映射",
)
def get_process_mappings(process_id: int, db: DbSession):
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return benchmark_service.process_mappings(db, process)


@router.post(
    "/mappings",
    response_model=BenchmarkMappingOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增流程 → 标准分类映射",
)
def create_mapping(payload: BenchmarkMappingCreate, db: DbSession, user: ManagerUser):
    process = db.get(ProcessArch, payload.process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    category = db.get(BenchmarkCategory, payload.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="标准分类不存在")
    framework = db.get(BenchmarkFramework, category.framework_id)
    if framework is None:
        raise HTTPException(status_code=404, detail="标准分类所属框架不存在")

    existing = db.scalar(
        select(ProcessBenchmarkMap).where(
            ProcessBenchmarkMap.process_id == payload.process_id,
            ProcessBenchmarkMap.category_id == payload.category_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该流程已映射到此标准分类")

    obj = ProcessBenchmarkMap(
        process_id=payload.process_id,
        category_id=payload.category_id,
        note=payload.note,
    )
    db.add(obj)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "benchmark_mapping",
        obj.id,
        f"{process.code} {process.name} → {framework.code} {category.code} {category.name}",
    )
    db.commit()
    db.refresh(obj)
    return benchmark_service.mapping_out(obj, process, category, framework)


@router.delete(
    "/mappings/{mapping_id}",
    response_model=DeleteResult,
    summary="删除流程 → 标准分类映射",
)
def delete_mapping(mapping_id: int, db: DbSession, user: ManagerUser):
    obj = db.get(ProcessBenchmarkMap, mapping_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="映射不存在")
    process = db.get(ProcessArch, obj.process_id)
    category = db.get(BenchmarkCategory, obj.category_id)
    framework = db.get(BenchmarkFramework, category.framework_id) if category else None

    summary = (
        f"{process.code} {process.name} → {framework.code} {category.code} {category.name}"
        if process and category and framework
        else f"映射 #{mapping_id}"
    )
    audit_service.record(db, user, "DELETE", "benchmark_mapping", obj.id, summary)
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=1)
