"""P3b service-level coverage matrix tests."""

from __future__ import annotations

import conftest  # noqa: F401
import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models.asset_graph import NodeActivityLink, UnmodeledActivity
from app.models.org import Position
from app.models.process import ProcessArch, ProcessModelVersion, ProcessNode
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import User
from app.services import key_process_coverage


@pytest.fixture(autouse=True)
def _cleanup_p3b_rows(client):
    yield
    with SessionLocal() as db:
        process_ids = list(
            db.scalars(select(ProcessArch.id).where(ProcessArch.code.like("P3B-SVC-%")))
        )
        if process_ids:
            activity_ids = list(
                db.scalars(select(ProcessArch.id).where(ProcessArch.parent_id.in_(process_ids)))
            )
            db.execute(delete(NodeActivityLink).where(NodeActivityLink.process_id.in_(process_ids)))
            db.execute(
                delete(UnmodeledActivity).where(UnmodeledActivity.process_id.in_(process_ids))
            )
            db.execute(delete(RaciAssignment).where(RaciAssignment.process_id.in_(process_ids)))
            db.execute(delete(ProcessNode).where(ProcessNode.process_id.in_(process_ids)))
            db.execute(
                delete(ProcessModelVersion).where(ProcessModelVersion.process_id.in_(process_ids))
            )
            if activity_ids:
                db.execute(delete(ProcessArch).where(ProcessArch.id.in_(activity_ids)))
            db.execute(delete(ProcessArch).where(ProcessArch.id.in_(process_ids)))
        db.commit()


def _admin():
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.username == "admin"))


def _case(prefix: str, *, key_l3=True, key_l4=False, basis="测试依据"):
    with SessionLocal() as db:
        l2 = ProcessArch(code=f"{prefix}-L2", name="覆盖度上级", level=2, is_draft=False)
        db.add(l2)
        db.flush()
        l3 = ProcessArch(
            code=f"{prefix}-L3",
            name="覆盖度流程",
            level=3,
            parent_id=l2.id,
            is_key_process=key_l3,
            key_basis=basis if key_l3 else None,
            is_draft=False,
        )
        db.add(l3)
        db.flush()
        l4 = ProcessArch(
            code=f"{prefix}-L4",
            name="覆盖度活动",
            level=4,
            parent_id=l3.id,
            is_key_process=key_l4,
            key_basis=basis if key_l4 else None,
            is_draft=False,
        )
        db.add(l4)
        db.flush()
        version = ProcessModelVersion(
            process_id=l3.id, version=1, status="PUBLISHED", snapshot={}, published_at=utcnow()
        )
        node = ProcessNode(
            process_id=l3.id,
            node_key="n1",
            name="覆盖度节点",
            node_type="TASK",
            lane="测试",
            sequence_order=1,
        )
        db.add_all([version, node])
        db.flush()
        l3.model_version = 1
        l3.published_model_version = 1
        db.commit()
        return l2.id, l3.id, l4.id, version.id, node.id


def _activity(prefix: str):
    with SessionLocal() as db:
        result = key_process_coverage.coverage(db, _admin())
        rows = db.scalars(select(ProcessArch).where(ProcessArch.code.like(f"{prefix}%"))).all()
        codes = [item.code for item in result.activities]
        assert f"{prefix}-L4" in codes, (
            [
                (
                    row.code,
                    row.level,
                    row.parent_id,
                    row.is_draft,
                    row.is_key_process,
                    row.key_basis,
                )
                for row in rows
            ],
            codes,
        )
        return next(item for item in result.activities if item.code == f"{prefix}-L4")


