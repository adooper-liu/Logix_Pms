/* 视图：开始使用
 *
 * 只回答公司流程地图的框架边界：哪些工作进这张图，上下级怎么挂，谁有权改图。
 * 某一条流程从哪开始、到哪结束，去十层核对。
 */

import { esc, tipHelp } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { renderAsync, go } from '../core/router.js';
import { GET } from '../core/api.js';
import { state, TITLES } from '../core/state.js';

const STATUS_TONE = {
  READY: 't-grn',
  IN_PROGRESS: 't-yel',
  NOT_STARTED: 't-gry',
  SKIPPED: 't-pur',
};

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
      ${lifecycleStrip()}
      ${step.next_hint ? `<p class="start-hint">${esc(step.next_hint)}</p>` : ''}
      ${stepActionsHtml(step)}
    </div>
    ${evidencePanel(step)}`;
}

function lifecycleStrip() {
  const steps = [
    ['strategy', '战略对齐', '战略目标'],
    ['pcf', '流程架构', 'APQC'],
    ['designer', '建模', '设计器'],
    ['monitor', '分析', '流程分析', 'tab=analysis'],
    ['designer', '设计', '设计器'],
    ['execution', '执行', '流程执行'],
    ['dashboard', '监控度量', '驾驶舱'],
    ['projects', '变革优化', '项目组合'],
    ['authorization', '治理', '授权矩阵'],
  ];
  const buttons = steps.map(([view, title, where, params]) => `
    <button type="button" class="life-step" data-act="start.go" data-view="${view}"${
      params ? ` data-params="${params}"` : ''}>
      <b>${esc(title)}</b><span class="tiny">${esc(where)}</span>
    </button>`).join('');
  return `<p class="start-kicker">公司体系按这个顺序走</p><div class="life-row">${buttons}</div>`;
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

function paint(data) {
  const step = (data.steps || [])[0];
  const ready = step && step.status === 'READY';
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>开始使用<span class="module-badge">唯一主入口 · 公司流程地图</span>${tipHelp(
            '数的是全公司这张流程地图：至少一条 L3 同时有 L1、L2 上级并对上 PCF，'
            + '并且至少一个治理角色启用且有成员。')}</h2>
        </div>
        <span class="tag ${ready ? 't-grn' : 't-yel'}">${ready ? '框架边界已划清' : '框架边界还没划清'}</span>
      </div>
    </div>
    ${step ? currentCard(step) : ''}
    ${pathRollupCard(data)}`;
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
    () => GET('/start/status'),
    (data) => {
      state.start.data = data;
      paint(data);
    },
  );
};

export { renderStart };
