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
      <h4>出门证据</h4>
      ${group('已具备', have, 'ok')}
      ${group('仍缺（必需）', missing, 'miss')}
      ${suggest.length ? group('建议补充', suggest, 'opt') : ''}
      ${step.skipped ? `<div class="note mt">已跳过，未计入就绪${
        step.skip_reason ? '；原因：' + esc(step.skip_reason) : ''}${
        step.skipped_by ? ' · ' + esc(step.skipped_by) : ''}</div>` : ''}
      <div class="gap mt">
        ${step.skipped
          ? `<button class="btn-sm" data-act="start.unskip" data-key="${esc(step.key)}">
               取消跳过</button>`
          : `<button class="btn-sm" data-act="start.skip" data-key="${esc(step.key)}">
               跳过本步（标记未验证）</button>`}
      </div>
    </aside>`;
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
          data-act="start.go" data-view="${esc(action.view)}"
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
        <h3>已完成 / 已跳过（${steps.length}）</h3>
        <span class="tiny muted">就绪度按“已就绪”计数，跳过不算完成</span>
      </div>
      <div class="start-done">
        ${steps.map((step) => `
          <div class="between">
            <span>${statusTag(step)} ${esc(step.title)}</span>
            <span class="gap">
              <span class="tiny muted">${esc(step.estimated || '')}</span>
              ${step.skipped
                ? `<button class="btn-sm" data-act="start.unskip"
                     data-key="${esc(step.key)}">取消跳过</button>`
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
        ? `九步已推进完 ${data.ready_count}/${data.total}`
        : `九步已全部就绪 ${data.ready_count}/${data.total}`}</h3>
      <div class="desc">${skipped
        ? `其中 ${skipped} 步标记为未验证；进入运营后仍可在本页取消跳过并补齐证据。`
        : '进入运营监控与流程卡持续运行；后续改善走受控变更与版本发布。'}</div>
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
      <h3>首次上线已就绪 ${data.pilot_ready_count}/${data.pilot_total}</h3>
      <div class="desc">S0–S7 已具备出门证据，可以进入日常运营；
        S8 改善闭环不阻塞首次上线，继续在运营中推进。</div>
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

  const rail = data.steps.map((step) => `
    <div class="rail-step ${RAIL_TONE[step.status] || 'gray'}${
      current && current.key === step.key ? ' current' : ''}${
      step.pilot ? '' : ' is-improvement'}" title="${esc(step.title)} · ${esc(step.status_label)}">
      <span class="dot">${step.order + 1}</span>
      <b>${esc(shortTitle(step))}</b>
      <em>${esc(step.status_label)}</em>
    </div>`).join('');

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>开始使用<span class="module-badge">九步启动路径</span></h2>
          <div class="desc">从范围与授权到改善复制，每一步只回答一个问题；状态由现有数据计算</div>
        </div>
        <div class="gap">
          <span class="tag t-blu">首次上线 ${data.pilot_ready_count}/${data.pilot_total}</span>
          <span class="tag ${data.ready_count >= data.total ? 't-grn' : 't-yel'}">
            ${data.ready_count}/${data.total} · ${pct}%</span>
        </div>
      </div>
      <div class="start-rail">${rail}</div>
      <div class="pipe" style="margin-top:12px">
        <i class="fill-ok" style="width:${pct}%"></i>
      </div>
      <div class="between mt">
        <span class="tiny muted">
          首次上线 = S0–S7（8 步，含制度与授权）；S8 改善闭环不阻塞日常运营。
          体系就绪度 ≠ 项目进度，9 阶段 / 27 步的执行进度在项目里单独管理。
        </span>
        <button class="btn-sm" data-act="start.setupProjects">体系落地项目 →</button>
      </div>
      ${data.skipped_count
        ? `<div class="note mt">${data.skipped_count} 步已跳过：跳过表示“未验证”，不计入就绪，也不阻塞后续步骤。</div>`
        : ''}
    </div>
    ${pilotReadyBanner(data)}
    ${current ? currentCard(current) : completionCard(data)}
    ${doneList(done)}
    ${upcomingList(upcoming)}`;
}

/* -------------------------------------------------- 交互 */

on('start.go', ({ view }) => go(view));

on('start.setupProjects', () => {
  state.projects.filter = {
    methodology: '', status: '', stage: '', projectType: 'GOVERNANCE_SETUP',
  };
  state.projects.keyword = '';
  go('projects');
});

on('start.skip', async ({ key }) => {
  const reason = await promptDialog(
    '跳过只表示本轮不验证该步骤，不会算作就绪；请说明原因（可留空）。',
    { title: '跳过步骤', okText: '跳过', value: '' },
  );
  if (reason === undefined) return;
  try {
    const data = await POST('/start/steps/' + encodeURIComponent(key) + '/skip',
      { reason: reason || null });
    state.start.data = data;
    paint(data);
    toast('已标记为未验证');
  } catch (e) {
    toast(e.message, true);
  }
});

on('start.unskip', async ({ key }) => {
  const ok = await confirmDialog('取消后该步骤会重新按现有数据判定。',
    { title: '取消跳过', okText: '取消跳过' });
  if (!ok) return;
  try {
    const data = await DEL('/start/steps/' + encodeURIComponent(key) + '/skip');
    state.start.data = data;
    paint(data);
    toast('已取消跳过');
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
