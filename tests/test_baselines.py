"""资产基线：快照、组织/流程范围、与当前有效版本的差异。"""

from __future__ import annotations

API = "/api/v1"
BYTES = b"PK\x03\x04" + b"baseline asset"


def _orgs(client) -> dict:
    return {row["code"]: row for row in client.get(f"{API}/org-units").json()}


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _doc(client, process_id, title, org_unit_id=None) -> dict:
    payload = {"process_id": process_id, "title": title, "category": "SOP"}
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    r = client.post(f"{API}/process-documents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _serve_doc(client, document_id, label, valid_from="2026-01-01") -> dict:
    r = client.post(
        f"{API}/process-documents/{document_id}/versions/upload",
        files={"file": (f"d{label}.docx", BYTES, "application/octet-stream")},
        data={"version_label": label, "valid_from": valid_from},
    )
    assert r.status_code == 201, r.text
    version = r.json()
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = client.post(
            f"{API}/process-documents/{document_id}/versions/{version['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text
    return version


def _template(client, name, org_unit_id=None) -> dict:
    payload = {"tool_code": "KB", "name": name, "format": "XLSX"}
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    r = client.post(f"{API}/tool-templates", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _serve_template(client, template_id, label="1.0.0") -> dict:
    r = client.post(
        f"{API}/tool-templates/{template_id}/versions/upload",
        files={"file": (f"t{label}.xlsx", BYTES, "application/octet-stream")},
        data={"version_label": label},
    )
    assert r.status_code == 201, r.text
    version = r.json()
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = client.post(
            f"{API}/tool-templates/{template_id}/versions/{version['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text
    return version


def _diff(client, baseline_id) -> dict:
    r = client.get(f"{API}/baselines/{baseline_id}/diff")
    assert r.status_code == 200, r.text
    return r.json()


def test_baseline_lifecycle_changed_added_removed(client, manager_client, viewer_client):
    process_id = _process_id(client, "L3-032")
    document = _doc(manager_client, process_id, "基线生命周期 SOP")
    _serve_doc(manager_client, document["id"], "1.0")
    template = _template(manager_client, "基线生命周期模板")
    _serve_template(manager_client, template["id"])
    # 基线创建后再停用，用来验证 REMOVED
    removed = _doc(manager_client, process_id, "基线后被停用 SOP")
    _serve_doc(manager_client, removed["id"], "1.0")

    assert (
        viewer_client.post(
            f"{API}/baselines", json={"name": "只读不能建", "scope": "ALL"}
        ).status_code
        == 403
    )

    r = manager_client.post(f"{API}/baselines", json={"name": "季度标准基线", "scope": "ALL"})
    assert r.status_code == 201, r.text
    baseline = r.json()
    assert baseline["scope_label"] == "全部资产"
    assert baseline["item_count"] >= 2

    detail = client.get(f"{API}/baselines/{baseline['id']}").json()
    kinds = {item["kind"] for item in detail["items"]}
    assert "document" in kinds and "template" in kinds
    doc_item = next(
        item
        for item in detail["items"]
        if item["kind"] == "document" and item["id"] == document["id"]
    )
    assert doc_item["version_display"] == "v1.0"

    # 发布新版本 → CHANGED
    _serve_doc(manager_client, document["id"], "1.1")
    # 新标准文件 → ADDED
    added = _doc(manager_client, process_id, "基线后新增 SOP")
    _serve_doc(manager_client, added["id"], "1.0")
    # 停用 → REMOVED
    assert (
        manager_client.patch(
            f"{API}/process-documents/{removed['id']}", json={"is_active": False}
        ).status_code
        == 200
    )

    diff = _diff(client, baseline["id"])
    by_key = {(item["kind"], item["id"]): item for item in diff["items"]}
    changed = by_key[("document", document["id"])]
    assert changed["status"] == "CHANGED"
    assert changed["old_version_display"] == "v1.0"
    assert changed["new_version_display"] == "v1.1"
    assert by_key[("document", added["id"])]["status"] == "ADDED"
    assert by_key[("document", removed["id"])]["status"] == "REMOVED"
    assert diff["counts"]["CHANGED"] >= 1
    assert diff["counts"]["ADDED"] >= 1
    assert diff["counts"]["REMOVED"] >= 1

    # 基线本身不可变：明细仍是创建时的版本
    detail = client.get(f"{API}/baselines/{baseline['id']}").json()
    doc_item = next(
        item
        for item in detail["items"]
        if item["kind"] == "document" and item["id"] == document["id"]
    )
    assert doc_item["version_display"] == "v1.0"


def test_baseline_scope_org_and_process(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client, "L3-032")
    other_process = _process_id(client, "L3-010")

    group_doc = _doc(manager_client, process_id, "范围集团 SOP")
    _serve_doc(manager_client, group_doc["id"], "1.0")
    east_doc = _doc(manager_client, process_id, "范围华东 SOP", orgs["CO-EAST"]["id"])
    _serve_doc(manager_client, east_doc["id"], "1.0")
    south_doc = _doc(manager_client, process_id, "范围华南 SOP", orgs["CO-SOUTH"]["id"])
    _serve_doc(manager_client, south_doc["id"], "1.0")
    other_doc = _doc(manager_client, other_process, "范围其他流程 SOP")
    _serve_doc(manager_client, other_doc["id"], "1.0")

    _serve_template(manager_client, _template(manager_client, "范围集团模板")["id"])

    r = manager_client.post(
        f"{API}/baselines",
        json={
            "name": "华东组织基线",
            "scope": "ORG",
            "org_unit_id": orgs["CO-EAST"]["id"],
        },
    )
    assert r.status_code == 201, r.text
    org_baseline = client.get(f"{API}/baselines/{r.json()['id']}").json()
    ids = {item["id"] for item in org_baseline["items"] if item["kind"] == "document"}
    assert group_doc["id"] in ids and east_doc["id"] in ids
    assert south_doc["id"] not in ids

    r = manager_client.post(
        f"{API}/baselines",
        json={"name": "L3-032 流程基线", "scope": "PROCESS", "process_id": process_id},
    )
    assert r.status_code == 201, r.text
    process_baseline = client.get(f"{API}/baselines/{r.json()['id']}").json()
    process_ids = {item["id"] for item in process_baseline["items"] if item["kind"] == "document"}
    assert group_doc["id"] in process_ids and east_doc["id"] in process_ids
    assert other_doc["id"] not in process_ids
    assert all(item["kind"] == "document" for item in process_baseline["items"])

    # 参数校验
    assert (
        manager_client.post(
            f"{API}/baselines", json={"name": "缺流程", "scope": "PROCESS"}
        ).status_code
        == 400
    )
    assert (
        manager_client.post(f"{API}/baselines", json={"name": "缺组织", "scope": "ORG"}).status_code
        == 400
    )
    assert (
        manager_client.post(
            f"{API}/baselines",
            json={"name": "组织不存在", "scope": "ORG", "org_unit_id": 999999},
        ).status_code
        == 400
    )


def test_baseline_list_and_meta(client):
    meta = client.get(f"{API}/baselines/meta").json()
    assert meta["scope_labels"]["ALL"] == "全部资产"
    assert meta["diff_status_labels"]["CHANGED"] == "已变更"

    rows = client.get(f"{API}/baselines").json()
    assert isinstance(rows, list) and rows
    assert all("code" in row and row["code"].startswith("BL-") for row in rows)
