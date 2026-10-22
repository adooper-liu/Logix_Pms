"""架构草图：独立 draw.io 白板的 CRUD、范围校验与权限。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client) -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == "L3-032")


def _project_id(client) -> int:
    rows = client.get(f"{API}/projects", params={"page_size": 1}).json()["items"]
    assert rows
    return rows[0]["id"]


def test_sketch_crud_and_permissions(client, manager_client, viewer_client, owner_client):
    process_id = _process_id(client)
    project_id = _project_id(client)
    sketch_id = None
    try:
        meta = client.get(f"{API}/sketches/meta")
        assert meta.status_code == 200
        assert meta.json()["embed_url"].startswith("http")

        created = client.post(
            f"{API}/sketches",
            json={
                "title": "华东流程架构草图",
                "description": "独立白板",
                "process_id": process_id,
                "project_id": project_id,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        sketch_id = body["id"]
        assert body["title"] == "华东流程架构草图"
        assert body["process_code"] == "L3-032"
        assert body["mxfile_xml"] == ""

        saved = client.patch(
            f"{API}/sketches/{sketch_id}",
            json={"mxfile_xml": "<mxfile><diagram id='p1'/></mxfile>"},
        )
        assert saved.status_code == 200, saved.text
        assert "mxfile" in saved.json()["mxfile_xml"]

        detail = client.get(f"{API}/sketches/{sketch_id}").json()
        assert detail["mxfile_xml"].startswith("<mxfile")
        summaries = client.get(f"{API}/sketches").json()
        row = next(item for item in summaries if item["id"] == sketch_id)
        assert "mxfile_xml" not in row, "列表不应下发大段 XML"

        assert (
            viewer_client.post(f"{API}/sketches", json={"title": "只读不能建"}).status_code == 403
        )
        assert owner_client.delete(f"{API}/sketches/{sketch_id}").status_code == 403
    finally:
        if sketch_id is not None:
            assert manager_client.delete(f"{API}/sketches/{sketch_id}").status_code == 200


def test_sketch_scope_validation(client):
    bad_process = client.post(f"{API}/sketches", json={"title": "坏流程", "process_id": 999999})
    assert bad_process.status_code == 400
    bad_project = client.post(f"{API}/sketches", json={"title": "坏项目", "project_id": 999999})
    assert bad_project.status_code == 400
    empty = client.post(f"{API}/sketches", json={"title": "   "})
    assert empty.status_code == 400
