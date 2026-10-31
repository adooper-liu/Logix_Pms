"""治理体系落地项目：9 阶段模板与动态阶段推进。"""

from __future__ import annotations

API = "/api/v1"


def _user_id(client) -> int:
    return client.get(f"{API}/execution/assignees").json()[0]["id"]


def _payload(client, **overrides) -> dict:
    payload = {
        "name": "治理体系落地测试",
        "owner_user_id": _user_id(client),
        "sponsor": "集团总经理",
        "objective": "用九阶段路径建立可运行的流程治理体系",
        "scope": "试点：采购需求提报",
        "priority": 2,
        "start_date": "2026-11-01",
        "end_date": "2027-02-28",
    }
    payload.update(overrides)
    return payload


def _evidence_stage(client) -> int:
    """与启动页同一个当前阶段：第一个未就绪且未跳过的阶段。"""
    status = client.get(f"{API}/start/status").json()
    if status["next_step"] is None:
        return len(status["steps"])
    for index, step in enumerate(status["steps"], start=1):
        if step["key"] == status["next_step"]:
            return index
    return len(status["steps"])


def test_create_setup_program_with_nine_stages(client):
    created = client.post(f"{API}/projects/setup-program", json=_payload(client))
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["project_type"] == "GOVERNANCE_SETUP"
    assert data["project_type_label"] == "治理体系落地"
    assert data["code"].startswith("SET-")
    pid = data["id"]

    detail = client.get(f"{API}/projects/{pid}").json()
    assert detail["project"]["project_type"] == "GOVERNANCE_SETUP"
    assert len(detail["stages"]) == 9
    assert [stage["stage_no"] for stage in detail["stages"]] == list(range(1, 10))
    assert detail["stages"][0]["stage_name"] == "立项定界"
    assert detail["stages"][-1]["stage_name"] == "改善与复制"

    steps = client.get(f"{API}/projects/{pid}/steps").json()
    assert len(steps) == 27
    assert sum(1 for step in steps if step["is_milestone"]) == 9

    expected = _evidence_stage(client)
    # 勾完第 1 阶段也不会另开一套进度，阶段仍等于启动页证据
    for step in [item for item in steps if item["stage_no"] == 1]:
        updated = client.patch(f"{API}/projects/steps/{step['id']}", json={"status": "DONE"})
        assert updated.status_code == 200, updated.text
    after = client.get(f"{API}/projects/{pid}").json()["project"]
    assert after["current_stage"] == expected
    assert 1 <= after["current_stage"] <= 9

    patched = client.patch(f"{API}/projects/{pid}", json={"current_stage": 9})
    assert patched.status_code == 200, patched.text
    assert patched.json()["current_stage"] == expected
    late_steps = client.get(f"{API}/projects/{pid}/steps", params={"stage_no": 9}).json()
    assert len(late_steps) == 3
    late_rows = client.get(
        f"{API}/projects",
        params={"project_type": "GOVERNANCE_SETUP", "stage": expected},
    ).json()
    assert pid in {row["id"] for row in late_rows["items"]}

    rows = client.get(f"{API}/projects", params={"project_type": "GOVERNANCE_SETUP"}).json()[
        "items"
    ]
    assert pid in {row["id"] for row in rows}

    assert client.delete(f"{API}/projects/{pid}").status_code == 200


def test_generic_create_rejects_setup_type(client):
    response = client.post(
        f"{API}/projects",
        json={
            "name": "错误入口创建",
            "methodology": "HYBRID",
            "project_type": "GOVERNANCE_SETUP",
            "owner_user_id": _user_id(client),
        },
    )
    assert response.status_code == 400
    assert "setup-program" in response.json()["detail"]


def test_setup_program_requires_owner(client):
    response = client.post(
        f"{API}/projects/setup-program",
        json={"name": "无 Owner 落地项目"},
    )
    assert response.status_code == 400
    assert "Owner" in response.json()["detail"]


def test_viewer_cannot_create_setup_program(viewer_client):
    response = viewer_client.post(
        f"{API}/projects/setup-program",
        json={"name": "只读创建", "owner_user_id": 1},
    )
    assert response.status_code == 403
