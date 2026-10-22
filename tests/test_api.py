"""接口冒烟测试：覆盖 8 个模块的主要读路径与关键写路径。"""

from __future__ import annotations

API = "/api/v1"


# ------------------------------------------------------------------ 系统


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_schema_builds(client):
    """所有路由的 response_model 都能生成 schema —— 泛型/递归模型出问题会在这里炸。"""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    expected = [
        f"{API}/dashboard/overview",
        f"{API}/process-map/tree",
        f"{API}/workflow/stages",
        f"{API}/workflow/contracts",
        f"{API}/workflow/deliverable-definitions",
        f"{API}/projects",
        f"{API}/projects/{{project_id}}/deliverables",
        f"{API}/deliverables/{{instance_id}}/versions",
        f"{API}/deliverables/{{instance_id}}/versions/upload",
        f"{API}/projects/recommend-methodology",
        f"{API}/tools/match",
        f"{API}/tool-templates",
        f"{API}/tool-templates/{{template_id}}/copy",
        f"{API}/process-documents",
        f"{API}/process-documents/{{document_id}}/promote",
        f"{API}/process-documents/{{document_id}}/upgrade-impact",
        f"{API}/process-documents/{{document_id}}/rebase",
        f"{API}/org-units",
        f"{API}/org-units/tree",
        f"{API}/baselines",
        f"{API}/baselines/governance",
        f"{API}/baselines/findings",
        f"{API}/baselines/audit-scan",
        f"{API}/design/analyze",
        f"{API}/monitor/kpi-radar",
        f"{API}/knowledge",
    ]
    for path in expected:
        assert path in paths, f"路由缺失：{path}"


def test_root_serves_wired_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/static/js/main.js" in r.text
    assert 'type="module"' in r.text, "入口必须以 ES 模块方式加载"
    assert "流程管理系统" in r.text
    # 已知视图路径直接返回前端入口，未知路径仍然 404
    r = client.get("/orgs")
    assert r.status_code == 200
    assert "/static/js/main.js" in r.text
    assert client.get("/not-a-view").status_code == 404


