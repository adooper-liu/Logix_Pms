/* 设计器编排：加载数据、注入 ctx、组装子模块及注册动作。
 * 子模块不互相 import；共享能力只通过 ctx。
 */

import { esc, num, dur, tipHelp } from '../../core/format.js';
import { toast, closeModal, openModal, viewEl, on } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { pageShell } from '../../core/layout.js';
import { renderAsync, go, RENDERERS, urlParams, setUrlState } from '../../core/router.js';
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
import { createBinding } from './binding.js';
import { createBindingEdit } from './binding-edit.js';
import { createComments } from './comments.js';
import { createSimulation } from './simulation.js';
import { toolMountHtml } from '../shared/tool_mount.js';
import { createCompensation } from './compensation.js';
import { workbenchHtml } from '../shared/workbench.js';
import { createDecisions } from './decisions.js';

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
const binding = createBinding(ctx);
createBindingEdit(ctx);
const comments = createComments(ctx);
const simulation = createSimulation(ctx);
const compensation = createCompensation();
const decisions = createDecisions();
on('designer.executionProvider', async (_data, element) => {
  const st = state.designer;
  const modeler = st.bpmnModeler;
  if (!modeler) return;
  try {
    const { xml } = await modeler.saveXML({ format: true });
    const response = await POST('/processes/' + st.processId + '/bpmn', {
      xml, execution_provider: element.value, expected_version: st.model.version,
    });
    st.model = response;
    st.savedModel = cloneModel(response);
    await ctx.reload();
  } catch (error) { toast(error.message, true); element.value = st.model.execution_provider; }
});

