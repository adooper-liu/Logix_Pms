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
    assert {"SCOR", "APQC_PCF", "APQC_PCF_CP", "APQC_PCF_CE"} <= set(items)

    assert items["SCOR"]["category_count"] == 32
    assert items["APQC_PCF"]["category_count"] == 2017
    assert items["APQC_PCF_CP"]["category_count"] == 2039
    assert items["APQC_PCF_CE"]["category_count"] == 2047

    assert items["APQC_PCF"]["is_primary"] is True
    assert items["APQC_PCF_CP"]["is_primary"] is False
    assert items["APQC_PCF_CP"]["base_framework_code"] == "APQC_PCF"
    assert items["APQC_PCF_CE"]["base_framework_code"] == "APQC_PCF"
    assert items["APQC_PCF"]["industry"] == "CROSS_INDUSTRY"
    assert items["APQC_PCF_CP"]["industry"] == "CONSUMER_PRODUCTS"
    assert items["APQC_PCF_CE"]["industry"] == "CONSUMER_ELECTRONICS"
    assert items["APQC_PCF"]["version"] == "8.0"
    assert "APQC" in items["APQC_PCF"]["attribution"]

    # 已映射的流程数按框架不同：SCOR 只覆盖供应链相关流程。
    # L4 活动继承所属 L3 的映射，所以数量包含 L3 + L4。
    assert items["SCOR"]["mapped_process_count"] == 117
    assert items["APQC_PCF"]["mapped_process_count"] == 134
    # 行业变体按 PCF ID 继承主框架映射，不需要重复维护。
    assert items["APQC_PCF_CP"]["mapped_process_count"] == 134
    assert items["APQC_PCF_CE"]["mapped_process_count"] == 134


def test_pcf_tree_keeps_bilingual_names(client):
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 3}).json()
    root = next(node for node in tree if node["code"] == "1.0")
    assert root["name_zh"] == "制定愿景与战略"
    assert root["name_en"] == "Develop Vision and Strategy"
    assert root["name"] == root["name_zh"]
    assert root["external_id"] == "10002"

    # L4/L5 的中文来自本系统覆盖层（参考译文）：name 回落中文，英文原文仍保留在 name_en。
    full = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 5}).json()
    stack = list(full)
    leaf = None
    while stack:
        node = stack.pop()
        if node["level"] == 5:
            leaf = node
            break
        stack.extend(node["children"])
    assert leaf is not None
    assert leaf["name_zh"]
    assert leaf["name"] == leaf["name_zh"]
    assert leaf["name_en"] and leaf["name_en"] != leaf["name_zh"]
    assert leaf["name_zh_source"] == "REFERENCE"


def test_pcf_tree_supports_five_levels(client):
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 5}).json()

    def depth(nodes):
        return max((1 + depth(node["children"]) for node in nodes), default=0)

    assert depth(tree) == 5


def test_category_metrics_endpoint(client):
    tree = client.get(f"{API}/benchmark/frameworks/APQC_PCF/tree", params={"max_level": 1}).json()
    root = next(node for node in tree if node["code"] == "1.0")
    assert root["metric_count"] >= 1

    data = client.get(f"{API}/benchmark/categories/{root['id']}/metrics").json()
    assert data["external_id"] == "10002"
    assert data["metrics"]
    assert all(metric["external_id"] == "10002" for metric in data["metrics"])
    assert all(metric["metric_id"] for metric in data["metrics"])

    assert client.get(f"{API}/benchmark/categories/999999/metrics").status_code == 404


def test_scor_category_has_no_pcf_metrics(client):
    tree = client.get(f"{API}/benchmark/frameworks/SCOR/tree", params={"max_level": 1}).json()
    plan = next(node for node in tree if node["code"] == "PLAN")
    data = client.get(f"{API}/benchmark/categories/{plan['id']}/metrics").json()
    assert data["metrics"] == []


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


def test_industry_variants_inherit_primary_mappings(client):
    """行业版与主框架共享 PCF ID，覆盖率不应要求重复维护映射。"""
    for code in ("APQC_PCF_CP", "APQC_PCF_CE"):
        data = client.get(
            f"{API}/benchmark/frameworks/{code}/coverage", params={"process_level": 3}
        ).json()
        assert data["mapped_processes"] == 28, code
        assert data["coverage_rate"] == 1.0, code
        assert data["unmapped_processes"] == [], code


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
    apqc = next(m for m in data["mappings"] if m["framework_code"] == "APQC_PCF")
    assert apqc["category_external_id"] == "10216"


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
