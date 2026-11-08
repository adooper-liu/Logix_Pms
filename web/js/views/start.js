/* 视图：体系总览
 *
 * 只回答公司流程地图的框架边界：哪些工作进这张图，上下级怎么挂，谁有权改图。
 * 某一条流程从哪开始、到哪结束，去十层核对。
 */

import { esc, tipHelp } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { loadLifecycle, lifecycleHtml } from '../core/lifecycle.js';
import { renderAsync, go, urlParams } from '../core/router.js';
import { GET } from '../core/api.js';
import { state, TITLES } from '../core/state.js';

const STATUS_TONE = {
  READY: 't-grn',
  IN_PROGRESS: 't-yel',
  NOT_STARTED: 't-gry',
  SKIPPED: 't-pur',
};

/* 企业管理体系：流程是让目标可控的一种实践。
 * 前五层是主链，治理与支持横切；首页图谱和侧栏都从这里派生。 */
const FRAMEWORK_LAYERS = [
  {
    no: '01',
    label: '价值与目标',
    flow: '客户 / 市场价值 → 战略 → 目标 / KPI',
    question: '客户要什么？公司要赢什么？目标由哪条流程承接？',
    out: '产物：战略目标、KPI、目标—流程承接',
    views: [['dashboard', '运营驾驶舱'], ['strategy', '战略目标'], ['orgs', '组织与人员']],
  },
  {
    no: '02',
    label: '流程架构',
    flow: 'L1 价值链 → L2 类别 → L3 流程 → L4 活动',
    question: '公司有哪些流程？边界、Owner、分类和层级是什么？',
    out: '产物：流程地图、L1–L4、Owner、边界',
    views: [['map', '企业流程地图'], ['pcf', '流程架构 / PCF'], ['sketches', '架构草图']],
  },
  {
    no: '03',
    label: '流程资产',
    flow: '模型 → 资产包（编译）/ SOP / 表单 / 规则 / RACI / 控制点',
    question: '这条流程的资产齐不齐？谁负责、依据什么、留下什么记录？',
    out: '产物：模型版本、资产包、受控 SOP、表单与规则',
    views: [
      ['asset', '流程资产'], ['designer', '流程设计器'],
      ['deliverables', '交付物与模板库'], ['pilot', '十层核对'],
    ],
  },
  {
    no: '04',
    label: '作业与执行',
    flow: 'L4–L5 活动 → 工作流 / 审批流 / 作业资源 → ERP / OA',
    question: '资产能不能变成可执行的待办、审批与系统动作？',
    out: '产物：运行配置、任务实例、系统集成',
    views: [['execution', '流程执行']],
  },
  {
    no: '05',
    label: '度量与反馈',
    flow: '周期 / 等待 / 质量 / 成本 / 体验 + 证据观测 → 下一轮改善',
    question: '跑得怎么样？偏差在哪里？改善了多少？',
    out: '产物：KPI、日志实测、前后对照、改善项目',
    views: [['monitor', '流程分析'], ['projects', '流程项目组合'], ['workflow', '五阶段工作流']],
  },
];

function frameworkMapHtml() {
  const layers = FRAMEWORK_LAYERS.map((layer, index) => `
    <div class="fw-layer">
      <div class="fw-no">${layer.no}</div>
      <div class="fw-main">
        <div class="fw-hd"><b>${esc(layer.label)}</b>
          <span class="fw-flow">${esc(layer.flow)}</span></div>
        <div class="fw-q">${esc(layer.question)}</div>
        <div class="fw-actions">${layer.views.map(([view, label]) => (
          `<button class="btn btn-sm" data-act="start.go" data-view="${view}">${esc(label)}</button>`
        )).join('')}</div>
      </div>
      <div class="fw-out">${esc(layer.out)}</div>
    </div>
    ${index < FRAMEWORK_LAYERS.length - 1 ? '<div class="fw-arrow">↓</div>' : ''}`).join('');
  return `<div class="card fw-wrap">
    <div class="fw-head">
      <div>
        <h3>企业管理体系</h3>
        <p class="desc">流程不是目的，是让目标可控的一种实践。治理、证据和产物贯穿全过程。</p>
      </div>
      <span class="tag t-blu">客户价值 → 下一轮改善</span>
    </div>
    ${layers}
    <div class="fw-loop">↺ 度量回到目标与资产
      <button class="btn-sm" data-act="start.go" data-view="monitor">看流程分析</button>
      <button class="btn-sm" data-act="start.go" data-view="projects">开改善项目</button>
      <button class="btn-sm" data-act="start.go" data-view="asset">回流程资产</button>
    </div>
    <div class="fw-cross"><b>治理与支持贯穿始终</b>
      <button class="btn-sm" data-act="start.go" data-view="authorization">授权矩阵</button>
      <button class="btn-sm" data-act="start.go" data-view="toolbox">方法论工具箱</button>
      <button class="btn-sm" data-act="start.go" data-view="data">数据治理</button>
      <button class="btn-sm" data-act="start.go" data-view="cbok">CBOK</button>
      <button class="btn-sm" data-act="start.go" data-view="train">BPM 实训</button>
      <button class="btn-sm" data-act="start.go" data-view="bpmn">BPMN 符号</button>
    </div>
  </div>`;
}

