/* 视图：designer */
import { esc, num, dur, dtShort, emptyRow, NODE_LABEL, NODE_CLASS } from '../core/format.js';
import { toast, openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { metricHelp } from '../core/metrics.js';
import { API_BASE, GET, PATCH, POST, PUT, getToken } from '../core/api.js';
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
  if (!st.mode) st.mode = 'bpmn';
  normalizeLayout(st);

  const tab = st.tab || 'model';
  const tabBar = `
    <div class="seg">
      <button class="${tab === 'model' ? 'on' : ''}" onclick="setDesignerTab('model')">流程模型</button>
      <button class="${tab === 'analysis' ? 'on' : ''}" onclick="setDesignerTab('analysis')">
        指标与建议${st.analysis ? ' · ' + st.analysis.suggestions.length : ''}</button>
    </div>`;

  const simplePane = `
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

  const bpmnPane = `
    <div class="card designer-card" id="bpmnCard">
      <div class="mb designer-toolbar bpmn-toolbar">
        <div class="gap bpmn-toolbar-left">
          <span class="tiny">专业 BPMN 2.0 画布（bpmn-js）</span>
          <button class="btn-sm" onclick="runBpmnLint()">运行校验</button>
          <button class="btn-sm" onclick="autoLayoutBpmn()">自动布局</button>
          <button class="btn-sm" onclick="toggleBpmnFullscreen()">全屏</button>
          <button class="btn-sm" id="bpmnPropsToggle"
            onclick="toggleBpmnSidebar('props')">属性</button>
          <button class="btn-sm bpmn-lint-toggle" id="bpmnLintToggle"
            onclick="toggleBpmnSidebar('lint')">校验问题</button>
          <span class="tiny" id="bpmnSaveState">${
            model.status_label ? esc(model.status_label) + ' · v' + (model.draft_version || model.version)
              : '编辑后自动保存草稿'}</span>
        </div>
        <button class="btn-sm bpmn-fit-btn" onclick="fitBpmnViewport()">适应画布</button>
        <div class="tiny bpmn-toolbar-hint">单击选中 · 双击改名 · 点「属性」查看/编辑指标与执行配置</div>
      </div>
      <div id="bpmnCanvas" class="bpmn-canvas${editable ? '' : ' readonly'}"></div>
      <div id="bpmnSidebar" class="bpmn-drawer" aria-hidden="true">
        <div class="bpmn-drawer-head">
          <div class="seg bpmn-drawer-tabs">
            <button id="bpmnTabProps" class="on"
              onclick="showBpmnSidebarTab('props')">属性</button>
            <button id="bpmnTabLint" onclick="showBpmnSidebarTab('lint')">校验</button>
          </div>
          <button class="btn-sm" onclick="closeBpmnSidebar()">收起</button>
        </div>
        <div class="bpmn-drawer-body">
          <div id="bpmnPropsPanel" class="bpmn-drawer-pane">
            <div class="tiny muted">选中一个元素查看/编辑 PMS 指标与执行配置</div>
          </div>
          <div id="bpmnLintPanel" class="bpmn-drawer-pane hide">
            <div id="bpmnLint" class="bpmn-lint"></div>
          </div>
        </div>
      </div>
      <div class="note" style="margin-top:8px">执行引擎只支持串行流程：调色板与「更改元素」菜单已隐藏
        并行网关、子流程和边界事件。从外部导入包含这些构造的 BPMN 文件时，保存仍会被拒绝并给出提示。</div>
      ${validationHtml(st.model)}
    </div>`;

  const modelPane = st.mode === 'bpmn' ? bpmnPane : simplePane;

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
    <div class="card page-head designer-head">
      <div class="designer-head-top">
        <div class="designer-head-main">
          <div class="designer-head-title">
            <h2>流程设计器<span class="module-badge">建模与测算</span> · ${esc(model.process_name || '')}
              ${statusBadge}
              <span class="tiny">运行时版本 ${
                model.published_version ? 'v' + model.published_version : '尚未发布'}</span></h2>
          </div>
          ${tabBar}
        </div>
        <div class="designer-head-primary">
          <select class="sel sel-sm" onchange="switchProcess(this.value)">${opts}</select>
          ${publishable
            ? '<button class="btn-sm btn-p" onclick="publishDesign()">发布到运行时</button>' : ''}
          <button class="btn-sm btn-p" onclick="reanalyze()">重新测算</button>
        </div>
      </div>
      <div class="designer-head-bar">
        <div class="designer-head-actions">
          ${editable
            ? `<button class="btn-sm btn-g" onclick="toggleDesignerMode()">${
              st.mode === 'bpmn' ? '简洁画布' : '专业 BPMN 画布'}</button>` : ''}
          <button class="btn-sm btn-g" onclick="openVersionHistory()">版本历史</button>
          ${model.status === 'DRAFT' && editable
            ? '<button class="btn-sm btn-g" onclick="submitReview()">提交评审</button>' : ''}
          ${model.status === 'IN_REVIEW' && canManage()
            ? '<button class="btn-sm btn-g" onclick="rejectReview()">驳回</button>' : ''}
          <button class="btn-sm btn-g" onclick="exportBpmn()">导出 BPMN</button>
          ${editable ? '<button class="btn-sm btn-g" onclick="importBpmn()">导入 BPMN</button>' : ''}
          ${inReview
            ? '<span class="tiny">评审中，暂不可编辑</span>'
            : editable
              ? '<button class="btn-sm btn-g" onclick="addLaneNode()">+ 添加泳道节点</button>'
              : '<span class="tiny">只读（你不是这条流程的 Owner）</span>'}
          <a class="link-btn link-btn-sm" onclick="go('execution')">去流程执行 →</a>
        </div>
      </div>
    </div>
    ${tab === 'analysis' ? analysisPane : modelPane}`;
  if (tab !== 'analysis') {
    if (st.mode === 'bpmn') mountBpmnEditor();
    else renderCanvas();
  }
}

