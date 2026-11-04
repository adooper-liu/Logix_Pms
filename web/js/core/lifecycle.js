/* 生命周期共享内容：只消费后端目录，不持有业务阶段状态。 */
import { GET } from './api.js';
import { esc } from './format.js';
import { state } from './state.js';

export async function loadLifecycle(params = {}) {
  const query = new URLSearchParams();
  if (params.process !== undefined && params.process !== '') query.set('process_id', params.process);
  if (params.project !== undefined && params.project !== '') query.set('project_id', params.project);
  return GET('/lifecycle' + (query.size ? '?' + query : ''));
}

function identityParams(data) {
  const params = {};
  if (data.context.process) params.process = String(data.context.process.id);
  if (data.context.project) params.project = String(data.context.project.id);
  return params;
}

export function stageByKey(data, key) {
  return [...data.stages, data.governance].find((row) => row.key === key);
}

export function destination(data, key) {
  const stage = stageByKey(data, key);
  if (!stage) throw new Error('未知的生命周期任务');
  return { view: stage.target.view,
    params: { ...identityParams(data), ...stage.target.params, lifecycle: key } };
}

export function taskHtml(data, key) {
  const stage = stageByKey(data, key);
  if (!stage) return '';
  const process = data.context.process;
  const project = data.context.project;
  return `<section class="card" id="lifecycleTask" data-lifecycle="${esc(key)}">
    <div class="between"><h3>${esc(stage.label)} · 任务与交接</h3>
      <button class="btn-sm" data-act="lifecycle.return">返回生命周期</button></div>
    <p class="tiny">${process ? esc(process.code + ' ' + process.name) : '尚未选择流程'}${project ? ' · 项目 ' + esc(project.code) : ' · 未关联项目（不强迫立项）'}</p>
    <dl><dt>本步任务</dt><dd>${esc(stage.task)}</dd>
      <dt>方法</dt><dd>${stage.method_codes.map((code) => `<button class="btn-sm" data-act="lifecycle.method" data-code="${esc(code)}">${esc(data.method_labels[code] || code)}</button>`).join(' ')}</dd>
      <dt>原产物</dt><dd>${esc(stage.artifact)}</dd>
      <dt>核验</dt><dd>${esc(stage.verification)}</dd></dl>
    <p class="tiny muted">${esc(stage.boundary)}</p>
    <button class="btn-sm" data-act="lifecycle.open" data-key="${esc(stage.next_key)}">下一步：${esc(stageByKey(data, stage.next_key).label)}（按任务选择，非阶段推进）</button>
  </section>`;
}

export function lifecycleHtml(data, processes) {
  state.lifecycle = data;
  const selected = data.context.process;
  const options = (processes || []).filter((row) => row.level === 3 || row.level === 4);
  return `<section class="card" id="lifecycleDirectory">
    <h3>BPM生命周期 · 八阶段任务导航</h3>
    <p class="tiny">管理同一条长期流程；不是项目阶段或必须顺序完成的状态机。项目交付仍用原五阶段。</p>
    <label>流程上下文 <select class="sel" data-act="lifecycle.process">
      <option value="">尚未选择流程</option>${options.map((row) => `<option value="${row.id}"${selected && selected.id === row.id ? ' selected' : ''}>${esc(row.code + ' ' + row.name)}</option>`).join('')}</select></label>
    <div class="life-row">${data.stages.map((row) => `<button class="life-step" data-act="lifecycle.open" data-key="${esc(row.key)}"><b>${esc(row.label)}</b><span class="tiny">${esc(row.target.label)}</span></button>`).join('')}</div>
    <div class="note mt">治理贯穿全程：<button class="btn-sm" data-act="lifecycle.open" data-key="governance">${esc(data.governance.label)}</button></div>
    <p class="tiny">进入原模块后按任务使用方法、保存原产物并核验；入口说明不代表算法或业务验收已实现。</p>
  </section>`;
}
