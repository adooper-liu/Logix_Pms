/* 复制到项目：工具模板与流程标准文件共用同一套交互。
 *
 * 放在 core 而不是某个视图里，避免 views 之间互相 import。
 * 复制成功后刷新当前视图，保证项目交付物列表拿到最新状态。
 */
import { GET, POST } from './api.js';
import { toast, openModal, closeModal } from './ui.js';
import { state } from './state.js';
import { esc } from './format.js';
import { RENDERERS } from './router.js';

function renderDialog(source) {
  return `
    <div class="note mb">来源：<b>${esc(source.code)}</b> · ${esc(source.version)}
      ${source.target
        ? ' · 产出「' + esc(source.target) + '」' : ''}
      <div class="mt">复制会创建交付物新版本，并固定来源版本；来源后续升级不会改动它。</div></div>
    <div class="field"><label>目标项目</label>
      <select class="sel" id="cpProject" onchange="fillCopyInstances()">
        ${source.projects.map((p) =>
          `<option value="${p.id}">${esc(p.code)} · ${esc(p.name)}</option>`).join('')}
      </select></div>
    <div class="field"><label>目标交付物</label>
      <select class="sel" id="cpInstance"><option value="">加载中…</option></select></div>
    <div class="field"><label>版本标题（可选）</label>
      <input id="cpTitle" value="${esc(source.title)}"></div>`;
}

const FOOT = `<button class="btn btn-g" onclick="closeModal()">取消</button>
  <button class="btn btn-p" onclick="submitTemplateCopy()">复制</button>`;

export async function openTemplateCopy(templateId) {
  try {
    const [tpl, page] = await Promise.all([
      GET('/tool-templates/' + templateId),
      GET('/projects?page_size=200'),
    ]);
    const projects = page.items || [];
    if (!projects.length) return toast('还没有项目，先去「流程项目组合」立项', true);
    if (!tpl.effective_version) return toast('该模板还没有已生效版本', true);
    state.copySource = {
      kind: 'template',
      id: tpl.id,
      code: tpl.code,
      version: tpl.effective_version.version_label,
      title: tpl.name,
      target: tpl.deliverable_definition_name,
      definitionId: tpl.deliverable_definition_id,
      projects,
    };
    openModal('复制模板到项目', renderDialog(state.copySource), FOOT);
    fillCopyInstances();
  } catch (e) {
    toast(e.message, true);
  }
}

export async function openDocumentCopy(documentId) {
  try {
    const [doc, page] = await Promise.all([
      GET('/process-documents/' + documentId),
      GET('/projects?page_size=200'),
    ]);
    const projects = page.items || [];
    if (!projects.length) return toast('还没有项目，先去「流程项目组合」立项', true);
    if (!doc.effective_version) return toast('该标准文件还没有已生效版本', true);
    if (!doc.effective_version.has_file) return toast('该标准版本没有文件，无法复制', true);
    state.copySource = {
      kind: 'document',
      id: doc.id,
      versionId: doc.effective_version.id,
      code: doc.code,
      version: doc.effective_version.version_display,
      title: doc.title,
      target: doc.process_code ? doc.process_code + ' ' + (doc.process_name || '') : '',
      definitionId: null,
      projects,
    };
    openModal('复制标准文件到项目', renderDialog(state.copySource), FOOT);
    fillCopyInstances();
  } catch (e) {
    toast(e.message, true);
  }
}

export async function fillCopyInstances() {
  const select = document.getElementById('cpInstance');
  const projectSelect = document.getElementById('cpProject');
  if (!select || !projectSelect) return;
  const source = state.copySource;
  select.innerHTML = '<option value="">加载中…</option>';
  try {
    const rows = await GET('/projects/' + projectSelect.value + '/deliverables');
    const filtered = source && source.definitionId
      ? rows.filter((r) => r.definition_id === source.definitionId)
      : rows;
    select.innerHTML = filtered.length
      ? filtered.map((r) => `<option value="${r.id}">${esc(r.step_no)} · ${esc(r.definition_name)}
          （${esc(r.status_label)}）</option>`).join('')
      : '<option value="">没有匹配的交付物</option>';
  } catch (e) {
    select.innerHTML = '<option value="">加载失败</option>';
    toast(e.message, true);
  }
}

export async function submitTemplateCopy() {
  const source = state.copySource;
  const select = document.getElementById('cpInstance');
  if (!source || !select || !select.value) return toast('请选择目标交付物', true);
  const titleBox = document.getElementById('cpTitle');
  const title = titleBox && titleBox.value.trim() ? titleBox.value.trim() : null;
  const path = source.kind === 'document'
    ? '/process-documents/' + source.id + '/versions/' + source.versionId
      + '/copy-to-deliverable'
    : '/tool-templates/' + source.id + '/copy';
  try {
    const version = await POST(path, {
      deliverable_instance_id: Number(select.value),
      title,
    });
    toast('已复制为 ' + version.version_label);
    closeModal();
    const render = RENDERERS[state.view];
    if (render) render();
  } catch (e) {
    toast(e.message, true);
  }
}
