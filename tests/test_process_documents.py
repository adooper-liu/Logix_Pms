"""流程标准配套文件：版本、审批、复制到项目、晋升与范围校验。"""

from __future__ import annotations

import hashlib

API = "/api/v1"

DOCX_BYTES = b"PK\x03\x04" + b"fake standard document"
XLSX_BYTES = b"PK\x03\x04" + b"fake standard form"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _create_document(client, process_id: int, title: str, category: str = "SOP", **extra):
    r = client.post(
        f"{API}/process-documents",
        json={"process_id": process_id, "title": title, "category": category, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, document_id: int, name: str, content: bytes, label: str, **data):
    return client.post(
        f"{API}/process-documents/{document_id}/versions/upload",
        files={"file": (name, content, "application/octet-stream")},
        data={"version_label": label, **data},
    )


def _transition(client, document_id: int, version_id: int, target: str):
    return client.post(
        f"{API}/process-documents/{document_id}/versions/{version_id}/transition",
        json={"status": target},
    )


def _make_effective(client, document_id: int, version_id: int) -> dict:
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = _transition(client, document_id, version_id, target)
        assert r.status_code == 200, r.text
    return r.json()


def _create_project(client, process_id=None, owner: str = "流程管理科") -> dict:
    payload = {
        "name": "标准文件测试项目",
        "methodology": "BPI",
        "owner": owner,
        "start_date": "2026-10-01",
        "end_date": "2027-03-31",
    }
    if process_id is not None:
        payload["process_id"] = process_id
    r = client.post(f"{API}/projects", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _instance(client, project_id: int, step_no: str = "2.1") -> dict:
    rows = client.get(f"{API}/projects/{project_id}/deliverables").json()
    return next(row for row in rows if row["step_no"] == step_no)


# ------------------------------------------------------------------ 文档与版本


def test_document_create_upload_and_approve(client, manager_client, viewer_client):
    process_id = _process_id(client, "L3-032")
    assert (
        viewer_client.post(
            f"{API}/process-documents",
            json={"process_id": process_id, "title": "只读不能建", "category": "SOP"},
        ).status_code
        == 403
    )

    document = _create_document(client, process_id, "采购需求提报 SOP")
    assert document["code"].startswith("PD-L3-032-")
    assert document["category_label"] == "SOP"
    assert document["process_code"] == "L3-032"
    assert document["version_count"] == 0

    r = manager_client.post(
        f"{API}/process-documents",
        json={
            "process_id": process_id,
            "code": document["code"],
            "title": "重复编码",
            "category": "SOP",
        },
    )
    assert r.status_code == 409

    r = manager_client.post(
        f"{API}/process-documents",
        json={"process_id": 999999, "title": "流程不存在", "category": "SOP"},
    )
    assert r.status_code == 400

    r = _upload(
        manager_client,
        document["id"],
        "采购SOP.docx",
        DOCX_BYTES,
        "1.0",
        note="首版",
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["version_display"] == "v1.0"
    assert version["status"] == "DRAFT"
    assert version["checksum"] == hashlib.sha256(DOCX_BYTES).hexdigest()
    assert version["has_file"] is True

    # 登录用户都能下载
    r = viewer_client.get(
        f"{API}/process-documents/{document['id']}/versions/{version['id']}/download"
    )
    assert r.status_code == 200
    assert r.content == DOCX_BYTES

    # 版本号格式与唯一性
    assert _upload(manager_client, document["id"], "x.docx", DOCX_BYTES, "v1").status_code == 400
    assert _upload(manager_client, document["id"], "x.docx", DOCX_BYTES, "1.0").status_code == 400

    _make_effective(manager_client, document["id"], version["id"])
    detail = client.get(f"{API}/process-documents/{document['id']}").json()
    assert detail["effective_version"]["version_label"] == "1.0"

    v2 = _upload(manager_client, document["id"], "采购SOP-v11.docx", DOCX_BYTES, "1.1").json()
    _make_effective(manager_client, document["id"], v2["id"])
    detail = client.get(f"{API}/process-documents/{document['id']}").json()
    statuses = {v["version_display"]: v["status"] for v in detail["versions"]}
    assert statuses == {"v1.0": "SUPERSEDED", "v1.1": "EFFECTIVE"}


# ------------------------------------------------------------------ 复制到项目


def test_copy_standard_document_to_project(client, manager_client):
    process_id = _process_id(client, "L3-032")
    document = _create_document(client, process_id, "采购申请单模板", "FORM")
    version = _upload(manager_client, document["id"], "采购申请单.xlsx", XLSX_BYTES, "2.0").json()
    _make_effective(manager_client, document["id"], version["id"])

    project = _create_project(client, process_id)
    instance = _instance(client, project["id"])

    r = manager_client.post(
        f"{API}/process-documents/{document['id']}/versions/{version['id']}/copy-to-deliverable",
        json={"deliverable_instance_id": instance["id"], "title": "本项目采购申请单"},
    )
    assert r.status_code == 201, r.text
    copied = r.json()
    assert copied["version_label"] == "R1"
    assert copied["source_document_version_id"] == version["id"]
    assert copied["checksum"] == hashlib.sha256(XLSX_BYTES).hexdigest()

    r = client.get(copied["download_url"])
    assert r.status_code == 200 and r.content == XLSX_BYTES

    # 子节点（L4）的标准文件不适用于挂在 L3 的项目
    child_id = _process_id(client, "L4-201")
    child_doc = _create_document(manager_client, child_id, "L4 点检表", "CHECKLIST")
    child_version = _upload(manager_client, child_doc["id"], "check.xlsx", XLSX_BYTES, "1.0").json()
    _make_effective(manager_client, child_doc["id"], child_version["id"])
    r = manager_client.post(
        f"{API}/process-documents/{child_doc['id']}/versions/{child_version['id']}"
        "/copy-to-deliverable",
        json={"deliverable_instance_id": instance["id"]},
    )
    assert r.status_code == 400
    assert "不属于" in r.json()["detail"]


def test_manual_deliverable_upload_records_source_document(client, manager_client):
    process_id = _process_id(client, "L3-032")
    document = _create_document(client, process_id, "根因分析规范", "SOP")
    version = _upload(manager_client, document["id"], "rca.docx", DOCX_BYTES, "1.0").json()
    _make_effective(manager_client, document["id"], version["id"])

    project = _create_project(client, process_id)
    instance = _instance(client, project["id"], "2.3")

    r = client.post(
        f"{API}/deliverables/{instance['id']}/versions/upload",
        files={"file": ("rca.docx", DOCX_BYTES, "application/octet-stream")},
        data={"source_document_version_id": str(version["id"])},
    )
    assert r.status_code == 201, r.text
    assert r.json()["source_document_version_id"] == version["id"]

    # 草稿标准版本不能作为来源
    draft = _upload(manager_client, document["id"], "draft.docx", DOCX_BYTES, "1.1").json()
    r = client.post(
        f"{API}/deliverables/{instance['id']}/versions/upload",
        files={"file": ("rca2.docx", DOCX_BYTES, "application/octet-stream")},
        data={"source_document_version_id": str(draft["id"])},
    )
    assert r.status_code == 400
    assert "已生效" in r.json()["detail"]


# ------------------------------------------------------------------ 晋升


def test_promote_deliverable_to_standard_draft(client, manager_client):
    process_id = _process_id(client, "L3-032")
    document = _create_document(client, process_id, "采购流程 SOP", "SOP")

    project = _create_project(client, process_id)
    instance = _instance(client, project["id"], "3.5")
    r = client.post(
        f"{API}/deliverables/{instance['id']}/versions/upload",
        files={"file": ("新SOP.docx", DOCX_BYTES, "application/octet-stream")},
        data={"title": "改善后的 SOP"},
    )
    deliverable_version = r.json()
    for target in ("IN_REVIEW", "APPROVED"):
        r = client.post(
            f"{API}/deliverables/{instance['id']}/versions/{deliverable_version['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text

    r = manager_client.post(
        f"{API}/process-documents/{document['id']}/promote",
        json={"deliverable_version_id": deliverable_version["id"], "version_label": "2.0"},
    )
    assert r.status_code == 201, r.text
    promoted = r.json()
    assert promoted["version_display"] == "v2.0"
    assert promoted["status"] == "DRAFT"
    assert promoted["source_deliverable_version_id"] == deliverable_version["id"]
    assert project["code"] in promoted["source_label"]

    r = manager_client.get(
        f"{API}/process-documents/{document['id']}/versions/{promoted['id']}/download"
    )
    assert r.status_code == 200 and r.content == DOCX_BYTES

    # 同一目标版本号不能重复
    r = manager_client.post(
        f"{API}/process-documents/{document['id']}/promote",
        json={"deliverable_version_id": deliverable_version["id"], "version_label": "2.0"},
    )
    assert r.status_code == 400

    # 未关联流程的项目不能晋升
    loose_project = _create_project(client, None)
    loose_instance = _instance(client, loose_project["id"], "3.5")
    loose_version = client.post(
        f"{API}/deliverables/{loose_instance['id']}/versions/upload",
        files={"file": ("loose.docx", DOCX_BYTES, "application/octet-stream")},
    ).json()
    for target in ("IN_REVIEW", "APPROVED"):
        client.post(
            f"{API}/deliverables/{loose_instance['id']}/versions/{loose_version['id']}/transition",
            json={"status": target},
        )
    r = manager_client.post(
        f"{API}/process-documents/{document['id']}/promote",
        json={"deliverable_version_id": loose_version["id"], "version_label": "3.0"},
    )
    assert r.status_code == 400
    assert "未关联流程" in r.json()["detail"]


# ------------------------------------------------------------------ 权限、删除、范围筛选


def test_document_permissions_and_delete_guard(client, manager_client, viewer_client, owner_client):
    process_id = _process_id(client, "L3-032")
    document = _create_document(client, process_id, "待删除文档", "OTHER")

    assert manager_client.delete(f"{API}/process-documents/{document['id']}").status_code == 200

    with_version = _create_document(client, process_id, "有版本文档", "SOP")
    version = _upload(manager_client, with_version["id"], "a.docx", DOCX_BYTES, "1.0").json()
    _make_effective(manager_client, with_version["id"], version["id"])
    assert manager_client.delete(f"{API}/process-documents/{with_version['id']}").status_code == 409

    # 只读不能上传/审批
    assert (
        viewer_client.post(
            f"{API}/process-documents/{with_version['id']}/versions/upload",
            files={"file": ("x.docx", DOCX_BYTES, "application/octet-stream")},
            data={"version_label": "9.9"},
        ).status_code
        == 403
    )
    assert (
        viewer_client.post(
            f"{API}/process-documents/{with_version['id']}/promote",
            json={"deliverable_version_id": 1, "version_label": "9.9"},
        ).status_code
        == 403
    )

    # 复制到他人项目：OWNER 只能操作自己名下
    project = _create_project(client, process_id, owner="流程管理科")
    instance = _instance(client, project["id"])
    assert (
        owner_client.post(
            f"{API}/process-documents/{with_version['id']}/versions/{version['id']}"
            "/copy-to-deliverable",
            json={"deliverable_instance_id": instance["id"]},
        ).status_code
        == 403
    )


def test_document_list_scope_for_project(client, manager_client):
    process_id = _process_id(client, "L3-032")
    parent_id = _process_id(client, "L2-003")
    child_id = _process_id(client, "L4-201")
    doc_l3 = _create_document(client, process_id, "L3 标准文件", "SOP")
    doc_parent = _create_document(client, parent_id, "L2 父级标准文件", "POLICY")
    doc_child = _create_document(client, child_id, "L4 子级标准文件", "CHECKLIST")

    project = _create_project(client, process_id)
    rows = client.get(f"{API}/process-documents", params={"project_id": project["id"]}).json()
    ids = {row["id"] for row in rows}
    assert doc_l3["id"] in ids
    assert doc_parent["id"] in ids
    assert doc_child["id"] not in ids

    # 流程详情默认只看本节点；include_ancestors 才带上级继承
    direct = client.get(f"{API}/process-documents", params={"process_id": process_id}).json()
    direct_ids = {row["id"] for row in direct}
    assert doc_l3["id"] in direct_ids
    assert doc_parent["id"] not in direct_ids
    assert doc_child["id"] not in direct_ids

    inherited = client.get(
        f"{API}/process-documents",
        params={"process_id": process_id, "include_ancestors": True},
    ).json()
    inherited_ids = {row["id"] for row in inherited}
    assert doc_l3["id"] in inherited_ids
    assert doc_parent["id"] in inherited_ids
    assert doc_child["id"] not in inherited_ids
