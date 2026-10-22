/* 视图：designer */
import { esc, num, dur, dtShort, emptyRow, NODE_LABEL, NODE_CLASS } from '../core/format.js';
import { toast, openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { metricHelp } from '../core/metrics.js';
import { API_BASE, GET, POST, PUT, getToken } from '../core/api.js';
import { openToolByCode } from './toolbox.js';

/* ============================================================ 6. 流程设计器 */

async function openDesigner(processId) {
  state.designer.processId = processId;
  go('designer');
}

const renderDesigner = () => {
  const load = async () => {
    if (!state.designer.processes) {
      const rows = await GET('/process-map/flat');
      state.designer.processes = rows.filter((r) => r.level >= 3);
    }
    const list = state.designer.processes;
    if (!state.designer.processId && list.length) {
      const preferred = list.find((r) => r.code === 'L3-032') || list[0];
      state.designer.processId = preferred.id;
    }
    if (state.designer.processId) {
      const id = state.designer.processId;
      const [model, analysis] = await Promise.all([
        GET('/processes/' + id + '/design'),
        POST('/processes/' + id + '/design/analyze', {}),
      ]);
      state.designer.model = model;
      state.designer.savedModel = cloneModel(model);   // 回滚基准
      state.designer.analysis = analysis;
      state.designer.history = [];
      state.designer.future = [];
      state.designer.fitted = false;
      state.designer.processCode = (list.find((r) => r.id === id) || {}).code;
    }
  };
  renderAsync('designer', load, () => paintDesigner());
};

function paintDesigner() {
  const st = state.designer;
  const model = st.model;
  if (!model) {
    viewEl().innerHTML = '<div class="card"><div class="empty">请先选择一条流程</div></div>';
    return;
  }
  const opts = st.processes.map((p) =>
    '<option value="' + p.id + '"' + (p.id === st.processId ? ' selected' : '') + '>' +
    'L' + p.level + ' ' + esc(p.code) + ' ' + esc(p.name) + '</option>').join('');

  // 按泳道分组，泳道顺序取该泳道最早出现的节点顺序
  const lanes = [];
  const laneOf = {};
  model.nodes.slice().sort((a, b) => a.sequence_order - b.sequence_order).forEach((n) => {
    if (!laneOf[n.lane]) {
      laneOf[n.lane] = { name: n.lane, nodes: [], first: n.sequence_order };
      lanes.push(laneOf[n.lane]);
    }
    laneOf[n.lane].nodes.push(n);
  });
  lanes.sort((a, b) => a.first - b.first);

  // 按钮用下标引用泳道名，避免把用户输入拼进 onclick 属性
  st.lanes = lanes.map((l) => l.name);

  const proc = (st.processes || []).find((p) => p.id === st.processId) || {};
  const inReview = model.status === 'IN_REVIEW';
  const editable = !inReview && canWrite() && (canManage()
    || (AUTH.user && proc.owner_user_id === AUTH.user.id));

  const bnSet = new Set((st.analysis ? st.analysis.nodes : []).filter((n) => n.is_bottleneck)
    .map((n) => n.node_key));
  const metricOf = {};
  (st.analysis ? st.analysis.nodes : []).forEach((n) => { metricOf[n.node_key] = n; });
  st.editable = editable;
  st.bnSet = bnSet;
  st.metricOf = metricOf;
  normalizeLayout(st);

  const tab = st.tab || 'model';
  const tabBar = `
    <div class="seg">
      <button class="${tab === 'model' ? 'on' : ''}" onclick="setDesignerTab('model')">流程模型</button>
      <button class="${tab === 'analysis' ? 'on' : ''}" onclick="setDesignerTab('analysis')">
        指标与建议${st.analysis ? ' · ' + st.analysis.suggestions.length : ''}</button>
    </div>`;

  const modelPane = `
    <div class="card designer-card">
      <div class="between mb designer-toolbar">
        <div class="gap">
          <span class="tiny">添加：</span>
          ${Object.keys(NODE_LABEL).map((t) =>
            `<button class="btn-sm" onclick="addNodeAtCenter('${t}')"${
              editable ? '' : ' disabled'}>${NODE_LABEL[t]}</button>`).join('')}
          <button class="btn-sm" onclick="addLane()"${editable ? '' : ' disabled'}>+ 泳道</button>
          <span class="designer-sep"></span>
          <button class="btn-sm" onclick="undoDesigner()" title="撤销">撤销</button>
          <button class="btn-sm" onclick="redoDesigner()" title="重做">重做</button>
          <button class="btn-sm" onclick="fitDesigner()">适应画布</button>
          <span class="tiny" id="designerZoom">100%</span>
        </div>
        <div class="tiny">拖拽移动 · 从节点右侧圆点拉线 · 点击连线编辑 · 滚轮缩放 · 拖空白平移</div>
      </div>
      <div class="designer-canvas" id="designerCanvas">
        <div class="designer-world" id="designerWorld">
          <div class="designer-lanes" id="designerLanes"></div>
          <svg class="designer-edge-layer" id="designerEdges"></svg>
          <div class="designer-node-layer" id="designerNodes"></div>
        </div>
      </div>
      ${validationHtml(st.model)}
    </div>`;

  const analysisPane = `
    <div class="grid g2">
      <div class="card">
        <h3>流程指标测算</h3>
        <div class="desc">全部由当前节点数据算出，不是拍脑袋</div>
        ${paintMetrics(st.analysis)}
      </div>
      <div class="card">
        <h3>${metricHelp('suggestion_rules', '改善建议')}</h3>
        <div class="desc">${st.analysis ? st.analysis.suggestions.length : 0} 条 · 按严重度排序，
          ${metricHelp('methodology_pick', '推荐方法论')}：<b>${esc((state.meta.methodology[st.analysis && st.analysis.recommended_methodology] ||
            (st.analysis && st.analysis.recommended_methodology) || '—'))}</b></div>
        ${paintSuggestions(st.analysis)}
      </div>
    </div>`;

  const statusTone = {
    DRAFT: 't-gry', IN_REVIEW: 't-yel', PUBLISHED: 't-grn', SUPERSEDED: 't-gry',
  };
  const statusBadge = model.status
    ? `<span class="tag ${statusTone[model.status] || 't-blu'}">${
      esc(model.status_label || model.status)} · v${model.draft_version || model.version}</span>`
    : '';
  const publishable = canManage() && (model.status === 'DRAFT' || model.status === 'IN_REVIEW');

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>流程设计器<span class="module-badge">建模与测算</span> · ${esc(model.process_name || '')}</h2>
          <div class="desc">${statusBadge}
            运行时版本 ${model.published_version ? 'v' + model.published_version : '尚未发布'} ·
            泳道式建模 · 改动保存为草稿，发布后才影响新实例</div>
        </div>
        <div class="gap">
          <select class="sel" onchange="switchProcess(this.value)">${opts}</select>
          <button class="btn btn-g" onclick="openVersionHistory()">版本历史</button>
          ${model.status === 'DRAFT' && editable
            ? '<button class="btn btn-g" onclick="submitReview()">提交评审</button>' : ''}
          ${model.status === 'IN_REVIEW' && canManage()
            ? '<button class="btn btn-g" onclick="rejectReview()">驳回</button>' : ''}
          ${publishable
            ? '<button class="btn btn-p" onclick="publishDesign()">发布到运行时</button>' : ''}
          <button class="btn btn-g" onclick="exportBpmn()">导出 BPMN</button>
          ${editable ? '<button class="btn btn-g" onclick="importBpmn()">导入 BPMN</button>' : ''}
          ${inReview
            ? '<span class="tiny" style="align-self:center">评审中，暂不可编辑</span>'
            : editable
              ? '<button class="btn btn-g" onclick="addLaneNode()">+ 添加泳道节点</button>'
              : '<span class="tiny" style="align-self:center">只读（你不是这条流程的 Owner）</span>'}
          <a class="link-btn" onclick="go('execution')">去流程执行 →</a>
          <button class="btn btn-p" onclick="reanalyze()">重新测算</button>
        </div>
      </div>
      <div class="mt">${tabBar}</div>
    </div>
    ${tab === 'analysis' ? analysisPane : modelPane}`;
  if (tab !== 'analysis') renderCanvas();
}

/* -------------------------------------------------- 画布 */

const DW = { laneH: 140, nodeW: 170, nodeH: 60, x0: 120, step: 200, top: 40 };

function normalizeLayout(st) {
  const ordered = st.model.nodes.slice().sort(
    (a, b) => (a.sequence_order || 0) - (b.sequence_order || 0));
  const lanes = [];
  ordered.forEach((n) => { if (!lanes.includes(n.lane)) lanes.push(n.lane); });
  st.lanes = lanes;
  const laneIdx = {};
  lanes.forEach((l, i) => { laneIdx[l] = i; });
  const counters = {};
  st.model.nodes.forEach((n) => {
    const i = laneIdx[n.lane] === undefined ? 0 : laneIdx[n.lane];
    counters[n.lane] = (counters[n.lane] || 0) + 1;
    if (!n.position_x || n.position_x < 20) {
      n.position_x = DW.x0 + (counters[n.lane] - 1) * DW.step;
    }
    n.position_y = DW.top + i * DW.laneH + 40;
  });
}

function validateModel(model) {
  const errors = [];
  const warnings = [];
  const keys = new Set();
  (model.nodes || []).forEach((n) => {
    if (keys.has(n.node_key)) errors.push(`节点 key 重复：${n.node_key}`);
    keys.add(n.node_key);
  });
  const pairs = new Set();
  (model.edges || []).forEach((e) => {
    if (!keys.has(e.source_key) || !keys.has(e.target_key)) {
      errors.push(`连线 ${e.source_key} → ${e.target_key} 引用了不存在的节点`);
    }
    if (e.source_key === e.target_key) {
      errors.push(`连线 ${e.source_key} → ${e.target_key} 是自环`);
    }
    const pair = e.source_key + '→' + e.target_key;
    if (pairs.has(pair)) errors.push(`重复连线：${pair}`);
    pairs.add(pair);
    if (e.probability < 0 || e.probability > 1) {
      errors.push(`连线 ${pair} 的概率必须在 0–1`);
    }
  });
  const starts = (model.nodes || []).filter((n) => n.node_type === 'START');
  if (starts.length > 1) errors.push(`只能有一个开始节点，当前有 ${starts.length} 个`);
  if (!starts.length) warnings.push('没有开始节点，运行时将按唯一入口推断');
  if (!(model.nodes || []).some((n) => n.node_type === 'END')) {
    warnings.push('没有结束节点，末端任务完成后实例结束');
  }
  const targets = new Set((model.edges || []).map((e) => e.target_key));
  (model.nodes || []).forEach((n) => {
    if (n.node_type !== 'START' && !targets.has(n.node_key)) {
      warnings.push(`节点「${n.name}」没有入边，可能是不可达节点`);
    }
  });
  return { errors, warnings };
}

function validationHtml(model) {
  const v = validateModel(model);
  if (!v.errors.length && !v.warnings.length) return '';
  const items = [
    ...v.errors.map((m) => `<div class="designer-issue error">✕ ${esc(m)}</div>`),
    ...v.warnings.map((m) => `<div class="designer-issue warn">! ${esc(m)}</div>`),
  ].join('');
  return `<div class="designer-validation">${items}</div>`;
}

function renderCanvas() {
  const st = state.designer;
  const world = document.getElementById('designerWorld');
  if (!world || !st.model) return;
  const lanesEl = document.getElementById('designerLanes');
  const edgesEl = document.getElementById('designerEdges');
  const nodesEl = document.getElementById('designerNodes');
  const zoomEl = document.getElementById('designerZoom');
  const zoom = st.zoom || 1;
  const pan = st.pan || { x: 0, y: 0 };
  const laneCount = Math.max(1, (st.lanes || []).length);
  const maxX = Math.max(900, ...st.model.nodes.map((n) => (n.position_x || 0) + 360));
  const height = DW.top + laneCount * DW.laneH + 80;
  world.style.width = maxX + 'px';
  world.style.height = height + 'px';
  world.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
  if (zoomEl) zoomEl.textContent = Math.round(zoom * 100) + '%';

  lanesEl.innerHTML = (st.lanes || []).map((name, i) => `
    <div class="designer-lane" style="top:${DW.top + i * DW.laneH}px;
      height:${DW.laneH}px;width:${maxX}px">
      <span>${esc(name)}</span>
    </div>`).join('');

  const byKey = {};
  st.model.nodes.forEach((n) => { byKey[n.node_key] = n; });
  edgesEl.setAttribute('width', maxX);
  edgesEl.setAttribute('height', height);
  edgesEl.setAttribute('viewBox', `0 0 ${maxX} ${height}`);
  edgesEl.innerHTML = `
    <defs>
      <marker id="dArrow" viewBox="0 0 10 10" refX="9" refY="5"
        markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--line-strong)"></path>
      </marker>
      <marker id="dArrowSel" viewBox="0 0 10 10" refX="9" refY="5"
        markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--brand)"></path>
      </marker>
    </defs>
    ${(st.model.edges || []).map((e, i) => {
      const s = byKey[e.source_key];
      const t = byKey[e.target_key];
      if (!s || !t) return '';
      const sx = (s.position_x || 0) + DW.nodeW;
      const sy = (s.position_y || 0) + DW.nodeH / 2;
      const tx = t.position_x || 0;
      const ty = (t.position_y || 0) + DW.nodeH / 2;
      const bend = Math.max(50, Math.abs(tx - sx) / 2);
      const d = `M ${sx} ${sy} C ${sx + bend} ${sy}, ${tx - bend} ${ty}, ${tx} ${ty}`;
      const label = e.label || e.condition || '';
      const mx = (sx + tx) / 2;
      const my = (sy + ty) / 2 - 6;
      return `<path class="designer-edge-hit" data-edge="${i}" d="${d}"></path>
        <path class="designer-edge" data-edge="${i}" d="${d}"
          marker-end="url(#dArrow)"></path>${
        label ? `<text class="designer-edge-label" x="${mx}" y="${my}">${
          esc(label.length > 18 ? label.slice(0, 18) + '…' : label)}</text>` : ''}`;
    }).join('')}`;

  nodesEl.innerHTML = st.model.nodes.map((n) => {
    const bn = st.bnSet && st.bnSet.has(n.node_key);
    const m = st.metricOf ? st.metricOf[n.node_key] : null;
    return `<div class="node designer-node ${NODE_CLASS[n.node_type] || ''}${bn ? ' bn' : ''}"
        data-key="${esc(n.node_key)}"
        style="left:${n.position_x || 0}px;top:${n.position_y || 0}px;
          width:${DW.nodeW}px;height:${DW.nodeH}px">
      ${bn ? '<span class="bnbadge">瓶颈</span>' : ''}
      <b>${esc(n.name)}</b>
      <span class="designer-node-meta">${NODE_LABEL[n.node_type] || n.node_type} · ${
        dur(n.duration_minutes)}${n.wait_minutes > 0 ? ' +等 ' + dur(n.wait_minutes) : ''}${
        m && m.visit_count > 1.001 ? ' · ↻' + num(m.visit_count, 2) + '次' : ''}</span>
      <span class="designer-port" data-port="out" data-key="${esc(n.node_key)}"></span>
    </div>`;
  }).join('');

  attachCanvasInteractions();
  if (!st.fitted && st.model.nodes.length) {
    st.fitted = true;
    setTimeout(fitDesigner, 0);
  }
}

function canvasPoint(clientX, clientY) {
  const canvas = document.getElementById('designerCanvas');
  const st = state.designer;
  const rect = canvas.getBoundingClientRect();
  const pan = st.pan || { x: 0, y: 0 };
  const zoom = st.zoom || 1;
  return {
    x: (clientX - rect.left - pan.x) / zoom,
    y: (clientY - rect.top - pan.y) / zoom,
  };
}

function attachCanvasInteractions() {
  const st = state.designer;
  const canvas = document.getElementById('designerCanvas');
  if (!canvas) return;
  const editable = !!st.editable;

  document.querySelectorAll('.designer-edge-hit').forEach((el) => {
    el.addEventListener('click', (evt) => {
      evt.stopPropagation();
      openEdgeEditor(Number(el.dataset.edge));
    });
  });

  document.querySelectorAll('.designer-node').forEach((el) => {
    if (!editable) {
      el.addEventListener('click', () => openNodeEditor(el.dataset.key));
      return;
    }
    let drag = null;
    el.addEventListener('pointerdown', (evt) => {
      if (evt.target.classList.contains('designer-port')) return;
      evt.stopPropagation();
      const p = canvasPoint(evt.clientX, evt.clientY);
      drag = {
        key: el.dataset.key,
        startX: p.x,
        startY: p.y,
        nodeX: Number(el.style.left.replace('px', '')),
        nodeY: Number(el.style.top.replace('px', '')),
        moved: false,
        history: cloneModel(st.model),
      };
      el.setPointerCapture(evt.pointerId);
    });
    el.addEventListener('pointermove', (evt) => {
      if (!drag) return;
      const p = canvasPoint(evt.clientX, evt.clientY);
      const dx = p.x - drag.startX;
      const dy = p.y - drag.startY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true;
      el.style.left = Math.max(20, drag.nodeX + dx) + 'px';
      el.style.top = Math.max(20, drag.nodeY + dy) + 'px';
    });
    el.addEventListener('pointerup', () => {
      if (!drag) return;
      const node = st.model.nodes.find((n) => n.node_key === drag.key);
      const left = Number(el.style.left.replace('px', ''));
      const top = Number(el.style.top.replace('px', ''));
      if (drag.moved && node) {
        st.history.push(drag.history);
        st.history = st.history.slice(-60);
        st.future = [];
        node.position_x = left;
        node.lane = laneAt(top, st);
        persistDesign('节点位置已保存');
      } else if (!drag.moved) {
        openNodeEditor(drag.key);
      }
      drag = null;
    });
  });

  document.querySelectorAll('.designer-port').forEach((port) => {
    if (!editable) return;
    port.addEventListener('pointerdown', (evt) => {
      evt.stopPropagation();
      evt.preventDefault();
      const node = st.model.nodes.find((n) => n.node_key === port.dataset.key);
      if (!node) return;
      const sx = (node.position_x || 0) + DW.nodeW;
      const sy = (node.position_y || 0) + DW.nodeH / 2;
      const edgeLayer = document.getElementById('designerEdges');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', 'designer-edge draft');
      path.setAttribute('d', `M ${sx} ${sy} L ${sx} ${sy}`);
      path.setAttribute('marker-end', 'url(#dArrowSel)');
      edgeLayer.appendChild(path);
      const move = (e) => {
        const p = canvasPoint(e.clientX, e.clientY);
        const b = Math.max(40, Math.abs(p.x - sx) / 2);
        path.setAttribute('d',
          `M ${sx} ${sy} C ${sx + b} ${sy}, ${p.x - b} ${p.y}, ${p.x} ${p.y}`);
      };
      const up = (e) => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        const targetEl = document.elementFromPoint(e.clientX, e.clientY);
        const target = targetEl && targetEl.closest('.designer-node');
        const targetKey = target && target.dataset.key;
        path.remove();
        if (!targetKey || targetKey === node.node_key) return;
        if (st.model.edges.some((x) =>
          x.source_key === node.node_key && x.target_key === targetKey)) {
          return toast('这两个节点之间已有连线', true);
        }
        pushHistory();
        st.model.edges.push({
          source_key: node.node_key, target_key: targetKey,
          label: null, condition: null, probability: 1,
        });
        persistDesign('连线已创建');
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });
  });

  // 空白拖拽平移
  let panState = null;
  canvas.addEventListener('pointerdown', (evt) => {
    if (evt.target.closest('.designer-node') || evt.target.closest('.designer-edge')
      || evt.target.closest('.designer-edge-hit')) return;
    evt.preventDefault();
    panState = {
      x: evt.clientX, y: evt.clientY,
      panX: (st.pan || { x: 0, y: 0 }).x,
      panY: (st.pan || { x: 0, y: 0 }).y,
    };
    canvas.setPointerCapture(evt.pointerId);
  });
  canvas.addEventListener('pointermove', (evt) => {
    if (!panState) return;
    st.pan = {
      x: panState.panX + evt.clientX - panState.x,
      y: panState.panY + evt.clientY - panState.y,
    };
    const world = document.getElementById('designerWorld');
    if (world) {
      world.style.transform = `translate(${st.pan.x}px, ${st.pan.y}px) scale(${st.zoom || 1})`;
    }
  });
  canvas.addEventListener('pointerup', () => { panState = null; });
  canvas.addEventListener('wheel', (evt) => {
    evt.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const cx = evt.clientX - rect.left;
    const cy = evt.clientY - rect.top;
    const zoom = st.zoom || 1;
    const next = Math.min(2, Math.max(0.35, zoom * (evt.deltaY < 0 ? 1.1 : 0.9)));
    const m = canvasPoint(evt.clientX, evt.clientY);
    st.pan = { x: cx - m.x * next, y: cy - m.y * next };
    st.zoom = next;
    renderCanvas();
  }, { passive: false });
}

function laneAt(y, st) {
  const idx = Math.floor((y - DW.top) / DW.laneH);
  return (st.lanes && st.lanes[idx]) || (st.lanes && st.lanes[0]) || '主流程';
}

function pushHistory() {
  const st = state.designer;
  st.history = st.history || [];
  st.history.push(cloneModel(st.model));
  st.history = st.history.slice(-60);
  st.future = [];
}

function undoDesigner() {
  const st = state.designer;
  if (!st.history || !st.history.length) return toast('没有可撤销的操作');
  st.future = st.future || [];
  st.future.push(cloneModel(st.model));
  st.model = st.history.pop();
  normalizeLayout(st);
  paintDesigner();
  persistDesign('已撤销');
}

function redoDesigner() {
  const st = state.designer;
  if (!st.future || !st.future.length) return toast('没有可重做的操作');
  st.history = st.history || [];
  st.history.push(cloneModel(st.model));
  st.model = st.future.pop();
  normalizeLayout(st);
  paintDesigner();
  persistDesign('已重做');
}

function fitDesigner() {
  const st = state.designer;
  const canvas = document.getElementById('designerCanvas');
  if (!canvas || !st.model.nodes.length) return;
  const rect = canvas.getBoundingClientRect();
  const maxX = Math.max(...st.model.nodes.map((n) => (n.position_x || 0) + DW.nodeW)) + 80;
  const maxY = Math.max(...st.model.nodes.map((n) => (n.position_y || 0) + DW.nodeH)) + 80;
  const zoom = Math.min(1.2, Math.max(0.35,
    Math.min((rect.width - 40) / maxX, (rect.height - 40) / maxY)));
  st.zoom = zoom;
  st.pan = { x: 20, y: 20 };
  renderCanvas();
}

function addNodeAtCenter(type, lane, name) {
  const st = state.designer;
  const canvas = document.getElementById('designerCanvas');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const p = canvasPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
  let seq = 1;
  st.model.nodes.forEach((n) => { seq = Math.max(seq, n.sequence_order + 1); });
  let key = 'new_' + seq;
  while (st.model.nodes.some((n) => n.node_key === key)) key = 'new_' + (++seq);
  const laneName = lane || laneAt(p.y, st);
  const laneNodes = st.model.nodes.filter((n) => n.lane === laneName);
  const maxX = laneNodes.length
    ? Math.max(...laneNodes.map((n) => n.position_x || 0)) : 0;
  let x = Math.max(20, p.x);
  if (laneNodes.length && x <= maxX + 40) x = maxX + DW.step;
  pushHistory();
  st.model.nodes.push({
    node_key: key,
    name: name || NODE_LABEL[type] || '新节点',
    node_type: type,
    lane: laneName,
    owner_role: null,
    duration_minutes: 30,
    wait_minutes: 0,
    cost: 0,
    rework_rate: 0,
    approval_levels: 0,
    is_value_added: type !== 'DECISION' && type !== 'END',
    sequence_order: seq,
    position_x: x,
    position_y: Math.max(20, p.y),
  });
  normalizeLayout(st);
  paintDesigner();
  persistDesign('节点已添加');
}

function addLane() {
  const name = prompt('输入泳道名称（部门 / 角色）：', '新泳道');
  if (name === null) return;
  const lane = name.trim() || '新泳道';
  if (state.designer.lanes.includes(lane)) return toast('泳道已存在', true);
  addNodeAtCenter('TASK', lane, '新活动');
}

async function openEdgeEditor(index) {
  const st = state.designer;
  const e = st.model.edges[index];
  if (!e) return;
  openModal('编辑连线', `
    <div class="field"><label>起点 → 终点</label>
      <input value="${esc(e.source_key)} → ${esc(e.target_key)}" readonly></div>
    <div class="row2">
      <div class="field"><label>标签</label>
        <input id="edgeLabel" value="${esc(e.label || '')}" placeholder="通过 / 驳回"></div>
      <div class="field"><label>概率</label>
        <input id="edgeProb" type="number" min="0" max="1" step="0.05"
          value="${e.probability}"></div>
    </div>
    <div class="field"><label>条件说明</label>
      <input id="edgeCond" value="${esc(e.condition || '')}"
        placeholder="预算与需求均合规"></div>`,
    `<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"
       onclick="deleteEdge(${index})">删除连线</button>
     <button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveEdge(${index})">保存</button>`);
}

