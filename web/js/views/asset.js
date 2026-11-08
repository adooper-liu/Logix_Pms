/* 视图：流程资产工作台
 *
 * 默认只回答三个问题：能产出什么、还缺什么、下一步做什么。
 * 资产图、关系表、证据账本放在下方专家区，不抢占首屏。
 *
 * 数据全部来自后端；前端不重算 PCE、不维护中文枚举、不拼第二套口径。
 */
import { esc, fmtDateTime, tipHelp } from '../core/format.js';
import { pageShell, foldCard, sideCard } from '../core/layout.js';
import { toast, openModal, closeModal, confirmDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, urlParams } from '../core/router.js';
import { canWrite, canManage } from '../core/auth.js';
import { GET, POST, POST_FORM, DEL, download } from '../core/api.js';

const ASSET = () => (state.asset || (state.asset = {
  processId: null, package: null, preview: null, tab: 'overview',
}));

const HARD_BLOCKERS = new Set(['MODEL_NOT_VERSIONED', 'NODE_ACTIVITY_UNMAPPED']);

function errorText(error) {
  const raw = error && error.message ? error.message : '操作失败';
  try {
    const detail = JSON.parse(raw);
    if (detail && detail.message) {
      const blockers = (detail.blockers || []).map((row) => row.message).filter(Boolean).join('；');
      return blockers ? `${detail.message}：${blockers}` : detail.message;
    }
  } catch (_) { /* 不是 JSON，沿用原文 */ }
  return raw;
}

function tagTone(code) {
  return HARD_BLOCKERS.has(code) ? 't-red' : 't-yel';
}

function blockerAction(item) {
  const pid = ASSET().processId;
  if (item.code === 'MODEL_NOT_VERSIONED') {
    return `<button class="btn-sm mt" data-act="asset.go" data-view="designer"
      data-process="${pid}">去发布模型</button>`;
  }
  if (item.code === 'NODE_ACTIVITY_UNMAPPED') {
    return `<button class="btn-sm mt" data-act="asset.go" data-view="designer"
      data-tab="model" data-process="${pid}">去画模型 / 映射</button>`;
  }
  if (item.code === 'ACTIVITY_CARRIER_MISSING' || item.code === 'DECISION_RULE_MISSING') {
    return `<button class="btn-sm mt" data-act="asset.go" data-view="execution"
      data-tab="config" data-process="${pid}">去补表单 / 规则</button>`;
  }
  if (item.code === 'EVIDENCE_CONFLICT' || item.code === 'EVIDENCE_EXPIRED') {
    return `<button class="btn-sm mt" data-act="asset.go" data-view="monitor"
      data-tab="analysis" data-process="${pid}">去分析 / 裁决</button>`;
  }
  return `<button class="btn-sm mt" data-act="asset.go" data-view="designer"
    data-process="${pid}">去设计器</button>`;
}

function blockerHtml(item) {
  const targets = (item.targets || []).slice(0, 8).join('、');
  return `<div class="note" style="margin-bottom:8px">
    <div class="between"><b>${esc(item.message)}</b>
      <span class="tag ${tagTone(item.code)}">${esc(item.code)}</span></div>
    ${targets ? `<div class="tiny muted mt">${esc(targets)}</div>` : ''}
    ${blockerAction(item)}
  </div>`;
}

function relationHtml(map) {
  const editable = canWrite() && ASSET().readiness?.versioned;
  const rows = (map.nodes || []).map((node) => {
    const links = (node.links || []).map((link) => {
      const remove = editable && !link.legacy && link.id > 0
        ? ` <button class="btn-sm" data-act="asset.deleteLink"
            data-id="${link.id}">删除</button>`
        : '';
      return `${esc(link.relation)} ${esc(link.activity_code || link.activity_id)}`
        + ` <span class="tiny muted">${esc(link.path_condition)}</span>`
        + (link.legacy ? ' <span class="tag t-yel">兼容指针</span>' : '')
        + remove;
    }).join('<br>') || '<span class="tag t-yel">未映射</span>';
    return `<tr><td>${esc(node.node_key)} ${esc(node.name)}</td>
      <td>${esc(node.owner_role || '—')}</td><td>${links}</td></tr>`;
  }).join('');
  const relationRows = (map.activity_relations || []).map((row) => (
    `<tr><td>${esc(row.source_code || '')} ${esc(row.source_name || '')}</td>
      <td>${esc(row.relation)}</td>
      <td>${esc(row.target_code || '')} ${esc(row.target_name || '')}</td>
      <td>${editable ? `<button class="btn-sm" data-act="asset.deleteRelation"
        data-id="${row.id}">删除</button>` : '—'}</td></tr>`
  )).join('');
  const handoffRows = (map.handoffs || []).map((row) => (
    `<tr><td>${esc(row.edge_key)}</td><td>${esc(row.handoff_type)}</td>
      <td>${esc(row.confirmed_by_name || '—')}</td>
      <td>${editable ? `<button class="btn-sm" data-act="asset.deleteHandoff"
        data-id="${row.id}">删除</button>` : '—'}</td></tr>`
  )).join('');
  const unmodeled = (map.unmodeled || []).map((row) => (
    `<li>${esc(row.activity_code || '')} ${esc(row.activity_name || '')}：${esc(row.reason)}
      ${editable ? `<button class="btn-sm" data-act="asset.deleteUnmodeled"
        data-id="${row.id}">删除</button>` : ''}</li>`
  )).join('') || '<li class="tiny muted">无</li>';
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <h3>架构关系 ${tipHelp(
      '节点↔活动、活动关系、交接与未建模；关系是治理断言，确认后才生效。',
      '架构关系说明',
    )}</h3>
    ${editable ? `<div class="gap" style="margin-bottom:8px">
      <button class="btn-sm" data-act="asset.newLink">登记节点↔活动</button>
      <button class="btn-sm" data-act="asset.newRelation">登记活动关系</button>
      <button class="btn-sm" data-act="asset.newHandoff">登记交接</button>
      <button class="btn-sm" data-act="asset.newUnmodeled">登记未建模</button>
    </div>` : (canWrite() ? '<div class="tiny muted" style="margin-bottom:8px">先发布模型版本，才能登记关系。</div>' : '')}
    <table class="tbl">
      <thead><tr><th>节点</th><th>责任角色</th><th>关系</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="3" class="tiny muted">没有节点</td></tr>'}</tbody>
    </table>
    <div class="tiny muted mt">活动关系</div>
    <table class="tbl">
      <thead><tr><th>源活动</th><th>关系</th><th>目标活动</th><th>操作</th></tr></thead>
      <tbody>${relationRows || '<tr><td colspan="4" class="tiny muted">没有活动关系</td></tr>'}</tbody>
    </table>
    <div class="tiny muted mt">连线交接</div>
    <table class="tbl">
      <thead><tr><th>连线</th><th>类型</th><th>确认人</th><th>操作</th></tr></thead>
      <tbody>${handoffRows || '<tr><td colspan="4" class="tiny muted">没有交接记录</td></tr>'}</tbody>
    </table>
    <div class="tiny muted mt">未建模活动</div>
    <ul class="tiny">${unmodeled}</ul>
  </div>`;
}

function claimHtml(claims) {
  const rows = (claims.claims || []).map((claim) => {
    const adjudicated = (claim.adjudications || []).length > 0;
    const action = canManage() && claim.conflict_group && !adjudicated
      ? `<button class="btn-sm" data-act="asset.adjudicate"
          data-claim="${claim.id}">裁决</button>`
      : (adjudicated ? '<span class="tag t-grn">已裁决</span>' : '—');
    return `<tr><td>${esc(claim.claim)}</td><td>${esc(claim.method)}</td>
      <td>${esc(claim.samples ?? '—')}</td><td>${esc(claim.status)}</td>
      <td>${esc(claim.conflict_group || '—')}</td><td>${action}</td></tr>`;
  }).join('');
  const editable = canWrite() && ASSET().readiness?.versioned;
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <h3>证据主张 ${tipHelp(
      '主张级证据；未裁决冲突与未覆盖目标必须显式保留，不能当成无问题。',
      '证据账本说明',
    )}</h3>
    ${editable ? '<button class="btn-sm" data-act="asset.newClaim" style="margin-bottom:8px">登记证据主张</button>' : ''}
    <table class="tbl">
      <thead><tr><th>主张</th><th>方法</th><th>样本</th><th>状态</th><th>冲突组</th><th>操作</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="tiny muted">还没有证据主张</td></tr>'}</tbody>
    </table>
    <div class="tiny muted mt">未裁决：${esc((claims.conflicts || []).join('、') || '无')}</div>
    <div class="tiny muted">未覆盖：${esc((claims.unknown_targets || []).slice(0, 8).join('、') || '无')}</div>
  </div>`;
}

