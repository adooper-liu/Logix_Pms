"""岗位职责投影：重复实现不重复算责，角色歧义不自动分摊。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.org import Position
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import User

API = "/api/v1"


@pytest.fixture
def coverage_case(client):
    suffix = uuid4().hex[:8]
    p = client.post(
        f"{API}/process-map",
        json={
            "code": "COV-" + suffix,
            "name": "岗位职责流程",
            "level": 3,
        },
    ).json()
    a = client.post(
        f"{API}/process-map",
        json={
            "code": "CA-" + suffix,
            "name": "活动职责",
            "level": 4,
            "parent_id": p["id"],
        },
    ).json()
    with SessionLocal() as db:
        positions = [Position(code=f"CP{i}-{suffix}", name=f"岗位{i}") for i in range(2)]
        db.add_all(positions)
        db.flush()
        role = GovernanceRole(code="CR-" + suffix, name="活动执行者", is_active=True)
        db.add(role)
        db.flush()
        users = [
            User(
                username=f"cu{i}-{suffix}",
                display_name="测试成员",
                password_hash="not-a-login",
                position_id=positions[0].id,
            )
            for i in range(2)
        ]
        db.add_all(users)
        db.flush()
        db.add_all([GovernanceRoleMember(role_id=role.id, user_id=u.id) for u in users])
        db.commit()
        ids = {
            "position": positions[0].id,
            "other": positions[1].id,
            "role": role.id,
            "users": [u.id for u in users],
        }
    response = client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": key,
                    "name": key,
                    "node_type": "TASK",
                    "process_arch_id": a["id"],
                    "owner_position_id": ids["position"],
                }
                for key in ["n1", "n2"]
            ],
            "edges": [{"source_key": "n1", "target_key": "n2"}],
        },
    )
    assert response.status_code == 200, response.text
    yield p, a, ids
    with SessionLocal() as db:
        db.execute(delete(RaciAssignment).where(RaciAssignment.process_id == p["id"]))
        db.execute(delete(GovernanceRoleMember).where(GovernanceRoleMember.role_id == ids["role"]))
        db.execute(delete(GovernanceRole).where(GovernanceRole.id == ids["role"]))
        db.execute(delete(User).where(User.id.in_(ids["users"])))
        db.commit()
    assert client.delete(f"{API}/process-map/{p['id']}").status_code == 200
    with SessionLocal() as db:
        from app.models.workload import WorkMeasurementStandard

        db.execute(
            delete(WorkMeasurementStandard).where(
                WorkMeasurementStandard.position_id.in_([ids["position"], ids["other"]])
            )
        )
        db.execute(delete(Position).where(Position.id.in_([ids["position"], ids["other"]])))
        db.commit()


def _raci(client, case, **extra):
    p, _a, ids = case
    response = client.post(
        f"{API}/governance/raci",
        json={
            "process_id": p["id"],
            "matter": "岗位职责",
            "role_id": ids["role"],
            "raci": "R",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _coverage(client, case):
    response = client.get(
        f"{API}/workload/position-coverage",
        params={
            "position_id": case[2]["position"],
            "period": "2026-10-19",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_coverage_deduplicates_activity_across_nodes_and_roles(client, coverage_case):
    _p, a, _ids = coverage_case
    assignment = _raci(client, coverage_case, activity_id=a["id"])
    data = _coverage(client, coverage_case)
    assert data["period"] == "2026-10-01"
    rows = [r for r in data["activities"] if r["activity_id"] == a["id"]]
    assert len(rows) == 1
    assert rows[0]["node_keys"] == ["n1", "n2"]
    assert [r["id"] for r in rows[0]["raci"]] == [assignment["id"]]
    assert data["workload"]["totals"]["utilization"] is None


@pytest.mark.parametrize("state", ["empty", "no-position", "multiple", "inactive"])
def test_role_resolution_requires_one_unambiguous_position(client, coverage_case, state):
    _p, a, ids = coverage_case
    assignment = _raci(client, coverage_case, activity_id=a["id"])
    with SessionLocal() as db:
        if state == "empty":
            db.execute(
                delete(GovernanceRoleMember).where(GovernanceRoleMember.role_id == ids["role"])
            )
        else:
            u = db.get(User, ids["users"][1])
            if state == "multiple":
                u.position_id = ids["other"]
            elif state == "no-position":
                u.position_id = None
            else:
                u.is_active = False
        db.commit()
    data = _coverage(client, coverage_case)
    gap = next(r for r in data["unmapped_roles"] if r["role_id"] == ids["role"])
    assert gap["code"] == "UNMAPPED_ROLE"
    row = next(r for r in data["activities"] if r["activity_id"] == a["id"])
    assert assignment["id"] not in [r["id"] for r in row["raci"]]


def test_matter_and_node_scopes_do_not_invent_activity(client, coverage_case):
    _p, a, _ids = coverage_case
    node = _raci(client, coverage_case, node_key="n1")
    matter = _raci(client, coverage_case)
    data = _coverage(client, coverage_case)
    row = next(r for r in data["activities"] if r["activity_id"] == a["id"])
    assert [r["id"] for r in row["raci"]] == [node["id"]]
    assert row["raci"][0]["node_key"] == "n1"
    assert [r["id"] for r in data["matter_assignments"]] == [matter["id"]]


def test_coverage_uses_summary_without_inflating_demand(client, coverage_case):
    from app.models.workload import WorkMeasurementStandard

    _p, a, ids = coverage_case
    with SessionLocal() as db:
        for status, minutes in [("VERIFIED", 12), ("DRAFT", 99)]:
            db.add(
                WorkMeasurementStandard(
                    code="CVWS-" + uuid4().hex[:8],
                    name="测试工时",
                    activity_id=a["id"],
                    position_id=ids["position"],
                    standard_minutes=minutes,
                    monthly_frequency=10,
                    status=status,
                )
            )
        db.commit()
    data = _coverage(client, coverage_case)
    assert data["workload"]["totals"]["demand_minutes"] == 120
    assert data["workload"]["totals"]["utilization"] is None
    original = client.get(f"{API}/workload/summary?period=2026-10-01").json()
    expected = [r for r in original["standards"] if r["position_id"] == ids["position"]]
    assert data["workload"]["standards"] == expected
    assert len([r for r in data["activities"] if r["activity_id"] == a["id"]]) == 1


def test_coverage_scopes_sources_and_is_read_only(client, viewer_client, coverage_case):
    from sqlalchemy import func, select

    from app.models.org import OrgUnit
    from app.models.process import ProcessModelVersion
    from app.models.user import AuditLog
    from app.models.workload import WorkMeasurementStandard

    _p, a, ids = coverage_case
    with SessionLocal() as db:
        org = OrgUnit(code="CVORG-" + uuid4().hex[:8], name="受限部门", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        orgid = org.id
        db.add(
            WorkMeasurementStandard(
                code="SECRET-" + uuid4().hex[:8],
                name="受限标准名称",
                activity_id=a["id"],
                position_id=ids["position"],
                org_unit_id=orgid,
                standard_minutes=57,
                monthly_frequency=10,
                status="VERIFIED",
            )
        )
        db.commit()
        before = (
            db.scalar(select(func.count()).select_from(AuditLog)),
            db.scalar(select(func.count()).select_from(ProcessModelVersion)),
        )
    try:
        response = viewer_client.get(
            f"{API}/workload/position-coverage",
            params={"position_id": ids["position"], "period": "2026-10-01"},
        )
        assert response.status_code == 200, response.text
        assert "受限标准名称" not in response.text
        assert response.json()["workload"]["totals"]["demand_minutes"] == 0
        summary = viewer_client.get(f"{API}/workload/summary?period=2026-10-01")
        assert "受限标准名称" not in summary.text
        with SessionLocal() as db:
            after = (
                db.scalar(select(func.count()).select_from(AuditLog)),
                db.scalar(select(func.count()).select_from(ProcessModelVersion)),
            )
            assert after == before
            db.get(Position, ids["other"]).org_unit_id = orgid
            db.commit()
        assert (
            viewer_client.get(
                f"{API}/workload/position-coverage", params={"position_id": ids["other"]}
            ).status_code
            == 404
        )
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(WorkMeasurementStandard).where(WorkMeasurementStandard.org_unit_id == orgid)
            )
            db.get(Position, ids["other"]).org_unit_id = None
            db.flush()
            db.delete(db.get(OrgUnit, orgid))
            db.commit()
