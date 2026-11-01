/* designer 的纯 BPMN XML 工具：不碰 DOM 事件、不发请求。
 *
 * 这些函数是自动布局、泳道恢复与类型改写的核心，抽出来后可以独立测试，
 * 也避免 designer 主文件继续膨胀。
 */

const PMS_NS = 'http://logix-pms.local/bpmn';

export function setPmsNodeType(xml, nodeId, pmsType) {
  const doc = bpmnXmlDoc(xml);
  const processEl = doc.getElementsByTagNameNS(BPMN_NS, 'process')[0];
  if (!processEl) return xml;
  const target = Array.from(processEl.children)
    .find((el) => el.getAttribute('id') === nodeId);
  if (!target) return xml;
  let ext = directChildren(target, 'extensionElements')[0];
  if (!ext) {
    ext = doc.createElementNS(BPMN_NS, 'bpmn:extensionElements');
    target.insertBefore(ext, target.firstChild);
  }
  let typeEl = Array.from(ext.children)
    .find((el) => el.namespaceURI === PMS_NS && el.localName === 'nodeType');
  if (!typeEl) {
    typeEl = doc.createElementNS(PMS_NS, 'pms:nodeType');
    ext.appendChild(typeEl);
  }
  typeEl.textContent = pmsType;
  return new XMLSerializer().serializeToString(doc);
}


function collectBpmnIds(doc) {
  const ids = new Set();
  Array.from(doc.getElementsByTagName('*')).forEach((el) => {
    const id = el.getAttribute('id');
    if (id) ids.add(id);
  });
  return ids;
}

/** 在现有 BPMN XML 末尾追加一条泳道和一个默认活动。
 *  bpmn-js 没有官方的 createLane API，这里用 DOM 修改后重新导入。 */