/* -------------------------------------------------- 画布 */

const DW = { laneH: 140, nodeW: 170, nodeH: 60, x0: 120, step: 200, top: 40 };

const EMPTY_BPMN_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" name="开始"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="180" y="160" width="36" height="36"/>
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;

function destroyBpmnModeler() {
  const st = state.designer;
  if (st.bpmnSaveTimer) clearTimeout(st.bpmnSaveTimer);
  st.bpmnSaveTimer = null;
  if (st.bpmnFullscreenHandler) {
    document.removeEventListener('keydown', st.bpmnFullscreenHandler);
    st.bpmnFullscreenHandler = null;
  }
  const card = document.getElementById('bpmnCard');
  if (card) card.classList.remove('fullscreen');
  if (st.bpmnModeler) {
    try { st.bpmnModeler.destroy(); } catch (e) { /* 已销毁 */ }
    st.bpmnModeler = null;
  }
}

function toggleDesignerMode() {
  const st = state.designer;
  destroyBpmnModeler();
  st.tab = 'model';
  st.mode = st.mode === 'bpmn' ? 'simple' : 'bpmn';
  RENDERERS.designer();
}

function fitBpmnViewport() {
  const modeler = state.designer.bpmnModeler;
  const container = document.getElementById('bpmnCanvas');
  if (!modeler) return;
  const canvas = modeler.get('canvas');
  if (!container) {
    canvas.zoom('fit-viewport');
    return;
  }
  const inner = canvas.viewbox().inner;
  const rect = container.getBoundingClientRect();
  if (!inner || !inner.width || !inner.height || !rect.width || !rect.height) {
    canvas.zoom('fit-viewport');
    return;
  }
  // 调色板和右侧属性栏都浮在画布上：适应画布时要给它们留出空间
  const PAD = 24;
  const palette = container.querySelector('.djs-palette');
  const paletteRect = palette ? palette.getBoundingClientRect() : null;
  const sidebar = document.getElementById('bpmnSidebar');
  const sidebarOpen = sidebar && sidebar.classList.contains('open');
  // 侧栏有 200ms 滑入动画，此时 getBoundingClientRect().left 还在移动；
  // 用布局宽度计算最终占位，避免动画期间适应画布算少。
  const sidebarWidth = sidebarOpen ? Math.max(sidebar.offsetWidth, 0) : 0;
  const leftInset = (paletteRect ? paletteRect.right - rect.left : 48) + PAD;
  const rightInset = (sidebarWidth ? sidebarWidth + 12 : 0) + PAD;
  const availW = Math.max(160, rect.width - leftInset - rightInset);
  const availH = Math.max(160, rect.height - PAD * 2);
  const scale = Math.min(1, availW / inner.width, availH / inner.height);
  if (!Number.isFinite(scale) || scale <= 0) {
    canvas.zoom('fit-viewport');
    return;
  }
  const offsetX = (leftInset - rightInset) / 2;
  const viewWidth = rect.width / scale;
  const viewHeight = rect.height / scale;
  canvas.viewbox({
    x: inner.x + inner.width / 2 - viewWidth / 2 - offsetX / scale,
    y: inner.y + inner.height / 2 - viewHeight / 2,
    width: viewWidth,
    height: viewHeight,
  });
}

function setBpmnSaveState(text) {
  const el = document.getElementById('bpmnSaveState');
  if (el) el.textContent = text;
}

async function fetchBpmnXml() {
  const pid = state.designer.processId;
  const model = await GET('/processes/' + pid + '/design');
  if (!(model.nodes || []).length) return EMPTY_BPMN_XML;
  const res = await fetch(API_BASE + '/processes/' + pid + '/bpmn', {
    headers: { Authorization: 'Bearer ' + getToken() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || ('BPMN 加载失败（' + res.status + '）'));
  }
  return await res.text();
}

function scheduleBpmnSave() {
  const st = state.designer;
  if (st.bpmnImporting || !st.bpmnModeler) return;
  setBpmnSaveState('有未保存修改…');
  if (st.bpmnSaveTimer) clearTimeout(st.bpmnSaveTimer);
  st.bpmnSaveTimer = setTimeout(saveBpmnNow, 900);
}

async function saveBpmnNow() {
  const st = state.designer;
  const modeler = st.bpmnModeler;
  if (!modeler) return;
  try {
    const { xml } = await modeler.saveXML({ format: true });
    const response = await POST('/processes/' + st.processId + '/bpmn', {
      xml,
      expected_version: st.model ? st.model.version : null,
    });
    st.model = response;
    st.savedModel = cloneModel(response);
    st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
    setBpmnSaveState('已保存 · v' + (response.draft_version || response.version));
    renderBpmnSelection(st.bpmnSelection || []);
    runBpmnLint();
    return true;
  } catch (e) {
    setBpmnSaveState('保存失败：' + e.message);
    toast(e.message, true);
    return false;
  }
}

let bpmnJsPromise = null;
let bpmnLintPromise = null;
let bpmnLayoutPromise = null;

function loadScriptOnce(src, getGlobal) {
  if (getGlobal()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error('资源加载失败：' + src));
    document.head.appendChild(script);
  });
}

function loadBpmnJs() {
  if (window.BpmnJS) return Promise.resolve();
  if (!bpmnJsPromise) {
    bpmnJsPromise = loadScriptOnce(
      '/static/vendor/bpmn-js/bpmn-modeler.js?v=18.31.1', () => window.BpmnJS);
  }
  return bpmnJsPromise;
}

function loadBpmnLint() {
  if (window.BpmnLint) return Promise.resolve();
  if (!bpmnLintPromise) {
    bpmnLintPromise = loadScriptOnce(
      '/static/vendor/bpmn-js/bpmn-lint.js?v=2', () => window.BpmnLint);
  }
  return bpmnLintPromise;
}

