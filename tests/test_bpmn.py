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

LAYOUT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  id="D3" targetNamespace="http://example.com/bpmn">
  <bpmn:process id="P3">
    <bpmn:startEvent id="start" name="开始"/>
    <bpmn:task id="task1" name="处理"/>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="start" targetRef="task1"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram_1">
    <bpmndi:BPMNPlane id="Plane_1" bpmnElement="P3">
      <bpmndi:BPMNShape id="Shape_start" bpmnElement="start">
        <dc:Bounds x="111" y="222" width="36" height="36"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Shape_task1" bpmnElement="task1">
        <dc:Bounds x="333" y="444" width="180" height="80"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Edge_f1" bpmnElement="Flow_1">
        <di:waypoint x="147" y="240"/>
        <di:waypoint x="777" y="484"/>
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
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
        assert by_key["n4"]["owner_role"] == "部门负责人"
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


def test_bpmn_layout_and_waypoints_persist(client):
    """bpmn-js 调整过的坐标/折点必须原样保存，刷新后不能重新排版。"""
    pid = _create_process(client, "L3-BPMN-LAYOUT")
    try:
        imported = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": LAYOUT_XML})
        assert imported.status_code == 200, imported.text
        model = imported.json()
        by_key = {node["node_key"]: node for node in model["nodes"]}
        assert by_key["start"]["position_x"] == 111
        assert by_key["task1"]["position_y"] == 444

        exported = client.get(f"{API}/processes/{pid}/bpmn")
        assert exported.status_code == 200
        xml = exported.text
        assert 'x="111"' in xml and 'y="444"' in xml
        assert 'x="777"' in xml, "连线折点被重新生成了"
        assert "pms:durationMinutes" in xml
    finally:
        client.delete(f"{API}/process-map/{pid}")


DOC_DEFAULT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="D4" targetNamespace="http://example.com/bpmn">
  <bpmn:process id="P4">
    <bpmn:startEvent id="start" name="开始"/>
    <bpmn:exclusiveGateway id="gw" name="判断" default="f2"/>
    <bpmn:task id="ok" name="通过">
      <bpmn:documentation>正常路径的处理说明</bpmn:documentation>
    </bpmn:task>
    <bpmn:task id="fallback" name="兜底"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="gw">
      <bpmn:documentation>进入判断</bpmn:documentation>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="f2" sourceRef="gw" targetRef="fallback"/>
    <bpmn:sequenceFlow id="f3" sourceRef="gw" targetRef="ok"/>
  </bpmn:process>
</bpmn:definitions>
"""


def test_documentation_and_default_branch_round_trip(client):
    pid = _create_process(client, "L3-BPMN-DOC")
    try:
        imported = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": DOC_DEFAULT_XML})
        assert imported.status_code == 200, imported.text
        model = imported.json()
        node = next(n for n in model["nodes"] if n["node_key"] == "ok")
        assert node["description"] == "正常路径的处理说明"
        flow = next(e for e in model["edges"] if e["source_key"] == "start")
        assert flow["description"] == "进入判断"
        default_edge = next(
            e for e in model["edges"] if e["source_key"] == "gw" and e["target_key"] == "fallback"
        )
        assert default_edge["is_default"] is True

        exported = client.get(f"{API}/processes/{pid}/bpmn").text
        assert "正常路径的处理说明" in exported
        assert "进入判断" in exported
        assert "default=" in exported
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


def test_external_editor_can_drop_pms_extensions(client):
    """bpmn-js 等编辑器可能不认识 pms:*；同 id 节点应从当前草稿继承指标。"""
    pid = _create_process(client, "L3-BPMN-EXT")
    try:
        saved = client.put(
            f"{API}/processes/{pid}/design",
            json={
                "nodes": [
                    {
                        "node_key": "task1",
                        "name": "处理",
                        "node_type": "TASK",
                        "lane": "L",
                        "duration_minutes": 15,
                        "wait_minutes": 2,
                        "cost": 3,
                        "rework_rate": 0.1,
                        "approval_levels": 1,
                        "is_value_added": False,
                    }
                ],
                "edges": [],
            },
        )
        assert saved.status_code == 200, saved.text
        external = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="D1" targetNamespace="http://example.com/bpmn">
  <bpmn:process id="P1">
    <bpmn:task id="task1" name="处理（外部编辑器）"/>
  </bpmn:process>
</bpmn:definitions>
"""
        imported = client.post(f"{API}/processes/{pid}/bpmn", json={"xml": external})
        assert imported.status_code == 200, imported.text
        node = imported.json()["nodes"][0]
        assert node["name"] == "处理（外部编辑器）"
        assert node["duration_minutes"] == 15
        assert node["wait_minutes"] == 2
        assert node["cost"] == 3
        assert node["rework_rate"] == 0.1
        assert node["approval_levels"] == 1
        assert node["is_value_added"] is False
    finally:
        client.delete(f"{API}/process-map/{pid}")


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


def test_owner_role_patch_survives_stale_bpmn_save(client):
    """属性栏用 PATCH 改负责人后，画布里旧的 pms:ownerRole 不能把它覆盖回去。"""
    source = _process_pid(client)
    xml = client.get(f"{API}/processes/{source}/bpmn").text
    pid = _create_process(client, "L3-BPMN-OWNER")
    try:
        imported = client.post(
            f"{API}/processes/{pid}/bpmn", json={"xml": xml, "expected_version": 0}
        )
        assert imported.status_code == 200, imported.text
        stale_xml = client.get(f"{API}/processes/{pid}/bpmn").text

        patched = client.patch(
            f"{API}/processes/{pid}/design/nodes/n4",
            json={"owner_role": "新角色"},
        )
        assert patched.status_code == 200, patched.text
        assert (
            next(node for node in patched.json()["nodes"] if node["node_key"] == "n4")["owner_role"]
            == "新角色"
        )

        saved = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": stale_xml, "expected_version": patched.json()["version"]},
        )
        assert saved.status_code == 200, saved.text
        assert (
            next(node for node in saved.json()["nodes"] if node["node_key"] == "n4")["owner_role"]
            == "新角色"
        )
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_explicit_probability_one_survives_resave(client):
    """把连线概率显式改成 1.0 后，不能被「缺省值兜底」还原成旧概率。"""
    source = _process_pid(client)
    xml = client.get(f"{API}/processes/{source}/bpmn").text
    pid = _create_process(client, "L3-BPMN-PROB")
    try:
        imported = client.post(
            f"{API}/processes/{pid}/bpmn", json={"xml": xml, "expected_version": 0}
        )
        assert imported.status_code == 200, imported.text
        exported = client.get(f"{API}/processes/{pid}/bpmn").text
        assert 'pms:probability="0.7"' in exported
        edited = exported.replace('pms:probability="0.7"', 'pms:probability="1"', 1)
        saved = client.post(
            f"{API}/processes/{pid}/bpmn",
            json={"xml": edited, "expected_version": imported.json()["version"]},
        )
        assert saved.status_code == 200, saved.text
        edge = next(
            item
            for item in saved.json()["edges"]
            if item["source_key"] == "n4" and item["target_key"] == "n5"
        )
        assert edge["probability"] == 1.0
    finally:
        client.delete(f"{API}/process-map/{pid}")