export function appendBpmnLane(xml, name, modelKeys = []) {
  const doc = bpmnXmlDoc(xml);
  const processEl = doc.getElementsByTagNameNS(BPMN_NS, 'process')[0];
  if (!processEl) return null;
  const plane = doc.getElementsByTagNameNS(BPMNDI_NS, 'BPMNPlane')[0];
  const ids = collectBpmnIds(doc);
  let laneSet = directChildren(processEl, 'laneSet')[0];
  if (!laneSet) {
    laneSet = doc.createElementNS(BPMN_NS, 'bpmn:laneSet');
    laneSet.setAttribute('id', 'LaneSet_1');
    ids.add('LaneSet_1');
    processEl.insertBefore(laneSet, processEl.firstChild);
  }
  const existingLaneIds = new Set(
    directChildren(laneSet, 'lane').map((lane) => lane.getAttribute('id')),
  );
  let laneIndex = 1;
  while (ids.has('Lane_' + laneIndex)) laneIndex += 1;
  const laneId = 'Lane_' + laneIndex;
  ids.add(laneId);
  const usedKeys = new Set(modelKeys);
  let nodeIndex = 1;
  while (usedKeys.has('n' + nodeIndex) || ids.has('n' + nodeIndex)) nodeIndex += 1;
  const taskId = 'n' + nodeIndex;

  const shapeBounds = (shape) => {
    const bounds = directChildren(shape, 'Bounds')[0];
    if (!bounds) return null;
    return {
      x: Number(bounds.getAttribute('x')) || 0,
      y: Number(bounds.getAttribute('y')) || 0,
      width: Number(bounds.getAttribute('width')) || 0,
      height: Number(bounds.getAttribute('height')) || 0,
    };
  };
  let left = 40;
  let width = 800;
  let top = 40;
  if (plane) {
    const laneBounds = directChildren(plane, 'BPMNShape')
      .filter((shape) => existingLaneIds.has(shape.getAttribute('bpmnElement')))
      .map(shapeBounds)
      .filter(Boolean);
    const nodeBounds = directChildren(plane, 'BPMNShape')
      .map(shapeBounds)
      .filter(Boolean);
    if (laneBounds.length) {
      left = Math.min(...laneBounds.map((item) => item.x));
      width = Math.max(...laneBounds.map((item) => item.x + item.width)) - left;
      top = Math.max(...laneBounds.map((item) => item.y + item.height)) + 20;
    } else if (nodeBounds.length) {
      left = Math.max(0, Math.min(...nodeBounds.map((item) => item.x)) - 40);
      width = Math.max(...nodeBounds.map((item) => item.x + item.width)) - left + 40;
      top = Math.max(...nodeBounds.map((item) => item.y + item.height)) + 20;
    }
    width = Math.max(width, 600);
  }

  const lane = doc.createElementNS(BPMN_NS, 'bpmn:lane');
  lane.setAttribute('id', laneId);
  lane.setAttribute('name', name);
  const ref = doc.createElementNS(BPMN_NS, 'bpmn:flowNodeRef');
  ref.textContent = taskId;
  lane.appendChild(ref);
  laneSet.appendChild(lane);

  const task = doc.createElementNS(BPMN_NS, 'bpmn:task');
  task.setAttribute('id', taskId);
  task.setAttribute('name', '新活动');
  const firstFlow = directChildren(processEl, 'sequenceFlow')[0] || null;
  processEl.insertBefore(task, firstFlow);

  if (plane) {
    const laneShape = doc.createElementNS(BPMNDI_NS, 'bpmndi:BPMNShape');
    laneShape.setAttribute('id', 'Shape_' + laneId);
    laneShape.setAttribute('bpmnElement', laneId);
    laneShape.setAttribute('isHorizontal', 'true');
    const laneBox = doc.createElementNS(DC_NS, 'dc:Bounds');
    laneBox.setAttribute('x', String(roundCoord(left)));
    laneBox.setAttribute('y', String(roundCoord(top)));
    laneBox.setAttribute('width', String(roundCoord(width)));
    laneBox.setAttribute('height', '140');
    laneShape.appendChild(laneBox);
    const firstShape = directChildren(plane, 'BPMNShape')[0] || null;
    plane.insertBefore(laneShape, firstShape);

    const taskShape = doc.createElementNS(BPMNDI_NS, 'bpmndi:BPMNShape');
    taskShape.setAttribute('id', taskId + '_di');
    taskShape.setAttribute('bpmnElement', taskId);
    const taskBox = doc.createElementNS(DC_NS, 'dc:Bounds');
    taskBox.setAttribute('x', String(roundCoord(left + 120)));
    taskBox.setAttribute('y', String(roundCoord(top + 30)));
    taskBox.setAttribute('width', '100');
    taskBox.setAttribute('height', '80');
    taskShape.appendChild(taskBox);
    const firstEdge = directChildren(plane, 'BPMNEdge')[0] || null;
    plane.insertBefore(taskShape, firstEdge);
  }
  return { xml: new XMLSerializer().serializeToString(doc), laneId, taskId };
}


const BPMN_NS = 'http://www.omg.org/spec/BPMN/20100524/MODEL';
const BPMNDI_NS = 'http://www.omg.org/spec/BPMN/20100524/DI';
const DC_NS = 'http://www.omg.org/spec/DD/20100524/DC';
const DI_NS = 'http://www.omg.org/spec/DD/20100524/DI';

function bpmnXmlDoc(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) {
    throw new Error('BPMN XML 解析失败，无法自动布局');
  }
  return doc;
}

function directChildren(element, name) {
  return Array.from(element.children).filter((child) => child.localName === name);
}

function roundCoord(value) {
  return Math.round(value * 10) / 10;
}

/** 把折线强制成正交走线，并去掉重复点/共线中间点。
 *  自动布局的折点在泳道重排后可能变成斜线，斜穿泳道很难看。 */
