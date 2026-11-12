"""P3b: explicit key-process fields and coverage matrix."""

from __future__ import annotations

import pytest
from conftest import API


@pytest.fixture(autouse=True)
def _cleanup_p3b_processes(client):
    yield
    rows = client.get(f"{API}/process-map/flat").json()
    for row in rows:
        if row["code"].startswith("P3B-T1-") and row["level"] in {1, 2, 3}:
            client.delete(f"{API}/process-map/{row['id']}")


def _create_process(client, code: str, **extra):
    payload = {
        "code": code,
        "name": f"{code} 测试流程",
        "level": 3,
        "parent_id": None,
        "strategic_importance": 3,
        "pain_score": 3,
        "improvement_space": 3,
        **extra,
    }
    return client.post(f"{API}/process-map", json=payload)


def test_key_process_requires_basis_on_create(client):
    response = _create_process(
        client,
        "P3B-T1-CREATE-MISSING-BASIS",
        is_key_process=True,
        key_basis="",
    )

    assert response.status_code == 422, response.text
    rows = client.get(
        f"{API}/process-map/flat",
        params={"keyword": "P3B-T1-CREATE-MISSING-BASIS"},
    ).json()
    assert rows == []


def test_key_process_requires_basis_on_update(client):
    created = _create_process(client, "P3B-T1-UPDATE-BASIS")
    assert created.status_code == 201, created.text
    process_id = created.json()["id"]

    missing = client.patch(
        f"{API}/process-map/{process_id}",
        json={"is_key_process": True},
    )
    assert missing.status_code == 422, missing.text

    updated = client.patch(
        f"{API}/process-map/{process_id}",
        json={"is_key_process": True, "key_basis": "关键客户订单履约风险"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_key_process"] is True
    assert updated.json()["key_basis"] == "关键客户订单履约风险"

    fetched = client.get(f"{API}/process-map/{process_id}")
    assert fetched.status_code == 200
    assert fetched.json()["is_key_process"] is True
    assert fetched.json()["key_basis"] == "关键客户订单履约风险"


def test_key_process_can_be_unchecked_and_basis_cleared(client):
    created = _create_process(
        client,
        "P3B-T1-CLEAR-BASIS",
        is_key_process=True,
        key_basis="本期经营关键过程",
    )
    assert created.status_code == 201, created.text
    process_id = created.json()["id"]

    updated = client.patch(
        f"{API}/process-map/{process_id}",
        json={"is_key_process": False, "key_basis": None},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_key_process"] is False
    assert updated.json()["key_basis"] is None


def test_key_process_null_boolean_is_rejected(client):
    created = _create_process(client, "P3B-T1-NULL-BOOL")
    assert created.status_code == 201, created.text
    response = client.patch(
        f"{API}/process-map/{created.json()['id']}",
        json={"is_key_process": None},
    )
    assert response.status_code == 422, response.text

    created = _create_process(client, "P3B-T1-DEFAULT")

    assert created.status_code == 201, created.text
    assert created.json()["is_key_process"] is False
    assert created.json()["key_basis"] is None
