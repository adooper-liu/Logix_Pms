"""Gate 5 rules on synthetic objects inside the existing pytest test database."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.security import create_token
from app.main import app
from app.models.execution import NodeAssignment
from app.models.org import OrgUnit
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.user import AuditLog, User
from app.services import gate5_readiness as service


@pytest.fixture
def case():
    """API commits release savepoints only; the outer transaction always rolls back."""
    # This fixture is intentionally independent of the seeded client; create only
    # the ORM schema in the pytest-owned temporary SQLite database.
    from app.core.database import Base

    Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        outer = connection.begin()
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN")
        db = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        suffix = uuid4().hex[:8]
        org = OrgUnit(code=f"G5-{suffix}", name="合成组织", type="DEPARTMENT")
        other = OrgUnit(code=f"G5-X-{suffix}", name="其他合成组织", type="DEPARTMENT")
        db.add_all([org, other])
        db.flush()
        org.path, other.path = f"/{org.id}/", f"/{other.id}/"
        child = OrgUnit(
            code=f"G5-C-{suffix}", name="合成子组织", type="DEPARTMENT", parent_id=org.id
        )
        db.add(child)
        db.flush()
        child.path = f"/{org.id}/{child.id}/"

        def user(label, role, unit):
            row = User(
                username=f"g5-{label}-{suffix}",
                display_name=label,
                role=role,
                password_hash="not-a-login",
                org_unit_id=unit.id,
                is_active=True,
            )
            db.add(row)
            db.flush()
            return row

        admin = user("admin", "ADMIN", org)
        owner = user("owner", "OWNER", org)
        outsider = user("other-owner", "OWNER", other)
        executor = user("executor", "VIEWER", child)
        foreign = user("foreign", "VIEWER", other)
        process = ProcessArch(
            code=f"G5-P-{suffix}",
            name="合成流程",
            level=3,
            owner_user_id=owner.id,
            org_unit_id=org.id,
            published_model_version=1,
        )
        activity = ProcessArch(code=f"G5-A-{suffix}", name="合成活动", level=4, parent=process)
        db.add_all([process, activity])
        db.flush()
        version = ProcessModelVersion(
            process_id=process.id,
            version=1,
            status="PUBLISHED",
            snapshot={
                "nodes": [
                    {
                        "node_key": "work",
                        "name": "合成活动",
                        "node_type": "TASK",
                        "process_arch_id": activity.id,
                    }
                ],
                "edges": [],
            },
        )
        role = GovernanceRole(code=f"G5-R-{suffix}", name="合成 A", is_active=True)
        second_role = GovernanceRole(code=f"G5-R2-{suffix}", name="其他 A", is_active=True)
        db.add_all([version, role, second_role])
        db.flush()

        def dependency():
            yield db

        old = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = dependency
        api = TestClient(app)

        def headers(subject):
            return {"Authorization": "Bearer " + create_token(subject.id)[0]}

        data = SimpleNamespace(
            db=db,
            api=api,
            org=org,
            other=other,
            child=child,
            admin=admin,
            owner=owner,
            outsider=outsider,
            executor=executor,
            foreign=foreign,
            process=process,
            activity=activity,
            version=version,
            role=role,
            second_role=second_role,
            headers=headers,
            base=f"/api/v1/processes/{process.id}/gate5",
        )
        try:
            yield data
        finally:
            api.close()
            if old is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = old
            db.close()
            outer.rollback()


def test_owned_assignment_rejects_invisible_organization_before_write(case):
    c = case
    with pytest.raises(HTTPException) as exc:
        service.upsert_assignment(
            c.db, c.process, "work", {"org_unit_id": c.other.id}, c.owner, c.version.id
        )
    assert exc.value.status_code == 404
    assert (
        c.db.scalar(
            select(func.count())
            .select_from(NodeAssignment)
            .where(NodeAssignment.process_id == c.process.id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "field",
    [
        "default_assignee_user_id",
        "approver_user_id",
        "backup_assignee_user_id",
        "escalation_user_id",
    ],
)
def test_assignment_rejects_account_outside_selected_organization(case, field):
    c = case
    with pytest.raises(HTTPException) as exc:
        service.upsert_assignment(
            c.db,
            c.process,
            "work",
            {"org_unit_id": c.org.id, field: c.foreign.id},
            c.admin,
            c.version.id,
        )
    assert exc.value.status_code == 400


def test_assignment_allows_child_org_account_and_admin_cross_org_selection(case):
    c = case
    row = service.upsert_assignment(
        c.db,
        c.process,
        "work",
        {
            "org_unit_id": c.org.id,
            "default_assignee_user_id": c.executor.id,
        },
        c.owner,
        c.version.id,
    )
    assert row.default_assignee_user_id == c.executor.id
    row = service.upsert_assignment(
        c.db,
        c.process,
        "work",
        {
            "org_unit_id": c.other.id,
            "default_assignee_user_id": c.foreign.id,
        },
        c.admin,
        c.version.id,
    )
    assert row.org_unit_id == c.other.id


@pytest.mark.parametrize("invalid", ["missing", "inactive"])
def test_assignment_rejects_invalid_organization(case, invalid):
    c = case
    ident = c.other.id
    if invalid == "missing":
        ident = max(c.org.id, c.other.id, c.child.id) + 100000
    else:
        c.other.is_active = False
    with pytest.raises(HTTPException) as exc:
        service.upsert_assignment(
            c.db, c.process, "work", {"org_unit_id": ident}, c.admin, c.version.id
        )
    assert exc.value.status_code == 400


def test_assignment_partial_update_checks_existing_scope_and_accounts(case):
    c = case
    row = service.upsert_assignment(
        c.db,
        c.process,
        "work",
        {
            "org_unit_id": c.org.id,
            "default_assignee_user_id": c.executor.id,
        },
        c.admin,
        c.version.id,
    )
    with pytest.raises(HTTPException) as exc:
        service.upsert_assignment(
            c.db, c.process, "work", {"org_unit_id": c.other.id}, c.admin, c.version.id
        )
    assert exc.value.status_code == 400
    assert row.org_unit_id == c.org.id


def test_owner_can_update_owned_process_via_api(case):
    c = case
    response = c.api.put(
        c.base + "/owner",
        headers=c.headers(c.owner),
        json={
            "expected_model_version_id": c.version.id,
            "owner_user_id": c.owner.id,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["owner_user_id"] == c.owner.id


@pytest.mark.parametrize("operation", ["owner", "assignment"])
def test_other_owner_cannot_update_process_even_through_service(case, operation):
    c = case
    with pytest.raises(HTTPException) as exc:
        if operation == "owner":
            service.set_process_owner(
                c.db,
                c.process,
                owner_user_id=c.outsider.id,
                actor=c.outsider,
                expected_model_version_id=c.version.id,
            )
        else:
            service.upsert_assignment(c.db, c.process, "work", {}, c.outsider, c.version.id)
    assert exc.value.status_code == 403
    assert c.process.owner_user_id == c.owner.id


def test_owner_api_rejects_other_owner_and_stale_version(case):
    c = case
    payload = {"expected_model_version_id": c.version.id, "owner_user_id": c.outsider.id}
    assert (
        c.api.put(c.base + "/owner", headers=c.headers(c.outsider), json=payload).status_code == 403
    )
    payload["expected_model_version_id"] += 10000
    assert c.api.put(c.base + "/owner", headers=c.headers(c.owner), json=payload).status_code == 409
    assert c.process.owner_user_id == c.owner.id


@pytest.mark.parametrize("invalid", ["missing", "inactive"])
def test_accountability_api_returns_business_error_for_invalid_role(case, invalid):
    c = case
    ident = c.role.id
    if invalid == "missing":
        ident = c.second_role.id + 100000
    else:
        c.role.is_active = False
    response = c.api.put(
        c.base + "/accountability/work",
        headers=c.headers(c.admin),
        json={"expected_model_version_id": c.version.id, "role_id": ident},
    )
    assert response.status_code == 400, response.text
    assert (
        c.db.scalar(
            select(func.count())
            .select_from(RaciAssignment)
            .where(RaciAssignment.process_id == c.process.id)
        )
        == 0
    )


def test_accountability_api_is_idempotent_and_rejects_second_a(case):
    c = case
    payload = {"expected_model_version_id": c.version.id, "role_id": c.role.id}
    first = c.api.put(c.base + "/accountability/work", headers=c.headers(c.admin), json=payload)
    assert first.status_code == 200, first.text
    again = c.api.put(c.base + "/accountability/work", headers=c.headers(c.admin), json=payload)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    payload["role_id"] = c.second_role.id
    conflict = c.api.put(c.base + "/accountability/work", headers=c.headers(c.admin), json=payload)
    assert conflict.status_code == 409, conflict.text
    rows = c.db.scalars(
        select(RaciAssignment).where(RaciAssignment.process_id == c.process.id)
    ).all()
    assert len(rows) == 1 and rows[0].role_id == c.role.id
    assert c.db.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_type == "raci_assignment", AuditLog.entity_id == rows[0].id
        )
    )


def test_accountability_uses_published_version_not_unreleased_draft(case):
    c = case
    c.db.add(
        ProcessModelVersion(
            process_id=c.process.id, version=2, status="DRAFT", snapshot={"nodes": [], "edges": []}
        )
    )
    c.db.flush()
    response = c.api.put(
        c.base + "/accountability/work",
        headers=c.headers(c.admin),
        json={
            "expected_model_version_id": c.version.id,
            "role_id": c.role.id,
        },
    )
    assert response.status_code == 200, response.text


def test_accountability_versioned_mapping_does_not_need_legacy_pointer(case):
    from app.models.asset_graph import NodeActivityLink

    c = case
    c.version.snapshot = {
        "nodes": [{"node_key": "work", "name": "合成活动", "node_type": "TASK"}],
        "edges": [],
    }
    c.db.add(
        NodeActivityLink(
            process_id=c.process.id,
            model_version_id=c.version.id,
            node_key="work",
            activity_id=c.activity.id,
            relation="REALIZES",
            path_condition="ALL",
        )
    )
    c.db.flush()
    response = c.api.put(
        c.base + "/accountability/work",
        headers=c.headers(c.admin),
        json={
            "expected_model_version_id": c.version.id,
            "role_id": c.role.id,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["activity_id"] == c.activity.id