function loadBpmnAutoLayout() {
  if (window.BpmnAutoLayout) return Promise.resolve();
  if (!bpmnLayoutPromise) {
    bpmnLayoutPromise = loadScriptOnce(
      '/static/vendor/bpmn-js/bpmn-auto-layout.js?v=1.3.0', () => window.BpmnAutoLayout);
  }
  return bpmnLayoutPromise;
}

/* 执行引擎只支持串行流程：这些构造一旦画出，保存会被后端拒绝。
 * 在调色板、上下文菜单和「更改元素」菜单里直接隐藏，避免用户白画一遍。 */
const UNSUPPORTED_REPLACE_FRAGMENTS = [
  'parallel-gateway', 'complex-gateway', 'event-based-gateway',
  'transaction', 'subprocess', 'boundary',
];

function isUnsupportedReplaceEntry(key) {
  return key.startsWith('replace-with-')
    && UNSUPPORTED_REPLACE_FRAGMENTS.some((fragment) => key.includes(fragment));
}

function PmsPaletteProvider(palette, create, elementFactory) {
  this._create = create;
  this._elementFactory = elementFactory;
  palette.registerProvider(500, this);
}
PmsPaletteProvider.$inject = ['palette', 'create', 'elementFactory'];
PmsPaletteProvider.prototype.getPaletteEntries = function () {
  const create = this._create;
  const elementFactory = this._elementFactory;
  const startWait = (event) => {
    create.start(event, elementFactory.createShape({ type: 'bpmn:IntermediateCatchEvent' }));
  };
  // 返回函数而不是对象：在默认调色板（优先级 1000）之后执行，才能删掉既有条目
  return function (entries) {
    delete entries['create.subprocess-expanded'];
    // 默认条目会创建抛出事件；拖到活动上还会变成执行引擎不支持的边界事件
    delete entries['create.intermediate-event'];
    entries['create.pms-wait-event'] = {
      group: 'event',
      className: 'bpmn-icon-intermediate-event-none pms-wait-entry',
      title: '创建等待事件（中间捕获事件，不是结束事件）',
      action: { dragstart: startWait, click: startWait },
    };
    // 评审/只读时保留调色板可见，但禁止创建元素；导航工具仍可用
    if (!state.designer.editable) {
      Object.keys(entries).forEach((key) => {
        if (key.startsWith('create.') && entries[key]) {
          entries[key] = { ...entries[key], action: {} };
        }
      });
    }
    return entries;
  };
};

function PmsContextPadProvider(contextPad) {
  contextPad.registerProvider(500, this);
}
PmsContextPadProvider.$inject = ['contextPad'];
PmsContextPadProvider.prototype.getContextPadEntries = function () {
  return function (entries) {
    delete entries['append.intermediate-event'];
    return entries;
  };
};

function PmsReplaceMenuProvider(popupMenu) {
  popupMenu.registerProvider('bpmn-replace', 500, this);
}
PmsReplaceMenuProvider.$inject = ['popupMenu'];
PmsReplaceMenuProvider.prototype.getPopupMenuEntries = function () {
  return function (entries) {
    Object.keys(entries).forEach((key) => {
      if (isUnsupportedReplaceEntry(key)) delete entries[key];
    });
    return entries;
  };
};

const PMS_BPMN_GUARDS = {
  __init__: ['pmsPaletteProvider', 'pmsContextPadProvider', 'pmsReplaceMenuProvider'],
  pmsPaletteProvider: ['type', PmsPaletteProvider],
  pmsContextPadProvider: ['type', PmsContextPadProvider],
  pmsReplaceMenuProvider: ['type', PmsReplaceMenuProvider],
};

async function mountBpmnEditor() {
  const st = state.designer;
  const container = document.getElementById('bpmnCanvas');
  if (!container) return;
  try {
    await loadBpmnJs();
  } catch (e) {
    container.innerHTML = `<div class="errbar">${esc(e.message)}</div>`;
    return;
  }
  if (!window.BpmnJS) {
    container.innerHTML = '<div class="errbar">bpmn-js 资源未加载</div>';
    return;
  }
  destroyBpmnModeler();
  const modeler = new window.BpmnJS({ container, additionalModules: [PMS_BPMN_GUARDS] });
  st.bpmnModeler = modeler;
  window.__bpmnSpike = { modeler, lint: window.BpmnLint };
  st.bpmnSelection = [];
  st.bpmnImporting = true;
  modeler.on('selection.changed', (event) => {
    st.bpmnSelection = event.newSelection || [];
    // 只更新属性内容，不自动开关侧栏；侧栏由工具栏「属性」或「收起」控制
    renderBpmnSelection(st.bpmnSelection);
  });
  // 画布内双击改名完成后，同步属性栏里的名称字段
  modeler.on('directEditing.complete', () => {
    renderBpmnSelection(st.bpmnSelection || []);
  });
  modeler.on('commandStack.changed', scheduleBpmnSave);
  try {
    const xml = await fetchBpmnXml();
    await modeler.importXML(xml);
    const paletteToggle = container.querySelector('.djs-palette-toggle');
    if (paletteToggle) paletteToggle.title = '展开/收起工具';
    fitBpmnViewport();
    st.bpmnImporting = false;
    setBpmnSaveState('草稿 · v' + (st.model.draft_version || st.model.version));
    runBpmnLint();
  } catch (e) {
    st.bpmnImporting = false;
    container.innerHTML = `<div class="errbar">BPMN 加载失败：${esc(e.message)}</div>`;
  }
}

function roleOptionHtml(roles, selected) {
  return roles.map((role) =>
    `<option value="${esc(role.value)}"${selected === role.value ? ' selected' : ''}>${
      esc(role.label)}</option>`).join('');
}

