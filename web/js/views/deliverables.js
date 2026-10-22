/* 视图：交付物与模板库
 *
 * 三个页签：
 *   1) 项目交付物：按标准步骤登记版本、上传文件、审批流转、下载；
 *   2) 流程标准文件：挂在 L1–L4 节点上的 SOP/表单，作为唯一标准源；
 *   3) 工具模板库：按工具浏览预制模板、上传版本、审批、复制到项目。
 *
 * 枚举中文标签全部来自后端（status_label / type_label / format_label / mode_label），
 * 这里只维护颜色映射。
 */
import {
  esc, num, dtShort, dateShort, skeleton, emptyRow, DLV_TONE,
} from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync } from '../core/router.js';
import { canManage, canWrite } from '../core/auth.js';
import { GET, PATCH, POST, POST_FORM, download } from '../core/api.js';

const FMT_ICON = {
  XLSX: '📊', DOCX: '📄', PPTX: '📽', PDF: '📕', BPMN: '⌗', CSV: '📑', ONLINE: '✍',
};

const statusTag = (status, label) =>
  '<span class="tag ' + (DLV_TONE[status] || 't-gry') + '">' + esc(label || status) + '</span>';

/* ============================================================ 壳与页签 */

const renderDeliverables = () => renderAsync('deliverables',
  () => Promise.all([
    GET('/projects?page_size=200'),
    GET('/deliverables/meta'),
    GET('/tool-templates/meta'),
    GET('/tools'),
    GET('/workflow/deliverable-definitions'),
    GET('/process-documents/meta'),
    GET('/process-map/flat'),
    GET('/org-units'),
    GET('/baselines/meta'),
    GET('/baselines'),
  ]),
  ([page, dmeta, tmeta, tools, definitions, docmeta, processes, orgs, blmeta, baselines]) => {
    state.dlvProjects = page.items || [];
    state.dlvMeta = dmeta;
    state.tplMeta = tmeta;
    state.tplTools = tools || [];
    state.tplDefinitions = definitions || [];
    state.docMeta = docmeta;
    state.processes = processes || [];
    state.orgUnits = orgs || [];
    state.baselineMeta = blmeta;
    state.baselines = baselines || [];
    paintShell();
  });

function paintShell() {
  const tab = state.deliverables.tab;
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div><h2>交付物与模板库<span class="module-badge">可追溯 · 版本化</span></h2>
          <div class="desc">流程标准文件是唯一源；项目交付物保存实例与来源版本；模板库按工具维护预制模板</div></div>
        <a class="link-btn" onclick="go('workflow')">查看 24 步标准工作流 →</a>
      </div>
      <div class="tabs" style="margin-bottom:0">
        <button class="${tab === 'project' ? 'on' : ''}" onclick="setDlvTab('project')">项目交付物</button>
        <button class="${tab === 'document' ? 'on' : ''}" onclick="setDlvTab('document')">流程标准文件</button>
        <button class="${tab === 'template' ? 'on' : ''}" onclick="setDlvTab('template')">工具模板库</button>
        <button class="${tab === 'baseline' ? 'on' : ''}" onclick="setDlvTab('baseline')">基线与审计</button>
      </div>
    </div>
    <div id="dlvBody">${skeleton(4)}</div>`;
  if (tab === 'project') paintProjectTab();
  else if (tab === 'document') paintDocumentTab();
  else if (tab === 'template') paintTemplateTab();
  else paintBaselineTab();
}

function setDlvTab(tab) {
  state.deliverables.tab = tab;
  paintShell();
}

/* ============================================================ 项目交付物 */

function paintProjectTab() {
  const body = document.getElementById('dlvBody');
  const projects = state.dlvProjects || [];
  if (!projects.length) {
    body.innerHTML = '<div class="card"><div class="empty">还没有项目，先去「流程项目组合」立项。</div></div>';
    return;
  }
  const current = Number(state.deliverables.projectId) || projects[0].id;
  state.deliverables.projectId = current;
  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <div><h2>项目交付物</h2>
          <div class="desc" style="margin:0">每个标准步骤要产出什么、谁负责、当前是哪一版，都在这里</div></div>
        <select class="sel" onchange="setDlvProject(this.value)">
          ${projects.map((p) => `<option value="${p.id}" ${p.id === current ? 'selected' : ''}>
            ${esc(p.code)} · ${esc(p.name)}</option>`).join('')}
        </select>
      </div>
      <div id="dlvSummary">${skeleton(1)}</div>
    </div>
    <div class="card" id="dlvList">${skeleton(4)}</div>`;
  loadProjectDeliverables(current);
}

function setDlvProject(value) {
  state.deliverables.projectId = Number(value);
  paintProjectTab();
}

