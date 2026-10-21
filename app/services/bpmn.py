"""BPMN 2.0 导入/导出（结构子集）。

导出：把设计器的节点/连线/泳道/坐标写成 BPMN 2.0 XML。
导入：解析常见 BPMN 元素，替换目标流程的设计模型。

刻意不支持的：subProcess / boundaryEvent / complexGateway / parallelGateway。
当前执行引擎是单令牌顺序执行，把并行网关导入成判断节点会制造错误的运行语义，
所以直接返回 400，而不是静默降级。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.models.enums import NodeType
from app.models.process import ProcessArch, ProcessEdge, ProcessNode

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
PMS_NS = "http://logix-pms.local/bpmn"

MAX_XML_BYTES = 2 * 1024 * 1024
MAX_NODES = 500

# 设计器节点类型 → BPMN 元素
NODE_TO_BPMN = {
    NodeType.START.value: "startEvent",
    NodeType.END.value: "endEvent",
    NodeType.TASK.value: "task",
    NodeType.APPROVAL.value: "userTask",
    NodeType.HANDOFF.value: "manualTask",
    NodeType.WAIT.value: "intermediateCatchEvent",
    NodeType.DECISION.value: "exclusiveGateway",
}

# BPMN 元素 → 设计器节点类型（pms:nodeType 优先）
BPMN_TO_NODE = {
    "startEvent": NodeType.START.value,
    "endEvent": NodeType.END.value,
    "task": NodeType.TASK.value,
    "userTask": NodeType.APPROVAL.value,
    "manualTask": NodeType.TASK.value,
    "serviceTask": NodeType.TASK.value,
    "scriptTask": NodeType.TASK.value,
    "businessRuleTask": NodeType.TASK.value,
    "sendTask": NodeType.TASK.value,
    "receiveTask": NodeType.TASK.value,
    "callActivity": NodeType.TASK.value,
    "exclusiveGateway": NodeType.DECISION.value,
    "inclusiveGateway": NodeType.DECISION.value,
    "intermediateCatchEvent": NodeType.WAIT.value,
}

UNSUPPORTED = {
    "subProcess": "子流程",
    "boundaryEvent": "边界事件",
    "complexGateway": "复杂网关",
    "parallelGateway": "并行网关",
    "transaction": "事务子流程",
    "eventBasedGateway": "事件网关",
}

_SAFE_ID = re.compile(r"^[A-Za-z_][\w.\-]*$")


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _elem_id(key: str) -> str:
    return key if _SAFE_ID.match(key) else "Node_" + re.sub(r"\W", "_", key)


def _add_extension(parent: ET.Element, node: ProcessNode) -> None:
    ext = ET.SubElement(parent, _q(BPMN_NS, "extensionElements"))
    ET.SubElement(ext, _q(PMS_NS, "nodeType")).text = node.node_type
    if node.owner_role:
        ET.SubElement(ext, _q(PMS_NS, "ownerRole")).text = node.owner_role


def export_bpmn(process: ProcessArch, nodes: List[ProcessNode], edges: List[ProcessEdge]) -> str:
    for prefix, uri in (
        ("bpmn", BPMN_NS),
        ("bpmndi", BPMNDI_NS),
        ("dc", DC_NS),
        ("di", DI_NS),
        ("xsi", XSI_NS),
        ("pms", PMS_NS),
    ):
        ET.register_namespace(prefix, uri)

    definitions = ET.Element(
        _q(BPMN_NS, "definitions"),
        {
            "id": "Definitions_1",
            "targetNamespace": PMS_NS,
            _q(XSI_NS, "schemaLocation"): f"{BPMN_NS} {BPMN_NS}/BPMN20.xsd",
        },
    )
    process_id = f"Process_{process.id}"
    process_el = ET.SubElement(
        definitions,
        _q(BPMN_NS, "process"),
        {"id": process_id, "name": process.name, "isExecutable": "true"},
    )

    ordered = sorted(nodes, key=lambda n: (n.sequence_order, n.id or 0))
    lanes: List[str] = []
    for node in ordered:
        lane = node.lane or "主流程"
        if lane not in lanes:
            lanes.append(lane)

    # 泳道
    lane_set = ET.SubElement(process_el, _q(BPMN_NS, "laneSet"), {"id": "LaneSet_1"})
    for index, lane in enumerate(lanes, start=1):
        lane_el = ET.SubElement(
            lane_set, _q(BPMN_NS, "lane"), {"id": f"Lane_{index}", "name": lane}
        )
        for node in ordered:
            if (node.lane or "主流程") == lane:
                ET.SubElement(lane_el, _q(BPMN_NS, "flowNodeRef")).text = _elem_id(node.node_key)

    # 节点
    for node in ordered:
        tag = NODE_TO_BPMN.get(node.node_type, "task")
        el = ET.SubElement(
            process_el, _q(BPMN_NS, tag), {"id": _elem_id(node.node_key), "name": node.name}
        )
        _add_extension(el, node)

    # 连线
    flow_ids: Dict[int, str] = {}
    for index, edge in enumerate(edges, start=1):
        flow_id = f"Flow_{index}"
        flow_ids[id(edge)] = flow_id
        attrs = {
            "id": flow_id,
            "sourceRef": _elem_id(edge.source_key),
            "targetRef": _elem_id(edge.target_key),
        }
        if edge.label:
            attrs["name"] = edge.label
        if edge.probability is not None and edge.probability != 1.0:
            attrs[_q(PMS_NS, "probability")] = str(edge.probability)
        flow = ET.SubElement(process_el, _q(BPMN_NS, "sequenceFlow"), attrs)
        if edge.condition:
            condition = ET.SubElement(
                flow,
                _q(BPMN_NS, "conditionExpression"),
                {_q(XSI_NS, "type"): "bpmn:tFormalExpression"},
            )
            condition.text = edge.condition

    # 图形信息（可选，但让导入到其他建模工具时不会全挤在原点）
    diagram = ET.SubElement(definitions, _q(BPMNDI_NS, "BPMNDiagram"), {"id": "Diagram_1"})
    plane = ET.SubElement(
        diagram, _q(BPMNDI_NS, "BPMNPlane"), {"id": "Plane_1", "bpmnElement": process_id}
    )
    positions: Dict[str, Tuple[float, float]] = {}
    for index, node in enumerate(ordered):
        lane_index = lanes.index(node.lane or "主流程")
        x = node.position_x if node.position_x else 180.0 * (index + 1)
        y = node.position_y if node.position_y else 120.0 * (lane_index + 1)
        positions[node.node_key] = (x, y)
        shape = ET.SubElement(
            plane,
            _q(BPMNDI_NS, "BPMNShape"),
            {"id": f"Shape_{_elem_id(node.node_key)}", "bpmnElement": _elem_id(node.node_key)},
        )
        ET.SubElement(
            shape,
            _q(DC_NS, "Bounds"),
            {"x": str(x), "y": str(y), "width": "180", "height": "80"},
        )
    for index, edge in enumerate(edges, start=1):
        source = positions.get(edge.source_key)
        target = positions.get(edge.target_key)
        if source is None or target is None:
            continue
        shape = ET.SubElement(
            plane,
            _q(BPMNDI_NS, "BPMNEdge"),
            {"id": f"Edge_{index}", "bpmnElement": flow_ids[id(edge)]},
        )
        ET.SubElement(
            shape,
            _q(DI_NS, "waypoint"),
            {"x": str(source[0] + 90), "y": str(source[1] + 40)},
        )
        ET.SubElement(
            shape,
            _q(DI_NS, "waypoint"),
            {"x": str(target[0] + 90), "y": str(target[1] + 40)},
        )

    ET.indent(definitions, space="  ")
    xml = ET.tostring(definitions, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml


def _parse_bpmn(xml_text: str) -> ET.Element:
    if len(xml_text.encode("utf-8")) > MAX_XML_BYTES:
        raise HTTPException(status_code=400, detail="BPMN 文件超过 2MB 限制")
    upper = xml_text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise HTTPException(status_code=400, detail="BPMN 文件包含 DOCTYPE/ENTITY，已拒绝解析")
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"BPMN XML 解析失败：{exc}") from exc


def _parse_extension(element: ET.Element) -> Tuple[Optional[str], Optional[str]]:
    node_type = None
    owner_role = None
    for ext in element:
        if _local(ext.tag) != "extensionElements":
            continue
        for child in ext:
            name = _local(child.tag)
            if name == "nodeType" and child.text:
                node_type = child.text.strip()
            elif name == "ownerRole" and child.text:
                owner_role = child.text.strip()
    return node_type, owner_role


def _parse_bounds(root: ET.Element) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    for shape in root.iter():
        if _local(shape.tag) != "BPMNShape":
            continue
        element_id = shape.get("bpmnElement") or shape.get(_q(BPMN_NS, "bpmnElement"))
        if not element_id:
            continue
        for child in shape:
            if _local(child.tag) == "Bounds":
                try:
                    positions[element_id] = (float(child.get("x", 0)), float(child.get("y", 0)))
                except (TypeError, ValueError):
                    pass
    return positions


def import_bpmn(xml_text: str) -> Dict[str, List[Dict]]:
    root = _parse_bpmn(xml_text)
    process_el = next((el for el in root.iter() if _local(el.tag) == "process"), None)
    if process_el is None:
        raise HTTPException(status_code=400, detail="BPMN 中没有找到 process 元素")

    # 泳道映射
    lane_of: Dict[str, str] = {}
    for lane in process_el.iter():
        if _local(lane.tag) != "lane":
            continue
        lane_name = lane.get("name") or "主流程"
        for ref in lane:
            if _local(ref.tag) == "flowNodeRef" and ref.text:
                lane_of[ref.text.strip()] = lane_name

    positions = _parse_bounds(root)
    nodes: List[Dict] = []
    node_ids: set[str] = set()
    unsupported: List[str] = []

    for index, el in enumerate(process_el):
        tag = _local(el.tag)
        if tag in ("laneSet", "sequenceFlow"):
            continue
        if tag in UNSUPPORTED:
            unsupported.append(f"{UNSUPPORTED[tag]}({el.get('id', '?')})")
            continue
        if tag not in BPMN_TO_NODE:
            continue
        element_id = el.get("id")
        if not element_id:
            raise HTTPException(status_code=400, detail=f"BPMN 元素 {tag} 缺少 id")
        if len(element_id) > 64:
            raise HTTPException(status_code=400, detail=f"BPMN 元素 id 超过 64 字符：{element_id}")
        if element_id in node_ids:
            raise HTTPException(status_code=400, detail=f"BPMN 元素 id 重复：{element_id}")
        node_ids.add(element_id)
        override, owner_role = _parse_extension(el)
        node_type = override if override in {n.value for n in NodeType} else BPMN_TO_NODE[tag]
        x, y = positions.get(element_id, (180.0 * (index + 1), 120.0))
        nodes.append(
            {
                "node_key": element_id,
                "name": (el.get("name") or element_id)[:128],
                "node_type": node_type,
                "lane": lane_of.get(element_id, "主流程")[:64],
                "owner_role": owner_role,
                "duration_minutes": 0.0,
                "wait_minutes": 0.0,
                "cost": 0.0,
                "rework_rate": 0.0,
                "approval_levels": 1 if node_type == NodeType.APPROVAL.value else 0,
                "is_value_added": node_type
                in (NodeType.TASK.value, NodeType.START.value, NodeType.END.value),
                "sequence_order": len(nodes) + 1,
                "position_x": x,
                "position_y": y,
            }
        )

    if unsupported:
        raise HTTPException(
            status_code=400,
            detail="当前执行引擎不支持以下 BPMN 构造，请先在建模工具中移除或改为串行："
            + "、".join(unsupported),
        )
    if not nodes:
        raise HTTPException(status_code=400, detail="BPMN 中没有可导入的流程节点")
    if len(nodes) > MAX_NODES:
        raise HTTPException(status_code=400, detail=f"节点数超过 {MAX_NODES} 个限制")

    edges: List[Dict] = []
    for el in process_el:
        if _local(el.tag) != "sequenceFlow":
            continue
        source = el.get("sourceRef")
        target = el.get("targetRef")
        if not source or not target:
            raise HTTPException(status_code=400, detail="sequenceFlow 缺少 sourceRef/targetRef")
        if source not in node_ids or target not in node_ids:
            raise HTTPException(
                status_code=400,
                detail=f"sequenceFlow 引用了不存在的节点：{source} → {target}",
            )
        condition = None
        for child in el:
            if _local(child.tag) == "conditionExpression" and child.text:
                condition = child.text.strip()
        probability = el.get(_q(PMS_NS, "probability"))
        try:
            probability_value = float(probability) if probability else 1.0
        except ValueError:
            probability_value = 1.0
        edges.append(
            {
                "source_key": source,
                "target_key": target,
                "label": (el.get("name") or None) and el.get("name")[:64],
                "condition": condition[:128] if condition else None,
                "probability": probability_value,
            }
        )

    return {"nodes": nodes, "edges": edges}