function orgOptionHtml(orgs, selected) {
  return orgs.map((org) =>
    `<option value="${org.id}"${selected === org.id ? ' selected' : ''}>${
      esc(org.name)}</option>`).join('');
}

function userOptionHtml(users, selected) {
  return users.map((user) =>
    `<option value="${user.id}"${selected === user.id ? ' selected' : ''}>${
      esc(user.display_name)} · ${esc(user.role_label || user.role)}</option>`).join('');
}

async function fetchAssignmentContext(processId) {
  const [assignments, users, orgs, meta] = await Promise.all([
    GET('/execution/assignments?process_id=' + processId),
    GET('/execution/assignees'),
    GET('/org-units'),
    GET('/auth/meta'),
  ]);
  return {
    processId,
    assignments: new Map(assignments.map((item) => [item.node_key, item])),
    users,
    orgs,
    roles: meta.roles || [],
  };
}

/** 分派配置是流程级数据：选中节点时按需加载并缓存，避免每次改选都打四个接口。 */
function assignmentContext(processId) {
  const st = state.designer;
  if (st.assignmentCtx && st.assignmentCtx.processId === processId) {
    return Promise.resolve(st.assignmentCtx);
  }
  if (st.assignmentPending && st.assignmentPending.processId === processId) {
    return st.assignmentPending.promise;
  }
  const clearPending = () => {
    if (st.assignmentPending && st.assignmentPending.processId === processId) {
      st.assignmentPending = null;
    }
  };
  const promise = fetchAssignmentContext(processId)
    .then((ctx) => {
      clearPending();
      // 加载期间可能已经切到别的流程，别把旧流程的配置写进缓存
      if (state.designer.processId === processId) st.assignmentCtx = ctx;
      return ctx;
    })
    .catch((error) => {
      clearPending();
      throw error;
    });
  st.assignmentPending = { processId, promise };
  return promise;
}

function renderBpmnSelection(selection) {
  const panel = document.getElementById('bpmnPropsPanel');
  if (!panel) return;
  const element = (selection || [])[0];
  const bo = element && element.businessObject;
  if (!bo) {
    panel.innerHTML = '<div class="tiny muted">选中一个元素查看/编辑 PMS 指标与执行配置</div>';
    return;
  }
  const st = state.designer;
  const node = ((st.model || {}).nodes || [])
    .find((item) => item.node_key === bo.id);
  const type = String(bo.$type || '').replace('bpmn:', '');
  const editable = !!st.editable && !!node;
  // 分派配置的写接口要求 MANAGER+，权限比 PMS 指标更窄
  const canConfigExec = editable && canManage();
  const ro = editable ? '' : ' readonly';
  panel.innerHTML = `
    <div class="between mb">
      <b>${esc(bo.name || bo.id || '未命名元素')}</b>
      <span class="tag t-blu">${esc(type)}</span>
    </div>
    <div class="field"><label>名称</label>
      <input id="bpName" value="${esc(bo.name || '')}" placeholder="未命名"${
        st.editable ? '' : ' readonly'}></div>
    ${st.editable
      ? `<div class="between mb"><span class="tiny muted">双击画布元素可直接改名；这里也可以修改同一名称</span>
          <button class="btn-sm" onclick="saveBpmnName('${esc(bo.id)}')">保存名称</button></div>`
      : ''}
    ${node ? `
      <div class="grid g3">
        <div class="field"><label>作业时间（分钟）</label>
          <input id="bpDur" type="number" min="0" value="${node.duration_minutes}"${ro}></div>
        <div class="field"><label>等待时间（分钟）</label>
          <input id="bpWait" type="number" min="0" value="${node.wait_minutes}"${ro}></div>
        <div class="field"><label>单次成本（元）</label>
          <input id="bpCost" type="number" min="0" step="0.1" value="${node.cost}"${ro}></div>
        <div class="field"><label>返工率（0–1）</label>
          <input id="bpRework" type="number" min="0" max="1" step="0.05" value="${node.rework_rate}"${ro}></div>
        <div class="field"><label>审批层级</label>
          <input id="bpApproval" type="number" min="0" max="10" value="${node.approval_levels}"${ro}></div>
        <div class="field"><label>增值活动</label>
          <select id="bpVa"${editable ? '' : ' disabled'}>
            <option value="true"${node.is_value_added ? ' selected' : ''}>是</option>
            <option value="false"${!node.is_value_added ? ' selected' : ''}>否</option>
          </select></div>
      </div>
      ${editable
        ? `<div class="between mt"><div class="hint">指标保存后不影响图形；发布后才影响运行时。</div>
            <button class="btn-sm btn-p" onclick="saveBpmnMetrics('${esc(node.node_key)}')">保存指标</button></div>`
        : '<div class="hint">只读：需要 Owner 或流程管理科权限才能修改。</div>'}`
      : '<div class="tiny muted">该元素没有 PMS 测算数据</div>'}
    ${canConfigExec
      ? '<div id="bpmnAssignSlot" class="bpmn-assign-slot">'
        + '<div class="tiny muted">正在加载执行配置…</div></div>'
      : ''}
    <div class="hint">BPMN 图形修改会自动保存草稿；PMS 指标与执行配置各自单独保存。</div>`;
  if (canConfigExec) renderBpmnAssignment(bo.id);
}

