/* 视图：开始使用
 *
 * 九步启动路径：默认只展开当前一步，其余步骤折叠。
 * readiness 由后端按真实证据计算；人工“跳过”只表示本轮不验证，不计入就绪。
 */

import { esc, dtShort, tipHelp } from '../core/format.js';
import { viewEl, on, confirmDialog, promptDialog, toast } from '../core/ui.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
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

function currentCard(step, flat = false) {
  return `
    <div class="${flat ? 'start-current start-current-flat' : 'card start-current'}">
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
    <details class="card start-fold">
      <summary><span>后续 ${steps.length} 个阶段</span>
        <span class="tiny muted">按顺序推进；展开可看输入、输出与证据</span></summary>
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
    </details>`;
}

function doneList(steps) {
  if (!steps.length) return '';
  return `
    <details class="card start-fold">
      <summary><span>已经具备 / 这次先不做（${steps.length}）</span>
        <span class="tiny muted">只有“已具备”计入完成；“这次先不做”不算</span></summary>
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
    </details>`;
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

function pilotGateCard(data) {
  if (data.pilot_confirmed) {
    const stale = data.pilot_stale
      ? `<div class="note mb">证据已变化，当前不再满足上线条件：${
        data.pilot_missing_steps.map(esc).join('、')}。请补齐后重新确认。</div>`
      : '';
    return `
      <div class="card start-complete">
        <h3>第一条流程已确认上线</h3>
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
      <div class="desc">从“立项定界”到“评审与固化”都齐了；确认后默认首页切到驾驶舱，
        第 9 阶段“改善与复制”在运营中继续。</div>
      <div class="gap">
        <button class="btn btn-p" data-act="start.confirmPilot">确认首次上线</button>
        <button class="btn btn-g" data-act="start.setupProjects">体系落地项目</button>
      </div>
    </div>`;
}

/* -------------------------------------------------- 三栏八问 */

function evidenceByName(step) {
  return Object.fromEntries((step.evidence_items || []).map((item) => [item.key, item]));
}

function valueOf(step, key) {
  const item = evidenceByName(step)[key];
  return item ? item.value : 0;
}

function chipsFor(step, keys) {
  if (!step) return '';
  const map = evidenceByName(step);
  return keys.map((key) => {
    const item = map[key];
    if (!item) return '';
    const tone = item.met ? 't-grn' : item.required ? 't-red' : 't-gry';
    return `<span class="tag ${tone}">${esc(item.label)} ${item.value}</span>`;
  }).join(' ');
}

function missingAll(data) {
  const seen = new Set();
  const rows = [];
  for (const step of data.steps) {
    for (const item of step.evidence_items || []) {
      if (!item.required || item.met || seen.has(item.key)) continue;
      seen.add(item.key);
      rows.push({ ...item, stepKey: step.key, stepTitle: step.title });
    }
  }
  return rows;
}

const GAP_GROUPS = [
  { name: '共同语言', keys: ['l1', 'l2', 'l3', 'pcf_mapped_l3', 'benchmark_maps'] },
  {
    name: '角色与权责',
    keys: ['l3_with_owner', 'governance_roles', 'positions', 'raci_matters', 'invalid_processes'],
  },
  { name: '制度与授权', keys: ['effective_documents', 'effective_authorization_rules'] },
  { name: '方法与工具', keys: ['forms', 'bindings', 'rules', 'node_tools'] },
  {
    name: '目标与指标',
    keys: [
      'objectives', 'linked_objectives', 'objectives_with_owner', 'objectives_with_baseline',
      'kpi_cards', 'kpi_records', 'verified_standards', 'capacity_rows',
    ],
  },
  {
    name: '改善与版本',
    keys: ['improvement_projects', 'applied_changes', 'open_findings', 'l3_published'],
  },
];

function gapGroups(data) {
  const missing = new Map(missingAll(data).map((item) => [item.key, item]));
  return GAP_GROUPS.map((group) => ({
    name: group.name,
    items: group.keys.map((key) => missing.get(key)).filter(Boolean),
  }));
}

function questionCard({ id, no, title, map, status, answer, chips, extra, actions, deps }) {
  return `
    <div class="card start-q" id="${id}">
      <div class="start-q-hd">
        <span class="start-q-no">${no}</span>
        <div class="start-q-title"><h3>${esc(title)}</h3>
          <span class="tiny muted">${esc(map)}</span></div>
        <div class="start-q-status">${status || ''}</div>
      </div>
      <div class="start-q-answer">${chips || answer}</div>
      ${deps ? `<div class="start-deps">${deps}</div>` : ''}
      ${extra || ''}
      ${actions ? `<div class="gap mt">${actions}</div>` : ''}
    </div>`;
}

function viewButton(label, view, cls = 'btn btn-g') {
  return `<button class="${cls}" data-act="start.go" data-view="${esc(view)}">${esc(label)}</button>`;
}

function depsHtml(prev, input, output, next) {
  return `<span><b>前置</b>${esc(prev)}</span>`
    + `<span><b>输入</b>${esc(input)}</span>`
    + `<span><b>输出</b>${esc(output)}</span>`
    + `<span><b>下一步</b>${esc(next)}</span>`;
}

function navDot(step) {
  if (!step) return '<span class="nav-dot gray"></span>';
  return `<span class="nav-dot ${RAIL_TONE[step.status] || 'gray'}"></span>`;
}

function navItem(target, label, step, active) {
  return `<button class="start-nav-item${active ? ' on' : ''}"
    data-act="start.selectQ" data-q="${target}">
    ${navDot(step)}<span>${esc(label)}</span></button>`;
}

function paint(data) {
  const byKey = Object.fromEntries(data.steps.map((step) => [step.key, step]));
  const currentIndex = data.steps.findIndex(
    (step) => step.status !== 'READY' && step.status !== 'SKIPPED');
  const done = currentIndex < 0 ? data.steps : data.steps.slice(0, currentIndex);
  const current = currentIndex < 0 ? null : data.steps[currentIndex];
  const upcoming = currentIndex < 0 ? [] : data.steps.slice(currentIndex + 1);
  const pct = data.readiness_pct;
  const gaps = gapGroups(data);
  const missing = missingAll(data);
  const missingCount = missing.length;

  const strategy = byKey.strategy;
  const arch = byKey.architecture;
  const policy = byKey.policy;
  const design = byKey.process_design;
  const perf = byKey.performance;

  const q1Missing = (strategy.evidence_items || []).filter((item) => item.required && !item.met);
  const q1 = questionCard({
    id: 'q1', no: 'Q1', title: '要什么', map: '战略地图', status: statusTag(strategy),
    deps: depsHtml('无（从这里开始）', '年度经营计划、现状数据', '目标卡 + 现状基线',
      'Q2 有什么'),
    answer: strategy.status === 'READY'
      ? '目标、目标值和现状基线都已挂到这条流程上。'
      : `还缺 ${q1Missing.length} 项：${q1Missing.map((item) => esc(item.label)).join('、')}。`,
    chips: chipsFor(strategy, [
      'objectives', 'linked_objectives', 'objectives_with_owner', 'objectives_with_baseline',
    ]),
    actions: viewButton('去定目标', 'strategy'),
  });

  const q2 = questionCard({
    id: 'q2', no: 'Q2', title: '有什么', map: '价值流地图', status: statusTag(arch),
    deps: depsHtml('Q1 战略目标', '流程地图、组织、制度、工具', '资产盘点',
      'Q3 还缺什么'),
    answer: `已有 ${valueOf(arch, 'l1')} 个 L1、${valueOf(arch, 'l2')} 个 L2、`
      + `${valueOf(arch, 'l3')} 个 L3；${valueOf(arch, 'positions')} 个岗位、`
      + `${valueOf(policy, 'documents')} 份制度/文件、${valueOf(design, 'forms')} 份表单、`
      + `${valueOf(perf, 'kpi_cards')} 张完整 KPI 卡。`,
    chips: chipsFor(arch, ['l1', 'l2', 'l3', 'positions'])
      + chipsFor(policy, ['documents']) + chipsFor(design, ['forms'])
      + chipsFor(perf, ['kpi_cards']),
    actions: viewButton('看流程地图', 'map') + viewButton('看组织与人员', 'orgs'),
  });

  const gapChips = gaps.filter((group) => group.items.length)
    .map((group) => `<span class="tag t-red">${esc(group.name)} ${group.items.length}</span>`)
    .join(' ');
  const topMissing = missing.slice(0, 6)
    .map((item) => `<span class="tag t-red">${esc(item.label)}</span>`).join(' ');
  const q3 = questionCard({
    id: 'q3', no: 'Q3', title: '还缺什么', map: '差距地图',
    deps: depsHtml('Q1–Q2', '全部必需证据', '缺口清单',
      'Q4 做什么 / Q7 当前阶段'),
    status: missingCount
      ? `<span class="tag t-yel">还缺 ${missingCount} 项</span>`
      : '<span class="tag t-grn">必需证据已齐</span>',
    answer: missingCount
      ? `还缺 ${missingCount} 项必需证据。先补最影响上线的那几项。`
      : '必需证据已经齐了；可以继续往下走或直接确认上线。',
    chips: gapChips || '<span class="tag t-grn">没有必需缺口</span>',
    extra: `${topMissing ? `<div class="gap mt">${topMissing}</div>` : ''}
      <div class="start-gap-note">三问法：有没有必要做 · 有没有标准 · 有没有证据</div>`,
    actions: '<button class="btn btn-g" data-act="start.jump" data-target="q7">看当前阶段</button>',
  });

  const q4 = questionCard({
    id: 'q4', no: 'Q4', title: '做什么', map: '流程地图', status: statusTag(arch),
    deps: depsHtml('Q1 / Q3', 'PCF、流程清单', 'L1–L3 + PCF 映射',
      'Q5 输入什么'),
    answer: `L1 ${valueOf(arch, 'l1')} · L2 ${valueOf(arch, 'l2')} · L3 ${valueOf(arch, 'l3')}；`
      + `已对应 PCF 的 L3 ${valueOf(arch, 'pcf_mapped_l3')} 个。`,
    chips: chipsFor(arch, ['l1', 'l2', 'l3', 'pcf_mapped_l3', 'benchmark_maps']),
    actions: viewButton('去建流程地图', 'map') + viewButton('看 PCF', 'pcf')
      + '<button class="btn btn-g" data-act="start.guidedPcf">1+3+10 建架构</button>',
  });

  const q5 = questionCard({
    id: 'q5', no: 'Q5', title: '输入什么', map: '岗位地图', status: statusTag(arch),
    deps: depsHtml('Q4 流程地图', '组织树、岗位', 'RACI / 岗位边界',
      'Q6 用什么'),
    answer: `岗位 ${valueOf(arch, 'positions')} 个；RACI 关键事项 `
      + `${valueOf(arch, 'raci_matters')} 个；权责冲突 ${valueOf(arch, 'invalid_processes')} 个。`,
    chips: chipsFor(arch, ['positions', 'raci_matters', 'invalid_processes']),
    extra: '<div class="tiny muted">每个关键事项只能有一个 A；输入、处理、审核、交付都要落到岗位或角色。</div>',
    actions: viewButton('去配组织', 'orgs') + viewButton('去配权责', 'designer'),
  });

  const q6 = questionCard({
    id: 'q6', no: 'Q6', title: '用什么', map: '方法工具箱', status: statusTag(design),
    deps: depsHtml('Q5 权责', '控制点、表单字段、工具', '表单/规则/工具绑定',
      'Q7 输出什么'),
    answer: `表单 ${valueOf(design, 'forms')} 份 · 规则 ${valueOf(design, 'rules')} 条 · `
      + `工具绑定 ${valueOf(design, 'node_tools')} 个；累计绑定 ${valueOf(design, 'bindings')} 项。`,
    chips: chipsFor(design, ['forms', 'rules', 'node_tools', 'bindings']),
    extra: '<div class="tiny muted">先问问题，再选工具；不能改变现场行为的工具不引入。</div>',
    actions: viewButton('去画流程', 'designer') + viewButton('看方法工具箱', 'toolbox'),
  });

  const timelineParts = [];
  data.steps.forEach((step, index) => {
    const isCurrent = !!current && current.key === step.key;
    const state = step.status === 'READY'
      ? 'done'
      : step.status === 'SKIPPED'
        ? 'skipped'
        : isCurrent
          ? 'current'
          : 'future';
    const mark = state === 'done' ? '✓' : state === 'skipped' ? '–' : step.order + 1;
    timelineParts.push(`
      <div class="tl-step ${state}"
        title="${esc(step.title)} · ${esc(step.status_label)}">
        <span class="tl-dot">${mark}</span>
        <span class="tl-label">${esc(shortTitle(step))}</span>
        ${isCurrent ? '<span class="tl-now">当前</span>' : ''}
        ${state === 'skipped' ? '<span class="tl-skip">未验证</span>' : ''}
      </div>`);
    if (index < data.steps.length - 1) {
      timelineParts.push(
        `<span class="tl-line ${step.status === 'READY' ? 'done' : ''}"></span>`);
    }
  });
  const railCard = `
    <div class="card start-rail-card">
      <div class="between mb"><h3>执行层：9 个阶段</h3>
        <span class="tiny muted">蓝勾 = 已具备 · 圆环 = 当前全局证据阶段 · 灰 = 还没开始</span></div>
      <div class="start-timeline">${timelineParts.join('')}</div>
    </div>`;

  const q7 = questionCard({
    id: 'q7', no: 'Q7', title: '输出什么', map: '证据地图',
    deps: depsHtml('Q6 方法/工具', '当前阶段证据', '证据清单',
      'Q8 下一步'),
    status: current ? statusTag(current) : '<span class="tag t-grn">全部完成</span>',
    answer: current
      ? `全局证据进度${tipHelp(
        '全局 = 全公司流程/制度/授权/工时/KPI 的证据汇总，不限定某一条试点路径；'
        + '这里不是项目当前层。当前阶段和状态见下方「展开当前阶段工作区」。')}`
      : '全局证据进度：九个阶段都已具备或标记为本次不做。',
    extra: current
      ? `<details class="start-subfold" id="pilot-current-stage"${
        state.start.openStage ? ' open' : ''}>
          <summary><span>展开当前阶段工作区</span>
            <span class="tiny muted">${esc(current.title)} · ${esc(current.status_label)}</span>
          </summary>
          ${currentCard(current, true)}
        </details>`
      : completionCard(data),
    actions: current
      ? '<button class="btn btn-g" data-act="start.jump" data-target="q8">看退出门和下一步</button>'
        + viewButton('打开十层单页', 'pilot')
      : viewButton('打开十层单页', 'pilot'),
  });

  const gateStatus = data.pilot_confirmed
    ? '<span class="tag t-grn">已确认上线</span>'
    : data.pilot_gate_open
      ? '<span class="tag t-blu">可确认上线</span>'
      : `<span class="tag t-yel">还差 ${data.pilot_missing_steps.length} 个阶段</span>`;
  const q8 = questionCard({
    id: 'q8', no: 'Q8', title: '下一步', map: '下一层地图', status: gateStatus,
    deps: depsHtml('Q7 证据', '退出门', '下一阶段 / 上线确认',
      '十层单页 / 项目详情'),
    answer: current
      ? (current.next_hint
        ? `${esc(current.next_hint)}${tipHelp('全局证据阶段退出门：' + current.exit_criteria)}`
        : `全局证据阶段退出门：${esc(current.exit_criteria)}`)
      : '前 8 个阶段已齐，确认上线后进入日常运营。',
    extra: `${data.skipped_count
        ? `<div class="note mb">${data.skipped_count} 个阶段标了“这次先不做”：不计入完成，也不挡后续。</div>`
        : ''}
      <div class="tiny muted">前 8 个阶段（到“评审与固化”）齐了，第一条流程就能上线；
        第 9 阶段“改善与复制”在运营中持续做。</div>`,
    actions: current
      ? '<button class="btn btn-g" data-act="start.jump" data-target="q7">回到当前阶段</button>'
      : '',
  });

  const q3Step = { status: missingCount ? 'IN_PROGRESS' : 'READY' };
  const q8Step = {
    status: data.pilot_confirmed ? 'READY' : data.pilot_gate_open ? 'IN_PROGRESS' : 'NOT_STARTED',
  };
  const activeQ = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8']
    .includes(state.start.activeQ) ? state.start.activeQ : 'q1';
  const nav = `
    <div class="card start-nav">
      <div class="start-nav-layer">地图层</div>
      ${navItem('q1', 'Q1 要什么', strategy, activeQ === 'q1')}
      ${navItem('q2', 'Q2 有什么', arch, activeQ === 'q2')}
      ${navItem('q3', 'Q3 还缺什么', q3Step, activeQ === 'q3')}
      <div class="start-nav-layer">骨架层</div>
      ${navItem('q4', 'Q4 做什么', arch, activeQ === 'q4')}
      ${navItem('q5', 'Q5 输入什么', arch, activeQ === 'q5')}
      <div class="start-nav-layer">执行层</div>
      ${navItem('q6', 'Q6 用什么', design, activeQ === 'q6')}
      ${navItem('q7', 'Q7 输出什么', current || { status: 'READY' }, activeQ === 'q7')}
      ${navItem('q8', 'Q8 下一步', q8Step, activeQ === 'q8')}
    </div>
    <div class="card start-aside-card">
      <h3>三层与页面</h3>
      <div class="start-map-line"><b>地图层</b>战略目标 → 企业流程地图 → 差距</div>
      <div class="start-map-line"><b>骨架层</b>PCF / 流程地图 → 组织与人员 / 设计器</div>
      <div class="start-map-line"><b>执行层</b>设计器 / 工具箱 → 当前阶段 → 十层单页 / 项目</div>
    </div>`;

  const qCards = { q1, q2, q3, q4, q5, q6, q7, q8 };
  const gateCard = pilotGateCard(data);
  const aside = `
    <div class="card start-aside-card">
      <div class="tiny muted">全局证据进度（不是项目当前层）</div>
      <h3>${current ? esc(shortTitle(current)) : '已完成'}</h3>
      <div class="gap">${current ? statusTag(current) : ''}
        ${current && current.estimated ? `<span class="tag t-blu">预计 ${esc(current.estimated)}</span>` : ''}</div>
      <button class="btn-sm mt" data-act="start.openCurrentStage">展开当前阶段</button>
      <div class="tiny muted mt">项目当前层在「十层单页」里看。</div>
      <div class="tiny muted mt">全局 = 全公司证据汇总，不分试点路径。</div>
    </div>
    ${gateCard || `
      <div class="card start-aside-card">
        <h3>退出门自检</h3>
        <div class="tiny muted">还差 ${data.pilot_missing_steps.length} 个阶段：</div>
        <div class="gap">${data.pilot_missing_steps
          .map((title) => `<span class="tag t-yel">${esc(title)}</span>`).join('')}</div>
        <button class="btn-sm mt" data-act="start.jump" data-target="q3">看差距地图</button>
      </div>`}
    <div class="card start-aside-card">
      <h3>能力库</h3>
      <div class="gap">
        <button class="btn-sm" data-act="start.go" data-view="pcf">PCF 分类</button>
        <button class="btn-sm" data-act="start.go" data-view="toolbox">方法工具箱</button>
        <button class="btn-sm" data-act="start.go" data-view="authorization">授权矩阵</button>
        <button class="btn-sm" data-act="start.go" data-view="designer">流程设计器</button>
        <button class="btn-sm" data-act="start.go" data-view="monitor">运营监控</button>
        <button class="btn-sm" data-act="start.go" data-view="knowledge">知识库</button>
      </div>
      <div class="tiny muted mt">按问题取用，不预设绑定。</div>
    </div>
    ${doneList(done)}
    ${upcomingList(upcoming)}`;

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>开始使用<span class="module-badge">唯一主入口 · 0→1 启动路径</span>${tipHelp(
            '先答完 8 个问题，把一条流程从「要什么」走到「下一步」；每个答案都来自系统里已有的证据。'
            + '主线：战略 → 架构 → 组织 → 制度 → 流程 → 表单/工具 → 工作量 → 绩效 → 改善 → 新版本。'
            + '原则：统一原则、统一基线、分级授权、受控差异。')}</h2>
        </div>
        <div class="gap">
          ${data.pilot_confirmed
            ? '<span class="tag t-grn">已确认上线</span>'
            : `<span class="tag t-blu">能上线 ${data.pilot_ready_count}/${data.pilot_total}</span>`}
          <span class="tag ${data.ready_count >= data.total ? 't-grn' : 't-yel'}">
            ${data.ready_count}/${data.total} · ${pct}%</span>
        </div>
      </div>
      <div class="pipe" style="margin-top:12px">
        <i class="fill-ok" style="width:${pct}%"></i>
      </div>
    </div>
    ${railCard}
    <div class="start-shell">
      <aside class="start-side">${nav}</aside>
      <main class="start-center">${qCards[activeQ] || q1}</main>
      <aside class="start-aside">${aside}</aside>
    </div>`;
}

/* -------------------------------------------------- 交互 */

on('start.go', ({ view }) => go(view));

on('start.selectQ', ({ q }) => {
  if (!q) return;
  state.start.activeQ = q;
  state.start.openStage = false;
  RENDERERS.start();
});

on('start.jump', ({ target }) => {
  if (target && /^q[1-8]$/.test(target)) {
    state.start.activeQ = target;
    state.start.openStage = target === 'q7';
    RENDERERS.start();
    setTimeout(() => {
      const el = document.getElementById(target);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
    return;
  }
  const el = document.getElementById(target);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

on('start.openCurrentStage', () => {
  state.start.activeQ = 'q7';
  state.start.openStage = true;
  RENDERERS.start();
  setTimeout(() => {
    const el = document.getElementById('q7');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 50);
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
