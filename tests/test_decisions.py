"""决策表：命中策略与求值。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _table(client) -> dict:
    code = "DMN" + uuid.uuid4().hex[:6].upper()
    created = client.post(
        f"{API}/decisions",
        json={
            "code": code,
            "name": "采购审批分级",
            "hit_policy": "FIRST",
            "inputs": [
                {"name": "amount", "label": "金额", "type": "number"},
                {"name": "urgent", "label": "加急", "type": "boolean"},
            ],
            "outputs": [{"name": "level", "label": "审批级别"}],
            "rules": [
                {"conditions": {"amount": {"op": "gt", "value": 10000}}, "outputs": {"level": "A"}},
                {"conditions": {"urgent": True}, "outputs": {"level": "B"}},
                {"conditions": {"amount": {"op": "always"}}, "outputs": {"level": "C"}},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_decision_first_hit(client, viewer_client):
    table = _table(client)
    high = client.post(
        f"{API}/decisions/{table['code']}/evaluate",
        json={"inputs": {"amount": 20000, "urgent": False}},
    )
    assert high.status_code == 200, high.text
    assert high.json()["outputs"]["level"] == "A"
    assert high.json()["matched_count"] == 1

    urgent = client.post(
        f"{API}/decisions/{table['code']}/evaluate",
        json={"inputs": {"amount": 500, "urgent": True}},
    )
    assert urgent.json()["outputs"]["level"] == "B"

    normal = client.post(
        f"{API}/decisions/{table['code']}/evaluate",
        json={"inputs": {"amount": 500, "urgent": False}},
    )
    assert normal.json()["outputs"]["level"] == "C"

    assert (
        viewer_client.post(
            f"{API}/decisions",
            json={"code": "DMNX" + uuid.uuid4().hex[:4], "name": "越权"},
        ).status_code
        == 403
    )
    assert (
        viewer_client.post(
            f"{API}/decisions/{table['code']}/evaluate", json={"inputs": {"amount": 1}}
        ).status_code
        == 200
    )


def test_decision_update_bumps_version(client):
    table = _table(client)
    updated = client.patch(f"{API}/decisions/{table['id']}", json={"description": "补充说明"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
