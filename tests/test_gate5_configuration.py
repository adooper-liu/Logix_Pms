"""Gate 5 generic configuration write contracts."""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _sample(client):
    return next(
        row for row in client.get("/api/v1/process-map/flat").json() if row["code"] == "L3-032"
    )


def _published(db, pid):
    from app.models.process import ProcessArch, ProcessModelVersion

    process = db.get(ProcessArch, pid)
    version = db.scalar(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == pid,
            ProcessModelVersion.status == "PUBLISHED",
        )
    )
    if version is None:
        activity = db.scalar(
            select(ProcessArch)
            .where(ProcessArch.parent_id == pid, ProcessArch.level == 4)
            .order_by(ProcessArch.id)
        )
        version = ProcessModelVersion(
            process_id=pid,
            version=1,
            status="PUBLISHED",
            snapshot={
                "nodes": [
                    {
                        "node_key": "n1",
                        "name": "测试活动",
                        "node_type": "TASK",
                        "process_arch_id": activity.id,
                    }
                ],
                "edges": [],
            },
        )
        db.add(version)
        process.published_model_version = 1
        db.flush()
    return process, version


def test_set_owner_rejects_wrong_published_version(client):
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services.gate5_readiness import set_process_owner

    sample = _sample(client)
    with SessionLocal() as db:
        process, version = _published(db, sample["id"])
        actor = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
        with pytest.raises(HTTPException) as exc:
            set_process_owner(
                db,
                process,
                owner_user_id=actor.id,
                actor=actor,
                expected_model_version_id=version.id + 1,
            )
        assert exc.value.status_code == 409
        db.rollback()


def test_assignment_write_rejects_inactive_accounts(client):
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services.gate5_readiness import upsert_assignment

    sample = _sample(client)
    with SessionLocal() as db:
        process, version = _published(db, sample["id"])
        user = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
        user.is_active = False
        with pytest.raises(HTTPException) as exc:
            upsert_assignment(db, process, "n1", {"default_assignee_user_id": 69}, user, version.id)
        assert exc.value.status_code == 400
        db.rollback()


def test_acceptance_requires_current_published_model_and_preserves_history(client):
    from app.core.database import SessionLocal
    from app.models.responsibility import ProcessResponsibilityAcceptance
    from app.models.user import User
    from app.services.gate5_readiness import accept_responsibility

    sample = _sample(client)
    with SessionLocal() as db:
        process, version = _published(db, sample["id"])
        actor = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
        row = accept_responsibility(
            db,
            process,
            model_version_id=version.id,
            node_key="n1",
            scope="EXECUTOR",
            subject_user_id=actor.id,
            actor=actor,
            valid_until=date(2030, 1, 1),
            evidence_note="测试确认",
        )
        db.flush()
        assert row.status == "ACCEPTED"
        with pytest.raises((IntegrityError, HTTPException)):
            accept_responsibility(
                db,
                process,
                model_version_id=version.id,
                node_key="n1",
                scope="EXECUTOR",
                subject_user_id=actor.id,
                actor=actor,
                valid_until=None,
                evidence_note="重复",
            )
        db.flush()
        assert (
            db.scalar(
                select(ProcessResponsibilityAcceptance.id).where(
                    ProcessResponsibilityAcceptance.id == row.id
                )
            )
            is not None
        )
        db.rollback()
