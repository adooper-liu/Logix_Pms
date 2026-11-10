"""NODE作用域责任覆盖不能被活动聚合抹平。"""

from uuid import uuid4

from app.core.database import SessionLocal
from app.models.org import Position

API = "/api/v1"


def test_two_nodes_same_activity_have_independent_accountability(client):
    suffix = uuid4().hex[:8]
    p = client.post(
        f"{API}/process-map", json={"code": "NTEAM-" + suffix, "name": "节点责任", "level": 3}
    ).json()
    a = client.post(
        f"{API}/process-map",
        json={"code": "NA-" + suffix, "name": "共用活动", "level": 4, "parent_id": p["id"]},
    ).json()
    with SessionLocal() as db:
        position = Position(code="NP-" + suffix, name="有效岗位")
        db.add(position)
        db.commit()
        posid = position.id
    roles = client.get(f"{API}/governance/roles?active_only=true").json()[:2]
    response = client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": key,
                    "name": key,
                    "node_type": "TASK",
                    "process_arch_id": a["id"],
                    "owner_position_id": posid,
                }
                for key in ["n1", "n2"]
            ],
            "edges": [{"source_key": "n1", "target_key": "n2"}],
        },
    )
    assert response.status_code == 200, response.text
    ids = []

    def teams():
        data = client.get(f"{API}/processes/{p['id']}/binding-readiness").json()
        return {
            n["node_key"]: next(f["status"] for f in n["facets"] if f["key"] == "TEAM")
            for n in data["nodes"]
        }

    try:
        first = client.post(
            f"{API}/governance/raci",
            json={
                "process_id": p["id"],
                "matter": "节点责任",
                "node_key": "n1",
                "role_id": roles[0]["id"],
                "raci": "A",
            },
        )
        assert first.status_code == 201, first.text
        ids.append(first.json()["id"])
        assert teams() == {"n1": "READY", "n2": "PARTIAL"}
        second = client.post(
            f"{API}/governance/raci",
            json={
                "process_id": p["id"],
                "matter": "节点责任",
                "node_key": "n2",
                "role_id": roles[1]["id"],
                "raci": "A",
            },
        )
        assert second.status_code == 201, second.text
        ids.append(second.json()["id"])
        assert teams() == {"n1": "READY", "n2": "READY"}
    finally:
        for rid in ids:
            client.delete(f"{API}/governance/raci/{rid}")
        client.delete(f"{API}/process-map/{p['id']}")
        with SessionLocal() as db:
            db.delete(db.get(Position, posid))
            db.commit()