Object.assign(ctx, {
  renderSelection: panels.renderSelection,
  renderNodeBinding: binding.nodeHtml,
  refreshBinding: binding.refresh,
  applyBindingMarkers: binding.mounted,
  showModel: () => setDesignerTab('model'),
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
  go('designer', { params: { process: processId }, push: true });
}

let designerLoadRevision = 0;

export function renderDesigner() {
  const revision = ++designerLoadRevision;
  const current = () => revision === designerLoadRevision && state.view === 'designer';
  const load = async () => {
    const params = urlParams();
    if (params.process) state.designer.processId = Number(params.process);
    if (['model', 'analysis', 'change', 'raci', 'binding'].includes(params.tab)) {
      state.designer.tab = params.tab;
    }
    // 每次进入都拉清单：seed --reset 后 id 会变，缓存会指向已删除流程
    const rows = await GET('/process-map/flat');
    if (!current()) return;
    state.designer.processes = rows.filter((r) => r.level >= 3);
    const list = state.designer.processes;
    const preferred = () => list.find((r) => r.code === 'L3-032') || list[0] || null;
    const inList = list.some((r) => r.id === state.designer.processId);
    if (params.lifecycle && params.process && !inList) {
      throw new Error('所选流程不可用于本步建模，未切换其他流程');
    }
    if (!state.designer.processId || !inList) {
      // URL/状态里的旧 process（常见于重灌后）自动落到演示流程
      const pick = preferred();
      state.designer.processId = pick ? pick.id : null;
      state.designer.model = null;
    }
    if (state.designer.processId) {
      const id = state.designer.processId;
      const url = params.node ? { process: id, node: params.node, basis: params.basis } : { process: id };
      if (state.designer.tab && state.designer.tab !== 'model') url.tab = state.designer.tab;
      setUrlState('designer', url, { push: false });
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
      const workbench = await GET('/processes/'+id+'/workbench');
      const bindingData = await binding.load(id);
      if (!current() || state.designer.processId !== id) return;
      binding.accept(bindingData, model); binding.acceptLocation(params, bindingData, model);
      state.designer.workbench=workbench;
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
  const forceSkeleton = !!state.designer.forceSkeleton;
  state.designer.forceSkeleton = false;
  renderAsync('designer', load, () => paintDesigner(), { forceSkeleton });
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
  // 页签 = 看哪里（内容切换）；与下方「对流程做什么」动作条分离
  const tabBar = `
    <nav class="designer-tabs" aria-label="设计器页签">
      <button type="button" class="${tab === 'model' ? 'on' : ''}"
        data-act="designer.tab" data-tab="model">流程模型</button>
      <button type="button" class="${tab === 'analysis' ? 'on' : ''}"
        data-act="designer.tab" data-tab="analysis">测算分析${
          st.analysis ? ' · ' + st.analysis.suggestions.length : ''}</button>
      <button type="button" class="${tab === 'raci' ? 'on' : ''}"
        data-act="designer.tab" data-tab="raci">权责${
          st.raci && st.raci.matters ? ' · ' + st.raci.matters.length : ''}</button>
      <button type="button" class="${tab === 'binding' ? 'on' : ''}"
        data-act="designer.tab" data-tab="binding">绑定</button>
      <button type="button" class="${tab === 'change' ? 'on' : ''}"
        data-act="designer.tab" data-tab="change">变更${
          (st.changes || []).length ? ' · ' + st.changes.length : ''}</button>
    </nav>`;

  const bpmnPane = `
    <div class="card designer-card" id="bpmnCard">
      <div class="bpmn-toolbar" role="toolbar" aria-label="画布工具">
        <div class="designer-act-group" data-group="view">
          <button class="btn-sm" data-act="designer.autoLayout" title="按泳道重排节点与连线">自动布局</button>
          <button class="btn-sm bpmn-fit-btn" data-act="designer.fit" title="缩放到可见区域">适应画布</button>
          <button class="btn-sm" data-act="designer.fullscreen">全屏</button>
        </div>
        <div class="designer-act-group" data-group="lint">
          <button class="btn-sm" data-act="designer.lint">运行校验</button>
          <button class="btn-sm bpmn-lint-toggle" id="bpmnLintToggle"
            data-act="designer.sidebar" data-tab="lint" title="打开校验结果">校验问题</button>
        </div>
        <div class="designer-act-group" data-group="analyze">
          <button class="btn-sm" data-act="designer.simulate">路径模拟</button>
          <button class="btn-sm" data-act="designer.decisions">决策表</button>
          <button class="btn-sm" data-act="designer.compensation">补偿动作</button>
          <button class="btn-sm" data-act="designer.comments">评论</button>
        </div>
        ${editable
          ? `<div class="designer-act-group" data-group="edit">
              <button class="btn-sm" data-act="designer.addLane">+ 泳道</button>
            </div>`
          : ''}
        <div class="designer-act-group" data-group="help">
          <button class="btn-sm" data-act="designer.shortcuts">快捷键</button>
          ${tipHelp(
            '单击选中 · 双击改名。右侧「属性」按主题编辑（基本 / 责任 / 测算 / 文件 / 执行）；方法工具挂五阶段步骤。',
            '画布操作说明')}
        </div>
        <div class="bpmn-toolbar-status">
          <span class="tiny" id="bpmnSaveState">${
            model.status_label
              ? esc(model.status_label) + ' · v' + (model.draft_version || model.version)
              : '编辑后自动保存草稿'}</span>
        </div>
      </div>
      <div id="bpmnCanvas" class="bpmn-canvas${editable ? '' : ' readonly'}"></div>
      <button type="button" class="bpmn-drawer-rail" id="bpmnPropsToggle"
        data-act="designer.sidebar" data-tab="props"
        aria-expanded="false" aria-controls="bpmnSidebar" title="展开属性栏">
        <span class="bpmn-drawer-rail-mark" aria-hidden="true">‹</span>
        <span class="bpmn-drawer-rail-text">属性</span>
      </button>
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
      ${versions.validationHtml(st.model)}
    </div>`;

  const modelPane = bpmnPane;
  const changePane = changes.paneHtml();
  const raciPane = raci.paneHtml();

  const analysisPane = `
    <div class="grid g2">
      <div class="card">
        <h3>流程指标测算</h3>
        <div class="desc">设计态估计（来自节点「测算」），用于 PCE/瓶颈诊断；不是运营实测 KPI</div>
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
  const draftVer = model.draft_version || model.version;
  const liveVer = model.published_version
    ? 'v' + model.published_version
    : '尚未发布';
  const publishable = canManage() && (model.status === 'DRAFT' || model.status === 'IN_REVIEW');
  const approvedChange = model.requires_change_request
    ? (st.changes || []).find((row) => row.status === 'APPROVED')
    : null;
  const gateBlocksPublish = !!(model.requires_change_request && !approvedChange);
  // 生命周期按钮只出现在动作条一次：草稿→提交/发布，待评审→发布/驳回
  const lifecycleHtml = [
    model.status === 'DRAFT' && editable
      ? `<button class="btn-sm btn-g" data-act="designer.submitReview">提交评审</button>${
        tipHelp(
          '锁定草稿为待评审，不改运行时；通过后由管理科「发布到运行时」。',
          '提交评审')}`
      : '',
    publishable
      ? `<button class="btn-sm btn-p" data-act="designer.publish"${
        gateBlocksPublish
          ? ' title="变更门禁未通过：请先在「变更」页提交并批准变更申请"'
          : ''
      }>发布到运行时</button>${
        tipHelp(
          gateBlocksPublish
            ? '该流程启用了变更门禁：须有「已批准」的变更申请后才能发布。'
            : inReview
              ? '评审通过后的上线：本草稿成为运行时版本，新实例按此启动。'
              : '将当前草稿发布为运行时模型；策略为「须先评审」时需先提交评审。',
          '发布说明')}`
      : '',
    model.status === 'IN_REVIEW' && canManage()
      ? `<button class="btn-sm btn-g" data-act="designer.rejectReview">驳回改草稿</button>${
        tipHelp('退回可编辑草稿；运行时不变。', '驳回')}`
      : '',
  ].filter(Boolean).join('');

  // 一条状态条说清三件事：当前草稿 / 运行时 / 下一步（取代标签堆 + 长说明条）
  let nextLine = '';
  if (inReview) {
    if (gateBlocksPublish) {
      nextLine = '先在「变更」批准变更单，再发布上线或驳回';
    } else if (canManage()) {
      nextLine = '发布上线，或驳回继续改';
    } else {
      nextLine = '等待管理科发布或驳回';
    }
  } else if (model.status === 'DRAFT' && editable) {
    if (model.publish_policy === 'direct') {
      nextLine = gateBlocksPublish
        ? '直接发布策略；发布前须先批准变更单'
        : '可提交评审，或直接发布到运行时';
    } else {
      nextLine = gateBlocksPublish
        ? '须先评审；发布前还须批准变更单'
        : '先提交评审，通过后再发布到运行时';
    }
  } else if (!editable) {
    nextLine = '只读（非 Owner）；可查看版本历史';
  }
  const modeBit = inReview
    ? '画布只读'
    : editable
      ? '可编辑'
      : '只读';
  const stateStrip = `
    <div class="designer-state" role="status">
      <div class="designer-state-cell">
        <span class="designer-state-lab">当前草稿</span>
        <span class="tag ${statusTone[model.status] || 't-blu'}">${
          esc(model.status_label || model.status || '—')} · v${draftVer}</span>
        <span class="tiny">${modeBit}</span>
      </div>
      <div class="designer-state-cell">
        <span class="designer-state-lab">运行时</span>
        <b>${esc(liveVer)}</b>
        ${inReview && model.published_version
          ? '<span class="tiny">未切换</span>' : ''}
      </div>
      <div class="designer-state-cell designer-state-next">
        <span class="designer-state-lab">下一步</span>
        <span>${esc(nextLine)}</span>
        ${tipHelp(
          '提交评审只锁定草稿，不等于上线；发布后新实例才用新版本，在途实例仍钉旧版。'
            + (model.change_note ? ' 本轮说明：' + model.change_note : ''),
          '版本与发布说明')}
      </div>
    </div>`;

  const content = `
    ${workbenchHtml(st.workbench, urlParams().lifecycle === 'design' ? 'DESIGN'
    : (urlParams().lifecycle === 'modeling' ? 'MODELING' : (st.workKind || 'MODELING')), 'designer')}
    ${tab === 'analysis' ? analysisPane
    : tab === 'change' ? changePane
      : tab === 'binding' ? '<div id="designerBindingPane">' + binding.paneHtml() + '</div>'
      : tab === 'raci' ? raciPane : modelPane}`;
  const shell = pageShell({
    title: '流程设计器',
    badge: '<span class="module-badge">建模与测算</span>',
    subtitle: esc(model.process_name || ''),
    tip: tipHelp(
      '执行引擎只支持串行流程：调色板与「更改元素」菜单已隐藏并行网关、子流程和边界事件；'
      + '外部导入包含这些构造的 BPMN 会被拒绝并提示。属性/校验在画布右侧抽屉，版本历史在弹窗。',
      '设计器说明',
    ),
    actions: `<div class="gap" style="flex-wrap:wrap;justify-content:flex-end">
      <select class="sel sel-sm" data-act="designer.process"
        title="切换当前流程">${opts}</select>
      <a class="link-btn link-btn-sm" data-act="designer.goExecution">去流程执行 →</a>
      <button class="btn-sm btn-g" data-act="designer.versions">版本历史</button>
      ${gateBlocksPublish
        ? `<button class="btn-sm btn-g" data-act="designer.tab" data-tab="change"
            title="发布前须有已批准变更单">去批准变更</button>` : ''}
    </div>`,
    sections: [{
      key: 'main',
      html: `
        ${toolMountHtml(st.tools, 'design', st.processId)}
        ${stateStrip}
        <div class="field"><label>执行目标</label>
          <select data-act="designer.executionProvider" ${editable ? '' : 'disabled'}>
            ${Object.entries(model.execution_provider_labels || {}).map(([key, label]) => `<option value="${esc(key)}" ${key === model.execution_provider ? 'selected' : ''}>${esc(label)}</option>`).join('')}
          </select>
          <span class="tiny">切换后保存新工作版；Flowable 沙箱仅支持已验证的串行/并行人工任务。</span></div>
        <div class="designer-head-nav">
          ${tabBar}
          <div class="designer-head-actions" role="toolbar" aria-label="流程操作">
            ${lifecycleHtml
              ? `<div class="designer-act-group" data-group="lifecycle">${lifecycleHtml}</div>`
              : ''}
            <div class="designer-act-group" data-group="io">
              <button class="btn-sm btn-g" data-act="designer.export">导出 BPMN</button>
              ${editable
                ? '<button class="btn-sm btn-g" data-act="designer.import">导入 BPMN</button>'
                : ''}
              ${tab === 'analysis'
                ? '<button class="btn-sm btn-g" data-act="designer.reanalyze">重新测算</button>'
                : ''}
            </div>
          </div>
        </div>
        ${content}`,
    }],
    active: 'main',
    mode: 'plain',
  });
  viewEl().innerHTML = shell.html;
  if (tab === 'model') canvas.mount();
}

function paintMetrics(a) {
  if (!a) return '<div class="empty">暂无测算结果</div>';
  const m = a.metrics;

  // ratio 为 null 时不画进度条 —— 没有目标值的指标画条只能是编造百分比。
  const row = (label, value, hint, ratio, color) => {
    const hasBar = ratio !== null && ratio !== undefined && isFinite(ratio);
    const w = hasBar ? Math.max(0, Math.min(100, ratio)) : 0;
    return `
      <div class="designer-metric-row">
        <span class="designer-metric-label">${label}</span>
        ${hasBar
          ? '<span class="designer-metric-bar"><i style="width:' + w + '%;background:' + color + '"></i></span>'
          : '<span class="designer-metric-bar spacer"></span>'}
        <span class="designer-metric-value">${value}
          <span class="tiny">${hint}</span></span>
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

  const cycleHint = m.has_branch_or_loop
    ? '线性合计 ' + dur(m.linear_lead_time_minutes) + '（旧口径，未计回路）'
    : '无分支回路，与线性合计一致';

  const waitWorkHint = '等待 ' + num(m.wait_minutes, 0) + ' 分 · 作业 '
    + num(m.process_time_minutes, 0) + ' 分（二者对同一期望周期）';

  return warn + `
    <div class="designer-metric-block">
      <div class="tiny muted mb">重点（结构诊断）</div>
      ${row(metricHelp('pce'), num(pce, 1) + '%',
        '增值 / 期望端到端 · 锚点 &lt;15% 偏低（可校准）',
        pce, pce >= 35 ? 'var(--ok)' : pce >= 15 ? 'var(--warn)' : 'var(--bad)')}
      ${row(metricHelp('wait_ratio', '等待 / 作业'),
        num(waitShare, 1) + '% / ' + num(workShare, 1) + '%', waitWorkHint,
        waitShare, waitShare >= 50 ? 'var(--bad)' : waitShare >= 30 ? 'var(--warn)' : 'var(--ok)')}
      ${row(metricHelp('lead_time', '期望端到端周期'), dur(m.lead_time_minutes), cycleHint, null, '')}
      ${row(metricHelp('rework_loss', '返工损失'), dur(m.rework_loss_minutes),
        '额外作业 ' + dur(m.rework_work_minutes) + ' · 占作业 ' + num(reworkShare, 1) + '%',
        reworkShare, reworkShare >= 15 ? 'var(--bad)' : reworkShare > 0 ? 'var(--warn)' : 'var(--ok)')}
    </div>
    <div class="designer-metric-block secondary">
      <div class="tiny muted mb">辅助</div>
      ${row(metricHelp('handoff_count', '跨泳道移交'), m.handoff_count + ' 次',
        m.lane_count + ' 个部门/角色', null, '')}
      ${row(metricHelp('approval_levels', '累计审批层级'), m.total_approval_levels + ' 层',
        m.approval_node_count + ' 个审批节点 · 未填层级按 1', null, '')}
      ${row(metricHelp('unit_cost', '单次执行成本'), num(m.unit_cost, 1) + ' 元',
        '期望成本合计（设计估计）', null, '')}
    </div>
    <details class="designer-metric-fte">
      <summary class="tiny">管理层换算（假设，非财务核算）</summary>
      <div class="note mt">按月均 <b>1000</b> 单、人天 <b>480</b> 分钟估算，
        ${metricHelp('fte_saved', '可释放人天/月')}约 <b>${num(m.fte_days_saved_per_month, 0)}</b>
        （仅计返工额外作业，阈值在服务端常量，可按企业校准）。</div>
    </details>`;
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
  state.designer.forceSkeleton = true;
  setUrlState('designer', { process: Number(id) }, { push: true });
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

/** 原节点编辑保存失败时，重载服务端已确认模型及绑定。 */
async function reloadDesign() {
  const st = state.designer;
  const pid = st.processId;
  const revision = ++designerLoadRevision;
  try {
    const [model, analysis] = await Promise.all([
      GET('/processes/' + pid + '/design'),
      POST('/processes/' + pid + '/design/analyze', {}),
    ]);
    if (revision !== designerLoadRevision || state.view !== 'designer' || st.processId !== pid) return;
    st.model = model;
    st.savedModel = cloneModel(model);
    st.analysis = analysis;
    await binding.refresh();
    if (revision !== designerLoadRevision || state.view !== 'designer' || st.processId !== pid) return;
    // 冲突重载可能带回别人的结构改动，分派配置也跟着重新拉取
    st.assignmentCtx = null;
    st.assignmentPending = null;
    paintDesigner();
  } catch (e) {
    toast(e.message, true);
  }
}

function setDesignerTab(tab) {
  const next = ['model', 'analysis', 'change', 'raci', 'binding'].includes(tab) ? tab : 'model';
  state.designer.tab = next;
  const params = {};
  if (state.designer.processId) params.process = state.designer.processId;
  if (next !== 'model') params.tab = next;
  setUrlState('designer', params, { push: false });
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
on('designer.propSection', ({ section }) => panels.setPropSection(section));
on('designer.closeSidebar', () => panels.closeSidebar());
on('designer.fit', () => canvas.fit());
on('designer.process', (_data, el) => switchProcess(el.value));
on('designer.publish', () => versions.publishDesign());
on('designer.confirmPublish', ({ change }) => versions.confirmPublish(change || null));
on('designer.reanalyze', () => reanalyze());
on('designer.versions', () => versions.openVersionHistory());
on('designer.submitReview', () => versions.submitReview());
on('designer.rejectReview', () => versions.rejectReview());
on('designer.export', () => transfer.exportBpmn());
on('designer.import', () => transfer.importBpmn());
on('designer.goExecution', () => {
  const pid = state.designer.processId;
  go('execution', {
    params: pid ? { process: pid, tab: 'config' } : {},
    push: true,
  });
});
on('designer.publishFromChange', () => {
  state.designer.tab = 'model';
  RENDERERS.designer();
  setTimeout(() => versions.publishDesign(), 150);
});
on('designer.saveName', ({ id }) => panels.saveName(id));
on('designer.saveDescription', ({ id }) => panels.saveDescription(id));
on('designer.comments', () => comments.open());
on('designer.simulate', () => simulation.open());
on('designer.compensation', () => compensation.open());
on('designer.saveCompensation', () => compensation.save());
on('designer.decisions', () => decisions.open());
on('designer.createDecision', () => decisions.openCreate());
on('designer.submitDecision', () => decisions.submitCreate());
on('designer.evaluateDecision', () => decisions.evaluate());
on('designer.addComment', ({ element, name, type }) => comments.add(element, name, type));
on('designer.resolveComment', ({ id }) => comments.resolve(Number(id)));
on('designer.shortcuts', () => {  openModal('画布快捷键', `
    <table class="tbl">
      <thead><tr><th>操作</th><th>快捷键 / 方式</th></tr></thead>
      <tbody>
        <tr><td>撤销 / 重做</td><td>Ctrl+Z / Ctrl+Shift+Z</td></tr>
        <tr><td>删除元素</td><td>选中后按 Delete</td></tr>
        <tr><td>框选多个元素</td><td>Shift + 拖动</td></tr>
        <tr><td>移动画布</td><td>Space + 拖动，或抓手工具</td></tr>
        <tr><td>缩放</td><td>Ctrl + 滚轮</td></tr>
        <tr><td>改名</td><td>双击元素</td></tr>
        <tr><td>查看 / 编辑属性</td><td>单击元素 → 工具栏「属性」</td></tr>
        <tr><td>连线</td><td>悬停元素边缘的箭头拖出</td></tr>
      </tbody>
    </table>
    <div class="note mt">快捷键由 bpmn-js 提供；输入框聚焦时不会触发画布快捷键。</div>`,
  '<button class="btn btn-g" data-act="designer.close">关闭</button>');
});
on('designer.changeType', ({ id }) => panels.changeNodeType(id));
on('designer.moveLane', ({ id }) => panels.moveNodeToLane(id));
on('designer.saveActivity', ({ node }) => assignment.saveBpmnNodeActivity(node));
on('designer.savePosition', ({ node }) => panels.savePosition(node));
on('designer.saveMetrics', ({ node }) => panels.saveMetrics(node));
on('designer.deleteFlow', ({ id }) => panels.deleteFlow(id));
on('designer.saveFlow', ({ id }) => panels.saveFlow(id));
on('designer.addFlowMatch', () => panels.addFlowMatch());
on('designer.removeFlowMatch', (_data, el) => panels.removeFlowMatch(el));
on('designer.flowMatchOp', (_data, el) => panels.flowMatchOp(el));
on('designer.saveLaneName', ({ id }) => panels.saveLaneName(id));
on('designer.saveAssignment', ({ node }) => assignment.saveBpmnAssignment(node));
on('designer.addNodeTool', ({ node }) => assignment.addBpmnNodeTool(node));
on('designer.removeNodeTool', ({ node, code }) => assignment.removeBpmnNodeTool(node, code));
on('designer.openNodeDoc', ({ node }) => assignment.openNodeDocumentModal(node));
on('designer.goDeliverables', () => {
  const pid = state.designer.processId;
  go('deliverables', {
    params: { tab: 'document', ...(pid ? { process: String(pid) } : {}) },
    push: true,
  });
});
on('designer.goToolbox', () => go('toolbox'));
on('designer.close', () => closeModal());
on('designer.submitNodeDoc', ({ node }) => assignment.submitNodeDocument(node));
on('designer.executionConfig', ({ focus }) => assignment.openExecutionConfig(focus || 'forms'));
on('designer.openTool', ({ code }) => appActions['toolbox.openTool'](code));
on('designer.lintIssue', ({ index }) => lint.selectIssue(Number(index)));
on('designer.diffVersion', ({ id }) => versions.diffVersion(Number(id)));
on('designer.rollbackVersion', ({ id }) => versions.rollbackVersion(Number(id)));
on('designer.publishRollback', ({ id }) => versions.publishRollback(Number(id)));

export const actions = {
  'designer.open': openDesigner,
  'designer.switch': switchProcess,
};
