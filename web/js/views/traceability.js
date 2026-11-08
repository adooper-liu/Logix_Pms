/* 视图：追溯矩阵
 *
 * 只读：目标 / KPI → L3 → L4 → BPMN 节点 → 资产版本 → 证据。
 * 缺链接显示「未承接」，不推断关系。
 */
import { esc } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { renderAsync, go, urlParams } from '../core/router.js';
import { GET } from '../core/api.js';

function assetHtml(asset) {
  return `<div class="tiny"><b>${esc(asset.document_code)}</b> v${esc(asset.version_label)}
    <span class="tag t-mute">${esc(asset.kind_label || asset.kind || '交付物')}</span>
    <span class="tiny muted">${esc(asset.status_label)}</span></div>`;
}

function claimHtml(claim) {
  const samples = claim.samples !== null && claim.samples !== undefined
    ? ` · ${claim.samples} 样本` : '';
  return `<div class="tiny"><b>${esc(claim.claim)}</b>
    <div class="tiny muted">${esc(claim.method_label || claim.method)}
      · ${esc(claim.status_label || claim.status)}${samples}</div></div>`;
}

function gapHtml(gaps) {
  if (!gaps || !gaps.length) return '<span class="tag t-grn">链路齐</span>';
  return gaps.map((gap) => `<span class="tag t-red">${esc(gap)}</span>`).join(' ');
}

function rowHtml(row) {
  const objective = row.objective_code
    ? `<b>${esc(row.objective_code)}</b> ${esc(row.objective_name)}`
    : '<span class="tag t-red">未承接</span>';
  const kpi = row.kpi
    ? `<b>${esc(row.kpi.code)}</b> ${esc(row.kpi.name)}
      <div class="tiny muted">${row.kpi.latest_value !== null && row.kpi.latest_value !== undefined
        ? `最新 ${row.kpi.latest_value}${esc(row.kpi.unit || '')} @ ${esc(row.kpi.latest_period || '—')}`
        : '还没有记录'}</div>`
    : '<span class="tag t-red">未挂 KPI</span>';
  const process = `<b>${esc(row.process_code)}</b> ${esc(row.process_name)}
    <div class="tiny muted">${row.activity_code
      ? `${esc(row.activity_code)} ${esc(row.activity_name || '')}`
      : '没有 L4 活动'}</div>`;
  const nodes = row.node_keys.length
    ? row.node_keys.map((key) => `<span class="tag t-blu">${esc(key)}</span>`).join(' ')
    : '<span class="tag t-yel">未映射</span>';
  const assets = row.assets.length
    ? row.assets.map(assetHtml).join('')
    : '<span class="tag t-yel">无编译资产</span>';
  const claims = row.claims.length
    ? row.claims.map(claimHtml).join('')
    : '<span class="tag t-yel">无证据</span>';
  return `<tr>
    <td>${objective}</td><td>${kpi}</td>
    <td title="${esc(row.process_path)}">${process}</td>
    <td>${nodes}</td><td>${assets}</td><td>${claims}</td><td>${gapHtml(row.gaps)}</td>
  </tr>`;
}

function paint(data) {
  const { trace, objectives, processes } = data;
  const params = urlParams();
  const summary = trace.summary || {};
  const orphans = trace.orphans || [];
  const rows = trace.rows || [];
  const objectiveOptions = objectives.map((row) => (
    `<option value="${row.id}"${String(params.objective || '') === String(row.id) ? ' selected' : ''}>${esc(row.code)} ${esc(row.name)}</option>`
  )).join('');
  const processOptions = processes.map((row) => (
    `<option value="${row.id}"${String(params.process || '') === String(row.id) ? ' selected' : ''}>${esc(row.code)} ${esc(row.name)}</option>`
  )).join('');
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>追溯矩阵</h2>
          <p class="desc">目标 / KPI → L3 → L4 → BPMN 节点 → 资产版本 → 证据。缺链接显示「未承接」，不推断。</p>
        </div>
        <div class="gap">
          <select class="sel" data-act="trace.objective">
            <option value="">全部目标</option>${objectiveOptions}
          </select>
          <select class="sel" data-act="trace.process">
            <option value="">全部 L3</option>${processOptions}
          </select>
          <button class="btn-sm" data-act="trace.reset">重置</button>
        </div>
      </div>
    </div>
    <div class="kpi-strip" style="grid-template-columns:repeat(8,1fr);margin-bottom:14px">
      <div><b>${summary.objectives || 0}</b><span>目标</span></div>
      <div><b>${summary.kpis || 0}</b><span>KPI</span></div>
      <div><b>${summary.processes || 0}</b><span>流程</span></div>
      <div><b>${summary.activities || 0}</b><span>L4 活动</span></div>
      <div><b>${summary.asset_versions || 0}</b><span>资产版本</span></div>
      <div><b>${summary.claims || 0}</b><span>证据</span></div>
      <div><b>${summary.gap_rows || 0}</b><span>缺口行</span></div>
      <div><b>${summary.orphans || 0}</b><span>未承接</span></div>
    </div>
    ${orphans.length ? `<div class="card" style="padding:14px 18px;margin-bottom:14px">
      <h3>未承接</h3>
      <ul class="tiny">${orphans.map((row) => (
        `<li><b>${esc(row.kind)} ${esc(row.code)} ${esc(row.name)}</b> — ${esc(row.reason)}</li>`
      )).join('')}</ul>
    </div>` : ''}
    <div class="card" style="padding:16px 18px;overflow:auto">
      <table class="tbl">
        <thead><tr><th>目标</th><th>KPI</th><th>L3 / L4</th><th>模型节点</th>
          <th>资产版本</th><th>证据</th><th>缺口</th></tr></thead>
        <tbody>${rows.map(rowHtml).join('') || '<tr><td colspan="7" class="tiny muted">没有可追溯的链路；先建立目标承接或流程资产。</td></tr>'}</tbody>
      </table>
    </div>`;
}

export async function renderTraceability() {
  const params = urlParams();
  const query = new URLSearchParams();
  if (params.objective) query.set('objective_id', params.objective);
  if (params.process) query.set('process_id', params.process);
  if (params.kpi) query.set('kpi_id', params.kpi);
  if (params.activity) query.set('activity_id', params.activity);
  return renderAsync(
    'traceability',
    () => Promise.all([
      GET('/traceability' + (query.size ? '?' + query : '')),
      GET('/strategy/objectives'),
      GET('/process-map/flat?level=3'),
    ]),
    ([trace, objectives, processes]) => paint({ trace, objectives, processes }),
  );
}

on('trace.objective', (_data, el) => {
  const params = { ...urlParams() };
  if (el.value) params.objective = el.value;
  else delete params.objective;
  go('traceability', { params, push: true });
});
on('trace.process', (_data, el) => {
  const params = { ...urlParams() };
  if (el.value) params.process = el.value;
  else delete params.process;
  go('traceability', { params, push: true });
});
on('trace.reset', () => go('traceability', { params: {}, push: true }));
