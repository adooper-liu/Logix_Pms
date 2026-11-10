/* 岗位职责：同源覆盖度 → 责任书预览 → 原文档版本。 */
import { GET, POST, download } from '../core/api.js';
import { canManage } from '../core/auth.js';
import { esc, tipHelp } from '../core/format.js';
import { pageShell, foldCard, sideCard } from '../core/layout.js';
import { go, renderAsync, urlParams } from '../core/router.js';
import { state } from '../core/state.js';
import { on, toast, viewEl } from '../core/ui.js';

let currentData = null;
let revision = 0;
let busy = false;
const TABS = { overview: '岗位概览', activities: '职责活动', description: '责任书预览', versions: '版本与评审' };
function params() { return { ...urlParams() }; }
function current(key) { return state.view === 'responsibility' && context() === key; }
function context() { const p = params(); return `${p.position || ''}|${p.period || ''}`; }
function navigate(p) { revision += 1; currentData = null; busy = false; go('responsibility', { params: p, push: true }); }

on('responsibility.position', (_data, el) => navigate({ ...params(), position: el.value, tab: 'overview' }));
on('responsibility.period', (_data, el) => navigate({ ...params(), period: el.value ? el.value + '-01' : '', tab: 'overview' }));
on('responsibility.tab', ({ tab }) => navigate({ ...params(), tab }));
on('responsibility.refresh', () => navigate(params()));
on('responsibility.node', ({ process, node, activity, model }) => go('designer', {
  params: { process, node, activity, basis: model, tab: 'model' }, push: true,
}));
on('responsibility.download', async ({ url }) => {
  try { await download(url.replace(/^\/api\/v1/, ''), '岗位责任书.html'); } catch (error) { toast(error.message, 'error'); }
});
on('responsibility.compile', async () => {
  if (busy || !currentData?.preview?.can_compile) return;
  const key = context();
  const p = params();
  const digest = currentData.preview.input_hash;
  busy = true;
  paint(currentData);
  try {
    await POST(`/positions/${p.position}/job-descriptions`, { period: p.period || null, expected_input_hash: digest });
    if (!current(key)) return;
    toast('已生成岗位责任书草稿');
    navigate({ ...p, tab: 'versions' });
  } catch (error) {
    if (!current(key)) return;
    toast(error.message + '；请先刷新预览或查询版本，勿重复生成。', 'error');
    busy = false;
    paint(currentData);
  }
});
on('responsibility.transition', async ({ document, version, status }) => {
  if (busy) return;
  const key = context();
  const p = params();
  busy = true;
  paint(currentData);
  try {
    await POST(`/process-documents/${document}/versions/${version}/transition`, { status });
    if (!current(key)) return;
    navigate({ ...p, tab: 'versions' });
  } catch (error) {
    if (!current(key)) return;
    busy = false;
    toast(error.message, 'error');
    paint(currentData);
  }
});

export function renderResponsibility() {
  const ticket = ++revision;
  const p = params();
  currentData = null;
  busy = false;
  return renderAsync('responsibility', async () => {
    const positions = await GET('/positions?active_only=false');
    if (!p.position) return { positions };
    if (!/^\d+$/.test(p.position)) throw new Error('岗位标识无效，请重新选择岗位');
    const query = new URLSearchParams({ position_id: p.position });
    if (p.period) query.set('period', p.period);
    const [coverage, preview, versions] = await Promise.all([
      GET('/workload/position-coverage?' + query),
      POST(`/positions/${p.position}/job-description/preview`, { period: p.period || null }),
      GET(`/positions/${p.position}/job-descriptions`),
    ]);
    return { positions, coverage, preview, versions };
  }, data => {
    if (ticket !== revision) return;
    currentData = data;
    paint(data);
  });
}

