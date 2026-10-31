/* 视图：开始使用
 *
 * 公司流程体系的唯一主入口：九个阶段、全公司计数。
 * 点非当前阶段只是查看证据；就绪由后端按证据算；「这次先不做」不计入就绪。
 */

import { esc, dtShort, tipHelp } from '../core/format.js';
import { viewEl, on, confirmDialog, promptDialog, toast } from '../core/ui.js';
import { renderAsync, go } from '../core/router.js';
import { GET, POST, DEL } from '../core/api.js';
import { state, TITLES } from '../core/state.js';

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
      ${step.skipped ? `<div class="note mt">这次先不做：时间线会跳过；确认上线仍要它变成已具备${
        step.skip_reason ? '；原因：' + esc(step.skip_reason) : ''}${
        step.skipped_by ? ' · ' + esc(step.skipped_by) : ''}</div>` : ''}
      <div class="gap mt">
        ${step.skipped
          ? `<button class="btn-sm" data-act="start.unskip" data-key="${esc(step.key)}">
               恢复这一阶段</button>`
          : `<button class="btn-sm" data-act="start.skip" data-key="${esc(step.key)}">
               这次先不做</button>`}
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
      ${step.next_hint
        ? `<p class="start-hint">${esc(step.next_hint)}</p>`
        : ''}
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

function currentCard(step, flat = false) {
  return `
    <div class="${flat ? 'start-current start-current-flat' : 'card start-current'}">
      <div class="start-current-hd">
        <div>
          <h3>${esc(step.title)}</h3>
          <div class="desc">只看右侧计数。全公司达到门槛，这一阶段才算已具备。</div>
        </div>
        <div class="gap">
          ${step.estimated ? `<span class="tag t-blu">预计 ${esc(step.estimated)}</span>` : ''}
          ${statusTag(step)}
        </div>
      </div>
      ${stepBody(step)}
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
        ? `其中 ${skipped} 个阶段标了“这次先不做”。时间线会跳过它们，确认上线仍要它们变成已具备。`
        : '进入运营驾驶舱与流程卡持续运行；后续改善走同一条改善链，改完发布新版本。'}</div>
      <div class="gap">
        <button class="btn btn-p" data-act="start.go" data-view="dashboard">运营驾驶舱（总览）</button>
        <button class="btn btn-g" data-act="start.go" data-view="monitor">运营驾驶舱（KPI）</button>
        <button class="btn btn-g" data-act="start.go" data-view="process_card">流程卡</button>
      </div>
    </div>`;
}

function pilotGateCard(data) {
  if (data.pilot_confirmed) {
    const stale = data.pilot_stale
      ? `<div class="note mb">证据已变化，当前不再满足上线条件：${
        data.pilot_missing_steps.map(esc).join('、')}。请补齐后重新确认。</div>`
      : '';
    return `
      <div class="card start-complete">
        <h3>首次上线已确认</h3>
        <div class="desc">确认人：${esc(data.pilot_confirmed_by || '—')} · ${
          dtShort(data.pilot_confirmed_at)}${
          data.pilot_confirm_note ? ' · ' + esc(data.pilot_confirm_note) : ''}</div>
        ${stale}
        <div class="gap">
          <button class="btn btn-p" data-act="start.go" data-view="dashboard">进入驾驶舱</button>
          <button class="btn btn-g" data-act="start.revokePilot">撤销确认</button>
        </div>
      </div>`;
  }
  if (!data.pilot_gate_open) return '';
  return `
    <div class="card start-complete">
      <h3>前 8 个阶段已齐，可以确认上线</h3>
      <div class="desc">从「立项定界」到「评审与固化」都齐了；确认后默认首页切到驾驶舱。
        第 9 阶段「改善与复制」在运营中继续。</div>
      <div class="gap">
        <button class="btn btn-p" data-act="start.confirmPilot">确认首次上线</button>
        <button class="btn btn-g" data-act="start.setupProjects">体系落地项目</button>
      </div>
    </div>`;
}

/* -------------------------------------------------- 九个阶段 */

function openStage(data) {
  return data.steps.find((step) => step.status !== 'READY' && step.status !== 'SKIPPED') || null;
}

function viewedStage(data) {
  const current = openStage(data);
  const picked = data.steps.find((step) => step.key === state.start.stageKey);
  return picked || current || data.steps[data.steps.length - 1];
}

function stageNav(data, viewed, current) {
  return `
    <div class="card start-nav">
      <div class="start-nav-layer">阶段</div>
      ${data.steps.map((step) => `
        <button type="button" class="start-nav-item${step.key === viewed.key ? ' on' : ''}"
          data-act="start.selectStage" data-key="${esc(step.key)}">
          <span class="nav-dot ${RAIL_TONE[step.status] || 'gray'}"></span>
          <span>${esc(shortTitle(step))}</span>
          ${current && current.key === step.key ? '<span class="tl-now">当前</span>' : ''}
        </button>`).join('')}
    </div>`;
}