export function orthogonalizePath(points) {
  if (points.length < 2) return points;
  const fixed = [points[0]];
  for (let index = 1; index < points.length; index += 1) {
    const prev = fixed[fixed.length - 1];
    const point = points[index];
    const dx = point.x - prev.x;
    const dy = point.y - prev.y;
    if (Math.abs(dx) > 0.5 && Math.abs(dy) > 0.5) {
      fixed.push(Math.abs(dx) >= Math.abs(dy)
        ? { x: point.x, y: prev.y }
        : { x: prev.x, y: point.y });
    }
    fixed.push(point);
  }
  const result = [];
  fixed.forEach((point) => {
    const last = result[result.length - 1];
    if (last && Math.abs(last.x - point.x) < 0.5 && Math.abs(last.y - point.y) < 0.5) return;
    result.push(point);
  });
  for (let index = result.length - 2; index >= 1; index -= 1) {
    const a = result[index - 1];
    const b = result[index];
    const c = result[index + 1];
    const sameX = Math.abs(a.x - b.x) < 0.5 && Math.abs(b.x - c.x) < 0.5;
    const sameY = Math.abs(a.y - b.y) < 0.5 && Math.abs(b.y - c.y) < 0.5;
    if (sameX || sameY) result.splice(index, 1);
  }
  return result;
}

/**
 * 水平泳道自动布局：按拓扑列从左到右、按泳道分行。
 * bpmn-auto-layout 默认纵向排布，和横向泳道冲突，故有泳道时用本算法。
 */
