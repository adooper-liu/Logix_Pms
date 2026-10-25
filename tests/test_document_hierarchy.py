"""制度层级与适用范围：标准文件的层级/法人/工厂/产品族/语言字段。"""

from __future__ import annotations

API = "/api/v1"


def test_document_level_and_scope_fields(client):
    processes = client.get(f"{API}/process-map/flat").json()
    process_id = next(row["id"] for row in processes if row["code"] == "L3-032")

    meta = client.get(f"{API}/process-documents/meta").json()
    assert meta["level_labels"]["GROUP"] == "集团制度"
    assert meta["level_labels"]["PROCESS"] == "流程文件"

    created = client.post(
        f"{API}/process-documents",
        json={
            "process_id": process_id,
            "title": "层级测试制度",
            "category": "POLICY",
            "level": "COMPANY",
            "legal_entity": "华东制造有限公司",
            "plant": "苏州一厂",
            "product_family": "动力总成",
            "language": "zh-CN",
            "control_points": "金额 > 10 万需双人复核",
            "exception_terms": "试点期可临时单签，须在 30 天内复盘",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    document_id = body["id"]
    try:
        assert body["level"] == "COMPANY"
        assert body["level_label"] == "公司制度"
        assert body["legal_entity"] == "华东制造有限公司"
        assert body["plant"] == "苏州一厂"
        assert body["product_family"] == "动力总成"
        assert body["control_points"]
        assert body["exception_terms"]

        filtered = client.get(f"{API}/process-documents", params={"level": "COMPANY"}).json()
        assert any(row["id"] == document_id for row in filtered)

        updated = client.patch(
            f"{API}/process-documents/{document_id}",
            json={"level": "GROUP", "plant": None},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["level_label"] == "集团制度"
        assert updated.json()["plant"] is None
    finally:
        assert client.delete(f"{API}/process-documents/{document_id}").status_code == 200
