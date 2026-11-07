"""Projection applies confirmed engine facts only, preserving multi-task identity."""

import uuid

import pytest
from fastapi import HTTPException

from app.core.database import SessionLocal
from app.models.engine import EngineDeployment
from app.models.execution import ProcessInstance
from app.models.process import ProcessArch, ProcessModelVersion


def test_parallel_projection_idempotent_and_wrong_definition_rejected(client):
    from app.services.engine_projection import apply_snapshot

    with SessionLocal() as db:
        process = ProcessArch(code="R3-PROJ-" + uuid.uuid4().hex[:6], name="投影", level=3)
        db.add(process)
        db.flush()
        version = ProcessModelVersion(
            process_id=process.id, version=1, status="PUBLISHED", snapshot={}
        )
        db.add(version)
        db.flush()
        deployment = EngineDeployment(
            model_version_id=version.id,
            namespace="test",
            xml_hash="a" * 64,
            basis_hash="b" * 64,
            definition_id="def",
            deployment_id="deploy",
            execution_hash="c" * 64,
            command_id=str(uuid.uuid4()),
            configuration={"assignments": {"a": ["pms:1"], "b": ["pms:1"]}},
        )
        db.add(deployment)
        db.flush()
        instance = ProcessInstance(
            code="R3-" + uuid.uuid4().hex[:8],
            process_id=process.id,
            process_name="投影",
            provider="FLOWABLE",
            engine_namespace="test",
            engine_instance_id="engine-one",
            deployment_id=deployment.id,
            model_version_id=version.id,
            snapshot={"nodes": []},
        )
        db.add(instance)
        db.flush()
        context = {
            "process_id": process.id,
            "model_version_id": version.id,
            "instance_id": instance.id,
            "namespace": "test",
        }
        tasks = [
            {
                "task_id": key,
                "activity_id": key,
                "execution_id": "exec-" + key,
                "name": key,
                "assignee": None,
                "candidates": ["pms:1"],
                "created_at": "2026-11-05T10:00:00+00:00",
            }
            for key in ["a", "b"]
        ]
        view = {
            "instance_id": "engine-one",
            "definition_id": "def",
            "context": context,
            "status": "RUNNING",
            "tasks": tasks,
            "history_tasks": [{**t, "completed_at": None, "delete_reason": None} for t in tasks],
            "completed_at": None,
        }
        apply_snapshot(db, instance, view)
        apply_snapshot(db, instance, view)
        assert len(instance.tasks) == 2
        assert all(t.provider == "FLOWABLE" for t in instance.tasks)
        assert len({t.engine_task_id for t in instance.tasks}) == 2
        with pytest.raises(HTTPException):
            apply_snapshot(db, instance, {**view, "definition_id": "foreign"})
        with pytest.raises(HTTPException):
            apply_snapshot(db, instance, {**view, "tasks": []})
        with pytest.raises(HTTPException):
            apply_snapshot(db, instance, {**view, "context": {**context, "round_id": 999}})
        finished = {
            **view,
            "tasks": [],
            "status": "COMPLETED",
            "completed_at": "2026-11-05T10:01:00+00:00",
            "history_tasks": [
                {**t, "completed_at": "2026-11-05T10:01:00+00:00", "delete_reason": None}
                for t in tasks
            ],
        }
        apply_snapshot(db, instance, finished)
        apply_snapshot(db, instance, view)
        assert instance.status == "COMPLETED", (
            "Late snapshot must not resurrect a terminal instance"
        )
        db.rollback()