function saveEdge(index) {
  const st = state.designer;
  const e = st.model.edges[index];
  if (!e) return;
  const prob = Number(document.getElementById('edgeProb').value);
  if (!Number.isFinite(prob) || prob < 0 || prob > 1) {
    return toast('概率必须在 0–1 之间', true);
  }
  pushHistory();
  e.label = document.getElementById('edgeLabel').value.trim() || null;
  e.condition = document.getElementById('edgeCond').value.trim() || null;
  e.probability = prob;
  closeModal();
  persistDesign('连线已保存');
}

function deleteEdge(index) {
  const st = state.designer;
  if (!st.model.edges[index]) return;
  pushHistory();
  st.model.edges.splice(index, 1);
  closeModal();
  persistDesign('连线已删除');
}

async function submitReview() {
  const note = window.prompt('评审说明（可选；取消则不提交）', '');
  if (note === null) return;
  try {
    await POST('/processes/' + state.designer.processId + '/design/submit-review', {
      note: note.trim() || null,
    });
    toast('已提交评审');
    await reloadDesign();
  } catch (e) {
    toast(e.message, true);
  }
}

async function rejectReview() {
  const note = window.prompt('驳回原因（可选）', '');
  if (note === null) return;
  try {
    await POST('/processes/' + state.designer.processId + '/design/reject', {
      note: note.trim() || null,
    });
    toast('已驳回，草稿可继续修改');
    await reloadDesign();
  } catch (e) {
    toast(e.message, true);
  }
}

