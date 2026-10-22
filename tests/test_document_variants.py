"""流程标准文件的变体策略与有效版本解析。"""

from __future__ import annotations

API = "/api/v1"
BYTES = b"PK\x03\x04" + b"variant document"


def _orgs(client) -> dict:
    return {row["code"]: row for row in client.get(f"{API}/org-units").json()}


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _create_doc(
    client, process_id, title, org_unit_id=None, policy="PARAMETERIZED", variant_of=None
):
    payload = {
        "process_id": process_id,
        "title": title,
        "category": "SOP",
        "variation_policy": policy,
    }
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    if variant_of is not None:
        payload["variant_of_document_id"] = variant_of
    return client.post(f"{API}/process-documents", json=payload)


def _serve(client, document_id, label="1.0", valid_from="2026-01-01"):
    r = client.post(
        f"{API}/process-documents/{document_id}/versions/upload",
        files={"file": (f"v{label}.docx", BYTES, "application/octet-stream")},
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


def _effective(client, org_unit_id, process_id, on_date=None):
    params = {"org_unit_id": org_unit_id, "process_id": process_id}
    if on_date:
        params["date"] = on_date
    r = client.get(f"{API}/process-documents/effective", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_locked_policy_blocks_and_unlocks_variants(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    base = _create_doc(
        manager_client,
        process_id,
        "锁定策略标准 SOP",
        org_unit_id=orgs["GROUP-001"]["id"],
        policy="LOCKED",
    ).json()
    _serve(manager_client, base["id"])

    r = _create_doc(
        manager_client,
        process_id,
        "华东变体（应拒绝）",
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of=base["id"],
    )
    assert r.status_code == 400
    assert "锁定" in r.json()["detail"]

    assert (
        manager_client.patch(
            f"{API}/process-documents/{base['id']}", json={"variation_policy": "PARAMETERIZED"}
        ).status_code
        == 200
    )
    variant = _create_doc(
        manager_client,
        process_id,
        "华东变体",
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of=base["id"],
    )
    assert variant.status_code == 201, variant.text
    body = variant.json()
    assert body["variant_of_document_id"] == base["id"]
    assert body["variant_of_code"] == base["code"]
    assert body["variant_base_version_display"] == "v1.0"
    assert body["variation_policy_label"] == "参数可调"

    # 已有变体后不能再改回锁定
    r = manager_client.patch(
        f"{API}/process-documents/{base['id']}", json={"variation_policy": "LOCKED"}
    )
    assert r.status_code == 409


def test_variant_org_and_base_version_rules(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    base = _create_doc(
        manager_client, process_id, "总部标准 SOP", org_unit_id=orgs["GROUP-001"]["id"]
    ).json()
    _serve(manager_client, base["id"])

    # 同组织不能建变体
    r = _create_doc(
        manager_client,
        process_id,
        "同组织变体",
        org_unit_id=orgs["GROUP-001"]["id"],
        variant_of=base["id"],
    )
    assert r.status_code == 400
    assert "下级" in r.json()["detail"]

    # 上级没有生效版本时不能建变体
    draft_base = _create_doc(
        manager_client,
        process_id,
        "未生效标准 SOP",
        org_unit_id=orgs["GROUP-001"]["id"],
    ).json()
    r = _create_doc(
        manager_client,
        process_id,
        "变体无生效依据",
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of=draft_base["id"],
    )
    assert r.status_code == 400
    assert "已生效" in r.json()["detail"]

    # 变体必须是上级组织的下级：华东的变体不能挂到华南
    east_base = _create_doc(
        manager_client, process_id, "华东父级 SOP", org_unit_id=orgs["CO-EAST"]["id"]
    ).json()
    _serve(manager_client, east_base["id"])
    r = _create_doc(
        manager_client,
        process_id,
        "华南错挂变体",
        org_unit_id=orgs["CO-SOUTH"]["id"],
        variant_of=east_base["id"],
    )
    assert r.status_code == 400
    assert "下级" in r.json()["detail"]
    r = _create_doc(
        manager_client,
        process_id,
        "华东下级变体",
        org_unit_id=orgs["DEPT-EAST-MFG"]["id"],
        variant_of=east_base["id"],
    )
    assert r.status_code == 201, r.text


def test_effective_resolution_prefers_variant_and_respects_dates(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    group_id = orgs["GROUP-001"]["id"]
    east_id = orgs["CO-EAST"]["id"]

    base = _create_doc(manager_client, process_id, "有效版本集团 SOP", org_unit_id=group_id).json()
    _serve(manager_client, base["id"], "1.0", "2026-01-01")
    variant = _create_doc(
        manager_client,
        process_id,
        "有效版本华东变体",
        org_unit_id=east_id,
        variant_of=base["id"],
    ).json()
    _serve(manager_client, variant["id"], "1.0", "2026-06-01")

    east = _effective(client, east_id, process_id)
    chosen = next(
        row
        for row in east
        if row["base_document_code"] == base["code"] or row["code"] == variant["code"]
    )
    assert chosen["document_id"] == variant["id"]
    assert chosen["is_variant"] is True
    assert chosen["base_document_id"] == base["id"]
    assert chosen["inherited"] is False
    assert "华东分公司" in chosen["explanation"]

    south = _effective(client, orgs["CO-SOUTH"]["id"], process_id)
    inherited = next(row for row in south if row["code"] == base["code"])
    assert inherited["is_variant"] is False
    assert inherited["inherited"] is True
    assert inherited["scope_label"] == "集团总部"

    # 变体尚未生效的日期回退到集团版本
    early = _effective(client, east_id, process_id, on_date="2026-03-01")
    early_row = next(row for row in early if row["code"] == base["code"])
    assert early_row["document_id"] == base["id"]
    assert "继承" in early_row["explanation"]

    # 草稿变体没有生效版本，也回退到集团
    draft_variant = _create_doc(
        manager_client,
        process_id,
        "草稿华东变体",
        org_unit_id=east_id,
        variant_of=base["id"],
    ).json()
    assert draft_variant["id"] != variant["id"]
    later = _effective(client, east_id, process_id, on_date="2026-12-01")
    # 同一族在华东有多个变体时取最新的生效变体；草稿不影响
    codes = {row["code"] for row in later}
    assert variant["code"] in codes
    assert draft_variant["code"] not in codes


def test_local_only_not_inherited(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    east_id = orgs["CO-EAST"]["id"]
    child_id = orgs["DEPT-EAST-MFG"]["id"]

    local = _create_doc(
        manager_client,
        process_id,
        "仅华东本地 SOP",
        org_unit_id=east_id,
        policy="LOCAL_ONLY",
    ).json()
    _serve(manager_client, local["id"])

    east_rows = client.get(
        f"{API}/process-documents", params={"org_unit_id": east_id, "process_id": process_id}
    ).json()
    assert local["id"] in {row["id"] for row in east_rows}

    child_rows = client.get(
        f"{API}/process-documents", params={"org_unit_id": child_id, "process_id": process_id}
    ).json()
    assert local["id"] not in {row["id"] for row in child_rows}

    child_effective = _effective(client, child_id, process_id)
    assert local["code"] not in {row["code"] for row in child_effective}

    # 仅本地必须指定组织
    r = manager_client.post(
        f"{API}/process-documents",
        json={
            "process_id": process_id,
            "title": "无组织仅本地",
            "category": "SOP",
            "variation_policy": "LOCAL_ONLY",
        },
    )
    assert r.status_code == 400


def test_effective_requires_org(client):
    r = client.get(f"{API}/process-documents/effective", params={"org_unit_id": 999999})
    assert r.status_code == 400


# ------------------------------------------------------------------ 升级影响与变基


def _project(client, process_id):
    r = client.post(
        f"{API}/projects",
        json={
            "name": "变基影响测试项目",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": process_id,
            "start_date": "2026-10-01",
            "end_date": "2027-03-31",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _instance(client, project_id, step_no="2.1"):
    rows = client.get(f"{API}/projects/{project_id}/deliverables").json()
    return next(row for row in rows if row["step_no"] == step_no)


def test_upgrade_impact_and_minor_rebase(client, manager_client, viewer_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    base = _create_doc(
        manager_client,
        process_id,
        "升级影响集团 SOP",
        org_unit_id=orgs["GROUP-001"]["id"],
    ).json()
    v10 = _serve(manager_client, base["id"], "1.0", "2026-01-01")
    variant = _create_doc(
        manager_client,
        process_id,
        "升级影响华东变体",
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of=base["id"],
    ).json()
    _serve(manager_client, variant["id"], "1.0", "2026-01-01")

    # 项目复制旧版并审批，作为「仍固定旧版」的交付物
    project = _project(client, process_id)
    instance = _instance(client, project["id"])
    copied = manager_client.post(
        f"{API}/process-documents/{base['id']}/versions/{v10['id']}/copy-to-deliverable",
        json={"deliverable_instance_id": instance["id"]},
    ).json()
    for target in ("IN_REVIEW", "APPROVED"):
        manager_client.post(
            f"{API}/deliverables/{instance['id']}/versions/{copied['id']}/transition",
            json={"status": target},
        )

    v11 = _serve(manager_client, base["id"], "1.1", "2026-10-01")

    impact = client.get(f"{API}/process-documents/{base['id']}/upgrade-impact").json()
    assert impact["base_effective_version"]["version_label"] == "1.1"
    row = next(item for item in impact["variants"] if item["document_id"] == variant["id"])
    assert row["status"] == "BEHIND_MINOR"
    assert row["base_old_version_display"] == "v1.0"
    assert row["base_new_version_display"] == "v1.1"
    assert row["requires_reapproval"] is True
    assert {f["field"] for f in row["changed_fields"]} >= {"title", "version_note", "checksum"}

    refs = impact["project_references"]
    assert any(
        item["project_code"] == project["code"]
        and item["deliverable_version_id"] == copied["id"]
        and item["source_version_display"] == "v1.0"
        for item in refs
    )

    # 权限：只读不能变基
    assert (
        viewer_client.post(
            f"{API}/process-documents/{variant['id']}/rebase",
            json={"base_version_id": v11["id"]},
        ).status_code
        == 403
    )

    # 变基生成草稿，未审批前依据版本不变
    r = manager_client.post(
        f"{API}/process-documents/{variant['id']}/rebase",
        json={"base_version_id": v11["id"], "note": "跟随集团 1.1"},
    )
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "DRAFT"
    assert draft["source_base_version_display"] == "v1.1"
    assert "变基" in draft["note"]
    detail = client.get(f"{API}/process-documents/{variant['id']}").json()
    assert detail["variant_base_version_display"] == "v1.0"

    # 同一版本不能重复变基
    r = manager_client.post(
        f"{API}/process-documents/{variant['id']}/rebase",
        json={"base_version_id": v11["id"]},
    )
    assert r.status_code == 400

    # 审批生效后才推进依据版本，影响分析转为已对齐
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = manager_client.post(
            f"{API}/process-documents/{variant['id']}/versions/{draft['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text
    detail = client.get(f"{API}/process-documents/{variant['id']}").json()
    assert detail["variant_base_version_display"] == "v1.1"
    impact = client.get(f"{API}/process-documents/{base['id']}/upgrade-impact").json()
    row = next(item for item in impact["variants"] if item["document_id"] == variant["id"])
    assert row["status"] == "UP_TO_DATE"

    # 清理本次创建的项目，避免影响其他用例的项目总数断言
    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200


def test_major_rebase_requires_acknowledgement(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)
    base = _create_doc(
        manager_client,
        process_id,
        "major 升级集团 SOP",
        org_unit_id=orgs["GROUP-001"]["id"],
    ).json()
    _serve(manager_client, base["id"], "1.0", "2026-01-01")
    variant = _create_doc(
        manager_client,
        process_id,
        "major 升级华东变体",
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of=base["id"],
    ).json()
    _serve(manager_client, variant["id"], "1.0", "2026-01-01")

    v20 = _serve(manager_client, base["id"], "2.0", "2026-10-01")
    r = manager_client.post(
        f"{API}/process-documents/{variant['id']}/rebase",
        json={"base_version_id": v20["id"]},
    )
    assert r.status_code == 400
    assert "major" in r.json()["detail"]

    r = manager_client.post(
        f"{API}/process-documents/{variant['id']}/rebase",
        json={"base_version_id": v20["id"], "acknowledge_major": True},
    )
    assert r.status_code == 201, r.text
    assert r.json()["source_base_version_display"] == "v2.0"
