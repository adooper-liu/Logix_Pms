/* 视图：execution —— 流程实例与任务队列 */
import { esc, dtShort, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';

/* ============================================================ 9. 流程执行 */

const renderExecution = () => {
  const ex = state.execution || (state.execution = { tab: 'tasks', filter: 'open' });
  return renderAsync('execution',
    () => Promise.all([
      GET('/execution/tasks?only_open=true&limit=500'),
      GET('/execution/instances?limit=200'),
      GET('/execution/processes'),
    ]).then(async ([tasks, instances, processes]) => {
      let forms = [];
      let rules = [];
      let endpoints = [];
      let deliveries = [];
      if (ex.tab === 'config' && processes.length) {
        const pid = ex.configProcess || processes[0].id;
        ex.configProcess = pid;
        [forms, rules] = await Promise.all([
          GET('/execution/forms?process_id=' + pid),
          GET('/execution/rules?process_id=' + pid),
        ]);
      }
      if (ex.tab === 'integrations') {
        [endpoints, deliveries] = await Promise.all([
          GET('/integrations/endpoints'),
          GET('/integrations/deliveries?limit=100'),
        ]);
      }
      return { tasks, instances, processes, forms, rules, endpoints, deliveries };
    }),
    (d) => {
      state.executionTasks = d.tasks;
      state.executionInstances = d.instances;
      state.executionProcesses = d.processes;
      state.executionForms = d.forms;
      state.executionRules = d.rules;
      state.executionEndpoints = d.endpoints;
      state.executionDeliveries = d.deliveries;

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
        ${canManage() ? `<button class="${ex.tab === 'config' ? 'on' : ''}"
          onclick="setExecutionTab('config')">表单与规则</button>
          <button class="${ex.tab === 'integrations' ? 'on' : ''}"
          onclick="setExecutionTab('integrations')">集成</button>` : ''}
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

    const cfgProcess = d.processes.find((p) => p.id === ex.configProcess) || d.processes[0];
    const formRows = (d.forms || []).map((f) => `
      <tr><td><b>${esc(f.node_key || '流程默认')}</b></td><td>${esc(f.name)}</td>
        <td>${(f.fields || []).length}</td>
        <td>${f.is_active ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
        <td><button class="btn-sm" onclick="editFormModal(${f.id})">编辑</button>
          <button class="btn-sm" onclick="deleteForm(${f.id})">删除</button></td></tr>`).join('')
      || emptyRow(5, '暂无表单定义');
    const ruleRows = (d.rules || []).map((r) => {
      const cond = (r.conditions || [])
        .map((c) => `${c.field} ${c.op} ${c.value}`).join(' 且 ') || '无条件（兜底）';
      return `<tr><td><b>${esc(r.node_key)}</b></td>
        <td>${esc(r.name)}<div class="tiny">${esc(cond)}</div></td>
        <td>${esc(r.target_node_key)}</td><td>${r.priority}</td>
        <td><button class="btn-sm" onclick="editRuleModal(${r.id})">编辑</button>
          <button class="btn-sm" onclick="deleteRule(${r.id})">删除</button></td></tr>`;
    }).join('') || emptyRow(5, '暂无分支规则');

    const configPane = !canManage()
      ? '<div class="card"><div class="empty">需要流程管理科或管理员权限</div></div>'
      : `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">表单与规则</h3>
            <div class="desc" style="margin:2px 0 0">表单随实例启动冻结；规则按优先级匹配，显式下一步优先</div></div>
          <select class="sel" onchange="setExecutionConfigProcess(this.value)">
            ${d.processes.map((p) => `<option value="${p.id}"${
              cfgProcess && p.id === cfgProcess.id ? ' selected' : ''}>L${p.level} ${esc(p.code)} ${esc(p.name)}</option>`).join('')}
          </select>
        </div>
        <div class="grid g2" style="align-items:start">
          <div>
            <div class="between mb"><h3 style="margin:0">表单定义</h3>
              <button class="btn-sm" onclick="editFormModal(null)">+ 新建表单</button></div>
            <table class="tbl">
              <thead><tr><th>节点</th><th>名称</th><th>字段</th><th>状态</th><th></th></tr></thead>
              <tbody>${formRows}</tbody>
            </table>
          </div>
          <div>
            <div class="between mb"><h3 style="margin:0">分支规则</h3>
              <button class="btn-sm" onclick="editRuleModal(null)">+ 新建规则</button></div>
            <table class="tbl">
              <thead><tr><th>节点</th><th>规则</th><th>目标</th><th>优先级</th><th></th></tr></thead>
              <tbody>${ruleRows}</tbody>
            </table>
          </div>
        </div>
      </div>`;

    const endpointRows = (d.endpoints || []).map((ep) => `
      <tr><td><b>${esc(ep.code)}</b><div class="tiny">${esc(ep.url)}</div></td>
        <td>${esc(ep.name)}<div class="tiny">${esc(ep.kind)}</div></td>
        <td class="tiny">${(ep.events || []).length ? esc(ep.events.join('、')) : '全部事件'}</td>
        <td>${ep.has_secret ? '<span class="tag t-blu">已签名</span>' : '<span class="muted">无签名</span>'}</td>
        <td>${ep.is_active ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
        <td><button class="btn-sm" onclick="editEndpointModal(${ep.id})">编辑</button>
          <button class="btn-sm" onclick="deleteEndpoint(${ep.id})">删除</button></td></tr>`).join('')
      || emptyRow(6, '暂无集成端点');
    const deliveryRows = (d.deliveries || []).map((dl) => `
      <tr><td><b>${esc(dl.event_type)}</b><div class="tiny">${esc(dl.endpoint_code)}</div></td>
        <td><span class="tag ${dl.status === 'SUCCESS' ? 't-grn' : dl.status === 'FAILED' ? 't-red' : 't-yel'}">
          ${esc(dl.status_label)}</span></td>
        <td>${dl.attempts}</td>
        <td class="tiny">${dtShort(dl.created_at)}</td>
        <td class="tiny" style="max-width:260px">${dl.error ? esc(dl.error) : '—'}</td>
        <td>${dl.status === 'SUCCESS' ? ''
          : `<button class="btn-sm" onclick="retryDelivery(${dl.id})">重试</button>`}</td></tr>`).join('')
      || emptyRow(6, '暂无投递记录');
    const integrationsPane = !canManage()
      ? '<div class="card"><div class="empty">需要流程管理科或管理员权限</div></div>'
      : `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">集成端点</h3>
            <div class="desc" style="margin:2px 0 0">业务事件写入 Outbox，由「运行待发送」统一投递；
              配置 secret 后带 HMAC-SHA256 签名</div></div>
          <div class="gap">
            <button class="btn-sm" onclick="runDeliveries()">运行待发送</button>
            <button class="btn-sm" onclick="editEndpointModal(null)">+ 新建端点</button>
          </div>
        </div>
        <table class="tbl">
          <thead><tr><th>端点</th><th>名称 / 类型</th><th>订阅事件</th><th>签名</th>
            <th>状态</th><th></th></tr></thead>
          <tbody>${endpointRows}</tbody>
        </table>
      </div>
      <div class="card">
        <h3>投递记录</h3>
        <div class="desc">失败最多重试 3 次；可手动重试。接收方应校验 X-Logix-Signature</div>
        <table class="tbl">
          <thead><tr><th>事件</th><th>状态</th><th>尝试</th><th>创建时间</th>
            <th>错误</th><th></th></tr></thead>
          <tbody>${deliveryRows}</tbody>
        </table>
      </div>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>流程执行</h2>
            <div class="desc">运行已建模流程的实例 · 认领任务 · 推进到下一节点；改善项目进度在「流程项目组合」维护</div></div>
          <div class="gap">
            <button class="btn btn-p" id="execStartBtn"
              onclick="startInstanceModal()"${canWrite() ? '' : ' disabled'}>+ 启动流程</button>
          </div>
        </div>
        <div class="mt">${tabs}</div>
      </div>
      ${ex.tab === 'instances' ? instancePane : ex.tab === 'config' ? configPane : ex.tab === 'integrations' ? integrationsPane : taskPane}`;
    });
};

function setExecutionTab(tab) {
  state.execution.tab = tab;
  RENDERERS.execution();
}

function setExecutionFilter(filter) {
  state.execution.filter = filter;
  state.execution.tab = 'tasks';
  RENDERERS.execution();
}

function setExecutionConfigProcess(processId) {
  state.execution.configProcess = Number(processId);
  state.execution.tab = 'config';
  RENDERERS.execution();
}

/* -------------------------------------------------- ERP / OA 集成 */

function editEndpointModal(endpointId) {
  const endpoints = state.executionEndpoints || [];
  const ep = endpointId ? endpoints.find((e) => e.id === endpointId) : null;
  const kinds = ['WEBHOOK', 'ERP', 'OA'].map((kind) =>
    `<option value="${kind}"${ep && ep.kind === kind ? ' selected' : ''}>${kind}</option>`).join('');
  openModal(ep ? '编辑集成端点 · ' + ep.code : '新建集成端点', `
    <div class="row2">
      <div class="field"><label>编码 *</label>
        <input id="ieCode" value="${esc(ep ? ep.code : '')}"${ep ? ' readonly' : ''}
          placeholder="ERP-PROD"></div>
      <div class="field"><label>名称 *</label>
        <input id="ieName" value="${esc(ep ? ep.name : '')}" placeholder="ERP 生产事件接收"></div>
    </div>
    <div class="row2">
      <div class="field"><label>类型</label><select id="ieKind">${kinds}</select></div>
      <div class="field"><label>状态</label>
        <select id="ieActive">
          <option value="true"${!ep || ep.is_active ? ' selected' : ''}>启用</option>
          <option value="false"${ep && !ep.is_active ? ' selected' : ''}>停用</option>
        </select></div>
    </div>
    <div class="field"><label>Webhook URL *</label>
      <input id="ieUrl" value="${esc(ep ? ep.url : '')}"
        placeholder="https://erp.example.com/hooks/logix"></div>
    <div class="field"><label>签名密钥</label>
      <input id="ieSecret" placeholder="${
        ep && ep.has_secret ? '已配置，留空保持原值' : '留空表示不签名'
      }"><div class="hint">配置后请求头带 X-Logix-Signature: sha256=...</div></div>
    <div class="field"><label>订阅事件</label>
      <input id="ieEvents" value="${esc((ep ? ep.events : []).join(', '))}"
        placeholder="instance.started, task.completed；留空=全部">
      <div class="hint">可用：instance.started / task.created / task.assigned / task.claimed /
        task.completed / instance.completed / instance.cancelled / exception.created /
        exception.updated / *</div></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitEndpoint(${ep ? ep.id : 'null'})">保存</button>`);
}

async function submitEndpoint(endpointId) {
  const code = document.getElementById('ieCode').value.trim();
  const name = document.getElementById('ieName').value.trim();
  const url = document.getElementById('ieUrl').value.trim();
  const events = document.getElementById('ieEvents').value
    .split(',').map((item) => item.trim()).filter(Boolean);
  const payload = {
    name,
    kind: document.getElementById('ieKind').value,
    url,
    events,
    is_active: document.getElementById('ieActive').value === 'true',
  };
  const secret = document.getElementById('ieSecret').value.trim();
  if (secret) payload.secret = secret;
  if (!name || !url) return toast('名称和 URL 必填', true);
  try {
    if (endpointId) {
      await PATCH('/integrations/endpoints/' + endpointId, payload);
    } else {
      if (!code) return toast('编码必填', true);
      await POST('/integrations/endpoints', { ...payload, code });
    }
    closeModal();
    toast('集成端点已保存');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteEndpoint(endpointId) {
  if (!confirm('确定删除这个集成端点？其投递记录会一并删除。')) return;
  try {
    await DEL('/integrations/endpoints/' + endpointId);
    toast('集成端点已删除');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function runDeliveries() {
  try {
    const result = await POST('/integrations/deliveries/run', {});
    toast(result.processed
      ? `投递完成：成功 ${result.delivered}，失败 ${result.failed}，待发送 ${result.pending}`
      : '没有待发送的投递');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function retryDelivery(deliveryId) {
  try {
    await POST('/integrations/deliveries/' + deliveryId + '/retry', {});
    toast('已加入重试队列');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 表单定义 */

function editFormModal(formId) {
  const forms = state.executionForms || [];
  const form = formId ? forms.find((f) => f.id === formId) : null;
  const fields = form ? form.fields : [
    { key: 'approved', label: '是否通过', type: 'select', required: true, options: ['是', '否'] },
  ];
  openModal(form ? '编辑表单 · ' + form.name : '新建表单', `
    <div class="row2">
      <div class="field"><label>节点 key</label>
        <input id="efNode" value="${esc(form ? form.node_key : '')}"
          placeholder="如 n1；留空表示流程默认表单"${form ? ' readonly' : ''}></div>
      <div class="field"><label>表单名称 *</label>
        <input id="efName" value="${esc(form ? form.name : '')}" placeholder="如：需求审批"></div>
    </div>
    <div class="field"><label>字段定义（JSON）*</label>
      <textarea id="efFields" style="min-height:220px">${esc(JSON.stringify(fields, null, 2))}</textarea>
      <div class="hint">type 支持 text / textarea / number / date / select / checkbox；
        select 必须提供 options</div></div>
    <div class="field"><label>状态</label>
      <select id="efActive">
        <option value="true"${!form || form.is_active ? ' selected' : ''}>启用</option>
        <option value="false"${form && !form.is_active ? ' selected' : ''}>停用</option>
      </select></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitForm(${form ? form.id : 'null'})">保存</button>`);
}

async function submitForm(formId) {
  const nodeKey = document.getElementById('efNode').value.trim();
  const name = document.getElementById('efName').value.trim();
  if (!name) return toast('请填写表单名称', true);
  let fields;
  try { fields = JSON.parse(document.getElementById('efFields').value); } catch (e) {
    return toast('字段定义不是合法 JSON', true);
  }
  if (!Array.isArray(fields)) return toast('字段定义必须是数组', true);
  const active = document.getElementById('efActive').value === 'true';
  try {
    if (formId) {
      await PATCH('/execution/forms/' + formId, { name, fields, is_active: active });
    } else {
      await POST('/execution/forms', {
        process_id: state.execution.configProcess,
        node_key: nodeKey,
        name,
        fields,
        is_active: active,
      });
    }
    closeModal();
    toast('表单已保存');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteForm(formId) {
  if (!confirm('确定删除这个表单定义？已启动实例使用快照，不受影响。')) return;
  try {
    await DEL('/execution/forms/' + formId);
    toast('表单已删除');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 分支规则 */

function editRuleModal(ruleId) {
  const rules = state.executionRules || [];
  const rule = ruleId ? rules.find((r) => r.id === ruleId) : null;
  const conditions = rule ? rule.conditions : [{ field: 'approved', op: 'eq', value: '是' }];
  openModal(rule ? '编辑规则 · ' + rule.name : '新建分支规则', `
    <div class="row2">
      <div class="field"><label>节点 key *</label>
        <input id="erNode" value="${esc(rule ? rule.node_key : 'n4')}"${rule ? ' readonly' : ''}></div>
      <div class="field"><label>规则名称 *</label>
        <input id="erName" value="${esc(rule ? rule.name : '')}" placeholder="如：审批通过 → 采购计划"></div>
    </div>
    <div class="field"><label>条件（JSON 数组）</label>
      <textarea id="erConditions" style="min-height:150px">${esc(JSON.stringify(conditions, null, 2))}</textarea>
      <div class="hint">全部条件满足才命中；空数组表示兜底。op 支持
        eq/ne/gt/gte/lt/lte/in/contains/truthy/falsy</div></div>
    <div class="row3">
      <div class="field"><label>目标节点 *</label>
        <input id="erTarget" value="${esc(rule ? rule.target_node_key : '')}" placeholder="n5"></div>
      <div class="field"><label>优先级</label>
        <input id="erPriority" type="number" value="${rule ? rule.priority : 100}"></div>
      <div class="field"><label>状态</label>
        <select id="erActive">
          <option value="true"${!rule || rule.is_active ? ' selected' : ''}>启用</option>
          <option value="false"${rule && !rule.is_active ? ' selected' : ''}>停用</option>
        </select></div>
    </div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitRule(${rule ? rule.id : 'null'})">保存</button>`);
}

async function submitRule(ruleId) {
  const nodeKey = document.getElementById('erNode').value.trim();
  const name = document.getElementById('erName').value.trim();
  const target = document.getElementById('erTarget').value.trim();
  const priority = Number(document.getElementById('erPriority').value || 100);
  const active = document.getElementById('erActive').value === 'true';
  if (!nodeKey || !name || !target) return toast('节点、名称、目标节点都必填', true);
  let conditions;
  try { conditions = JSON.parse(document.getElementById('erConditions').value || '[]'); } catch (e) {
    return toast('条件不是合法 JSON', true);
  }
  if (!Array.isArray(conditions)) return toast('条件必须是数组', true);
  try {
    if (ruleId) {
      await PATCH('/execution/rules/' + ruleId, {
        name, conditions, target_node_key: target, priority, is_active: active,
      });
    } else {
      await POST('/execution/rules', {
        process_id: state.execution.configProcess,
        node_key: nodeKey,
        name,
        conditions,
        target_node_key: target,
        priority,
        is_active: active,
      });
    }
    closeModal();
    toast('规则已保存');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteRule(ruleId) {
  if (!confirm('确定删除这条分支规则？已启动实例使用快照，不受影响。')) return;
  try {
    await DEL('/execution/rules/' + ruleId);
    toast('规则已删除');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
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

function renderFormFields(fields) {
  return (fields || []).map((f) => {
    const id = 'exf_' + f.key;
    const required = f.required ? ' *' : '';
    const placeholder = f.placeholder ? ` placeholder="${esc(f.placeholder)}"` : '';
    let input;
    if (f.type === 'textarea') {
      input = `<textarea id="${id}" data-form-key="${esc(f.key)}"
        data-form-type="textarea"${placeholder}></textarea>`;
    } else if (f.type === 'select') {
      input = `<select id="${id}" data-form-key="${esc(f.key)}" data-form-type="select">${
        (f.options || []).map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join('')}</select>`;
    } else if (f.type === 'checkbox') {
      input = `<input id="${id}" type="checkbox" data-form-key="${esc(f.key)}"
        data-form-type="checkbox">`;
    } else {
      const type = f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text';
      input = `<input id="${id}" type="${type}" data-form-key="${esc(f.key)}"
        data-form-type="${esc(f.type)}"${placeholder}>`;
    }
    return `<div class="field"><label>${esc(f.label)}${required}</label>${input}</div>`;
  }).join('');
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
          <div class="hint">该节点有多个分支；有匹配规则时会自动选择，这里可以显式覆盖</div></div>` : ''}
      ${(task.form_schema && task.form_schema.length)
        ? '<div class="note">表单：' + esc(task.form_name || task.name) + '</div>' +
          renderFormFields(task.form_schema)
        : `<div class="field"><label>表单数据（JSON，可选）</label>
            <textarea id="exForm" placeholder='{"审批意见":"同意","金额":10000}'>{}</textarea></div>`}
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
  const dynamic = Array.from(document.querySelectorAll('[data-form-key]'));
  let formData = null;
  if (dynamic.length) {
    formData = {};
    dynamic.forEach((el) => {
      const key = el.dataset.formKey;
      const type = el.dataset.formType;
      if (type === 'checkbox') formData[key] = el.checked;
      else if (type === 'number') formData[key] = el.value === '' ? null : Number(el.value);
      else formData[key] = el.value;
    });
  } else {
    const raw = document.getElementById('exForm')
      ? document.getElementById('exForm').value.trim() : '';
    if (raw) {
      try { formData = JSON.parse(raw); } catch (e) {
        return toast('表单数据不是合法 JSON', true);
      }
    }
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
  renderExecution, cancelInstance, claimTask, completeTask, deleteEndpoint, deleteForm,
  deleteRule, editEndpointModal, editFormModal, editRuleModal, openInstance, openTask,
  retryDelivery, runDeliveries, setExecutionConfigProcess, setExecutionFilter,
  setExecutionTab, startInstanceModal, submitEndpoint, submitForm, submitRule,
  submitStartInstance,
};