async function publishDesign() {
  if (!confirm('发布后，新启动的流程实例将使用这个模型；运行中的实例仍用启动时快照。确定发布？')) {
    return;
  }
  try {
    await POST('/processes/' + state.designer.processId + '/design/publish', {
      expected_version: state.designer.model.version,
      change_note: null,
    });
    toast('模型已发布到运行时');
    await reloadDesign();
  } catch (e) {
    toast(e.message, true);
  }
}

async function openVersionHistory() {
  const pid = state.designer.processId;
  let rows = [];
  try {
    rows = await GET('/processes/' + pid + '/design/versions');
  } catch (e) {
    return toast(e.message, true);
  }
  const current = state.designer.model || {};
  const tone = { DRAFT: 't-gry', IN_REVIEW: 't-yel', PUBLISHED: 't-grn', SUPERSEDED: 't-gry' };
  const body = rows.map((v) => `
    <tr>
      <td><b>v${v.version}</b></td>
      <td><span class="tag ${tone[v.status] || 't-blu'}">${esc(v.status_label)}</span></td>
      <td class="tiny">${esc(v.change_note || '—')}</td>
      <td class="tiny">${esc(v.created_by_name || '—')}<div>${dtShort(v.created_at)}</div></td>
      <td class="tiny">${v.published_at ? dtShort(v.published_at) : '—'}</td>
      <td>
        ${v.id !== current.version_id
          ? `<button class="btn-sm" onclick="diffVersion(${v.id})">对比当前</button>` : ''}
        ${v.version !== current.version
          ? `<button class="btn-sm" onclick="rollbackVersion(${v.id})">回滚到此版</button>` : ''}
      </td>
    </tr>`).join('') || emptyRow(6, '还没有模型版本');
  openModal('模型版本历史', `
    <div class="note">草稿会覆盖；已发布版本保留。回滚会生成新草稿，发布后才影响运行时。</div>
    <table class="tbl">
      <thead><tr><th>版本</th><th>状态</th><th>说明</th><th>创建人</th><th>发布时间</th><th></th></tr></thead>
      <tbody>${body}</tbody>
    </table>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
}

async function diffVersion(versionId) {
  const currentId = state.designer.model && state.designer.model.version_id;
  if (!currentId) return toast('当前模型还没有版本记录', true);
  try {
    const d = await GET(
      '/processes/' + state.designer.processId + '/design/diff?from_version_id=' +
      versionId + '&to_version_id=' + currentId,
    );
    const line = (label, items, format) => items.length
      ? `<div class="diff-block"><b>${label}（${items.length}）</b>${
        items.map((item) => `<div class="tiny">${esc(format(item))}</div>`).join('')}</div>`
      : '';
    const content = [
      line('新增节点', d.nodes_added, (x) => x.node_key + ' ' + (x.name || '')),
      line('删除节点', d.nodes_removed, (x) => x.node_key + ' ' + (x.name || '')),
      line('修改节点', d.nodes_changed,
        (x) => x.node_key + '：' + x.fields.join('、')),
      line('新增连线', d.edges_added, (x) => x.source_key + ' → ' + x.target_key),
      line('删除连线', d.edges_removed, (x) => x.source_key + ' → ' + x.target_key),
      line('修改连线', d.edges_changed,
        (x) => x.source_key + ' → ' + x.target_key + '：' + x.fields.join('、')),
    ].join('') || '<div class="empty">两个版本没有差异</div>';
    openModal(`版本差异 · v${d.from_version} → v${d.to_version}`, content,
      '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
  } catch (e) {
    toast(e.message, true);
  }
}

async function rollbackVersion(versionId) {
  if (!confirm('回滚会在当前模型上创建一个新草稿，发布后才影响运行时。继续？')) return;
  try {
    await POST(
      '/processes/' + state.designer.processId + '/design/versions/' +
      versionId + '/rollback', { note: null });
    toast('已从历史版本创建草稿');
    closeModal();
    await reloadDesign();
  } catch (e) {
    toast(e.message, true);
  }
}

function setDesignerTab(tab) {
  state.designer.tab = tab;
  RENDERERS.designer();
}

/* -------------------------------------------------- BPMN 导入 / 导出 */

async function exportBpmn() {
  const id = state.designer.processId;
  if (!id) return toast('请先选择一条流程', true);
  try {
    const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
      headers: { Authorization: 'Bearer ' + getToken() },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || ('导出失败（' + res.status + '）'));
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (state.designer.processCode || 'process') + '.bpmn';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('BPMN 已导出');
  } catch (e) {
    toast(e.message, true);
  }
}

function importBpmn() {
  const id = state.designer.processId;
  if (!id) return toast('请先选择一条流程', true);
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.bpmn,.xml,text/xml,application/xml';
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    try {
      const xml = await file.text();
      const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + getToken(),
        },
        body: JSON.stringify({
          xml,
          expected_version: state.designer.model ? state.designer.model.version : null,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || ('导入失败（' + res.status + '）'));
      state.designer.model = body;
      state.designer.savedModel = cloneModel(body);
      state.designer.analysis = await POST(
        '/processes/' + id + '/design/analyze', {});
      state.designer.history = [];
      state.designer.future = [];
      state.designer.zoom = 1;
      state.designer.pan = { x: 0, y: 0 };
      state.designer.fitted = false;
      toast('BPMN 已导入并更新模型');
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  };
  input.click();
}

function paintMetrics(a) {
  if (!a) return '<div class="empty">暂无测算结果</div>';
  const m = a.metrics;

  // ratio 为 null 时不画进度条 —— 没有目标值的指标（周期、成本、移交次数）
  // 画条只能是编出来的百分比，那是误导，不如老实显示数字。
  const row = (label, value, hint, ratio, color) => {
    const hasBar = ratio !== null && ratio !== undefined && isFinite(ratio);
    const w = hasBar ? Math.max(0, Math.min(100, ratio)) : 0;
    return `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <span style="width:112px;font-size:12.5px">${label}</span>
        ${hasBar
          ? '<span style="flex:1;height:7px;background:var(--line-soft);border-radius:4px;overflow:hidden">' +
            '<i style="display:block;height:100%;border-radius:4px;width:' + w + '%;background:' + color + '"></i></span>'
          : '<span style="flex:1"></span>'}
        <span style="width:118px;font-size:12.5px;font-weight:600;text-align:right">${value}
          <span class="tiny" style="display:block;font-weight:400;line-height:1.4">${hint}</span></span>
      </div>`;
  };

  const pce = m.pce * 100;
  const waitShare = m.wait_ratio * 100;
  const workShare = m.lead_time_minutes ? (m.process_time_minutes / m.lead_time_minutes) * 100 : 0;
  const reworkShare = m.process_time_minutes
    ? (m.rework_work_minutes / m.process_time_minutes) * 100 : 0;

  const warn = m.diverged
    ? '<div class="warnbox mb">模型存在无法退出的环路或没有入口，当前已退回「每个节点各算一次」的粗略口径，'
      + '结果不可信。请检查连线与开始节点。</div>'
    : '';

  // 期望值 vs 线性合计：有分支/回路时两者会明显不同，必须让用户看见差别
  const cycleHint = m.has_branch_or_loop
    ? '线性合计 ' + dur(m.linear_lead_time_minutes) + '（旧口径，未计回路）'
    : '无分支回路，与线性合计一致';

  return warn +
    row(metricHelp('pce', '流程周期效率'), num(pce, 1) + '%', '增值 / 期望端到端',
      pce, pce >= 35 ? 'var(--ok)' : pce >= 15 ? 'var(--warn)' : 'var(--bad)') +
    row(metricHelp('wait_ratio', '等待占比'), num(waitShare, 1) + '%', num(m.wait_minutes, 0) + ' 分钟等待',
      waitShare, waitShare >= 50 ? 'var(--bad)' : waitShare >= 30 ? 'var(--warn)' : 'var(--ok)') +
    row(metricHelp('work_share', '作业时间占比'), num(workShare, 1) + '%', num(m.process_time_minutes, 0) + ' 分钟作业',
      workShare, 'var(--brand)') +
    row(metricHelp('rework_loss', '返工损失'), dur(m.rework_loss_minutes),
      '额外作业 ' + dur(m.rework_work_minutes) + ' · 占作业 ' + num(reworkShare, 1) + '%',
      reworkShare, reworkShare >= 15 ? 'var(--bad)' : reworkShare > 0 ? 'var(--warn)' : 'var(--ok)') +
    row(metricHelp('lead_time', '期望端到端周期'), dur(m.lead_time_minutes), cycleHint, null, '') +
    row(metricHelp('handoff_count', '跨泳道移交'), m.handoff_count + ' 次', m.lane_count + ' 个部门/角色', null, '') +
    row(metricHelp('approval_levels', '累计审批层级'), m.total_approval_levels + ' 层',
      m.approval_node_count + ' 个审批节点', null, '') +
    row(metricHelp('unit_cost', '单次执行成本'), num(m.unit_cost, 1) + ' 元', '全部节点的期望成本合计', null, '') +
    '<div class="note" style="margin-top:4px">按月 1000 单估算，' + metricHelp('fte_saved', '可释放人天/月') + '约 <b>' +
      num(m.fte_days_saved_per_month, 0) + ' 人天/月</b>（仅计返工带来的额外作业时间）。</div>';
}

function paintSuggestions(a) {
  if (!a || !a.suggestions.length) return '<div class="empty">暂无建议</div>';
  // 建议里的 related_nodes 是节点键，展示时翻成中文名
  const nameOf = {};
  ((state.designer.model || {}).nodes || []).forEach((n) => { nameOf[n.node_key] = n.name; });

  return a.suggestions.map((s) => `
    <div class="sug ${s.severity}">
      <div class="hd">
        <span>${s.severity === 'HIGH' ? '🔴' : s.severity === 'MEDIUM' ? '🟡' : '🟢'} ${esc(s.title)}</span>
        <span class="tag ${{ HIGH: 't-red', MEDIUM: 't-yel', LOW: 't-blu' }[s.severity]}">
          ${s.severity === 'HIGH' ? '高' : s.severity === 'MEDIUM' ? '中' : '低'}</span>
      </div>
      <div class="bd">${esc(s.detail)}</div>
      ${s.related_nodes && s.related_nodes.length
        ? '<div class="tiny" style="margin-top:6px">涉及节点：' +
          s.related_nodes.map((k) => esc(nameOf[k] || k)).join('、') + '</div>' : ''}
      ${s.suggested_tool ? '<button class="tool" onclick="openToolByCode(\'' + s.suggested_tool +
        '\')">→ 用「' + esc(s.suggested_tool) + '」动手</button>' : ''}
    </div>`).join('');
}

function switchProcess(id) {
  state.designer.processId = Number(id);
  state.designer.processCode = (state.designer.processes.find((p) => p.id === Number(id)) || {}).code;
  state.designer.tab = 'model';
  state.designer.zoom = 1;
  state.designer.pan = { x: 0, y: 0 };
  state.designer.fitted = false;
  state.designer.history = [];
  state.designer.future = [];
  RENDERERS.designer();
}

async function reanalyze() {
  try {
    state.designer.analysis = await POST('/processes/' + state.designer.processId + '/design/analyze', {});
    paintDesigner();
    toast('已重新测算');
  } catch (e) {
    toast(e.message, true);
  }
}

function cloneModel(model) {
  return JSON.parse(JSON.stringify(model));
}

/** 把当前内存中的模型整份提交给后端（后端是覆盖式保存）
 *
 *  节点编辑是「先改内存模型，再提交」的乐观更新。一旦后端拒绝（比如唯一键冲突、
 *  连线悬空），必须把模型回滚到最后一个服务端确认过的版本并重绘，
 *  否则内存里的模型和界面显示就分叉了，下次重绘会冒出从未保存成功的节点。
 */
async function persistDesign(successMsg) {
  const st = state.designer;
  const validation = validateModel(st.model);
  if (validation.errors.length) {
    toast('模型有错误：' + validation.errors[0], true);
    paintDesigner();
    return;
  }
  normalizeLayout(st);
  const payload = {
    nodes: st.model.nodes.map((n) => ({
      node_key: n.node_key, name: n.name, node_type: n.node_type, lane: n.lane,
      owner_role: n.owner_role, duration_minutes: n.duration_minutes, wait_minutes: n.wait_minutes,
      cost: n.cost, rework_rate: n.rework_rate, approval_levels: n.approval_levels,
      is_value_added: n.is_value_added, sequence_order: n.sequence_order,
      position_x: n.position_x, position_y: n.position_y,
    })),
    edges: st.model.edges.map((e) => ({
      source_key: e.source_key, target_key: e.target_key,
      label: e.label, condition: e.condition, probability: e.probability,
    })),
    // 带上「我编辑时所基于的版本」，服务端据此发现别人的并发修改
    expected_version: st.savedModel ? st.savedModel.version : null,
  };
  try {
    st.model = await PUT('/processes/' + st.processId + '/design', payload);
    st.savedModel = cloneModel(st.model);
    st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
    paintDesigner();
    if (successMsg) toast(successMsg);
  } catch (e) {
    if (e.status === 409) {
      // 别人先保存了：丢弃本地改动并重新载入最新版本，而不是覆盖别人的劳动成果
      toast(e.message + ' 已为你载入最新版本。', true);
      await reloadDesign();
      return;
    }
    st.model = cloneModel(st.savedModel);
    paintDesigner();
    toast('保存失败，已回滚到上次保存的版本：' + e.message, true);
  }
}

/** 丢弃本地改动，重新拉取服务端的最新模型与分析结果 */
async function reloadDesign() {
  const st = state.designer;
  try {
    const [model, analysis] = await Promise.all([
      GET('/processes/' + st.processId + '/design'),
      POST('/processes/' + st.processId + '/design/analyze', {}),
    ]);
    st.model = model;
    st.savedModel = cloneModel(model);
    st.analysis = analysis;
    st.history = [];
    st.future = [];
    paintDesigner();
  } catch (e) {
    toast(e.message, true);
  }
}

/** 节点点击入口：有权限就编辑，没权限就看只读详情 */
function openNodeEditor(nodeKey) {
  const st = state.designer;
  const proc = (st.processes || []).find((p) => p.id === st.processId) || {};
  const editable = canWrite() && (canManage()
    || (AUTH.user && proc.owner_user_id === AUTH.user.id));
  if (editable) return editNode(nodeKey);

  const n = (st.model.nodes || []).find((x) => x.node_key === nodeKey);
  if (!n) return;
  const m = (st.analysis ? st.analysis.nodes : []).find((x) => x.node_key === nodeKey) || {};
  openModal(n.name + ' · 节点详情', `
    <div class="row2">
      <div class="field"><label>节点类型</label>
        <input value="${NODE_LABEL[n.node_type] || n.node_type}" readonly></div>
      <div class="field"><label>所属泳道</label><input value="${esc(n.lane)}" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>负责人 / 岗位</label>
        <input value="${esc(n.owner_role || '未指定')}" readonly></div>
      <div class="field"><label>是否增值</label>
        <input value="${n.is_value_added ? '增值（VA）' : '非增值（NVA）'}" readonly></div>
    </div>
    <div class="row3">
      <div class="field"><label>作业时间</label><input value="${dur(n.duration_minutes)}" readonly></div>
      <div class="field"><label>等待时间</label><input value="${dur(n.wait_minutes)}" readonly></div>
      <div class="field"><label>返工率</label><input value="${num(n.rework_rate * 100, 0)}%" readonly></div>
    </div>
    <div class="row3">
      <div class="field"><label>审批层级</label><input value="${n.approval_levels}" readonly></div>
      <div class="field"><label>期望执行次数</label>
        <input value="${m.visit_count === undefined ? '—' : num(m.visit_count, 2)}" readonly></div>
      <div class="field"><label>对周期贡献</label>
        <input value="${m.weighted_minutes === undefined ? '—' : dur(m.weighted_minutes)}" readonly></div>
    </div>
    <div class="note">当前角色无编辑权限，如需修改请联系这条流程的 Owner 或流程管理科。</div>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
}

async function editNode(nodeKey) {
  const n = state.designer.model.nodes.find((x) => x.node_key === nodeKey);
  if (!n) return;
  const laneList = [...new Set(state.designer.model.nodes.map((x) => x.lane))];
  const pid = state.designer.processId;

  let assignment = null;
  let users = [];
  let orgs = [];
  let roles = [];
  let executionBlock = '';
  if (canManage()) {
    try {
      const [assignments, assignees, orgRows, meta] = await Promise.all([
        GET('/execution/assignments?process_id=' + pid),
        GET('/execution/assignees'),
        GET('/org-units'),
        GET('/auth/meta'),
      ]);
      assignment = assignments.find((x) => x.node_key === nodeKey) || {};
      users = assignees;
      orgs = orgRows;
      roles = meta.roles || [];
      const roleOpts = roles.map((r) =>
        `<option value="${esc(r.value)}"${assignment.role === r.value ? ' selected' : ''}>${
          esc(r.label)}</option>`).join('');
      const orgOpts = orgs.map((o) =>
        `<option value="${o.id}"${assignment.org_unit_id === o.id ? ' selected' : ''}>${
          esc(o.name)}</option>`).join('');
      const userOpts = users.map((u) =>
        `<option value="${u.id}"${assignment.default_assignee_user_id === u.id
          ? ' selected' : ''}>${esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`
      ).join('');
      const escUserOpts = users.map((u) =>
        `<option value="${u.id}"${assignment.escalation_user_id === u.id
          ? ' selected' : ''}>${esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`
      ).join('');
      executionBlock = `
        <div class="designer-exec-config">
          <div class="between mb"><h3 style="margin:0">执行配置</h3>
            <button class="btn-sm btn-p" onclick="saveNodeAssignment('${esc(nodeKey)}')">
              保存执行配置</button></div>
          <div class="desc" style="margin:0 0 8px">只影响发布后的新实例；运行中实例使用启动快照</div>
          <div class="row2">
            <div class="field"><label>候选角色</label>
              <select id="edRole"><option value="">不限</option>${roleOpts}</select></div>
            <div class="field"><label>限定组织</label>
              <select id="edOrg"><option value="">不限</option>${orgOpts}</select></div>
          </div>
          <div class="row2">
            <div class="field"><label>默认处理人</label>
              <select id="edAssignee"><option value="">公共队列</option>${userOpts}</select></div>
            <div class="field"><label>节点时限（小时）</label>
              <input id="edDue" type="number" min="0" max="8760"
                value="${assignment.due_hours ?? ''}" placeholder="跟随流程"></div>
          </div>
          <div class="row2">
            <div class="field"><label>升级时限（小时）</label>
              <input id="edEscHours" type="number" min="0" max="8760"
                value="${assignment.escalation_hours ?? ''}" placeholder="跟随流程"></div>
            <div class="field"><label>升级处理人</label>
              <select id="edEscUser"><option value="">跟随流程</option>${escUserOpts}</select></div>
          </div>
        </div>`;
    } catch (e) {
      executionBlock = `<div class="note mb">执行配置加载失败：${esc(e.message)}</div>`;
    }
  }

  openModal('编辑活动节点 · ' + n.name, `
    <div class="row2">
      <div class="field"><label>活动名称</label><input id="edName" value="${esc(n.name)}"></div>
      <div class="field"><label>节点类型</label>
        <select id="edType">${Object.keys(NODE_LABEL).map((t) =>
          '<option value="' + t + '"' + (n.node_type === t ? ' selected' : '') + '>' +
          NODE_LABEL[t] + '</option>').join('')}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>所属泳道（部门/角色）</label>
        <input id="edLane" list="laneList" value="${esc(n.lane)}">
        <datalist id="laneList">${laneList.map((l) => '<option value="' + esc(l) + '">').join('')}</datalist></div>
      <div class="field"><label>负责人 / 岗位</label>
        <input id="edOwner" value="${esc(n.owner_role || '')}" placeholder="如：采购计划员"></div>
    </div>
    <div class="row3">
      <div class="field"><label>作业时间（分钟）</label>
        <input id="edDur" type="number" min="0" step="1" value="${n.duration_minutes}"></div>
      <div class="field"><label>等待 / 排队（分钟）</label>
        <input id="edWait" type="number" min="0" step="1" value="${n.wait_minutes}"></div>
      <div class="field"><label>单次执行成本（元）</label>
        <input id="edCost" type="number" min="0" step="0.1" value="${n.cost}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>返工率（0–1）</label>
        <input id="edRework" type="number" min="0" max="1" step="0.05" value="${n.rework_rate}">
        <div class="hint">>0.1 会触发返工损失建议</div></div>
      <div class="field"><label>审批层级数</label>
        <input id="edLevels" type="number" min="0" max="10" step="1" value="${n.approval_levels}">
        <div class="hint">累计 >3 层会触发决策下沉建议</div></div>
      <div class="field"><label>是否增值活动</label>
        <select id="edVa">
          <option value="true"${n.is_value_added ? ' selected' : ''}>增值（VA）</option>
          <option value="false"${!n.is_value_added ? ' selected' : ''}>非增值（NVA）</option>
        </select></div>
    </div>
    ${executionBlock}
    <div class="note">节点的「等待时间」是周期效率的主要杀手。真实场景下把它按现场实测填进去，
      右侧测算会立刻反映出来。</div>`,
    `<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"
       onclick="deleteNode('${nodeKey}')">删除节点</button>
     <button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveNode('${nodeKey}')">保存节点</button>`);
}

async function saveNodeAssignment(nodeKey) {
  const pid = state.designer.processId;
  const numOrNull = (id) => {
    const raw = document.getElementById(id).value.trim();
    if (raw === '') return null;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0 || value > 8760) {
      throw new Error('时限应为 0–8760 小时');
    }
    return value;
  };
  try {
    const role = document.getElementById('edRole').value || null;
    const org = document.getElementById('edOrg').value;
    const assignee = document.getElementById('edAssignee').value;
    const escUser = document.getElementById('edEscUser').value;
    await PUT('/execution/assignments', {
      process_id: pid,
      node_key: nodeKey,
      role,
      org_unit_id: org ? Number(org) : null,
      default_assignee_user_id: assignee ? Number(assignee) : null,
      due_hours: numOrNull('edDue'),
      escalation_hours: numOrNull('edEscHours'),
      escalation_user_id: escUser ? Number(escUser) : null,
    });
    toast('节点执行配置已保存');
  } catch (e) {
    toast(e.message, true);
  }
}