def test_static_assets_served(client):
    for path, marker in [
        ("/static/css/base.css", "--brand"),
        ("/static/css/components.css", ".modal"),
        ("/static/css/views.css", ".gantt"),
        ("/static/js/main.js", "Object.assign(window"),
        ("/static/js/core/api.js", "export const api ="),
        ("/static/js/views/projects.js", "export {"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} 访问失败"
        assert marker in r.text, f"{path} 里找不到 {marker!r}"


def test_sample_prototype_still_available(client):
    r = client.get("/sample")
    assert r.status_code == 200
    assert "const DB = {" in r.text


# ------------------------------------------------------------------ 管理驾驶舱


def test_dashboard_overview(client):
    r = client.get(f"{API}/dashboard/overview")
    assert r.status_code == 200
    data = r.json()

    assert len(data["cards"]) >= 5
    assert len(data["stage_health"]) == 5
    assert data["stage_health"][0]["stage_name"] == "识别与优先级排序"
    assert sum(s["count"] for s in data["methodology_distribution"]) >= 1
    assert len(data["project_board"]) > 0
    assert "by_severity" in data["exception_summary"]


def test_dashboard_board_carries_chinese_labels(client):
    """前端直接使用后端下发的中文标签，不再自己维护枚举映射表。"""
    d = client.get(f"{API}/dashboard/overview").json()
    for p in d["project_board"]:
        assert p["status_label"] and p["status_label"] != p["status"], p
        assert p["methodology_label"] and p["methodology_label"] != p["methodology"], p
    for m in d["methodology_distribution"]:
        assert m["label"] and m["label"] != m["methodology"], m


# ------------------------------------------------------------------ 流程地图


def test_process_map_tree(client):
    r = client.get(f"{API}/process-map/tree")
    assert r.status_code == 200
    tree = r.json()
    assert len(tree) >= 7  # L1 价值链

    scm = next(n for n in tree if n["code"] == "L1-03")
    assert scm["name"] == "采购供应"
    assert any(c["code"] == "L2-003" for c in scm["children"])

    # 下钻到 L4：L2-003 → L3-032 → L4-201
    l2 = next(c for c in scm["children"] if c["code"] == "L2-003")
    l3 = next(c for c in l2["children"] if c["code"] == "L3-032")
    assert any(c["code"] == "L4-201" for c in l3["children"])


def test_process_map_tree_max_level(client):
    r = client.get(f"{API}/process-map/tree", params={"max_level": 2})
    tree = r.json()
    scm = next(n for n in tree if n["code"] == "L1-03")
    for child in scm["children"]:
        assert child["children"] == []


def test_process_map_heatmap(client):
    r = client.get(f"{API}/process-map/heatmap", params={"level": 3})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert items[0]["heat_level"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    # 排序：热度高的在前
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    assert [rank[i["heat_level"]] for i in items] == sorted(rank[i["heat_level"]] for i in items)

    codes = {i["code"] for i in items}
    assert "L3-032" in codes  # 采购需求提报应作为重点改善对象出现


def test_heat_levels_are_calibrated(client):
    """热度阈值必须跟综合得分的实际量级匹配，否则会出现「全是紧急」，等于没有区分度。"""
    items = client.get(f"{API}/process-map/heatmap", params={"level": 3, "limit": 100}).json()
    counts: dict = {}
    for i in items:
        counts[i["heat_level"]] = counts.get(i["heat_level"], 0) + 1

    assert len(counts) >= 3, f"热度分档太少：{counts}"
    assert counts.get("CRITICAL", 0) < len(items) * 0.35, f"紧急档过多：{counts}"
    assert counts.get("LOW", 0) > 0, f"没有低热度流程，阈值偏高：{counts}"


def test_tree_nodes_carry_heat_level(client):
    """热度判定统一由后端给出，前端不再自己算一套。"""
    tree = client.get(f"{API}/process-map/tree").json()
    assert all(n["heat_level"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"} for n in tree)
    scm = next(n for n in tree if n["code"] == "L1-03")
    # 采购供应健康度 58、痛点 4.4 → 至少「高」
    assert scm["heat_level"] in {"CRITICAL", "HIGH"}


def test_process_crud(client):
    payload = {
        "code": "L3-999",
        "name": "测试流程",
        "level": 3,
        "parent_id": None,
        "strategic_importance": 4,
        "pain_score": 4,
        "improvement_space": 4,
    }
    created = client.post(f"{API}/process-map", json=payload)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["priority_score"] == 64.0

    dup = client.post(f"{API}/process-map", json=payload)
    assert dup.status_code == 409

    patched = client.patch(f"{API}/process-map/{pid}", json={"health_score": 55})
    assert patched.status_code == 200
    assert patched.json()["health_score"] == 55

    assert client.delete(f"{API}/process-map/{pid}").status_code == 200
    assert client.get(f"{API}/process-map/{pid}").status_code == 404


# ------------------------------------------------------------------ 标准工作流


def test_workflow_stages(client):
    r = client.get(f"{API}/workflow/stages")
    assert r.status_code == 200
    stages = r.json()
    assert len(stages) == 5
    assert [s["stage_no"] for s in stages] == [1, 2, 3, 4, 5]
    # 4 + 4 + 5 + 6 + 5 = 24
    assert sum(len(s["steps"]) for s in stages) == 24
    assert [len(s["steps"]) for s in stages] == [4, 4, 5, 6, 5]

    first = stages[0]["steps"][0]
    assert first["step_no"] == "1.1"
    assert first["name"] == "流程盘点"


def test_workflow_single_stage(client):
    r = client.get(f"{API}/workflow/stages/4")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 6
    assert client.get(f"{API}/workflow/stages/9").status_code == 404


# ------------------------------------------------------------------ 工具箱


def test_tools_grouped(client):
    r = client.get(f"{API}/tools/grouped")
    assert r.status_code == 200
    groups = {g["category"]: g for g in r.json()}
    assert set(groups) == {"DIAGNOSE", "DESIGN", "DEPLOY", "MONITOR"}
    assert groups["DIAGNOSE"]["count"] == 9
    assert groups["DESIGN"]["count"] == 9
    assert groups["DEPLOY"]["count"] == 7
    assert groups["MONITOR"]["count"] == 8
    assert sum(g["count"] for g in groups.values()) == 33


def test_tool_detail_has_steps(client):
    r = client.get(f"{API}/tools/VSM")
    assert r.status_code == 200
    tool = r.json()
    assert tool["name"] == "价值流图 VSM"
    assert len(tool["steps"]) == 5
    assert tool["category"] == "DIAGNOSE"


def test_tool_match(client):
    r = client.post(f"{API}/tools/match", json={"problem": "审批太多，周期太长怎么办"})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert hits, "应至少匹配到一个工具"
    codes = [h["tool"]["code"] for h in hits]
    assert "RACI" in codes or "BPR6" in codes
    assert hits[0]["score"] > 0


def test_tool_match_no_result(client):
    """完全无关的输入不应硬凑出结果。"""
    r = client.post(f"{API}/tools/match", json={"problem": "qwertyuiop"})
    assert r.status_code == 200
    assert r.json()["hits"] == []


# ------------------------------------------------------------------ 项目组合


def test_project_list_filters(client):
    all_r = client.get(f"{API}/projects")
    assert all_r.status_code == 200
    assert all_r.json()["total"] == 8

    bpr = client.get(f"{API}/projects", params={"methodology": "BPR"}).json()
    assert bpr["total"] == 2
    assert all(p["methodology"] == "BPR" for p in bpr["items"])
    assert bpr["items"][0]["methodology_label"] == "BPR 阶跃式重组"

    active = client.get(f"{API}/projects", params={"status": "ACTIVE"}).json()
    assert active["total"] == 4


def test_project_detail(client):
    listing = client.get(f"{API}/projects", params={"keyword": "采购需求提报"}).json()
    pid = listing["items"][0]["id"]

    r = client.get(f"{API}/projects/{pid}")
    assert r.status_code == 200
    detail = r.json()

    assert detail["project"]["code"] == "PR-2026-018"
    assert detail["project"]["process_name"] == "采购需求提报"
    assert detail["project"]["improvement_pct"] == 64.3

    assert len(detail["stages"]) == 5
    assert sum(s["total"] for s in detail["stages"]) == 24
    assert len(detail["steps"]) == 24
    assert detail["next_action"] is not None
    assert detail["next_action"]["stage_no"] == detail["project"]["current_stage"]


def test_project_step_progress_advances(client):
    created = client.post(
        f"{API}/projects",
        json={"name": "测试项目", "methodology": "BPI", "owner": "测试员", "current_stage": 1},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert len(client.get(f"{API}/projects/{pid}/steps").json()) == 24

    stage1 = client.get(f"{API}/projects/{pid}/steps", params={"stage_no": 1}).json()
    for step in stage1:
        r = client.patch(f"{API}/projects/steps/{step['id']}", json={"status": "DONE"})
        assert r.status_code == 200

    detail = client.get(f"{API}/projects/{pid}").json()
    assert detail["project"]["current_stage"] == 2, "阶段1全部完成后应自动推进到阶段2"
    assert detail["project"]["progress"] == 16.7  # 4/24

    assert client.delete(f"{API}/projects/{pid}").status_code == 200


def test_project_summary(client):
    r = client.get(f"{API}/projects/meta/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 8
    assert data["by_methodology"]["BPR"] >= 2
    assert data["by_status"]["ACTIVE"] >= 4


# ------------------------------------------------------------------ 甘特图与里程碑


def test_schedule_exposes_stages_and_milestones(client):
    listing = client.get(f"{API}/projects", params={"keyword": "采购需求提报"}).json()
    pid = listing["items"][0]["id"]

    r = client.get(f"{API}/projects/{pid}/schedule")
    assert r.status_code == 200
    s = r.json()

    assert s["project_code"] == "PR-2026-018"
    assert s["start_date"] and s["end_date"]
    assert s["total_days"] and s["total_days"] > 0
    assert len(s["stages"]) == 5
    assert sum(st["total"] for st in s["stages"]) == 24

    # 每个阶段的最后一步是里程碑，一共 5 个（4+4+5+6+5 各取最后一步）
    assert len(s["milestones"]) == 5
    assert [m["step_no"] for m in s["milestones"]] == ["1.4", "2.4", "3.5", "4.6", "5.5"]

    # 阶段日期必须递增，且落在项目窗口内
    dates = [st["end"] for st in s["stages"]]
    assert dates == sorted(dates)
    assert dates[-1] <= s["end_date"]

    # 里程碑日期与所属阶段的结束日一致
    for m in s["milestones"]:
        stage = next(st for st in s["stages"] if st["stage_no"] == m["stage_no"])
        assert m["due_date"] == stage["end"]


def test_schedule_flags_overdue_milestones(client):
    created = client.post(
        f"{API}/projects",
        json={
            "name": "逾期里程碑测试",
            "methodology": "BPI",
            "owner": "测试员",
            # 把整个窗口放在过去，所有未完成的里程碑都应判逾期
            "start_date": "2020-01-01",
            "end_date": "2020-06-30",
        },
    ).json()
    s = client.get(f"{API}/projects/{created['id']}/schedule").json()
    assert s["milestones"], "应生成里程碑"
    assert all(m["is_overdue"] for m in s["milestones"])
    client.delete(f"{API}/projects/{created['id']}")


def test_steps_carry_due_dates(client):
    listing = client.get(f"{API}/projects", params={"keyword": "采购需求提报"}).json()
    pid = listing["items"][0]["id"]
    steps = client.get(f"{API}/projects/{pid}/steps").json()
    assert all(st["due_date"] for st in steps), "种子项目的步骤应带计划日期"
    due = [st["due_date"] for st in steps]
    assert due == sorted(due), "计划日期应随步骤顺序递增"


# ------------------------------------------------------------------ 立项向导


def test_recommend_bpr_for_severe_and_high_target(client):
    r = client.post(
        f"{API}/projects/recommend-methodology",
        json={
            "process_state": "SEVERE_OUTDATED",
            "target_improvement_pct": 60,
            "scope": "END_TO_END",
            "involves_org_change": True,
            "data_available": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["methodology"] == "BPR"
    assert data["confidence"] > 0.7
    assert len(data["rationale"]) >= 3
    assert len(data["recommended_tools"]) > 0
    assert all(t["code"] for t in data["recommended_tools"])


def test_recommend_lean_for_shopfloor(client):
    r = client.post(
        f"{API}/projects/recommend-methodology",
        json={
            "process_state": "SHOPFLOOR_WASTE",
            "target_improvement_pct": 20,
            "scope": "SHOPFLOOR",
        },
    )
    assert r.status_code == 200
    assert r.json()["methodology"] == "LEAN"


def test_recommend_upgrades_bpi_to_bpr_on_step_change(client):
    """目标 ≥50% 时，渐进方案应被上调为 BPR。"""
    r = client.post(
        f"{API}/projects/recommend-methodology",
        json={
            "process_state": "SOUND_BUT_INEFFICIENT",
            "target_improvement_pct": 55,
            "scope": "LOCAL",
        },
    )
    assert r.json()["methodology"] == "BPR"


def test_recommend_warns_on_low_target_for_broken_process(client):
    r = client.post(
        f"{API}/projects/recommend-methodology",
        json={"process_state": "SEVERE_OUTDATED", "target_improvement_pct": 8, "scope": "LOCAL"},
    )
    data = r.json()
    assert data["confidence"] < 0.62
    assert any("局部改善" in risk or "过时" in risk for risk in data["risks"])


def test_recommend_mixed(client):
    r = client.post(
        f"{API}/projects/recommend-methodology",
        json={"process_state": "MIXED", "target_improvement_pct": 40, "scope": "END_TO_END"},
    )
    assert r.json()["methodology"] == "HYBRID"
    assert len(r.json()["phase_plan"]) == 3


# ------------------------------------------------------------------ 流程设计器


def test_design_get_and_analyze(client):
    tree = client.get(f"{API}/process-map/flat", params={"keyword": "采购需求提报"}).json()
    pid = tree[0]["id"]

    model = client.get(f"{API}/processes/{pid}/design")
    assert model.status_code == 200
    body = model.json()
    assert len(body["nodes"]) == 6
    assert len(body["edges"]) == 6
    assert body["process_name"] == "采购需求提报"

    analysis = client.post(f"{API}/processes/{pid}/design/analyze")
    assert analysis.status_code == 200
    data = analysis.json()
    m = data["metrics"]

    # 线性合计（每个节点各算一次）= 作业 960 + 等待 5760
    assert m["linear_lead_time_minutes"] == 6720.0
    # 期望值计入了两件事：n4→n6 的 30% 驳回回路，以及 n2/n6 的节点级返工率
    #   A[n2]=A[n3]=A[n4]=10/7, A[n5]=1, A[n6]=3/7
    #   返工倍率 n2=1/0.75, n6=1/0.65
    assert m["lead_time_minutes"] == 9458.9
    assert m["process_time_minutes"] == 1172.5
    # 增值时间只算「一次通过」：n1 120 + n2 240×(10/7) + n5 180
    assert m["value_added_minutes"] == 642.9
    assert m["wait_minutes"] == 8286.4
    assert m["pce"] == 0.068
    assert m["wait_ratio"] == 0.876
    assert m["rework_loss_minutes"] == 3314.9
    assert m["rework_work_minutes"] == 434.5
    # 成本与时间同口径：n2 返工率 25%、n6 返工率 35%，重复执行的成本也要计入
    assert m["unit_cost"] == 65.51
    assert m["has_branch_or_loop"] is True
    assert m["diverged"] is False

    # 期望周期明显高于线性合计，说明回路与返工确实被计入了
    assert m["lead_time_minutes"] > m["linear_lead_time_minutes"]

    assert m["handoff_count"] == 5
    assert m["total_approval_levels"] == 4
    assert m["lane_count"] == 5

    codes = {s["code"] for s in data["suggestions"]}
    assert "LOW_PCE" in codes
    assert "WAIT_DOMINANT" in codes
    assert "TOO_MANY_APPROVALS" in codes
    assert "MANY_HANDOFFS" in codes
    assert "REWORK_LOSS" in codes

    # 瓶颈识别要有区分度：等待型流程里几乎每个节点等待占比都高，
    # 如果判据用「等待占比」就会得出「全是瓶颈」，等于没结论
    bottlenecks = [n for n in data["nodes"] if n["is_bottleneck"]]
    assert {n["node_key"] for n in bottlenecks} == {"n2", "n4", "n6"}
    assert len(bottlenecks) < len(data["nodes"])

    bottleneck_sug = next(s for s in data["suggestions"] if s["code"] == "BOTTLENECK")
    assert "需求审批" in bottleneck_sug["title"], "瓶颈清单应按端到端时长降序，最长者在前"

    # 并行候选要按连线推导，并排除「驳回」这类分支边
    parallel = next(s for s in data["suggestions"] if s["code"] == "SERIAL_TO_PARALLEL")
    assert parallel["related_nodes"] == ["n1", "n2"]
    assert "驳回" not in parallel["detail"]

    assert data["recommended_methodology"] == "BPR"
    # 建议按严重度排序，HIGH 在最前
    assert data["suggestions"][0]["severity"] == "HIGH"


def test_rework_cost_counts_repeated_execution(client):
    """返工 50% → 期望执行 2 次，成本也必须按 2 次计，不能只放大时间。"""
    payload = {
        "nodes": [
            {
                "node_key": "A",
                "name": "返工节点",
                "node_type": "TASK",
                "lane": "主流程",
                "duration_minutes": 10,
                "wait_minutes": 0,
                "cost": 100,
                "rework_rate": 0.5,
                "is_value_added": True,
                "sequence_order": 1,
            }
        ],
        "edges": [],
    }
    m = client.post(f"{API}/design/analyze", json=payload).json()["metrics"]
    assert m["process_time_minutes"] == 20.0
    assert m["unit_cost"] == 200.0


def test_design_inline_analyze(client):
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "接单",
                "node_type": "TASK",
                "lane": "销售",
                "duration_minutes": 10,
                "wait_minutes": 0,
                "is_value_added": True,
            },
            {
                "node_key": "b",
                "name": "审核",
                "node_type": "APPROVAL",
                "lane": "财务",
                "duration_minutes": 10,
                "wait_minutes": 400,
                "is_value_added": False,
                "approval_levels": 4,
            },
            {
                "node_key": "c",
                "name": "发货",
                "node_type": "TASK",
                "lane": "仓储",
                "duration_minutes": 10,
                "wait_minutes": 0,
                "is_value_added": True,
            },
            {
                "node_key": "d",
                "name": "质检",
                "node_type": "TASK",
                "lane": "质检",
                "duration_minutes": 10,
                "wait_minutes": 0,
                "is_value_added": True,
            },
        ],
        "edges": [
            {"source_key": "a", "target_key": "b"},
            {"source_key": "b", "target_key": "c"},
            {"source_key": "c", "target_key": "d"},
        ],
    }
    r = client.post(f"{API}/design/analyze", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["metrics"]["node_count"] == 4
    assert data["metrics"]["wait_ratio"] > 0.9
    assert data["metrics"]["handoff_count"] == 3
    # PCE 极低 + 三次跨部门移交 → 结构性断裂，应推荐 BPR 而非精益
    assert data["recommended_methodology"] == "BPR"


def test_design_inline_analyze_prefers_lean_when_wait_only(client):
    """单一部门内等待为主时，应推荐精益而非 BPR。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "备料",
                "node_type": "TASK",
                "lane": "车间",
                "duration_minutes": 10,
                "wait_minutes": 300,
                "is_value_added": True,
            },
            {
                "node_key": "b",
                "name": "加工",
                "node_type": "TASK",
                "lane": "车间",
                "duration_minutes": 10,
                "wait_minutes": 200,
                "is_value_added": True,
            },
        ],
        "edges": [{"source_key": "a", "target_key": "b"}],
    }
    data = client.post(f"{API}/design/analyze", json=payload).json()
    assert data["metrics"]["handoff_count"] == 0
    assert data["recommended_methodology"] == "LEAN"


def test_linear_model_expected_equals_linear(client):
    """没有分支也没有返工时，期望值必须严格等于线性合计。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "A",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 100,
                "wait_minutes": 50,
                "is_value_added": True,
            },
            {
                "node_key": "b",
                "name": "B",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 200,
                "wait_minutes": 0,
                "is_value_added": True,
            },
            {
                "node_key": "c",
                "name": "结束",
                "node_type": "END",
                "lane": "L",
                "duration_minutes": 0,
                "wait_minutes": 0,
                "is_value_added": False,
            },
        ],
        "edges": [
            {"source_key": "a", "target_key": "b"},
            {"source_key": "b", "target_key": "c"},
        ],
    }
    m = client.post(f"{API}/design/analyze", json=payload).json()["metrics"]
    assert m["lead_time_minutes"] == m["linear_lead_time_minutes"] == 350.0
    assert m["rework_loss_minutes"] == 0
    assert m["has_branch_or_loop"] is False
    assert m["diverged"] is False


def test_loop_inflates_expected_lead_time(client):
    """C→B 有 50% 驳回回路时，B 与 C 的期望执行次数都是 2 次。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "A",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 10,
                "is_value_added": True,
            },
            {
                "node_key": "b",
                "name": "B",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 20,
                "is_value_added": True,
            },
            {
                "node_key": "c",
                "name": "审批",
                "node_type": "APPROVAL",
                "lane": "L",
                "duration_minutes": 40,
                "is_value_added": False,
            },
            {
                "node_key": "e",
                "name": "结束",
                "node_type": "END",
                "lane": "L",
                "duration_minutes": 0,
            },
        ],
        "edges": [
            {"source_key": "a", "target_key": "b"},
            {"source_key": "b", "target_key": "c"},
            {"source_key": "c", "target_key": "b", "label": "驳回", "probability": 0.5},
            {"source_key": "c", "target_key": "e", "label": "通过", "probability": 0.5},
        ],
    }
    data = client.post(f"{API}/design/analyze", json=payload)
    m = data.json()["metrics"]

    assert m["has_branch_or_loop"] is True
    assert m["linear_lead_time_minutes"] == 70.0
    assert m["lead_time_minutes"] == 130.0, "B/C 各期望执行 2 次"
    assert m["rework_loss_minutes"] == 60.0

    visits = {n["node_key"]: n["visit_count"] for n in data.json()["nodes"]}
    assert visits["a"] == 1.0
    assert visits["b"] == 2.0 and visits["c"] == 2.0
    assert visits["e"] == 1.0


def test_untyped_node_rework_multiplier(client):
    """节点级返工率按 1/(1-r) 折算成期望执行次数。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "A",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 100,
                "rework_rate": 0.5,
                "is_value_added": True,
            },
        ],
        "edges": [],
    }
    m = client.post(f"{API}/design/analyze", json=payload).json()["metrics"]
    assert m["lead_time_minutes"] == 200.0  # 100 × 1/(1-0.5)
    assert m["rework_loss_minutes"] == 100.0  # 相对「不返工」多出一倍


