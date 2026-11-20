"""Generic Gate 5 readiness behavior."""

from sqlalchemy import select


def _generic_process(db):
    from app.models.process import ProcessArch, ProcessModelVersion

    process = ProcessArch(
        code="L3-GENERIC-GATE5-RULES", name="通用责任规则测试", level=3, is_draft=False
    )
    activity = ProcessArch(
        code="L4-GENERIC-GATE5-RULES",
        name="通用活动",
        level=4,
        parent=process,
        is_draft=False,
    )
    db.add_all([process, activity])
    db.flush()
    version = ProcessModelVersion(
        process_id=process.id,
        version=1,
        status="PUBLISHED",
        snapshot={
            "nodes": [
                {
                    "node_key": "n1",
                    "name": "通用活动",
                    "node_type": "TASK",
                    "process_arch_id": activity.id,
                }
            ],
            "edges": [],
        },
    )
    process.published_model_version = 1
    db.add(version)
    db.flush()
    return process, activity, version


def _viewer(db):
    from app.models.user import User

    return db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))


def test_generic_rules_block_missing_owner_and_assignment(client):
    from app.core.database import SessionLocal
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        process, _activity, _version = _generic_process(db)
        result = readiness(db, process.id, viewer=_viewer(db))
        assert result.status == "BLOCKED"
        codes = {item.code for item in result.blockers}
        assert {
            "OWNER_ACCOUNT_MISSING",
            "NODE_ASSIGNMENT_MISSING",
            "ACTIVITY_A_NOT_UNIQUE",
        } <= codes
        assert result.activities[0].node_key == "n1"
        db.rollback()


def test_generic_rules_reject_process_level_raci_as_activity_a(client):
    from app.core.database import SessionLocal
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        process, activity, _version = _generic_process(db)
        result = readiness(db, process.id, viewer=_viewer(db))
        row = next(item for item in result.activities if item.activity_id == activity.id)
        assert any(item.code == "ACTIVITY_A_NOT_UNIQUE" for item in row.blockers)
        db.rollback()


def test_generic_rules_block_without_published_model(client):
    from app.core.database import SessionLocal
    from app.models.process import ProcessArch
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        process = ProcessArch(
            code="L3-GENERIC-GATE5-NOVERSION", name="无版本流程", level=3, is_draft=False
        )
        db.add(process)
        db.flush()
        result = readiness(db, process.id, viewer=_viewer(db))
        assert result.blockers[0].code == "NO_PUBLISHED_MODEL"
        db.rollback()


def test_generic_rules_reject_non_l3(client):
    from fastapi import HTTPException

    from app.core.database import SessionLocal
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        _process, activity, _version = _generic_process(db)
        try:
            readiness(db, activity.id)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("non-L3 must be rejected")
        db.rollback()


def test_legacy_mapping_is_a_hard_gate5_blocker(client):
    from app.core.database import SessionLocal
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        process, _activity, _version = _generic_process(db)
        result = readiness(db, process.id, viewer=_viewer(db))
        assert any(item.code == "VERSIONED_ACTIVITY_MAPPING_REQUIRED" for item in result.blockers)
        db.rollback()


def test_partial_versioned_mapping_is_a_hard_gate5_blocker(client):
    from app.core.database import SessionLocal
    from app.models.asset_graph import NodeActivityLink
    from app.models.process import ProcessArch
    from app.services.gate5_readiness import readiness

    with SessionLocal() as db:
        process, activity, version = _generic_process(db)
        second = ProcessArch(
            code="L4-GENERIC-GATE5-RULES-2",
            name="第二活动",
            level=4,
            parent=process,
            is_draft=False,
        )
        db.add(second)
        db.flush()
        version.snapshot["nodes"].append(
            {
                "node_key": "n2",
                "name": "第二活动",
                "node_type": "TASK",
                "process_arch_id": second.id,
            }
        )
        db.add(
            NodeActivityLink(
                process_id=process.id,
                model_version_id=version.id,
                node_key="n1",
                activity_id=activity.id,
                relation="REALIZES",
                path_condition="ALL",
            )
        )
        db.flush()
        result = readiness(db, process.id, viewer=_viewer(db))
        assert any(item.code == "VERSIONED_ACTIVITY_MAPPING_REQUIRED" for item in result.blockers)
        db.rollback()


# Optional smoke test only; the generic synthetic tests above determine mechanism acceptance.
def test_optional_l3_032_smoke(client):
    from app.core.database import SessionLocal
    from app.services.gate5_readiness import readiness

    sample = next(
        row for row in client.get("/api/v1/process-map/flat").json() if row["code"] == "L3-032"
    )
    with SessionLocal() as db:
        result = readiness(db, sample["id"], viewer=_viewer(db))
        assert result.process_code == "L3-032"
        db.rollback()
