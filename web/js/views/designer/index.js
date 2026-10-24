/* 流程设计器编排层。
 *
 * `designer.js` 只是薄壳；这里负责：加载数据 → 创建 ctx → 组装子模块 →
 * 渲染页面 → 注册 data-act 处理器。子模块之间不互相 import，
 * 统一通过 ctx 访问画布与彼此的服务。
 */

import { esc, num, dur } from '../../core/format.js';
import { toast, closeModal, viewEl, on } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { renderAsync, go, RENDERERS } from '../../core/router.js';
import { AUTH, canWrite, canManage } from '../../core/auth.js';
import { metricHelp } from '../../core/metrics.js';
import { GET, POST } from '../../core/api.js';
import { actions as appActions } from '../../core/actions.js';
import { createCanvas } from './canvas.js';
import { createPanels } from './panels.js';
import { createAssignment } from './assignment.js';
import { createLint } from './lint.js';
import { createVersions } from './versions.js';
import { createTransfer } from './transfer.js';
import { createChanges } from './changes.js';
import { createRaci } from './raci.js';

/** 深拷贝模型，用作「服务端已确认」的回滚基准。 */
function cloneModel(model) {
  return JSON.parse(JSON.stringify(model));
}

const ctx = {
  cloneModel,
  getModeler: () => state.designer.bpmnModeler,
  getElement: (key) => {
    const modeler = state.designer.bpmnModeler;
    return modeler ? modeler.get('elementRegistry').get(key) : null;
  },
  select: (element) => {
    const modeler = state.designer.bpmnModeler;
    if (modeler) modeler.get('selection').select(element);
  },
  subscribe: (event, fn) => {
    const modeler = state.designer.bpmnModeler;
    if (modeler) modeler.on(event, fn);
  },
  reload: () => reloadDesign(),
};

const canvas = createCanvas(ctx);
const lint = createLint(ctx);
const panels = createPanels(ctx);
const assignment = createAssignment(ctx);
const versions = createVersions(ctx);
const transfer = createTransfer(ctx);
const changes = createChanges(ctx);
const raci = createRaci(ctx);

Object.assign(ctx, {
  renderSelection: panels.renderSelection,
  renderBpmnAssignment: assignment.renderBpmnAssignment,
  hydrateBpmnNodeExtras: assignment.hydrateBpmnNodeExtras,
  runLint: lint.run,
  loadLint: canvas.loadLint,
  showSidebar: panels.showSidebarTab,
  closeSidebar: panels.closeSidebar,
  saveNow: canvas.saveNow,
  postXml: canvas.postXml,
  clearSaveTimer: canvas.clearSaveTimer,
  setSaveState: canvas.setSaveState,
  fit: canvas.fit,
  approvedChangeRequest: changes.approvedForPublish,
});

/* -------------------------------------------------- 页面与数据 */

export async function openDesigner(processId) {
  state.designer.processId = processId;
  go('designer');
}

