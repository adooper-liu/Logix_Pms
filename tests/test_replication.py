"""复制资产包：条件、收益证据、发布与拒绝约束。"""

from __future__ import annotations

API = "/api/v1"


def _project(client) -> dict:
    created = client.post(
        f"{API}/projects",
        json={"name": "复制资产包测试项目", "methodology": "BPI", "owner": "流程管理科"},
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_replication_pack_lifecycle(client):
    project = _project(client)
    knowledge = client.get(f"{API}/knowledge", params={"page_size": 1}).json()["items"]
    assert knowledge

    created = client.post(
        f"{API}/replication-packs",
        json={
            "source_project_id": project["id"],
            "title": "采购需求归并复制包",
            "conditions": "多工厂、采购需求分散提报",
            "benefit_evidence": "周期从 14 天降到 9 天",
            "failure_notes": "小批量工厂不适合强制归并",
            "knowledge_ids": [knowledge[0]["id"]],
        },
    )
    assert created.status_code == 201, created.text
    pack = created.json()
    assert pack["status"] == "DRAFT"
    assert pack["status_label"] == "草稿"
    assert pack["knowledge"][0]["id"] == knowledge[0]["id"]

    rows = client.get(
        f"{API}/replication-packs", params={"source_project_id": project["id"]}
    ).json()
    assert any(row["id"] == pack["id"] for row in rows)

    published = client.patch(f"{API}/replication-packs/{pack['id']}", json={"status": "PUBLISHED"})
    assert published.status_code == 200, published.text
    assert published.json()["status_label"] == "已发布"

    rejected = client.patch(f"{API}/replication-packs/{pack['id']}", json={"status": "REJECTED"})
    assert rejected.status_code == 400
    assert "拒绝理由" in rejected.json()["detail"]

    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200
