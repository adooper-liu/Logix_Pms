"""客户/市场要求与目标承接工作台 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.common import DeleteResult
from app.schemas.requirement import AlignmentOut, RequirementIn, RequirementOut, RequirementUpdate
from app.services import alignment as alignment_service
from app.services import audit as audit_service

router = APIRouter(tags=["目标与承接"])


@router.get("/requirements", response_model=List[RequirementOut], summary="客户/市场要求清单")
def list_requirements(
    db: DbSession,
    user: CurrentUser,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    status_: Optional[str] = Query(default=None, alias="status"),
):
    return alignment_service.list_requirements(db, year=year, status=status_)


@router.post(
    "/requirements",
    response_model=RequirementOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记客户/市场要求（Manager）",
)
def create_requirement(payload: RequirementIn, db: DbSession, user: ManagerUser):
    row = alignment_service.create_requirement(db, user, payload)
    audit_service.record(
        db, user, "CREATE", "market_requirement", row.id, f"登记要求 {row.code} {row.title}"
    )
    db.commit()
    return row


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut, summary="修改要求")
def update_requirement(
    requirement_id: int, payload: RequirementUpdate, db: DbSession, user: ManagerUser
):
    from app.models.requirement import MarketRequirement

    row = db.get(MarketRequirement, requirement_id)
    if row is None:
        raise HTTPException(404, "要求不存在")
    result = alignment_service.update_requirement(db, row, payload)
    audit_service.record(
        db, user, "UPDATE", "market_requirement", row.id, f"修改要求 {row.code} {row.title}"
    )
    db.commit()
    return result


@router.delete("/requirements/{requirement_id}", response_model=DeleteResult, summary="删除要求")
def delete_requirement(requirement_id: int, db: DbSession, user: ManagerUser):
    from app.models.requirement import MarketRequirement

    row = db.get(MarketRequirement, requirement_id)
    if row is None:
        raise HTTPException(404, "要求不存在")
    code, title = row.code, row.title
    alignment_service.delete_requirement(db, row)
    audit_service.record(
        db, user, "DELETE", "market_requirement", requirement_id, f"删除要求 {code} {title}"
    )
    db.commit()
    return DeleteResult(deleted=1)


@router.get("/alignment", response_model=AlignmentOut, summary="目标与四路使能承接就绪度")
def get_alignment(
    db: DbSession,
    user: CurrentUser,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
):
    from datetime import date

    return alignment_service.alignment(db, year or date.today().year)
