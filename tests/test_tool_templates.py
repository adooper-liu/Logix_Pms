"""工具模板库：版本审批、下载、复制到项目、占位符上下文与权限。"""

from __future__ import annotations

import hashlib
import json

API = "/api/v1"

DOCX_BYTES = b"PK\x03\x04" + b"fake docx template"
XLSX_BYTES = b"PK\x03\x04" + b"fake xlsx template"


def _create_template(client, tool_code: str, fmt: str = "XLSX", **extra) -> dict:
    payload = {
        "tool_code": tool_code,
        "name": f"{tool_code} 预制模板",
        "format": fmt,
        "description": "测试用模板",
        **extra,
    }
    r = client.post(f"{API}/tool-templates", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, template_id: int, name: str, content: bytes, label: str, **data):
    return client.post(
        f"{API}/tool-templates/{template_id}/versions/upload",
        files={"file": (name, content, "application/octet-stream")},
        data={"version_label": label, **data},
    )


def _transition(client, template_id: int, version_id: int, target: str):
    return client.post(
        f"{API}/tool-templates/{template_id}/versions/{version_id}/transition",
        json={"status": target},
    )


def _make_effective(client, template_id: int, version_id: int) -> dict:
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = _transition(client, template_id, version_id, target)
        assert r.status_code == 200, r.text
    return r.json()


