"""发布策略、禁止自评自发、发布预览。"""

from __future__ import annotations

API = "/api/v1"


def _create(client, code: str = "L3-PPOL") -> int:
    response = client.post(
        f"{API}/process-map",
        json={"code": code, "name": "发布策略测试", "level": 3},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _save(client, pid: int, version_note: str = "a") -> int:
    saved = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {
                    "node_key": version_note,
                    "name": "活动",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 10,
                }
            ],
            "edges": [],
        },
    )
    assert saved.status_code == 200, saved.text
    return saved.json()["version"]


def test_review_required_blocks_direct_publish(client, manager_client):
    pid = _create(client, "L3-PREV")
    try:
        assert client.get(f"{API}/process-map/{pid}").json()["publish_policy"] == (
            "review_required"
        )
        ver = _save(client, pid)
        blocked = manager_client.post(
            f"{API}/processes/{pid}/design/publish",
            json={"expected_version": ver, "change_note": "首次发布说明"},
        )
        assert blocked.status_code == 409, blocked.text
        assert "提交评审" in blocked.json()["detail"]

        preview = manager_client.get(f"{API}/processes/{pid}/design/publish-preview").json()
        assert preview["can_publish"] is False
        assert any("提交评审" in msg for msg in preview["blockers"])

        assert (
            client.post(
                f"{API}/processes/{pid}/design/submit-review", json={"note": "请审"}
            ).status_code
            == 200
        )
        # same author (admin created) — manager can publish without self reason
        published = manager_client.post(
            f"{API}/processes/{pid}/design/publish",
            json={"expected_version": ver, "change_note": "评审后发布说明"},
        )
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "PUBLISHED"
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_self_publish_requires_reason_on_direct(client):
    pid = _create(client, "L3-PSLF")
    try:
        assert (
            client.patch(f"{API}/process-map/{pid}", json={"publish_policy": "direct"}).status_code
            == 200
        )
        ver = _save(client, pid)
        blocked = client.post(
            f"{API}/processes/{pid}/design/publish",
            json={"expected_version": ver, "change_note": "首次发布说明"},
        )
        assert blocked.status_code == 409, blocked.text
        assert "同一人" in blocked.json()["detail"]

        preview = client.get(f"{API}/processes/{pid}/design/publish-preview").json()
        assert preview["self_publish_reason_required"] is True
        assert preview["can_publish"] is True

        ok = client.post(
            f"{API}/processes/{pid}/design/publish",
            json={
                "expected_version": ver,
                "change_note": "首次发布说明",
                "self_publish_reason": "自动化测试环境豁免四人复核",
            },
        )
        assert ok.status_code == 200, ok.text
        note = client.get(
            f"{API}/processes/{pid}/design/versions/{ok.json()['version_id']}"
        ).json()["change_note"]
        assert "自评自发豁免" in note
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_change_note_required(client, manager_client):
    pid = _create(client, "L3-PNOT")
    try:
        client.patch(f"{API}/process-map/{pid}", json={"publish_policy": "direct"})
        ver = _save(client, pid)
        # manager publishes admin's draft — not same author; still needs note
        bad = manager_client.post(
            f"{API}/processes/{pid}/design/publish",
            json={"expected_version": ver, "change_note": "短"},
        )
        assert bad.status_code == 422, bad.text
    finally:
        client.delete(f"{API}/process-map/{pid}")