export function layoutHorizontalSwimlanes(xml) {
  const doc = bpmnXmlDoc(xml);
  const processEl = doc.getElementsByTagNameNS(BPMN_NS, 'process')[0];
  const plane = doc.getElementsByTagNameNS(BPMNDI_NS, 'BPMNPlane')[0];
  if (!processEl || !plane) return xml;
  const laneSet = directChildren(processEl, 'laneSet')[0];
  if (!laneSet || !directChildren(laneSet, 'lane').length) return xml;

  const ORIGIN_X = 180;
  const COL_GAP = 70;
  const LANE_PAD_TOP = 52; // 给回边「上绕」留走廊，避免贴底重叠
  const LANE_PAD_BOTTOM = 28;
  const LANE_GAP = 20;
  const MIN_LANE_H = 120;
  const LANE_LEFT = 100;

  const shapeById = new Map();
  directChildren(plane, 'BPMNShape').forEach((shape) => {
    const id = shape.getAttribute('bpmnElement');
    const bounds = directChildren(shape, 'Bounds')[0];
    if (!id || !bounds) return;
    shapeById.set(id, {
      shape,
      bounds,
      w: Number(bounds.getAttribute('width')) || 100,
      h: Number(bounds.getAttribute('height')) || 80,
    });
  });

  const laneOf = new Map();
  const lanes = directChildren(laneSet, 'lane').map((lane) => {
    const id = lane.getAttribute('id');
    const members = directChildren(lane, 'flowNodeRef')
      .map((ref) => (ref.textContent || '').trim())
      .filter((nid) => shapeById.has(nid));
    members.forEach((nid) => laneOf.set(nid, id));
    return { id, lane, members };
  });

  const flows = [];
  directChildren(processEl, 'sequenceFlow').forEach((flow) => {
    flows.push({
      id: flow.getAttribute('id'),
      source: flow.getAttribute('sourceRef'),
      target: flow.getAttribute('targetRef'),
    });
  });

  const nodeIds = [...shapeById.keys()].filter((id) =>
    !lanes.some((l) => l.id === id));
  const outgoing = new Map();
  const incoming = new Map();
  nodeIds.forEach((id) => {
    outgoing.set(id, []);
    incoming.set(id, []);
  });
  flows.forEach((f) => {
    if (outgoing.has(f.source)) outgoing.get(f.source).push(f.target);
    if (incoming.has(f.target)) incoming.get(f.target).push(f.source);
  });

  // 列号：从开始节点 BFS；已访问不再更新（回边保持原列，走外侧绕线）
  const rank = new Map();
  const starts = nodeIds.filter((id) => {
    const el = Array.from(processEl.children).find((c) => c.getAttribute('id') === id);
    return (el && el.localName === 'startEvent') || !(incoming.get(id) || []).length;
  });
  const queue = (starts.length ? starts : nodeIds.slice(0, 1)).slice();
  queue.forEach((id) => rank.set(id, 0));
  while (queue.length) {
    const cur = queue.shift();
    const base = rank.get(cur) || 0;
    (outgoing.get(cur) || []).forEach((nxt) => {
      if (rank.has(nxt)) return;
      rank.set(nxt, base + 1);
      queue.push(nxt);
    });
  }
  nodeIds.forEach((id) => {
    if (!rank.has(id)) rank.set(id, 0);
  });

  const maxRank = Math.max(0, ...nodeIds.map((id) => rank.get(id) || 0));
  const colWidth = [];
  for (let r = 0; r <= maxRank; r += 1) {
    const widths = nodeIds.filter((id) => rank.get(id) === r).map((id) => shapeById.get(id).w);
    colWidth[r] = widths.length ? Math.max(...widths) : 100;
  }
  const colX = [];
  let xCursor = ORIGIN_X;
  for (let r = 0; r <= maxRank; r += 1) {
    colX[r] = xCursor;
    xCursor += colWidth[r] + COL_GAP;
  }
  const contentRight = xCursor - COL_GAP + 40;

  // 每泳道内同列多节点纵向错开
  const pos = new Map();
  let laneTop = 40;
  const laneBoxes = [];
  lanes.forEach(({ id, members }) => {
    const byRank = new Map();
    members.forEach((nid) => {
      const r = rank.get(nid) || 0;
      if (!byRank.has(r)) byRank.set(r, []);
      byRank.get(r).push(nid);
    });
    let maxStack = 1;
    byRank.forEach((list) => {
      maxStack = Math.max(maxStack, list.length);
    });
    const stackH = Math.max(
      ...members.map((nid) => shapeById.get(nid).h),
      80,
    );
    const innerH = LANE_PAD_TOP + LANE_PAD_BOTTOM
      + maxStack * stackH + Math.max(0, maxStack - 1) * 16;
    const laneH = Math.max(MIN_LANE_H, innerH);
    laneBoxes.push({
      id,
      x: LANE_LEFT,
      y: laneTop,
      width: contentRight - LANE_LEFT,
      height: laneH,
    });
    byRank.forEach((list, r) => {
      list.sort((a, b) => a.localeCompare(b));
      // 节点偏下，上沿留给「重新提交」类回边
      let y0 = laneTop + LANE_PAD_TOP;
      list.forEach((nid) => {
        const sh = shapeById.get(nid);
        const px = colX[r] + (colWidth[r] - sh.w) / 2;
        pos.set(nid, { x: px, y: y0, w: sh.w, h: sh.h });
        y0 += stackH + 16;
      });
    });
    laneTop += laneH + LANE_GAP;
  });

  // 无泳道归属的节点（少见）排在最底
  nodeIds.filter((id) => !laneOf.has(id)).forEach((nid, index) => {
    const sh = shapeById.get(nid);
    const r = rank.get(nid) || 0;
    pos.set(nid, {
      x: colX[r],
      y: laneTop + 20 + index * (sh.h + 20),
      w: sh.w,
      h: sh.h,
    });
  });

  // 写回节点 Bounds；清掉旧泳道 Shape 后重建
  directChildren(plane, 'BPMNShape').forEach((shape) => {
    const id = shape.getAttribute('bpmnElement');
    if (lanes.some((l) => l.id === id)) {
      plane.removeChild(shape);
      return;
    }
    const p = pos.get(id);
    const bounds = directChildren(shape, 'Bounds')[0];
    if (!p || !bounds) return;
    bounds.setAttribute('x', String(roundCoord(p.x)));
    bounds.setAttribute('y', String(roundCoord(p.y)));
  });

  const firstNodeShape = directChildren(plane, 'BPMNShape')[0] || null;
  laneBoxes.forEach((box) => {
    const shape = doc.createElementNS(BPMNDI_NS, 'bpmndi:BPMNShape');
    shape.setAttribute('id', 'Shape_' + box.id);
    shape.setAttribute('bpmnElement', box.id);
    shape.setAttribute('isHorizontal', 'true');
    const bounds = doc.createElementNS(DC_NS, 'dc:Bounds');
    bounds.setAttribute('x', String(roundCoord(box.x)));
    bounds.setAttribute('y', String(roundCoord(box.y)));
    bounds.setAttribute('width', String(roundCoord(box.width)));
    bounds.setAttribute('height', String(roundCoord(box.height)));
    shape.appendChild(bounds);
    plane.insertBefore(shape, firstNodeShape);
  });

  // 正交连线：前向右→竖→右；回边从节点顶侧向上绕行再落到目标顶侧（错开正向竖线）
  const edgeByFlow = new Map();
  directChildren(plane, 'BPMNEdge').forEach((edge) => {
    edgeByFlow.set(edge.getAttribute('bpmnElement'), edge);
  });
  const forwardEdges = [];
  const backEdges = [];
  flows.forEach((f) => {
    const sRank = rank.get(f.source) || 0;
    const tRank = rank.get(f.target) || 0;
    if (tRank >= sRank) forwardEdges.push(f);
    else backEdges.push(f);
  });
  // 同起点多条前向边错开竖走廊，避免「驳回」与主干重叠
  const forwardFrom = new Map();
  forwardEdges.forEach((f) => {
    if (!forwardFrom.has(f.source)) forwardFrom.set(f.source, []);
    forwardFrom.get(f.source).push(f);
  });

  const routeEdge = (f, opts) => {
    const edge = edgeByFlow.get(f.id);
    const s = pos.get(f.source);
    const t = pos.get(f.target);
    if (!edge || !s || !t) return;
    let coords;
    if (!opts.back) {
      const sx = s.x + s.w;
      const sy = s.y + s.h / 2;
      const tx = t.x;
      const ty = t.y + t.h / 2;
      const siblings = forwardFrom.get(f.source) || [f];
      const idx = Math.max(0, siblings.findIndex((item) => item.id === f.id));
      const stagger = (idx - (siblings.length - 1) / 2) * 18;
      if (Math.abs(sy - ty) < 1 && Math.abs(stagger) < 1) {
        coords = [{ x: sx, y: sy }, { x: tx, y: ty }];
      } else {
        const midX = roundCoord((sx + tx) / 2 + stagger);
        coords = [
          { x: sx, y: sy },
          { x: midX, y: sy },
          { x: midX, y: ty },
          { x: tx, y: ty },
        ];
      }
    } else {
      // 回边：源顶心 → 上绕水平走廊 → 目标顶心（类似「重新提交」佳例）
      const sx = s.x + s.w / 2;
      const sy = s.y;
      const tx = t.x + t.w / 2;
      const ty = t.y;
      const laneId = laneOf.get(f.source) || laneOf.get(f.target);
      const laneBox = laneBoxes.find((b) => b.id === laneId);
      const stack = opts.backIndex || 0;
      // 优先走泳道内上沿走廊（节点已偏下），多条回边逐级再抬高
      let detourY = (laneBox ? laneBox.y + 16 : Math.min(s.y, t.y) - 36) - stack * 18;
      if (detourY >= Math.min(s.y, t.y) - 12) {
        detourY = Math.min(s.y, t.y) - 28 - stack * 18;
      }
      coords = [
        { x: sx, y: sy },
        { x: sx, y: detourY },
        { x: tx, y: detourY },
        { x: tx, y: ty },
      ];
    }
    coords = orthogonalizePath(coords);
    directChildren(edge, 'waypoint').forEach((wp) => edge.removeChild(wp));
    coords.forEach((point) => {
      const waypoint = doc.createElementNS(DI_NS, 'di:waypoint');
      waypoint.setAttribute('x', String(roundCoord(point.x)));
      waypoint.setAttribute('y', String(roundCoord(point.y)));
      edge.appendChild(waypoint);
    });
  };

  forwardEdges.forEach((f) => routeEdge(f, { back: false }));
  // 同泳道回边按目标列排序，走廊高度逐条抬高
  backEdges
    .slice()
    .sort((a, b) => (rank.get(a.target) || 0) - (rank.get(b.target) || 0))
    .forEach((f, index) => routeEdge(f, { back: true, backIndex: index }));

  return new XMLSerializer().serializeToString(doc);
}