def test_unextable_loop_is_flagged_not_silently_wrong(client):
    """START → B → START 且概率都是 100%：期望周期发散，必须显式标注。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "A",
                "node_type": "START",
                "lane": "L",
                "duration_minutes": 10,
            },
            {
                "node_key": "b",
                "name": "B",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 20,
            },
        ],
        "edges": [
            {"source_key": "a", "target_key": "b"},
            {"source_key": "b", "target_key": "a"},
        ],
    }
    data = client.post(f"{API}/design/analyze", json=payload).json()
    assert data["metrics"]["diverged"] is True
    # 兜底退回线性口径，而不是返回一个巨大的数字冒充期望值
    assert data["metrics"]["lead_time_minutes"] == 30.0
    codes = {s["code"] for s in data["suggestions"]}
    assert "DIVERGED" in codes


def test_no_entry_point_is_flagged(client):
    """所有节点都有入边、又没有 START：等于没有入口，测算结果无意义。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "A",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 10,
            },
            {
                "node_key": "b",
                "name": "B",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 20,
            },
        ],
        "edges": [
            {"source_key": "a", "target_key": "b"},
            {"source_key": "b", "target_key": "a"},
        ],
    }
    data = client.post(f"{API}/design/analyze", json=payload).json()
    assert data["metrics"]["diverged"] is True
    assert "NO_ENTRY" in {s["code"] for s in data["suggestions"]}