function packageHtml(pkg, blockers) {
  if (!pkg) {
    return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
      <div class="tiny muted">还没有生成资产包。先在阻断清零后生成 R0 草稿。</div></div>`;
  }
  const manifest = pkg.manifest || {};
  const blocked = blockers.length > 0;
  const tone = pkg.status === 'DRAFT' ? 't-gry' : (pkg.status === 'EFFECTIVE' ? 't-grn' : 't-yel');
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <div class="between">
      <h3>${esc(pkg.document_code)} · v${esc(pkg.version_label)}</h3>
      <span class="tag ${tone}">${esc(pkg.status_label || pkg.status)}</span>
    </div>
    <div class="tiny muted mt">模型 v${esc(manifest.model_version ?? '—')}
      · 生成于 ${esc(manifest.generated_at || '—')}
      · hash ${esc((pkg.content_hash || '').slice(0, 12))}…</div>
    <div class="gap mt">
      <button class="btn-sm" data-act="asset.openHtml">打开 HTML 预览</button>
      ${pkg.download_url ? '<button class="btn-sm" data-act="asset.download">下载 HTML</button>' : ''}
      ${pkg.pdf_url ? '<button class="btn-sm" data-act="asset.downloadPdf">下载 PDF</button>' : ''}
      <button class="btn-sm" data-act="asset.printPack" data-format="html">打印包 HTML</button>
      ${pkg.pdf_available ? '<button class="btn-sm" data-act="asset.printPack" data-format="pdf">打印包 PDF</button>' : ''}
      ${canManage() && pkg.status === 'DRAFT'
        ? `<button class="btn btn-p btn-sm" data-act="asset.transition"
            data-status="IN_REVIEW" ${blocked ? 'disabled' : ''}>提交评审</button>`
        : ''}
    </div>
    ${blocked ? '<div class="tiny muted mt">当前阻断未清零；提交评审会被后端拒绝。</div>' : ''}
  </div>`;
}

function sourceProfileHtml(profile) {
  if (!profile) {
    return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
      <h3>As-Is 来源画像</h3>
      <div class="tiny muted">来源画像加载失败。</div></div>`;
  }
  const canEdit = canWrite();
  const methodLabels = ASSET().claims?.labels?.method || {};
  const methodTags = Object.entries(profile.methods || {}).map(([code, count]) => (
    `<span class="tag t-mute">${esc(methodLabels[code] || code)} ${count}</span>`
  )).join(' ') || '<span class="tiny muted">还没有来源主张</span>';
  const uses = (profile.uses || []).map((row) => (
    `<tr><td>${esc(row.label)}</td>
      <td><span class="tag ${row.ready ? 't-grn' : 't-yel'}">${row.ready ? '可用' : '不可用'}</span></td>
      <td class="tiny muted">${esc(row.detail)}</td></tr>`
  )).join('');
  const activityRows = (profile.activities || []).map((row) => (
    `<tr><td>${esc(row.activity_code || '')} ${esc(row.activity_name || '')}</td>
      <td>${row.covered ? '<span class="tag t-grn">已覆盖</span>' : '<span class="tag t-yel">缺来源</span>'}</td>
      <td>${esc((row.methods || []).map((code) => methodLabels[code] || code).join('、') || '—')}</td></tr>`
  )).join('');
  const gaps = (profile.gaps || []).length
    ? `<div class="tiny muted mt">缺口：${esc(profile.gaps.join('、'))}</div>`
    : '';
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <div class="between">
      <h3>As-Is 来源画像 ${tipHelp(
        '说明这份 As-Is 模型有哪些来源、覆盖哪些活动；制度/访谈不能替代实测时间。',
        '来源画像说明',
      )}</h3>
      <div class="gap">
        ${canEdit ? `<button class="btn-sm" data-act="asset.newSource"
          ${profile.versioned ? '' : 'disabled'}>登记来源</button>
        <button class="btn-sm" data-act="asset.docExtract">从文档提取候选活动</button>
        <button class="btn-sm" data-act="asset.logImport">导入 CSV 日志</button>` : ''}
        <button class="btn-sm" data-act="asset.logCompare">日志前后对照</button>
      </div>
    </div>
    <div class="kpi-strip" style="grid-template-columns:repeat(4,1fr)">
      <div><b>${profile.claims_active || 0}<small>/${profile.claims_total || 0}</small></b><span>有效主张</span></div>
      <div><b>${profile.covered_activities || 0}<small>/${profile.activity_count || 0}</small></b><span>覆盖活动</span></div>
      <div><b>${profile.observed_time_claims || 0}</b><span>观测/日志时间</span></div>
      <div><b>${Object.keys(profile.source_types || {}).length}</b><span>来源类型</span></div>
    </div>
    <div class="mt">${methodTags}</div>
    <table class="tbl mt">
      <thead><tr><th>用途</th><th>就绪</th><th>说明</th></tr></thead>
      <tbody>${uses || '<tr><td colspan="3" class="tiny muted">没有用途数据</td></tr>'}</tbody>
    </table>
    <div class="tiny muted">下一步：${esc(profile.next_action)}</div>
    ${(profile.warnings || []).length
      ? `<div class="note mt tiny">${profile.warnings.map((item) => esc(item)).join('；')}</div>`
      : ''}
    <details class="mt">
      <summary class="tiny muted">活动覆盖明细</summary>
      <table class="tbl">
        <thead><tr><th>活动</th><th>状态</th><th>方法</th></tr></thead>
        <tbody>${activityRows || '<tr><td colspan="3" class="tiny muted">没有活动</td></tr>'}</tbody>
      </table>
      ${gaps}
    </details>
  </div>`;
}

function diagnosisPackageHtml(pkg, canSubmit) {
  if (!pkg) return '';
  const tone = pkg.status === 'DRAFT' ? 't-gry' : (pkg.status === 'EFFECTIVE' ? 't-grn' : 't-yel');
  return `<div class="note mt">
    <div class="between">
      <b>${esc(pkg.document_code)} · v${esc(pkg.version_label)}</b>
      <span class="tag ${tone}">${esc(pkg.status_label || pkg.status)}</span>
    </div>
    <div class="gap mt">
      <button class="btn-sm" data-act="asset.diagnosisOpen">打开 HTML</button>
      ${pkg.download_url ? '<button class="btn-sm" data-act="asset.diagnosisDownload">下载 HTML</button>' : ''}
      ${pkg.pdf_url ? '<button class="btn-sm" data-act="asset.diagnosisPdf">下载 PDF</button>' : ''}
      ${canManage() && pkg.status === 'DRAFT' && canSubmit
        ? '<button class="btn btn-p btn-sm" data-act="asset.diagnosisTransition">提交评审</button>'
        : ''}
    </div>
    ${pkg.status === 'DRAFT' && !canSubmit
      ? '<div class="tiny muted mt">R1 必填输入未齐，不能提交评审。</div>'
      : ''}
  </div>`;
}

function diagnosisHtml(readiness, diagnosis) {
  if (!readiness) {
    return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
      <h3>诊断证据包 R1</h3>
      <div class="tiny muted">R1 就绪度加载失败。</div></div>`;
  }
  const profile = readiness.source_profile || {};
  const uses = readiness.uses || [];
  const inputs = readiness.inputs || [];
  const blockers = readiness.blockers || [];
  const writable = canWrite();
  const methodLabels = ASSET().claims?.labels?.method || {};
  const useRows = uses.map((row) => (
    `<tr><td>${esc(row.label)}</td>
      <td><span class="tag ${row.ready ? 't-grn' : 't-yel'}">${row.ready ? '可用' : '不可用'}</span></td>
      <td class="tiny muted">${esc(row.detail)}</td></tr>`
  )).join('');
  const inputRows = inputs.map((row) => (
    `<tr><td>${esc(row.key)}</td><td>${esc(row.label)}</td>
      <td><span class="tag ${row.ready ? 't-grn' : (row.required ? 't-red' : 't-mute')}">
        ${row.ready ? '齐' : (row.required ? '缺' : '可选')}</span></td>
      <td class="tiny muted">${esc(row.detail)}</td></tr>`
  )).join('');
  const methods = Object.entries(profile.methods || {}).map(([code, count]) => (
    `<span class="tag t-mute">${esc(methodLabels[code] || code)} ${count}</span>`
  )).join(' ') || '<span class="tiny muted">还没有证据主张</span>';
  const pce = (readiness.metrics || {}).pce;
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <div class="between">
      <h3>诊断证据包 R1 ${tipHelp(
        '2.1–2.4 输入 + 模型 + 证据主张 → 来源画像、模型估算、瓶颈候选与未决项。',
        'R1 说明',
      )}</h3>
      <div class="gap">
        <span class="tag ${readiness.can_compile ? 't-grn' : 't-red'}">
          ${readiness.can_compile ? '可生成草稿' : '存在硬阻断'}</span>
        <span class="tag ${readiness.can_submit_review ? 't-grn' : 't-yel'}">
          ${readiness.can_submit_review ? '可提交评审' : '缺必填输入'}</span>
      </div>
    </div>
    <p class="tiny muted">2.1–2.4 输入 + 模型 + 证据主张 → 来源画像、模型估算、瓶颈候选与未决项。</p>
    <div class="kpi-strip" style="grid-template-columns:repeat(4,1fr)">
      <div><b>${profile.claims_active || 0}<small>/${profile.claims_total || 0}</small></b><span>有效主张</span></div>
      <div><b>${profile.covered_activities || 0}<small>/${profile.activity_count || 0}</small></b><span>覆盖活动</span></div>
      <div><b>${profile.observed_time_claims || 0}</b><span>观测/日志时间</span></div>
      <div><b>${pce !== undefined ? (pce * 100).toFixed(1) + '%' : '—'}</b><span>模型 PCE（估算）</span></div>
    </div>
    <div class="mt">${methods}</div>
    <table class="tbl mt">
      <thead><tr><th>R1 输入</th><th>要求</th><th>状态</th><th>说明</th></tr></thead>
      <tbody>${inputRows || '<tr><td colspan="4" class="tiny muted">没有输入数据</td></tr>'}</tbody>
    </table>
    <table class="tbl mt">
      <thead><tr><th>用途</th><th>就绪</th><th>说明</th></tr></thead>
      <tbody>${useRows || '<tr><td colspan="3" class="tiny muted">没有可用用途</td></tr>'}</tbody>
    </table>
    <div class="tiny muted">下一步：${esc(readiness.next_action)}</div>
    ${blockers.length
      ? `<div class="note mt tiny">${blockers.map((row) => esc(row.message)).join('；')}</div>`
      : ''}
    <div class="gap mt">
      <button class="btn-sm" data-act="asset.diagnosisPreview">预览 R1</button>
      <button class="btn btn-p btn-sm" data-act="asset.diagnosisCommit"
        ${readiness.can_compile && writable ? '' : 'disabled'}>生成 R1 草稿</button>
    </div>
    ${diagnosisPackageHtml(diagnosis, readiness.can_submit_review)}
  </div>`;
}

function impactHtml() {
  return `<div class="card" style="padding:16px 18px;margin-bottom:14px">
    <h3>变更影响</h3>
    <p class="tiny muted">给定活动/表单/规则，查哪些资产包版本引用了它。</p>
    <div class="gap mt">
      <select class="sel" id="assetImpactType" data-act="asset.impactType">
        <option value="ACTIVITY">活动</option>
        <option value="FORM_REF">表单</option>
        <option value="RULE_REF">规则</option>
      </select>
      <select class="sel" id="assetImpactRef"></select>
      <button class="btn btn-p" data-act="asset.impactQuery">查引用</button>
    </div>
    <div id="assetImpactResult" class="mt"></div>
  </div>`;
}

async function loadImpactRefs(type) {
  const pid = ASSET().processId;
  if (type === 'ACTIVITY') return activityOptions(pid);
  if (type === 'FORM_REF') {
    const rows = await GET(`/execution/forms?process_id=${pid}`);
    return rows.map((row) => ({
      id: row.id, label: `${row.name}（${row.node_key || '默认'}）`,
    }));
  }
  if (type === 'RULE_REF') {
    const rows = await GET(`/execution/rules?process_id=${pid}`);
    return rows.map((row) => ({ id: row.id, label: `${row.name}（${row.node_key}）` }));
  }
  return [];
}

function impactResultHtml(data) {
  if (!data.items || !data.items.length) {
    return '<div class="tiny muted">没有资产包引用这个组件。</div>';
  }
  const rows = data.items.map((item) => `<tr>
    <td>${esc(item.document_code)}
      <div class="tiny muted">${esc(item.document_title)}</div></td>
    <td>v${esc(item.version_label)}
      <div class="tiny muted">${esc(item.version_status_label)}</div></td>
    <td>${esc(item.process_code || '')} ${esc(item.process_name || '')}</td>
    <td>${esc(item.component_type_label)}
      ${item.activity_code ? `<div class="tiny muted">${esc(item.activity_code)} ${esc(item.activity_name || '')}</div>` : ''}</td>
    <td>${esc((item.source_hash || '').slice(0, 12))}</td>
    <td><button class="btn-sm" data-act="asset.impactOpen"
      data-version="${item.version_id}">查看</button></td>
  </tr>`).join('');
  return `<table class="tbl">
    <thead><tr><th>资产包</th><th>版本</th><th>流程</th><th>组件</th><th>hash</th><th>操作</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

async function queryImpact() {
  const type = document.getElementById('assetImpactType')?.value;
  const ref = Number(document.getElementById('assetImpactRef')?.value || 0);
  if (!type || !ref) {
    toast('请选择要查的组件', true);
    return;
  }
  const params = type === 'ACTIVITY'
    ? `activity_id=${ref}`
    : `component_type=${type}&component_ref_id=${ref}`;
  const target = document.getElementById('assetImpactResult');
  if (target) target.innerHTML = '<div class="empty">查询中…</div>';
  try {
    const data = await GET(`/asset-packages/impact?${params}`);
    if (target) target.innerHTML = impactResultHtml(data);
  } catch (error) {
    if (target) target.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function openImpactPackage(versionId) {
  try {
    const detail = await GET(`/asset-packages/${versionId}`);
    openHtmlModal(detail.preview_html);
  } catch (error) {
    toast(errorText(error), true);
  }
}

function paintPicker(rows) {
  const options = rows
    .filter((row) => row.level === 3 && !row.is_draft)
    .sort((a, b) => a.level - b.level || String(a.code).localeCompare(String(b.code)))
    .map((row) => `<option value="${row.id}">L${row.level} ${esc(row.code)} ${esc(row.name)}</option>`)
    .join('');
  viewEl().innerHTML = `
    <div class="card page-head">
      <div><h2>流程资产工作台</h2>
        <p class="desc">选一条 L3/L4 流程：看它能产出什么、还缺什么、下一步做什么。</p></div>
    </div>
    <div class="card" style="padding:18px 20px">
      <label class="tiny muted">选择流程</label>
      <select class="sel" data-act="asset.process" style="min-width:360px;display:block;margin-top:6px">
        <option value="">请选择</option>${options}
      </select>
      <p class="tiny muted mt">只显示已纳入目录的 L3 流程；草稿流程不进入资产生产。</p>
    </div>`;
}

function overviewHtml(readiness, blockers, writable) {
  const metrics = readiness.metrics || {};
  const missing = blockers.length ? `${blockers.length} 项待处理` : '没有阻断';
  const warnings = readiness.warnings && readiness.warnings.length
    ? `<div class="tiny muted mt">${readiness.warnings.map(esc).join('；')}</div>` : '';
  return `
    <div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:14px">
      <div class="card" style="padding:16px 18px">
        <div class="tiny muted">能产出什么</div>
        <h3 style="margin:6px 0">${readiness.can_generate_draft ? '活动级资产包 R0' : '还不能产出'}</h3>
        <div class="tiny muted">SOP 正文 · 活动责任 · 流程级 RACI · 控制点 · 表单引用</div>
      </div>
      <div class="card" style="padding:16px 18px">
        <div class="tiny muted">还缺什么</div>
        <h3 style="margin:6px 0">${esc(missing)}</h3>
        <div class="tiny muted">${esc(readiness.next_action)}</div>
      </div>
      <div class="card" style="padding:16px 18px">
        <div class="tiny muted">下一步做什么</div>
        <h3 style="margin:6px 0">${esc(readiness.next_action)}</h3>
        <div class="tiny muted">${writable
    ? '可生成草稿；提交评审前会重新跑阻断。' : '当前角色只读。'}</div>
      </div>
    </div>
    <div class="card" style="padding:16px 18px;margin-bottom:14px">
      <h3>生成就绪度</h3>
      <div class="grid" style="grid-template-columns:repeat(6,1fr);gap:10px;margin-top:12px">
        <div class="kpi"><div class="num">${metrics.activity_nodes || 0}</div><div class="lab">活动节点</div></div>
        <div class="kpi"><div class="num">${metrics.mapped_activities || 0}</div><div class="lab">已映射</div></div>
        <div class="kpi"><div class="num">${metrics.owner_ready || 0}</div><div class="lab">有责任角色</div></div>
        <div class="kpi"><div class="num">${metrics.carrier_ready || 0}</div><div class="lab">有表单载体</div></div>
        <div class="kpi"><div class="num">${metrics.rule_ready || 0}</div><div class="lab">规则就绪</div></div>
        <div class="kpi"><div class="num">${metrics.claims_total || 0}</div><div class="lab">证据主张</div></div>
      </div>
    </div>
    ${foldCard(
    '阻断与下一步',
    `${blockers.map(blockerHtml).join('') || '<div class="tiny muted">没有阻断，可以生成草稿并提交评审。</div>'}${warnings}`,
    { open: true },
  )}`;
}

function assetAside(readiness, pid, canGenerate) {
  const status = readiness.versioned
    ? `v${readiness.model_version}（${readiness.model_status}）` : '未发布';
  return `
    ${sideCard('流程状态', `
      <div class="kv"><span>层级</span><b>L3</b></div>
      <div class="kv"><span>模型</span><b>${esc(status)}</b></div>
      <div class="kv"><span>阻断</span><b>${(readiness.blockers || []).length}</b></div>
      <div class="kv"><span>下一步</span><b>${esc(readiness.next_action)}</b></div>`)}
    ${sideCard('主操作', `
      <button class="btn btn-p" style="width:100%" data-act="asset.generate"
        ${canGenerate ? '' : 'disabled'}>生成资产包草稿</button>
      <button class="btn btn-g mt" style="width:100%" data-act="asset.go"
        data-view="designer" data-process="${pid}">打开设计器</button>
      <button class="btn btn-g mt" style="width:100%" data-act="asset.pick">切换流程</button>`)}`;
}

function paintAsset(pid, data) {
  const {
    readiness, map, claims, pkg, diagnosisReadiness, diagnosis, sourceProfile,
  } = data;
  Object.assign(ASSET(), {
    readiness, map, claims, diagnosisReadiness, diagnosis, sourceProfile, data,
  });
  const blockers = readiness.blockers || [];
  const writable = canWrite();
  const stateLabel = readiness.versioned
    ? `模型 v${readiness.model_version}（${readiness.model_status}）`
    : '未发布模型';
  const missing = blockers.length
    ? `${blockers.length} 项待处理`
    : '没有阻断';
  const canGenerate = readiness.can_generate_draft && writable;

  const sections = {
    overview: overviewHtml(readiness, blockers, writable),
    package: packageHtml(pkg, blockers),
    sources: sourceProfileHtml(sourceProfile),
    diagnosis: diagnosisHtml(diagnosisReadiness, diagnosis),
    architecture: relationHtml(map),
    evidence: claimHtml(claims),
    impact: impactHtml(),
  };
  if (!sections[ASSET().tab]) ASSET().tab = 'overview';
  const sectionList = [
    { key: 'overview', label: '概览', count: blockers.length, html: sections.overview },
    { key: 'package', label: '资产包', html: sections.package },
    { key: 'sources', label: '来源画像', count: sourceProfile?.claims_active, html: sections.sources },
    {
      key: 'diagnosis',
      label: '诊断 R1',
      count: diagnosisReadiness?.missing_inputs?.length,
      html: sections.diagnosis,
    },
    { key: 'architecture', label: '架构关系', count: map?.nodes?.length, html: sections.architecture },
    { key: 'evidence', label: '证据账本', count: claims?.claims?.length, html: sections.evidence },
    { key: 'impact', label: '变更影响', html: sections.impact },
  ];

  const shell = pageShell({
    title: `${esc(readiness.process_code)} ${esc(readiness.process_name)}`,
    badge: `<span class="tag t-blu">L3</span>
      <span class="tag ${readiness.versioned ? 't-grn' : 't-yel'}">${esc(stateLabel)}</span>
      <span class="tag ${blockers.length ? 't-yel' : 't-grn'}">${esc(missing)}</span>`,
    subtitle: '一条流程的模型、资产、证据与日志都在这里。',
    tip: tipHelp(
      '关系与证据可在本页维护；阻断也可去设计器、执行运行配置或分析页处理。'
      + '资产包是流程级 SOP，不是项目交付物。',
      '本页说明',
    ),
    actions: `<button class="btn btn-g" data-act="asset.pick">切换流程</button>
      <button class="btn btn-g" data-act="asset.go" data-view="designer"
        data-process="${pid}">打开设计器</button>`,
    sections: sectionList,
    active: ASSET().tab,
    tabAct: 'asset.tab',
    aside: assetAside(readiness, pid, canGenerate),
  });
  ASSET().tab = shell.active;
  viewEl().innerHTML = shell.html;

  if (ASSET().tab === 'impact') {
    const currentPid = ASSET().processId;
    loadImpactRefs('ACTIVITY').then((items) => {
      if (ASSET().processId !== currentPid) return;
      const ref = document.getElementById('assetImpactRef');
      if (!ref) return;
      ref.innerHTML = optionsHtml(items);
      if (items.length) ref.value = String(items[0].id);
    }).catch(() => {});
  }
}

async function latestCompiled(documents, prefix, pid) {
  const document = (documents || []).find((row) => (row.code || '').startsWith(prefix));
  if (!document) return null;
  const detail = await GET(`/process-documents/${document.id}`);
  const versions = (detail.versions || []).filter((row) => row.source_kind === 'COMPILED');
  if (!versions.length) return null;
  const latest = versions.reduce((left, right) => (left.id > right.id ? left : right));
  const pkg = await GET(`/asset-packages/${latest.id}`).catch(() => null);
  return pkg ? { ...pkg, process_id: pid } : null;
}

async function loadAsset(pid) {
  const [readiness, map, claims, documents, diagnosisReadiness, sourceProfile] = await Promise.all([
    GET(`/processes/${pid}/asset-readiness`),
    GET(`/processes/${pid}/architecture-map`),
    GET(`/processes/${pid}/evidence-claims`),
    GET(`/process-documents?process_id=${pid}`),
    GET(`/processes/${pid}/r1-readiness`),
    GET(`/processes/${pid}/model-source-profile`),
  ]);
  let pkg = ASSET().package;
  if (!pkg || pkg.process_id !== pid) pkg = await latestCompiled(documents, 'AP-', pid);
  let diagnosis = ASSET().diagnosis;
  if (!diagnosis || diagnosis.process_id !== pid) {
    diagnosis = await latestCompiled(documents, 'DG-', pid);
  }
  return { readiness, map, claims, pkg, diagnosisReadiness, diagnosis, sourceProfile };
}

export async function renderAsset() {
  const params = urlParams();
  const pid = Number(params.process) || ASSET().processId || 0;
  if (!pid) {
    return renderAsync('asset', () => GET('/process-map/flat'), paintPicker);
  }
  if (ASSET().processId !== pid) ASSET().tab = 'overview';
  ASSET().processId = pid;
  if (ASSET().package && ASSET().package.process_id !== pid) ASSET().package = null;
  return renderAsync('asset', () => loadAsset(pid), (data) => paintAsset(pid, data));
}

function optionsHtml(items, placeholder = '请选择') {
  return `<option value="">${esc(placeholder)}</option>` + items.map((item) => (
    `<option value="${esc(item.id)}">${esc(item.label)}</option>`
  )).join('');
}

async function activityOptions(pid) {
  const rows = await GET('/process-map/flat');
  return rows
    .filter((row) => row.level === 4 && row.parent_id === pid && !row.is_draft)
    .sort((a, b) => String(a.code).localeCompare(String(b.code)))
    .map((row) => ({ id: row.id, label: `${row.code} ${row.name}` }));
}

function nodeLinkOptions() {
  return (ASSET().map?.nodes || [])
    .filter((node) => node.node_type !== 'START' && node.node_type !== 'END')
    .map((node) => ({ id: node.node_key, label: `${node.node_key} ${node.name}` }));
}

function nodeTargetOptions() {
  return (ASSET().map?.nodes || []).map((node) => ({
    id: node.id, label: `${node.node_key} ${node.name}`,
  }));
}

async function revokeRelation(kind, id) {
  const ok = await confirmDialog('撤销后需要重新登记，确定删除？', {
    title: '撤销关系', okText: '删除', danger: true,
  });
  if (!ok) return;
  const pid = ASSET().processId;
  const paths = {
    link: `/processes/${pid}/architecture-map/links/${id}`,
    relation: `/processes/${pid}/architecture-map/relations/${id}`,
    handoff: `/processes/${pid}/architecture-map/handoffs/${id}`,
    unmodeled: `/processes/${pid}/architecture-map/unmodeled/${id}`,
  };
  try {
    await DEL(paths[kind]);
    toast('已撤销');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openNewLink() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记架构关系', true);
    return;
  }
  const activities = await activityOptions(pid);
  if (!activities.length) {
    toast('该流程还没有 L4 活动，请先去流程地图补充', true);
    return;
  }
  openModal('登记节点 ↔ 活动', `
    <div class="field"><label>节点</label>
      <select class="sel" id="assetLinkNode">${optionsHtml(nodeLinkOptions())}</select></div>
    <div class="field"><label>L4 活动</label>
      <select class="sel" id="assetLinkActivity">${optionsHtml(activities)}</select></div>
    <div class="field"><label>关系</label>
      <select class="sel" id="assetLinkRelation">
        <option value="REALIZES">REALIZES · 实现</option>
        <option value="PART_OF">PART_OF · 组成</option>
        <option value="CONTROLS">CONTROLS · 控制点</option>
      </select></div>
    <div class="field"><label>路径</label>
      <select class="sel" id="assetLinkPath">
        <option value="STANDARD">标准路径</option>
        <option value="EXCEPTION">异常路径</option>
        <option value="ALL">全部</option>
      </select></div>
    <div class="field"><label>覆盖（0–1）</label>
      <input id="assetLinkCoverage" type="number" min="0" max="1" step="0.05" value="1"></div>
    <div class="field"><label>说明（可选）</label><input id="assetLinkNote"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitLink">保存关系</button>`);
}

async function submitLink() {
  const pid = ASSET().processId;
  const nodeKey = document.getElementById('assetLinkNode')?.value;
  const activityId = Number(document.getElementById('assetLinkActivity')?.value || 0);
  if (!nodeKey || !activityId) {
    toast('请选择节点和 L4 活动', true);
    return;
  }
  const payload = {
    node_key: nodeKey,
    activity_id: activityId,
    relation: document.getElementById('assetLinkRelation')?.value,
    path_condition: document.getElementById('assetLinkPath')?.value,
    coverage: Number(document.getElementById('assetLinkCoverage')?.value || 1),
    note: (document.getElementById('assetLinkNote')?.value || '').trim() || null,
  };
  try {
    await POST(`/processes/${pid}/architecture-map/links`, payload);
    closeModal();
    toast('节点↔活动关系已保存');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openNewRelation() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记架构关系', true);
    return;
  }
  const activities = await activityOptions(pid);
  if (activities.length < 2) {
    toast('至少需要两个 L4 活动才能登记活动关系', true);
    return;
  }
  openModal('登记活动 ↔ 活动', `
    <div class="field"><label>源活动</label>
      <select class="sel" id="assetRelSource">${optionsHtml(activities)}</select></div>
    <div class="field"><label>目标活动</label>
      <select class="sel" id="assetRelTarget">${optionsHtml(activities)}</select></div>
    <div class="field"><label>关系</label>
      <select class="sel" id="assetRelType">
        <option value="DECOMPOSES">DECOMPOSES · 分解</option>
        <option value="PART_OF">PART_OF · 组成</option>
        <option value="TRIGGERS">TRIGGERS · 触发</option>
        <option value="SERVES">SERVES · 支撑</option>
      </select></div>
    <div class="field"><label>说明（可选）</label><input id="assetRelNote"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitRelation">保存关系</button>`);
}

async function submitRelation() {
  const pid = ASSET().processId;
  const source = Number(document.getElementById('assetRelSource')?.value || 0);
  const target = Number(document.getElementById('assetRelTarget')?.value || 0);
  if (!source || !target) {
    toast('请选择源活动和目标活动', true);
    return;
  }
  try {
    await POST(`/processes/${pid}/architecture-map/relations`, {
      source_activity_id: source,
      target_activity_id: target,
      relation: document.getElementById('assetRelType')?.value,
      note: (document.getElementById('assetRelNote')?.value || '').trim() || null,
    });
    closeModal();
    toast('活动关系已保存');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openNewHandoff() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记交接', true);
    return;
  }
  const activities = await activityOptions(pid);
  openModal('登记连线交接', `
    <div class="field"><label>连线键 *</label>
      <input id="assetHandoffEdge" placeholder="例如 n1->n2 或 n1→n2"></div>
    <div class="field"><label>来源活动（可选）</label>
      <select class="sel" id="assetHandoffFrom">${optionsHtml(activities, '不指定')}</select></div>
    <div class="field"><label>接收活动（可选）</label>
      <select class="sel" id="assetHandoffTo">${optionsHtml(activities, '不指定')}</select></div>
    <div class="field"><label>交接类型</label>
      <select class="sel" id="assetHandoffType">
        <option value="HANDOFF">HANDOFF · 跨部门/跨活动交接</option>
        <option value="NO_HANDOFF">NO_HANDOFF · 显式无交接</option>
      </select></div>
    <div class="field"><label>说明（可选）</label><input id="assetHandoffNote"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitHandoff">保存交接</button>`);
}

async function submitHandoff() {
  const pid = ASSET().processId;
  const edgeKey = (document.getElementById('assetHandoffEdge')?.value || '').trim();
  if (!edgeKey) {
    toast('请填写连线键', true);
    return;
  }
  const from = Number(document.getElementById('assetHandoffFrom')?.value || 0);
  const to = Number(document.getElementById('assetHandoffTo')?.value || 0);
  try {
    await POST(`/processes/${pid}/architecture-map/handoffs`, {
      edge_key: edgeKey,
      from_activity_id: from || null,
      to_activity_id: to || null,
      handoff_type: document.getElementById('assetHandoffType')?.value,
      note: (document.getElementById('assetHandoffNote')?.value || '').trim() || null,
    });
    closeModal();
    toast('交接已保存');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openNewUnmodeled() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记未建模活动', true);
    return;
  }
  const activities = await activityOptions(pid);
  if (!activities.length) {
    toast('该流程还没有 L4 活动', true);
    return;
  }
  openModal('登记未建模活动', `
    <div class="field"><label>L4 活动</label>
      <select class="sel" id="assetUnmodeledActivity">${optionsHtml(activities)}</select></div>
    <div class="field"><label>原因 *</label>
      <textarea id="assetUnmodeledReason" rows="3"
        placeholder="例如：线下电话确认，模型没有对应节点"></textarea></div>
    <div class="field"><label>来源引用（可选）</label>
      <input id="assetUnmodeledSource" placeholder="访谈日期、制度编号等"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitUnmodeled">保存</button>`);
}

async function submitUnmodeled() {
  const pid = ASSET().processId;
  const activityId = Number(document.getElementById('assetUnmodeledActivity')?.value || 0);
  const reason = (document.getElementById('assetUnmodeledReason')?.value || '').trim();
  if (!activityId || !reason) {
    toast('请选择活动并写明原因', true);
    return;
  }
  try {
    await POST(`/processes/${pid}/architecture-map/unmodeled`, {
      activity_id: activityId,
      reason,
      source_ref: (document.getElementById('assetUnmodeledSource')?.value || '').trim() || null,
    });
    closeModal();
    toast('未建模活动已登记');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function loadClaimSources(pid) {
  const items = [];
  try {
    const card = await GET(`/process-card/${pid}`);
    for (const sheet of card.sheets || []) {
      items.push({
        value: `TOOL_SHEET:${sheet.id}`,
        label: `工具表 · ${sheet.tool_name || sheet.tool_code} · ${sheet.title}`,
      });
    }
  } catch (_) { /* 流程卡不可用不影响制度来源 */ }
  try {
    const docs = await GET(`/process-documents?process_id=${pid}`);
    for (const doc of docs.slice(0, 20)) {
      const detail = await GET(`/process-documents/${doc.id}`);
      for (const version of detail.versions || []) {
        if (version.status === 'EFFECTIVE') {
          items.push({
            value: `DOCUMENT_VERSION:${version.id}`,
            label: `制度 · ${doc.code} ${doc.title} v${version.version_label}`,
          });
        }
      }
    }
  } catch (_) { /* 无制度来源 */ }
  return items;
}

async function openNewClaim() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记证据', true);
    return;
  }
  const [activities, sources] = await Promise.all([activityOptions(pid), loadClaimSources(pid)]);
  if (!sources.length) {
    openModal('登记证据主张', `
      <div class="empty">没有可引用的来源。先去工具箱填写方法记录，或上传并生效一份制度版本。</div>`,
    `<button class="btn btn-g" data-act="ui.close">关闭</button>
     <button class="btn btn-p" data-act="asset.go" data-view="toolbox"
       data-process="${pid}">去工具箱</button>`);
    return;
  }
  const nodes = nodeTargetOptions();
  const targets = [
    ...activities.map((item) => ({ id: `ACTIVITY:${item.id}`, label: `活动 · ${item.label}` })),
    ...activities.map((item) => ({ id: `TIME_FIELD:${item.id}`, label: `时间字段 · ${item.label}` })),
    ...nodes.map((item) => ({ id: `NODE:${item.id}`, label: `节点 · ${item.label}` })),
  ];
  const sourceOptions = sources.map((item) => (
    `<option value="${esc(item.value)}">${esc(item.label)}</option>`
  )).join('');
  openModal('登记证据主张', `
    <div class="field"><label>主张 *</label>
      <textarea id="assetClaimText" rows="2"
        placeholder="一条可检验的主张，例如：A-04 平均等待 180 分钟"></textarea></div>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
      <div class="field"><label>主张类型</label>
        <select class="sel" id="assetClaimType">
          <option value="EXISTENCE">是否存在</option>
          <option value="CONTROL">控制</option>
          <option value="TIME">时间</option>
          <option value="ROLE">责任</option>
          <option value="RULE">规则</option>
          <option value="SEQUENCE">顺序</option>
          <option value="OUTCOME">结果</option>
        </select></div>
      <div class="field"><label>方法</label>
        <select class="sel" id="assetClaimMethod">
          <option value="OBSERVED">现场观测</option>
          <option value="DOCUMENTED">制度文本</option>
          <option value="STATED">访谈陈述</option>
          <option value="ESTIMATED">估算</option>
          <option value="LOGGED">系统日志</option>
          <option value="UNKNOWN">来源待核</option>
        </select></div>
    </div>
    <div class="field"><label>来源 *</label>
      <select class="sel" id="assetClaimSource">${sourceOptions}</select></div>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
      <div class="field"><label>目标 *</label>
        <select class="sel" id="assetClaimTarget">${optionsHtml(targets)}</select></div>
      <div class="field"><label>时间字段（TIME_FIELD 必填）</label>
        <input id="assetClaimField" placeholder="例如 wait 或 duration"></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr 1fr;gap:10px">
      <div class="field"><label>条件</label>
        <select class="sel" id="assetClaimCondition">
          <option value="STANDARD">标准路径</option>
          <option value="EXCEPTION">异常路径</option>
          <option value="ALL">全部</option>
        </select></div>
      <div class="field"><label>样本量</label>
        <input id="assetClaimSamples" type="number" min="0"></div>
      <div class="field"><label>覆盖（0–1）</label>
        <input id="assetClaimCoverage" type="number" min="0" max="1" step="0.05"></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
      <div class="field"><label>窗口开始</label>
        <input id="assetClaimWindowStart" type="datetime-local"></div>
      <div class="field"><label>窗口结束</label>
        <input id="assetClaimWindowEnd" type="datetime-local"></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
      <div class="field"><label>有效期开始</label>
        <input id="assetClaimValidFrom" type="date"></div>
      <div class="field"><label>有效期结束</label>
        <input id="assetClaimValidTo" type="date"></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
      <div class="field"><label>状态</label>
        <select class="sel" id="assetClaimStatus">
          <option value="OPEN">待核</option>
          <option value="CONFLICTED">冲突</option>
        </select></div>
      <div class="field"><label>冲突组（冲突状态必填）</label>
        <input id="assetClaimGroup" placeholder="例如 CG-03"></div>
    </div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitClaim">保存主张</button>`);
}

async function submitClaim() {
  const pid = ASSET().processId;
  const text = (document.getElementById('assetClaimText')?.value || '').trim();
  const source = document.getElementById('assetClaimSource')?.value || '';
  const target = document.getElementById('assetClaimTarget')?.value || '';
  const status = document.getElementById('assetClaimStatus')?.value || 'OPEN';
  const group = (document.getElementById('assetClaimGroup')?.value || '').trim();
  if (!text) {
    toast('请填写主张', true);
    return;
  }
  if (!source || !target) {
    toast('请选择来源和目标', true);
    return;
  }
  if (status === 'CONFLICTED' && !group) {
    toast('冲突状态必须填写冲突组', true);
    return;
  }
  const [sourceType, sourceId] = source.split(':');
  const [targetType, targetId] = target.split(':');
  const field = (document.getElementById('assetClaimField')?.value || '').trim();
  if (targetType === 'TIME_FIELD' && !field) {
    toast('时间字段目标必须填写 field', true);
    return;
  }
  const numberOrNull = (id) => {
    const value = document.getElementById(id)?.value;
    return value === undefined || value === '' ? null : Number(value);
  };
  const valueOrNull = (id) => {
    const value = document.getElementById(id)?.value;
    return value === undefined || value === '' ? null : value;
  };
  const payload = {
    claim: text,
    claim_type: document.getElementById('assetClaimType')?.value,
    source_type: sourceType,
    source_id: Number(sourceId),
    method: document.getElementById('assetClaimMethod')?.value,
    samples: numberOrNull('assetClaimSamples'),
    window_start: valueOrNull('assetClaimWindowStart'),
    window_end: valueOrNull('assetClaimWindowEnd'),
    coverage: numberOrNull('assetClaimCoverage'),
    conflict_group: group || null,
    status,
    valid_from: valueOrNull('assetClaimValidFrom'),
    valid_to: valueOrNull('assetClaimValidTo'),
    targets: [{
      target_type: targetType,
      target_id: Number(targetId),
      field: targetType === 'TIME_FIELD' ? field : null,
      condition: document.getElementById('assetClaimCondition')?.value,
    }],
  };
  try {
    await POST(`/processes/${pid}/evidence-claims`, payload);
    closeModal();
    toast('证据主张已保存');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

function candidateListHtml(items) {
  if (!items.length) {
    return '<div class="tiny muted">没有识别到编号或项目符号步骤。</div>';
  }
  const rows = items.map((item) => {
    let action = '—';
    if (item.status === 'PROPOSED') {
      action = `<button class="btn-sm" data-act="asset.confirmCandidate"
          data-id="${item.id}">确认</button>
        <button class="btn-sm" data-act="asset.rejectCandidate"
          data-id="${item.id}">驳回</button>`;
    } else if (item.status === 'CONFIRMED') {
      action = `<span class="tag t-grn">${esc(item.activity_code || '已确认')}</span>`;
    } else if (item.status === 'REJECTED') {
      action = '<span class="tag t-mute">已驳回</span>';
    }
    return `<tr><td class="num">${item.line_no}</td><td>${esc(item.text)}</td>
      <td>${esc(item.confidence)}</td><td>${esc(item.status)}</td>
      <td>${action}</td></tr>`;
  }).join('');
  return `<table class="tbl">
    <thead><tr><th>行</th><th>候选活动</th><th>识别</th><th>状态</th><th>操作</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function refreshCandidates() {
  const pid = ASSET().processId;
  const versionId = Number(document.getElementById('docCandidateVersion')?.value || 0);
  if (!versionId) return;
  const target = document.getElementById('docCandidateList');
  try {
    const items = await GET(
      `/processes/${pid}/document-candidates?document_version_id=${versionId}`,
    );
    if (target) target.innerHTML = candidateListHtml(items);
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openDocumentExtract() {
  const pid = ASSET().processId;
  if (!canWrite()) {
    toast('当前角色只读', true);
    return;
  }
  try {
    const sources = await loadClaimSources(pid);
    const documents = sources.filter((item) => item.value.startsWith('DOCUMENT_VERSION:'));
    if (!documents.length) {
      openModal('从文档提取候选活动', `
        <div class="empty">没有已生效的制度/SOP 版本可引用。先去交付物或制度库上传并生效一份文档。</div>`,
      `<button class="btn btn-g" data-act="ui.close">关闭</button>
       <button class="btn btn-p" data-act="asset.go" data-view="deliverables"
         data-process="${pid}">去交付物</button>`);
      return;
    }
    const options = documents.map((item) => (
      `<option value="${esc(item.value.split(':')[1])}">${esc(item.label)}</option>`
    )).join('');
    openModal('从文档提取候选活动', `
      <div class="field"><label>已生效文档版本</label>
        <select class="sel" id="docCandidateVersion">${options}</select></div>
      <div class="note tiny">只解析编号或项目符号步骤；确认只创建 L4 活动，不自动改 BPMN，
        也不等于 As-Is 实测。确认后仍需去设计器把活动映射到节点。</div>
      <div class="gap mt">
        <button class="btn btn-p" data-act="asset.extractCandidates">开始提取</button>
      </div>
      <div id="docCandidateList" class="mt"></div>`,
    `<button class="btn btn-g" data-act="ui.close">关闭</button>
     <button class="btn btn-p" data-act="asset.closeDocExtract">完成</button>`, 'sheet');
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function extractCandidates() {
  const pid = ASSET().processId;
  const versionId = Number(document.getElementById('docCandidateVersion')?.value || 0);
  if (!versionId) {
    toast('请选择文档版本', true);
    return;
  }
  const target = document.getElementById('docCandidateList');
  if (target) target.innerHTML = '<div class="empty">提取中…</div>';
  try {
    const items = await POST(
      `/processes/${pid}/document-candidates/extract`,
      { document_version_id: versionId },
    );
    if (target) target.innerHTML = candidateListHtml(items);
    toast(`识别到 ${items.length} 条候选`);
  } catch (error) {
    if (target) target.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function confirmCandidate(id) {
  const pid = ASSET().processId;
  try {
    const row = await POST(
      `/processes/${pid}/document-candidates/${id}/confirm`,
      {},
    );
    toast(`已创建 ${row.activity_code || 'L4 活动'}`);
    await refreshCandidates();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function rejectCandidate(id) {
  const pid = ASSET().processId;
  try {
    await POST(`/processes/${pid}/document-candidates/${id}/reject`, {});
    toast('已驳回');
    await refreshCandidates();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openLogImport() {
  const pid = ASSET().processId;
  if (!canWrite()) {
    toast('当前角色只读', true);
    return;
  }
  const activities = await activityOptions(pid);
  ASSET().logActivities = activities;
  if (!activities.length) {
    toast('该流程还没有 L4 活动，先补充活动再映射日志', true);
    return;
  }
  openModal('导入 CSV 事件日志', `
    <div class="note tiny">CSV 需含 case_id、activity、timestamp 列，可选 resource；
      UTF-8；≤20MB / 5 万行。</div>
    <div class="field mt"><label>CSV 文件</label>
      <input type="file" id="logFile" accept=".csv"></div>
    <button class="btn btn-p" data-act="asset.uploadLog">上传并解析</button>
    <div id="logImportBody" class="mt"></div>`,
  `<button class="btn btn-g" data-act="ui.close">关闭</button>
   <button class="btn btn-p" data-act="asset.closeLogImport">完成</button>`, 'sheet');
}

function logMappingHtml(data) {
  const activities = ASSET().logActivities || [];
  const rows = (data.labels || []).map((label) => {
    const selectedId = label.mapped_activity_id || label.suggested_activity_id;
    const options = activities.map((item) => (
      `<option value="${item.id}"${selectedId === item.id ? ' selected' : ''}>${esc(item.label)}</option>`
    )).join('');
    const hint = !label.mapped_activity_id && label.suggestion_reason
      ? ` <span class="tag t-yel">建议：${esc(label.suggestion_reason)}</span>` : '';
    return `<tr><td>${esc(label.label)}<div class="tiny muted">${label.count} 条</div></td>
      <td><select class="sel" data-log-label="${esc(label.label)}">
        <option value="">忽略</option>${options}</select>${hint}</td></tr>`;
  }).join('');
  return `<div class="tiny muted">${data.case_count} 单 / ${data.row_count} 事件
      · ${esc(data.file_name)}</div>
    <table class="tbl"><thead><tr><th>日志活动标签</th><th>映射到 L4 活动</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="2" class="tiny muted">没有标签</td></tr>'}</tbody></table>
    <button class="btn btn-p mt" data-act="asset.mapLog">计算指标</button>
    <div id="logMetrics" class="mt"></div>`;
}

function logMetricsHtml(data) {
  const metrics = data.metrics || {};
  const lead = metrics.lead_time_minutes || {};
  const variants = (metrics.variants || []).slice(0, 5).map((row) => (
    `<li>${esc(row.sequence)} <span class="tiny muted">× ${row.cases}</span></li>`
  )).join('') || '<li class="tiny muted">无</li>';
  return `<div class="kpi-strip" style="grid-template-columns:repeat(4,1fr)">
    <div><b>${metrics.case_count || 0}</b><span>单量</span></div>
    <div><b>${lead.mean ?? '—'}</b><span>平均周期(分)</span></div>
    <div><b>${lead.median ?? '—'}</b><span>中位(分)</span></div>
    <div><b>${Math.round((metrics.mapping_coverage || 0) * 100)}%</b><span>映射覆盖</span></div>
  </div>
  <div class="tiny muted mt">窗口 ${esc(metrics.window_start || '—')}
    → ${esc(metrics.window_end || '—')}
    · 未映射事件 ${metrics.unmapped_events || 0}</div>
  <div class="tiny muted mt">Top variants</div>
  <ul class="tiny">${variants}</ul>
  <button class="btn btn-p mt" data-act="asset.commitLog">提交为实测证据</button>`;
}

async function uploadLogImport() {
  const pid = ASSET().processId;
  const file = document.getElementById('logFile')?.files?.[0];
  if (!file) {
    toast('请选择 CSV 文件', true);
    return;
  }
  const body = document.getElementById('logImportBody');
  if (body) body.innerHTML = '<div class="empty">解析中…</div>';
  const form = new FormData();
  form.append('file', file, file.name);
  try {
    const data = await POST_FORM(`/processes/${pid}/log-imports`, form);
    ASSET().logImport = data;
    if (body) body.innerHTML = logMappingHtml(data);
  } catch (error) {
    if (body) body.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function mapLogImport() {
  const pid = ASSET().processId;
  const mapping = {};
  document.querySelectorAll('[data-log-label]').forEach((el) => {
    mapping[el.dataset.logLabel] = el.value ? Number(el.value) : null;
  });
  const target = document.getElementById('logMetrics');
  if (target) target.innerHTML = '<div class="empty">计算中…</div>';
  try {
    const data = await POST(
      `/processes/${pid}/log-imports/${ASSET().logImport.id}/map`,
      { mapping },
    );
    ASSET().logImport = data;
    if (target) target.innerHTML = logMetricsHtml(data);
  } catch (error) {
    if (target) target.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function commitLogImport() {
  const pid = ASSET().processId;
  try {
    const data = await POST(
      `/processes/${pid}/log-imports/${ASSET().logImport.id}/commit`,
      {},
    );
    ASSET().logImport = data;
    closeModal();
    toast(`日志已提交为实测证据${data.claim_id ? ' #' + data.claim_id : ''}`);
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

const COMPARE_LABELS = {
  mean_lead_minutes: '平均周期(分)',
  median_lead_minutes: '中位周期(分)',
  p90_lead_minutes: 'P90(分)',
  case_count: '单量',
  event_count: '事件数',
  mapping_coverage: '映射覆盖',
};

const RECEIPT_LABELS = { ACCEPT: '接收', RETURN: '退回', OBSERVE: '观察' };

function compareValue(key, value) {
  if (value === null || value === undefined) return '—';
  if (key === 'mapping_coverage') return `${(value * 100).toFixed(1)}%`;
  return Number(value).toFixed(2);
}

function compareDelta(value) {
  if (value === null || value === undefined) return '—';
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`;
}

function comparePct(value) {
  if (value === null || value === undefined) return '—';
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function variantList(items) {
  const rows = (items || []).slice(0, 3).map((row) => (
    `<li>${esc(row.sequence)} <span class="tiny muted">× ${row.cases}</span></li>`
  )).join('');
  return rows || '<li class="tiny muted">无</li>';
}

function comparisonHtml(data) {
  const rows = Object.entries(COMPARE_LABELS).map(([key, label]) => {
    const metric = data.metrics[key] || {};
    return `<tr><td>${label}</td>
      <td class="num">${compareValue(key, metric.before)}</td>
      <td class="num">${compareValue(key, metric.after)}</td>
      <td class="num">${compareDelta(metric.delta)}</td>
      <td class="num">${comparePct(metric.delta_pct)}</td></tr>`;
  }).join('');
  const reasons = (data.reasons || []).length
    ? `<div class="note tiny">不可比：${data.reasons.map((item) => esc(item)).join('；')}</div>`
    : '';
  const warnings = (data.warnings || []).length
    ? `<div class="note tiny">提示：${data.warnings.map((item) => esc(item)).join('；')}</div>`
    : '';
  return `<div class="between">
      <span class="tag ${data.comparable ? 't-grn' : 't-red'}">${data.comparable ? '可比较' : '不可比'}</span>
      <span class="tiny muted">${esc(data.before.file_name)} → ${esc(data.after.file_name)}</span>
    </div>
    ${reasons}${warnings}
    <table class="tbl mt">
      <thead><tr><th>指标</th><th>改善前</th><th>改善后</th><th>变化</th><th>变化%</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:12px">
      <div><div class="tiny muted">改善前 Top 变体</div><ul class="tiny">${variantList(data.variants?.before)}</ul></div>
      <div><div class="tiny muted">改善后 Top 变体</div><ul class="tiny">${variantList(data.variants?.after)}</ul></div>
    </div>
    <div class="note mt tiny">${esc(data.conclusion)}</div>`;
}

function receiptHistoryHtml(receipts) {
  if (!receipts.length) return '<div class="tiny muted mt">还没有接收记录。</div>';
  const rows = receipts.slice(0, 5).map((row) => `<tr>
      <td><span class="tag ${row.decision === 'ACCEPT' ? 't-grn' : 't-yel'}">${RECEIPT_LABELS[row.decision] || esc(row.decision)}</span></td>
      <td>${row.claim_allowed ? '可宣称' : '不可宣称'}</td>
      <td class="tiny">${esc(row.rationale)}</td>
      <td class="tiny muted">${esc(row.accepted_by_name || '—')} · ${fmtDateTime(row.accepted_at)}</td>
    </tr>`).join('');
  return `<table class="tbl mt">
      <thead><tr><th>结论</th><th>改善宣称</th><th>依据</th><th>接收人</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
}

function comparisonGateHtml(readiness, receipts) {
  const reasons = (readiness.reasons || []).length
    ? `<div class="note tiny">${readiness.reasons.map((item) => esc(item)).join('；')}</div>`
    : '';
  const writeBack = readiness.claim_allowed && canManage()
    ? `<button class="btn-sm" data-act="asset.openWriteBack"
        data-before="${readiness.before_import_id}" data-after="${readiness.after_import_id}">
        写回 KPI 基线</button>`
    : '';
  const form = canManage() ? `
    <div class="field"><label>接收结论</label>
      <select class="sel" id="logReceiptDecision">
        <option value="ACCEPT">接收</option>
        <option value="RETURN">退回</option>
        <option value="OBSERVE">观察</option>
      </select></div>
    <div class="field"><label>依据 *</label>
      <textarea id="logReceiptRationale" rows="2"
        placeholder="写清接收/退回的依据；样本不足时只能作为观察"></textarea></div>
    <div class="gap">
      <button class="btn btn-p" data-act="asset.submitLogReceipt">登记结论</button>
      ${writeBack}
    </div>`
    : '<div class="note tiny mt">接收对照结论需要流程管理科或系统管理员角色。</div>';
  return `<div class="between mt">
      <span class="tag ${readiness.claim_allowed ? 't-grn' : 't-yel'}">${readiness.claim_allowed ? '可据此宣称改善' : '不可据此宣称改善'}</span>
      <span class="tiny muted">门禁：可比 + 样本 ≥ 5 + 已接收</span>
    </div>
    ${reasons}
    ${receiptHistoryHtml(receipts)}
    <div class="mt">${form}</div>`;
}

async function loadComparisonGate(pid, before, after) {
  const target = document.getElementById('logCompareGate');
  if (!target) return;
  try {
    const [readiness, receipts] = await Promise.all([
      GET(`/processes/${pid}/log-imports/compare/claim-readiness?before_id=${before}&after_id=${after}`),
      GET(`/processes/${pid}/log-imports/compare/receipts?before_id=${before}&after_id=${after}`),
    ]);
    target.innerHTML = comparisonGateHtml(readiness, receipts);
  } catch (error) {
    target.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function submitLogReceipt() {
  const pid = ASSET().processId;
  const before = Number(document.getElementById('logCompareBefore')?.value || 0);
  const after = Number(document.getElementById('logCompareAfter')?.value || 0);
  const decision = document.getElementById('logReceiptDecision')?.value;
  const rationale = (document.getElementById('logReceiptRationale')?.value || '').trim();
  if (!before || !after || before === after) {
    toast('请先选择两次不同的日志', true);
    return;
  }
  if (!rationale) {
    toast('请填写接收/退回依据', true);
    return;
  }
  try {
    await POST(`/processes/${pid}/log-imports/compare/receipt`, {
      before_id: before,
      after_id: after,
      decision,
      rationale,
    });
    toast('对照结论已登记');
    await loadComparisonGate(pid, before, after);
  } catch (error) {
    toast(errorText(error), true);
  }
}

function writeBackHint(el) {
  const option = el?.selectedOptions?.[0];
  const hint = document.getElementById('wbObserved');
  if (!option || !hint) return;
  const unit = option.dataset.unit || '无单位';
  const baseline = option.dataset.baseline === '' ? '—' : option.dataset.baseline;
  const target = option.dataset.target === '' ? '—' : option.dataset.target;
  hint.textContent = `改善后平均周期 ${option.dataset.observed} ${unit}；` +
    `当前基线 ${baseline}，目标 ${target}`;
}

async function openWriteBack(before, after) {
  const pid = ASSET().processId;
  try {
    const options = await GET(
      `/processes/${pid}/log-imports/compare/write-back-options` +
      `?before_id=${before}&after_id=${after}`,
    );
    if (!options.claim_allowed) {
      openModal('写回 KPI 基线',
        `<div class="note tiny">对照尚未达到写回条件：${
          (options.reasons || []).map((item) => esc(item)).join('；')
        }</div>`,
        '<button class="btn btn-g" data-act="ui.close">关闭</button>');
      return;
    }
    if (!options.kpis.length) {
      openModal('写回 KPI 基线',
        `<div class="empty">本流程没有可写回的月频、流程级时长 KPI。
          日志对照只支持月频、流程级、时长单位（分钟/小时/天）的指标。</div>`,
        '<button class="btn btn-g" data-act="ui.close">关闭</button>');
      return;
    }
    const kpiOptions = options.kpis.map((row) => (
      `<option value="${row.kpi_id}"
        data-observed="${row.observed_value}"
        data-unit="${esc(row.unit || '')}"
        data-baseline="${row.baseline_value ?? ''}"
        data-target="${row.target_value ?? ''}">
        ${esc(row.code)} ${esc(row.name)}（${esc(row.unit || '无单位')}）</option>`
    )).join('');
    openModal('写回 KPI 基线', `
      <div class="note tiny">${esc(options.note)}</div>
      <div class="field"><label>KPI *</label>
        <select class="sel" id="wbKpi" data-act="asset.wbKpi">${kpiOptions}</select></div>
      <div class="tiny muted" id="wbObserved"></div>
      <div class="gap mt">
        <label class="tiny"><input type="checkbox" id="wbBaseline" checked>
          用改善后平均周期更新基线</label>
      </div>
      <div class="field"><label>目标值（留空表示不改）</label>
        <input id="wbTarget" type="number" step="any" placeholder="目标必须由人明确填写"></div>
      <div class="field"><label>写回依据 *</label>
        <textarea id="wbRationale" rows="2"
          placeholder="写明为什么用这次对照更新基线/目标"></textarea></div>`,
    `<button class="btn btn-g" data-act="ui.close">取消</button>
     <button class="btn btn-p" data-act="asset.submitWriteBack"
       data-before="${before}" data-after="${after}">写回</button>`);
    writeBackHint(document.getElementById('wbKpi'));
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function submitWriteBack(before, after) {
  const pid = ASSET().processId;
  const kpi = Number(document.getElementById('wbKpi')?.value || 0);
  const updateBaseline = !!document.getElementById('wbBaseline')?.checked;
  const rawTarget = (document.getElementById('wbTarget')?.value || '').trim();
  const target = rawTarget === '' ? null : Number(rawTarget);
  const rationale = (document.getElementById('wbRationale')?.value || '').trim();
  if (!kpi) {
    toast('请选择 KPI', true);
    return;
  }
  if (target !== null && !Number.isFinite(target)) {
    toast('目标值必须是数字', true);
    return;
  }
  if (!rationale) {
    toast('请填写写回依据', true);
    return;
  }
  try {
    const data = await POST(`/processes/${pid}/log-imports/compare/write-back`, {
      before_id: before,
      after_id: after,
      kpi_id: kpi,
      update_baseline: updateBaseline,
      target_value: target,
      rationale,
    });
    closeModal();
    toast(
      `已写回 ${data.kpi_code} v${data.kpi_version_after}：` +
      `基线 ${data.baseline_after ?? '未改'}，目标 ${data.target_after ?? '未改'}`,
    );
    await loadComparisonGate(pid, before, after);
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openLogCompare() {
  const pid = ASSET().processId;
  try {
    const imports = await GET(`/processes/${pid}/log-imports`);
    const committed = (imports || [])
      .filter((row) => row.status === 'COMMITTED')
      .sort((left, right) => left.id - right.id);
    if (committed.length < 2) {
      openModal('日志前后对照',
        '<div class="empty">至少需要两次已提交的日志导入。</div>',
        '<button class="btn btn-g" data-act="ui.close">关闭</button>');
      return;
    }
    const options = (selected) => committed.map((row, index) => (
      `<option value="${row.id}"${index === selected ? ' selected' : ''}>${esc(row.file_name)} · ${row.case_count} 单</option>`
    )).join('');
    openModal('日志前后对照', `
      <div class="note tiny">只读对照：同一流程、同一活动映射、两次已提交日志。
        样本不足或映射不同会明确标「不可比 / 证据不足」；接收结论后仍需过改善宣称门禁。</div>
      <div class="field"><label>改善前</label>
        <select class="sel" id="logCompareBefore">${options(0)}</select></div>
      <div class="field"><label>改善后</label>
        <select class="sel" id="logCompareAfter">${options(committed.length - 1)}</select></div>
      <button class="btn btn-p mt" data-act="asset.runLogCompare">比较</button>
      <div id="logCompareResult" class="mt"></div>
      <div id="logCompareGate"></div>`,
    '<button class="btn btn-g" data-act="ui.close">关闭</button>', 'sheet');
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function runLogCompare() {
  const pid = ASSET().processId;
  const before = Number(document.getElementById('logCompareBefore')?.value || 0);
  const after = Number(document.getElementById('logCompareAfter')?.value || 0);
  if (!before || !after) {
    toast('请选择两次日志', true);
    return;
  }
  if (before === after) {
    toast('请选择两次不同的日志', true);
    return;
  }
  const target = document.getElementById('logCompareResult');
  const gate = document.getElementById('logCompareGate');
  if (target) target.innerHTML = '<div class="empty">比较中…</div>';
  if (gate) gate.innerHTML = '';
  try {
    const data = await GET(
      `/processes/${pid}/log-imports/compare?before_id=${before}&after_id=${after}`,
    );
    if (target) target.innerHTML = comparisonHtml(data);
    await loadComparisonGate(pid, before, after);
  } catch (error) {
    if (target) target.innerHTML = '';
    toast(errorText(error), true);
  }
}

async function openSourceRegistration() {
  const pid = ASSET().processId;
  if (!ASSET().readiness?.versioned) {
    toast('请先发布模型版本，再登记来源', true);
    return;
  }
  const [activities, sources] = await Promise.all([activityOptions(pid), loadClaimSources(pid)]);
  if (!sources.length) {
    openModal('登记 As-Is 来源', `
      <div class="empty">没有可引用的来源。先去工具箱填写方法记录，或上传并生效一份制度版本。</div>`,
    `<button class="btn btn-g" data-act="ui.close">关闭</button>
     <button class="btn btn-p" data-act="asset.go" data-view="toolbox"
       data-process="${pid}">去工具箱</button>`);
    return;
  }
  if (!activities.length) {
    toast('该流程还没有 L4 活动', true);
    return;
  }
  const activityOptionsHtml = activities.map((item) => (
    `<option value="${item.id}">${esc(item.label)}</option>`
  )).join('');
  const sourceOptions = sources.map((item) => (
    `<option value="${esc(item.value)}">${esc(item.label)}</option>`
  )).join('');
  openModal('登记 As-Is 来源', `
    <div class="field"><label>来源方法</label>
      <select class="sel" id="sourceMethod">
        <option value="DOCUMENTED">制度文本</option>
        <option value="STATED">访谈陈述</option>
        <option value="OBSERVED">现场观测</option>
      </select></div>
    <div class="field"><label>来源 *</label>
      <select class="sel" id="sourceRef">${sourceOptions}</select></div>
    <div class="field"><label>覆盖活动（按住 Ctrl 多选）*</label>
      <select class="sel" id="sourceActivities" multiple size="8">${activityOptionsHtml}</select></div>
    <div class="gap">
      <label class="tiny"><input type="checkbox" id="sourceWait"> 覆盖等待时间</label>
      <label class="tiny"><input type="checkbox" id="sourceDuration"> 覆盖作业时间</label>
    </div>
    <div class="field"><label>样本量（观测时填写）</label>
      <input id="sourceSamples" type="number" min="0"></div>
    <div class="field"><label>说明（可选）</label>
      <textarea id="sourceNote" rows="2" placeholder="这份来源说明了什么"></textarea></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitSource">保存来源</button>`);
}

async function submitSource() {
  const pid = ASSET().processId;
  const method = document.getElementById('sourceMethod')?.value;
  const source = document.getElementById('sourceRef')?.value || '';
  const selected = Array.from(
    document.getElementById('sourceActivities')?.selectedOptions || [],
  ).map((option) => Number(option.value)).filter(Boolean);
  if (!source || !selected.length) {
    toast('请选择来源和至少一个活动', true);
    return;
  }
  const [sourceType, sourceId] = source.split(':');
  const targets = selected.map((id) => ({
    target_type: 'ACTIVITY', target_id: id, condition: 'ALL',
  }));
  const wait = !!document.getElementById('sourceWait')?.checked;
  const duration = !!document.getElementById('sourceDuration')?.checked;
  if (wait) {
    selected.forEach((id) => targets.push({
      target_type: 'TIME_FIELD', target_id: id, field: 'wait', condition: 'ALL',
    }));
  }
  if (duration) {
    selected.forEach((id) => targets.push({
      target_type: 'TIME_FIELD', target_id: id, field: 'duration', condition: 'ALL',
    }));
  }
  const note = (document.getElementById('sourceNote')?.value || '').trim();
  const samplesValue = document.getElementById('sourceSamples')?.value;
  const payload = {
    claim: note || `As-Is 来源登记 · 覆盖 ${selected.length} 个活动`,
    claim_type: wait || duration ? 'TIME' : 'EXISTENCE',
    source_type: sourceType,
    source_id: Number(sourceId),
    method,
    samples: samplesValue === '' || samplesValue === undefined ? null : Number(samplesValue),
    status: 'OPEN',
    targets,
  };
  try {
    await POST(`/processes/${pid}/evidence-claims`, payload);
    closeModal();
    toast('来源已登记');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function previewDiagnosis() {
  const pid = ASSET().processId;
  try {
    const preview = await POST(`/processes/${pid}/r1/compile`, {});
    ASSET().diagnosisPreview = preview;
    const blockers = (preview.blockers || []).map((row) => (
      `<li><b>${esc(row.message)}</b>${(row.targets || []).length
        ? `<div class="tiny muted">${esc(row.targets.join('、'))}</div>` : ''}</li>`
    )).join('') || '<li>无</li>';
    const body = `
      <div class="between">
        <span class="tag ${preview.can_compile ? 't-grn' : 't-red'}">
          ${preview.can_compile ? '可生成草稿' : '存在硬阻断'}</span>
        <span class="tiny muted">hash ${esc(preview.content_hash.slice(0, 12))}…</span>
      </div>
      <div class="note mt"><b>阻断</b><ul class="tiny">${blockers}</ul></div>
      <iframe sandbox="" title="诊断证据包预览"
        style="width:100%;height:55vh;border:1px solid var(--line);border-radius:10px;background:#fff"
        srcdoc="${esc(preview.preview_html)}"></iframe>`;
    openModal('诊断证据包预览', body,
      `<button class="btn btn-g" data-act="ui.close">取消</button>
       <button class="btn btn-p" data-act="asset.diagnosisCommit"
         ${preview.can_compile ? '' : 'disabled'}>生成草稿</button>`, 'sheet');
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function commitDiagnosis() {
  const pid = ASSET().processId;
  try {
    const created = await POST(`/processes/${pid}/r1`, {});
    ASSET().diagnosis = { ...created, process_id: pid };
    closeModal();
    toast(`已生成 ${created.document_code} v${created.version_label}`);
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function openDiagnosisHtml() {
  const pkg = ASSET().diagnosis;
  if (!pkg) return;
  if (pkg.preview_html) {
    openHtmlModal(pkg.preview_html);
    return;
  }
  try {
    const detail = await GET(`/asset-packages/${pkg.version_id}`);
    ASSET().diagnosis = { ...detail, process_id: ASSET().processId };
    openHtmlModal(detail.preview_html);
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function transitionDiagnosis() {
  const pkg = ASSET().diagnosis;
  if (!pkg) return;
  try {
    const moved = await POST(`/asset-packages/${pkg.version_id}/transition`, {
      status: 'IN_REVIEW',
    });
    ASSET().diagnosis = { ...moved, process_id: ASSET().processId };
    toast(`已提交：${moved.status_label || moved.status}`);
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function previewPackage() {
  const pid = ASSET().processId;
  if (!pid) return;
  try {
    const preview = await POST(`/processes/${pid}/asset-packages/compile`, {});
    ASSET().preview = preview;
    const blockers = (preview.blockers || []).map((row) => (
      `<li><b>${esc(row.message)}</b>${(row.targets || []).length
        ? `<div class="tiny muted">${esc(row.targets.join('、'))}</div>` : ''}</li>`
    )).join('') || '<li>无</li>';
    const body = `
      <div class="between">
        <span class="tag ${preview.can_generate ? 't-yel' : 't-red'}">
          ${preview.can_generate ? '可生成草稿' : '拒绝生成（硬阻断）'}</span>
        <span class="tiny muted">hash ${esc(preview.content_hash.slice(0, 12))}…</span>
      </div>
      <div class="note mt"><b>阻断</b><ul class="tiny">${blockers}</ul></div>
      <iframe sandbox="" title="资产包预览"
        style="width:100%;height:55vh;border:1px solid var(--line);border-radius:10px;background:#fff"
        srcdoc="${esc(preview.preview_html)}"></iframe>`;
    openModal('资产包预览', body,
      `<button class="btn btn-g" data-act="ui.close">取消</button>
       <button class="btn btn-p" data-act="asset.commit"
         ${preview.can_generate ? '' : 'disabled'}>生成草稿</button>`, 'sheet');
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function commitPackage() {
  const pid = ASSET().processId;
  try {
    const created = await POST(`/processes/${pid}/asset-packages`, {});
    ASSET().package = { ...created, process_id: pid };
    closeModal();
    toast(`已生成 ${created.document_code} v${created.version_label}`);
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

function openHtmlModal(html) {
  if (!html) {
    toast('资产包文件不存在或已被清理', true);
    return;
  }
  openModal('资产包 HTML',
    `<iframe sandbox="" title="资产包 HTML"
      style="width:100%;height:65vh;border:1px solid var(--line);border-radius:10px;background:#fff"
      srcdoc="${esc(html)}"></iframe>`,
    '<button class="btn btn-g" data-act="ui.close">关闭</button>', 'sheet');
}

async function openPackageHtml() {
  const pkg = ASSET().package;
  if (!pkg) return;
  if (pkg.preview_html) {
    openHtmlModal(pkg.preview_html);
    return;
  }
  try {
    const detail = await GET(`/asset-packages/${pkg.version_id}`);
    ASSET().package = { ...detail, process_id: ASSET().processId };
    openHtmlModal(detail.preview_html);
  } catch (error) {
    toast(errorText(error), true);
  }
}

function openAdjudicate(claimId) {
  openModal('裁决证据冲突', `
    <div class="field"><label>裁决结论</label>
      <select class="sel" id="adjDecision">
        <option value="ACCEPT_DOCUMENT">以制度为准</option>
        <option value="ACCEPT_OBSERVED">以观测为准</option>
        <option value="ACCEPT_STATED">以访谈为准</option>
        <option value="KEEP_CONFLICT">保留冲突</option>
        <option value="OTHER">其他</option>
      </select></div>
    <div class="field"><label>依据 *</label>
      <textarea id="adjRationale" rows="3" placeholder="写明为什么这样裁决"></textarea></div>
    <div class="field"><label>授权 / 依据引用（可选）</label>
      <input id="adjAuthority" placeholder="制度编号、会议纪要或授权人"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="asset.submitAdjudication"
     data-claim="${claimId}">提交裁决</button>`);
}

async function submitAdjudication(claimId) {
  const pid = ASSET().processId;
  const decision = document.getElementById('adjDecision')?.value;
  const rationale = (document.getElementById('adjRationale')?.value || '').trim();
  const authority = (document.getElementById('adjAuthority')?.value || '').trim() || null;
  if (!rationale) {
    toast('请填写裁决依据', true);
    return;
  }
  try {
    await POST(`/processes/${pid}/evidence-claims/${claimId}/adjudicate`, {
      decision,
      rationale,
      authority_ref: authority,
    });
    closeModal();
    toast('裁决已记录');
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

async function transitionPackage(status) {
  const pkg = ASSET().package;
  if (!pkg || !status) return;
  try {
    const moved = await POST(`/asset-packages/${pkg.version_id}/transition`, { status });
    ASSET().package = { ...moved, process_id: ASSET().processId };
    toast(`已提交：${moved.status_label || moved.status}`);
    renderAsset();
  } catch (error) {
    toast(errorText(error), true);
  }
}

on('asset.process', (_data, el) => {
  const value = el.value;
  if (!value) return;
  ASSET().processId = Number(value);
  ASSET().package = null;
  go('asset', { params: { process: value }, push: true });
});
on('asset.generate', () => previewPackage());
on('asset.commit', () => commitPackage());
on('asset.openHtml', () => openPackageHtml());
on('asset.download', () => {
  const pkg = ASSET().package;
  if (!pkg || !pkg.download_url) {
    toast('没有可下载的资产包文件', true);
    return;
  }
  download(pkg.download_url, `${pkg.document_code}-${pkg.version_label}.html`)
    .catch((error) => toast(errorText(error), true));
});
on('asset.pick', () => {
  ASSET().processId = null;
  ASSET().package = null;
  go('asset', { params: {}, push: true });
});
on('asset.impactType', async (_data, el) => {
  const pid = ASSET().processId;
  try {
    const items = await loadImpactRefs(el.value);
    if (ASSET().processId !== pid) return;
    const ref = document.getElementById('assetImpactRef');
    if (!ref) return;
    ref.innerHTML = optionsHtml(items);
    if (items.length) ref.value = String(items[0].id);
  } catch (error) {
    toast(errorText(error), true);
  }
});
on('asset.impactQuery', () => queryImpact());
on('asset.impactOpen', ({ version }) => openImpactPackage(Number(version)));
on('asset.deleteLink', ({ id }) => revokeRelation('link', Number(id)));
on('asset.deleteRelation', ({ id }) => revokeRelation('relation', Number(id)));
on('asset.deleteHandoff', ({ id }) => revokeRelation('handoff', Number(id)));
on('asset.deleteUnmodeled', ({ id }) => revokeRelation('unmodeled', Number(id)));
on('asset.newLink', () => openNewLink());
on('asset.submitLink', () => submitLink());
on('asset.newRelation', () => openNewRelation());
on('asset.submitRelation', () => submitRelation());
on('asset.newHandoff', () => openNewHandoff());
on('asset.submitHandoff', () => submitHandoff());
on('asset.newUnmodeled', () => openNewUnmodeled());
on('asset.submitUnmodeled', () => submitUnmodeled());
on('asset.newClaim', () => openNewClaim());
on('asset.submitClaim', () => submitClaim());
on('asset.logCompare', () => openLogCompare());
on('asset.runLogCompare', () => runLogCompare());
on('asset.submitLogReceipt', () => submitLogReceipt());
on('asset.openWriteBack', ({ before, after }) => openWriteBack(Number(before), Number(after)));
on('asset.wbKpi', (_, el) => writeBackHint(el));
on('asset.submitWriteBack', ({ before, after }) => submitWriteBack(Number(before), Number(after)));
on('asset.logImport', () => openLogImport());
on('asset.uploadLog', () => uploadLogImport());
on('asset.mapLog', () => mapLogImport());
on('asset.commitLog', () => commitLogImport());
on('asset.closeLogImport', () => {
  closeModal();
  renderAsset();
});
on('asset.docExtract', () => openDocumentExtract());
on('asset.extractCandidates', () => extractCandidates());
on('asset.confirmCandidate', ({ id }) => confirmCandidate(Number(id)));
on('asset.rejectCandidate', ({ id }) => rejectCandidate(Number(id)));
on('asset.closeDocExtract', () => {
  closeModal();
  renderAsset();
});
on('asset.newSource', () => openSourceRegistration());
on('asset.submitSource', () => submitSource());
on('asset.diagnosisPreview', () => previewDiagnosis());
on('asset.diagnosisCommit', () => commitDiagnosis());
on('asset.diagnosisOpen', () => openDiagnosisHtml());
on('asset.diagnosisTransition', () => transitionDiagnosis());
on('asset.diagnosisDownload', () => {
  const pkg = ASSET().diagnosis;
  if (!pkg || !pkg.download_url) {
    toast('没有可下载的诊断证据包', true);
    return;
  }
  download(pkg.download_url, `${pkg.document_code}-${pkg.version_label}.html`)
    .catch((error) => toast(errorText(error), true));
});
on('asset.diagnosisPdf', () => {
  const pkg = ASSET().diagnosis;
  if (!pkg || !pkg.pdf_url) {
    toast('当前环境没有 PDF 转换器', true);
    return;
  }
  download(pkg.pdf_url, `${pkg.document_code}-${pkg.version_label}.pdf`)
    .catch((error) => toast(errorText(error), true));
});
on('asset.printPack', ({ format }) => {
  const pkg = ASSET().package;
  if (!pkg) {
    toast('先生成资产包', true);
    return;
  }
  const pid = ASSET().processId;
  download(
    `/api/v1/processes/${pid}/asset-packages/print-pack?format=${format}`,
    `${pkg.document_code}-print-pack.${format}`,
  ).catch((error) => toast(errorText(error), true));
});
on('asset.downloadPdf', () => {
  const pkg = ASSET().package;
  if (!pkg || !pkg.pdf_url) {
    toast('当前环境没有 PDF 转换器', true);
    return;
  }
  download(pkg.pdf_url, `${pkg.document_code}-${pkg.version_label}.pdf`)
    .catch((error) => toast(errorText(error), true));
});
on('asset.adjudicate', ({ claim }) => openAdjudicate(Number(claim)));
on('asset.submitAdjudication', ({ claim }) => submitAdjudication(Number(claim)));
on('asset.tab', ({ tab }) => {
  if (!tab || !ASSET().data) return;
  ASSET().tab = tab;
  paintAsset(ASSET().processId, ASSET().data);
});
on('asset.transition', ({ status }) => transitionPackage(status));
on('asset.go', ({ view, tab, process: pid }) => {
  const params = { process: pid || ASSET().processId };
  if (tab) params.tab = tab;
  go(view, { params, push: true });
});
