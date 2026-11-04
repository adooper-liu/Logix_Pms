"""M4固定原模型与建模/分析/设计原方法交付。"""

from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def work_process(client):
    response = client.post(
        API + "/process-map",
        json={
            "code": "WRK-" + uuid4().hex[:8],
            "name": "作业测试",
            "level": 3,
            "owner_user_id": client.get(API + "/auth/me").json()["id"],
        },
    )
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    model = {
        "nodes": [
            {"node_key": "start", "name": "开始", "node_type": "START", "lane": "主线"},
            {"node_key": "task", "name": "核对", "node_type": "TASK", "lane": "主线"},
            {"node_key": "end", "name": "结束", "node_type": "END", "lane": "主线"},
        ],
        "edges": [
            {"source_key": "start", "target_key": "task"},
            {"source_key": "task", "target_key": "end"},
        ],
    }
    saved = client.put(f"{API}/processes/{pid}/design", json=model)
    assert saved.status_code == 200, saved.text
    yield pid, model, saved.json()
    client.delete(f"{API}/process-map/{pid}")


def test_frozen_model_is_not_overwritten_by_original_editor(client, work_process):
    pid, model, current = work_process
    response = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "现场确认输入版本"},
    )
    assert response.status_code == 200, response.text
    frozen = response.json()
    assert frozen["frozen_at"].endswith("+00:00")
    assert frozen["status"] == "DRAFT"
    assert client.get(f"{API}/processes/{pid}/design").json()["published_version"] == 0
    model["nodes"][1]["name"] = "修改后"
    changed = client.put(f"{API}/processes/{pid}/design", json=model)
    assert changed.status_code == 200, changed.text
    assert changed.json()["version_id"] != frozen["id"]
    original = client.get(f"{API}/processes/{pid}/design/versions/{frozen['id']}").json()
    assert original["nodes"][1]["name"] == "核对"
    again = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "旧页"},
    )
    assert again.status_code == 409


def test_freeze_requires_write_and_preserves_rollback_source(client, viewer_client, work_process):
    pid, model, current = work_process
    data = {"expected_version": current["version"], "note": "冻结现场依据"}
    assert viewer_client.post(f"{API}/processes/{pid}/design/freeze", json=data).status_code == 403
    response = client.post(f"{API}/processes/{pid}/design/freeze", json=data)
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    rolled = client.post(
        f"{API}/processes/{pid}/design/versions/{ident}/rollback",
        json={"note": "从固定版恢复工作副本"},
    )
    assert rolled.status_code == 200, rolled.text
    assert client.get(f"{API}/processes/{pid}/design/versions/{ident}").status_code == 200


def work_payload(client, model_id, kind="MODELING", upstream=None, source="OBSERVED"):
    people = client.get(API + "/auth/users").json()
    reviewer = next(row for row in people if row["username"] == "chen")
    return {
        "kind": kind,
        "model_version_id": model_id,
        "source_kind": source,
        "customer_result": "完整可用的交付",
        "problem": "现场与模型差异待解释",
        "findings": "抽样确认活动及例外",
        "evidence": "现场样本与访谈编号",
        "limitations": "样本范围有限",
        "next_action": "交给后续作业核验",
        "reviewer_user_id": reviewer["id"],
        "upstream_sheet_id": upstream,
        "alternatives": "不改/小改",
        "choice_reason": "保留控制先小改",
        "controls": "双人核对红线",
        "validation": "正常/拒绝/异常桌面测试",
        "rollback": "回退原模型",
    }