def test_unreachable_nodes_are_reported(client):
    """与入口断开的闭环会被指出，且不计入周期。"""
    payload = {
        "nodes": [
            {
                "node_key": "a",
                "name": "入口",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 10,
            },
            {
                "node_key": "x",
                "name": "孤立环1",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 999,
            },
            {
                "node_key": "y",
                "name": "孤立环2",
                "node_type": "TASK",
                "lane": "L",
                "duration_minutes": 999,
            },
        ],
        "edges": [
            {"source_key": "x", "target_key": "y"},
            {"source_key": "y", "target_key": "x"},
        ],
    }
    data = client.post(f"{API}/design/analyze", json=payload).json()
    assert data["metrics"]["lead_time_minutes"] == 10.0  # 只算入口节点
    for key in ("x", "y"):
        node = next(n for n in data["nodes"] if n["node_key"] == key)
        assert node["visit_count"] == 0
        assert node["weighted_minutes"] == 0
    assert "UNREACHABLE_NODES" in {s["code"] for s in data["suggestions"]}


def test_design_save_replaces_model(client):
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-998", "name": "设计器测试流程", "level": 3},
    ).json()
    pid = created["id"]

    payload = {
        "nodes": [
            {
                "node_key": "s",
                "name": "开始",
                "node_type": "START",
                "lane": "发起方",
                "duration_minutes": 5,
            },
            {
                "node_key": "t",
                "name": "结束",
                "node_type": "END",
                "lane": "受理方",
                "duration_minutes": 5,
            },
        ],
        "edges": [{"source_key": "s", "target_key": "t"}],
    }
    saved = client.put(f"{API}/processes/{pid}/design", json=payload)
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["nodes"]) == 2
    # 未传 sequence_order 时按数组顺序自动编号
    assert [n["sequence_order"] for n in saved.json()["nodes"]] == [1, 2]

    # 覆盖式保存：再提交一次应替换而非追加
    payload["nodes"].append(
        {
            "node_key": "u",
            "name": "中间",
            "node_type": "TASK",
            "lane": "受理方",
            "duration_minutes": 5,
        }
    )
    payload["edges"].append({"source_key": "t", "target_key": "u"})
    again = client.put(f"{API}/processes/{pid}/design", json=payload)
    assert len(again.json()["nodes"]) == 3

    client.delete(f"{API}/process-map/{pid}")