/* -------------------------------------------------- 展示片段 */

function evidencePanel(step) {
  const items = step.evidence_items || [];
  const have = items.filter((item) => item.met);
  const missing = items.filter((item) => !item.met && item.required);
  const suggest = items.filter((item) => !item.met && !item.required);
  const row = (item) => {
    const params = new URLSearchParams(item.view_params || {}).toString();
    const title = TITLES[item.view] || item.label;
    return `
    <div class="ev-row ${item.met ? 'ok' : item.required ? 'miss' : 'opt'}">
      <span>${esc(item.label)}</span>
      <button type="button" class="ev-jump" data-act="start.evidence"
        data-view="${esc(item.view)}"${params ? ` data-params="${esc(params)}"` : ''}
        title="打开${esc(title)}">${item.value}</button>
    </div>`;
  };
  const group = (title, rows, cls) => `
    <div class="ev-group ${cls}">
      <span class="ev-h">${title}</span>
      ${rows.map(row).join('') || '<div class="tiny muted">—</div>'}
    </div>`;
  return `
    <aside class="start-evidence">
      <h4>这一步要留下什么</h4>
      ${group('已经有的', have, 'ok')}
      ${group('还缺的', missing, 'miss')}
      ${suggest.length ? group('建议补上', suggest, 'opt') : ''}
    </aside>`;
}

function actionAttrs(action) {
  if (action.action === 'start.guidedPcf') return 'data-act="start.guidedPcf"';
  const params = new URLSearchParams(action.view_params || {}).toString();
  return `data-act="start.go"${params ? ` data-params="${esc(params)}"` : ''}`;
}

/** 主按钮跟「第一条未满足的必需证据」走同一去向。 */
function primaryActionIndex(step) {
  const actions = step.actions || [];
  if (!actions.length) return -1;
  const missing = (step.evidence_items || []).find((item) => !item.met && item.required);
  if (!missing) return -1;
  const hit = actions.findIndex((action) => {
    if (action.view !== missing.view) return false;
    const want = missing.view_params || {};
    const got = action.view_params || {};
    return Object.keys(want).every((key) => String(got[key] || '') === String(want[key]));
  });
  if (hit >= 0) return hit;
  return actions.findIndex((action) => action.view === missing.view);
}

