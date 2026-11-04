"""M5薄轮次身份、冻结口径/原样本快照及可追溯修订。"""

from datetime import date, timedelta
from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def round_sources(client):
    me = client.get(API + "/auth/me").json()
    process = client.post(
        API + "/process-map",
        json={
            "code": "RND-" + uuid4().hex[:8],
            "name": "轮次测试",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()
    pid = process["id"]
    model = client.put(
        f"{API}/processes/{pid}/design",
        json={"nodes": [{"node_key": "a", "name": "活动", "node_type": "TASK"}], "edges": []},
    ).json()
    fixed = client.post(
        f"{API}/processes/{pid}/design/freeze",
        json={"expected_version": model["version"], "note": "轮次现状"},
    ).json()
    kpi = client.post(
        API + "/monitor/kpis",
        json={
            "code": "K-RND-" + uuid4().hex[:8],
            "name": "明确时长口径",
            "dimension": "EFFICIENCY",
            "process_id": pid,
            "unit": "小时",
            "formula": "合格样本历时均值",
            "granularity": "每笔业务",
            "source_system": "现场核对",
        },
    ).json()
    record = client.post(
        f"{API}/monitor/kpis/{kpi['id']}/records",
        json={"period": "2026-10-01", "value": 14, "note": "原样本清单A"},
    ).json()
    yield {"process": pid, "model": fixed["id"], "kpi": kpi["id"], "record": record["id"]}
    # 测试专用按精确本轮ID清理，生产无删除接口；避免污染原全量用例统计。
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.improvement_round import ProcessImprovementRound
    from app.models.monitor import KpiDefinition, KpiRecord
    from app.models.process import ProcessArch
    from app.models.project import Project

    with SessionLocal() as db:
        rows = db.scalars(
            select(ProcessImprovementRound)
            .where(ProcessImprovementRound.process_id == pid)
            .order_by(ProcessImprovementRound.id.desc())
        ).all()
        projects = {row.project_id for row in rows if row.project_id}
        for row in rows:
            db.delete(row)
            # 自引用RESTRICT必须逐条从新修订向旧修订提交，不能让ORM按主键重排批量DELETE。
            db.flush()
        db.flush()
        for row in db.scalars(select(KpiRecord).where(KpiRecord.kpi_id == kpi["id"])).all():
            db.delete(row)
        db.delete(db.get(KpiDefinition, kpi["id"]))
        for ident in projects:
            obj = db.get(Project, ident)
            if obj:
                db.delete(obj)
        db.delete(db.get(ProcessArch, pid))
        db.commit()


def draft_payload(s):
    return {
        "name": "采购改善本轮",
        "scope_note": "单一流程明确业务群组",
        "asis_model_version_id": s["model"],
        "baseline_window": {"start": "2026-10-01", "end": "2026-10-31"},
        "metrics": [
            {
                "kpi_id": s["kpi"],
                "source_semantics": "合格业务端到端历时",
                "source_evidence": "现场样本清单A",
                "timezone": "UTC",
                "calendar": "自然日",
                "filters": "同一产品群组",
                "exclusions": "取消单",
            }
        ],
        "baseline_samples": [
            {
                "record_id": s["record"],
                "source_evidence": "现场原样本A",
                "quality_note": "已核完整性",
            }
        ],
    }


def test_round_baseline_snapshots_and_revision(client, round_sources):
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    created = client.post(path, json=draft_payload(s))
    assert created.status_code == 201, created.text
    row = created.json()
    rid = row["id"]
    assert "current_stage" not in row and "status" not in row
    frozen = client.post(path + f"/{rid}/lock-baseline", json={"expected_revision": 0})
    assert frozen.status_code == 200, frozen.text
    out = frozen.json()
    assert out["baseline_confirmed_at"].endswith("+00:00")
    contract = out["metric_contracts"][0]
    assert contract["formula"] == "合格样本历时均值" and len(contract["hash"]) == 64
    assert out["baseline_samples"][0]["value"] == 14
    assert (
        client.patch(
            path + f"/{rid}", json={**draft_payload(s), "expected_revision": out["revision"]}
        ).status_code
        == 409
    )
    client.patch(f"{API}/monitor/kpis/{s['kpi']}", json={"formula": "新版公式"})
    client.post(
        f"{API}/monitor/kpis/{s['kpi']}/records",
        json={"period": "2026-10-01", "value": 999, "note": "后来修正"},
    )
    stable = client.get(path + f"/{rid}").json()
    assert stable["metric_contracts"][0]["formula"] == contract["formula"]
    assert stable["baseline_samples"][0]["value"] == 14
    assert all(x["state"] == "PENDING" for x in stable["verification"])
    revised = client.post(path + f"/{rid}/revise", json={"expected_revision": out["revision"]})
    assert revised.status_code == 201, revised.text
    assert revised.json()["supersedes_id"] == rid
    assert revised.json()["baseline_confirmed_at"] is None
    assert client.get(path + f"/{rid}").json()["baseline_samples"][0]["value"] == 14


def test_round_identity_idempotency_and_delete_retention(client, viewer_client, round_sources):
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    key = {"Idempotency-Key": "round-" + uuid4().hex}
    body = draft_payload(s)
    assert viewer_client.post(path, json=body).status_code == 403
    first = client.post(path, json=body, headers=key)
    assert first.status_code == 201, first.text
    second = client.post(path, json=body, headers=key)
    assert second.json()["id"] == first.json()["id"]
    assert client.post(path, json={**body, "name": "不同请求"}, headers=key).status_code == 409
    assert client.delete(f"{API}/process-map/{s['process']}").status_code == 409
    rid = first.json()["id"]
    assert client.get(f"{API}/processes/999999/improvement-rounds/{rid}").status_code == 404


def test_lock_rejects_changed_original_basis(client, round_sources):
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    row = client.post(path, json=draft_payload(s)).json()
    client.post(
        f"{API}/monitor/kpis/{s['kpi']}/records",
        json={"period": "2026-10-01", "value": 999, "note": "确认前已变"},
    )
    response = client.post(path + f"/{row['id']}/lock-baseline", json={"expected_revision": 0})
    assert response.status_code == 409, response.text


def test_project_baseline_can_create_and_revise(client, round_sources):
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    project = client.post(
        API + "/projects",
        json={
            "name": "前置项目样本",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": s["process"],
        },
    ).json()["id"]
    try:
        record = client.post(
            f"{API}/monitor/kpis/{s['kpi']}/records",
            json={"period": "2026-10-01", "value": 13, "project_id": project, "note": "项目原样本"},
        ).json()
        body = draft_payload(s)
        body["project_id"] = project
        body["baseline_samples"][0]["record_id"] = record["id"]
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        row = response.json()
        frozen = client.post(
            path + f"/{row['id']}/lock-baseline", json={"expected_revision": 0}
        ).json()
        revised = client.post(
            path + f"/{row['id']}/revise", json={"expected_revision": frozen["revision"]}
        )
        assert revised.status_code == 201, revised.text
        assert revised.json()["project_id"] == project
    finally:
        # 已被引用时留fixture精确清理；未创建成功才清理本临时项目。
        client.delete(f"{API}/projects/{project}")


def test_draft_process_round_list_remains_readable(client, round_sources):
    from app.core.database import SessionLocal
    from app.models.process import ProcessArch

    s = round_sources
    with SessionLocal() as db:
        db.get(ProcessArch, s["process"]).is_draft = True
        db.commit()
    assert client.get(f"{API}/processes/{s['process']}/improvement-rounds").status_code == 200
    assert (
        client.post(
            f"{API}/processes/{s['process']}/improvement-rounds", json=draft_payload(s)
        ).status_code
        == 400
    )


def test_round_scope_length_is_bounded(client, round_sources, monkeypatch):
    from app.services import improvement_round as service

    original = service.idempotency.begin

    def checked(db, scope, key, digest):
        assert len(scope) <= 32, scope
        return original(db, scope, key, digest)

    monkeypatch.setattr(service.idempotency, "begin", checked)
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    row = client.post(path, json=draft_payload(s)).json()
    client.post(path + f"/{row['id']}/lock-baseline", json={"expected_revision": 0})
    # 大ID以直接scope函数/实际请求同一算法验证，不需制造百万行。
    if hasattr(service, "command_scope"):
        assert len(service.command_scope(123456, 123456, 123456, "lock-acceptance")) <= 32
    else:
        assert len("round.123456.123456.123456.lock-acceptance") <= 32


def test_revise_uses_database_revision_arbitration(client, round_sources, monkeypatch):
    from sqlalchemy import update

    from app.models.improvement_round import ProcessImprovementRound
    from app.services import improvement_round as service

    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    row = client.post(path, json=draft_payload(s)).json()
    original = service.cas
    fired = []

    def racing(db, obj, expected, values):
        if not fired:
            fired.append(True)
            db.execute(
                update(ProcessImprovementRound)
                .where(ProcessImprovementRound.id == obj.id)
                .values(revision=obj.revision + 1),
                execution_options={"synchronize_session": False},
            )
        return original(db, obj, expected, values)

    monkeypatch.setattr(service, "cas", racing)
    assert (
        client.post(path + f"/{row['id']}/revise", json={"expected_revision": 0}).status_code == 409
    )
    assert len(client.get(path).json()) == 1


def test_late_published_model_cannot_relabel_observation_window(client, round_sources):
    from datetime import datetime

    from app.core.database import SessionLocal
    from app.models.improvement_round import ProcessImprovementRound
    from app.models.process import ProcessModelVersion

    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    row = client.post(path, json=draft_payload(s)).json()
    locked = client.post(path + f"/{row['id']}/lock-baseline", json={"expected_revision": 0}).json()
    # 已存在的观察约定与实际发布事实来自原记录，不能用人工声明消除时间矛盾。
    with SessionLocal() as db:
        stored = db.get(ProcessImprovementRound, row["id"])
        stored.after_window = {"start": "2026-11-01", "end": "2026-11-02"}
        version = db.get(ProcessModelVersion, s["model"])
        version.status = "PUBLISHED"
        version.published_at = datetime(2026, 11, 3)
        db.commit()
    assert (
        client.post(
            path + f"/{row['id']}/bind-published",
            json={"expected_revision": locked["revision"], "reference_id": s["model"]},
        ).status_code
        == 400
    )


def test_reference_locks_exist_before_retention_scan(client, round_sources, monkeypatch):
    from app.services import improvement_round as service

    s = round_sources
    seen = []
    original = service.lock_reference

    def capture(db, kind, ident):
        seen.append((kind, ident))
        return original(db, kind, ident)

    monkeypatch.setattr(service, "lock_reference", capture)
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    assert client.post(path, json=draft_payload(s)).status_code == 201
    assert ("process", s["process"]) in seen
    seen.clear()
    assert client.delete(f"{API}/process-map/{s['process']}").status_code == 409
    assert ("process", s["process"]) in seen


def test_append_binding_and_after_samples_preserve_contract(client, round_sources, monkeypatch):
    from app.services import improvement_round as service

    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    row = client.post(path, json=draft_payload(s)).json()
    rid = row["id"]
    base = path + f"/{rid}"
    row = client.post(base + "/lock-baseline", json={"expected_revision": 0}).json()
    project = client.post(
        API + "/projects",
        json={
            "name": "本轮项目",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": s["process"],
        },
    ).json()["id"]
    row = client.post(
        base + "/bind-project", json={"expected_revision": row["revision"], "reference_id": project}
    ).json()
    assert row["project_id"] == project
    assert client.delete(f"{API}/projects/{project}").status_code == 409
    assert (
        client.post(
            base + "/bind-published",
            json={"expected_revision": row["revision"], "reference_id": s["model"]},
        ).status_code
        == 400
    )
    client.post(
        f"{API}/processes/{s['process']}/design/submit-review", json={"note": "本轮发布评审"}
    )
    published = client.post(
        f"{API}/processes/{s['process']}/design/publish",
        json={"change_note": "本轮真实发布", "self_publish_reason": "隔离测试环境验证原发布身份"},
    )
    assert published.status_code == 200, published.text
    row = client.post(
        base + "/bind-published",
        json={"expected_revision": row["revision"], "reference_id": s["model"]},
    ).json()
    tomorrow = date.today() + timedelta(days=1)
    end = tomorrow + timedelta(days=1)
    reviewer = client.get(API + "/auth/me").json()["id"]
    accepted = client.post(
        base + "/lock-acceptance",
        json={
            "expected_revision": row["revision"],
            "target": "周期降低且不损质量",
            "red_lines": "重大风险不得增加",
            "observation_rule": "同群组完整窗口",
            "reviewer_user_id": reviewer,
            "after_window": {"start": tomorrow.isoformat(), "end": end.isoformat()},
        },
    )
    assert accepted.status_code == 200, accepted.text
    row = accepted.json()
    after = client.post(
        f"{API}/monitor/kpis/{s['kpi']}/records",
        json={
            "period": tomorrow.isoformat(),
            "value": 5,
            "project_id": project,
            "note": "后侧原样本",
        },
    ).json()
    body = {
        "expected_revision": row["revision"],
        "samples": [
            {
                "record_id": after["id"],
                "source_evidence": "后侧原清单",
                "quality_note": "完整",
                "contract_hash": row["metric_contracts"][0]["hash"],
            }
        ],
    }
    assert client.post(base + "/capture-after", json=body).status_code == 400

    class Later(date):
        @classmethod
        def today(cls):
            return end + timedelta(days=1)

    monkeypatch.setattr(service, "date", Later)
    wrong = {**body, "samples": [{**body["samples"][0], "contract_hash": "0" * 64}]}
    assert client.post(base + "/capture-after", json=wrong).status_code == 400
    captured = client.post(base + "/capture-after", json=body)
    assert captured.status_code == 200, captured.text
    assert captured.json()["after_samples"][0]["value"] == 5
    assert (
        client.post(
            base + "/revise", json={"expected_revision": captured.json()["revision"]}
        ).status_code
        == 409
    )


def test_round_bad_window_and_cross_process_refs(client, round_sources):
    s = round_sources
    path = f"{API}/processes/{s['process']}/improvement-rounds"
    body = draft_payload(s)
    body["baseline_samples"] *= 2
    assert client.post(path, json=body).status_code == 400
    body = draft_payload(s)
    body["baseline_window"]["end"] = "2026-09-01"
    assert client.post(path, json=body).status_code == 422
    body = draft_payload(s)
    body["metrics"][0]["source_semantics"] = "   "
    assert client.post(path, json=body).status_code == 400