def test_work_records_form_same_process_chain_without_project(client, owner_client, work_process):
    pid, model, current = work_process
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "作业依据"},
    ).json()
    path = f"{API}/processes/{pid}/work-records"
    upstream = None
    for kind in ["MODELING", "ANALYSIS", "DESIGN"]:
        response = client.post(path, json=work_payload(client, frozen["id"], kind, upstream))
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved["project_id"] is None
        assert saved["work_context"]["model_version_id"] == frozen["id"]
        review = {
            "decision": "ACCEPT",
            "evidence": "本人核对该版原产物及未决项",
            "expected_revision": saved["revision"],
        }
        assert client.post(path + f"/{saved['id']}/review", json=review).status_code == 403
        reviewed = owner_client.post(path + f"/{saved['id']}/review", json=review)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review"]["decision"] == "ACCEPT"
        assert owner_client.post(path + f"/{saved['id']}/review", json=review).status_code == 409
        upstream = saved["id"]
    board = client.get(f"{API}/processes/{pid}/workbench")
    assert board.status_code == 200, board.text
    assert {row["work_context"]["kind"] for row in board.json()["records"]} == {
        "MODELING",
        "ANALYSIS",
        "DESIGN",
    }
    assert board.json()["limitations"]
    assert client.get(f"{API}/processes/{pid}/design").json()["published_version"] == 0


def test_work_rejects_unfixed_model_and_exercise_acceptance(client, owner_client, work_process):
    pid, model, current = work_process
    path = f"{API}/processes/{pid}/work-records"
    response = client.post(path, json=work_payload(client, current["version_id"]))
    assert response.status_code == 400, response.text
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "演练依据"},
    ).json()
    saved = client.post(path, json=work_payload(client, frozen["id"], source="EXERCISE"))
    assert saved.status_code == 201, saved.text
    ident = saved.json()["id"]
    rejected = owner_client.post(
        path + f"/{ident}/review",
        json={"decision": "ACCEPT", "evidence": "不能当真实现状", "expected_revision": 0},
    )
    assert rejected.status_code == 400, rejected.text
    assert (
        owner_client.post(
            path + f"/{ident}/review",
            json={"decision": "RETURN", "evidence": "请补真实现场样本", "expected_revision": 0},
        ).status_code
        == 200
    )


def test_upstream_return_invalidates_downstream_receipt(client, owner_client, work_process):
    pid, model, current = work_process
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "固定输入"},
    ).json()
    path = f"{API}/processes/{pid}/work-records"
    first = client.post(path, json=work_payload(client, frozen["id"])).json()
    assert "id" in first
    assert (
        owner_client.post(
            path + f"/{first['id']}/review",
            json={"decision": "ACCEPT", "evidence": "原输入足够", "expected_revision": 0},
        ).status_code
        == 200
    )
    second = client.post(
        path, json=work_payload(client, frozen["id"], "ANALYSIS", first["id"])
    ).json()
    assert (
        owner_client.post(
            path + f"/{second['id']}/review",
            json={"decision": "ACCEPT", "evidence": "分析可交付", "expected_revision": 0},
        ).status_code
        == 200
    )
    assert (
        owner_client.post(
            path + f"/{first['id']}/review",
            json={"decision": "RETURN", "evidence": "发现现场反证", "expected_revision": 1},
        ).status_code
        == 200
    )
    records = client.get(f"{API}/processes/{pid}/workbench").json()["records"]
    affected = next(row for row in records if row["id"] == second["id"])
    assert affected["review_label"] == "上游需复核"


def test_freeze_conflicts_with_save_that_already_read_draft(client, work_process, monkeypatch):
    from app.core.timeutil import utcnow
    from app.models.process import ProcessModelVersion
    from app.services import process_model

    pid, model, current = work_process
    original = process_model.snapshot_from_payload
    fired = []

    def racing(payload):
        snapshot = original(payload)
        if not fired:
            fired.append(True)
            # 在正文写入边界模拟另一请求已经冻结，保持ORM缓存仍为旧值。
            from sqlalchemy import update

            # 下方Session由服务侧测试入口捕获，模拟已提交结果而非线程压力验收。
            active[0].execute(
                update(ProcessModelVersion)
                .where(ProcessModelVersion.id == current["version_id"])
                .values(frozen_at=utcnow()),
                execution_options={"synchronize_session": False},
            )
        return snapshot

    active = []
    save_original = process_model.save_draft

    def save_with_session(db, *args, **kwargs):
        active.append(db)
        return save_original(db, *args, **kwargs)

    monkeypatch.setattr(process_model, "save_draft", save_with_session)
    monkeypatch.setattr(process_model, "snapshot_from_payload", racing)
    model["nodes"][1]["name"] = "并发覆盖"
    response = client.put(f"{API}/processes/{pid}/design", json=model)
    assert response.status_code == 409, response.text
    assert (
        client.get(f"{API}/processes/{pid}/design/versions/{current['version_id']}").json()[
            "nodes"
        ][1]["name"]
        == "核对"
    )


