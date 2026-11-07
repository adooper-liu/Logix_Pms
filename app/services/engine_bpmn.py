"""Strict non-executable-metadata BPMN subset for the first sandbox slice."""

import hashlib
import re
import xml.etree.ElementTree as ET

from fastapi import HTTPException

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
PMS = "http://logix-pms.local/bpmn"
METADATA = {
    PMS: {
        "nodeType",
        "ownerRole",
        "durationMinutes",
        "waitMinutes",
        "cost",
        "reworkRate",
        "approvalLevels",
        "valueAdded",
    },
    "http://www.omg.org/spec/BPMN/20100524/DI": {
        "BPMNDiagram",
        "BPMNPlane",
        "BPMNShape",
        "BPMNEdge",
        "BPMNLabel",
    },
    "http://www.omg.org/spec/DD/20100524/DC": {"Bounds"},
    "http://www.omg.org/spec/DD/20100524/DI": {"waypoint"},
}
ATTRS = {
    "definitions": {"id", "targetNamespace", "name"},
    "process": {"id", "name", "isExecutable"},
    "startEvent": {"id", "name"},
    "endEvent": {"id", "name"},
    "userTask": {"id", "name"},
    "parallelGateway": {"id", "name", "gatewayDirection"},
    "sequenceFlow": {"id", "name", "sourceRef", "targetRef"},
    "incoming": set(),
    "outgoing": set(),
    "documentation": set(),
    "extensionElements": set(),
    "laneSet": {"id", "name"},
    "lane": {"id", "name"},
    "flowNodeRef": set(),
}
KINDS = {
    "startEvent": "START",
    "endEvent": "END",
    "userTask": "APPROVAL",
    "parallelGateway": "PARALLEL",
}


def reject(detail):
    raise HTTPException(400, "Flowable沙箱模型不支持：" + detail)


def inspect_xml(xml: str) -> dict:
    raw = xml.encode("utf-8")
    if len(raw) > 2 * 1024 * 1024 or "<!" in xml or "${" in xml or "#{" in xml:
        reject("XML大小、实体或表达式")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        reject("XML格式")
    if root.tag != f"{{{BPMN}}}definitions":
        reject("definitions命名空间")
    for element in root.iter():
        namespace, _, tag = (
            element.tag[1:].partition("}") if element.tag.startswith("{") else ("", "", element.tag)
        )
        if namespace == BPMN:
            if tag not in ATTRS:
                reject(tag)
            allowed = ATTRS[tag]
        elif namespace in METADATA and tag in METADATA[namespace]:
            allowed = (
                {
                    "id",
                    "bpmnElement",
                    "x",
                    "y",
                    "width",
                    "height",
                    "isHorizontal",
                    "isExpanded",
                    "isMarkerVisible",
                }
                if namespace != PMS
                else set()
            )
        else:
            reject("未知元素 " + tag)
        for key, value in element.attrib.items():
            if key not in allowed:
                reject("未知属性 " + key)
            if (
                re.search(r"(?:\$|#)\{|(?:https?|file|jar):", value, re.I)
                and key != "targetNamespace"
            ):
                reject("可执行属性")
    processes = root.findall(f"{{{BPMN}}}process")
    if len(processes) != 1 or processes[0].get("isExecutable") != "true":
        reject("单一可执行process")
    process = processes[0]
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if (
            element.tag.startswith(f"{{{BPMN}}}")
            and tag in {*KINDS, "sequenceFlow"}
            and parents.get(element) is not process
        ):
            reject("执行节点必须是process直接子元素")
        if tag == "process" and parents.get(element) is not root:
            reject("嵌套process")
    ids = [el.get("id") for el in root.iter() if el.get("id")]
    if len(ids) != len(set(ids)) or any(
        not re.fullmatch(r"[A-Za-z_][\w.-]{0,127}", i) for i in ids
    ):
        reject("元素ID重复或非法")
    nodes = {el.get("id"): el for el in process if el.tag.rsplit("}", 1)[-1] in KINDS}
    if not nodes or len(nodes) > 500 or None in nodes:
        reject("节点数量/身份")
    ins, outs = {key: [] for key in nodes}, {key: [] for key in nodes}
    edges = []
    for flow in process.findall(f"{{{BPMN}}}sequenceFlow"):
        source, target = flow.get("sourceRef"), flow.get("targetRef")
        if source not in nodes or target not in nodes or not flow.get("id"):
            reject("连线身份/目标")
        outs[source].append(target)
        ins[target].append(source)
        edges.append({"source_key": source, "target_key": target, "label": flow.get("name")})
    starts = [key for key, el in nodes.items() if el.tag.endswith("}startEvent")]
    ends = [key for key, el in nodes.items() if el.tag.endswith("}endEvent")]
    if len(starts) != 1 or len(ends) != 1:
        reject("单一起止")
    for key, el in nodes.items():
        tag = el.tag.rsplit("}", 1)[-1]
        size = (len(ins[key]), len(outs[key]))
        valid = (
            size == (0, 1)
            if tag == "startEvent"
            else size == (1, 0)
            if tag == "endEvent"
            else size == (1, 1)
            if tag == "userTask"
            else (size[0] == 1 and size[1] >= 2) or (size[0] >= 2 and size[1] == 1)
        )
        if not valid:
            reject("节点入出边 " + key)
    # Topological order catches cycles/orphans. Token stack enforces properly nested fork/join.
    pending = dict((key, len(value)) for key, value in ins.items())
    queue, order = starts.copy(), []
    while queue:
        key = queue.pop(0)
        order.append(key)
        for target in outs[key]:
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if len(order) != len(nodes):
        reject("回路或不可达节点")
    stacks = {starts[0]: ()}
    branch_stacks = {}
    for key in order:
        if len(ins[key]) > 1:
            incoming = [branch_stacks[(source, key)] for source in ins[key]]
            if any(not s for s in incoming):
                reject("未配对汇聚")
            fork = incoming[0][-1][0]
            prefixes = [s[:-1] for s in incoming]
            branches = {s[-1][1] for s in incoming}
            if (
                any(s[-1][0] != fork for s in incoming)
                or any(s != prefixes[0] for s in prefixes)
                or branches != set(outs[fork])
            ):
                reject("非结构化并行汇聚")
            stacks[key] = prefixes[0]
        elif ins[key]:
            stacks[key] = branch_stacks[(ins[key][0], key)]
        for target in outs[key]:
            branch_stacks[(key, target)] = stacks[key] + (
                ((key, target),) if len(outs[key]) > 1 else ()
            )
    if stacks[ends[0]]:
        reject("未闭合并行")
    return {
        "process_key": process.get("id"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "contract_version": 1,
        "tasks": [key for key, el in nodes.items() if el.tag.endswith("}userTask")],
        "nodes": [
            {
                "node_key": key,
                "name": el.get("name") or key,
                "node_type": KINDS[el.tag.rsplit("}", 1)[-1]],
                "sequence_order": i,
            }
            for i, (key, el) in enumerate(nodes.items(), 1)
        ],
        "edges": edges,
    }
