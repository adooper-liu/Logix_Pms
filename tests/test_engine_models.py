"""Provider identities must preserve legacy uniqueness without forbidding engine parallelism."""

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.database import Base
from app.models.execution import ProcessInstance, ProcessTask


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.db'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def instance(db, provider):
    row = ProcessInstance(
        code=str(uuid.uuid4()),
        process_name="synthetic",
        provider=provider,
        snapshot={},
        engine_namespace="sandbox" if provider == "FLOWABLE" else None,
    )
    db.add(row)
    db.flush()
    return row


def task(db, row, provider=None, engine_id=None):
    item = ProcessTask(
        instance_id=row.id,
        provider=provider or row.provider,
        node_key="activity",
        name="synthetic",
        engine_namespace=row.engine_namespace,
        engine_task_id=engine_id,
    )
    db.add(item)
    db.flush()
    return item


def test_legacy_single_open_and_engine_parallel(db):
    old = instance(db, "LEGACY")
    task(db, old)
    with pytest.raises(IntegrityError), db.begin_nested():
        task(db, old)
    parallel = instance(db, "FLOWABLE")
    task(db, parallel, engine_id="first")
    task(db, parallel, engine_id="second")
    assert len(parallel.tasks) == 2


def test_engine_identity_unique(db):
    first = instance(db, "FLOWABLE")
    second = instance(db, "FLOWABLE")
    task(db, first, engine_id="same-engine-task")
    with pytest.raises(IntegrityError), db.begin_nested():
        task(db, second, engine_id="same-engine-task")


def test_provider_parent_mismatch_rejected(db):
    row = instance(db, "LEGACY")
    with pytest.raises(IntegrityError), db.begin_nested():
        task(db, row, provider="FLOWABLE", engine_id="wrong-parent")


def test_legacy_mutators_refuse_engine_facts_and_manager_not_candidate(db):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.models.engine import EngineDeployment
    from app.models.process import ProcessArch, ProcessModelVersion
    from app.services import engine_execution, execution

    process = ProcessArch(code="SANDBOX-GUARD", name="合成", level=3)
    db.add(process)
    db.flush()
    version = ProcessModelVersion(process_id=process.id, version=1, snapshot={})
    db.add(version)
    db.flush()
    deployment = EngineDeployment(
        model_version_id=version.id,
        namespace="sandbox",
        xml_hash="a" * 64,
        basis_hash="b" * 64,
        definition_id="def",
        deployment_id="deploy",
        execution_hash="c" * 64,
        command_id=str(uuid.uuid4()),
        configuration={"assignments": {"activity": ["pms:1"]}},
    )
    db.add(deployment)
    db.flush()
    row = instance(db, "FLOWABLE")
    row.process_id = process.id
    row.deployment_id = deployment.id
    item = task(db, row, engine_id="engine-guard")
    actor = SimpleNamespace(id=999, role="MANAGER", is_active=True, display_name="Synthetic")
    with pytest.raises(HTTPException):
        engine_execution.allowed_task(db, item, actor)
    with pytest.raises(HTTPException):
        execution.claim_task(db, item, actor)
    with pytest.raises(HTTPException):
        execution.assign_task(db, item, None, None)
    with pytest.raises(HTTPException):
        execution.cancel_instance(db, row, actor)
    with pytest.raises(HTTPException):
        execution.delete_instance(db, row, actor)
