"""工具模板填写后挂到流程，OGSM / 目标树同时写成战略目标。"""

from __future__ import annotations

API = "/api/v1"


def _process(client, code="L3-032"):
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)


def _delete_objective(client, objective_id):
    client.delete(f"{API}/strategy/objectives/{objective_id}")


def test_ogsm_sheet_writes_objective_and_mounts(client):
    process = _process(client)
    before = client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"]
    form = client.get(f"{API}/tools/OGSM/sheet-form")
    assert form.status_code == 200
    assert form.json()["writes"] == "objective"
    response = client.post(
        f"{API}/tools/OGSM/sheets",
        json={
            "process_id": process["id"],
            "values": {
                "direction": "测试把采购周期写进目标",
                "baseline": "14",
                "target": "5",
                "unit": "天",
                "approach": "靠采购需求提报",
                "measure": "端到端周期",
                "source": "模板填写测试",
            },
        },
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["objective_codes"]
    assert saved["process_code"] == "L3-032"
    after = client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"]
    assert after == before + 1
    card = client.get(f"{API}/process-card/{process['id']}").json()
    assert any(row["tool_code"] == "OGSM" for row in card["sheets"])
    _delete_objective(client, saved["objective_id"])


def test_swot_sheet_stays_on_process_until_kept(client):
    process = _process(client)
    before = client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"]
    held = client.post(
        f"{API}/tools/SWOT/sheets",
        json={
            "process_id": process["id"],
            "values": {"strengths": "计划员熟悉归并规则", "keep": ""},
            "make_objectives": False,
        },
    )
    assert held.status_code == 201, held.text
    assert held.json()["objective_codes"] == []
    assert client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"] == before
    written = client.post(
        f"{API}/tools/SWOT/sheets",
        json={
            "process_id": process["id"],
            "values": {
                "strengths": "计划员熟悉归并规则",
                "keep": "留下缩短审批\n留下减少返工",
            },
            "make_objectives": True,
        },
    )
    assert written.status_code == 201, written.text
    body = written.json()
    assert len(body["objective_codes"]) == 2
    for code in body["objective_codes"]:
        rows = client.get(f"{API}/strategy/objectives?year=2026").json()
        match = next(row for row in rows if row["code"] == code)
        _delete_objective(client, match["id"])


def test_every_tool_mounts_once_and_has_a_sheet(client):
    from pathlib import Path

    from app.seed.corpus import TOOLS

    text = Path("web/js/views/shared/tool_mount.js").read_text(encoding="utf-8")
    codes = [row["code"] for row in TOOLS]
    assert len(codes) == len(set(codes)) == 36
    for code in codes:
        assert text.count(f"'{code}'") == 1, code
        form = client.get(f"{API}/tools/{code}/sheet-form")
        assert form.status_code == 200, code
        assert form.json()["fields"], code


def test_each_tool_uses_its_own_library_template(client):
    from app.seed.sheet_templates import SHEET_TEMPLATES

    listed = client.get(f"{API}/tool-templates").json()
    by_tool = {row[2]: row for row in SHEET_TEMPLATES}
    assert len(by_tool) == 36
    for code, spec in by_tool.items():
        form = client.get(f"{API}/tools/{code}/sheet-form").json()
        assert form["template_code"] == spec[0], code
        assert form["template_name"] == spec[1], code
        assert [field["key"] for field in form["fields"]] == [field["key"] for field in spec[3]]
        assert "围绕结果组织工作，而非任务" not in " ".join(
            field["label"] for field in form["fields"]
        )
    bpr = client.get(f"{API}/tools/BPR6/sheet-form").json()
    assert bpr["template_name"] == "BPR 六原则检查表"
    principles = [field for field in bpr["fields"] if field["kind"] == "choice"]
    assert len(principles) == 6
    assert [field["key"] for field in principles] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    assert principles[0]["options"] == ["符合", "部分符合", "未体现"]
    assert any(row["code"] == "TPL-BPR6" and row["name"] == "BPR 六原则检查表" for row in listed)
    process = _process(client)
    values = {
        field["key"]: ("符合" if field["kind"] == "choice" else "对照 To-Be 第 2 段")
        for field in bpr["fields"]
    }
    saved = client.post(
        f"{API}/tools/BPR6/sheets", json={"process_id": process["id"], "values": values}
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["objective_codes"] == []
    assert len(saved.json()["fields"]) == len(bpr["fields"])


def test_generic_tool_sheet_does_not_create_objective(client):
    process = _process(client)
    before = client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"]
    form = client.get(f"{API}/tools/SIPOC/sheet-form").json()
    assert form["writes"] == "mount"
    assert form["fields"]
    values = {field["key"]: "供应商到计划员" for field in form["fields"]}
    response = client.post(
        f"{API}/tools/SIPOC/sheets",
        json={"process_id": process["id"], "values": values},
    )
    assert response.status_code == 201, response.text
    assert response.json()["objective_codes"] == []
    assert client.get(f"{API}/strategy/summary?year=2026").json()["objective_count"] == before