def test_design_read_only_returns_empty(client):
    """空的流程模型不应报错，而是返回空图。"""
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-EMPTY", "name": "空流程图", "level": 3},
    ).json()
    model = client.get(f"{API}/processes/{created['id']}/design").json()
    assert model["nodes"] == [] and model["edges"] == []
    assert model["version"] == 0
    client.delete(f"{API}/process-map/{created['id']}")


def test_design_version_conflict_detected(client):
    """两人先后保存同一条流程：后保存者提交旧版本号必须被拒绝。"""
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-VER", "name": "版本冲突测试", "level": 3},
    ).json()
    pid = created["id"]
    payload = {
        "nodes": [
            {"node_key": "a", "name": "A", "node_type": "TASK", "lane": "L", "duration_minutes": 10}
        ],
        "edges": [],
    }

    # A 先保存（基于 v0），服务端升到 v1
    first = client.put(f"{API}/processes/{pid}/design", json={**payload, "expected_version": 0})
    assert first.status_code == 200
    assert first.json()["version"] == 1

    # B 手里还是 v0，再提交应该被拒
    stale = client.put(f"{API}/processes/{pid}/design", json={**payload, "expected_version": 0})
    assert stale.status_code == 409
    assert "已被他人修改" in stale.json()["detail"]

    # B 刷新到 v1 后可以正常保存
    ok = client.put(f"{API}/processes/{pid}/design", json={**payload, "expected_version": 1})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    # 不传版本号时不做检查（向后兼容脚本/导入场景）
    legacy = client.put(f"{API}/processes/{pid}/design", json=payload)
    assert legacy.status_code == 200

    client.delete(f"{API}/process-map/{pid}")


