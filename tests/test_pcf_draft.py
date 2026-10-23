"""从 APQC PCF 生成企业流程架构草稿的回归测试。"""

from __future__ import annotations

API = "/api/v1"
PCF_L3 = "16379"  # 13.1.1 建立和维护流程管理治理
PCF_L1 = "10013"
PCF_L2 = "16378"


def _request(**overrides):
    payload = {
        "framework_code": "APQC_PCF",
        "external_ids": [PCF_L3],
        "include_activities": False,
    }
    payload.update(overrides)
    return payload


def _flat(client) -> dict[int, dict]:
    return {row["id"]: row for row in client.get(f"{API}/process-map/flat").json()}


def _preview(client, **overrides):
    response = client.post(f"{API}/process-map/pcf/preview", json=_request(**overrides))
    assert response.status_code == 200, response.text
    return response.json()


def _generate(client, **overrides):
    response = client.post(f"{API}/process-map/pcf/generate", json=_request(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_preview_expands_ancestors_without_writing(client):
    before = set(_flat(client))
    data = _preview(client)
    assert data["create_count"] == 3
    assert data["reuse_count"] == 0
    assert data["by_level"] == {
        "1": {"create": 1, "reuse": 0},
        "2": {"create": 1, "reuse": 0},
        "3": {"create": 1, "reuse": 0},
    }
    assert {item["external_id"] for item in data["items"]} == {PCF_L1, PCF_L2, PCF_L3}
    # 预览不能落库
    assert set(_flat(client)) == before


def test_generate_is_idempotent_promotable_and_cascades(client):
    root_id = None
    try:
        result = _generate(client)
        assert result["create_count"] == 3
        assert len(result["created_process_ids"]) == 3
        root_id = next(item["process_id"] for item in result["items"] if item["level"] == 1)

        rows = _flat(client)
        l1 = rows[next(i for i in result["created_process_ids"] if rows[i]["level"] == 1)]
        l2 = rows[next(i for i in result["created_process_ids"] if rows[i]["level"] == 2)]
        l3 = rows[next(i for i in result["created_process_ids"] if rows[i]["level"] == 3)]
        assert (l1["code"], l2["code"], l3["code"]) == ("PCF10013", "PCF16378", "PCF16379")
        assert l2["parent_id"] == l1["id"]
        assert l3["parent_id"] == l2["id"]
        assert {l1["name"], l2["name"], l3["name"]} == {
            "开发和管理业务能力",
            "管理业务流程",
            "建立和维护流程管理治理",
        }
        assert all(row["is_draft"] for row in (l1, l2, l3))
        assert all(row["source_framework_code"] == "APQC_PCF" for row in (l1, l2, l3))

        # 草稿不进入正式统计：新增 L3 草稿不应把对标覆盖率的分母撑大
        coverage = client.get(
            f"{API}/benchmark/frameworks/APQC_PCF/coverage",
            params={"process_level": 3},
        ).json()
        assert coverage["total_processes"] == 28
        assert coverage["mapped_processes"] == 28

        # 再跑一次：全部复用，不重复创建
        again = _preview(client)
        assert again["create_count"] == 0
        assert again["reuse_count"] == 3
        repeated = _generate(client)
        assert repeated["create_count"] == 0
        assert repeated["created_process_ids"] == []

        # 同时生成 L4 活动
        activities = _generate(client, include_activities=True)
        assert activities["create_count"] == 4
        assert activities["by_level"]["4"] == {"create": 4, "reuse": 0}
        assert all(
            _flat(client)[pid]["parent_id"] == l3["id"] for pid in activities["created_process_ids"]
        )

        # 确认草稿：is_draft 清零，但来源保留
        all_ids = result["created_process_ids"] + activities["created_process_ids"]
        promoted = client.post(f"{API}/process-map/drafts/promote", json={"process_ids": all_ids})
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["updated"] == 7
        rows = _flat(client)
        assert all(not rows[pid]["is_draft"] for pid in all_ids)
        assert all(rows[pid]["source_external_id"] for pid in all_ids)
    finally:
        if root_id is not None:
            client.delete(f"{API}/process-map/{root_id}")


def test_only_manager_can_generate(viewer_client):
    response = viewer_client.post(f"{API}/process-map/pcf/generate", json=_request())
    assert response.status_code == 403


def test_invalid_framework_or_category(client):
    assert (
        client.post(
            f"{API}/process-map/pcf/preview",
            json=_request(framework_code="SCOR"),
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{API}/process-map/pcf/preview",
            json=_request(framework_code="NOPE"),
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/process-map/pcf/preview",
            json=_request(external_ids=["does-not-exist"]),
        ).status_code
        == 400
    )