function paint(data) {
  const p = params();
  const active = TABS[p.tab] ? p.tab : 'overview';
  const cov = data.coverage;
  const controls = `<label>岗位 <select class="sel" data-responsibility-select data-act="responsibility.position">
    <option value="">请选择岗位</option>${data.positions.map(pos => `<option value="${pos.id}" ${String(pos.id) === p.position ? 'selected' : ''}>${esc(pos.name)} · ${esc(pos.code)}</option>`).join('')}</select></label>
    <label>月份 <input type="month" data-act="responsibility.period" value="${esc((p.period || cov?.period || '').slice(0, 7))}"></label>`;
  let body = '<div class="card"><h3>先选择岗位</h3><p>查看岗位负责的活动，再核对责任书；不会自动选取演示岗位。</p></div>';
  if (cov && active === 'overview') {
    body = `<div class="card" data-responsibility-overview><h3>${esc(cov.name)} · 岗位职责</h3>
      <p>${esc(cov.org_unit_name || '集团通用')} · ${cov.activities.length} 项活动 · ${cov.processes.length} 条流程</p>
      <p>下一步：核对职责活动与角色归位，再查看责任书预览。</p>
      ${(cov.gaps || []).map(g => `<p class="tiny">${esc(g.message)}</p>`).join('')}
      ${cov.unmapped_roles.length ? '<p class="warnbox">角色未归位：部分角色不能明确归到一个岗位，不自动分摊。</p>' : ''}</div>`;
  } else if (cov && active === 'activities') {
    body = `<div data-responsibility-activities>${cov.activities.map(a => foldCard(`${a.process_code} / ${a.activity_name}`,
      `<p>${a.sources.map(s => esc(s.label)).join(' · ')}</p><p>${a.raci.map(r => `${esc(r.role_name)} · ${esc(r.raci_label)}`).join('；') || '未绑定活动 RACI'}</p>
       <p>模型 #${esc(a.model_version_id || '未固定')} · 节点 ${a.node_keys.map(esc).join('、') || '未建模'}</p>
       ${a.node_keys.map(node => `<button class="btn-sm" data-act="responsibility.node" data-process="${a.process_id}" data-activity="${a.activity_id}" data-node="${esc(node)}" data-model="${a.model_version_id || ''}">定位 ${esc(node)}</button>`).join(' ')}`,
      { open: true })).join('') || '<div class="card">未发现明确活动，请回设计器维护原绑定。</div>'}
      ${foldCard('同源工作量参考', `<p>需求 ${cov.workload.totals.demand_minutes} 分钟 · 实际 ${cov.workload.totals.actual_minutes} 分钟 · 可用 ${cov.workload.totals.available_minutes} 分钟</p>
      <p>负荷率 ${cov.workload.totals.utilization === null ? '待登记产能' : esc((cov.workload.totals.utilization * 100).toFixed(1)) + '%'}</p>`, { open: false })}</div>`;
  } else if (cov && active === 'description') {
    body = `<div class="card"><h3>责任书预览</h3><p>${data.preview.can_compile ? '来源身份可核对；生成后仍为草稿。' : '来源身份待确认，仅可预览。'}</p>
      ${data.preview.gaps.map(g => `<p class="tiny">${esc(g.message)}</p>`).join('')}
      <button class="btn-sm btn-g" data-act="responsibility.refresh">刷新预览</button>
      ${canManage() ? `<button class="btn-sm" data-act="responsibility.compile" ${busy || !data.preview.can_compile ? 'disabled' : ''}>${busy ? '正在生成…' : '生成责任书草稿'}</button>` : ''}</div>
      ${data.preview.sections.map(section => foldCard(section.title, section.html, { open: false })).join('')}`;
  } else if (cov && active === 'versions') {
    const next = { DRAFT: [['IN_REVIEW', '提交评审']], IN_REVIEW: [['APPROVED', '批准'], ['DRAFT', '退回草稿']], APPROVED: [['EFFECTIVE', '生效']], EFFECTIVE: [], RETIRED: [] };
    body = `<div data-responsibility-versions>${data.versions.map(v => foldCard(`v${v.version_label} · ${v.status_label}`,
      `<p>${esc(v.manifest.rule_version)} · ${esc(v.manifest.period)}</p><p class="tiny" style="overflow-wrap:anywhere">内容 hash：${esc(v.content_hash)}</p>
      <button class="btn-sm btn-g" data-act="responsibility.download" data-url="${esc(v.download_url)}">下载固定版本</button>
      ${canManage() ? (next[v.status] || []).map(([status, label]) => `<button class="btn-sm" data-act="responsibility.transition" data-document="${v.document_id}" data-version="${v.version_id}" data-status="${status}" ${busy ? 'disabled' : ''}>${label}</button>`).join('') : ''}`,
      { open: true })).join('') || '<div class="card">尚未生成责任书。请先核对预览，再生成草稿。</div>'}</div>`;
  }
  const shell = pageShell({
    title: '岗位职责', subtitle: '先明确岗位负责什么，再从原绑定生成责任书。',
    tip: tipHelp('职级、能力等级与人数配置在后续工作量表环节管理；岗位名称不自动授予审批权限。', '范围说明'),
    actions: controls, sections: Object.entries(TABS).map(([key, label]) => ({ key, label, html: key === active ? body : '' })),
    active, tabAct: 'responsibility.tab', mode: 'nav',
    aside: cov ? sideCard('当前岗位', `<p>${esc(cov.name)}</p><p>${esc(cov.period)}</p><p>缺口回原设计器补齐；本页不另录职责。</p>`) : '',
  });
  viewEl().innerHTML = shell.html;
}