async function renderBpmnAssignment(nodeKey) {
  const st = state.designer;
  const processId = st.processId;
  const slot = document.getElementById('bpmnAssignSlot');
  if (!slot) return;
  // 加载或保存期间用户可能改选了别的元素：只更新仍然属于当前选中的槽位
  const stillSelected = () => {
    const current = (st.bpmnSelection || [])[0];
    const currentId = current && current.businessObject ? current.businessObject.id : null;
    return slot.isConnected && currentId === nodeKey && st.processId === processId;
  };
  let ctx;
  try {
    ctx = await assignmentContext(processId);
  } catch (e) {
    if (stillSelected()) {
      slot.innerHTML = `<div class="note">执行配置加载失败：${esc(e.message)}</div>`;
    }
    return;
  }
  if (!stillSelected()) return;
  const assignment = ctx.assignments.get(nodeKey) || {};
  slot.innerHTML = `
    <div class="designer-exec-config bpmn-assign">
      <div class="between mb"><h3 style="margin:0">执行配置</h3>
        <button class="btn-sm btn-p" onclick="saveBpmnAssignment('${esc(nodeKey)}')">
          保存执行配置</button></div>
      <div class="desc" style="margin:0 0 8px">候选角色 / 组织 / 默认处理人 / 节点时限 / 升级；
        只影响发布后的新实例</div>
      <div class="row2">
        <div class="field"><label>候选角色</label>
          <select id="baRole"><option value="">不限</option>${
            roleOptionHtml(ctx.roles, assignment.role)}</select></div>
        <div class="field"><label>限定组织</label>
          <select id="baOrg"><option value="">不限</option>${
            orgOptionHtml(ctx.orgs, assignment.org_unit_id)}</select></div>
      </div>
      <div class="row2">
        <div class="field"><label>默认处理人</label>
          <select id="baAssignee"><option value="">公共队列</option>${
            userOptionHtml(ctx.users, assignment.default_assignee_user_id)}</select></div>
        <div class="field"><label>节点时限（小时）</label>
          <input id="baDue" type="number" min="0" max="8760"
            value="${assignment.due_hours ?? ''}" placeholder="跟随流程"></div>
      </div>
      <div class="row2">
        <div class="field"><label>升级时限（小时）</label>
          <input id="baEscHours" type="number" min="0" max="8760"
            value="${assignment.escalation_hours ?? ''}" placeholder="跟随流程"></div>
        <div class="field"><label>升级处理人</label>
          <select id="baEscUser"><option value="">跟随流程</option>${
            userOptionHtml(ctx.users, assignment.escalation_user_id)}</select></div>
      </div>
    </div>`;
}

async function saveBpmnName(elementId) {
  const st = state.designer;
  const modeler = st.bpmnModeler;
  const input = document.getElementById('bpName');
  if (!modeler || !input) return;
  const element = modeler.get('elementRegistry').get(elementId);
  if (!element) return;
  try {
    const name = input.value.trim();
    modeler.get('modeling').updateProperties(element, { name: name || undefined });
    // updateProperties 会触发防抖保存；这里立即保存并清掉定时器，避免重复提交
    if (st.bpmnSaveTimer) {
      clearTimeout(st.bpmnSaveTimer);
      st.bpmnSaveTimer = null;
    }
    const saved = await saveBpmnNow();
    if (saved) toast('名称已更新');
    renderBpmnSelection(st.bpmnSelection || []);
  } catch (e) {
    toast(e.message, true);
  }
}

async function saveBpmnMetrics(nodeKey) {
  const st = state.designer;
  if (!st.model.nodes.some((node) => node.node_key === nodeKey)) {
    toast('画布还在保存，请稍后再试', true);
    return;
  }
  const value = (id) => Number(document.getElementById(id).value);
  try {
    const response = await PATCH(
      '/processes/' + st.processId + '/design/nodes/' + nodeKey,
      {
        duration_minutes: value('bpDur'),
        wait_minutes: value('bpWait'),
        cost: value('bpCost'),
        rework_rate: value('bpRework'),
        approval_levels: value('bpApproval'),
        is_value_added: document.getElementById('bpVa').value === 'true',
        expected_version: st.model.version,
      },
    );
    st.model = response;
    st.savedModel = cloneModel(response);
    st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
    setBpmnSaveState('指标已保存 · v' + (response.draft_version || response.version));
    renderBpmnSelection(st.bpmnSelection || []);
    toast('节点指标已保存');
  } catch (e) {
    toast(e.message, true);
  }
}

function hydrateLintConnections(container) {
  const elements = (container && container.flowElements) || [];
  elements.forEach((element) => {
    if (element.$type !== 'bpmn:SequenceFlow') return;
    const source = element.sourceRef;
    const target = element.targetRef;
    if (source) {
      source.outgoing = source.outgoing || [];
      if (!source.outgoing.includes(element)) source.outgoing.push(element);
    }
    if (target) {
      target.incoming = target.incoming || [];
      if (!target.incoming.includes(element)) target.incoming.push(element);
    }
  });
  elements.forEach((element) => {
    if (element.flowElements) hydrateLintConnections(element);
  });
}

async function runBpmnLint() {
  const st = state.designer;
  const modeler = st.bpmnModeler;
  if (!modeler) return;
  try {
    await loadBpmnLint();
    const definitions = modeler.getDefinitions();
    (definitions.rootElements || []).forEach((root) => {
      if (root.$type === 'bpmn:Process') hydrateLintConnections(root);
    });
    const grouped = await window.BpmnLint.lint(definitions);
    const registry = modeler.get('elementRegistry');
    const issues = [];
    Object.entries(grouped || {}).forEach(([rule, list]) => {
      (list || []).forEach((issue) => {
        const element = issue.id ? registry.get(issue.id) : null;
        issues.push({
          ...issue,
          rule,
          meta: { ...(issue.meta || {}), element },
        });
      });
    });
    // 错误优先，方便先处理会阻塞发布的问题；同级别保持规则原始顺序
    issues.sort((a, b) => (a.category === 'error' ? 0 : 1) - (b.category === 'error' ? 0 : 1));
    st.bpmnLint = issues;
    renderBpmnLint();
  } catch (e) {
    toast(e.message, true);
  }
}

/* bpmnlint 的规则名和英文消息对业务用户不友好，这里逐条翻译成「问题 + 建议」。
 * 未收录的规则保留原始消息，但仍以中文标题呈现，避免界面突然冒出英文。 */
