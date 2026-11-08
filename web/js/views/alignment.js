/* 视图：目标与承接
 *
 * 上游：客户/市场要求 → 战略目标 → 承接流程/KPI
 * 同页显示四路使能状态：配资源 / 搭班子 / 建流程 / 制度与绩效。
 * 只做状态与缺口，具体录入回到对应模块。
 */
import { esc, tipHelp } from '../core/format.js';
import { toast, openModal, closeModal, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go } from '../core/router.js';
import { canManage } from '../core/auth.js';
import { GET, POST, PATCH } from '../core/api.js';
import { pageShell, sideCard } from '../core/layout.js';

const AL = () => (state.alignment || (state.alignment = {
  year: new Date().getFullYear(), data: null, selectedId: null, tab: 'objectives',
}));

function errorText(error) {
  const raw = error && error.message ? error.message : '操作失败';
  try {
    const detail = JSON.parse(raw);
    if (detail && detail.message) return detail.message;
  } catch (_) { /* 不是 JSON */ }
  return raw;
}

function currentObjective() {
  const rows = AL().data?.objectives || [];
  return rows.find((row) => row.id === AL().selectedId) || rows[0] || null;
}

function requirementRows(data) {
  const rows = data.requirements || [];
  if (!rows.length) {
    return '<tr><td colspan="6" class="muted">还没有客户/市场要求。</td></tr>';
  }
  return rows.map((row) => `<tr>
    <td><b>${esc(row.code)}</b></td>
    <td><span class="tag t-mute">${esc(row.source_label)}</span></td>
    <td>${esc(row.title)}</td>
    <td class="tiny">${(row.objectives || []).map((item) => esc(item.code)).join('、') || '未承接'}</td>
    <td>${row.status === 'ACTIVE'
      ? '<span class="tag t-grn">有效</span>' : '<span class="tag t-gry">已关闭</span>'}</td>
    <td class="gap">
      ${canManage() ? `<button class="btn-sm" data-act="alignment.editRequirement"
        data-id="${row.id}">编辑</button>` : ''}
      ${canManage() && row.status === 'ACTIVE' ? `<button class="btn-sm"
        data-act="alignment.closeRequirement" data-id="${row.id}">关闭</button>` : ''}
    </td></tr>`).join('');
}

function enablerCard(item) {
  const metricRows = Object.entries(item.metrics || {}).map(([key, value]) => (
    `<span><b>${esc(String(value))}</b>${esc(item.metric_labels?.[key] || key)}</span>`
  )).join('');
  const gaps = (item.gaps || []).length
    ? `<ul class="al-gaps">${item.gaps.map((gap) => `<li>${esc(gap)}</li>`).join('')}</ul>`
    : '<div class="tiny muted">没有缺口。</div>';
  const action = item.next_view
    ? `<button class="btn-sm" data-act="alignment.go" data-view="${esc(item.next_view)}"
        data-params="${esc(JSON.stringify(item.next_params || {}))}">${esc(item.next_action)}</button>`
    : '';
  return `<div class="card al-enabler ${item.ready ? 'is-ok' : 'is-gap'}">
    <div class="between">
      <h3>${esc(item.label)}</h3>
      <span class="tag ${item.ready ? 't-grn' : 't-yel'}">${item.ready ? '可用' : '缺项'}</span>
    </div>
    <div class="al-metrics">${metricRows || '<span class="tiny muted">暂无数据</span>'}</div>
    ${gaps}
    ${action}
  </div>`;
}

function objectiveDetail(data) {
  const row = currentObjective();
  if (!row) {
    return `<div class="card"><div class="empty">今年还没有战略目标。
      <button class="btn-sm mt" data-act="alignment.goStrategy">去目标页新建</button></div></div>`;
  }
  const requirements = (row.requirements || []).map((item) => (
    `<span class="tag t-blu">${esc(item.code)} ${esc(item.name)}</span>`
  )).join(' ') || '<span class="tiny muted">未关联客户/市场要求</span>';
  const processes = (row.processes || []).map((item) => (
    `<button class="chip" data-act="alignment.openProcess" data-id="${item.id}">
      ${esc(item.code)} ${esc(item.name)}</button>`
  )).join(' ') || '<span class="tiny muted">未承接流程</span>';
  const kpis = (row.kpis || []).map((item) => (
    `<span class="tag t-mute">${esc(item.code)} ${esc(item.name)}${
      item.target_value === null ? ' · 缺目标' : ' · 目标 ' + item.target_value}</span>`
  )).join(' ') || '<span class="tiny muted">未承接 KPI</span>';
  return `<div class="card al-objective">
      <div class="between">
        <div>
          <h3>${esc(row.code)} ${esc(row.name)}</h3>
          <div class="tiny muted">${row.year} · ${esc(row.owner || '缺 Owner')}
            · 基线 ${row.baseline_value ?? '—'} → 目标 ${row.target_value ?? '—'} ${esc(row.unit || '')}</div>
        </div>
        <span class="tag ${(row.gaps || []).length ? 't-yel' : 't-grn'}">
          ${(row.gaps || []).length ? `${row.gaps.length} 项缺口` : '四路就绪'}</span>
      </div>
      <div class="al-links">
        <div><span class="tiny muted">客户/市场要求</span>${requirements}</div>
        <div><span class="tiny muted">承接流程</span>${processes}</div>
        <div><span class="tiny muted">承接 KPI</span>${kpis}</div>
      </div>
    </div>
    <div class="al-enablers">${(row.enablers || []).map(enablerCard).join('')}</div>`;
}

