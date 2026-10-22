"""组织单元与资产范围：树、权限、集团通用 + 上级继承。"""

from __future__ import annotations

API = "/api/v1"


def _orgs(client) -> dict:
    rows = client.get(f"{API}/org-units").json()
    return {row["code"]: row for row in rows}


def _create_document(client, process_id: int, title: str, org_unit_id=None):
    payload = {"process_id": process_id, "title": title, "category": "SOP"}
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    r = client.post(f"{API}/process-documents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_template(client, tool_code: str, name: str, org_unit_id=None):
    payload = {"tool_code": tool_code, "name": name, "format": "XLSX"}
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    r = client.post(f"{API}/tool-templates", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_org_tree_and_admin_permissions(client, manager_client, viewer_client):
    meta = client.get(f"{API}/org-units/meta").json()
    assert meta["type_labels"]["GROUP"] == "集团"
    assert meta["type_labels"]["COMPANY"] == "公司/分公司"

    tree = client.get(f"{API}/org-units/tree").json()
    group = next(node for node in tree if node["code"] == "GROUP-001")
    assert {child["code"] for child in group["children"]} >= {"CO-EAST", "CO-SOUTH"}
    east = next(child for child in group["children"] if child["code"] == "CO-EAST")
    assert {child["code"] for child in east["children"]} >= {"DEPT-EAST-MFG", "DEPT-EAST-QA"}

    body = {
        "parent_id": east["id"],
        "code": "DEPT-EAST-TEST",
        "name": "华东测试部",
        "type": "DEPARTMENT",
    }
    assert viewer_client.post(f"{API}/org-units", json=body).status_code == 403
    assert manager_client.post(f"{API}/org-units", json=body).status_code == 403  # 主数据仅管理员

    r = client.post(f"{API}/org-units", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["type_label"] == "部门"
    assert created["path"].startswith(east["path"])
    assert created["parent_id"] == east["id"]

    assert client.post(f"{API}/org-units", json=body).status_code == 409
    r = client.post(
        f"{API}/org-units",
        json={"parent_id": 999999, "code": "X-1", "name": "无父节点", "type": "COMPANY"},
    )
    assert r.status_code == 400

    r = client.patch(f"{API}/org-units/{created['id']}", json={"name": "华东测试中心"})
    assert r.status_code == 200 and r.json()["name"] == "华东测试中心"

    assert client.delete(f"{API}/org-units/{created['id']}").status_code == 200
    # 有下级的组织不能直接删
    r = client.delete(f"{API}/org-units/{east['id']}")
    assert r.status_code == 409


def test_document_scope_inheritance(client, manager_client):
    orgs = _orgs(client)
    group = orgs["GROUP-001"]
    east = orgs["CO-EAST"]
    south = orgs["CO-SOUTH"]
    process_id = client.get(f"{API}/process-map/flat").json()[0]["id"]

    common = _create_document(manager_client, process_id, "集团通用 SOP")
    hq = _create_document(manager_client, process_id, "集团总部 SOP", group["id"])
    east_doc = _create_document(manager_client, process_id, "华东 SOP", east["id"])
    south_doc = _create_document(manager_client, process_id, "华南 SOP", south["id"])
    assert common["scope_label"] == "集团通用"
    assert east_doc["scope_label"] == "华东分公司"

    def ids(query):
        return {row["id"] for row in client.get(f"{API}/process-documents", params=query).json()}

    east_ids = ids({"org_unit_id": east["id"]})
    assert {common["id"], hq["id"], east_doc["id"]} <= east_ids
    assert south_doc["id"] not in east_ids

    south_ids = ids({"org_unit_id": south["id"]})
    assert {common["id"], hq["id"], south_doc["id"]} <= south_ids
    assert east_doc["id"] not in south_ids

    all_ids = ids({})
    assert {common["id"], hq["id"], east_doc["id"], south_doc["id"]} <= all_ids

    r = manager_client.post(
        f"{API}/process-documents",
        json={
            "process_id": process_id,
            "title": "无效组织",
            "category": "SOP",
            "org_unit_id": 999999,
        },
    )
    assert r.status_code == 400


def test_template_scope_inheritance(client, manager_client):
    orgs = _orgs(client)
    group = orgs["GROUP-001"]
    east = orgs["CO-EAST"]
    south = orgs["CO-SOUTH"]

    common = _create_template(manager_client, "KB", "集团通用 SIPOC", None)
    hq = _create_template(manager_client, "KB", "总部 SIPOC", group["id"])
    east_tpl = _create_template(manager_client, "KB", "华东 SIPOC", east["id"])
    south_tpl = _create_template(manager_client, "KB", "华南 SIPOC", south["id"])
    assert common["scope_label"] == "集团通用"
    assert east_tpl["scope_org_code"] == "CO-EAST"

    east_ids = {
        row["id"]
        for row in client.get(f"{API}/tool-templates", params={"org_unit_id": east["id"]}).json()
    }
    assert {common["id"], hq["id"], east_tpl["id"]} <= east_ids
    assert south_tpl["id"] not in east_ids

    r = manager_client.post(
        f"{API}/tool-templates",
        json={
            "tool_code": "SIPOC",
            "name": "无效组织模板",
            "format": "XLSX",
            "org_unit_id": 999999,
        },
    )
    assert r.status_code == 400


def test_org_delete_blocked_by_document(client, manager_client):
    org = client.post(
        f"{API}/org-units",
        json={
            "parent_id": _orgs(client)["CO-EAST"]["id"],
            "code": "DEPT-DOC",
            "name": "有文档的部门",
            "type": "DEPARTMENT",
        },
    ).json()
    process_id = client.get(f"{API}/process-map/flat").json()[0]["id"]
    _create_document(manager_client, process_id, "部门 SOP", org["id"])

    r = client.delete(f"{API}/org-units/{org['id']}")
    assert r.status_code == 409
    assert "标准文件" in r.json()["detail"]

    # 停用后不再出现在默认清单里
    assert (
        client.patch(f"{API}/org-units/{org['id']}", json={"is_active": False}).status_code == 200
    )
    codes = {row["code"] for row in client.get(f"{API}/org-units").json()}
    assert "DEPT-DOC" not in codes