def test_upstream_reaccept_does_not_reactivate_old_downstream(client, owner_client, work_process):
    pid, model, current = work_process
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "输入"},
    ).json()
    path = f"{API}/processes/{pid}/work-records"
    first = client.post(path, json=work_payload(client, frozen["id"])).json()
    second = client.post(
        path, json=work_payload(client, frozen["id"], "ANALYSIS", first["id"])
    ).json()

    def decide(sid, revision, decision):
        return owner_client.post(
            path + f"/{sid}/review",
            json={
                "decision": decision,
                "evidence": "原依据发生变化",
                "expected_revision": revision,
            },
        )

    assert decide(first["id"], 0, "ACCEPT").status_code == 200
    assert decide(second["id"], 0, "ACCEPT").status_code == 200
    assert decide(first["id"], 1, "RETURN").status_code == 200
    assert decide(first["id"], 2, "ACCEPT").status_code == 200
    records = client.get(f"{API}/processes/{pid}/workbench").json()["records"]
    assert next(r for r in records if r["id"] == second["id"])["review_label"] == "上游需复核"
    assert decide(second["id"], 1, "ACCEPT").status_code == 200


def test_archived_method_cannot_create_work(client, work_process):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.tool import Tool

    pid, model, current = work_process
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "输入"},
    ).json()
    with SessionLocal() as db:
        tool = db.scalar(select(Tool).where(Tool.code == "BPMN"))
        old = tool.status
        tool.status = "ARCHIVED"
        db.commit()
    try:
        assert (
            client.post(
                f"{API}/processes/{pid}/work-records", json=work_payload(client, frozen["id"])
            ).status_code
            == 404
        )
    finally:
        with SessionLocal() as db:
            db.scalar(select(Tool).where(Tool.code == "BPMN")).status = old
            db.commit()


def test_draft_architecture_can_read_workbench_without_new_work_permission(client, work_process):
    from app.core.database import SessionLocal
    from app.models.process import ProcessArch

    pid, model, current = work_process
    with SessionLocal() as db:
        db.get(ProcessArch, pid).is_draft = True
        db.commit()
    assert client.get(f"{API}/processes/{pid}/design").status_code == 200
    response = client.get(f"{API}/processes/{pid}/workbench")
    assert response.status_code == 200, response.text
    assert response.json()["can_create"] is False


def test_work_references_hidden_upstream_stay_hidden_in_original_detail(
    client, viewer_client, work_process
):
    from app.core.database import SessionLocal
    from app.models.project import Project

    pid, model, current = work_process
    frozen = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": current["version"], "note": "私有输入"},
    ).json()
    project = client.post(
        API + "/projects",
        json={"name": "私有作业", "methodology": "BPI", "owner": "流程管理科", "process_id": pid},
    ).json()["id"]
    try:
        with SessionLocal() as db:
            db.get(Project, project).org_unit_id = 1
            db.commit()
        body = work_payload(client, frozen["id"])
        body["project_id"] = project
        first = client.post(f"{API}/processes/{pid}/work-records", json=body).json()
        second = client.post(
            f"{API}/processes/{pid}/work-records",
            json=work_payload(client, frozen["id"], "ANALYSIS", first["id"]),
        ).json()
        assert viewer_client.get(f"{API}/tools/FIVE-WHY/sheets/{second['id']}").status_code == 404
        card = viewer_client.get(f"{API}/process-card/{pid}").json()
        assert not any(row["id"] == second["id"] for row in card["sheets"])
    finally:
        client.delete(f"{API}/projects/{project}")