def _definition_id(client, code: str) -> int:
    rows = client.get(f"{API}/workflow/deliverable-definitions").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _create_project(client, owner: str = "流程管理科") -> dict:
    r = client.post(
        f"{API}/projects",
        json={
            "name": "模板复制测试项目",
            "methodology": "BPI",
            "owner": owner,
            "start_date": "2026-10-01",
            "end_date": "2027-03-31",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _instance(client, project_id: int, step_no: str) -> dict:
    rows = client.get(f"{API}/projects/{project_id}/deliverables").json()
    return next(row for row in rows if row["step_no"] == step_no)


# ------------------------------------------------------------------ 模板库


def test_template_create_default_and_permissions(client, manager_client, viewer_client):
    assert (
        viewer_client.post(
            f"{API}/tool-templates",
            json={"tool_code": "SIPOC", "name": "只读不能建", "format": "XLSX"},
        ).status_code
        == 403
    )

    first = _create_template(manager_client, "SIPOC", "XLSX", name="SIPOC 空白表")
    assert first["code"].startswith("TPL-SIPOC-")
    assert first["format_label"] == "Excel"
    assert first["is_default"] is True  # 同工具同格式的第一个模板成为默认
    assert first["tool_name"]

    second = _create_template(manager_client, "SIPOC", "XLSX", name="SIPOC 分区表", is_default=True)
    assert second["is_default"] is True
    rows = manager_client.get(f"{API}/tool-templates", params={"tool_code": "SIPOC"}).json()
    assert [row["is_default"] for row in rows].count(True) == 1
    assert next(row for row in rows if row["id"] == first["id"])["is_default"] is False

    # 取消默认后自动从同工具同格式里补一个，不能出现「无默认」
    r = manager_client.patch(f"{API}/tool-templates/{second['id']}", json={"is_default": False})
    assert r.status_code == 200
    rows = manager_client.get(f"{API}/tool-templates", params={"tool_code": "SIPOC"}).json()
    assert [row["is_default"] for row in rows].count(True) == 1

    r = manager_client.post(
        f"{API}/tool-templates",
        json={"tool_code": "NOT-A-TOOL", "name": "无效工具", "format": "XLSX"},
    )
    assert r.status_code == 400

    r = manager_client.post(
        f"{API}/tool-templates",
        json={
            "tool_code": "SIPOC",
            "code": first["code"],
            "name": "重复编码",
            "format": "XLSX",
        },
    )
    assert r.status_code == 409


def test_template_list_filters(manager_client):
    _create_template(manager_client, "VSM", "XLSX", name="VSM 价值流模板")
    rows = manager_client.get(
        f"{API}/tool-templates", params={"tool_code": "VSM", "format": "XLSX"}
    ).json()
    assert rows and all(row["tool_code"] == "VSM" and row["format"] == "XLSX" for row in rows)

    rows = manager_client.get(f"{API}/tool-templates", params={"stage_no": 2}).json()
    assert rows and all(row["stage_no"] == 2 for row in rows)

    rows = manager_client.get(f"{API}/tool-templates", params={"keyword": "价值流"}).json()
    assert rows


# ------------------------------------------------------------------ 版本与审批


def test_template_version_upload_download_and_usage(client, manager_client, viewer_client):
    template = _create_template(manager_client, "FIVE-WHY", "DOCX", name="5Why 分析表")
    placeholders = json.dumps(
        [{"key": "project_name", "label": "项目名称", "source": "project.name", "required": True}],
        ensure_ascii=False,
    )
    r = _upload(
        manager_client,
        template["id"],
        "5why.docx",
        DOCX_BYTES,
        "1.0.0",
        placeholders=placeholders,
        note="首版",
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["status"] == "DRAFT"
    assert version["has_file"] is True
    assert version["checksum"] == hashlib.sha256(DOCX_BYTES).hexdigest()
    assert version["placeholders"][0]["source"] == "project.name"

    # 登录用户都能下载；下载会记一条使用记录
    r = viewer_client.get(
        f"{API}/tool-templates/{template['id']}/versions/{version['id']}/download"
    )
    assert r.status_code == 200
    assert r.content == DOCX_BYTES
    assert r.headers["x-content-type-options"] == "nosniff"

    usages = manager_client.get(f"{API}/tool-templates/{template['id']}/usages").json()
    assert len(usages) == 1
    assert usages[0]["mode"] == "DOWNLOAD"
    assert usages[0]["created_by"] == "只读访客"

    # 版本号只追加不覆盖
    r = _upload(manager_client, template["id"], "5why.docx", DOCX_BYTES, "1.0.0")
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]

    # 版本号格式与文件格式都要校验
    r = _upload(manager_client, template["id"], "5why.docx", DOCX_BYTES, "v1")
    assert r.status_code == 400
    r = _upload(manager_client, template["id"], "5why.xlsx", XLSX_BYTES, "1.0.1")
    assert r.status_code == 400
    assert "DOCX" in r.json()["detail"]


def test_template_version_transition_supersedes(manager_client):
    template = _create_template(manager_client, "KAIZEN", "XLSX")
    v1 = _upload(manager_client, template["id"], "kaizen-v1.xlsx", XLSX_BYTES, "1.0.0").json()
    v2 = _upload(manager_client, template["id"], "kaizen-v2.xlsx", XLSX_BYTES, "1.1.0").json()

    # 跳级不允许
    assert _transition(manager_client, template["id"], v1["id"], "EFFECTIVE").status_code == 400

    _make_effective(manager_client, template["id"], v1["id"])
    detail = manager_client.get(f"{API}/tool-templates/{template['id']}").json()
    assert detail["effective_version"]["id"] == v1["id"]

    _make_effective(manager_client, template["id"], v2["id"])
    detail = manager_client.get(f"{API}/tool-templates/{template['id']}").json()
    assert detail["effective_version"]["id"] == v2["id"]
    statuses = {v["version_label"]: v["status"] for v in detail["versions"]}
    assert statuses == {"1.0.0": "SUPERSEDED", "1.1.0": "EFFECTIVE"}


# ------------------------------------------------------------------ 复制到项目


def test_copy_file_template_to_project(client, manager_client):
    definition_id = _definition_id(client, "DLV-2.3-01")
    template = _create_template(
        manager_client,
        "FISHBONE",
        "XLSX",
        name="鱼骨图模板",
        deliverable_definition_id=definition_id,
    )
    version = _upload(manager_client, template["id"], "fishbone.xlsx", XLSX_BYTES, "1.0.0").json()
    _make_effective(manager_client, template["id"], version["id"])

    project = _create_project(client)
    instance = _instance(client, project["id"], "2.3")

    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/copy",
        json={"deliverable_instance_id": instance["id"], "title": "根因分析-鱼骨图"},
    )
    assert r.status_code == 201, r.text
    copied = r.json()
    assert copied["version_label"] == "R1"
    assert copied["source_template_version_id"] == version["id"]
    assert copied["has_file"] is True
    assert copied["checksum"] == hashlib.sha256(XLSX_BYTES).hexdigest()

    r = client.get(copied["download_url"])
    assert r.status_code == 200
    assert r.content == XLSX_BYTES

    usages = manager_client.get(f"{API}/tool-templates/{template['id']}/usages").json()
    assert usages[0]["mode"] == "DOWNLOAD"
    assert usages[0]["project_code"] == project["code"]
    assert usages[0]["deliverable_version_id"] == copied["id"]

    # 模板定义与目标步骤不一致时拒绝
    other = _instance(client, project["id"], "2.2")
    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/copy",
        json={"deliverable_instance_id": other["id"]},
    )
    assert r.status_code == 400
    assert "不一致" in r.json()["detail"]

    # 升级模板不会改动已复制的版本
    v2 = _upload(manager_client, template["id"], "fishbone-v2.xlsx", XLSX_BYTES, "1.1.0").json()
    _make_effective(manager_client, template["id"], v2["id"])
    detail = client.get(f"{API}/deliverables/{instance['id']}").json()
    assert detail["current_version"]["id"] == copied["id"]
    assert detail["current_version"]["source_template_version_id"] == version["id"]


