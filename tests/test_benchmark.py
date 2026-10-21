"""对标框架：分类树、覆盖率与流程映射的回归测试。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(r["id"] for r in rows if r["code"] == code)


def _category_id(client, framework: str, code: str) -> int:
    tree = client.get(f"{API}/benchmark/frameworks/{framework}/tree").json()
    stack = list(tree)
    while stack:
        node = stack.pop()
        if node["code"] == code:
            return node["id"]
        stack.extend(node["children"])
    raise AssertionError(f"未找到分类 {framework}/{code}")


# ------------------------------------------------------------------ 框架与分类树


def test_framework_catalog(client):
    r = client.get(f"{API}/benchmark/frameworks")
    assert r.status_code == 200
    items = {f["code"]: f for f in r.json()}
    assert {"SCOR", "APQC_PCF"} <= set(items)

    assert items["SCOR"]["category_count"] == 32
    assert items["APQC_PCF"]["category_count"] == 39
    # 已映射的流程数按框架不同：SCOR 只覆盖供应链相关流程
    assert items["SCOR"]["mapped_process_count"] == 29
    assert items["APQC_PCF"]["mapped_process_count"] == 33


def test_scor_tree_has_six_l1_categories(client):
    tree = client.get(f"{API}/benchmark/frameworks/SCOR/tree", params={"max_level": 2}).json()
    assert [node["code"] for node in tree] == [
        "PLAN",
        "SOURCE",
        "MAKE",
        "DELIVER",
        "RETURN",
        "ENABLE",
    ]
    source = next(node for node in tree if node["code"] == "SOURCE")
    assert {child["code"] for child in source["children"]} == {"S1", "S2", "S3"}
    assert source["subtree_mapped_process_count"] >= source["mapped_process_count"]


def test_max_level_truncates_tree(client):
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 1}).json()
    assert len(tree) == 13
    assert all(node["children"] == [] for node in tree)


# ------------------------------------------------------------------ 覆盖率


def test_scor_coverage_reports_gaps(client):
    data = client.get(
        f"{API}/benchmark/frameworks/SCOR/coverage", params={"process_level": 3}
    ).json()
    assert data["total_processes"] == 28
    assert data["mapped_processes"] == 24
    assert data["coverage_rate"] == 0.8571
    # 研发与费用报销不在 SCOR 范围内，正是两套框架适配差异的体现
    assert {p["code"] for p in data["unmapped_processes"]} == {
        "L3-010",
        "L3-011",
        "L3-012",
        "L3-071",
    }
    by_top = {item["code"]: item for item in data["by_top_category"]}
    assert set(by_top) == {"PLAN", "SOURCE", "MAKE", "DELIVER", "RETURN", "ENABLE"}
    assert by_top["SOURCE"]["mapped_count"] == 5
    assert by_top["ENABLE"]["mapped_count"] == 8


def test_apqc_coverage_is_complete(client):
    data = client.get(
        f"{API}/benchmark/frameworks/APQC_PCF/coverage", params={"process_level": 3}
    ).json()
    assert data["total_processes"] == 28
    assert data["mapped_processes"] == 28
    assert data["coverage_rate"] == 1.0
    assert data["unmapped_processes"] == []
    assert len(data["by_top_category"]) == 13


def test_coverage_rolls_up_descendants(client):
    """上层流程的覆盖率由后代映射聚合，不会出现下层映射了、上层却是 0%。"""
    scor = client.get(
        f"{API}/benchmark/frameworks/SCOR/coverage", params={"process_level": 1}
    ).json()
    assert scor["total_processes"] == 7
    assert scor["mapped_processes"] == 6
    assert {p["code"] for p in scor["unmapped_processes"]} == {"L1-02"}

    apqc = client.get(
        f"{API}/benchmark/frameworks/APQC_PCF/coverage", params={"process_level": 1}
    ).json()
    assert apqc["coverage_rate"] == 1.0


# ------------------------------------------------------------------ 单个流程映射


def test_process_mappings_cover_both_frameworks(client):
    pid = _process_id(client, "L3-032")
    data = client.get(f"{API}/benchmark/processes/{pid}/mappings").json()
    assert data["process"]["code"] == "L3-032"
    assert {m["framework_code"] for m in data["mappings"]} == {"SCOR", "APQC_PCF"}
    assert {m["category_code"] for m in data["mappings"]} == {"S1", "4.2"}


def test_process_mappings_404(client):
    assert client.get(f"{API}/benchmark/processes/999999/mappings").status_code == 404


def test_unknown_framework_404(client):
    assert client.get(f"{API}/benchmark/frameworks/NOPE/tree").status_code == 404


# ------------------------------------------------------------------ 写入与权限


def test_manager_can_create_and_delete_mapping(manager_client):
    pid = _process_id(manager_client, "L3-071")
    category_id = _category_id(manager_client, "SCOR", "E6")
    created = manager_client.post(
        f"{API}/benchmark/mappings",
        json={"process_id": pid, "category_id": category_id, "note": "费用支付归入合同执行"},
    )
    assert created.status_code == 201, created.text
    mapping = created.json()
    assert mapping["framework_code"] == "SCOR"
    assert mapping["category_code"] == "E6"

    duplicate = manager_client.post(
        f"{API}/benchmark/mappings",
        json={"process_id": pid, "category_id": category_id},
    )
    assert duplicate.status_code == 409

    deleted = manager_client.delete(f"{API}/benchmark/mappings/{mapping['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1


def test_viewer_cannot_write_mapping(viewer_client):
    pid = _process_id(viewer_client, "L3-032")
    category_id = _category_id(viewer_client, "SCOR", "S1")
    r = viewer_client.post(
        f"{API}/benchmark/mappings",
        json={"process_id": pid, "category_id": category_id},
    )
    assert r.status_code == 403


def test_mapping_rejects_missing_targets(client):
    pid = _process_id(client, "L3-032")
    category_id = _category_id(client, "SCOR", "S1")
    assert (
        client.post(
            f"{API}/benchmark/mappings",
            json={"process_id": 999999, "category_id": category_id},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/benchmark/mappings",
            json={"process_id": pid, "category_id": 999999},
        ).status_code
        == 404
    )


def test_benchmark_requires_login(anon_client):
    assert anon_client.get(f"{API}/benchmark/frameworks").status_code == 401
