"""八阶段单一任务目录与只读上下文校验。"""

from uuid import uuid4

API = "/api/v1"


def test_lifecycle_catalog_has_eight_tasks_and_separate_governance(client):
    response = client.get(f"{API}/lifecycle")
    assert response.status_code == 200, response.text
    data = response.json()
    assert [row["key"] for row in data["stages"]] == [
        "strategy",
        "architecture",
        "modeling",
        "analysis",
        "design",
        "execution",
        "monitoring",
        "improvement",
    ]
    assert [row["target"]["view"] for row in data["stages"]] == [
        "strategy",
        "pcf",
        "designer",
        "monitor",
        "designer",
        "execution",
        "dashboard",
        "projects",
    ]
    for row in data["stages"]:
        assert all(
            row[field] for field in ["task", "method_codes", "artifact", "verification", "next_key"]
        )
    assert data["governance"]["target"]["view"] == "authorization"
    assert data["context"]["process"] is None
    assert data["context"]["project"] is None
    assert data["method_labels"]["SIPOC"]
    assert all(row["target"]["label"] for row in data["stages"])


def test_lifecycle_process_only_and_project_match(client):
    rows = client.get(f"{API}/process-map/flat?level=3").json()
    process = next(row for row in rows if row["code"] == "L3-032")
    other = process

    before = len(client.get(f"{API}/projects?page_size=200").json()["items"])
    data = client.get(f"{API}/lifecycle?process_id={process['id']}").json()
    assert data["context"]["process"]["id"] == process["id"]
    assert data["context"]["process"]["level"] == 3
    assert data["context"]["project"] is None
    assert len(client.get(f"{API}/projects?page_size=200").json()["items"]) == before
    response = client.post(
        f"{API}/projects",
        json={
            "name": "生命周期-" + uuid4().hex[:8],
            "methodology": "BPI",
            "process_id": process["id"],
            "owner": "流程管理科",
        },
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    try:
        assert (
            client.get(
                f"{API}/lifecycle?process_id={process['id']}&project_id={project_id}"
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"{API}/lifecycle?process_id={other['id']}&project_id={project_id}"
            ).status_code
            == 200
        )
        assert client.get(f"{API}/lifecycle?project_id={project_id}").status_code == 422
    finally:
        client.delete(f"{API}/projects/{project_id}")


def test_lifecycle_project_visibility_does_not_leak(client, viewer_client):
    from app.core.database import SessionLocal
    from app.models.project import Project

    process_id = client.get(f"{API}/process-map/flat?level=3").json()[0]["id"]
    viewer = viewer_client.get(f"{API}/auth/me").json()
    orgs = client.get(f"{API}/org-units").json()
    # 无组织的只读者只看集团通用；选择明确的非通用组织作为不可见引用。
    inaccessible = next(
        row
        for row in orgs
        if row["id"] != viewer.get("org_unit_id")
        and not (row.get("path") or "").startswith(viewer.get("org_path") or "no-path/")
    )
    response = client.post(
        f"{API}/projects",
        json={
            "name": "生命周期权限测试",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": process_id,
        },
    )
    project_id = response.json()["id"]
    try:
        with SessionLocal() as db:
            db.get(Project, project_id).org_unit_id = inaccessible["id"]
            db.commit()
        assert (
            viewer_client.get(
                f"{API}/lifecycle?process_id={process_id}&project_id={project_id}"
            ).status_code
            == 404
        )
    finally:
        client.delete(f"{API}/projects/{project_id}")


def test_lifecycle_unknown_identity_does_not_fallback(client, anon_client):
    assert anon_client.get(f"{API}/lifecycle").status_code == 401
    assert client.get(f"{API}/lifecycle?process_id=0").status_code == 422
    assert client.get(f"{API}/lifecycle?process_id=99999999").status_code == 404
    row = client.get(f"{API}/process-map/flat?level=3").json()[0]
    assert (
        client.get(f"{API}/lifecycle?process_id={row['id']}&project_id=99999999").status_code == 404
    )
