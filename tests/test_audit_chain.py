"""审计日志哈希链：正常链可验证，篡改中间记录会被发现。"""

from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.models.user import AuditLog
from app.services.audit import _digest

API = "/api/v1"


def test_audit_hash_chain_detects_tampering(client):
    code = "AUDIT" + uuid.uuid4().hex[:6].upper()
    created = client.post(
        f"{API}/knowledge/scenarios",
        json={"code": code, "name": "审计链测试场景"},
    )
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]
    try:
        verified = client.get(f"{API}/audit/verify")
        assert verified.status_code == 200, verified.text
        assert verified.json()["ok"] is True

        db = SessionLocal()
        try:
            row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
            assert row is not None and row.hash
            original_summary = row.summary
            row.summary = "被篡改的摘要"
            db.commit()
        finally:
            db.close()

        broken = client.get(f"{API}/audit/verify").json()
        assert broken["ok"] is False
        assert broken["broken_at"]

        db = SessionLocal()
        try:
            row = db.get(AuditLog, broken["broken_at"])
            row.summary = original_summary
            row.hash = _digest(row.prev_hash, row)
            db.commit()
        finally:
            db.close()
    finally:
        client.patch(f"{API}/knowledge/scenarios/{scenario_id}", json={"is_active": False})