/** bpmn-moddle 不会从 sequenceFlow 反推 incoming/outgoing。
 *  缺少这两个引用时，bpmn-auto-layout 会把所有节点排成一列。 */
export function ensureFlowRefs(xml) {
  const doc = bpmnXmlDoc(xml);
  const processEl = doc.getElementsByTagNameNS(BPMN_NS, 'process')[0];
  if (!processEl) return xml;
  const incoming = new Map();
  const outgoing = new Map();
  const push = (map, key, value) => {
    if (!key || !value) return;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(value);
  };
  directChildren(processEl, 'sequenceFlow').forEach((flow) => {
    push(outgoing, flow.getAttribute('sourceRef'), flow.getAttribute('id'));
    push(incoming, flow.getAttribute('targetRef'), flow.getAttribute('id'));
  });
  Array.from(processEl.children).forEach((element) => {
    const id = element.getAttribute('id');
    if (!id || (!incoming.has(id) && !outgoing.has(id))) return;
    if (directChildren(element, 'incoming').length
      || directChildren(element, 'outgoing').length) return;
    (incoming.get(id) || []).forEach((flowId) => {
      const ref = doc.createElementNS(BPMN_NS, 'bpmn:incoming');
      ref.textContent = flowId;
      element.appendChild(ref);
    });
    (outgoing.get(id) || []).forEach((flowId) => {
      const ref = doc.createElementNS(BPMN_NS, 'bpmn:outgoing');
      ref.textContent = flowId;
      element.appendChild(ref);
    });
  });
  return new XMLSerializer().serializeToString(doc);
}