const BPMN_LINT_HELP = {
  'start-event-required': {
    title: '缺少开始节点',
    detail: '整个流程没有开始事件。运行时只能按「唯一入口」推断起点，流程一复杂就可能推错。',
    action: '从调色板添加开始事件，并把第一条活动连到它。',
  },
  'end-event-required': {
    title: '缺少结束节点',
    detail: '整个流程没有结束事件。注意：等待事件（中间捕获/抛出事件）不算结束事件。',
    action: '从调色板添加粗圆圈的结束事件，并把最终活动连到它。',
  },
  'no-implicit-start': {
    title: '节点被当作隐式起点',
    detail: '这个节点没有上游连线，运行时会被当成流程入口。',
    action: '如果它确实是起点，建议改成开始事件；否则补上上游连线。',
  },
  'no-implicit-end': {
    title: '节点被当作隐式终点',
    detail: '这个节点没有下游连线，执行到这里实例会直接结束。若是等待事件，它不会起到结束事件的作用。',
    action: '如果流程还要继续，补下游连线；如果到此结束，接一个结束事件。',
  },
  'fake-join': {
    title: '多路汇入没有网关',
    detail: '有多条上游连线直接汇入这个节点，中间没有汇合网关，执行语义不明确。',
    action: '在汇入处加一个排他网关，让分支先汇合再进入该节点。',
  },
  'no-implicit-split': {
    title: '节点被当作隐式分支',
    detail: '这个节点有多条下游连线，但没有用网关明确分支。',
    action: '改用判断（排他）网关分支，执行引擎才能按条件路由。',
  },
  'superfluous-label': {
    title: '连线标签不会生效',
    detail: '这条连线填了标签，但起点不是判断或审批节点，标签不会参与运行时路由。',
    action: '删除标签；如果要按条件走不同分支，请把起点改为判断节点并配置条件。',
  },
  'conditional-flows': {
    title: '分支缺少条件',
    detail: '从判断节点分出的连线没有配置条件表达式。',
    action: '为每条分支补上条件，并设置一条默认分支兜底。',
  },
  'no-disconnected': {
    title: '元素没有接入流程',
    detail: '这个元素与主流程没有连线，运行时永远不会执行。',
    action: '用连线把它接入流程，或删除它。',
  },
  'label-required': {
    title: '元素缺少名称',
    detail: '这个元素还没有名称，任务列表和运行记录里无法辨认。',
    action: '双击元素补上名称。',
  },
  'no-duplicate-sequence-flows': {
    title: '存在重复连线',
    detail: '同一对节点之间有多条完全相同的连线。',
    action: '删除重复的连线，只保留一条。',
  },
  'superfluous-gateway': {
    title: '网关是多余的',
    detail: '这个网关只有一个入边和一个出边，没有起到分支或汇合作用。',
    action: '删除网关，直接把前后两个节点连起来。',
  },
  'no-gateway-join-fork': {
    title: '网关同时分流和汇合',
    detail: '同一个网关既做分支又做汇合，执行语义容易混淆。',
    action: '拆成两个网关：前面负责分流，后面负责汇合。',
  },
  'single-blank-start-event': {
    title: '开始事件不唯一',
    detail: '流程里有多个无类型开始事件，运行时无法确定从哪个开始。',
    action: '只保留一个无类型开始事件；其余改成带触发类型的开始事件或删除。',
  },
  'single-event-definition': {
    title: '事件定义重复',
    detail: '同一个事件配置了多个事件定义（例如同时是消息和定时），运行时无法判断用哪个。',
    action: '只保留一个事件定义。',
  },
  'sub-process-blank-start-event': {
    title: '子流程开始事件不规范',
    detail: '子流程里有不带事件定义的开始事件。',
    action: '为子流程的开始事件补上事件定义，或改用普通开始事件。',
  },
  'event-sub-process-typed-start-event': {
    title: '事件子流程缺少事件定义',
    detail: '事件子流程的开始事件需要消息、定时或信号等事件定义。',
    action: '给开始事件补上对应的事件定义。',
  },
  'event-based-gateway': {
    title: '不支持事件网关',
    detail: '执行引擎只做串行流程，事件网关不在支持范围内。',
    action: '改用排他网关，或把等待改成中间捕获事件。',
  },
  'no-complex-gateway': {
    title: '不支持复杂网关',
    detail: '执行引擎只做串行流程，复杂网关不在支持范围内。',
    action: '改用排他网关。',
  },
  'no-inclusive-gateway': {
    title: '不推荐包容网关',
    detail: '包容网关的多路执行语义与当前单令牌执行引擎不一致。',
    action: '改用排他网关。',
  },
  'ad-hoc-sub-process': {
    title: '不支持 Ad-hoc 子流程',
    detail: '执行引擎不支持 Ad-hoc 子流程。',
    action: '删掉子流程，把内部活动展开到主流程。',
  },
  'link-event': {
    title: '链接事件缺少名称',
    detail: '链接事件没有填写链接名称，无法与配对的另一个链接事件对应。',
    action: '在属性里补上链接名称。',
  },
  'no-overlapping-elements': {
    title: '元素在画布上重叠',
    detail: '两个元素的位置重叠，容易看错连线关系。',
    action: '拖动分开，或使用「自动布局」重新排列。',
  },
  'superfluous-termination': {
    title: '终止事件是多余的',
    detail: '终止事件后面没有其他元素，终止语义没有实际作用。',
    action: '改成普通结束事件。',
  },
  'no-bpmndi': {
    title: '缺少图形信息',
    detail: '元素没有对应的 BPMN DI 坐标，画布上无法定位。',
    action: '在 bpmn-js 里重新保存一次，让图形信息补齐。',
  },
  'rule-error': {
    title: '校验规则执行失败',
    detail: '这条规则本身报错，通常是模型结构异常。',
    action: '保存后重试；仍然失败请反馈给流程管理科。',
  },
  global: {
    title: '使用了全局任务',
    detail: '全局任务不是可执行的流程节点。',
    action: '改成普通任务或删除。',
  },
};

