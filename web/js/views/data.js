/* 视图：数据治理
 *
 * 最小集：数据域（谁负责、谁管质量）+ 数据流（来源、主键、频率、质量规则、
 * 保留期与跨法人可见性）。缺口由一致性扫描标记。
 */

import { esc, emptyRow } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';

on('data.domainNew', () => domainModal());
on('data.domainEdit', ({ id }) => domainModal(Number(id)));
on('data.submitDomain', ({ id }) => submitDomain(id ? Number(id) : null));
on('data.deleteDomain', ({ id }) => deleteDomain(Number(id)));
on('data.flowNew', () => flowModal());
on('data.flowEdit', ({ id }) => flowModal(Number(id)));
on('data.submitFlow', ({ id }) => submitFlow(id ? Number(id) : null));
on('data.deleteFlow', ({ id }) => deleteFlow(Number(id)));
on('data.close', () => closeModal());

const renderData = () => {
  renderAsync(
    'data',
    () => Promise.all([
      GET('/data-governance/domains'),
      GET('/data-governance/flows'),
      GET('/data-governance/meta'),
      GET('/data-governance/summary'),
      GET('/org-units'),
      GET('/execution/assignees'),
      GET('/process-map/flat'),
      GET('/monitor/kpis'),
    ]).then(([domains, flows, meta, summary, orgs, users, processes, kpis]) => ({
      domains, flows, meta, summary, orgs, users, processes, kpis,
    })),
    (d) => {
      state.dataGov = d;
      const s = d.summary;
      const domainRows = d.domains.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td>${esc(row.domain_type_label)}</td>
          <td>${esc(row.owner_name || '未指定')}<div class="tiny">管家：${
            esc(row.steward_name || '—')}</div></td>
          <td>${row.flow_count}</td>
          <td>${row.is_active
            ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
          <td>${canManage() ? `<div class="gap">
            <button class="btn-sm" data-act="data.domainEdit" data-id="${row.id}">编辑</button>
            <button class="btn-sm btn-g" data-act="data.deleteDomain"
              data-id="${row.id}">删除</button>
          </div>` : ''}</td>
        </tr>`).join('') || emptyRow(6, '还没有数据域');

      const flowRows = d.flows.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td>${esc(row.domain_name || '—')}</td>
          <td class="tiny">${esc(row.source_system || '—')} → ${esc(row.target_system || '—')}
            <div>${esc(row.frequency_label)}</div></td>
          <td class="tiny">${esc(row.primary_key || '—')}</td>
          <td class="tiny">${esc((row.quality_rule || '—').slice(0, 40))}</td>
          <td class="tiny">${esc(row.process_code || '—')}</td>
          <td>${canManage() ? `<div class="gap">
            <button class="btn-sm" data-act="data.flowEdit" data-id="${row.id}">编辑</button>
            <button class="btn-sm btn-g" data-act="data.deleteFlow"
              data-id="${row.id}">删除</button>
          </div>` : ''}</td>
        </tr>`).join('') || emptyRow(7, '还没有数据流');

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>数据治理<span class="module-badge">数据域 · 数据流</span></h2>
              <div class="desc">最小口径：谁负责、从哪来、主键是什么、质量规则与保留期；
                缺口由一致性扫描标记</div></div>
            ${canManage() ? `<div class="gap">
              <button class="btn btn-g" data-act="data.domainNew">+ 新建数据域</button>
              <button class="btn btn-p" data-act="data.flowNew">+ 新建数据流</button>
            </div>` : ''}
          </div>
        </div>
        <div class="grid g4 stat-row">
          <div class="kpi stat"><div class="num">${s.domains}</div><div class="lab">数据域</div></div>
          <div class="kpi stat"><div class="num">${s.flows}</div><div class="lab">数据流</div></div>
          <div class="kpi stat"><div class="num">${s.domains_without_owner}</div>
            <div class="lab">无所有者数据域</div></div>
          <div class="kpi stat"><div class="num">${s.flows_without_quality_rule}</div>
            <div class="lab">缺质量规则数据流</div></div>
        </div>
        <div class="card">
          <div class="between mb"><h3>数据域（${d.domains.length}）</h3></div>
          <table class="tbl">
            <thead><tr><th>数据域</th><th>类型</th><th>所有者 / 管家</th><th>数据流</th>
              <th>状态</th><th></th></tr></thead>
            <tbody>${domainRows}</tbody>
          </table>
        </div>
        <div class="card">
          <div class="between mb"><h3>数据流（${d.flows.length}）</h3>
            <div class="tiny muted">来源 → 目标 · 频率 · 主键 · 质量规则</div></div>
          <table class="tbl">
            <thead><tr><th>数据流</th><th>数据域</th><th>来源 / 频率</th><th>主键</th>
              <th>质量规则</th><th>关联流程</th><th></th></tr></thead>
            <tbody>${flowRows}</tbody>
          </table>
        </div>`;
    },
  );
};

function userOptions(selected) {
  const users = (state.dataGov && state.dataGov.users) || [];
  return users.map((user) =>
    `<option value="${user.id}"${selected === user.id ? ' selected' : ''}>${
      esc(user.display_name)} · ${esc(user.role_label || user.role)}</option>`).join('');
}

function domainModal(domainId = null) {
  const d = state.dataGov || {};
  const row = (d.domains || []).find((item) => item.id === domainId) || null;
  const meta = d.meta || { domain_type_labels: {} };
  const typeOptions = Object.entries(meta.domain_type_labels || {}).map(([code, label]) =>
    `<option value="${esc(code)}"${row && row.domain_type === code ? ' selected' : ''}>${
      esc(label)}</option>`).join('');
  const orgOptions = (d.orgs || []).map((org) =>
    `<option value="${org.id}"${row && row.org_unit_id === org.id ? ' selected' : ''}>${
      esc(org.name)} · ${esc(org.code)}</option>`).join('');

  openModal(row ? '编辑数据域 · ' + row.code : '新建数据域', `
    <div class="row2">
      <div class="field"><label>数据域名称 *</label>
        <input id="ddName" value="${esc(row ? row.name : '')}" placeholder="如 客户主数据"></div>
      <div class="field"><label>编码</label>
        <input id="ddCode" value="${esc(row ? row.code : '')}" placeholder="留空自动生成"></div>
    </div>
    <div class="row2">
      <div class="field"><label>类型</label><select id="ddType">${typeOptions}</select></div>
      <div class="field"><label>组织范围</label>
        <select id="ddOrg"><option value="">集团通用</option>${orgOptions}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>数据所有者 *</label>
        <select id="ddOwner"><option value="">请选择</option>${userOptions(row ? row.owner_user_id : null)}</select></div>
      <div class="field"><label>数据管家</label>
        <select id="ddSteward"><option value="">未指定</option>${userOptions(row ? row.steward_user_id : null)}</select></div>
    </div>
    <div class="field"><label>说明</label>
      <textarea id="ddDesc" rows="2">${esc(row ? row.description || '' : '')}</textarea></div>
    <div class="field"><label>状态</label>
      <select id="ddActive">
        <option value="true"${!row || row.is_active ? ' selected' : ''}>启用</option>
        <option value="false"${row && !row.is_active ? ' selected' : ''}>停用</option>
      </select></div>
    <div class="note">数据所有者对业务定义、质量与访问规则负责；管家负责术语、监控与跨域协调。</div>`,
    `<button class="btn btn-g" data-act="data.close">取消</button>
     <button class="btn btn-p" data-act="data.submitDomain"
       data-id="${row ? row.id : ''}">${row ? '保存' : '创建'}</button>`);
}

async function submitDomain(domainId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const name = val('ddName').trim();
  if (!name) return toast('请填写数据域名称', true);
  if (!val('ddOwner')) return toast('请选择数据所有者', true);
  const payload = {
    name,
    domain_type: val('ddType'),
    org_unit_id: val('ddOrg') ? Number(val('ddOrg')) : null,
    owner_user_id: Number(val('ddOwner')),
    steward_user_id: val('ddSteward') ? Number(val('ddSteward')) : null,
    description: val('ddDesc').trim() || null,
    is_active: val('ddActive') === 'true',
  };
  if (val('ddCode').trim()) payload.code = val('ddCode').trim();
  try {
    if (domainId) await PATCH('/data-governance/domains/' + domainId, payload);
    else await POST('/data-governance/domains', payload);
    closeModal();
    toast(domainId ? '数据域已更新' : '数据域已创建');
    RENDERERS.data();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteDomain(domainId) {
  const row = (state.dataGov.domains || []).find((item) => item.id === domainId);
  if (!row) return;
  const ok = await confirmDialog(`删除数据域「${row.name}」？仍有数据流时会被拒绝。`,
    { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/data-governance/domains/' + domainId);
    toast('数据域已删除');
    RENDERERS.data();
  } catch (e) {
    toast(e.message, true);
  }
}

function flowOptions(selected) {
  const d = state.dataGov || {};
  return (d.domains || []).map((domain) =>
    `<option value="${domain.id}"${selected === domain.id ? ' selected' : ''}>${
      esc(domain.name)}</option>`).join('');
}

function processOptions(selected) {
  const d = state.dataGov || {};
  return (d.processes || []).filter((row) => row.level >= 2).map((row) =>
    `<option value="${row.id}"${selected === row.id ? ' selected' : ''}>L${row.level} ${
      esc(row.code)} ${esc(row.name)}</option>`).join('');
}

function kpiOptions(selected) {
  const d = state.dataGov || {};
  return (d.kpis || []).map((row) =>
    `<option value="${row.id}"${selected === row.id ? ' selected' : ''}>${
      esc(row.code)} ${esc(row.name)}</option>`).join('');
}

function flowModal(flowId = null) {
  const d = state.dataGov || {};
  const row = (d.flows || []).find((item) => item.id === flowId) || null;
  const meta = d.meta || { frequency_labels: {} };
  const freqOptions = Object.entries(meta.frequency_labels || {}).map(([code, label]) =>
    `<option value="${esc(code)}"${row && row.frequency === code ? ' selected' : ''}>${
      esc(label)}</option>`).join('');

  openModal(row ? '编辑数据流 · ' + row.code : '新建数据流', `
    <div class="row2">
      <div class="field"><label>数据流名称 *</label>
        <input id="dfName" value="${esc(row ? row.name : '')}" placeholder="如 CRM → ERP 客户主数据"></div>
      <div class="field"><label>编码</label>
        <input id="dfCode" value="${esc(row ? row.code : '')}" placeholder="留空自动生成"></div>
    </div>
    <div class="row2">
      <div class="field"><label>数据域 *</label>
        <select id="dfDomain"><option value="">请选择</option>${
          flowOptions(row ? row.domain_id : null)}</select></div>
      <div class="field"><label>提取频率</label>
        <select id="dfFreq">${freqOptions}</select></div>
    </div>
    <div class="row3">
      <div class="field"><label>来源系统</label>
        <input id="dfSource" value="${esc(row ? row.source_system || '' : '')}"></div>
      <div class="field"><label>目标系统</label>
        <input id="dfTarget" value="${esc(row ? row.target_system || '' : '')}"></div>
      <div class="field"><label>主键</label>
        <input id="dfKey" value="${esc(row ? row.primary_key || '' : '')}" placeholder="如 customer_code"></div>
    </div>
    <div class="row2">
      <div class="field"><label>关联流程</label>
        <select id="dfProcess"><option value="">不关联</option>${
          processOptions(row ? row.process_id : null)}</select></div>
      <div class="field"><label>关联 KPI</label>
        <select id="dfKpi"><option value="">不关联</option>${
          kpiOptions(row ? row.kpi_id : null)}</select></div>
    </div>
    <div class="field"><label>质量规则</label>
      <textarea id="dfQuality" rows="2" placeholder="完整性/准确性/及时性规则">${esc(row ? row.quality_rule || '' : '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>字段定义</label>
        <textarea id="dfFields" rows="2">${esc(row ? row.field_definitions || '' : '')}</textarea></div>
      <div class="field"><label>允许值</label>
        <textarea id="dfAllowed" rows="2">${esc(row ? row.allowed_values || '' : '')}</textarea></div>
    </div>
    <div class="field"><label>用途</label>
      <input id="dfPurpose" value="${esc(row ? row.purpose || '' : '')}"></div>
    <div class="row3">
      <div class="field"><label>保留期</label>
        <input id="dfRetention" value="${esc(row ? row.retention_period || '' : '')}" placeholder="如 10 年"></div>
      <div class="field"><label>跨法人可见性</label>
        <input id="dfVisibility" value="${esc(row ? row.cross_legal_visibility || '' : '')}"></div>
      <div class="field"><label>数据主体权利</label>
        <input id="dfRights" value="${esc(row ? row.data_subject_rights || '' : '')}"></div>
    </div>
    <div class="note">来源系统、主键、质量规则建议在登记时补全；缺失会被治理扫描标记。</div>`,
    `<button class="btn btn-g" data-act="data.close">取消</button>
     <button class="btn btn-p" data-act="data.submitFlow"
       data-id="${row ? row.id : ''}">${row ? '保存' : '创建'}</button>`);
}

async function submitFlow(flowId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  if (!val('dfName').trim()) return toast('请填写数据流名称', true);
  if (!val('dfDomain')) return toast('请选择数据域', true);
  const payload = {
    name: val('dfName').trim(),
    domain_id: Number(val('dfDomain')),
    process_id: val('dfProcess') ? Number(val('dfProcess')) : null,
    kpi_id: val('dfKpi') ? Number(val('dfKpi')) : null,
    source_system: val('dfSource').trim() || null,
    target_system: val('dfTarget').trim() || null,
    frequency: val('dfFreq'),
    primary_key: val('dfKey').trim() || null,
    field_definitions: val('dfFields').trim() || null,
    allowed_values: val('dfAllowed').trim() || null,
    quality_rule: val('dfQuality').trim() || null,
    purpose: val('dfPurpose').trim() || null,
    retention_period: val('dfRetention').trim() || null,
    cross_legal_visibility: val('dfVisibility').trim() || null,
    data_subject_rights: val('dfRights').trim() || null,
  };
  if (val('dfCode').trim()) payload.code = val('dfCode').trim();
  try {
    if (flowId) await PATCH('/data-governance/flows/' + flowId, payload);
    else await POST('/data-governance/flows', payload);
    closeModal();
    toast(flowId ? '数据流已更新' : '数据流已创建');
    RENDERERS.data();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteFlow(flowId) {
  const row = (state.dataGov.flows || []).find((item) => item.id === flowId);
  if (!row) return;
  const ok = await confirmDialog(`删除数据流「${row.name}」？`, { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/data-governance/flows/' + flowId);
    toast('数据流已删除');
    RENDERERS.data();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderData };
