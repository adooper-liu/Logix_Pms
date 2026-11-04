"""三类型正式分类：继承、例外、未知、并发与原消费一致。"""

from uuid import uuid4

import pytest

API = "/api/v1/process-map"


@pytest.fixture
def classification_tree(client):
    prefix = "CLS-" + uuid4().hex[:8]
    ids = []
    parent = None
    for level in range(1, 5):
        response = client.post(
            API,
            json={
                "code": f"{prefix}-{level}",
                "name": f"分类测试{level}",
                "level": level,
                "parent_id": parent,
            },
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
        parent = ids[-1]
    yield ids
    assert client.delete(f"{API}/{ids[0]}").status_code == 200


def classify(client, ident, kind=None, basis="", inherit=True, revision=0):
    return client.put(
        f"{API}/{ident}/classification",
        json={
            "process_type": kind,
            "classification_basis": basis,
            "classification_inherit": inherit,
            "expected_revision": revision,
        },
    )


def test_flat_new_process_between_classification_and_list(client, monkeypatch):
    from app.api.v1 import process_map
    from app.core.database import SessionLocal
    from app.models.process import ProcessArch

    original = process_map.classification_service.resolve_all
    created = []

    def insert_after_snapshot(rows):
        snapshot = original(rows)
        if not created:
            with SessionLocal() as writer:
                row = ProcessArch(code="CLS-RACE-" + uuid4().hex[:8], name="查询期间新建", level=3)
                writer.add(row)
                writer.commit()
                created.append(row.id)
        return snapshot

    monkeypatch.setattr(process_map.classification_service, "resolve_all", insert_after_snapshot)
    try:
        response = client.get(API + "/flat")
        assert response.status_code == 200, response.text
    finally:
        for ident in created:
            client.delete(f"{API}/{ident}")


def test_flat_process_removed_between_output_and_classification(client, monkeypatch):
    from app.api.v1 import process_map

    original = process_map.classification_service.resolve_all
    removed = []

    def missing_snapshot(rows):
        snapshot = original(rows)
        if rows:
            removed.append(rows[-1].id)
            snapshot.pop(rows[-1].id)
        return snapshot

    monkeypatch.setattr(process_map.classification_service, "resolve_all", missing_snapshot)
    response = client.get(API + "/flat")
    assert response.status_code == 200, response.text
    assert not any(row["id"] in removed for row in response.json())


def test_classification_meta_and_unknown_history(client, classification_tree):
    meta = client.get(f"{API}/classification-meta")
    assert meta.status_code == 200
    assert meta.json()["process_types"] == {
        "CORE": "核心流程",
        "SUPPORT": "支持流程",
        "MANAGEMENT": "管理流程",
    }
    row = client.get(f"{API}/{classification_tree[2]}").json()
    assert row["process_type"] is None
    assert row["effective_process_type"] is None
    assert row["process_type_label"] == "未明确"
    assert row["classification_revision"] == 0


def test_inheritance_override_and_block(client, classification_tree):
    root, mid, leaf, activity = classification_tree
    result = classify(client, root, "CORE", "直接交付客户价值")
    assert result.status_code == 200, result.text
    assert result.json()["classification_revision"] == 1
    inherited = client.get(f"{API}/{activity}").json()
    assert inherited["effective_process_type"] == "CORE"
    assert inherited["classification_source_id"] == root
    assert inherited["classification_is_inherited"] is True
    assert classify(client, leaf, "SUPPORT", "为该价值链提供保障").status_code == 200
    override = client.get(f"{API}/{leaf}").json()
    assert override["classification_is_override"] is True
    assert override["process_type_label"] == "支持流程"
    assert client.get(f"{API}/{activity}").json()["classification_source_id"] == leaf
    assert classify(client, mid, None, "本分支待重新确认", False).status_code == 200
    assert client.get(f"{API}/{mid}").json()["effective_process_type"] is None
    assert client.get(f"{API}/{leaf}").json()["effective_process_type"] == "SUPPORT"
    assert classify(client, leaf, None, "", True, 1).status_code == 200
    assert client.get(f"{API}/{activity}").json()["effective_process_type"] is None
    assert classify(client, mid, None, "", True, 1).status_code == 200
    assert classify(client, root, "MANAGEMENT", "统筹经营与治理", revision=1).status_code == 200
    assert client.get(f"{API}/{activity}").json()["effective_process_type"] == "MANAGEMENT"


def test_classification_validation_revision_and_permissions(
    client, viewer_client, owner_client, classification_tree
):
    ident = classification_tree[0]
    assert classify(client, ident, "CORE").status_code == 422
    assert classify(client, ident, None, "", False).status_code == 422
    assert classify(client, ident, "NOT_A_TYPE", "错误值").status_code == 422
    assert classify(viewer_client, ident, "CORE", "不允许").status_code == 403
    assert classify(owner_client, ident, "CORE", "不允许").status_code == 403
    before = client.get(f"{API}/{ident}").json()
    assert classify(client, ident, "CORE", "客户交付").status_code == 200
    assert classify(client, ident, "SUPPORT", "旧页覆盖").status_code == 409
    after = client.get(f"{API}/{ident}").json()
    assert after["process_type"] == "CORE"
    assert after["priority_score"] == before["priority_score"]
    assert after["level"] == before["level"]


def test_type_filter_keeps_ancestors_and_card_matches(client, classification_tree):
    root, mid, leaf, activity = classification_tree
    assert classify(client, root, "CORE", "客户交付").status_code == 200
    assert classify(client, leaf, "SUPPORT", "保障服务").status_code == 200
    flat = client.get(f"{API}/flat?process_type=SUPPORT").json()
    assert {r["id"] for r in flat}.intersection(classification_tree) == {leaf, activity}
    trees = client.get(f"{API}/tree?process_type=SUPPORT").json()
    branch = next(r for r in trees if r["id"] == root)
    assert branch["classification_matches_filter"] is False
    assert branch["children"][0]["classification_matches_filter"] is False
    assert branch["children"][0]["children"][0]["classification_matches_filter"] is True
    card = client.get(f"/api/v1/process-card/{leaf}").json()["process"]
    assert card["effective_process_type"] == "SUPPORT"
    assert card["classification_source_id"] == leaf
    unknown = client.get(f"{API}/flat?process_type=UNCLASSIFIED").json()
    assert not set(classification_tree).intersection(r["id"] for r in unknown)
    assert client.get(f"{API}/tree?process_type=INVALID").status_code == 422


def test_new_child_and_generic_patch_keep_inherited_output(client, classification_tree):
    root = classification_tree[0]
    assert classify(client, root, "CORE", "客户价值").status_code == 200
    response = client.post(
        API,
        json={"code": "NEW-" + uuid4().hex[:8], "name": "继承子项", "level": 2, "parent_id": root},
    )
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["effective_process_type"] == "CORE"
    assert child["classification_source_id"] == root
    updated = client.patch(f"{API}/{child['id']}", json={"name": "改名不改分类"})
    assert updated.status_code == 200
    assert updated.json()["effective_process_type"] == "CORE"
    assert updated.json()["classification_revision"] == 0


def test_classification_resolver_cycle_fails_closed():
    from types import SimpleNamespace

    from app.services.process_classification import resolve_all

    rows = [
        SimpleNamespace(
            id=1, code="A", parent_id=2, process_type=None, classification_inherit=True
        ),
        SimpleNamespace(
            id=2, code="B", parent_id=1, process_type=None, classification_inherit=True
        ),
    ]
    resolved = resolve_all(rows)
    assert resolved[1]["effective_process_type"] is None
    assert resolved[2]["effective_process_type"] is None