function showBpmnSidebarTab(tab) {
  const sidebar = document.getElementById('bpmnSidebar');
  if (!sidebar) return;
  state.designer.bpmnSidebarTab = tab;
  sidebar.classList.add('open');
  sidebar.setAttribute('aria-hidden', 'false');
  const props = tab === 'props';
  const propsPanel = document.getElementById('bpmnPropsPanel');
  const lintPanel = document.getElementById('bpmnLintPanel');
  const propsTab = document.getElementById('bpmnTabProps');
  const lintTab = document.getElementById('bpmnTabLint');
  if (propsPanel) propsPanel.classList.toggle('hide', !props);
  if (lintPanel) lintPanel.classList.toggle('hide', props);
  if (propsTab) propsTab.classList.toggle('on', props);
  if (lintTab) lintTab.classList.toggle('on', !props);
}

function toggleBpmnSidebar(tab) {
  const sidebar = document.getElementById('bpmnSidebar');
  if (!sidebar) return;
  const open = sidebar.classList.contains('open');
  if (!open) {
    showBpmnSidebarTab(tab || state.designer.bpmnSidebarTab || 'props');
    return;
  }
  if (tab && tab !== state.designer.bpmnSidebarTab) {
    showBpmnSidebarTab(tab);
    return;
  }
  closeBpmnSidebar();
}

function closeBpmnSidebar() {
  const sidebar = document.getElementById('bpmnSidebar');
  if (!sidebar) return;
  sidebar.classList.remove('open');
  sidebar.setAttribute('aria-hidden', 'true');
}

function renderBpmnLint() {
  const box = document.getElementById('bpmnLint');
  if (!box) return;
  const issues = state.designer.bpmnLint || [];
  const errors = issues.filter((i) => i.category === 'error').length;
  const warns = issues.filter((i) => i.category !== 'error').length;
  const toggle = document.getElementById('bpmnLintToggle');
  if (toggle) {
    toggle.textContent = issues.length ? `校验问题 ${issues.length}` : '校验问题 无';
    toggle.classList.toggle('has-error', errors > 0);
    toggle.classList.toggle('has-warn', errors === 0 && warns > 0);
  }
  const summary = `<div class="between mb"><b>建模校验</b>
    <span class="tiny">${errors} 错误 · ${warns} 警告</span></div>`;
  if (!issues.length) {
    box.innerHTML = `${summary}<div class="tiny muted">bpmnlint 未发现问题</div>`;
    return;
  }
  box.innerHTML = `
    ${summary}
    ${issues.map((issue, index) => {
      const element = issue.meta && issue.meta.element;
      const bo = element && element.businessObject;
      const isProcess = bo && (bo.$type === 'bpmn:Process' || bo.$type === 'bpmn:Collaboration');
      const label = element && !isProcess ? ((bo && (bo.name || bo.id)) || element.id) : '整个流程';
      const category = issue.category === 'error' ? 'error' : 'warn';
      const help = BPMN_LINT_HELP[issue.rule];
      const title = help ? help.title : '建模规范提示';
      const detail = help ? help.detail : (issue.message || '');
      const raw = issue.rule + (issue.message ? '：' + issue.message : '');
      return `<div class="bpmn-lint-item ${category}" onclick="selectLintIssue(${index})"
          title="${esc(raw)}">
        <div class="bpmn-lint-head">
          <span class="tag ${category === 'error' ? 't-red' : 't-yel'}">${
            category === 'error' ? '错误' : '警告'}</span>
          <b>${esc(title)}</b>
          <span class="tiny muted">${esc(label)}</span>
        </div>
        <div class="bpmn-lint-detail">${esc(detail)}</div>
        ${help && help.action
          ? `<div class="bpmn-lint-action muted">建议：${esc(help.action)}</div>` : ''}
      </div>`;
    }).join('')}`;
}