async function loadProjectDeliverables(projectId) {
  const summaryBox = document.getElementById('dlvSummary');
  const listBox = document.getElementById('dlvList');
  if (!summaryBox || !listBox) return;
  try {
    const [summary, items] = await Promise.all([
      GET('/projects/' + projectId + '/deliverables/summary'),
      GET('/projects/' + projectId + '/deliverables'),
    ]);
    if (Number(state.deliverables.projectId) !== Number(projectId)) return;

    summaryBox.innerHTML = `
      <div class="grid g4 stat-row">
        <div class="kpi stat"><div class="num">${summary.total}</div><div class="lab">交付物总数</div></div>
        <div class="kpi stat"><div class="num">${summary.effective}</div><div class="lab">已生效</div></div>
        <div class="kpi stat ${summary.required_missing ? 'is-risk' : ''}">
          <div class="num">${summary.required_missing}</div><div class="lab">必需项未产出</div></div>
        <div class="kpi stat"><div class="num">${num(summary.completeness_pct)}<small>%</small></div>
          <div class="lab">已生效占比 · 评审中 ${summary.in_review} / 草稿 ${summary.draft}</div></div>
      </div>`;

    const rows = items.map((i) => {
      const cv = i.current_version;
      const version = cv
        ? `<b>${esc(cv.version_label)}</b> ${statusTag(cv.status, cv.status_label)}
           <div class="tiny">${esc(cv.file_name || cv.file_ref || '')}</div>`
        : '<span class="tiny">未登记</span>';
      const actions = [
        canWrite() ? `<button class="btn-sm" onclick="openDeliverableUpload(${i.id})">上传</button>` : '',
        `<button class="btn-sm" onclick="openDeliverable(${i.id})">详情</button>`,
        cv && cv.has_file
          ? `<button class="btn-sm" onclick="dlDeliverableVersion(${i.id}, ${cv.id}, '${esc(cv.version_label)}')">下载</button>`
          : '',
      ].filter(Boolean).join(' ');
      return `<tr>
        <td><b>${esc(i.step_no)}</b><div class="tiny">${esc(i.step_name)}</div></td>
        <td>${esc(i.definition_name)}
          <div class="tiny">${esc(i.definition_code)} · ${i.required ? '必需' : '可选'}</div></td>
        <td><span class="tag t-gry">${esc(i.type_label || i.type)}</span></td>
        <td>${statusTag(i.status, i.status_label)}</td>
        <td>${version}</td>
        <td>${esc(i.owner || '—')}</td>
        <td>${actions}</td>
      </tr>`;
    }).join('') || emptyRow(7, '该项目还没有交付物实例');

    listBox.innerHTML = `
      <table class="tbl">
        <thead><tr><th>步骤</th><th>交付物</th><th>类型</th><th>状态</th>
          <th>当前版本</th><th>负责人</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    summaryBox.innerHTML = '';
    listBox.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

function openDeliverableUpload(instanceId) {
  openModal('上传交付物版本', `
    <div class="field"><label>文件</label><input type="file" id="dvFile"></div>
    <div class="field"><label>标题</label><input id="dvTitle" placeholder="可留空，默认用交付物名称"></div>
    <div class="field"><label>版本说明</label><textarea id="dvNote" placeholder="这次改了什么"></textarea></div>
    <div class="note">上传后自动生成 R# 版本并计算 SHA-256；审批通过后才会成为生效版。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitDeliverableUpload(${instanceId})">上传</button>`);
}

async function submitDeliverableUpload(instanceId) {
  const input = document.getElementById('dvFile');
  if (!input || !input.files.length) return toast('请选择文件', true);
  const fd = new FormData();
  fd.append('file', input.files[0]);
  const title = document.getElementById('dvTitle').value.trim();
  const note = document.getElementById('dvNote').value.trim();
  if (title) fd.append('title', title);
  if (note) fd.append('note', note);
  try {
    const version = await POST_FORM('/deliverables/' + instanceId + '/versions/upload', fd);
    toast('已上传 ' + version.version_label);
    closeModal();
    loadProjectDeliverables(state.deliverables.projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function openDeliverable(instanceId) {
  const gen = openModal('加载中…', skeleton(4), '', true);
  try {
    const d = await GET('/deliverables/' + instanceId);
    if (!modalAlive(gen)) return;
    paintDeliverable(d);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

function paintDeliverable(d) {
  state.dlvCurrent = d;
  const transitions = state.dlvMeta.transitions || {};
  const labels = state.dlvMeta.status_labels || {};
  const rows = d.versions.map((v) => {
    const actions = [];
    if (v.has_file) {
      actions.push(`<button class="btn-sm" onclick="dlDeliverableVersion(${d.id}, ${v.id}, '${esc(v.version_label)}')">下载</button>`);
    }
    if (canWrite()) {
      (transitions[v.status] || []).forEach((target) => {
        actions.push(`<button class="btn-sm" onclick="transitionDeliverable(${d.id}, ${v.id}, '${target}')">
          ${esc(labels[target] || target)}</button>`);
      });
      if (['APPROVED', 'EFFECTIVE', 'SUPERSEDED'].includes(v.status)
          && !(v.status === 'EFFECTIVE' && v.id === d.current_version_id)) {
        actions.push(`<button class="btn-sm" onclick="restoreDeliverable(${d.id}, ${v.id})">恢复为现行版</button>`);
      }
    }
    if (canManage() && v.has_file && ['APPROVED', 'EFFECTIVE'].includes(v.status)) {
      actions.push(`<button class="btn-sm" onclick="closeModal();openPromote(${v.id})">晋升为标准</button>`);
    }
    return `<tr>
      <td><b>${esc(v.version_label)}</b> ${v.id === d.current_version_id ? '<span class="tag t-blu">当前</span>' : ''}</td>
      <td>${statusTag(v.status, v.status_label)}</td>
      <td>${esc(v.file_name || v.file_ref || '—')}
        <div class="tiny">${v.checksum ? 'sha256 ' + esc(v.checksum.slice(0, 12)) + '…' : '仅登记元数据'}</div>
        ${v.source_document_label
          ? '<div class="tiny">来源标准 ' + esc(v.source_document_label) + '</div>' : ''}</td>
      <td>${esc(v.author || '—')}<div class="tiny">${dtShort(v.created_at)}</div></td>
      <td>${esc(v.approver || '—')}<div class="tiny">${v.valid_from ? dateShort(v.valid_from) : '—'}</div></td>
      <td>${actions.join(' ') || '—'}</td>
    </tr>`;
  }).join('') || emptyRow(6, '还没有版本');

  openModal(d.definition_name, `
    <div class="note mb"><b>${esc(d.step_no)} ${esc(d.step_name)}</b> ·
      ${esc(d.definition_code)} · ${esc(d.type_label || d.type)} · ${d.required ? '必需' : '可选'}
      ${d.acceptance_criteria ? '<div class="mt">验收口径：' + esc(d.acceptance_criteria) + '</div>' : ''}</div>
    <div class="between mb">
      <div>当前状态：${statusTag(d.status, d.status_label)}</div>
      ${canWrite() ? `<button class="btn-sm" onclick="closeModal();openDeliverableUpload(${d.id})">上传新版本</button>` : ''}
    </div>
    <table class="tbl">
      <thead><tr><th>版本</th><th>状态</th><th>文件</th><th>编制</th><th>批准/生效</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`,
  '<button class="btn btn-g" onclick="closeModal()">关闭</button>', true);
}

async function transitionDeliverable(instanceId, versionId, target) {
  try {
    await POST('/deliverables/' + instanceId + '/versions/' + versionId + '/transition',
      { status: target });
    toast('状态已更新');
    await openDeliverable(instanceId);
    loadProjectDeliverables(state.deliverables.projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function restoreDeliverable(instanceId, versionId) {
  try {
    await POST('/deliverables/' + instanceId + '/versions/' + versionId + '/restore');
    toast('已恢复为现行版');
    await openDeliverable(instanceId);
    loadProjectDeliverables(state.deliverables.projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function dlDeliverableVersion(instanceId, versionId, label) {
  try {
    await download('/deliverables/' + instanceId + '/versions/' + versionId + '/download',
      '交付物' + (label || ''));
    toast('已开始下载');
  } catch (e) {
    toast(e.message, true);
  }
}

/* ============================================================ 流程标准文件 */

const DOC_ICON = {
  SOP: '📘', FORM: '📝', CHECKLIST: '✅', TEMPLATE: '🧩', POLICY: '📜', OTHER: '📄',
};

const IMPACT_TONE = {
  UP_TO_DATE: 't-grn', BEHIND_MINOR: 't-yel', BEHIND_MAJOR: 't-red',
  NO_BASE: 't-red', NO_EFFECTIVE: 't-gry',
};

const orgOptions = (selected) => (state.orgUnits || []).map((o) =>
  `<option value="${o.id}" ${String(selected) === String(o.id) ? 'selected' : ''}>
    ${esc(o.name)}（${esc(o.type_label)}）</option>`).join('');

const policyOptions = (selected) =>
  Object.entries((state.docMeta && state.docMeta.variation_policy_labels) || {})
    .map(([code, label]) => `<option value="${code}"
      ${selected === code ? 'selected' : ''}>${esc(label)}</option>`).join('');

function paintDocumentTab() {
  const body = document.getElementById('dlvBody');
  const d = state.deliverables;
  const processes = state.processes || [];
  const cats = (state.docMeta && state.docMeta.category_labels) || {};
  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <div><h2>流程标准文件</h2>
          <div class="desc" style="margin:0">挂在 L1–L4 节点上的 SOP / 表单，是项目复制时的唯一来源；集团通用对全部组织可见</div></div>
        ${canManage() ? '<button class="btn btn-p" onclick="openNewDocument()">+ 新建标准文件</button>' : ''}
      </div>
      <div class="gap" style="flex-wrap:wrap">
        <select class="sel" onchange="setDocProcess(this.value)">
          <option value="">全部流程</option>
          ${processes.map((p) => `<option value="${p.id}"
            ${String(d.documentProcessId) === String(p.id) ? 'selected' : ''}>
            ${esc(p.code)} · ${esc(p.name)}（L${p.level}）</option>`).join('')}
        </select>
        <select class="sel" onchange="setDocCategory(this.value)">
          <option value="">全部类型</option>
          ${Object.entries(cats).map(([code, label]) => `<option value="${code}"
            ${d.documentCategory === code ? 'selected' : ''}>${esc(label)}</option>`).join('')}
        </select>
        <select class="sel" onchange="setDocOrg(this.value)">
          <option value="">全部组织</option>${orgOptions(d.documentOrgUnitId)}
        </select>
      </div>
      <div class="tiny mt">选择组织后，同时显示集团通用与本级、上级继承的标准文件，并解析当前有效版本。</div>
    </div>
    <div id="docEffective"></div>
    <div id="docGrid">${skeleton(3)}</div>`;
  loadDocuments();
}

function setDocProcess(value) {
  state.deliverables.documentProcessId = value ? Number(value) : null;
  loadDocuments();
}

function setDocCategory(value) {
  state.deliverables.documentCategory = value;
  loadDocuments();
}

function setDocOrg(value) {
  state.deliverables.documentOrgUnitId = value ? Number(value) : null;
  loadDocuments();
}

async function loadDocuments() {
  const grid = document.getElementById('docGrid');
  if (!grid) return;
  const d = state.deliverables;
  if (!d.documentOrgUnitId) {
    const box = document.getElementById('docEffective');
    if (box) box.innerHTML = '';
  } else {
    loadEffectiveDocuments();
  }
  const qs = [];
  if (d.documentProcessId) qs.push('process_id=' + d.documentProcessId);
  if (d.documentCategory) qs.push('category=' + encodeURIComponent(d.documentCategory));
  if (d.documentOrgUnitId) qs.push('org_unit_id=' + d.documentOrgUnitId);
  try {
    const rows = await GET('/process-documents' + (qs.length ? '?' + qs.join('&') : ''));
    if (!rows.length) {
      grid.innerHTML = `<div class="card"><div class="empty">
        还没有标准文件。流程管理科可以从某个 L2–L4 流程开始建立 SOP / 表单，
        项目里复制后会自动记录来源版本。</div></div>`;
      return;
    }
    grid.innerHTML = '<div class="grid g3">' + rows.map((doc) => `
      <div class="tool" onclick="openDocument(${doc.id})">
        <div class="ico">${DOC_ICON[doc.category] || '📄'}</div>
        <h4>${esc(doc.title)}</h4>
        <p>${esc(doc.process_code || '')} ${esc(doc.process_name || '')}
          · ${esc(doc.category_label || doc.category)} · ${esc(doc.scope_label || '集团通用')}
          · ${esc(doc.variation_policy_label || doc.variation_policy)}
          · ${doc.version_count} 个版本</p>
        <div class="between" style="margin-top:8px">
          <span class="tag ${doc.effective_version ? 't-grn' : 't-gry'}">
            ${doc.effective_version
              ? '现行 ' + esc(doc.effective_version.version_display) : '无生效版本'}</span>
          <span class="tiny">${doc.variant_of_code
            ? '变体 ← ' + esc(doc.variant_of_code) : esc(doc.code)}</span>
        </div>
      </div>`).join('') + '</div>';
  } catch (e) {
    grid.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function loadEffectiveDocuments() {
  const box = document.getElementById('docEffective');
  const d = state.deliverables;
  if (!box) return;
  if (!d.documentOrgUnitId) {
    box.innerHTML = '';
    return;
  }
  const orgId = d.documentOrgUnitId;
  const qs = ['org_unit_id=' + orgId];
  if (d.documentProcessId) qs.push('process_id=' + d.documentProcessId);
  if (d.documentCategory) qs.push('category=' + encodeURIComponent(d.documentCategory));
  box.innerHTML = '<div class="card"><div class="tiny">解析有效版本…</div></div>';
  try {
    const rows = await GET('/process-documents/effective?' + qs.join('&'));
    if (!box.isConnected || Number(state.deliverables.documentOrgUnitId) !== Number(orgId)) return;
    if (!rows.length) {
      box.innerHTML = '<div class="card"><div class="empty">该组织在所选范围内没有可用标准文件</div></div>';
      return;
    }
    box.innerHTML = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">有效版本解析</h3>
            <div class="desc" style="margin:0">按「组织 + 流程 + 日期」解析；同族取最具体的生效变体，否则向上继承</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>文件</th><th>有效版本</th><th>来源</th><th>解析说明</th></tr></thead>
          <tbody>${rows.map((row) => `<tr>
            <td><b>${esc(row.title)}</b><div class="tiny">${esc(row.code)}</div></td>
            <td>${esc(row.version.version_display)}
              ${row.is_variant ? '<span class="tag t-blu">变体</span>' : ''}</td>
            <td>${esc(row.source_org_name || '集团通用')}</td>
            <td class="muted">${esc(row.explanation)}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  } catch (e) {
    if (box.isConnected) {
      box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
    }
  }
}

async function openDocument(documentId) {
  const gen = openModal('加载中…', skeleton(5), '', true);
  try {
    const doc = await GET('/process-documents/' + documentId);
    if (!modalAlive(gen)) return;
    paintDocument(doc);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

function paintDocument(doc) {
  const transitions = (state.docMeta && state.docMeta.transitions) || {};
  const labels = (state.docMeta && state.docMeta.status_labels) || {};
  const rows = doc.versions.map((v) => {
    const actions = [];
    if (v.has_file) {
      actions.push(`<button class="btn-sm" onclick="dlDocumentVersion(${doc.id}, ${v.id}, '${esc(v.version_display)}')">下载</button>`);
    }
    if (canManage()) {
      (transitions[v.status] || []).forEach((target) => {
        actions.push(`<button class="btn-sm" onclick="transitionDocument(${doc.id}, ${v.id}, '${target}')">
          ${esc(labels[target] || target)}</button>`);
      });
    }
    return `<tr>
      <td><b>${esc(v.version_display)}</b>
        ${v.id === doc.current_version_id ? '<span class="tag t-blu">当前</span>' : ''}</td>
      <td>${statusTag(v.status, v.status_label)}</td>
      <td>${esc(v.file_name || '—')}
        <div class="tiny">${v.checksum ? 'sha256 ' + esc(v.checksum.slice(0, 12)) + '…' : ''}</div></td>
      <td>${v.source_label
        ? esc(v.source_label)
        : v.source_base_version_display
          ? '<span class="tag t-blu">变基</span> ' + esc(v.source_base_version_display)
          : '—'}</td>
      <td>${esc(v.approved_by || '—')}<div class="tiny">${v.valid_from ? dateShort(v.valid_from) : '—'}</div></td>
      <td>${actions.join(' ') || '—'}</td>
    </tr>`;
  }).join('') || emptyRow(6, '还没有版本');

  const footer = [
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>',
    `<button class="btn btn-g" onclick="closeModal();openDocumentImpact(${doc.id})">变体 / 升级影响</button>`,
    canManage()
      ? `<button class="btn btn-g" onclick="closeModal();openDocumentUpload(${doc.id})">上传新版本</button>` : '',
    canWrite() && doc.effective_version && doc.effective_version.has_file
      ? `<button class="btn btn-p" onclick="closeModal();openDocumentCopy(${doc.id})">复制到项目</button>` : '',
  ].filter(Boolean).join('');

  openModal(doc.process_code + ' · ' + doc.title, `
    <div class="note mb">
      <b>${esc(doc.code)}</b> · ${esc(doc.category_label || doc.category)}
      · ${doc.version_count} 个版本
      <div class="mt">${esc(doc.description || '（无说明）')}</div>
      <div class="mt">负责人：${esc(doc.owner || '未指定')}
        · 范围：${esc(doc.scope_label || '集团通用')}
        · 策略：${esc(doc.variation_policy_label || doc.variation_policy)}
        · 现行版本：${doc.effective_version
          ? esc(doc.effective_version.version_display) + ' ' +
            statusTag(doc.effective_version.status, doc.effective_version.status_label)
          : '<span class="tag t-gry">暂无</span>'}</div>
      ${doc.variant_of_code
        ? `<div class="mt">变体依据：${esc(doc.variant_of_code)} ${esc(doc.variant_base_version_display || '')}</div>`
        : ''}
    </div>
    <table class="tbl">
      <thead><tr><th>版本</th><th>状态</th><th>文件</th><th>来源</th><th>批准/生效</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="note mt">项目里的交付物只能记录来源版本；要把项目成果变成标准，走「晋升」生成草稿后仍需审批。</div>`,
  footer, true);
}

/* -------------------------------------------------- 升级影响与变基 */

async function openDocumentImpact(documentId) {
  const gen = openModal('加载中…', skeleton(4), '', true);
  try {
    const impact = await GET('/process-documents/' + documentId + '/upgrade-impact');
    if (!modalAlive(gen)) return;
    paintDocumentImpact(documentId, impact);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    }
  }
}

function paintDocumentImpact(documentId, impact) {
  const variants = impact.variants.map((v) => `
    <tr>
      <td><b>${esc(v.title)}</b><div class="tiny">${esc(v.code)}</div></td>
      <td>${esc(v.scope_label || '—')}<div class="tiny">${esc(v.variation_policy_label || '')}</div></td>
      <td>${v.current_version ? esc(v.current_version.version_display) : '—'}</td>
      <td>${esc(v.base_old_version_display || '—')} → ${esc(v.base_new_version_display || '—')}</td>
      <td><span class="tag ${IMPACT_TONE[v.status] || 't-gry'}">${esc(v.status_label)}</span></td>
      <td>${canManage() && v.requires_reapproval
        ? `<button class="btn-sm" onclick="closeModal();openRebase(${v.document_id}, ${impact.base_effective_version.id}, '${esc(impact.base_effective_version.version_display)}', ${documentId}, ${v.status === 'BEHIND_MAJOR' || v.status === 'NO_BASE'})">变基</button>`
        : '—'}</td>
    </tr>`).join('') || emptyRow(6, '还没有本地变体');

  const refs = impact.project_references.map((r) => `
    <tr>
      <td>${esc(r.project_code || '—')}</td>
      <td>${esc(r.definition_code || '—')}</td>
      <td>${esc(r.version_label)} ${statusTag(r.status, r.status_label)}</td>
      <td>${esc(r.source_version_display || '—')}</td>
      <td><span class="tag t-yel">仍固定旧版</span></td>
    </tr>`).join('') || emptyRow(5, '没有仍固定旧版的项目交付物');

  openModal('变体与升级影响 · ' + impact.title, `
    <div class="note mb">上级现行版本 <b>${esc(impact.base_effective_version.version_display)}</b>。
      变基只生成草稿，审批生效后才推进变体的依据版本；项目已复制的交付物保持原版本。</div>
    <h3>本地变体（${impact.variants.length}）</h3>
    <table class="tbl">
      <thead><tr><th>变体</th><th>范围</th><th>现行</th><th>依据版本</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${variants}</tbody>
    </table>
    <h3 class="mt">项目交付物仍固定旧版（${impact.project_references.length}）</h3>
    <table class="tbl">
      <thead><tr><th>项目</th><th>交付物</th><th>版本</th><th>来源标准版本</th><th>说明</th></tr></thead>
      <tbody>${refs}</tbody>
    </table>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>', true);
}

function openRebase(variantId, baseVersionId, baseLabel, baseDocId, major) {
  openModal('变基到上级 ' + baseLabel, `
    <div class="note mb">将为该变体生成新的草稿版本，内容复制当前生效版；审批生效后才更新依据版本。</div>
    ${major ? '<label class="gap" style="margin-bottom:12px">'
      + '<input type="checkbox" id="rbAck"> 我确认这是 major 升级，需要重新评估内容</label>' : ''}
    <div class="field"><label>变基说明</label><textarea id="rbNote"></textarea></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitRebase(${variantId}, ${baseVersionId}, ${baseDocId}, ${major})">生成草稿</button>`);
}

async function submitRebase(variantId, baseVersionId, baseDocId, major) {
  const ack = document.getElementById('rbAck');
  if (major && (!ack || !ack.checked)) return toast('major 升级需要显式确认', true);
  const note = document.getElementById('rbNote').value.trim() || null;
  try {
    const version = await POST('/process-documents/' + variantId + '/rebase', {
      base_version_id: baseVersionId,
      acknowledge_major: !!major,
      note,
    });
    toast('已生成变基草稿 ' + version.version_display + '，待审批');
    closeModal();
    openDocumentImpact(baseDocId);
  } catch (e) {
    toast(e.message, true);
  }
}

function openNewDocument() {
  const processes = state.processes || [];  const cats = (state.docMeta && state.docMeta.category_labels) || {};
  openModal('新建流程标准文件', `
    <div class="field"><label>所属流程</label><select class="sel" id="ndProcess"
      onchange="refreshVariantCandidates()">
      ${processes.map((p) => `<option value="${p.id}"
        ${String(state.deliverables.documentProcessId) === String(p.id) ? 'selected' : ''}>
        ${esc(p.code)} · ${esc(p.name)}（L${p.level}）</option>`).join('')}
    </select></div>
    <div class="field"><label>标题</label><input id="ndTitle" placeholder="如：采购申请单模板"></div>
    <div class="field"><label>适用范围</label><select class="sel" id="ndOrg"
      onchange="refreshVariantCandidates()">
      <option value="">集团通用（所有组织可见）</option>${orgOptions(state.deliverables.documentOrgUnitId)}
    </select></div>
    <div class="row2">
      <div class="field"><label>类型</label><select class="sel" id="ndCategory">
        ${Object.entries(cats).map(([code, label]) => `<option value="${code}">${esc(label)}</option>`).join('')}
      </select></div>
      <div class="field"><label>变体策略</label><select class="sel" id="ndPolicy">
        ${policyOptions('PARAMETERIZED')}
      </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>依据上级标准（可选）</label><select class="sel" id="ndVariant">
        <option value="">不基于上级（本级标准）</option>
      </select></div>
      <div class="field"><label>负责人（可选）</label><input id="ndOwner" placeholder="流程 Owner / 岗位"></div>
    </div>
    <div class="field"><label>说明</label><textarea id="ndDesc" placeholder="适用范围、填写要求"></textarea></div>
    <div class="note">选择「依据上级标准」会建立本地变体：要求上级已有生效版本且策略不是锁定；
      变体记录它依据的上游版本。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitNewDocument()">创建</button>`);
  refreshVariantCandidates();
}

async function refreshVariantCandidates() {
  const select = document.getElementById('ndVariant');
  const orgSelect = document.getElementById('ndOrg');
  if (!select || !orgSelect) return;
  const orgId = orgSelect.value;
  if (!orgId) {
    select.innerHTML = '<option value="">请先选择适用组织</option>';
    return;
  }
  const processId = document.getElementById('ndProcess').value;
  select.innerHTML = '<option value="">加载中…</option>';
  try {
    const rows = await GET(
      '/process-documents?process_id=' + processId + '&org_unit_id=' + orgId);
    const candidates = rows.filter((doc) =>
      doc.effective_version
      && doc.variation_policy !== 'LOCKED'
      && String(doc.org_unit_id) !== String(orgId));
    select.innerHTML = candidates.length
      ? '<option value="">不基于上级（本级标准）</option>' + candidates.map((doc) =>
        `<option value="${doc.id}">${esc(doc.code)} · ${esc(doc.title)}
          （现行 ${esc(doc.effective_version.version_display)}）</option>`).join('')
      : '<option value="">没有可用的上级标准</option>';
  } catch (e) {
    select.innerHTML = '<option value="">加载失败</option>';
    toast(e.message, true);
  }
}

async function submitNewDocument() {
  const title = document.getElementById('ndTitle').value.trim();
  if (!title) return toast('请填写标题', true);
  const payload = {
    process_id: Number(document.getElementById('ndProcess').value),
    title,
    category: document.getElementById('ndCategory').value,
    variation_policy: document.getElementById('ndPolicy').value,
    description: document.getElementById('ndDesc').value.trim() || null,
  };
  const org = document.getElementById('ndOrg').value;
  payload.org_unit_id = org ? Number(org) : null;
  const variant = document.getElementById('ndVariant').value;
  if (variant) payload.variant_of_document_id = Number(variant);
  const owner = document.getElementById('ndOwner').value.trim();
  if (owner) payload.owner = owner;
  try {
    const doc = await POST('/process-documents', payload);
    toast('已创建 ' + doc.code);
    closeModal();
    loadDocuments();
  } catch (e) {
    toast(e.message, true);
  }
}

function openDocumentUpload(documentId) {
  openModal('上传标准文件版本', `
    <div class="field"><label>文件</label><input type="file" id="pdFile"></div>
    <div class="field"><label>版本号（major.minor）</label>
      <input id="pdLabel" placeholder="3.2"></div>
    <div class="field"><label>版本说明</label><textarea id="pdNote"></textarea></div>
    <div class="note">版本只追加不覆盖；上传后为草稿，审批到「已生效」后才能被项目复制。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitDocumentUpload(${documentId})">上传</button>`);
}

async function submitDocumentUpload(documentId) {
  const file = document.getElementById('pdFile');
  const label = document.getElementById('pdLabel').value.trim();
  if (!file || !file.files.length) return toast('请选择文件', true);
  if (!/^\d+\.\d+$/.test(label)) return toast('版本号必须形如 3.2', true);
  const fd = new FormData();
  fd.append('file', file.files[0]);
  fd.append('version_label', label);
  const note = document.getElementById('pdNote').value.trim();
  if (note) fd.append('note', note);
  try {
    const version = await POST_FORM('/process-documents/' + documentId + '/versions/upload', fd);
    toast('已上传 ' + version.version_display);
    closeModal();
    openDocument(documentId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function transitionDocument(documentId, versionId, target) {
  try {
    await POST(
      '/process-documents/' + documentId + '/versions/' + versionId + '/transition',
      { status: target },
    );
    toast('状态已更新');
    openDocument(documentId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function dlDocumentVersion(documentId, versionId, label) {
  try {
    await download(
      '/process-documents/' + documentId + '/versions/' + versionId + '/download',
      '标准文件' + (label || ''),
    );
    toast('已开始下载');
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 项目成果晋升 */

async function openPromote(versionId) {
  const d = state.dlvCurrent;
  if (!d) return toast('请先打开交付物详情', true);
  try {
    const project = await GET('/projects/' + d.project_id);
    if (!project.process_id) return toast('项目未关联流程，不能晋升为标准', true);
    const docs = await GET('/process-documents?project_id=' + d.project_id);
    if (!docs.length) return toast('该项目流程下还没有标准文件，请先创建', true);
    state.promoteDocs = docs;
    openModal('晋升为流程标准', `
      <div class="note mb">从交付物「${esc(d.definition_name)}」的版本
        <b>${esc(d.versions.find((v) => v.id === versionId)?.version_label || '')}</b>
        生成标准文件草稿；审批通过后才生效。</div>
      <div class="field"><label>目标标准文件</label>
        <select class="sel" id="pmDoc" onchange="syncPromoteLabel()">
          ${docs.map((doc) => `<option value="${doc.id}">${esc(doc.code)} · ${esc(doc.title)}
            ${doc.effective_version ? '（现行 ' + esc(doc.effective_version.version_display) + '）' : '（无生效版本）'}</option>`).join('')}
        </select></div>
      <div class="field"><label>目标版本号（major.minor）</label>
        <input id="pmLabel" placeholder="2.0"></div>
      <div class="field"><label>晋升说明</label><textarea id="pmNote"></textarea></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitPromote(${versionId})">生成草稿</button>`);
    syncPromoteLabel();
  } catch (e) {
    toast(e.message, true);
  }
}

function syncPromoteLabel() {
  const select = document.getElementById('pmDoc');
  const input = document.getElementById('pmLabel');
  if (!select || !input) return;
  const doc = (state.promoteDocs || []).find((row) => String(row.id) === select.value);
  if (!doc) return;
  if (!doc.effective_version) {
    input.value = '1.0';
    return;
  }
  const parts = doc.effective_version.version_label.split('.').map(Number);
  input.value = parts[0] + '.' + (parts[1] + 1);
}

async function submitPromote(versionId) {
  const docId = document.getElementById('pmDoc').value;
  const label = document.getElementById('pmLabel').value.trim();
  if (!/^\d+\.\d+$/.test(label)) return toast('版本号必须形如 2.0', true);
  try {
    const version = await POST('/process-documents/' + docId + '/promote', {
      deliverable_version_id: versionId,
      version_label: label,
      note: document.getElementById('pmNote').value.trim() || null,
    });
    toast('已生成标准草稿 ' + version.version_display + '，待审批');
    closeModal();
  } catch (e) {
    toast(e.message, true);
  }
}

/* ============================================================ 基线与审计 */

const BASELINE_TONE = {
  UNCHANGED: 't-gry', CHANGED: 't-yel', ADDED: 't-blu', REMOVED: 't-red',
};
const SEVERITY_TONE = { HIGH: 't-red', MEDIUM: 't-yel', LOW: 't-gry' };
const BASELINE_KIND = { document: '标准文件', template: '模板' };

function paintBaselineTab() {
  const body = document.getElementById('dlvBody');
  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <div><h2>基线与审计</h2>
          <div class="desc" style="margin:0">基线是某个时点的标准版本快照；差异用来回答「基准之后变了什么」</div></div>
        ${canManage() ? '<button class="btn btn-p" onclick="openNewBaseline()">+ 创建基线</button>' : ''}
      </div>
    </div>
    <div id="govPanel">${skeleton(2)}</div>
    <div id="govFindings"></div>
    <div id="blList">${skeleton(3)}</div>`;
  loadGovernance();
  loadFindings();
  loadBaselines();
}

async function loadGovernance() {
  const box = document.getElementById('govPanel');
  if (!box) return;
  try {
    const g = await GET('/baselines/governance');
    const stale = g.stale_variants.map((item) => `
      <tr>
        <td><b>${esc(item.title)}</b><div class="tiny">${esc(item.code)}</div></td>
        <td>${esc(item.scope_label || '—')}</td>
        <td>${esc(item.base_now || '—')} → ${esc(item.base_latest || '—')}</td>
        <td><span class="tag t-yel">${esc(item.status_label)}</span></td>
      </tr>`).join('') || emptyRow(4, '没有落后变体');
    const frozen = g.frozen_items.map((item) => `
      <tr>
        <td>${esc(item.project_code || '—')}</td>
        <td>${esc(item.definition_code || '—')}</td>
        <td>${esc(item.version_label)}</td>
        <td>${esc(item.source_display || '—')} → ${esc(item.latest_display || '—')}</td>
      </tr>`).join('') || emptyRow(4, '没有仍固定旧版的交付物');

    box.innerHTML = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">治理概览</h3>
            <div class="desc" style="margin:0">资产有效性、落后变体、固定旧版与基线覆盖</div></div>
          <span class="tiny">${g.latest_baseline_code
            ? '最新基线：' + esc(g.latest_baseline_name) + '（' + esc(g.latest_baseline_code) + '）'
            : '还没有基线'}</span>
          ${canManage() ? '<button class="btn btn-p" onclick="runAuditScan()">运行审计</button>' : ''}
        </div>
        <div class="grid g4 stat-row">
          <div class="kpi stat"><div class="num">${g.documents_effective}<small>/${g.documents_total}</small></div>
            <div class="lab">标准文件已生效</div></div>
          <div class="kpi stat ${g.variants_stale ? 'is-risk' : ''}">
            <div class="num">${g.variants_stale}<small>/${g.variants_total}</small></div>
            <div class="lab">落后变体</div></div>
          <div class="kpi stat ${g.frozen_references ? 'is-risk' : ''}">
            <div class="num">${g.frozen_references}</div><div class="lab">仍固定旧版交付物</div></div>
          <div class="kpi stat"><div class="num">${num(g.process_coverage_pct)}<small>%</small></div>
            <div class="lab">流程基线覆盖 ${g.processes_covered}/${g.processes_total}</div></div>
        </div>
        <div class="tiny mt">模板：${g.templates_effective}/${g.templates_total} 生效
          · 近 30 天使用 ${g.template_usage_30d} 次
          ${g.latest_diff && Object.keys(g.latest_diff).length
            ? ' · 最新基线差异：变更 ' + (g.latest_diff.CHANGED || 0)
              + ' / 新增 ' + (g.latest_diff.ADDED || 0)
              + ' / 移除 ' + (g.latest_diff.REMOVED || 0)
            : ''}</div>
        <div class="row2 mt">
          <div><h3>待升级变体（${g.variants_stale}）</h3>
            <table class="tbl">
              <thead><tr><th>变体</th><th>范围</th><th>依据 → 最新</th><th>状态</th></tr></thead>
              <tbody>${stale}</tbody>
            </table></div>
          <div><h3>仍固定旧版（${g.frozen_references}）</h3>
            <table class="tbl">
              <thead><tr><th>项目</th><th>交付物</th><th>版本</th><th>来源 → 最新</th></tr></thead>
              <tbody>${frozen}</tbody>
            </table></div>
        </div>
      </div>`;
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function loadFindings() {
  const box = document.getElementById('govFindings');
  if (!box) return;
  try {
    const rows = await GET('/baselines/findings?status=OPEN&limit=50');
    if (!rows.length) {
      box.innerHTML = '<div class="card"><div class="empty">没有待处理的治理问题。</div></div>';
      return;
    }
    box.innerHTML = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">治理待办（${rows.length}）</h3>
            <div class="desc" style="margin:0">扫描自动去重；条件消失会自动关闭，人工可忽略</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>严重度</th><th>类型</th><th>问题</th><th>责任人</th><th>操作</th></tr></thead>
          <tbody>${rows.map((row) => `<tr>
            <td><span class="tag ${SEVERITY_TONE[row.severity] || 't-gry'}">
              ${esc(row.severity_label || row.severity)}</span></td>
            <td>${esc(row.type_label || row.type)}</td>
            <td><b>${esc(row.title)}</b>
              <div class="tiny">${esc(row.detail || '')}${row.org_unit_name
                ? ' · ' + esc(row.org_unit_name) : ''}</div></td>
            <td>${esc(row.owner_name || '—')}</td>
            <td>${canManage()
              ? `<button class="btn-sm" onclick="ignoreFinding(${row.id})">忽略</button>` : '—'}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function runAuditScan() {
  try {
    const result = await POST('/baselines/audit-scan');
    toast('审计完成：新增 ' + result.created + '，自动关闭 ' + result.resolved
      + '，通知 ' + result.notified);
    loadGovernance();
    loadFindings();
  } catch (e) {
    toast(e.message, true);
  }
}

async function ignoreFinding(findingId) {
  try {
    await PATCH('/baselines/findings/' + findingId, { status: 'IGNORED' });
    toast('已忽略该治理待办');
    loadFindings();
  } catch (e) {
    toast(e.message, true);
  }
}

async function loadBaselines() {
  const box = document.getElementById('blList');
  if (!box) return;
  try {
    const rows = await GET('/baselines');
    state.baselines = rows;
    if (!rows.length) {
      box.innerHTML = `<div class="card"><div class="empty">
        还没有基线。建议在年度发布、项目立项或集团升级前创建。</div></div>`;
      return;
    }
    box.innerHTML = `
      <div class="card">
        <table class="tbl">
          <thead><tr><th>基线</th><th>范围</th><th>对象</th><th>项数</th><th>创建</th><th>操作</th></tr></thead>
          <tbody>${rows.map((row) => `<tr>
            <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
            <td>${esc(row.scope_label || row.scope)}</td>
            <td>${esc(row.process_code || row.org_unit_name || '全部')}</td>
            <td>${row.item_count}</td>
            <td>${esc(row.created_by || '—')}<div class="tiny">${dtShort(row.created_at)}</div></td>
            <td><button class="btn-sm" onclick="openBaseline(${row.id})">查看 / 差异</button></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function openBaseline(baselineId) {
  const gen = openModal('加载中…', skeleton(4), '', true);
  try {
    const [detail, diff] = await Promise.all([
      GET('/baselines/' + baselineId),
      GET('/baselines/' + baselineId + '/diff'),
    ]);
    if (!modalAlive(gen)) return;
    paintBaseline(detail, diff);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    }
  }
}

function paintBaseline(detail, diff) {
  const counts = diff.counts || {};
  const diffRows = diff.items.map((item) => `
    <tr>
      <td>${esc(BASELINE_KIND[item.kind] || item.kind)}</td>
      <td><b>${esc(item.title)}</b><div class="tiny">${esc(item.code)}</div></td>
      <td><span class="tag ${BASELINE_TONE[item.status] || 't-gry'}">${esc(item.status_label)}</span></td>
      <td>${esc(item.old_version_display || '—')} → ${esc(item.new_version_display || '—')}</td>
      <td>${esc(item.scope_label || '—')}</td>
    </tr>`).join('') || emptyRow(5, '没有可比较的资产');
  const snapshotRows = detail.items.map((item) => `
    <tr>
      <td>${esc(BASELINE_KIND[item.kind] || item.kind)}</td>
      <td><b>${esc(item.title)}</b><div class="tiny">${esc(item.code)}</div></td>
      <td>${esc(item.version_display)}</td>
      <td>${esc(item.scope_label || '—')}</td>
      <td>${esc(item.process_code || item.definition_code || '—')}</td>
    </tr>`).join('') || emptyRow(5, '基线为空');

  openModal('基线 · ' + detail.name, `
    <div class="note mb">
      <b>${esc(detail.code)}</b> · ${esc(detail.scope_label || detail.scope)}
      · ${detail.item_count} 项 · ${dtShort(detail.created_at)}
      ${detail.note ? '<div class="mt">' + esc(detail.note) + '</div>' : ''}
    </div>
    <div class="grid g4 stat-row">
      <div class="kpi stat"><div class="num">${counts.CHANGED || 0}</div><div class="lab">已变更</div></div>
      <div class="kpi stat"><div class="num">${counts.ADDED || 0}</div><div class="lab">新增</div></div>
      <div class="kpi stat"><div class="num">${counts.REMOVED || 0}</div><div class="lab">已移除</div></div>
      <div class="kpi stat"><div class="num">${counts.UNCHANGED || 0}</div><div class="lab">未变</div></div>
    </div>
    <h3 class="mt">基线 vs 当前有效版本</h3>
    <table class="tbl">
      <thead><tr><th>类型</th><th>资产</th><th>状态</th><th>版本</th><th>范围</th></tr></thead>
      <tbody>${diffRows}</tbody>
    </table>
    <h3 class="mt">基线快照（创建时）</h3>
    <table class="tbl">
      <thead><tr><th>类型</th><th>资产</th><th>当时版本</th><th>范围</th><th>流程/交付物</th></tr></thead>
      <tbody>${snapshotRows}</tbody>
    </table>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>', true);
}

function openNewBaseline() {
  const labels = (state.baselineMeta && state.baselineMeta.scope_labels) || {};
  const processes = state.processes || [];
  openModal('创建资产基线', `
    <div class="field"><label>名称</label>
      <input id="blName" placeholder="如：2026 Q4 标准基线"></div>
    <div class="field"><label>范围</label><select class="sel" id="blScope"
      onchange="syncBaselineScope()">
      ${Object.entries(labels).map(([code, label]) =>
        `<option value="${code}">${esc(label)}</option>`).join('')}
    </select></div>
    <div class="field" id="blProcessWrap"><label>流程（流程范围必填）</label>
      <select class="sel" id="blProcess">
        <option value="">不指定</option>
        ${processes.map((p) => `<option value="${p.id}">${esc(p.code)} · ${esc(p.name)}（L${p.level}）</option>`).join('')}
      </select></div>
    <div class="field" id="blOrgWrap"><label>组织（组织范围必填）</label>
      <select class="sel" id="blOrg">
        <option value="">不指定</option>${orgOptions('')}
      </select></div>
    <div class="field"><label>说明</label><textarea id="blNote"></textarea></div>
    <div class="note">基线只记录当时生效的标准版本，不复制文件；创建后不可修改。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitNewBaseline()">创建</button>`);
  syncBaselineScope();
}

function syncBaselineScope() {
  const scope = document.getElementById('blScope').value;
  const processWrap = document.getElementById('blProcessWrap');
  const orgWrap = document.getElementById('blOrgWrap');
  if (processWrap) processWrap.style.display = scope === 'PROCESS' ? '' : 'none';
  if (orgWrap) orgWrap.style.display = scope === 'ORG' ? '' : 'none';
}

async function submitNewBaseline() {
  const name = document.getElementById('blName').value.trim();
  if (!name) return toast('请填写基线名称', true);
  const scope = document.getElementById('blScope').value;
  const payload = { name, scope, note: document.getElementById('blNote').value.trim() || null };
  if (scope === 'PROCESS') {
    const value = document.getElementById('blProcess').value;
    if (!value) return toast('流程范围的基线必须选择流程', true);
    payload.process_id = Number(value);
  }
  if (scope === 'ORG') {
    const value = document.getElementById('blOrg').value;
    if (!value) return toast('组织范围的基线必须选择组织', true);
    payload.org_unit_id = Number(value);
  }
  try {
    const baseline = await POST('/baselines', payload);
    toast('已创建基线 ' + baseline.code + '（' + baseline.item_count + ' 项）');
    closeModal();
    loadBaselines();
  } catch (e) {
    toast(e.message, true);
  }
}

/* ============================================================ 模板库 */

function paintTemplateTab() {
  const body = document.getElementById('dlvBody');
  const tools = state.tplTools || [];
  const formats = (state.tplMeta && state.tplMeta.format_labels) || {};
  const f = state.deliverables;
  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <div><h2>工具模板库</h2>
          <div class="desc" style="margin:0">模板是受控的方法资产：版本只追加不覆盖，使用与复制都会留痕</div></div>
        ${canManage() ? '<button class="btn btn-p" onclick="openNewTemplate()">+ 新建模板</button>' : ''}
      </div>
      <div class="gap" style="flex-wrap:wrap">
        <select class="sel" onchange="setTplTool(this.value)">
          <option value="">全部工具</option>
          ${tools.map((t) => `<option value="${esc(t.code)}" ${f.templateTool === t.code ? 'selected' : ''}>
            ${esc(t.name)}（阶段${t.stage_no}）</option>`).join('')}
        </select>
        <select class="sel" onchange="setTplFormat(this.value)">
          <option value="">全部格式</option>
          ${Object.entries(formats).map(([code, label]) =>
            `<option value="${code}" ${f.templateFormat === code ? 'selected' : ''}>${esc(label)}</option>`).join('')}
        </select>
        <select class="sel" onchange="setTplOrg(this.value)">
          <option value="">全部组织</option>${orgOptions(f.templateOrgUnitId)}
        </select>
      </div>
    </div>
    <div id="tplGrid">${skeleton(3)}</div>`;
  loadTemplates();
}

function setTplTool(value) {
  state.deliverables.templateTool = value;
  loadTemplates();
}

function setTplFormat(value) {
  state.deliverables.templateFormat = value;
  loadTemplates();
}

function setTplOrg(value) {
  state.deliverables.templateOrgUnitId = value ? Number(value) : null;
  loadTemplates();
}

async function loadTemplates() {
  const grid = document.getElementById('tplGrid');
  if (!grid) return;
  const f = state.deliverables;
  const qs = [];
  if (f.templateTool) qs.push('tool_code=' + encodeURIComponent(f.templateTool));
  if (f.templateFormat) qs.push('format=' + encodeURIComponent(f.templateFormat));
  if (f.templateOrgUnitId) qs.push('org_unit_id=' + f.templateOrgUnitId);
  try {
    const rows = await GET('/tool-templates' + (qs.length ? '?' + qs.join('&') : ''));
    if (!rows.length) {
      grid.innerHTML = `<div class="card"><div class="empty">
        模板库还没有模板。模板属于组织资产，请由流程管理科创建并上传版本。</div></div>`;
      return;
    }
    grid.innerHTML = '<div class="grid g3">' + rows.map((t) => `
      <div class="tool" onclick="openTemplate(${t.id})">
        <div class="ico">${FMT_ICON[t.format] || '📄'}</div>
        <h4>${esc(t.name)}
          ${t.is_default ? '<span class="tag t-grn">默认</span>' : ''}
          ${t.review_overdue ? '<span class="tag t-red">复审逾期</span>' : ''}</h4>
        <p>${esc(t.tool_name || t.tool_code)} · ${esc(t.format_label || t.format)}
          · ${esc(t.scope_label || '集团通用')} · ${t.version_count} 个版本</p>
        <div class="between" style="margin-top:8px">
          <span class="tag ${t.effective_version ? 't-grn' : 't-gry'}">
            ${t.effective_version ? '现行 ' + esc(t.effective_version.version_label) : '无生效版本'}</span>
          <span class="tiny">${esc(t.deliverable_definition_name || '不限交付物')}</span>
        </div>
      </div>`).join('') + '</div>';
  } catch (e) {
    grid.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function openTemplate(templateId) {
  const gen = openModal('加载中…', skeleton(5), '', true);
  try {
    const [d, usages] = await Promise.all([
      GET('/tool-templates/' + templateId),
      canManage() ? GET('/tool-templates/' + templateId + '/usages?limit=20').catch(() => []) : [],
    ]);
    if (!modalAlive(gen)) return;
    paintTemplate(d, usages);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

function paintTemplate(d, usages) {
  const transitions = state.tplMeta.transitions || {};
  const labels = state.tplMeta.status_labels || {};
  const rows = d.versions.map((v) => {
    const actions = [];
    if (v.has_file) {
      actions.push(`<button class="btn-sm" onclick="dlTemplateVersion(${d.id}, ${v.id}, '${esc(v.version_label)}')">下载</button>`);
    }
    if (canManage()) {
      (transitions[v.status] || []).forEach((target) => {
        actions.push(`<button class="btn-sm" onclick="transitionTemplate(${d.id}, ${v.id}, '${target}')">
          ${esc(labels[target] || target)}</button>`);
      });
    }
    return `<tr>
      <td><b>${esc(v.version_label)}</b>
        ${v.id === d.current_version_id ? '<span class="tag t-blu">当前</span>' : ''}</td>
      <td>${statusTag(v.status, v.status_label)}</td>
      <td>${esc(v.file_name || '在线模板')}
        <div class="tiny">${v.checksum ? 'sha256 ' + esc(v.checksum.slice(0, 12)) + '…' : esc(v.note || '')}</div></td>
      <td>${esc(v.created_by || '—')}<div class="tiny">${dtShort(v.created_at)}</div></td>
      <td>${v.valid_from ? dateShort(v.valid_from) : '—'}</td>
      <td>${actions.join(' ') || '—'}</td>
    </tr>`;
  }).join('') || emptyRow(6, '还没有版本');

  const phSource = d.effective_version || d.current_version;
  const placeholders = phSource && phSource.placeholders && phSource.placeholders.length
    ? `<h3 class="mt">占位符（${esc(phSource.version_label)}）</h3>
       <div class="gap" style="flex-wrap:wrap">${phSource.placeholders.map((p) =>
         `<span class="tag ${p.required ? 't-yel' : 't-gry'}">${esc(p.label || p.key)}
            · ${esc(p.source)}${p.required ? ' · 必填' : ''}</span>`).join('')}</div>`
    : '';

  const usageTable = canManage() && usages.length
    ? `<h3 class="mt">最近使用</h3>
       <table class="tbl">
         <thead><tr><th>时间</th><th>方式</th><th>项目</th><th>版本</th><th>操作人</th></tr></thead>
         <tbody>${usages.map((u) => `<tr>
           <td>${dtShort(u.created_at)}</td><td>${esc(u.mode_label || u.mode)}</td>
           <td>${esc(u.project_code || '—')}</td><td>${esc(u.version_label || '—')}</td>
           <td>${esc(u.created_by || '—')}</td></tr>`).join('')}</tbody>
       </table>`
    : '';

  const footer = [
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>',
    canManage() && d.format !== 'ONLINE'
      ? `<button class="btn btn-g" onclick="closeModal();openTemplateUpload(${d.id})">上传新版本</button>` : '',
    canManage() && d.format === 'ONLINE'
      ? `<button class="btn btn-g" onclick="closeModal();openOnlineVersion(${d.id})">新增在线版本</button>` : '',
    canWrite() && d.effective_version
      ? `<button class="btn btn-p" onclick="closeModal();openTemplateCopy(${d.id})">复制到项目</button>` : '',
  ].filter(Boolean).join('');

  openModal((d.tool_name || d.tool_code) + ' · ' + d.name, `
    <div class="note mb">
      <b>${esc(d.code)}</b> · ${esc(d.format_label || d.format)}
      ${d.is_default ? ' · 默认模板' : ''} · 范围：${esc(d.scope_label || '集团通用')}
      · ${d.version_count} 个版本
      <div class="mt">${esc(d.description || '（无说明）')}</div>
      ${d.instructions ? '<div class="mt">使用说明：' + esc(d.instructions) + '</div>' : ''}
      <div class="mt">产出交付物：${esc(d.deliverable_definition_name || '不限')}
        · 负责人：${esc(d.owner || '未指定')}
        · 复审：${d.review_date ? dateShort(d.review_date) : '未设置'}
        ${d.review_overdue ? ' · <span class="tag t-red">已逾期</span>' : ''}</div>
    </div>
    <div class="between mb">
      <div>现行版本：${d.effective_version
        ? esc(d.effective_version.version_label) + ' ' + statusTag(d.effective_version.status, d.effective_version.status_label)
        : '<span class="tag t-gry">暂无</span>'}</div>
    </div>
    <table class="tbl">
      <thead><tr><th>版本</th><th>状态</th><th>文件</th><th>编制</th><th>生效</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${placeholders}${usageTable}`,
  footer, true);
}

function openTemplateUpload(templateId) {
  openModal('上传模板版本', `
    <div class="field"><label>文件</label><input type="file" id="tpFile"></div>
    <div class="field"><label>版本号（major.minor.patch）</label>
      <input id="tpLabel" placeholder="1.0.0"></div>
    <div class="field"><label>版本说明</label><textarea id="tpNote"></textarea></div>
    <div class="field"><label>占位符 JSON（可选）</label>
      <textarea id="tpPh" placeholder='[{"key":"project_name","label":"项目名称","source":"project.name","required":true}]'></textarea></div>
    <div class="note">版本只追加不覆盖；上传后为草稿，审批到「已生效」后才能被使用。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitTemplateUpload(${templateId})">上传</button>`);
}

async function submitTemplateUpload(templateId) {
  const file = document.getElementById('tpFile');
  const label = document.getElementById('tpLabel').value.trim();
  if (!file || !file.files.length) return toast('请选择模板文件', true);
  if (!/^\d+\.\d+\.\d+$/.test(label)) return toast('版本号必须形如 1.0.0', true);
  const fd = new FormData();
  fd.append('file', file.files[0]);
  fd.append('version_label', label);
  const note = document.getElementById('tpNote').value.trim();
  const ph = document.getElementById('tpPh').value.trim();
  if (note) fd.append('note', note);
  if (ph) fd.append('placeholders', ph);
  try {
    const version = await POST_FORM('/tool-templates/' + templateId + '/versions/upload', fd);
    toast('已上传版本 ' + version.version_label);
    closeModal();
    openTemplate(templateId);
  } catch (e) {
    toast(e.message, true);
  }
}

function openOnlineVersion(templateId) {
  openModal('新增在线模板版本', `
    <div class="field"><label>版本号（major.minor.patch）</label><input id="tpLabel" placeholder="1.0.0"></div>
    <div class="field"><label>版本说明</label><textarea id="tpNote"></textarea></div>
    <div class="field"><label>占位符 JSON（可选）</label>
      <textarea id="tpPh" placeholder='[{"key":"project_name","label":"项目名称","source":"project.name","required":true}]'></textarea></div>
    <div class="note">在线模板不生成文件；复制到项目时创建元数据版本，适合清单/检查表。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitOnlineVersion(${templateId})">创建</button>`);
}

async function submitOnlineVersion(templateId) {
  const label = document.getElementById('tpLabel').value.trim();
  if (!/^\d+\.\d+\.\d+$/.test(label)) return toast('版本号必须形如 1.0.0', true);
  const raw = document.getElementById('tpPh').value.trim();
  let placeholders = [];
  if (raw) {
    try { placeholders = JSON.parse(raw); } catch (_) { return toast('占位符不是合法 JSON', true); }
  }
  try {
    const version = await POST('/tool-templates/' + templateId + '/versions', {
      version_label: label,
      note: document.getElementById('tpNote').value.trim() || null,
      placeholders,
    });
    toast('已创建版本 ' + version.version_label);
    closeModal();
    openTemplate(templateId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function transitionTemplate(templateId, versionId, target) {
  try {
    await POST('/tool-templates/' + templateId + '/versions/' + versionId + '/transition',
      { status: target });
    toast('状态已更新');
    openTemplate(templateId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function dlTemplateVersion(templateId, versionId, label) {
  try {
    await download('/tool-templates/' + templateId + '/versions/' + versionId + '/download',
      '模板' + (label || ''));
    toast('已开始下载');
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 新建模板 */

function openNewTemplate() {
  const tools = state.tplTools || [];
  const formats = (state.tplMeta && state.tplMeta.format_labels) || {};
  const defs = state.tplDefinitions || [];
  openModal('新建工具模板', `
    <div class="row2">
      <div class="field"><label>归属工具</label><select class="sel" id="ntTool">
        ${tools.map((t) => `<option value="${esc(t.code)}">${esc(t.name)}（阶段${t.stage_no}）</option>`).join('')}
      </select></div>
      <div class="field"><label>格式</label><select class="sel" id="ntFormat">
        ${Object.entries(formats).map(([code, label]) =>
          `<option value="${code}">${esc(label)}</option>`).join('')}
      </select></div>
    </div>
    <div class="field"><label>模板名称</label><input id="ntName" placeholder="如：SIPOC 空白表"></div>
    <div class="field"><label>适用范围</label><select class="sel" id="ntOrg">
      <option value="">集团通用（所有组织可见）</option>${orgOptions('')}
    </select></div>
    <div class="row2">
      <div class="field"><label>产出交付物（可选）</label><select class="sel" id="ntDef">
        <option value="">不限</option>
        ${defs.map((d) => `<option value="${d.id}">${esc(d.step_no)} · ${esc(d.name)}</option>`).join('')}
      </select></div>
      <div class="field"><label>负责人（可选）</label><input id="ntOwner" placeholder="姓名或岗位"></div>
    </div>
    <div class="field"><label>说明</label><textarea id="ntDesc" placeholder="适用场景、填写要求"></textarea></div>
    <div class="note">编码自动生成；同工具同格式的第一个模板会成为默认模板。</div>`,
  `<button class="btn btn-g" onclick="closeModal()">取消</button>
   <button class="btn btn-p" onclick="submitNewTemplate()">创建</button>`);
}

async function submitNewTemplate() {
  const name = document.getElementById('ntName').value.trim();
  if (!name) return toast('请填写模板名称', true);
  const defId = document.getElementById('ntDef').value;
  const payload = {
    tool_code: document.getElementById('ntTool').value,
    name,
    format: document.getElementById('ntFormat').value,
    description: document.getElementById('ntDesc').value.trim() || null,
    deliverable_definition_id: defId ? Number(defId) : null,
  };
  const org = document.getElementById('ntOrg').value;
  payload.org_unit_id = org ? Number(org) : null;
  const owner = document.getElementById('ntOwner').value.trim();
  if (owner) payload.owner = owner;
  try {
    const t = await POST('/tool-templates', payload);
    toast('已创建模板 ' + t.code);
    closeModal();
    loadTemplates();
  } catch (e) {
    toast(e.message, true);
  }
}

export {
  renderDeliverables, setDlvTab, setDlvProject,
  openDeliverableUpload, submitDeliverableUpload, openDeliverable,
  transitionDeliverable, restoreDeliverable, dlDeliverableVersion,
  setDocProcess, setDocCategory, setDocOrg, openDocument, openNewDocument,
  submitNewDocument, refreshVariantCandidates, openDocumentUpload, submitDocumentUpload,
  transitionDocument, dlDocumentVersion,
  openDocumentImpact, openRebase, submitRebase,
  openPromote, syncPromoteLabel, submitPromote,
  openBaseline, openNewBaseline, submitNewBaseline, syncBaselineScope,
  runAuditScan, ignoreFinding,
  setTplTool, setTplFormat, setTplOrg, openNewTemplate, submitNewTemplate,
  openTemplate, openTemplateUpload, submitTemplateUpload,
  openOnlineVersion, submitOnlineVersion, transitionTemplate, dlTemplateVersion,
};
