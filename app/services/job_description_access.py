"""固定岗位产物的来源访问凭据：原范围与当前范围都需可见。"""

from fastapi import HTTPException
from sqlalchemy import select

from app.models.org import Position
from app.models.process_document import ProcessDocument
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.services import org_access
from app.services.process_document import visible_conditions

MODELS = {
    "POSITION": Position,
    "ROLE": GovernanceRole,
    "WORK_STANDARD": WorkMeasurementStandard,
    "CAPACITY": CapacityCalendar,
    "DOCUMENT": ProcessDocument,
}


def capture(db, coverage, bindings):
    refs = {("POSITION", coverage.position_id)}
    refs.update(("WORK_STANDARD", r.standard_id) for r in coverage.workload.standards)
    refs.update(("CAPACITY", r.capacity_id) for r in coverage.workload.capacity)
    for data in bindings:
        for activity in data["activities"]:
            for facet in activity["facets"]:
                for ref in facet["refs"]:
                    kind, ident = ref["kind"], ref.get("id")
                    if kind == "RACI" and ident:
                        row = db.get(RaciAssignment, ident)
                        if row:
                            refs.add(("ROLE", row.role_id))
                    elif kind in MODELS and ident:
                        refs.add((kind, ident))
    for activity in coverage.activities:
        refs.update(("ROLE", r.role_id) for r in activity.raci)
    guards = []
    for kind, ident in sorted(refs):
        row = db.get(MODELS[kind], ident)
        if row is None:
            continue
        guards.append(
            {
                "kind": kind,
                "id": ident,
                "org_unit_id": row.org_unit_id,
                "variation_policy": getattr(row, "variation_policy", None),
            }
        )
    return guards


def ensure_manifest_visible(db, user, manifest):
    if org_access.unrestricted(user):
        return
    guards = manifest.get("source_scopes")
    if guards is None:
        raise HTTPException(404, "原固定来源范围未核对")
    for guard in guards:
        model = MODELS.get(guard["kind"])
        row = db.get(model, guard["id"]) if model else None
        if row is None:
            raise HTTPException(404, "原固定来源不可见")
        if guard["kind"] == "DOCUMENT":
            from app.services.org_scope import ancestor_ids

            allowed = ancestor_ids(db, user.org_unit_id)
            original_org = guard["org_unit_id"]
            if original_org is not None and original_org not in allowed:
                raise HTTPException(404, "原文档范围不可见")
            if guard.get("variation_policy") == "LOCAL_ONLY" and original_org != user.org_unit_id:
                raise HTTPException(404, "原本地文档不可见")
            condition = visible_conditions(db, user.org_unit_id)
            stmt = select(ProcessDocument.id).where(ProcessDocument.id == row.id)
            stmt = (
                stmt.where(condition)
                if condition is not None
                else stmt.where(ProcessDocument.org_unit_id.is_(None))
            )
            if db.scalar(stmt) is None:
                raise HTTPException(404, "原文档不可见")
        else:
            org_access.ensure_visible(db, user, guard["org_unit_id"])
            org_access.ensure_visible(db, user, row.org_unit_id)