function selectLintIssue(index) {
  const issue = (state.designer.bpmnLint || [])[index];
  const element = issue && issue.meta && issue.meta.element;
  if (!element) return;
  const modeler = state.designer.bpmnModeler;
  if (!modeler) return;
  modeler.get('selection').select(element);
  modeler.get('canvas').scrollToElement(element);
  // 跳到属性页签，方便直接修改刚定位到的节点
  showBpmnSidebarTab('props');
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
function orthogonalizePath(points) {
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

/** bpmn-moddle 不会从 sequenceFlow 反推 incoming/outgoing。
 *  缺少这两个引用时，bpmn-auto-layout 会把所有节点排成一列。 */
function ensureFlowRefs(xml) {
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

/** bpmn-auto-layout 只排 flowElements，会丢掉泳道 DI。
 *  这里保留它算出的横向顺序，按泳道重新分配纵向区域并补回泳道 DI 与连线折点。 */
function restoreLanes(xml) {
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

async function autoLayoutBpmn() {
  const modeler = state.designer.bpmnModeler;
  if (!modeler) return;
  if (!confirm('自动布局会重新排列节点并覆盖当前画布布局，确定继续？')) return;
  try {
    await loadBpmnAutoLayout();
    const { xml } = await modeler.saveXML({ format: true });
    const layouted = await window.BpmnAutoLayout.layoutProcess(ensureFlowRefs(xml));
    state.designer.bpmnImporting = true;
    await modeler.importXML(restoreLanes(layouted));
    state.designer.bpmnImporting = false;
    state.designer.bpmnSelection = [];
    renderBpmnSelection([]);
    fitBpmnViewport();
    const saved = await saveBpmnNow();
    if (saved) {
      await runBpmnLint();
      toast('已自动布局并保存');
    }
  } catch (e) {
    state.designer.bpmnImporting = false;
    toast(e.message, true);
  }
}

function toggleBpmnFullscreen() {
  const card = document.getElementById('bpmnCard');
  if (!card) return;
  const enter = !card.classList.contains('fullscreen');
  card.classList.toggle('fullscreen', enter);
  // 全屏优先保证画布高度：属性/校验侧栏默认收起，用工具栏按钮随时打开
  if (enter) closeBpmnSidebar();
  const resize = () => {
    const modeler = state.designer.bpmnModeler;
    const container = document.getElementById('bpmnCanvas');
    // 全屏切换的瞬间容器可能还没有布局尺寸：此时 fit-viewport 会算出非有限值
    if (!modeler || !container || container.clientWidth < 1 || container.clientHeight < 1) return;
    modeler.get('canvas').resized();
    fitBpmnViewport();
  };
  if (enter) {
    state.designer.bpmnFullscreenHandler = (event) => {
      if (event.key !== 'Escape') return;
      card.classList.remove('fullscreen');
      document.removeEventListener('keydown', state.designer.bpmnFullscreenHandler);
      state.designer.bpmnFullscreenHandler = null;
      setTimeout(resize, 60);
    };
    document.addEventListener('keydown', state.designer.bpmnFullscreenHandler);
  } else {
    if (state.designer.bpmnFullscreenHandler) {
      document.removeEventListener('keydown', state.designer.bpmnFullscreenHandler);
      state.designer.bpmnFullscreenHandler = null;
    }
  }
  setTimeout(resize, 60);
}

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
    if (state.designer.bpmnModeler) {
      const ok = await saveBpmnNow();
      if (!ok) return;
    }
    const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
      headers: { Authorization: 'Bearer ' + getToken() },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || ('导出失败（' + res.status + '）'));
    }
    const xml = await res.text();
    downloadBpmn(xml);
    toast('BPMN 已导出');
  } catch (e) {
    toast(e.message, true);
  }
}

function downloadBpmn(xml) {
  const blob = new Blob([xml], { type: 'application/xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = (state.designer.processCode || 'process') + '.bpmn';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
  state.designer.assignmentCtx = null;
  state.designer.assignmentPending = null;
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
    // 冲突重载可能带回别人的结构改动，分派配置也跟着重新拉取
    st.assignmentCtx = null;
    st.assignmentPending = null;
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
  let executionBlock = '';
  if (canManage()) {
    try {
      const ctx = await assignmentContext(pid);
      assignment = ctx.assignments.get(nodeKey) || {};
      const roleOpts = roleOptionHtml(ctx.roles, assignment.role);
      const orgOpts = orgOptionHtml(ctx.orgs, assignment.org_unit_id);
      const userOpts = userOptionHtml(ctx.users, assignment.default_assignee_user_id);
      const escUserOpts = userOptionHtml(ctx.users, assignment.escalation_user_id);
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

/** 从表单读取分派配置；bpmn 属性面板与节点弹窗共用，字段 id 由调用方传入。 */
function readAssignmentPayload(nodeKey, ids) {
  const value = (id) => document.getElementById(id).value;
  const numOrNull = (id) => {
    const raw = value(id).trim();
    if (raw === '') return null;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 8760) {
      throw new Error('时限应为 0–8760 小时');
    }
    return parsed;
  };
  const idOrNull = (id) => (value(id) ? Number(value(id)) : null);
  return {
    process_id: state.designer.processId,
    node_key: nodeKey,
    role: value(ids.role) || null,
    org_unit_id: idOrNull(ids.org),
    default_assignee_user_id: idOrNull(ids.assignee),
    due_hours: numOrNull(ids.due),
    escalation_hours: numOrNull(ids.escalationHours),
    escalation_user_id: idOrNull(ids.escalationUser),
  };
}

async function persistAssignment(nodeKey, ids) {
  const payload = readAssignmentPayload(nodeKey, ids);
  const saved = await PUT('/execution/assignments', payload);
  const st = state.designer;
  if (saved && st.assignmentCtx && st.assignmentCtx.processId === payload.process_id) {
    st.assignmentCtx.assignments.set(nodeKey, saved);
  }
  return saved;
}

async function saveBpmnAssignment(nodeKey) {
  try {
    await persistAssignment(nodeKey, {
      role: 'baRole',
      org: 'baOrg',
      assignee: 'baAssignee',
      due: 'baDue',
      escalationHours: 'baEscHours',
      escalationUser: 'baEscUser',
    });
    toast('节点执行配置已保存');
  } catch (e) {
    toast(e.message, true);
  }
}

async function saveNodeAssignment(nodeKey) {
  try {
    await persistAssignment(nodeKey, {
      role: 'edRole',
      org: 'edOrg',
      assignee: 'edAssignee',
      due: 'edDue',
      escalationHours: 'edEscHours',
      escalationUser: 'edEscUser',
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
  addDesignerNode, addLane, addLaneNode, addNode, addNodeAtCenter, autoLayoutBpmn,
  cloneModel, deleteEdge, deleteNode, diffVersion, editNode, exportBpmn,
  fitBpmnViewport, fitDesigner, importBpmn, openDesigner, openEdgeEditor,
  openNodeEditor, openVersionHistory, paintDesigner, paintMetrics,
  paintSuggestions, persistDesign, publishDesign, reanalyze, redoDesigner,
  rejectReview, reloadDesign, renderDesigner, rollbackVersion, runBpmnLint,
  saveEdge, saveNode, saveNodeAssignment, saveBpmnMetrics, saveBpmnName,
  saveBpmnAssignment,
  selectLintIssue,
  closeBpmnSidebar, setDesignerTab, showBpmnSidebarTab, submitReview, switchProcess,
  toggleBpmnFullscreen, toggleBpmnSidebar, toggleDesignerMode, undoDesigner,
};