function requirementsHtml(data) {
  return `<div class="card">
    <div class="between mb"><h3>客户 / 市场要求</h3>
      <span class="tiny muted">每一条要求都应挂到至少一个目标</span></div>
    <table class="tbl"><thead><tr><th>编码</th><th>来源</th><th>要求</th>
      <th>承接目标</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${requirementRows(data)}</tbody></table>
  </div>`;
}

function objectivesHtml(data) {
  const objectives = data.objectives || [];
  const objectiveList = objectives.map((row) => `
    <button class="al-obj ${row.id === AL().selectedId ? 'on' : ''}"
      data-act="alignment.selectObjective" data-id="${row.id}">
      <b>${esc(row.code)}</b>
      <span>${esc(row.name)}</span>
      <em class="${(row.gaps || []).length ? 'is-gap' : 'is-ok'}">
        ${(row.gaps || []).length ? `${row.gaps.length} 缺口` : '就绪'}</em>
    </button>`).join('');
  return `<div class="al-layout">
    <div class="card al-obj-list">
      <div class="between mb"><h3>目标</h3><span class="tiny muted">${objectives.length} 条</span></div>
      ${objectiveList || '<div class="empty">今年还没有目标。</div>'}
    </div>
    <div>${objectiveDetail(data)}</div>
  </div>`;
}

function alignmentAside(data) {
  const summary = data.summary || {};
  const labels = data.enabler_labels || {};
  const ready = summary.enabler_ready || {};
  const enablerRows = Object.entries(labels).map(([key, label]) => (
    `<div class="kv"><span>${esc(label)}</span><b>${ready[key] ?? 0}</b></div>`
  )).join('') || '<div class="tiny muted">暂无目标。</div>';
  const gapRows = (data.objectives || [])
    .filter((row) => (row.gaps || []).length)
    .slice(0, 5)
    .map((row) => `<div class="kv"><span>${esc(row.code)}</span><b>${row.gaps.length} 项</b></div>`)
    .join('') || '<div class="tiny muted">所有目标四路就绪。</div>';
  return `
    ${sideCard('年度汇总', `
      <div class="kv"><span>客户/市场要求</span><b>${summary.requirements ?? 0}</b></div>
      <div class="kv"><span>战略目标</span><b>${summary.objectives ?? 0}</b></div>
      <div class="kv"><span>四路就绪</span><b>${summary.ready_objectives ?? 0}</b></div>
      <div class="kv"><span>仍有缺口</span><b>${summary.gap_objectives ?? 0}</b></div>`)}
    ${sideCard('四路就绪目标数', enablerRows)}
    ${sideCard('缺口目标', gapRows)}`;
}

function paint(data) {
  AL().data = data;
  const objectives = data.objectives || [];
  if (!objectives.some((row) => row.id === AL().selectedId)) {
    AL().selectedId = objectives.length ? objectives[0].id : null;
  }
  const yearOptions = [AL().year - 1, AL().year, AL().year + 1]
    .map((year) => `<option value="${year}"${year === AL().year ? ' selected' : ''}>${year}</option>`)
    .join('');
  const sections = [
    {
      key: 'requirements',
      label: '客户/市场要求',
      count: (data.requirements || []).length,
      html: requirementsHtml(data),
    },
    {
      key: 'objectives',
      label: '目标与四路',
      count: objectives.length,
      html: objectivesHtml(data),
    },
  ];
  const shell = pageShell({
    title: '目标与承接',
    subtitle: '客户/市场要求 → 战略目标 → 承接流程/KPI → 四路使能状态。',
    tip: tipHelp(
      '四路规则：配资源=项目预算+标准工时/产能；搭班子=Owner+RACI-A+Sponsor；'
      + '建流程=已发布模型+L4；制度与绩效=生效制度+授权+KPI 口径。',
      '四路说明',
    ),
    actions: `<select class="sel" id="alYear" data-act="alignment.year">${yearOptions}</select>
      ${canManage() ? `<button class="btn btn-g" data-act="alignment.newRequirement">登记客户要求</button>` : ''}
      <button class="btn btn-p" data-act="alignment.goStrategy">打开目标</button>`,
    sections,
    active: AL().tab,
    tabAct: 'alignment.tab',
    aside: alignmentAside(data),
  });
  AL().tab = shell.active;
  viewEl().innerHTML = shell.html;
}