def test_design_rejects_bad_payload(client):
    pid = client.get(f"{API}/process-map/flat", params={"keyword": "询比价"}).json()[0]["id"]

    dup = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {"node_key": "x", "name": "A", "node_type": "TASK", "lane": "L"},
                {"node_key": "x", "name": "B", "node_type": "TASK", "lane": "L"},
            ],
            "edges": [],
        },
    )
    assert dup.status_code == 400
    assert "node_key 重复" in dup.json()["detail"]

    dangling = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [{"node_key": "x", "name": "A", "node_type": "TASK", "lane": "L"}],
            "edges": [{"source_key": "x", "target_key": "ghost"}],
        },
    )
    assert dangling.status_code == 400
    assert "不存在的节点" in dangling.json()["detail"]


# ------------------------------------------------------------------ 运营监控


def test_kpi_radar(client):
    r = client.get(f"{API}/monitor/kpi-radar")
    assert r.status_code == 200
    data = r.json()
    assert len(data["dimensions"]) == 4
    assert {d["dimension"] for d in data["dimensions"]} == {
        "EFFICIENCY",
        "QUALITY",
        "COST",
        "FLEXIBILITY",
    }
    assert data["overall_achievement"] > 0
    assert all(d["status"] in {"GOOD", "WATCH", "RISK"} for d in data["dimensions"])
    assert len(data["series"]) == 15
    assert all(len(s["points"]) == 6 for s in data["series"])