function saveNode(nodeKey) {
  const n = state.designer.model.nodes.find((x) => x.node_key === nodeKey);
  if (!n) return;
  const g = (id) => document.getElementById(id).value;
  pushHistory();
  n.name = g('edName').trim() || n.name;
  n.node_type = g('edType');
  n.lane = g('edLane').trim() || n.lane;
  n.owner_role = g('edOwner').trim() || null;
  n.duration_minutes = Number(g('edDur') || 0);
  n.wait_minutes = Number(g('edWait') || 0);
  n.cost = Number(g('edCost') || 0);
  n.rework_rate = Number(g('edRework') || 0);
  n.approval_levels = Number(g('edLevels') || 0);
  n.is_value_added = g('edVa') === 'true';
  closeModal();
  persistDesign('节点已保存，指标已重算');
}

function deleteNode(nodeKey) {
  const st = state.designer;
  pushHistory();
  st.model.nodes = st.model.nodes.filter((x) => x.node_key !== nodeKey);
  // 连线引用已删节点会导致后端校验失败，这里一并清掉
  st.model.edges = st.model.edges.filter((e) => e.source_key !== nodeKey && e.target_key !== nodeKey);
  closeModal();
  persistDesign('节点已删除');
}

function addNode(lane) {
  addNodeAtCenter('TASK', lane, '新活动');
}

function addDesignerNode(laneIdx) {
  addNode((state.designer.lanes || [])[laneIdx]);
}

function addLaneNode() {
  addLane();
}


export {
  addDesignerNode, addLane, addLaneNode, addNode, addNodeAtCenter, cloneModel,
  deleteEdge, deleteNode, diffVersion, editNode, exportBpmn, fitDesigner, importBpmn,
  openDesigner, openEdgeEditor, openNodeEditor, openVersionHistory, paintDesigner,
  paintMetrics, paintSuggestions, persistDesign, publishDesign, reanalyze,
  redoDesigner, rejectReview, reloadDesign, renderDesigner, rollbackVersion,
  saveEdge, saveNode, saveNodeAssignment, setDesignerTab, submitReview, switchProcess,
  undoDesigner,
};