export function renderDesigner() {
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
      const [model, analysis, positions, tools, toolMeta, docMeta, changes, changeMeta,
        raciMatrix, governanceRoles, raciMeta] =
        await Promise.all([
          GET('/processes/' + id + '/design'),
          POST('/processes/' + id + '/design/analyze', {}),
          GET('/positions'),
          GET('/tools'),
          GET('/tools/meta'),
          GET('/process-documents/meta'),
          GET('/changes?process_id=' + id),
          GET('/changes/meta'),
          GET('/governance/raci?process_id=' + id),
          GET('/governance/roles?active_only=true'),
          GET('/governance/meta'),
        ]);
      state.designer.model = model;
      state.designer.savedModel = cloneModel(model);   // 回滚基准
      state.designer.analysis = analysis;
      state.designer.positions = positions;
      state.designer.tools = tools;
      state.designer.toolMeta = toolMeta;
      state.docMeta = docMeta;
      state.designer.changes = changes;
      state.designer.changeMeta = changeMeta;
      state.designer.raci = raciMatrix;
      state.designer.governanceRoles = governanceRoles;
      state.designer.raciMeta = raciMeta;
      state.designer.processCode = (list.find((r) => r.id === id) || {}).code;
    }
  };
  renderAsync('designer', load, () => paintDesigner());
}

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

  const proc = (st.processes || []).find((p) => p.id === st.processId) || {};
  const inReview = model.status === 'IN_REVIEW';
  const editable = !inReview && canWrite() && (canManage()
    || (AUTH.user && proc.owner_user_id === AUTH.user.id));
  st.editable = editable;

  const tab = st.tab || 'model';
  const tabBar = `
    <div class="seg">
      <button class="${tab === 'model' ? 'on' : ''}" data-act="designer.tab" data-tab="model">流程模型</button>
      <button class="${tab === 'analysis' ? 'on' : ''}" data-act="designer.tab" data-tab="analysis">
        指标与建议${st.analysis ? ' · ' + st.analysis.suggestions.length : ''}</button>
      <button class="${tab === 'change' ? 'on' : ''}" data-act="designer.tab" data-tab="change">
        变更${(st.changes || []).length ? ' · ' + st.changes.length : ''}</button>
      <button class="${tab === 'raci' ? 'on' : ''}" data-act="designer.tab" data-tab="raci">
        权责${st.raci && st.raci.matters ? ' · ' + st.raci.matters.length : ''}</button>
    </div>`;

  const bpmnPane = `
    <div class="card designer-card" id="bpmnCard">
      <div class="mb designer-toolbar bpmn-toolbar">
        <div class="gap bpmn-toolbar-left">
          <span class="tiny">专业 BPMN 2.0 画布（bpmn-js）</span>
          <button class="btn-sm" data-act="designer.lint">运行校验</button>
          <button class="btn-sm" data-act="designer.autoLayout">自动布局</button>
          <button class="btn-sm" data-act="designer.fullscreen">全屏</button>
          ${editable ? '<button class="btn-sm" data-act="designer.addLane">+ 泳道</button>' : ''}
          <button class="btn-sm" id="bpmnPropsToggle"
            data-act="designer.sidebar" data-tab="props">属性</button>
          <button class="btn-sm bpmn-lint-toggle" id="bpmnLintToggle"
            data-act="designer.sidebar" data-tab="lint">校验问题</button>
          <span class="tiny" id="bpmnSaveState">${
            model.status_label ? esc(model.status_label) + ' · v' + (model.draft_version || model.version)
              : '编辑后自动保存草稿'}</span>
        </div>
        <button class="btn-sm bpmn-fit-btn" data-act="designer.fit">适应画布</button>
        <div class="tiny bpmn-toolbar-hint">单击选中 · 双击改名 · 点「属性」查看/编辑指标与执行配置</div>
      </div>
      <div id="bpmnCanvas" class="bpmn-canvas${editable ? '' : ' readonly'}"></div>
      <div id="bpmnSidebar" class="bpmn-drawer" aria-hidden="true">
        <div class="bpmn-drawer-head">
          <div class="seg bpmn-drawer-tabs">
            <button id="bpmnTabProps" class="on"
              data-act="designer.sidebarTab" data-tab="props">属性</button>
            <button id="bpmnTabLint" data-act="designer.sidebarTab" data-tab="lint">校验</button>
          </div>
          <button class="btn-sm" data-act="designer.closeSidebar">收起</button>
        </div>
        <div class="bpmn-drawer-body">
          <div id="bpmnPropsPanel" class="bpmn-drawer-pane">
            <div class="tiny muted">选中一个元素查看/编辑属性</div>
          </div>
          <div id="bpmnLintPanel" class="bpmn-drawer-pane hide">
            <div id="bpmnLint" class="bpmn-lint"></div>
          </div>
        </div>
      </div>
      <div class="note" style="margin-top:8px">执行引擎只支持串行流程：调色板与「更改元素」菜单已隐藏
        并行网关、子流程和边界事件。从外部导入包含这些构造的 BPMN 文件时，保存仍会被拒绝并给出提示。</div>
      ${versions.validationHtml(st.model)}
    </div>`;

  const modelPane = bpmnPane;
  const changePane = changes.paneHtml();
  const raciPane = raci.paneHtml();

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
              ${model.requires_change_request
                ? '<span class="tag t-yel">变更门禁</span>' : ''}
              <span class="tiny">运行时版本 ${
                model.published_version ? 'v' + model.published_version : '尚未发布'}</span></h2>
          </div>
          ${tabBar}
        </div>
        <div class="designer-head-primary">
          <select class="sel sel-sm" data-act="designer.process">${opts}</select>
          ${publishable
            ? '<button class="btn-sm btn-p" data-act="designer.publish">发布到运行时</button>' : ''}
          <button class="btn-sm btn-p" data-act="designer.reanalyze">重新测算</button>
        </div>
      </div>
      <div class="designer-head-bar">
        <div class="designer-head-actions">
          <button class="btn-sm btn-g" data-act="designer.versions">版本历史</button>
          ${model.status === 'DRAFT' && editable
            ? '<button class="btn-sm btn-g" data-act="designer.submitReview">提交评审</button>' : ''}
          ${model.status === 'IN_REVIEW' && canManage()
            ? '<button class="btn-sm btn-g" data-act="designer.rejectReview">驳回</button>' : ''}
          <button class="btn-sm btn-g" data-act="designer.export">导出 BPMN</button>
          ${editable ? '<button class="btn-sm btn-g" data-act="designer.import">导入 BPMN</button>' : ''}
          ${inReview
            ? '<span class="tiny">评审中，暂不可编辑</span>'
            : editable
              ? ''
              : '<span class="tiny">只读（你不是这条流程的 Owner）</span>'}
          <a class="link-btn link-btn-sm" data-act="designer.goExecution">去流程执行 →</a>
        </div>
      </div>
    </div>
    ${tab === 'analysis' ? analysisPane
      : tab === 'change' ? changePane
        : tab === 'raci' ? raciPane : modelPane}`;
  if (tab !== 'analysis' && tab !== 'change' && tab !== 'raci') canvas.mount();
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
      ${s.suggested_tool ? '<button class="tool" type="button" data-act="designer.openTool"'
        + ' data-code="' + esc(s.suggested_tool) + '">→ 用「' + esc(s.suggested_tool) +
        '」动手</button>' : ''}
    </div>`).join('');
}

