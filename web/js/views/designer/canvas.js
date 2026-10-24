/* bpmn-js 画布：脚本加载、挂载、销毁、视口适配与自动保存。
 *
 * 所有跨模块动作都走 `ctx`（由 index.js 注入），本文件不 import 其他
 * 有状态的 designer 子模块，避免拆包后互相依赖成环。
 */

import { esc } from '../../core/format.js';
import { confirmDialog, toast } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { API_BASE, GET, POST, getToken } from '../../core/api.js';
import { PMS_BPMN_GUARDS } from './providers.js';
import { ensureFlowRefs, restoreLanes } from './xml.js';

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

let bpmnJsPromise = null;
let bpmnLintPromise = null;
let bpmnLayoutPromise = null;

export function createCanvas(ctx) {
  function destroy() {
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

  function fit() {
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

  function setSaveState(text) {
    const el = document.getElementById('bpmnSaveState');
    if (el) el.textContent = text;
  }

  async function fetchXml() {
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

  function clearSaveTimer() {
    const st = state.designer;
    if (st.bpmnSaveTimer) {
      clearTimeout(st.bpmnSaveTimer);
      st.bpmnSaveTimer = null;
    }
  }

  function scheduleSave() {
    const st = state.designer;
    if (st.bpmnImporting || !st.bpmnModeler) return;
    setSaveState('有未保存修改…');
    if (st.bpmnSaveTimer) clearTimeout(st.bpmnSaveTimer);
    st.bpmnSaveTimer = setTimeout(saveNow, 900);
  }

  async function postXml(xml) {
    const st = state.designer;
    try {
      const response = await POST('/processes/' + st.processId + '/bpmn', {
        xml,
        expected_version: st.model ? st.model.version : null,
      });
      st.model = response;
      st.savedModel = ctx.cloneModel(response);
      st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
      setSaveState('已保存 · v' + (response.draft_version || response.version));
      ctx.renderSelection(st.bpmnSelection || []);
      ctx.runLint();
      return true;
    } catch (e) {
      setSaveState('保存失败：' + e.message);
      toast(e.message, true);
      return false;
    }
  }

  async function saveNow() {
    const st = state.designer;
    const modeler = st.bpmnModeler;
    if (!modeler) return false;
    let xml;
    try {
      ({ xml } = await modeler.saveXML({ format: true }));
    } catch (e) {
      setSaveState('保存失败：' + e.message);
      toast(e.message, true);
      return false;
    }
    return postXml(xml);
  }

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

  function loadLint() {
    if (window.BpmnLint) return Promise.resolve();
    if (!bpmnLintPromise) {
      bpmnLintPromise = loadScriptOnce(
        '/static/vendor/bpmn-js/bpmn-lint.js?v=2', () => window.BpmnLint);
    }
    return bpmnLintPromise;
  }

  function loadAutoLayout() {
    if (window.BpmnAutoLayout) return Promise.resolve();
    if (!bpmnLayoutPromise) {
      bpmnLayoutPromise = loadScriptOnce(
        '/static/vendor/bpmn-js/bpmn-auto-layout.js?v=1.3.0', () => window.BpmnAutoLayout);
    }
    return bpmnLayoutPromise;
  }

  async function mount() {
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
    destroy();
    const modeler = new window.BpmnJS({ container, additionalModules: [PMS_BPMN_GUARDS] });
    st.bpmnModeler = modeler;
    window.__bpmnSpike = { modeler, lint: window.BpmnLint };
    st.bpmnSelection = [];
    st.bpmnImporting = true;
    ctx.subscribe('selection.changed', (event) => {
      st.bpmnSelection = event.newSelection || [];
      // 只更新属性内容，不自动开关侧栏；侧栏由工具栏「属性」或「收起」控制
      ctx.renderSelection(st.bpmnSelection);
    });
    // 画布内双击改名完成后，同步属性栏里的名称字段
    ctx.subscribe('directEditing.complete', () => {
      ctx.renderSelection(st.bpmnSelection || []);
    });
    ctx.subscribe('commandStack.changed', scheduleSave);
    try {
      const xml = await fetchXml();
      await modeler.importXML(xml);
      const paletteToggle = container.querySelector('.djs-palette-toggle');
      if (paletteToggle) paletteToggle.title = '展开/收起工具';
      fit();
      st.bpmnImporting = false;
      setSaveState('草稿 · v' + (st.model.draft_version || st.model.version));
      ctx.runLint();
    } catch (e) {
      st.bpmnImporting = false;
      container.innerHTML = `<div class="errbar">BPMN 加载失败：${esc(e.message)}</div>`;
    }
  }

  function toggleFullscreen() {
    const card = document.getElementById('bpmnCard');
    if (!card) return;
    const enter = !card.classList.contains('fullscreen');
    card.classList.toggle('fullscreen', enter);
    // 全屏优先保证画布高度：属性/校验侧栏默认收起，用工具栏按钮随时打开
    if (enter) ctx.closeSidebar();
    const resize = () => {
      const modeler = state.designer.bpmnModeler;
      const container = document.getElementById('bpmnCanvas');
      // 全屏切换的瞬间容器可能还没有布局尺寸：此时 fit-viewport 会算出非有限值
      if (!modeler || !container || container.clientWidth < 1 || container.clientHeight < 1) return;
      modeler.get('canvas').resized();
      fit();
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

  async function autoLayout() {
    const modeler = state.designer.bpmnModeler;
    if (!modeler) return;
    const ok = await confirmDialog('自动布局会重新排列节点并覆盖当前画布布局，确定继续？',
      { title: '自动布局', okText: '继续' });
    if (!ok) return;
    try {
      await loadAutoLayout();
      const { xml } = await modeler.saveXML({ format: true });
      const layouted = await window.BpmnAutoLayout.layoutProcess(ensureFlowRefs(xml));
      state.designer.bpmnImporting = true;
      await modeler.importXML(restoreLanes(layouted));
      state.designer.bpmnImporting = false;
      state.designer.bpmnSelection = [];
      ctx.renderSelection([]);
      fit();
      const saved = await saveNow();
      if (saved) {
        await ctx.runLint();
        toast('已自动布局并保存');
      }
    } catch (e) {
      state.designer.bpmnImporting = false;
      toast(e.message, true);
    }
  }

  return {
    mount,
    destroy,
    fit,
    setSaveState,
    fetchXml,
    saveNow,
    clearSaveTimer,
    postXml,
    loadLint,
    toggleFullscreen,
    autoLayout,
  };
}
