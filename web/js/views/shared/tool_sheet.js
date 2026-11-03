/* 填写工具模板并挂到流程。工具箱和各生命周期页面共用这一张表。 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal, modalAlive } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { RENDERERS, urlParams } from '../../core/router.js';
import { GET, POST } from '../../core/api.js';
import { canWrite } from '../../core/auth.js';

function sheetProjectId() {
  const trail = state.navTrail || [];
  for (let index = trail.length - 1; index >= 0; index -= 1) {
    const project = (trail[index].params || {}).project;
    if (project) return Number(project);
  }
  const current = urlParams().project;
  return current ? Number(current) : null;
}

async function openToolSheet(code, processId) {
  if (!canWrite()) {
    toast('填写并挂上需要可写权限', true);
    return;
  }
  const preset = Number(processId) || null;
  const gen = openModal('填写模板', '<div class="empty">加载模板…</div>');
  try {
    const [form, processes] = await Promise.all([
      GET('/tools/' + encodeURIComponent(code) + '/sheet-form'),
      GET('/process-map/flat'),
    ]);
    if (!modalAlive(gen)) return;
    const options = processes
      .filter((row) => !row.is_draft)
      .sort((a, b) => a.level - b.level || String(a.code).localeCompare(String(b.code)))
      .map((row) => `<option value="${row.id}"${
        preset === row.id ? ' selected' : ''}>L${row.level} ${esc(row.code)} ${esc(row.name)}</option>`)
      .join('');
    const fields = form.fields.map((field) => {
      const label = `<label>${esc(field.label)}${field.required ? ' *' : ''}</label>`;
      if (field.kind === 'choice' && field.options && field.options.length) {
        const options = field.options.map((item) => `<option value="${esc(item)}">${esc(item)}</option>`).join('');
        return `<div class="field">${label}<select id="ts-${esc(field.key)}"><option value="">请选择</option>${options}</select></div>`;
      }
      return `<div class="field">${label}${field.multiline
        ? `<textarea id="ts-${esc(field.key)}" rows="3"></textarea>`
        : `<input id="ts-${esc(field.key)}">`}</div>`;
    }).join('');
    const source = form.template_name
      ? `工具模板库 · ${form.template_name}${form.template_version ? ' ' + form.template_version : ''}`
      : (form.source_note || '');
    const writeNote = form.writes === 'objective'
      ? '保存后写成一条战略目标，并挂到所选流程。地图上的三个分数不在这里改。'
      : '保存后挂到所选流程。流程卡上能看到这次填写。';
    const body = form.fields.length
      ? `${fields}
      <div class="field"><label>挂到流程 *</label>
        <select id="tsProcess">${options || '<option value="">还没有流程</option>'}</select></div>
      ${form.allow_keep
        ? `<label class="tiny"><input type="checkbox" id="tsKeep"> 把「留下」里的每一行写成一条目标，并挂到这条流程</label>`
        : ''}`
      : `<div class="empty">${esc(form.source_note || '工具模板库还没有这份可填写的模板。')}</div>`;
    const submit = form.fields.length
      ? `<button class="btn btn-p" data-act="toolbox.submitSheet" data-code="${esc(code)}">写入并挂上</button>`
      : '';
    openModal('填写 · ' + (form.template_name || form.tool_name), `
      ${source ? `<div class="note mb">${esc(source)}</div>` : ''}
      <div class="note mb">${writeNote}</div>
      ${body}`,
    `<button class="btn btn-g" data-act="toolbox.close">取消</button>${submit}`);
  } catch (e) {
    if (!modalAlive(gen)) return;
    openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

async function submitToolSheet(code) {
  const processId = Number(document.getElementById('tsProcess')?.value || '');
  if (!processId) return toast('请选择要挂上的流程', true);
  const values = {};
  document.querySelectorAll('[id^="ts-"]').forEach((el) => {
    values[el.id.slice(3)] = el.value.trim();
  });
  const keep = document.getElementById('tsKeep');
  try {
    const saved = await POST('/tools/' + encodeURIComponent(code) + '/sheets', {
      process_id: processId,
      project_id: sheetProjectId(),
      step_no: state.toolbox.step || null,
      values,
      make_objectives: !!(keep && keep.checked),
    });
    const where = (saved.process_code || '') + ' ' + (saved.process_name || '');
    const made = saved.objective_codes && saved.objective_codes.length
      ? '；已生成目标 ' + saved.objective_codes.join('、')
      : '';
    toast('方法记录已保存，已关联' + where.trim() + made);
    closeModal();
    const refresh = RENDERERS[state.view];
    if (typeof refresh === 'function') refresh();
  } catch (e) {
    toast(e.message, true);
  }
}

export { openToolSheet, submitToolSheet };
