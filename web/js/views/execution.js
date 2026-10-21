/* 视图：execution —— 流程实例与任务队列 */
import { esc, dtShort, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { GET, POST } from '../core/api.js';

/* ============================================================ 9. 流程执行 */

const renderExecution = () => renderAsync('execution',
  () => Promise.all([
    GET('/execution/tasks?only_open=true&limit=500'),
    GET('/execution/instances?limit=200'),
    GET('/execution/processes'),
  ]).then(([tasks, instances, processes]) => ({ tasks, instances, processes })),
  (d) => {
    const ex = state.execution || (state.execution = { tab: 'tasks', filter: 'open' });
    state.executionTasks = d.tasks;
    state.executionInstances = d.instances;
    state.executionProcesses = d.processes;

    const me = AUTH.user ? AUTH.user.id : null;
    const mine = d.tasks.filter((t) => t.assignee_user_id === me);
    const queue = d.tasks.filter((t) => t.assignee_user_id === null);
    const running = d.instances.filter((i) => i.status === 'RUNNING');
    const filter = ex.filter || 'open';
    const shown = filter === 'mine' ? mine : filter === 'queue' ? queue : d.tasks;

    const taskRows = shown.map((t) => {
      const canAct = canWrite()
        && (t.assignee_user_id === null || t.assignee_user_id === me || canManage());
      const action = !canWrite()
        ? '<button class="btn-sm" onclick="openTask(' + t.id + ')">查看</button>'
        : t.assignee_user_id === null
          ? '<button class="btn-sm btn-p" onclick="claimTask(' + t.id + ')">认领</button>'
          : canAct
            ? '<button class="btn-sm" onclick="openTask(' + t.id + ')">处理</button>'
            : '<button class="btn-sm" onclick="openTask(' + t.id + ')">查看</button>';
      return `
        <tr class="exec-task-row" data-task-id="${t.id}" data-instance-id="${t.instance_id}">
          <td><b>${esc(t.name)}</b>
            <div class="tiny">${esc(t.node_key)} · ${esc(t.task_type_label)} ·
              ${esc(t.instance_code)}</div></td>
          <td>${esc(t.process_name)}<div class="tiny">${esc(t.lane || '—')}</div></td>
          <td>${esc(t.candidate_role || '—')}</td>
          <td>${t.assignee_name ? esc(t.assignee_name) : '<span class="muted">公共队列</span>'}</td>
          <td><span class="tag ${t.status === 'PENDING' ? 't-yel' : 't-blu'}">${esc(t.status_label)}</span></td>
          <td class="tiny">${dtShort(t.created_at)}</td>
          <td>${action}</td>
        </tr>`;
    }).join('') || emptyRow(7, filter === 'mine'
      ? '当前没有指派给你的任务'
      : filter === 'queue' ? '公共队列为空' : '没有待办任务');

    const instanceRows = d.instances.map((i) => `
      <tr class="exec-instance-row" data-instance-id="${i.id}" onclick="openInstance(${i.id})">
        <td><b>${esc(i.code)}</b><div class="tiny">${esc(i.process_name)}</div></td>
        <td><span class="tag ${i.status === 'RUNNING' ? 't-blu' : i.status === 'COMPLETED' ? 't-grn' : 't-gry'}">
          ${esc(i.status_label)}</span></td>
        <td>${i.current_node_name ? esc(i.current_node_name) : '—'}
          <div class="tiny">${esc(i.current_node_key || '')}</div></td>
        <td>${i.open_task_count}</td>
        <td class="tiny">${esc(i.started_by_name || '—')}<div>${dtShort(i.started_at)}</div></td>
        <td><button class="btn-sm" onclick="event.stopPropagation();openInstance(${i.id})">详情</button></td>
      </tr>`).join('') || emptyRow(6, '还没有流程实例');

    const tabs = `
      <div class="seg">
        <button class="${ex.tab === 'tasks' ? 'on' : ''}" onclick="setExecutionTab('tasks')">待办任务</button>
        <button class="${ex.tab === 'instances' ? 'on' : ''}" onclick="setExecutionTab('instances')">流程实例</button>
      </div>`;

    const taskPane = `
      <div class="grid g4 stat-row">
        <button class="kpi stat" onclick="setExecutionFilter('mine')">
          <div class="num">${mine.length}</div><div class="lab">我的待办</div></button>
        <button class="kpi stat" onclick="setExecutionFilter('queue')">
          <div class="num">${queue.length}</div><div class="lab">公共队列</div></button>
        <button class="kpi stat" onclick="setExecutionFilter('open')">
          <div class="num">${d.tasks.length}</div><div class="lab">全部待办</div></button>
        <div class="kpi stat"><div class="num">${running.length}</div><div class="lab">运行中实例</div></div>
      </div>
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">任务队列</h3>
            <div class="desc" style="margin:2px 0 0">认领后即可处理；分支节点在完成时选择下一步</div></div>
          <div class="seg">
            <button class="${filter === 'open' ? 'on' : ''}" onclick="setExecutionFilter('open')">全部待办</button>
            <button class="${filter === 'mine' ? 'on' : ''}" onclick="setExecutionFilter('mine')">我的</button>
            <button class="${filter === 'queue' ? 'on' : ''}" onclick="setExecutionFilter('queue')">公共队列</button>
          </div>
        </div>
        <table class="tbl">
          <thead><tr><th>任务</th><th>流程</th><th>候选角色</th><th>处理人</th>
            <th>状态</th><th>创建时间</th><th></th></tr></thead>
          <tbody>${taskRows}</tbody>
        </table>
      </div>`;

    const instancePane = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">流程实例</h3>
            <div class="desc" style="margin:2px 0 0">共 ${d.instances.length} 个实例；点击查看任务时间线</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>实例</th><th>状态</th><th>当前节点</th><th>待办</th>
            <th>发起人 / 时间</th><th></th></tr></thead>
          <tbody>${instanceRows}</tbody>
        </table>
      </div>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>流程执行</h2>
            <div class="desc">启动流程实例 · 认领任务 · 推进到下一节点</div></div>
          <div class="gap">
            <button class="btn btn-p" id="execStartBtn"
              onclick="startInstanceModal()"${canWrite() ? '' : ' disabled'}>+ 启动流程</button>
          </div>
        </div>
        <div class="mt">${tabs}</div>
      </div>
      ${ex.tab === 'instances' ? instancePane : taskPane}`;
  });

function setExecutionTab(tab) {
  state.execution.tab = tab;
  RENDERERS.execution();
}

function setExecutionFilter(filter) {
  state.execution.filter = filter;
  state.execution.tab = 'tasks';
  RENDERERS.execution();
}

async function claimTask(taskId) {
  try {
    await POST('/execution/tasks/' + taskId + '/claim', {});
    toast('任务已认领');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function startInstanceModal() {
  openModal('启动流程实例', skeleton(4));
  let processes = state.executionProcesses;
  let projects = [];
  try {
    [processes, projects] = await Promise.all([
      processes || GET('/execution/processes'),
      GET('/projects?page_size=100'),
    ]);
  } catch (e) {
    openModal('加载失败', `<div class="errbar"><div>${esc(e.message)}</div></div>`);
    return;
  }
  const processOpts = processes.map((p) =>
    `<option value="${p.id}">L${p.level} ${esc(p.code)} ${esc(p.name)}（${p.node_count} 节点）</option>`
  ).join('');
  const projectOpts = projects.items.map((p) =>
    `<option value="${p.id}">${esc(p.code)} ${esc(p.name)}</option>`
  ).join('');
  openModal('启动流程实例', `
    <div class="field"><label>流程 *</label>
      <select id="exProcess">${processOpts || '<option value="">没有已建模的流程</option>'}</select>
      <div class="hint">只列出设计器里已有节点的流程</div></div>
    <div class="field"><label>关联项目</label>
      <select id="exProject"><option value="">不关联</option>${projectOpts}</select></div>
    <div class="field"><label>流程变量（JSON）</label>
      <textarea id="exVars" placeholder='{"申请人":"张三","金额":10000}'>{"source":"manual"}</textarea></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitStartInstance()">启动</button>`);
}

async function submitStartInstance() {
  const processId = document.getElementById('exProcess').value;
  const projectId = document.getElementById('exProject').value;
  const raw = document.getElementById('exVars').value.trim();
  let variables = {};
  if (raw) {
    try { variables = JSON.parse(raw); } catch (e) { return toast('流程变量不是合法 JSON', true); }
  }
  if (!processId) return toast('请选择流程', true);
  try {
    const instance = await POST('/execution/instances', {
      process_id: Number(processId),
      project_id: projectId ? Number(projectId) : null,
      variables,
    });
    closeModal();
    toast('流程已启动：' + instance.code);
    state.execution.tab = 'tasks';
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function openTask(taskId) {
  const gen = openModal('加载中…', skeleton(4));
  let task;
  try {
    task = await GET('/execution/tasks/' + taskId);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal('加载失败', `<div class="errbar"><div>${esc(e.message)}</div></div>`);
    }
    return;
  }
  if (!modalAlive(gen)) return;
  const me = AUTH.user ? AUTH.user.id : null;
  const canAct = canWrite()
    && (task.assignee_user_id === null || task.assignee_user_id === me || canManage());
  const options = task.next_options.map((o) =>
    `<option value="${esc(o.node_key)}">${esc(o.node_key)} ${esc(o.name)}${
      o.label ? ' · ' + esc(o.label) : ''}</option>`
  ).join('');

  openModal(task.name + ' · ' + task.instance_code, `
    <div class="row2">
      <div class="field"><label>流程</label><input value="${esc(task.process_name)}" readonly></div>
      <div class="field"><label>节点</label>
        <input value="${esc(task.node_key)} · ${esc(task.task_type_label)}" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>候选角色 / 泳道</label>
        <input value="${esc(task.candidate_role || task.lane || '—')}" readonly></div>
      <div class="field"><label>处理人</label>
        <input value="${esc(task.assignee_name || '公共队列')}" readonly></div>
    </div>
    ${task.status === 'COMPLETED' ? `
      <div class="field"><label>完成情况</label>
        <textarea readonly>${esc(task.comment || '—')}</textarea></div>` : ''}
    ${canAct && task.status !== 'COMPLETED' ? `
      ${task.next_options.length > 1 ? `
        <div class="field"><label>下一步 *</label>
          <select id="exNext">${options}</select>
          <div class="hint">该节点有多个分支，请选择实际流转方向</div></div>` : ''}
      <div class="field"><label>表单数据（JSON，可选）</label>
        <textarea id="exForm" placeholder='{"审批意见":"同意","金额":10000}'>{}</textarea></div>
      <div class="field"><label>处理意见 / 备注</label>
        <input id="exComment" placeholder="处理结论或说明"></div>` : ''}
    ${canAct && task.status !== 'COMPLETED'
      ? '<div class="note">完成后流程会自动推进到下一节点；没有后续节点时实例结束。</div>'
      : '<div class="note">只读：任务已指派给其他人，或当前角色没有处理权限。</div>'}`,
    `<button class="btn btn-g" onclick="closeModal()">关闭</button>
     ${canAct && task.status !== 'COMPLETED'
       ? '<button class="btn btn-p" onclick="completeTask(' + task.id + ')">完成并推进</button>' : ''}`);
}

async function completeTask(taskId) {
  const raw = document.getElementById('exForm') ? document.getElementById('exForm').value.trim() : '';
  let formData = null;
  if (raw) {
    try { formData = JSON.parse(raw); } catch (e) { return toast('表单数据不是合法 JSON', true); }
  }
  const nextEl = document.getElementById('exNext');
  const commentEl = document.getElementById('exComment');
  try {
    await POST('/execution/tasks/' + taskId + '/complete', {
      form_data: formData,
      next_node_key: nextEl ? nextEl.value : null,
      comment: commentEl ? commentEl.value.trim() || null : null,
    });
    closeModal();
    toast('任务已完成，流程已推进');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function openInstance(instanceId) {
  const gen = openModal('加载中…', skeleton(6));
  let detail;
  try {
    detail = await GET('/execution/instances/' + instanceId);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal('加载失败', `<div class="errbar"><div>${esc(e.message)}</div></div>`);
    }
    return;
  }
  if (!modalAlive(gen)) return;
  const i = detail.instance;
  const rows = detail.tasks.map((t) => `
    <tr>
      <td>${esc(t.node_key)} ${esc(t.name)}<div class="tiny">${esc(t.task_type_label)}</div></td>
      <td><span class="tag ${t.status === 'COMPLETED' ? 't-grn' : t.status === 'CANCELLED' ? 't-gry' : 't-blu'}">
        ${esc(t.status_label)}</span></td>
      <td>${esc(t.assignee_name || '—')}</td>
      <td class="tiny">${t.completed_at ? dtShort(t.completed_at) : '—'}
        ${t.comment ? '<div>' + esc(t.comment) + '</div>' : ''}</td>
    </tr>`).join('') || emptyRow(4, '还没有任务');

  openModal(i.code + ' · ' + i.process_name, `
    <div class="row2">
      <div class="field"><label>状态</label><input value="${esc(i.status_label)}" readonly></div>
      <div class="field"><label>当前节点</label>
        <input value="${esc(i.current_node_name || '—')}" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>发起人</label><input value="${esc(i.started_by_name || '—')}" readonly></div>
      <div class="field"><label>发起时间</label><input value="${dtShort(i.started_at)}" readonly></div>
    </div>
    <div class="field"><label>流程变量</label>
      <textarea readonly>${esc(JSON.stringify(detail.variables || {}, null, 2))}</textarea></div>
    <h3 class="mt">任务时间线</h3>
    <table class="tbl">
      <thead><tr><th>节点</th><th>状态</th><th>处理人</th><th>完成时间 / 备注</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`,
    `${canManage() && i.status === 'RUNNING'
      ? '<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"'
        + ' onclick="cancelInstance(' + i.id + ')">取消实例</button>' : ''}
     <button class="btn btn-g" onclick="closeModal()">关闭</button>`);
}

async function cancelInstance(instanceId) {
  if (!confirm('确定取消这个流程实例？未完成的任务会一并取消。')) return;
  try {
    await POST('/execution/instances/' + instanceId + '/cancel', {});
    closeModal();
    toast('流程实例已取消');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}


export {
  renderExecution, cancelInstance, claimTask, completeTask, openInstance, openTask,
  setExecutionFilter, setExecutionTab, startInstanceModal, submitStartInstance,
};