export function restoreLanes(xml) {
  const doc = bpmnXmlDoc(xml);
  const processEl = doc.getElementsByTagNameNS(BPMN_NS, 'process')[0];
  const plane = doc.getElementsByTagNameNS(BPMNDI_NS, 'BPMNPlane')[0];
  if (!processEl || !plane) return xml;
  const laneSet = directChildren(processEl, 'laneSet')[0];
  if (!laneSet) return xml;

  const shapes = new Map();
  directChildren(plane, 'BPMNShape').forEach((shape) => {
    const id = shape.getAttribute('bpmnElement');
    const bounds = directChildren(shape, 'Bounds')[0];
    if (!id || !bounds) return;
    shapes.set(id, {
      id,
      bounds,
      x: Number(bounds.getAttribute('x')) || 0,
      y: Number(bounds.getAttribute('y')) || 0,
      width: Number(bounds.getAttribute('width')) || 0,
      height: Number(bounds.getAttribute('height')) || 0,
    });
  });

  const flows = new Map();
  directChildren(processEl, 'sequenceFlow').forEach((flow) => {
    flows.set(flow.getAttribute('id'), {
      source: flow.getAttribute('sourceRef'),
      target: flow.getAttribute('targetRef'),
    });
  });

  let minX = Infinity;
  let maxX = -Infinity;
  const laneRows = directChildren(laneSet, 'lane').map((lane) => {
    const members = directChildren(lane, 'flowNodeRef')
      .map((ref) => shapes.get((ref.textContent || '').trim()))
      .filter(Boolean);
    members.forEach((item) => {
      minX = Math.min(minX, item.x);
      maxX = Math.max(maxX, item.x + item.width);
    });
    // 自动布局把并行分支放在不同行；同泳道内保留这些行，避免节点重叠
    const rows = [];
    members.slice().sort((a, b) => a.y - b.y || a.x - b.x).forEach((item) => {
      const row = rows.find((candidate) => Math.abs(candidate.y - item.y) <= 5);
      if (row) row.items.push(item);
      else rows.push({ y: item.y, items: [item] });
    });
    return { lane, rows };
  }).filter((entry) => entry.rows.length);
  if (!laneRows.length) return xml;

  const PAD_X = 90;
  const PAD_Y = 24;
  const ROW_GAP = 24;
  const LANE_GAP = 18;
  // 左侧留出泳道标题栏（bpmn-js 约 30px）和调色板覆盖区
  const SHIFT_X = 80;
  const left = minX + SHIFT_X - PAD_X;
  const width = maxX - minX + PAD_X * 2;
  const deltaY = new Map();
  const laneShapes = [];
  let cursor = 40;
  laneRows.forEach(({ lane, rows }) => {
    const rowHeights = rows.map((row) => Math.max(...row.items.map((item) => item.height)));
    const height = PAD_Y * 2
      + rowHeights.reduce((sum, value) => sum + value, 0)
      + ROW_GAP * (rows.length - 1);
    laneShapes.push({
      id: lane.getAttribute('id'),
      x: left,
      y: cursor,
      width,
      height,
    });
    let rowTop = cursor + PAD_Y;
    rows.forEach((row, rowIndex) => {
      const rowHeight = rowHeights[rowIndex];
      row.items.forEach((item) => {
        const y = rowTop + (rowHeight - item.height) / 2;
        deltaY.set(item.id, y - item.y);
        item.bounds.setAttribute('x', String(roundCoord(item.x + SHIFT_X)));
        item.bounds.setAttribute('y', String(roundCoord(y)));
      });
      rowTop += rowHeight + ROW_GAP;
    });
    cursor += height + LANE_GAP;
  });

  // 泳道要画在节点下面，所以插到第一个节点形状之前
  const firstShape = directChildren(plane, 'BPMNShape')[0] || null;
  laneShapes.forEach((lane) => {
    const shape = doc.createElementNS(BPMNDI_NS, 'bpmndi:BPMNShape');
    shape.setAttribute('id', 'Shape_' + lane.id);
    shape.setAttribute('bpmnElement', lane.id);
    shape.setAttribute('isHorizontal', 'true');
    const bounds = doc.createElementNS(DC_NS, 'dc:Bounds');
    bounds.setAttribute('x', String(roundCoord(lane.x)));
    bounds.setAttribute('y', String(roundCoord(lane.y)));
    bounds.setAttribute('width', String(roundCoord(lane.width)));
    bounds.setAttribute('height', String(roundCoord(lane.height)));
    shape.appendChild(bounds);
    plane.insertBefore(shape, firstShape);
  });

  // 节点换了纵向位置，连线折点也要跟着走，并强制成正交走线
  directChildren(plane, 'BPMNEdge').forEach((edge) => {
    const flow = flows.get(edge.getAttribute('bpmnElement'));
    if (!flow) return;
    const dyS = deltaY.get(flow.source) || 0;
    const dyT = deltaY.get(flow.target) || 0;
    const points = directChildren(edge, 'waypoint');
    if (!points.length) return;
    const middle = (points.length - 1) / 2;
    let coords = points.map((point, index) => ({
      x: (Number(point.getAttribute('x')) || 0) + SHIFT_X,
      y: (Number(point.getAttribute('y')) || 0) + (index < middle ? dyS : dyT),
    }));
    // 首尾点严格跟随源/目标节点，避免终点脱离节点
    coords[0] = { ...coords[0], y: (Number(points[0].getAttribute('y')) || 0) + dyS };
    coords[coords.length - 1] = {
      ...coords[coords.length - 1],
      y: (Number(points[points.length - 1].getAttribute('y')) || 0) + dyT,
    };
    coords = orthogonalizePath(coords);
    points.forEach((point) => edge.removeChild(point));
    coords.forEach((point) => {
      const waypoint = doc.createElementNS(DI_NS, 'di:waypoint');
      waypoint.setAttribute('x', String(roundCoord(point.x)));
      waypoint.setAttribute('y', String(roundCoord(point.y)));
      edge.appendChild(waypoint);
    });
  });

  return new XMLSerializer().serializeToString(doc);
}

