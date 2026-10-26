"""步骤契约与交付物：实例化、版本状态机、权限与级联。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import settings

API = "/api/v1"

XLSX_BYTES = b"PK\x03\x04" + b"fake xlsx payload for storage tests"


def _create_project(client, owner: str = "流程管理科") -> dict:
    r = client.post(
        f"{API}/projects",
        json={
            "name": "交付物测试项目",
            "methodology": "BPI",
            "owner": owner,
            "start_date": "2026-10-01",
            "end_date": "2027-03-31",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _instances(client, project_id: int) -> list:
    r = client.get(f"{API}/projects/{project_id}/deliverables")
    assert r.status_code == 200, r.text
    return r.json()


def _instance(client, project_id: int, step_no: str) -> dict:
    return next(i for i in _instances(client, project_id) if i["step_no"] == step_no)


def _transition(client, instance_id: int, version_id: int, target: str):
    return client.post(
        f"{API}/deliverables/{instance_id}/versions/{version_id}/transition",
        json={"status": target},
    )


# ------------------------------------------------------------------ 标准侧


def test_step_contracts_are_seeded(client):
    r = client.get(f"{API}/workflow/contracts")
    assert r.status_code == 200
    contracts = r.json()
    assert len(contracts) == 24

    step_21 = next(c for c in contracts if c["step_no"] == "2.1")
    assert [t["code"] for t in step_21["tools"]] == ["SIPOC", "SWIMLANE"]
    assert step_21["tool_levels"] == {"SIPOC": "REQUIRED", "SWIMLANE": "RECOMMENDED"}
    assert step_21["tools"][0]["level_label"] == "必用"
    assert step_21["tools"][1]["level_label"] == "推荐"
    assert step_21["owner_role"] == "流程 Owner"
    assert step_21["inputs"].startswith("上游交付物：")
    assert [d["name"] for d in step_21["deliverables"]] == ["As-Is 流程图"]
    assert step_21["deliverables"][0]["type_label"] == "图表"
    assert step_21["decision_gate"] is False

    # 每个阶段的最后一步是决策门
    gates = {c["step_no"] for c in contracts if c["decision_gate"]}
    assert gates == {"1.4", "2.4", "3.5", "4.6", "5.5"}

    # 24 个步骤都至少有一个交付物定义（共 32 个）
    assert sum(len(c["deliverables"]) for c in contracts) == 32
    assert all(c["deliverables"] for c in contracts)


def test_contract_update_requires_manager_and_existing_tools(client, viewer_client, manager_client):
    url = f"{API}/workflow/steps/1.1/contract"
    r = viewer_client.put(url, json={"tool_codes": ["BPMN"]})
    assert r.status_code == 403

    r = manager_client.put(url, json={"tool_codes": ["NOT-A-TOOL"]})
    assert r.status_code == 400
    assert "NOT-A-TOOL" in r.json()["detail"]

    r = manager_client.put(
        url,
        json={
            "tool_codes": ["BPMN", "SIPOC", "BPMN"],
            "tool_levels": {"BPMN": "REQUIRED", "SIPOC": "OPTIONAL"},
            "owner_role": "流程管理科",
            "acceptance_criteria": "流程地图覆盖 L1–L4 且每条流程有 Owner",
            "decision_gate": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool_codes"] == ["BPMN", "SIPOC"]  # 去重且保持顺序
    assert body["tool_levels"] == {"BPMN": "REQUIRED", "SIPOC": "OPTIONAL"}
    assert len(body["tools"]) == 2
    assert body["acceptance_criteria"].startswith("流程地图")

    # 使用要求必须指向本步骤已有的工具
    r = manager_client.put(url, json={"tool_levels": {"VSM": "REQUIRED"}})
    assert r.status_code == 400

    # 清空工具引用
    r = manager_client.put(url, json={"tool_codes": []})
    assert r.status_code == 200
    assert r.json()["tool_codes"] == []
    assert r.json()["tool_levels"] == {}


def test_definition_crud(client, viewer_client, manager_client):
    r = viewer_client.post(
        f"{API}/workflow/deliverable-definitions",
        json={"step_no": "1.4", "name": "只读不能建"},
    )
    assert r.status_code == 403

    r = manager_client.post(
        f"{API}/workflow/deliverable-definitions",
        json={
            "step_no": "1.4",
            "name": "方法论决策记录（测试）",
            "type": "DECISION",
            "acceptance_criteria": "写明备选方法与排除理由",
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["code"] == "DLV-1.4-02"
    assert created["type_label"] == "决策记录"

    r = manager_client.post(
        f"{API}/workflow/deliverable-definitions",
        json={"step_no": "1.4", "code": created["code"], "name": "重复编码"},
    )
    assert r.status_code == 409

    r = manager_client.patch(
        f"{API}/workflow/deliverable-definitions/{created['id']}",
        json={"name": "方法论决策记录（改名）", "is_active": True},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "方法论决策记录（改名）"

    r = manager_client.delete(f"{API}/workflow/deliverable-definitions/{created['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1


def test_definition_for_unknown_step_rejected(manager_client):
    r = manager_client.post(
        f"{API}/workflow/deliverable-definitions",
        json={"step_no": "9.9", "name": "不存在的步骤"},
    )
    assert r.status_code == 400


# ------------------------------------------------------------------ 项目实例


def test_project_creation_instantiates_deliverables(client):
    project = _create_project(client)
    items = _instances(client, project["id"])
    assert len(items) == 32
    assert all(i["status"] == "MISSING" for i in items)
    assert all(i["status_label"] == "未产出" for i in items)
    assert all(i["required"] for i in items)
    assert all(i["current_version"] is None and i["version_count"] == 0 for i in items)

    r = client.get(f"{API}/projects/{project['id']}/deliverables/summary")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total"] == 32
    assert summary["required_missing"] == 32
    assert summary["effective"] == 0
    assert summary["completeness_pct"] == 0.0
    assert summary["status_labels"]["MISSING"] == "未产出"


# ------------------------------------------------------------------ 版本状态机


def test_version_lifecycle_and_restore(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.1")
    base = f"{API}/deliverables/{instance['id']}"

    r = client.post(
        base + "/versions",
        json={
            "title": "As-Is 流程 v1",
            "note": "首次现场梳理",
            "file_ref": "//fileserver/pms/prj/as-is-v1.xlsx",
            "file_name": "as-is-v1.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": 20480,
            "checksum": "a" * 64,
        },
    )
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["version_label"] == "R1"
    assert v1["status"] == "DRAFT"
    assert v1["author"] == "系统管理员"

    # 跳级不允许
    r = _transition(client, instance["id"], v1["id"], "EFFECTIVE")
    assert r.status_code == 400

    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = _transition(client, instance["id"], v1["id"], target)
        assert r.status_code == 200, r.text
    v1 = r.json()
    assert v1["status"] == "EFFECTIVE"
    assert v1["approver"] == "系统管理员"
    assert v1["approved_at"] and v1["valid_from"]

    # 第二个版本：登记后当前指针指向 R2，R1 仍是生效版
    r = client.post(base + "/versions", json={"title": "As-Is 流程 v2"})
    assert r.status_code == 201
    v2 = r.json()
    assert v2["version_label"] == "R2"
    assert v2["base_version_id"] == v1["id"]

    detail = client.get(base).json()
    assert detail["current_version_id"] == v2["id"]
    assert detail["version_count"] == 2
    assert {v["version_label"]: v["status"] for v in detail["versions"]} == {
        "R1": "EFFECTIVE",
        "R2": "DRAFT",
    }

    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = _transition(client, instance["id"], v2["id"], target)
        assert r.status_code == 200, r.text
    detail = client.get(base).json()
    assert {v["version_label"]: v["status"] for v in detail["versions"]} == {
        "R1": "SUPERSEDED",
        "R2": "EFFECTIVE",
    }
    assert detail["versions"][0]["valid_to"] is not None

    # 恢复 R1：移动指针，不复制版本，不新增 R3
    r = client.post(f"{base}/versions/{v1['id']}/restore")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["current_version_id"] == v1["id"]
    assert detail["current_version"]["version_label"] == "R1"
    assert detail["status"] == "EFFECTIVE"
    assert detail["version_count"] == 2
    assert {v["version_label"]: v["status"] for v in detail["versions"]} == {
        "R1": "EFFECTIVE",
        "R2": "SUPERSEDED",
    }
    assert detail["versions"][0]["valid_to"] is None

    # 作废后再恢复：拒绝
    assert _transition(client, instance["id"], v1["id"], "RETIRED").status_code == 200
    detail = client.get(base).json()
    # 当前版本作废后，指针退回最近一个未作废版本，而不是悬空
    assert detail["current_version_id"] == v2["id"]
    assert detail["status"] == "SUPERSEDED"
    r = client.post(f"{base}/versions/{v1['id']}/restore")
    assert r.status_code == 400
    assert "已批准" in r.json()["detail"]


def test_checksum_must_be_sha256(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.1")
    r = client.post(
        f"{API}/deliverables/{instance['id']}/versions",
        json={"title": "坏校验值", "checksum": "xyz"},
    )
    assert r.status_code == 422


# ------------------------------------------------------------------ 权限与同步


def test_version_write_permissions(client, viewer_client, owner_client, manager_client):
    project = _create_project(client, owner="流程管理科")  # 归属 manager，不属于 chen
    instance = _instance(client, project["id"], "2.1")
    url = f"{API}/deliverables/{instance['id']}/versions"

    assert viewer_client.post(url, json={"title": "只读"}).status_code == 403
    assert owner_client.post(url, json={"title": "他人项目"}).status_code == 403
    r = manager_client.post(url, json={"title": "流程管理科登记"})
    assert r.status_code == 201


def test_sync_is_idempotent_and_picks_up_new_definitions(client, manager_client):
    project = _create_project(client)
    url = f"{API}/projects/{project['id']}/deliverables/sync"

    r = client.post(url)
    assert r.status_code == 200
    first = r.json()
    assert first["created"] == 0
    assert first["total"] == 32

    r = manager_client.post(
        f"{API}/workflow/deliverable-definitions",
        json={"step_no": "2.1", "name": "泳道责任人清单", "type": "DATA"},
    )
    assert r.status_code == 201
    definition = r.json()

    r = client.post(url)
    assert r.status_code == 200
    assert r.json() == {"created": 1, "total": 33}

    items = _instances(client, project["id"])
    assert any(i["definition_id"] == definition["id"] for i in items)

    # 已有实例时不允许删定义，只能停用
    r = manager_client.delete(f"{API}/workflow/deliverable-definitions/{definition['id']}")
    assert r.status_code == 409


def test_delete_project_cascades_deliverables(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "3.5")
    assert client.get(f"{API}/deliverables/{instance['id']}").status_code == 200

    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200
    assert client.get(f"{API}/deliverables/{instance['id']}").status_code == 404


# ------------------------------------------------------------------ 文件上传与下载


def _upload(client, instance_id: int, name: str, content: bytes, **data):
    return client.post(
        f"{API}/deliverables/{instance_id}/versions/upload",
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )


def test_upload_computes_checksum_and_downloads(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")

    r = _upload(
        client,
        instance["id"],
        "价值流现状图.xlsx",
        XLSX_BYTES,
        title="价值流现状图 v1",
        note="现场观测",
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["version_label"] == "R1"
    assert version["file_name"] == "价值流现状图.xlsx"
    assert version["size_bytes"] == len(XLSX_BYTES)
    assert version["has_file"] is True
    assert version["storage_backend"] == "local"
    assert version["checksum"] == hashlib.sha256(XLSX_BYTES).hexdigest()
    assert version["download_url"].endswith(
        f"/deliverables/{instance['id']}/versions/{version['id']}/download"
    )

    r = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/download")
    assert r.status_code == 200
    assert r.content == XLSX_BYTES
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in r.headers["content-disposition"]


def test_metadata_only_version_has_no_download(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    r = client.post(
        f"{API}/deliverables/{instance['id']}/versions",
        json={"title": "只登记外部引用", "file_ref": "//fileserver/as-is.xlsx"},
    )
    version = r.json()
    assert version["has_file"] is False
    assert version["download_url"] is None
    r = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/download")
    assert r.status_code == 404


def test_pdf_preview_is_inline_and_office_requires_download(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"

    uploaded = _upload(client, instance["id"], "现状说明.pdf", pdf)
    assert uploaded.status_code == 201, uploaded.text
    version = uploaded.json()
    assert version["preview_kind"] == "PDF"
    assert version["preview_url"].endswith(
        f"/deliverables/{instance['id']}/versions/{version['id']}/preview"
    )

    preview = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/preview")
    assert preview.status_code == 200
    assert preview.content == pdf
    assert preview.headers["content-type"].startswith("application/pdf")
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.headers["x-content-type-options"] == "nosniff"

    office = _upload(client, instance["id"], "现状说明.docx", XLSX_BYTES)
    assert office.status_code == 201, office.text
    office_version = office.json()
    assert office_version["preview_kind"] is None
    assert office_version["preview_url"] is None
    blocked = client.get(
        f"{API}/deliverables/{instance['id']}/versions/{office_version['id']}/preview"
    )
    assert blocked.status_code == 415
    assert "不支持在线预览" in blocked.json()["detail"]


def test_office_preview_converts_to_pdf_and_caches(client, monkeypatch):
    from app.services import preview as preview_service

    converted = b"%PDF-1.4\nconverted by fake office\n%%EOF"
    calls = {"count": 0}

    def fake_convert(source, filename):
        calls["count"] += 1
        assert source.read(2) == b"PK"
        return converted

    monkeypatch.setattr(preview_service, "converter_available", lambda: True)
    monkeypatch.setattr(preview_service, "convert_to_pdf", fake_convert)

    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    uploaded = _upload(client, instance["id"], "方案.docx", XLSX_BYTES + b"-docx")
    assert uploaded.status_code == 201, uploaded.text
    version = uploaded.json()
    assert version["preview_kind"] == "PDF"
    assert version["preview_url"].endswith(
        f"/deliverables/{instance['id']}/versions/{version['id']}/preview"
    )

    preview = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.content == converted
    assert preview.headers["content-type"].startswith("application/pdf")
    assert preview.headers["content-disposition"].startswith("inline;")
    assert calls["count"] == 1

    # 同一版本再次预览走缓存，不重复调用转换器。
    again = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/preview")
    assert again.status_code == 200
    assert again.content == converted
    assert calls["count"] == 1


def test_office_preview_conversion_failure_returns_502(client, monkeypatch):
    from app.services import preview as preview_service

    monkeypatch.setattr(preview_service, "converter_available", lambda: True)

    def broken_convert(source, filename):
        raise preview_service.PreviewConversionError("soffice 未生成 PDF")

    monkeypatch.setattr(preview_service, "convert_to_pdf", broken_convert)

    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    uploaded = _upload(client, instance["id"], "坏文件.docx", XLSX_BYTES + b"-bad")
    assert uploaded.status_code == 201, uploaded.text
    version = uploaded.json()
    failed = client.get(f"{API}/deliverables/{instance['id']}/versions/{version['id']}/preview")
    assert failed.status_code == 502
    assert "转换预览失败" in failed.json()["detail"]


def test_print_pack_html_and_pdf(client, monkeypatch):
    from app.services import preview as preview_service

    project = _create_project(client)
    html = client.get(f"{API}/projects/{project['id']}/deliverables/print-pack")
    assert html.status_code == 200, html.text
    assert html.headers["content-type"].startswith("text/html")
    body = html.text
    assert "项目交付物打印包" in body
    assert project["code"] in body
    assert "1.1" in body and "企业流程地图" in body
    assert "阶段退出门槛" in body

    # 未安装转换器时，服务端 PDF 明确拒绝，前端可退回 HTML 打印。
    unavailable = client.get(
        f"{API}/projects/{project['id']}/deliverables/print-pack", params={"format": "pdf"}
    )
    assert unavailable.status_code == 503

    monkeypatch.setattr(preview_service, "converter_available", lambda: True)
    monkeypatch.setattr(
        preview_service,
        "convert_to_pdf",
        lambda source, filename: b"%PDF-1.4\nprint pack\n%%EOF",
    )
    pdf = client.get(
        f"{API}/projects/{project['id']}/deliverables/print-pack", params={"format": "pdf"}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_upload_rejects_extension_and_magic_mismatch(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")

    r = _upload(client, instance["id"], "evil.exe", b"MZ\x90\x00")
    assert r.status_code == 400
    assert "不支持的文件类型" in r.json()["detail"]

    # 扩展名是 xlsx，但内容不是 ZIP 容器
    r = _upload(client, instance["id"], "fake.xlsx", b"not a zip at all")
    assert r.status_code == 400
    assert "文件内容与扩展名不符" in r.json()["detail"]

    detail = client.get(f"{API}/deliverables/{instance['id']}").json()
    assert detail["version_count"] == 0


def test_upload_checksum_mismatch_discards_file(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    files_before = {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()}

    r = _upload(
        client,
        instance["id"],
        "mismatch.xlsx",
        XLSX_BYTES,
        checksum="0" * 64,
    )
    assert r.status_code == 400
    assert "不一致" in r.json()["detail"]
    assert client.get(f"{API}/deliverables/{instance['id']}").json()["version_count"] == 0

    files_after = {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()}
    assert files_after == files_before, "校验失败的文件应被清理"


def test_upload_strips_path_from_filename(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    r = _upload(client, instance["id"], "../../etc/passwd.xlsx", XLSX_BYTES)
    assert r.status_code == 201, r.text
    assert r.json()["file_name"] == "passwd.xlsx"

    root = Path(settings.attachment_dir).resolve()
    stored = [p for p in root.rglob("*") if p.is_file() and p.name.endswith(".xlsx")]
    assert stored, "文件应落在附件目录内"
    assert all(root in p.resolve().parents for p in stored)


def test_upload_bad_base_version_cleans_file(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    before = {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()}

    r = _upload(client, instance["id"], "orphan.xlsx", XLSX_BYTES, base_version_id=999999)
    assert r.status_code == 400
    assert "base_version_id" in r.json()["detail"]
    assert client.get(f"{API}/deliverables/{instance['id']}").json()["version_count"] == 0
    assert {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()} == before


def test_viewer_can_download_but_not_upload(client, viewer_client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    r = _upload(client, instance["id"], "viewer-check.xlsx", XLSX_BYTES)
    version = r.json()

    assert (
        viewer_client.get(
            f"{API}/deliverables/{instance['id']}/versions/{version['id']}/download"
        ).status_code
        == 200
    )
    assert (
        viewer_client.post(
            f"{API}/deliverables/{instance['id']}/versions/upload",
            files={"file": ("blocked.xlsx", XLSX_BYTES, "application/octet-stream")},
        ).status_code
        == 403
    )


def test_delete_project_removes_uploaded_file(client):
    project = _create_project(client)
    instance = _instance(client, project["id"], "2.2")
    before = {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()}
    r = _upload(client, instance["id"], "cleanup-me.xlsx", XLSX_BYTES)
    assert r.status_code == 201
    uploaded = {p for p in Path(settings.attachment_dir).rglob("*") if p.is_file()} - before
    assert len(uploaded) == 1

    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200
    assert all(not path.exists() for path in uploaded)