function timeline(data, viewed, current) {
  const parts = [];
  data.steps.forEach((step, index) => {
    const visual = step.status === 'READY'
      ? 'done'
      : step.status === 'SKIPPED'
        ? 'skipped'
        : current && current.key === step.key
          ? 'current'
          : 'future';
    const mark = visual === 'done' ? '✓' : visual === 'skipped' ? '–' : index + 1;
    parts.push(`
      <button type="button" class="tl-step ${visual}${step.key === viewed.key ? ' viewing' : ''}"
        data-act="start.selectStage" data-key="${esc(step.key)}"
        title="${esc(step.title)} · ${esc(step.status_label)}">
        <span class="tl-dot">${mark}</span>
        <span class="tl-label">${esc(shortTitle(step))}</span>
        ${current && current.key === step.key ? '<span class="tl-now">当前</span>' : ''}
        ${visual === 'skipped' ? '<span class="tl-skip">未验证</span>' : ''}
      </button>`);
    if (index < data.steps.length - 1) {
      parts.push(`<span class="tl-line ${step.status === 'READY' ? 'done' : ''}"></span>`);
    }
  });
  return `
    <div class="card start-rail-card">
      <div class="between mb"><h3>9 个阶段</h3>
        <span class="tiny muted">点阶段可查看证据；公司停在「当前」那一步</span></div>
      <div class="start-timeline">${parts.join('')}</div>
    </div>`;
}

function skippedFold(data) {
  const skipped = data.steps.filter((step) => step.skipped);
  if (!skipped.length) return '';
  return `
    <details class="card start-fold">
      <summary><span>这次先不做（${skipped.length}）</span>
        <span class="tiny muted">时间线会跳过；确认上线仍要它变成已具备</span></summary>
      <div class="start-done">
        ${skipped.map((step) => `
          <div class="between">
            <span>${statusTag(step)} ${esc(step.title)}</span>
            <button class="btn-sm" data-act="start.unskip" data-key="${esc(step.key)}">恢复这一阶段</button>
          </div>`).join('')}
      </div>
    </details>`;
}

function goLiveCard(data) {
  const readyCard = pilotGateCard(data);
  if (readyCard) return readyCard;
  const missing = data.pilot_missing_steps || [];
  return `
    <div class="card start-aside-card">
      <h3>确认上线</h3>
      <div class="tiny muted">前 8 个阶段（到评审与固化）都要变成已具备。第 9 阶段不挡上线。这次先不做不算已具备。</div>
      <div class="tiny muted mt">还差 ${missing.length} 个阶段：</div>
      <div class="gap">${missing.map((title) => `<span class="tag t-yel">${esc(title)}</span>`).join('')}</div>
    </div>`;
}

function paint(data) {
  const current = openStage(data);
  const viewed = viewedStage(data);
  const viewingOther = current && viewed.key !== current.key;
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>开始使用<span class="module-badge">唯一主入口 · 公司流程体系</span>${tipHelp(
            '证据按全公司计数。多数项大于 0 就算具备；权责冲突、未闭环治理待办、未关闭的授权例外要等于 0。'
            + '当前位置是第一个还没就绪、也没标成这次先不做的阶段。'
            + '确认上线只认前 8 个阶段都已具备。这次先不做的阶段，时间线会跳过，上线确认仍把它当成还没具备。')}</h2>
        </div>
        <div class="gap">
          <span class="tag t-blu">${current
            ? '当前 ' + esc(shortTitle(current))
            : '时间线已走完'}</span>
          <span class="tag ${data.pilot_gate_open ? 't-grn' : 't-yel'}">上线 ${
            data.pilot_ready_count}/${data.pilot_total}</span>
        </div>
      </div>
    </div>
    ${timeline(data, viewed, current)}
    <div class="start-shell">
      <aside class="start-side">${stageNav(data, viewed, current)}</aside>
      <main class="start-center">
        ${viewingOther
          ? `<div class="note mb">公司现在停在「${esc(current.title)}」。下面是「${esc(viewed.title)}」的证据。</div>`
          : ''}
        ${current ? '' : completionCard(data)}
        ${currentCard(viewed)}
      </main>
      <aside class="start-aside">
        <div class="card start-aside-card">
          <div class="tiny muted">当前位置</div>
          <h3>${current ? esc(shortTitle(current)) : '时间线已走完'}</h3>
          ${current
            ? `<button class="btn-sm mt" data-act="start.selectStage" data-key="${esc(current.key)}">看当前阶段</button>`
            : ''}
        </div>
        ${goLiveCard(data)}
        ${skippedFold(data)}
      </aside>
    </div>`;
}

/* -------------------------------------------------- 交互 */

on('start.go', ({ view }) => go(view));

on('start.evidence', ({ view, params }) => {
  if (!view) return;
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  go(view, { params: parsed, push: true });
});

on('start.selectStage', ({ key }) => {
  if (!key) return;
  state.start.stageKey = key;
  if (state.start.data) paint(state.start.data);
});

on('start.guidedPcf', () => {
  state.map.openGuidedPcf = true;
  go('map');
});

on('start.confirmPilot', async () => {
  const note = await promptDialog('上线备注（可留空）',
    { title: '确认首次上线', okText: '确认', value: '' });
  if (note === undefined) return;
  try {
    const data = await POST('/start/pilot/confirm', { note: note || null });
    state.start.data = data;
    paint(data);
    toast('已确认首次上线');
  } catch (e) {
    toast(e.message, true);
  }
});

on('start.revokePilot', async () => {
  const ok = await confirmDialog('撤销后默认首页会回到开始使用，确定继续？',
    { title: '撤销首次上线', okText: '撤销', danger: true });
  if (!ok) return;
  try {
    const data = await DEL('/start/pilot/confirm');
    state.start.data = data;
    paint(data);
    toast('已撤销首次上线确认');
  } catch (e) {
    toast(e.message, true);
  }
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
    '时间线会跳过这一阶段。确认上线仍要它变成已具备。请说明原因（可留空）。',
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