def test_kpi_achievement_direction(client):
    """越小越好的指标：目标 5 天、当前 8.2 天 → 达成率应低于 100%。"""
    kpis = client.get(f"{API}/monitor/kpis", params={"dimension": "EFFICIENCY"}).json()
    cycle = next(k for k in kpis if k["code"] == "EFF-01")
    assert cycle["latest_value"] == 8.2
    assert cycle["target_value"] == 5.0
    assert cycle["achievement_rate"] == 61.0
    assert cycle["trend"] == "DOWN"  # 周期在下降，是好事

    otd = next(
        k
        for k in client.get(f"{API}/monitor/kpis", params={"dimension": "QUALITY"}).json()
        if k["code"] == "QUA-01"
    )
    assert otd["direction"] == "HIGHER_BETTER"
    assert otd["achievement_rate"] == 92.6


def test_kpi_record_upsert(client):
    kpis = client.get(f"{API}/monitor/kpis").json()
    kpi_id = kpis[0]["id"]

    first = client.post(
        f"{API}/monitor/kpis/{kpi_id}/records",
        json={"period": "2026-10-01", "value": 7.5, "note": "十月首测"},
    )
    assert first.status_code == 201

    # 同期间重复提交应覆盖
    second = client.post(
        f"{API}/monitor/kpis/{kpi_id}/records",
        json={"period": "2026-10-01", "value": 7.0, "note": "修正"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["value"] == 7.0

    records = client.get(f"{API}/monitor/kpis/{kpi_id}/records").json()
    assert sum(1 for r in records if r["period"] == "2026-10-01") == 1


def test_exceptions(client):
    summary = client.get(f"{API}/monitor/exceptions/summary").json()
    assert summary["total"] == 8
    assert summary["open"] == 2
    assert summary["in_progress"] == 4
    assert summary["resolved"] == 1
    assert summary["closed"] == 1
    assert summary["by_severity"]["HIGH"] >= 1

    high = client.get(f"{API}/monitor/exceptions", params={"severity": "HIGH"}).json()
    assert len(high) == 4

    overdue = [e for e in client.get(f"{API}/monitor/exceptions").json() if e["is_overdue"]]
    assert overdue, "应存在已超期未闭环的异常事件"


def test_exception_lifecycle(client):
    created = client.post(
        f"{API}/monitor/exceptions",
        json={"title": "测试异常", "severity": "MEDIUM", "owner": "测试员"},
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    assert created.json()["code"].startswith("EXC-")
    assert created.json()["status"] == "OPEN"

    resolved = client.patch(
        f"{API}/monitor/exceptions/{eid}",
        json={"status": "RESOLVED", "root_cause": "根因测试", "action_taken": "已处理"},
    )
    assert resolved.json()["resolved_at"] is not None

    closed = client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "CLOSED"})
    assert closed.json()["closed_at"] is not None

    assert client.delete(f"{API}/monitor/exceptions/{eid}").status_code == 200


def test_reopened_exception_clears_closure_timestamps(client):
    """重开意味着闭环结论被推翻，两个时间戳必须清空。

    否则台账会出现「未闭环但已有闭环时间」的矛盾记录，
    按 resolved_at 统计闭环率的报表会失真。
    """
    created = client.post(
        f"{API}/monitor/exceptions", json={"title": "重开测试", "severity": "LOW"}
    ).json()
    eid = created["id"]
    client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "RESOLVED"})
    closed = client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "CLOSED"}).json()
    assert closed["resolved_at"] and closed["closed_at"]

    reopened = client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "OPEN"}).json()
    assert reopened["status"] == "OPEN"
    assert reopened["resolved_at"] is None, "重开后仍带着解决时间"
    assert reopened["closed_at"] is None, "重开后仍带着关闭时间"

    # 再次关闭时应写入新的时间戳
    again = client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "CLOSED"}).json()
    assert again["resolved_at"] and again["closed_at"]
    assert again["closed_at"] != closed["closed_at"]