function switchProcess(id) {
  state.designer.processId = Number(id);
  state.designer.processCode = (state.designer.processes.find((p) => p.id === Number(id)) || {}).code;
  state.designer.tab = 'model';
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

/** 把当前内存中的模型整份提交给后端（后端是覆盖式保存）
 *
 *  节点编辑是「先改内存模型，再提交」的乐观更新。一旦后端拒绝（比如唯一键冲突、
 *  连线悬空），必须把模型回滚到最后一个服务端确认过的版本并重绘，
 *  否则内存里的模型和界面显示就分叉了，下次重绘会冒出从未保存成功的节点。
 */
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
    // 冲突重载可能带回别人的结构改动，分派配置也跟着重新拉取
    st.assignmentCtx = null;
    st.assignmentPending = null;
    paintDesigner();
  } catch (e) {
    toast(e.message, true);
  }
}

function setDesignerTab(tab) {
  state.designer.tab = tab;
  RENDERERS.designer();
}

/* -------------------------------------------------- data-act 处理器 */

on('designer.tab', ({ tab }) => setDesignerTab(tab));
on('designer.lint', () => lint.run());
on('designer.autoLayout', () => canvas.autoLayout());
on('designer.fullscreen', () => canvas.toggleFullscreen());
on('designer.addLane', () => panels.addLane());
on('designer.sidebar', ({ tab }) => panels.toggleSidebar(tab));
on('designer.sidebarTab', ({ tab }) => panels.showSidebarTab(tab));
on('designer.closeSidebar', () => panels.closeSidebar());
on('designer.fit', () => canvas.fit());
on('designer.process', (_data, el) => switchProcess(el.value));
on('designer.publish', () => versions.publishDesign());
on('designer.reanalyze', () => reanalyze());
on('designer.versions', () => versions.openVersionHistory());
on('designer.submitReview', () => versions.submitReview());
on('designer.rejectReview', () => versions.rejectReview());
on('designer.export', () => transfer.exportBpmn());
on('designer.import', () => transfer.importBpmn());
on('designer.goExecution', () => go('execution'));
on('designer.saveName', ({ id }) => panels.saveName(id));
on('designer.changeType', ({ id }) => panels.changeNodeType(id));
on('designer.moveLane', ({ id }) => panels.moveNodeToLane(id));
on('designer.saveActivity', ({ node }) => assignment.saveBpmnNodeActivity(node));
on('designer.saveMetrics', ({ node }) => panels.saveMetrics(node));
on('designer.deleteFlow', ({ id }) => panels.deleteFlow(id));
on('designer.saveFlow', ({ id }) => panels.saveFlow(id));
on('designer.saveLaneName', ({ id }) => panels.saveLaneName(id));
on('designer.saveAssignment', ({ node }) => assignment.saveBpmnAssignment(node));
on('designer.addNodeTool', ({ node }) => assignment.addBpmnNodeTool(node));
on('designer.removeNodeTool', ({ node, code }) => assignment.removeBpmnNodeTool(node, code));
on('designer.openNodeDoc', ({ node }) => assignment.openNodeDocumentModal(node));
on('designer.goDeliverables', () => go('deliverables'));
on('designer.close', () => closeModal());
on('designer.submitNodeDoc', ({ node }) => assignment.submitNodeDocument(node));
on('designer.executionConfig', () => assignment.openExecutionConfig());
on('designer.openTool', ({ code }) => appActions['toolbox.openTool'](code));
on('designer.lintIssue', ({ index }) => lint.selectIssue(Number(index)));
on('designer.diffVersion', ({ id }) => versions.diffVersion(Number(id)));
on('designer.rollbackVersion', ({ id }) => versions.rollbackVersion(Number(id)));

export const actions = {
  'designer.open': openDesigner,
  'designer.switch': switchProcess,
};