const renderAlignment = () => renderAsync(
  'alignment',
  () => GET('/alignment?year=' + AL().year),
  paint,
);

/* -------------------------------------------------- 要求录入 */

function openRequirementModal(row = null) {
  const data = AL().data || {};
  const sourceLabels = data.source_labels || {};
  const objectiveOptions = (data.objectives || []).map((item) => {
    const selected = row?.objectives?.some((obj) => obj.id === item.id) ? ' selected' : '';
    return `<option value="${item.id}"${selected}>${esc(item.code)} ${esc(item.name)}</option>`;
  }).join('');
  const sourceOptions = Object.entries(sourceLabels).map(([code, label]) => (
    `<option value="${code}"${row?.source_type === code ? ' selected' : ''}>${esc(label)}</option>`
  )).join('');
  openModal(row ? '编辑客户/市场要求' : '登记客户/市场要求', `
    <div class="row3">
      <div class="field"><label>来源</label>
        <select class="sel" id="alSource">${sourceOptions}</select></div>
      <div class="field"><label>编码</label>
        <input id="alCode" value="${esc(row?.code || '')}" placeholder="留空自动生成"></div>
      <div class="field"><label>标题 *</label>
        <input id="alTitle" value="${esc(row?.title || '')}"></div>
    </div>
    <div class="field"><label>要求正文 *</label>
      <textarea id="alRequirement" rows="3">${esc(row?.requirement || '')}</textarea></div>
    <div class="field"><label>证据链接</label>
      <input id="alEvidence" value="${esc(row?.evidence_url || '')}"
        placeholder="客户邮件 / 市场报告 / 法规条款"></div>
    <div class="field"><label>承接目标（可多选）</label>
      <select class="sel" id="alObjectives" multiple size="6">${objectiveOptions}</select></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="alignment.submitRequirement"
     data-id="${row ? row.id : ''}">${row ? '保存' : '登记'}</button>`);
}

async function submitRequirement(id) {
  const value = (key) => (document.getElementById(key)?.value || '').trim();
  const title = value('alTitle');
  const requirement = value('alRequirement');
  if (!title || !requirement) return toast('标题和正文必填', true);
  const objectiveIds = Array.from(
    document.getElementById('alObjectives')?.selectedOptions || [],
  ).map((option) => Number(option.value)).filter(Boolean);
  const payload = {
    source_type: value('alSource'),
    title,
    requirement,
    evidence_url: value('alEvidence') || null,
    objective_ids: objectiveIds,
  };
  if (!id && value('alCode')) payload.code = value('alCode');
  try {
    if (id) {
      await PATCH('/requirements/' + id, payload);
      toast('要求已更新');
    } else {
      await POST('/requirements', payload);
      toast('要求已登记');
    }
    closeModal();
    renderAlignment();
  } catch (error) {
    toast(errorText(error), true);
  }
}

/* -------------------------------------------------- 交互 */

on('alignment.tab', ({ tab }) => {
  if (!tab || !AL().data) return;
  AL().tab = tab;
  paint(AL().data);
});
on('alignment.year', (_, el) => {
  AL().year = Number(el.value);
  renderAlignment();
});
on('alignment.selectObjective', ({ id }) => {
  AL().selectedId = Number(id);
  paint(AL().data);
});
on('alignment.newRequirement', () => openRequirementModal());
on('alignment.editRequirement', ({ id }) => {
  const row = (AL().data?.requirements || []).find((item) => item.id === Number(id));
  if (row) openRequirementModal(row);
});
on('alignment.closeRequirement', async ({ id }) => {
  try {
    await PATCH('/requirements/' + Number(id), { status: 'CLOSED' });
    toast('要求已关闭');
    renderAlignment();
  } catch (error) {
    toast(errorText(error), true);
  }
});
on('alignment.submitRequirement', ({ id }) => submitRequirement(Number(id) || null));
on('alignment.go', ({ view, params }) => {
  if (!view) return;
  let parsed = {};
  try {
    parsed = params ? JSON.parse(params) : {};
  } catch (_) {
    parsed = {};
  }
  go(view, { params: parsed });
});
on('alignment.openProcess', ({ id }) => go('asset', { params: { process: Number(id) } }));
on('alignment.goStrategy', () => go('strategy'));

export { renderAlignment };