def test_datetimes_serialized_with_utc_offset(client):
    """出参必须带 +00:00，否则前端没法区分 UTC 和本地时间。"""
    e = client.post(
        f"{API}/monitor/exceptions", json={"title": "序列化探测", "severity": "LOW"}
    ).json()
    assert e["detected_at"].endswith("+00:00"), e["detected_at"]


def test_exception_overdue_with_timezone_aware_input(client):
    """入参带时区时按 UTC 归一化，超期判断方向必须正确。"""
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    not_due = client.post(
        f"{API}/monitor/exceptions", json={"title": "未超期", "severity": "LOW", "due_at": future}
    ).json()
    assert not_due["is_overdue"] is False, not_due["due_at"]

    past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    overdue = client.post(
        f"{API}/monitor/exceptions", json={"title": "已超期", "severity": "LOW", "due_at": past}
    ).json()
    assert overdue["is_overdue"] is True, overdue["due_at"]


# ------------------------------------------------------------------ 知识库


def test_knowledge_list_and_search(client):
    r = client.get(f"{API}/knowledge")
    assert r.status_code == 200
    assert r.json()["total"] == 9

    bpr = client.get(f"{API}/knowledge", params={"methodology": "BPR"}).json()
    assert all(i["methodology"] == "BPR" for i in bpr["items"])

    kw = client.get(f"{API}/knowledge", params={"keyword": "VSM"}).json()
    assert kw["total"] >= 1
    assert any("VSM" in i["title"] for i in kw["items"])


def test_knowledge_tag_filter_and_cloud(client):
    tags = client.get(f"{API}/knowledge/meta/tags").json()["tags"]
    assert tags and "count" in tags[0]

    top_tag = tags[0]["tag"]
    filtered = client.get(f"{API}/knowledge", params={"tag": top_tag}).json()
    assert filtered["total"] >= 1
    assert all(top_tag in i["tags"] for i in filtered["items"])


def test_knowledge_tag_filter_total_independent_of_page_size(client):
    """标签筛选必须在 SQL 层完成。

    早期实现是「先分页取一页 → 再在内存里按标签过滤」，导致 total 随 page_size 变化：
    page_size=50 报 2 条、page_size=2 报 0 条。这条测试用来钉住这个回归。
    """
    full = client.get(f"{API}/knowledge", params={"tag": "BPR", "page_size": 50}).json()
    assert full["total"] >= 2

    for size in (1, 2, 5):
        paged = client.get(f"{API}/knowledge", params={"tag": "BPR", "page_size": size}).json()
        assert paged["total"] == full["total"], f"page_size={size} 时 total 变了"
        assert len(paged["items"]) == min(size, full["total"])
        assert all("BPR" in i["tags"] for i in paged["items"])


def test_knowledge_hot_sort(client):
    items = client.get(f"{API}/knowledge", params={"sort": "hot"}).json()["items"]
    counts = [i["download_count"] for i in items]
    assert counts == sorted(counts, reverse=True)
    assert items[0]["title"] == "RACI 权责矩阵模板（含示例）"


def test_knowledge_crud_and_read(client):
    created = client.post(
        f"{API}/knowledge",
        json={
            "title": "测试条目",
            "type": "CASE",
            "tags": ["测试"],
            "summary": "摘要",
            "content": "正文",
        },
    )
    assert created.status_code == 201
    kid = created.json()["id"]
    assert created.json()["download_count"] == 0

    read = client.post(f"{API}/knowledge/{kid}/read", json={"increment": 3})
    assert read.json()["download_count"] == 3

    patched = client.patch(f"{API}/knowledge/{kid}", json={"summary": "改过的摘要"})
    assert patched.json()["summary"] == "改过的摘要"

    assert client.delete(f"{API}/knowledge/{kid}").status_code == 200


def test_lower_better_zero_value_is_full_achievement():
    """零缺陷/零客诉这类指标，实际值 0 就是达成目标，不能算成空值。"""
    from app.api.v1.monitor import _achievement

    assert _achievement("LOWER_BETTER", 0, 5) == 100.0
    assert _achievement("LOWER_BETTER", 10, 5) == 50.0
