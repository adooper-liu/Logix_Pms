"""BPMN 2.0 导入/导出：结构往返、版本冲突、权限与拒绝不支持的构造。"""

from __future__ import annotations

API = "/api/v1"

MINIMAL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="D1" targetNamespace="http://example.com/bpmn">
  <bpmn:process id="P1" name="最小流程">
    <bpmn:startEvent id="start" name="开始"/>
    <bpmn:task id="task1" name="处理"/>
    <bpmn:endEvent id="end" name="结束"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="task1"/>
    <bpmn:sequenceFlow id="f2" sourceRef="task1" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>
"""

PARALLEL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="D2" targetNamespace="http://example.com/bpmn">
  <bpmn:process id="P2">
    <bpmn:startEvent id="start"/>
    <bpmn:parallelGateway id="fork"/>
    <bpmn:endEvent id="end"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="fork"/>
    <bpmn:sequenceFlow id="f2" sourceRef="fork" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>
"""


def _process_pid(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(r["id"] for r in rows if r["code"] == code)


def _create_process(client, code: str = "L3-BPMN") -> int:
    r = client.post(
        f"{API}/process-map",
        json={"code": code, "name": "BPMN 导入测试", "level": 3},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_export_contains_structure(client):
    pid = _process_pid(client)
    r = client.get(f"{API}/processes/{pid}/bpmn")
    assert r.status_code == 200, r.text
    assert "application/xml" in r.headers["content-type"]
    assert "L3-032.bpmn" in r.headers["content-disposition"]
    xml = r.text
    assert "<bpmn:process" in xml
    assert 'id="n1"' in xml and 'id="n4"' in xml
    assert "sequenceFlow" in xml
    assert "laneSet" in xml
    assert "pms:nodeType" in xml


def test_export_empty_process_rejected(client):
    pid = _create_process(client, "L3-BPMN-EMPTY")
    try:
        r = client.get(f"{API}/processes/{pid}/bpmn")
        assert r.status_code == 400
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_import_round_trip(client):
    source = _process_pid(client)
    xml = client.get(f"{API}/processes/{source}/bpmn").text
    pid = _create_process(client, "L3-BPMN")
    try:
        imported = client.post(
            f"{API}/processes/{pid}/bpmn", json={"xml": xml, "expected_version": 0}
        )
        assert imported.status_code == 200, imported.text
        model = imported.json()
        assert model["version"] == 1
        assert len(model["nodes"]) == 6
        assert len(model["edges"]) == 6
        by_key = {n["node_key"]: n for n in model["nodes"]}
        assert by_key["n4"]["node_type"] == "APPROVAL"
        assert by_key["n4"]["lane"] == "部门负责人"
        assert by_key["n6"]["node_type"] == "TASK"

        # n4 → n6 的条件在往返后仍然保留
        edge = next(
            e for e in model["edges"] if e["source_key"] == "n4" and e["target_key"] == "n6"
        )
        assert edge["condition"]

        # 再次导出，关键结构仍在
        again = client.get(f"{API}/processes/{pid}/bpmn").text
        assert 'id="n4"' in again and "userTask" in again
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_import_minimal_external_bpmn(client):
    pid = _create_process(client, "L3-BPMN-MIN")
    try:
        r = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": MINIMAL_XML})
        assert r.status_code == 200, r.text
        model = r.json()
        assert [n["node_key"] for n in model["nodes"]] == ["start", "task1", "end"]
        assert [n["node_type"] for n in model["nodes"]] == ["START", "TASK", "END"]
        assert len(model["edges"]) == 2
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_import_rejects_parallel_gateway(client):
    pid = _create_process(client, "L3-BPMN-PAR")
    try:
        r = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": PARALLEL_XML})
        assert r.status_code == 400
        assert "并行网关" in r.json()["detail"]
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_import_rejects_malformed_and_unsafe_xml(client):
    pid = _create_process(client, "L3-BPMN-BAD")
    try:
        bad = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": "<not-xml"})
        assert bad.status_code == 400
        assert "解析失败" in bad.json()["detail"]

        unsafe = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": '<!DOCTYPE x [<!ENTITY e "x">]>' + MINIMAL_XML},
        )
        assert unsafe.status_code == 400
        assert "DOCTYPE" in unsafe.json()["detail"]
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_round_trip_preserves_pms_metrics(client):
    source = _create_process(client, "L3-BPMN-MET")
    target = None
    try:
        saved = client.put(
            f"{API}/processes/{source}/design",
            json={
                "nodes": [
                    {
                        "node_key": "a",
                        "name": "测算节点",
                        "node_type": "TASK",
                        "lane": "L",
                        "duration_minutes": 12.5,
                        "wait_minutes": 3,
                        "cost": 4.5,
                        "rework_rate": 0.2,
                        "approval_levels": 2,
                        "is_value_added": False,
                    }
                ],
                "edges": [],
            },
        )
        assert saved.status_code == 200, saved.text
        xml = client.get(f"{API}/processes/{source}/bpmn").text
        assert "pms:durationMinutes" in xml

        target = _create_process(client, "L3-BPMN-MET2")
        imported = client.post(
            f"{API}/processes/{target}/bpmn", json={"xml": xml, "expected_version": 0}
        )
        assert imported.status_code == 200, imported.text
        node = imported.json()["nodes"][0]
        assert node["duration_minutes"] == 12.5
        assert node["wait_minutes"] == 3
        assert node["cost"] == 4.5
        assert node["rework_rate"] == 0.2
        assert node["approval_levels"] == 2
        assert node["is_value_added"] is False
    finally:
        client.delete(f"{API}/process-map/{source}")
        if target is not None:
            client.delete(f"{API}/process-map/{target}")


def test_import_version_conflict(client):
    pid = _create_process(client, "L3-BPMN-VER")
    try:
        first = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": MINIMAL_XML, "expected_version": 0},
        )
        assert first.status_code == 200
        stale = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": MINIMAL_XML, "expected_version": 0},
        )
        assert stale.status_code == 409
        ok = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": MINIMAL_XML, "expected_version": 1},
        )
        assert ok.status_code == 200
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_viewer_can_export_but_not_import(viewer_client):
    pid = _process_pid(viewer_client)
    assert viewer_client.get(f"{API}/processes/{pid}/bpmn").status_code == 200
    r = viewer_client.post(f"{API}/processes/{pid}/bpmn", json={"xml": MINIMAL_XML})
    assert r.status_code == 403
