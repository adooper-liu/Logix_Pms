"""DMAIC 阶段跟踪与长期未更新扫描。"""

from __future__ import annotations

from datetime import timedelta

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models.project import Project

API = "/api/v1"


def _project(client) -> dict:
    created = client.post(
        f"{API}/projects",
        json={"name": "DMAIC 测试项目", "methodology": "BPI", "owner": "流程管理科"},
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_dmaic_stage_tracking_and_stale_scan(client):
    project = _project(client)
    try:
        updated = client.patch(
            f"{API}/projects/{project['id']}",
            json={"dmaic_stage": "ANALYZE", "dmaic_note": "正在做根因分析"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["dmaic_stage_label"] == "分析"
        assert updated.json()["dmaic_updated_at"]

        db = SessionLocal()
        try:
            row = db.get(Project, project["id"])
            row.dmaic_updated_at = utcnow() - timedelta(days=45)
            db.commit()
        finally:
            db.close()

        assert client.post(f"{API}/baselines/audit-scan").status_code == 200
        findings = client.get(
            f"{API}/baselines/findings", params={"status": "OPEN", "type": "DMAIC_STAGE_STALE"}
        ).json()
        assert any(row["entity_id"] == project["id"] for row in findings)
    finally:
        assert client.delete(f"{API}/projects/{project['id']}").status_code == 200