function stepActionsHtml(step) {
  const actions = step.actions || [];
  const primary = primaryActionIndex(step);
  if (!actions.length) return '';
  const missing = (step.evidence_items || []).find((item) => !item.met && item.required);
  if (!missing) {
    return `<div class="note mb">框架边界的必需证据已齐。</div>
      <div class="gap">${actions.map((action) => `<button class="btn btn-g"
        ${actionAttrs(action)} data-view="${esc(action.view)}"
        title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}</div>`;
  }
  return `<div class="gap">${actions.map((action, index) => {
    const cls = index === primary ? 'btn btn-p' : 'btn btn-g';
    return `<button class="${cls}" ${actionAttrs(action)}
      data-view="${esc(action.view)}"
      title="${esc(action.hint || '')}">${esc(action.label)}</button>`;
  }).join('')}</div>`;
}

function stepBody(step) {
  const points = (step.points || []).map((point) => `
    <li>
      <span class="start-point-label">${esc(point.label)}</span>
      <span>${esc(point.text)}</span>
    </li>`).join('');
  return `
    <div class="start-main">
      ${step.goal
        ? `<p class="start-kicker">这一步只回答</p><p class="start-goal">${esc(step.goal)}</p>`
        : ''}
      ${points ? `<ul class="start-points">${points}</ul>` : ''}
      ${step.next_hint ? `<p class="start-hint">${esc(step.next_hint)}</p>` : ''}
      ${stepActionsHtml(step)}
    </div>
    ${evidencePanel(step)}`;
}

function statusTag(step) {
  return `<span class="tag ${STATUS_TONE[step.status] || 't-gry'}">${esc(step.status_label)}</span>`;
}

function currentCard(step) {
  const missing = (step.evidence_items || []).some((item) => item.required && !item.met);
  const desc = missing
    ? '右边是流程地图要数的证据。主按钮打开第一条还缺的必需证据。'
    : '右边是流程地图要数的证据。必需项已经齐了。';
  return `
    <div class="card start-current">
      <div class="start-current-hd">
        <div>
          <h3>${esc(step.title)}</h3>
          <div class="desc">${desc}</div>
        </div>
        ${statusTag(step)}
      </div>
      ${stepBody(step)}
    </div>`;
}

function pathRollupCard(data) {
  const count = data.path_count || 0;
  const done = data.path_completed_count || 0;
  const avg = data.path_avg_layer || 0;
  return `
    <div class="card start-aside-card">
      <div class="tiny muted">单条流程的边界</div>
      <h3>${count ? `${count} 条十层路径` : '还没有十层路径'}</h3>
      <div class="tiny muted mt">${count
        ? `已完成 ${done} 条 · 平均到第 ${avg} 层。某一条流程从哪开始、到哪结束，在十层核对里写。`
        : '某一条流程从哪开始、到哪结束，去十层核对写。这里只数公司这张流程地图。'}</div>
      <button class="btn-sm mt" data-act="start.go" data-view="pilot">${
        count ? '打开十层核对' : '去建第一条路径'}</button>
    </div>`;
}

function paint(data, lifecycle, processes) {
  const step = (data.steps || [])[0];
  const ready = step && step.status === 'READY';
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>体系总览<span class="module-badge">企业管理体系 · 从价值到反馈</span>${tipHelp(
            '流程不是目的，是让目标可控的一种实践。先选你所在的一层：'
            + '目标、架构、资产、执行、度量，或治理支持。')}</h2>
          <p class="desc">首页图谱与侧栏按同一框架组织；每层都能进入对应页面办理。</p>
        </div>
        <span class="tag ${ready ? 't-grn' : 't-yel'}">${ready ? '最低框架条件已满足' : '最低框架条件待补充'}</span>
      </div>
    </div>
    ${frameworkMapHtml()}
    <div class="grid mt2" style="grid-template-columns:1.4fr .8fr;gap:14px;align-items:start">
      ${step ? currentCard(step) : ''}
      ${pathRollupCard(data)}
    </div>
    <details class="start-fold mt2">
      <summary><b>按任务导航 · BPM 八阶段</b>
        <span class="tiny muted">辅助入口，不是状态机；主线仍是上面的企业管理体系</span></summary>
      ${lifecycleHtml(lifecycle, processes)}
    </details>`;
}

/* -------------------------------------------------- 交互 */

on('start.go', ({ view, params }) => {
  if (!view) return;
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  go(view, Object.keys(parsed).length ? { params: parsed, push: true } : undefined);
});

on('start.evidence', ({ view, params }) => {
  if (!view) return;
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  go(view, { params: parsed, push: true });
});

on('start.guidedPcf', () => {
  state.map.openGuidedPcf = true;
  go('map');
});

const renderStart = () => {
  renderAsync(
    'start',
    () => Promise.all([GET('/start/status'), loadLifecycle(urlParams()), GET('/process-map/flat')]),
    ([data, lifecycle, processes]) => {
      state.start.data = data;
      paint(data, lifecycle, processes);
    },
  );
};

export { renderStart };