def test_old_published_links_are_not_current_implementations():
    prefix = "P3B-SVC-OLD-VERSION"
    _, process_id, activity_id, version_id, node_id = _case(prefix)
    with SessionLocal() as db:
        version = ProcessModelVersion(
            process_id=process_id, version=2, status="PUBLISHED", snapshot={}, published_at=utcnow()
        )
        db.add(version)
        db.flush()
        db.get(ProcessArch, process_id).published_model_version = 2
        db.get(ProcessNode, node_id).process_arch_id = activity_id
        db.add(
            NodeActivityLink(
                model_version_id=version_id,
                process_id=process_id,
                node_key="n1",
                activity_id=activity_id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        db.commit()
    activity = _activity(prefix)
    assert len(activity.implementations) == 1
    assert activity.implementations[0].legacy is True
    assert activity.implementations[0].current is False


def test_owner_projection_is_scoped_by_process_and_node_key():
    prefix = "P3B-SVC-OWNER-SCOPE"
    _, process_id, activity_id, version_id, _ = _case(prefix)
    with SessionLocal() as db:
        unrelated = ProcessArch(
            code=f"{prefix}-UNRELATED",
            name="无关流程",
            level=3,
            is_key_process=False,
            is_draft=False,
        )
        db.add(unrelated)
        db.flush()
        version = ProcessModelVersion(
            process_id=unrelated.id,
            version=1,
            status="PUBLISHED",
            snapshot={},
            published_at=utcnow(),
        )
        position = Position(code=f"{prefix}-POS", name="无关岗位")
        node = ProcessNode(
            process_id=unrelated.id,
            node_key="n1",
            name="同名无关节点",
            node_type="TASK",
            lane="测试",
            owner_position=position,
        )
        db.add_all([version, position, node])
        db.flush()
        unrelated.published_model_version = 1
        db.add(
            NodeActivityLink(
                model_version_id=version_id,
                process_id=process_id,
                node_key="n1",
                activity_id=activity_id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        db.commit()
    activity = _activity(prefix)
    assert not any(row.code == f"{prefix}-POS" for row in activity.gap_owner_positions)


def test_invalid_node_relation_is_reported_as_gap():
    prefix = "P3B-SVC-INVALID-LINK"
    _, process_id, activity_id, version_id, _ = _case(prefix)
    with SessionLocal() as db:
        db.add(
            NodeActivityLink(
                model_version_id=version_id,
                process_id=process_id,
                node_key="missing",
                activity_id=activity_id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        db.commit()
    activity = _activity(prefix)
    assert not activity.implementations
    assert any(g.code == "INVALID_IMPLEMENTATION" for g in activity.gaps)


def test_broken_parent_chain_is_reported_as_gap():
    prefix = "P3B-SVC-BROKEN-HIERARCHY"
    with SessionLocal() as db:
        l4 = ProcessArch(
            code=f"{prefix}-L4",
            name="断链活动",
            level=4,
            parent_id=999999,
            is_key_process=True,
            key_basis="断链依据",
            is_draft=False,
        )
        db.add(l4)
        db.commit()
    activity = _activity(prefix)
    assert any(g.code == "INVALID_HIERARCHY" for g in activity.gaps)


def test_unrelated_l2_and_uncovered_activity_do_not_hide_owner_gap():
    prefix = "P3B-SVC-UNCOVERED-GAP"
    _, _, _, _, _ = _case(prefix)
    with SessionLocal() as db:
        db.add(ProcessArch(code=f"{prefix}-OTHER-L2", name="无关上级", level=2, is_draft=False))
        db.commit()
    activity = _activity(prefix)
    assert activity.coverage_status == "UNCOVERED"
    assert any(g.code == "UNMAPPED_POSITION" for g in activity.gaps)
    with SessionLocal() as db:
        result = key_process_coverage.coverage(db, _admin())
    assert all(row.code != f"{prefix}-OTHER-L2" for row in result.boundary_reviews)

    prefix = "P3B-SVC-INHERIT"
    _case(prefix, key_l3=True, key_l4=False)
    activity = _activity(prefix)
    assert activity.key_basis == "测试依据"
    assert activity.key_basis_source == "INHERITED"


def test_explicit_key_l4_is_included_without_key_l3():
    prefix = "P3B-SVC-DIRECT-L4"
    _case(prefix, key_l3=False, key_l4=True)
    activity = _activity(prefix)
    assert activity.key_basis == "测试依据"
    assert activity.key_basis_source == "DIRECT"


def test_missing_basis_is_not_treated_as_key():
    prefix = "P3B-SVC-MISSING-BASIS"
    _, l3_id, activity_id, _, _ = _case(prefix, key_l3=True, basis="测试依据")
    with SessionLocal() as db:
        db.get(ProcessArch, l3_id).key_basis = None
        db.commit()
    activity = _activity(prefix)
    assert activity.coverage_status == "INVALID_KEY_BASIS"
    assert any(g.code == "INVALID_KEY_BASIS" for g in activity.gaps)


def test_versioned_and_historical_links_are_deduplicated_and_marked():
    prefix = "P3B-SVC-VERSIONS"
    _, process_id, activity_id, version_id, node_id = _case(prefix)
    with SessionLocal() as db:
        node = db.get(ProcessNode, node_id)
        db.add_all(
            [
                NodeActivityLink(
                    model_version_id=None,
                    process_id=process_id,
                    node_key=node.node_key,
                    activity_id=activity_id,
                    relation="REALIZES",
                    path_condition="ALL",
                ),
                NodeActivityLink(
                    model_version_id=version_id,
                    process_id=process_id,
                    node_key=node.node_key,
                    activity_id=activity_id,
                    relation="REALIZES",
                    path_condition="ALL",
                ),
            ]
        )
        db.commit()
    activity = _activity(prefix)
    assert len(activity.implementations) == 1
    implementation = activity.implementations[0]
    assert implementation.current is True
    assert implementation.historical is True
    assert set(implementation.source_model_version_ids) == {None, version_id}


def test_legacy_process_arch_pointer_is_fallback_only():
    prefix = "P3B-SVC-LEGACY"
    _, process_id, activity_id, _, node_id = _case(prefix)
    with SessionLocal() as db:
        db.get(ProcessNode, node_id).process_arch_id = activity_id
        db.commit()
    activity = _activity(prefix)
    assert len(activity.implementations) == 1
    assert activity.implementations[0].legacy is True
    with SessionLocal() as db:
        db.add(
            NodeActivityLink(
                process_id=process_id,
                node_key="n1",
                activity_id=activity_id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        db.commit()
    activity = _activity(prefix)
    assert len(activity.implementations) == 1
    assert activity.implementations[0].legacy is False


def test_unmodeled_uncovered_and_multi_process_are_distinct():
    prefix = "P3B-SVC-UNMODELED"
    _, process_id, activity_id, _, _ = _case(prefix)
    with SessionLocal() as db:
        db.add(UnmodeledActivity(process_id=process_id, activity_id=activity_id, reason="线下确认"))
        db.commit()
    uncovered = "P3B-SVC-UNCOVERED"
    _case(uncovered)
    multi = "P3B-SVC-MULTI"
    _, first_process, activity_id, first_version, _ = _case(multi)
    with SessionLocal() as db:
        second = ProcessArch(code=f"{multi}-L3-B", name="第二流程", level=3, is_draft=False)
        db.add(second)
        db.flush()
        version = ProcessModelVersion(
            process_id=second.id, version=1, status="PUBLISHED", snapshot={}, published_at=utcnow()
        )
        node = ProcessNode(
            process_id=second.id, node_key="n2", name="第二节点", node_type="TASK", lane="测试"
        )
        db.add_all([version, node])
        db.flush()
        second.model_version = 1
        second.published_model_version = 1
        db.add_all(
            [
                NodeActivityLink(
                    model_version_id=first_version,
                    process_id=first_process,
                    node_key="n1",
                    activity_id=activity_id,
                    relation="REALIZES",
                    path_condition="ALL",
                ),
                NodeActivityLink(
                    model_version_id=version.id,
                    process_id=second.id,
                    node_key="n2",
                    activity_id=activity_id,
                    relation="REALIZES",
                    path_condition="ALL",
                ),
            ]
        )
        db.commit()
    assert _activity(prefix).coverage_status == "UNMODELED"
    assert _activity(uncovered).coverage_status == "UNCOVERED"
    multi_activity = _activity(multi)
    assert len(multi_activity.duplicate_processes) == 2
    assert "重叠" not in " ".join(g.message for g in multi_activity.gaps)


def test_unreviewed_sibling_boundary_is_not_no_overlap():
    prefix = "P3B-SVC-BOUNDARY"
    _case(prefix)
    with SessionLocal() as db:
        result = key_process_coverage.coverage(db, _admin())
        boundary = next(row for row in result.boundary_reviews if row.code == f"{prefix}-L2")
    assert boundary.status == "UNREVIEWED"
    assert boundary.status_label == "未评审"
    assert boundary.overlap_found is None


def test_gap_owner_positions_are_explicit_only():
    prefix = "P3B-SVC-OWNERS"
    _, process_id, activity_id, version_id, node_id = _case(prefix)
    with SessionLocal() as db:
        db.add(
            NodeActivityLink(
                model_version_id=version_id,
                process_id=process_id,
                node_key="n1",
                activity_id=activity_id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        position = Position(code=f"{prefix}-POS", name="显式岗位")
        role = GovernanceRole(code=f"{prefix}-ROLE", name="显式角色")
        member = User(
            username=f"{prefix.lower()}-user",
            display_name="岗位成员",
            password_hash="not-used",
            role="VIEWER",
            position=position,
        )
        db.add_all([position, role, member])
        db.flush()
        db.get(ProcessNode, node_id).owner_position_id = position.id
        db.add(GovernanceRoleMember(role_id=role.id, user_id=member.id))
        db.add(
            RaciAssignment(
                process_id=process_id,
                matter="活动责任",
                activity_id=activity_id,
                role_id=role.id,
                raci="R",
            )
        )
        db.commit()
    activity = _activity(prefix)
    assert any(row.code == f"{prefix}-POS" for row in activity.gap_owner_positions)
    assert not any(g.code == "UNMAPPED_POSITION" for g in activity.gaps)


def test_coverage_is_read_only_and_deterministic():
    prefix = "P3B-SVC-DETERMINISTIC"
    _case(prefix)
    with SessionLocal() as db:
        first = key_process_coverage.coverage(db, _admin()).model_dump(exclude={"generated_at"})
        second = key_process_coverage.coverage(db, _admin()).model_dump(exclude={"generated_at"})
    assert first == second