def test_copy_online_template_and_context(client, manager_client):
    definition_id = _definition_id(client, "DLV-4.3-01")
    template = _create_template(
        manager_client,
        "PDCA",
        "ONLINE",
        name="试点复盘清单",
        deliverable_definition_id=definition_id,
    )
    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/versions",
        json={
            "version_label": "1.0.0",
            "note": "在线清单首版",
            "placeholders": [
                {
                    "key": "project_name",
                    "label": "项目名称",
                    "source": "project.name",
                    "required": True,
                },
                {"key": "step_name", "label": "步骤", "source": "step.name", "required": True},
                {"key": "company", "label": "公司", "source": "group.name", "required": True},
            ],
        },
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["has_file"] is False
    _make_effective(manager_client, template["id"], version["id"])

    project = _create_project(client)
    instance = _instance(client, project["id"], "4.3")

    # 在线模板必须先走 ONLINE 版本，不能直接上传
    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/versions/upload",
        files={"file": ("x.xlsx", XLSX_BYTES, "application/octet-stream")},
        data={"version_label": "9.9.9"},
    )
    assert r.status_code == 400

    context = manager_client.get(
        f"{API}/tool-templates/{template['id']}/versions/{version['id']}/context",
        params={"deliverable_instance_id": instance["id"]},
    ).json()
    assert context["context"]["project.name"] == project["name"]
    assert context["missing_required"] == ["company"]
    values = {item["key"]: item["value"] for item in context["placeholders"]}
    assert values["project_name"] == project["name"]
    assert values["step_name"] == "试点执行与复盘"

    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/copy",
        json={"deliverable_instance_id": instance["id"]},
    )
    assert r.status_code == 201, r.text
    copied = r.json()
    assert copied["has_file"] is False
    assert copied["source_template_version_id"] == version["id"]

    usages = manager_client.get(f"{API}/tool-templates/{template['id']}/usages").json()
    assert usages[0]["mode"] == "ONLINE"


def test_copy_permissions(client, manager_client, viewer_client, owner_client):
    template = _create_template(manager_client, "DMAIC", "XLSX")
    version = _upload(manager_client, template["id"], "dmaic.xlsx", XLSX_BYTES, "1.0.0").json()
    _make_effective(manager_client, template["id"], version["id"])
    project = _create_project(client, owner="流程管理科")
    instance = _instance(client, project["id"], "2.1")

    body = {"deliverable_instance_id": instance["id"]}
    assert (
        viewer_client.post(f"{API}/tool-templates/{template['id']}/copy", json=body).status_code
        == 403
    )
    assert (
        owner_client.post(f"{API}/tool-templates/{template['id']}/copy", json=body).status_code
        == 403
    )
    assert (
        manager_client.post(f"{API}/tool-templates/{template['id']}/copy", json=body).status_code
        == 201
    )


def test_copy_requires_effective_version(client, manager_client):
    template = _create_template(manager_client, "BALANCED-SCORE", "XLSX")
    _upload(manager_client, template["id"], "scorecard.xlsx", XLSX_BYTES, "1.0.0")
    project = _create_project(client)
    instance = _instance(client, project["id"], "3.3")
    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/copy",
        json={"deliverable_instance_id": instance["id"]},
    )
    assert r.status_code == 409
    assert "生效" in r.json()["detail"]


# ------------------------------------------------------------------ 其他规则


def test_step_recommendations_include_tools_and_templates(client, manager_client):
    definition_id = _definition_id(client, "DLV-2.1-01")
    template = _create_template(
        manager_client,
        "SIPOC",
        "XLSX",
        name="SIPOC 推荐模板",
        deliverable_definition_id=definition_id,
    )
    version = _upload(manager_client, template["id"], "sipoc-step.xlsx", XLSX_BYTES, "1.0.0").json()
    _make_effective(manager_client, template["id"], version["id"])

    # 工具不在 2.1 契约清单里，但绑定到了本步骤交付物 → 单独列出
    extra = _create_template(
        manager_client,
        "VSM",
        "XLSX",
        name="VSM 交付物模板",
        deliverable_definition_id=definition_id,
    )

    r = client.get(f"{API}/workflow/steps/2.1/recommendations")
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["step_name"] == "现状流程绘制"
    tools = {t["code"]: t for t in rec["tools"]}
    assert tools["SIPOC"]["level"] == "REQUIRED"
    assert tools["SIPOC"]["level_label"] == "必用"
    assert any(t["id"] == template["id"] for t in tools["SIPOC"]["templates"])
    assert tools["SWIMLANE"]["level"] == "RECOMMENDED"
    assert tools["SWIMLANE"]["templates"] == []
    assert [t["id"] for t in rec["deliverable_templates"]] == [extra["id"]]

    assert client.get(f"{API}/workflow/steps/9.9/recommendations").status_code == 404


def test_generate_mode_not_implemented(manager_client):
    template = _create_template(manager_client, "GOLIVE", "XLSX")
    version = _upload(manager_client, template["id"], "golive.xlsx", XLSX_BYTES, "1.0.0").json()
    _make_effective(manager_client, template["id"], version["id"])
    r = manager_client.post(
        f"{API}/tool-templates/{template['id']}/usages", json={"mode": "GENERATE"}
    )
    assert r.status_code == 400
    assert "尚未实现" in r.json()["detail"]


def test_delete_template_guard(manager_client):
    with_version = _create_template(manager_client, "PARETO", "XLSX")
    _upload(manager_client, with_version["id"], "pareto.xlsx", XLSX_BYTES, "1.0.0")
    r = manager_client.delete(f"{API}/tool-templates/{with_version['id']}")
    assert r.status_code == 409

    empty = _create_template(manager_client, "PROCESS-MINING", "XLSX")
    r = manager_client.delete(f"{API}/tool-templates/{empty['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
