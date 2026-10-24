/* 视图：开始使用
 *
 * 九步启动路径：默认只展开当前一步，其余步骤折叠。
 * readiness 由后端按真实证据计算；人工“跳过”只表示本轮不验证，不计入就绪。
 */

import { esc } from '../core/format.js';
import { viewEl, on, confirmDialog, promptDialog, toast } from '../core/ui.js';
import { renderAsync, go } from '../core/router.js';
import { GET, POST, DEL } from '../core/api.js';
import { state } from '../core/state.js';

const STATUS_TONE = {
  READY: 't-grn',
  IN_PROGRESS: 't-yel',
  NOT_STARTED: 't-gry',
  SKIPPED: 't-pur',
};
const RAIL_TONE = {
  READY: 'ok',
  IN_PROGRESS: 'warn',
  NOT_STARTED: 'gray',
  SKIPPED: 'purple',
};

function shortTitle(step) {
  return step.title.replace(/^\d+\.\s*/, '');
}

/* -------------------------------------------------- 展示片段 */

function evidencePanel(step) {
  const items = step.evidence_items || [];
  const have = items.filter((item) => item.met);
  const missing = items.filter((item) => !item.met && item.required);
  const suggest = items.filter((item) => !item.met && !item.required);
  const row = (item) => `
    <div class="ev-row ${item.met ? 'ok' : item.required ? 'miss' : 'opt'}">
      <span>${esc(item.label)}</span><b>${item.value}</b>
    </div>`;
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
      ${suggest.length ? group('有更好，没有也能先跑', suggest, 'opt') : ''}
      ${step.skipped ? `<div class="note mt">这次先不做，不算完成${
        step.skip_reason ? '；原因：' + esc(step.skip_reason) : ''}${
        step.skipped_by ? ' · ' + esc(step.skipped_by) : ''}</div>` : ''}
      <div class="gap mt">
        ${step.skipped
          ? `<button class="btn-sm" data-act="start.unskip" data-key="${esc(step.key)}">
               恢复这一阶段</button>`
          : `<button class="btn-sm" data-act="start.skip" data-key="${esc(step.key)}">
               这次先不做（标记未验证）</button>`}
      </div>
    </aside>`;
}

function actionAttrs(action) {
  return action.action === 'start.guidedPcf'
    ? 'data-act="start.guidedPcf"'
    : 'data-act="start.go"';
}

function stepBody(step) {
  return `
    <div class="start-main">
      <div class="start-meta">
        <div><span class="ev-h">输入</span><p>${esc(step.input)}</p></div>
        <div><span class="ev-h">输出</span><p>${esc(step.output)}</p></div>
        <div><span class="ev-h">退出条件</span><p>${esc(step.exit_criteria)}</p></div>
      </div>
      ${step.next_hint ? `<div class="note mb">${esc(step.next_hint)}</div>` : ''}
      <div class="gap">
        ${step.actions.map((action) => `<button class="btn btn-g"
          ${actionAttrs(action)} data-view="${esc(action.view)}"
          title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
      </div>
    </div>
    ${evidencePanel(step)}`;
}

function statusTag(step) {
  return `<span class="tag ${STATUS_TONE[step.status] || 't-gry'}">${esc(step.status_label)}</span>`;
}

function currentCard(step) {
  return `
    <div class="card start-current">
      <div class="start-current-hd">
        <div>
          <h3>${esc(step.title)}</h3>
          <div class="desc">${esc(step.goal)}</div>
        </div>
        <div class="gap">
          ${step.estimated ? `<span class="tag t-blu">预计 ${esc(step.estimated)}</span>` : ''}
          ${statusTag(step)}
        </div>
      </div>
      ${stepBody(step)}
    </div>`;
}

function upcomingList(steps) {
  if (!steps.length) return '';
  return `
    <div class="card">
      <div class="between mb">
        <h3>后续 ${steps.length} 步</h3>
        <span class="tiny muted">按顺序推进；展开可看输入、输出与证据</span>
      </div>
      <div class="start-upcoming">
        ${steps.map((step) => `
          <details class="start-step">
            <summary>
              ${statusTag(step)}
              <b>${esc(step.title)}</b>
              <span class="tiny muted">${esc(step.estimated || '')}</span>
              ${step.skipped ? '<span class="tag t-pur">未验证</span>' : ''}
            </summary>
            <div class="start-step-body">${stepBody(step)}</div>
          </details>`).join('')}
      </div>
    </div>`;
}

function doneList(steps) {
  if (!steps.length) return '';
  return `
    <div class="card">
      <div class="between mb">
        <h3>已经具备 / 这次先不做（${steps.length}）</h3>
        <span class="tiny muted">只有“已具备”计入完成；“这次先不做”不算</span>
      </div>
      <div class="start-done">
        ${steps.map((step) => `
          <div class="between">
            <span>${statusTag(step)} ${esc(step.title)}</span>
            <span class="gap">
              <span class="tiny muted">${esc(step.estimated || '')}</span>
              ${step.skipped
                ? `<button class="btn-sm" data-act="start.unskip"
                     data-key="${esc(step.key)}">恢复这一阶段</button>`
                : ''}
            </span>
          </div>`).join('')}
      </div>
    </div>`;
}

function completionCard(data) {
  const skipped = data.steps.filter((step) => step.status === 'SKIPPED').length;
  return `
    <div class="card start-complete">
      <h3>${skipped
        ? `能做的都做了 ${data.ready_count}/${data.total}`
        : `九个阶段都齐了 ${data.ready_count}/${data.total}`}</h3>
      <div class="desc">${skipped
        ? `其中 ${skipped} 个阶段标了“这次先不做”；进入运营后仍可回到本页恢复并补齐。`
        : '进入运营监控与流程卡持续运行；后续改善走同一条改善链，改完发布新版本。'}</div>
      <div class="gap">
        <button class="btn btn-p" data-act="start.go" data-view="dashboard">进入驾驶舱</button>
        <button class="btn btn-g" data-act="start.go" data-view="monitor">运营监控</button>
        <button class="btn btn-g" data-act="start.go" data-view="process_card">流程卡</button>
      </div>
    </div>`;
}

function pilotReadyBanner(data) {
  if (data.pilot_ready_count < data.pilot_total || data.ready_count >= data.total) return '';
  return `
    <div class="card start-complete">
      <h3>前 8 个阶段已齐，第一条流程可以上线</h3>
      <div class="desc">从“立项定界”到“评审与固化”都齐了；第 9 阶段“改善与复制”
        在运营中继续做，不挡上线。</div>
      <div class="gap">
        <button class="btn btn-p" data-act="start.go" data-view="dashboard">进入驾驶舱</button>
        <button class="btn btn-g" data-act="start.go" data-view="monitor">运营监控</button>
        <button class="btn btn-g" data-act="start.setupProjects">体系落地项目</button>
      </div>
    </div>`;
}

function paint(data) {
  const currentIndex = data.steps.findIndex(
    (step) => step.status !== 'READY' && step.status !== 'SKIPPED');
  const done = currentIndex < 0 ? data.steps : data.steps.slice(0, currentIndex);
  const current = currentIndex < 0 ? null : data.steps[currentIndex];
  const upcoming = currentIndex < 0 ? [] : data.steps.slice(currentIndex + 1);
  const pct = data.readiness_pct;

  const railFor = (steps) => steps.map((step) => `
    <div class="rail-step ${RAIL_TONE[step.status] || 'gray'}${
      current && current.key === step.key ? ' current' : ''}${
      step.pilot ? '' : ' is-improvement'}" title="${esc(step.title)} · ${esc(step.status_label)}">
      <span class="dot">${step.order + 1}</span>
      <b>${esc(shortTitle(step))}</b>
      <em>${esc(step.status_label)}</em>
    </div>`).join('');

  const phaseGroups = [
    { name: 'A 定方向', range: '阶段 1–3', steps: data.steps.slice(0, 3) },
    { name: 'B 建体系', range: '阶段 4–6', steps: data.steps.slice(3, 6) },
    { name: 'C 跑闭环', range: '阶段 7–9', steps: data.steps.slice(6, 9) },
  ];

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>开始使用<span class="module-badge">一条流程的试点路径</span></h2>
          <div class="desc">先把一条流程从立项走到评审固化；每个阶段只问一个问题，做完要留下看得见的东西。其他模块用到时再展开。</div>
        </div>
        <div class="gap">
          <span class="tag t-blu">能上线 ${data.pilot_ready_count}/${data.pilot_total}</span>
          <span class="tag ${data.ready_count >= data.total ? 't-grn' : 't-yel'}">
            ${data.ready_count}/${data.total} · ${pct}%</span>
        </div>
      </div>
      <div class="start-chain">战略 → 架构 → 组织 → 制度 → 流程 → 表单/工具 → 工作量 → 绩效 → 改善 → 新版本</div>
      <div class="tiny muted" style="margin-top:6px">统一原则 · 统一基线 · 分级授权 · 受控差异</div>
      <div class="start-phases">
        ${phaseGroups.map((group, index) => `
          <div class="phase-block phase-${index}">
            <div class="phase-label"><b>${group.name}</b><span>${group.range}</span></div>
            <div class="start-rail">${railFor(group.steps)}</div>
          </div>`).join('')}
      </div>
      <div class="pipe" style="margin-top:12px">
        <i class="fill-ok" style="width:${pct}%"></i>
      </div>
      <div class="between mt">
        <span class="tiny muted">
          前 8 个阶段（到“评审与固化”）齐了，第一条流程就能上线；第 9 阶段“改善与复制”
          在运营中持续做。这页看“该留下的东西齐不齐”，项目页看“事情做到哪一步”。
        </span>
        <button class="btn-sm" data-act="start.guidedPcf">1+3+10 建架构</button>
        <button class="btn-sm" data-act="start.setupProjects">体系落地项目 →</button>
      </div>
      ${data.skipped_count
        ? `<div class="note mt">${data.skipped_count} 个阶段标了“这次先不做”：不计入完成，也不挡后续；随时可以恢复。</div>`
        : ''}
    </div>
    ${pilotReadyBanner(data)}
    ${current ? currentCard(current) : completionCard(data)}
    ${doneList(done)}
    ${upcomingList(upcoming)}`;
}

/* -------------------------------------------------- 交互 */

on('start.go', ({ view }) => go(view));

on('start.guidedPcf', () => {
  state.map.openGuidedPcf = true;
  go('map');
});

on('start.setupProjects', () => {
  state.projects.filter = {
    methodology: '', status: '', stage: '', projectType: 'GOVERNANCE_SETUP',
  };
  state.projects.keyword = '';
  go('projects');
});

on('start.skip', async ({ key }) => {
  const reason = await promptDialog(
    '“这次先不做”只表示本轮不验证，不算完成；请说明原因（可留空）。',
    { title: '这次先不做', okText: '确认', value: '' },
  );
  if (reason === undefined) return;
  try {
    const data = await POST('/start/steps/' + encodeURIComponent(key) + '/skip',
      { reason: reason || null });
    state.start.data = data;
    paint(data);
    toast('已标记为这次先不做');
  } catch (e) {
    toast(e.message, true);
  }
});

on('start.unskip', async ({ key }) => {
  const ok = await confirmDialog('恢复后该阶段会重新按现有数据判定。',
    { title: '恢复阶段', okText: '恢复' });
  if (!ok) return;
  try {
    const data = await DEL('/start/steps/' + encodeURIComponent(key) + '/skip');
    state.start.data = data;
    paint(data);
    toast('已恢复这一阶段');
  } catch (e) {
    toast(e.message, true);
  }
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
