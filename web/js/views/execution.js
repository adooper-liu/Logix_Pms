/* 视图：execution —— 流程实例与任务队列 */
import { esc, dtShort, emptyRow, skeleton, tipHelp } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, confirmDialog, promptDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { GET, POST, PATCH, PUT, DEL } from '../core/api.js';

/* ============================================================ 9. 流程执行 */

on('execution.tab', ({ tab }) => setExecutionTab(tab));
on('execution.filter', ({ filter }) => setExecutionFilter(filter));
on('execution.openTask', ({ id }) => openTask(Number(id)));
on('execution.claimTask', ({ id }) => claimTask(Number(id)));
on('execution.openInstance', ({ id }) => openInstance(Number(id)));
on('execution.openAssignment', ({ node }) => openAssignmentModal(node));
on('execution.saveConfig', () => saveExecutionConfig());
on('execution.runEscalation', () => runEscalationScan());
on('execution.configProcess', (_data, el) => setExecutionConfigProcess(el.value));
on('execution.editForm', ({ id }) => editFormModal(id ? Number(id) : null));
on('execution.deleteForm', ({ id }) => deleteForm(Number(id)));
on('execution.editRule', ({ id }) => editRuleModal(id ? Number(id) : null));
on('execution.deleteRule', ({ id }) => deleteRule(Number(id)));
on('execution.editEndpoint', ({ id }) => editEndpointModal(id ? Number(id) : null));
on('execution.deleteEndpoint', ({ id }) => deleteEndpoint(Number(id)));
on('execution.retryDelivery', ({ id }) => retryDelivery(Number(id)));
on('execution.runDeliveries', () => runDeliveries());
on('execution.editInboundHook', ({ id }) => editInboundHookModal(id ? Number(id) : null));
on('execution.deleteInboundHook', ({ id }) => deleteInboundHook(Number(id)));
on('execution.close', () => closeModal());
on('execution.submitAssignment', ({ node }) => submitAssignment(node));
on('execution.submitEndpoint', ({ id }) => submitEndpoint(id ? Number(id) : null));
on('execution.submitInboundHook', ({ id }) => submitInboundHook(id ? Number(id) : null));
on('execution.submitForm', ({ id }) => submitForm(id ? Number(id) : null));
on('execution.submitRule', ({ id }) => submitRule(id ? Number(id) : null));
on('execution.startModal', () => startInstanceModal());
on('execution.loadStartNodes', (_data, el) => loadStartNodes(el.value));
on('execution.submitStart', () => submitStartInstance());
on('execution.branchMode', () => toggleBranchMode());
on('execution.openWorklog', ({ id }) => openWorklogModal(Number(id)));
on('execution.completeTask', ({ id }) => completeTask(Number(id)));
on('execution.submitWorklog', ({ id }) => submitWorklog(Number(id)));
on('execution.suspend', ({ id }) => suspendInstance(Number(id)));
on('execution.resume', ({ id }) => resumeInstance(Number(id)));
on('execution.cancel', ({ id }) => cancelInstance(Number(id)));
on('execution.completeCompensation', ({ id }) => completeCompensation(Number(id)));
on('execution.archiveInstances', () => archiveInstances());
on('execution.goProjects', () => go('projects'));

let manualBranchTask = null;

const renderExecution = () => {
  const ex = state.execution || (state.execution = { tab: 'tasks', filter: 'open' });
  const params = urlParams();
  if (params.process) {
    ex.configProcess = Number(params.process);
    ex.tab = params.tab || 'config';
  } else if (params.tab) {
    ex.tab = params.tab;
  }
  // 从模型发布跳过来时带 start=1：先落到配置页，再自动拉起启动流程弹窗
  if (params.start) {
    ex.tab = 'config';
    ex.startProcess = Number(params.process) || 0;
  } else {
    ex.startProcess = null;
  }
  return renderAsync('execution',
    () => Promise.all([
      GET('/execution/tasks?only_open=true&limit=500'),
      GET('/execution/instances?limit=200'),
      GET('/execution/processes'),
    ]).then(async ([tasks, instances, processes]) => {
      let forms = [];
      let rules = [];
      let config = null;
      let assignments = [];
      let orgs = [];
      let roleMeta = null;
      let assignees = [];
      let endpoints = [];
      let deliveries = [];
      let inboundHooks = [];
      let inboundActions = [];
      if (ex.tab === 'config' && processes.length) {
        const pid = ex.configProcess || processes[0].id;
        ex.configProcess = pid;
        [forms, rules, config, assignments, orgs, roleMeta, assignees] = await Promise.all([
          GET('/execution/forms?process_id=' + pid),
          GET('/execution/rules?process_id=' + pid),
          GET('/execution/config?process_id=' + pid),
          GET('/execution/assignments?process_id=' + pid),
          GET('/org-units'),
          GET('/auth/meta'),
          GET('/execution/assignees'),
        ]);
      }
      if (ex.tab === 'integrations') {
        [endpoints, deliveries, inboundHooks, inboundActions, assignees] = await Promise.all([
          GET('/integrations/endpoints'),
          GET('/integrations/deliveries?limit=100'),
          GET('/integrations/inbound-hooks'),
          GET('/integrations/inbound-actions'),
          GET('/execution/assignees'),
        ]);
      }
      return {
        tasks, instances, processes, forms, rules, config, assignments, orgs, roleMeta,
        assignees, endpoints, deliveries, inboundHooks, inboundActions,
      };
    }),
    (d) => {
      state.executionTasks = d.tasks;
      state.executionInstances = d.instances;
      state.executionProcesses = d.processes;
      state.executionForms = d.forms;
      state.executionRules = d.rules;
      state.executionConfig = d.config;
      state.executionAssignments = d.assignments;
      state.executionOrgs = d.orgs;
      state.executionRoleMeta = d.roleMeta;
      state.executionAssignees = d.assignees.length ? d.assignees : state.executionAssignees;
      state.executionEndpoints = d.endpoints;
      state.executionDeliveries = d.deliveries;
      state.executionInboundHooks = d.inboundHooks;
      state.executionInboundActions = d.inboundActions;

    const me = AUTH.user ? AUTH.user.id : null;
    const mine = d.tasks.filter((t) => t.assignee_user_id === me);
    const queue = d.tasks.filter((t) => t.assignee_user_id === null);
    const running = d.instances.filter((i) => i.status === 'RUNNING');
    const filter = ex.filter || 'open';
    const shown = filter === 'mine' ? mine : filter === 'queue' ? queue : d.tasks;

    const taskRows = shown.map((t) => {
      const suspended = t.instance_status === 'SUSPENDED';
      const canAct = !suspended && canWrite()
        && (t.assignee_user_id === null || t.assignee_user_id === me || canManage());
      const overdue = t.due_at && new Date(t.due_at).getTime() < Date.now();
      const action = suspended
        ? '<span class="tag t-yel">实例挂起</span>'
        : !canWrite()
          ? `<button class="btn-sm" data-act="execution.openTask" data-id="${t.id}">查看</button>`
          : t.assignee_user_id === null
            ? `<button class="btn-sm btn-p" data-act="execution.claimTask" data-id="${t.id}">认领</button>`
            : canAct
              ? `<button class="btn-sm" data-act="execution.openTask" data-id="${t.id}">处理</button>`
              : `<button class="btn-sm" data-act="execution.openTask" data-id="${t.id}">查看</button>`;
      return `
        <tr class="exec-task-row" data-task-id="${t.id}" data-instance-id="${t.instance_id}">
          <td><b>${esc(t.name)}</b>
            <div class="tiny">${esc(t.node_key)} · ${esc(t.task_type_label)} ·
              ${esc(t.instance_code)}</div></td>
          <td>${esc(t.process_name)}<div class="tiny">${esc(t.lane || '—')}</div></td>
          <td>${esc(t.candidate_role || '—')}</td>
          <td>${t.assignee_name ? esc(t.assignee_name) : '<span class="muted">公共队列</span>'}</td>
          <td><span class="tag ${t.status === 'PENDING' ? 't-yel' : 't-blu'}">${esc(t.status_label)}</span></td>
          <td class="tiny">${dtShort(t.created_at)}
            ${t.due_at ? `<div>${overdue ? '<span class="tag t-red">已超期</span> ' : '到期 '}${dtShort(t.due_at)}</div>` : ''}
            ${t.escalated_at ? `<div><span class="tag t-blu">已升级</span> ${dtShort(t.escalated_at)}</div>` : ''}</td>
          <td>${action}</td>
        </tr>`;
    }).join('') || emptyRow(7, filter === 'mine'
      ? '当前没有指派给你的任务'
      : filter === 'queue' ? '公共队列为空' : '没有待办任务');

    const instanceRows = d.instances.map((i) => `
      <tr class="exec-instance-row" data-instance-id="${i.id}">
        <td><button class="project-open" type="button" data-act="execution.openInstance"
            data-id="${i.id}"><b>${esc(i.code)}</b></button>
          <div class="tiny">${esc(i.process_name)}</div></td>
        <td><span class="tag ${i.status === 'RUNNING' ? 't-blu'
          : i.status === 'COMPLETED' ? 't-grn'
          : i.status === 'SUSPENDED' ? 't-yel' : 't-gry'}">
          ${esc(i.status_label)}</span></td>
        <td>${i.current_node_name ? esc(i.current_node_name) : '—'}
          <div class="tiny">${esc(i.current_node_key || '')}</div></td>
        <td>${i.open_task_count}</td>
        <td class="tiny">${esc(i.started_by_name || '—')}<div>${dtShort(i.started_at)}</div></td>
        <td><button class="btn-sm" data-act="execution.openInstance"
          data-id="${i.id}">详情</button></td>
      </tr>`).join('') || emptyRow(6, '还没有流程实例');

    const tabs = `
      <div class="seg">
        <button class="${ex.tab === 'tasks' ? 'on' : ''}" data-act="execution.tab" data-tab="tasks">待办任务</button>
        <button class="${ex.tab === 'instances' ? 'on' : ''}" data-act="execution.tab" data-tab="instances">流程实例</button>
        ${canManage() ? `<button class="${ex.tab === 'config' ? 'on' : ''}"
          data-act="execution.tab" data-tab="config">表单与规则</button>
          <button class="${ex.tab === 'integrations' ? 'on' : ''}"
          data-act="execution.tab" data-tab="integrations">集成</button>` : ''}
      </div>`;

    const taskPane = `
      <div class="grid g4 stat-row">
        <button class="kpi stat" data-act="execution.filter" data-filter="mine">
          <div class="num">${mine.length}</div><div class="lab">我的待办</div></button>
        <button class="kpi stat" data-act="execution.filter" data-filter="queue">
          <div class="num">${queue.length}</div><div class="lab">公共队列</div></button>
        <button class="kpi stat" data-act="execution.filter" data-filter="open">
          <div class="num">${d.tasks.length}</div><div class="lab">全部待办</div></button>
        <div class="kpi stat"><div class="num">${running.length}</div><div class="lab">运行中实例</div></div>
      </div>
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">任务队列</h3>
            <div class="desc" style="margin:2px 0 0">认领后即可处理；分支节点在完成时选择下一步</div></div>
          <div class="seg">
            <button class="${filter === 'open' ? 'on' : ''}" data-act="execution.filter" data-filter="open">全部待办</button>
            <button class="${filter === 'mine' ? 'on' : ''}" data-act="execution.filter" data-filter="mine">我的</button>
            <button class="${filter === 'queue' ? 'on' : ''}" data-act="execution.filter" data-filter="queue">公共队列</button>
          </div>
        </div>
        <table class="tbl">
          <thead><tr><th>任务</th><th>流程</th><th>候选角色</th><th>处理人</th>
            <th>状态</th><th>创建 / 时限</th><th></th></tr></thead>
          <tbody>${taskRows}</tbody>
        </table>
      </div>`;

    const instancePane = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">流程实例</h3>
            <div class="desc" style="margin:2px 0 0">共 ${d.instances.length} 个实例；点击查看任务时间线</div></div>
          ${canManage() ? `<button class="btn-sm" data-act="execution.archiveInstances">
            归档旧实例</button>` : ''}
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
        <td><button class="btn-sm" data-act="execution.editForm" data-id="${f.id}">编辑</button>
          <button class="btn-sm" data-act="execution.deleteForm" data-id="${f.id}">删除</button></td></tr>`).join('')
      || emptyRow(5, '暂无表单定义');
    const ruleRows = (d.rules || []).map((r) => {
      const cond = (r.conditions || [])
        .map((c) => `${c.field} ${c.op} ${c.value}`).join(' 且 ') || '无条件（兜底）';
      return `<tr><td><b>${esc(r.node_key)}</b></td>
        <td>${esc(r.name)}<div class="tiny">${esc(cond)}</div></td>
        <td>${esc(r.target_node_key)}</td><td>${r.priority}</td>
        <td><button class="btn-sm" data-act="execution.editRule" data-id="${r.id}">编辑</button>
          <button class="btn-sm" data-act="execution.deleteRule" data-id="${r.id}">删除</button></td></tr>`;
    }).join('') || emptyRow(5, '暂无分支规则');

    const assignmentRows = (d.assignments || []).map((n) => `
      <tr>
        <td><b>${esc(n.node_key)}</b><div class="tiny">${esc(n.name)} · ${esc(n.node_type)}</div></td>
        <td>${esc(n.lane || '—')}<div class="tiny">${esc(n.owner_role || '')}</div></td>
        <td>${n.role_label ? '<span class="tag t-blu">' + esc(n.role_label) + '</span>' : '—'}</td>
        <td>${esc(n.org_unit_name || '—')}</td>
        <td>${esc(n.default_assignee_name || '公共队列')}</td>
        <td>${n.due_hours !== null && n.due_hours !== undefined
          ? n.due_hours + ' 小时' : '跟随流程'}</td>
        <td class="tiny">${n.escalation_hours !== null && n.escalation_hours !== undefined
          ? n.escalation_hours + ' 小时 → ' + esc(n.escalation_user_name || '未设处理人')
          : '跟随流程'}</td>
        <td><button class="btn-sm" data-act="execution.openAssignment"
          data-node="${esc(n.node_key)}">配置</button></td>
      </tr>`).join('') || emptyRow(8, '该流程还没有节点');

    const escUserOpts = (d.assignees || []).map((u) =>
      `<option value="${u.id}"${d.config && d.config.default_escalation_user_id === u.id
        ? ' selected' : ''}>${esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`
    ).join('');

    const configPane = !canManage()
      ? '<div class="card"><div class="empty">需要流程管理科或管理员权限</div></div>'
      : `
      <div class="card">
        <div class="between">
          <div><h3 style="margin:0">任务时限与升级</h3>
            <div class="desc" style="margin:2px 0 0">新任务按小时数生成到期时间；到期后再过
              升级时限，自动改派给升级处理人</div></div>
          <div class="gap">
            <input class="sel" id="exDueHours" type="number" min="0" max="8760"
              style="width:110px" placeholder="时限（小时）"
              value="${d.config && d.config.default_task_due_hours !== null
                ? d.config.default_task_due_hours : ''}">
            <input class="sel" id="exEscHours" type="number" min="0" max="8760"
              style="width:110px" placeholder="升级（小时）"
              value="${d.config && d.config.default_escalation_hours !== null
                ? d.config.default_escalation_hours : ''}">
            <select class="sel" id="exEscUser">
              <option value="">不自动升级</option>${escUserOpts}</select>
            <button class="btn-sm btn-p" data-act="execution.saveConfig">保存</button>
          </div>
        </div>
        <div class="between mt">
          <div class="tiny">扫描会按实例启动时的快照执行；生产环境可用 cron 调用同接口或
            <code>scripts/run_escalations.py</code></div>
          <button class="btn-sm" data-act="execution.runEscalation">运行升级扫描</button>
        </div>
      </div>
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">节点分派</h3>
            <div class="desc" style="margin:2px 0 0">角色/组织作为候选范围；默认处理人优先直接指派；
              节点时限与升级覆盖流程默认</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>节点</th><th>泳道 / Owner</th><th>候选角色</th><th>组织</th>
            <th>默认处理人</th><th>时限</th><th>升级</th><th></th></tr></thead>
          <tbody>${assignmentRows}</tbody>
        </table>
      </div>
      <div class="card" id="execution-evidence">
        <div class="between mb">
          <div><h3 style="margin:0">表单与规则</h3>
            <div class="desc" style="margin:2px 0 0">表单随实例启动冻结；规则按优先级匹配，显式下一步优先</div></div>
          <select class="sel" data-act="execution.configProcess">
            ${d.processes.map((p) => `<option value="${p.id}"${
              cfgProcess && p.id === cfgProcess.id ? ' selected' : ''}>L${p.level} ${esc(p.code)} ${esc(p.name)}</option>`).join('')}
          </select>
        </div>
        <div class="grid g2" style="align-items:start">
          <div>
            <div class="between mb"><h3 style="margin:0">表单定义</h3>
              <button class="btn-sm" data-act="execution.editForm">+ 新建表单</button></div>
            <table class="tbl">
              <thead><tr><th>节点</th><th>名称</th><th>字段</th><th>状态</th><th></th></tr></thead>
              <tbody>${formRows}</tbody>
            </table>
          </div>
          <div>
            <div class="between mb"><h3 style="margin:0">分支规则</h3>
              <button class="btn-sm" data-act="execution.editRule">+ 新建规则</button></div>
            <table class="tbl">
              <thead><tr><th>节点</th><th>规则</th><th>目标</th><th>优先级</th><th></th></tr></thead>
              <tbody>${ruleRows}</tbody>
            </table>
          </div>
        </div>
      </div>`;

    const inboundRows = (d.inboundHooks || []).map((h) => `
      <tr><td><b>${esc(h.code)}</b><div class="tiny">${esc(h.name)}</div></td>
        <td>${h.process_code
          ? esc(h.process_code) + ' · ' + esc(h.process_name)
          : '<span class="muted">全部流程</span>'}</td>
        <td>${esc(h.run_as_user_name || '—')}</td>
        <td class="tiny">${(h.action_labels || []).length
          ? esc(h.action_labels.join('、')) : '—'}</td>
        <td>${h.is_active ? '<span class="tag t-grn">启用</span>'
          : '<span class="tag t-gry">停用</span>'}</td>
        <td class="tiny">${h.last_received_at ? dtShort(h.last_received_at) : '—'}</td>
        <td><button class="btn-sm" data-act="execution.editInboundHook" data-id="${h.id}">编辑</button>
          <button class="btn-sm" data-act="execution.deleteInboundHook" data-id="${h.id}">删除</button></td></tr>`).join('')
      || emptyRow(7, '暂无入站 Webhook');

    const endpointRows = (d.endpoints || []).map((ep) => `
      <tr><td><b>${esc(ep.code)}</b><div class="tiny">${esc(ep.url)}</div></td>
        <td>${esc(ep.name)}<div class="tiny">${esc(ep.kind)}</div></td>
        <td class="tiny">${(ep.events || []).length ? esc(ep.events.join('、')) : '全部事件'}</td>
        <td>${ep.has_secret ? '<span class="tag t-blu">已签名</span>' : '<span class="muted">无签名</span>'}</td>
        <td>${ep.is_active ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
        <td><button class="btn-sm" data-act="execution.editEndpoint" data-id="${ep.id}">编辑</button>
          <button class="btn-sm" data-act="execution.deleteEndpoint" data-id="${ep.id}">删除</button></td></tr>`).join('')
      || emptyRow(6, '暂无集成端点');
    const deliveryRows = (d.deliveries || []).map((dl) => `
      <tr><td><b>${esc(dl.event_type)}</b><div class="tiny">${esc(dl.endpoint_code)}</div></td>
        <td><span class="tag ${dl.status === 'SUCCESS' ? 't-grn' : dl.status === 'FAILED' ? 't-red' : 't-yel'}">
          ${esc(dl.status_label)}</span></td>
        <td>${dl.attempts}</td>
        <td class="tiny">${dtShort(dl.created_at)}</td>
        <td class="tiny" style="max-width:260px">${dl.error ? esc(dl.error) : '—'}</td>
        <td>${dl.status === 'SUCCESS' ? ''
          : `<button class="btn-sm" data-act="execution.retryDelivery" data-id="${dl.id}">重试</button>`}</td></tr>`).join('')
      || emptyRow(6, '暂无投递记录');
    const integrationsPane = !canManage()
      ? '<div class="card"><div class="empty">需要流程管理科或管理员权限</div></div>'
      : `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">入站 Webhook</h3>
            <div class="desc" style="margin:2px 0 0">ERP/OA 反向调用：HMAC-SHA256 签名 +
              event_id 幂等；密钥只在创建或轮换时显示一次</div></div>
          <button class="btn-sm" data-act="execution.editInboundHook">+ 新建入站</button>
        </div>
        <table class="tbl">
          <thead><tr><th>编码 / 名称</th><th>限定流程</th><th>服务账号</th>
            <th>允许动作</th><th>状态</th><th>最近接收</th><th></th></tr></thead>
          <tbody>${inboundRows}</tbody>
        </table>
      </div>
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">集成端点</h3>
            <div class="desc" style="margin:2px 0 0">业务事件写入 Outbox，由「运行待发送」统一投递；
              配置 secret 后带 HMAC-SHA256 签名</div></div>
          <div class="gap">
            <button class="btn-sm" data-act="execution.runDeliveries">运行待发送</button>
            <button class="btn-sm" data-act="execution.editEndpoint">+ 新建端点</button>
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
          <div><h2>流程执行<span class="module-badge">运行时 · 实例与任务</span></h2>
            <div class="desc">运行已建模流程的实例 · 认领任务 · 推进到下一节点；改善项目进度在「流程项目组合」维护</div></div>
          <div class="gap">
            <a class="link-btn" data-act="execution.goProjects">改善项目进度 →</a>
            <button class="btn btn-p" id="execStartBtn"
              data-act="execution.startModal"${canWrite() ? '' : ' disabled'}>+ 启动流程</button>
          </div>
        </div>
        <div class="mt">${tabs}</div>
      </div>
      ${ex.tab === 'instances' ? instancePane : ex.tab === 'config' ? configPane : ex.tab === 'integrations' ? integrationsPane : taskPane}`;

    if (params.focus === 'forms' && ex.tab === 'config') {
      const evidence = document.getElementById('execution-evidence');
      if (evidence) evidence.scrollIntoView({ block: 'start' });
    }

    // 发布后自动拉起启动弹窗；消费一次后把 start 参数从 URL 去掉，避免重渲染再弹一次
    if (ex.startProcess !== undefined && ex.startProcess !== null) {
      const startPid = ex.startProcess;
      ex.startProcess = null;
      setUrlState('execution', {
        process: startPid || '',
        tab: ex.tab,
      }, { push: false });
      startInstanceModal(startPid || null);
    }
    });
};

function setExecutionTab(tab) {
  state.execution.tab = tab;
  const params = { tab };
  if (tab === 'config' && state.execution.configProcess) {
    params.process = state.execution.configProcess;
  }
  setUrlState('execution', params, { push: false });
  RENDERERS.execution();
}

function setExecutionFilter(filter) {
  state.execution.filter = filter;
  state.execution.tab = 'tasks';
  setUrlState('execution', { tab: 'tasks' }, { push: false });
  RENDERERS.execution();
}

function setExecutionConfigProcess(processId) {
  const pid = Number(processId);
  state.execution.configProcess = pid;
  state.execution.tab = 'config';
  setUrlState('execution', { process: pid, tab: 'config' }, { push: true });
  RENDERERS.execution();
}

async function saveExecutionConfig() {
  const pid = state.execution.configProcess
    || (state.executionProcesses && state.executionProcesses[0]
      ? state.executionProcesses[0].id : null);
  if (!pid) return toast('请先选择流程', true);
  const raw = document.getElementById('exDueHours').value.trim();
  const value = raw === '' ? null : Number(raw);
  if (value !== null && (!Number.isFinite(value) || value < 0 || value > 8760)) {
    return toast('任务时限应为 0–8760 小时', true);
  }
  const escRaw = document.getElementById('exEscHours').value.trim();
  const escValue = escRaw === '' ? null : Number(escRaw);
  if (escValue !== null && (!Number.isFinite(escValue) || escValue < 0 || escValue > 8760)) {
    return toast('升级时限应为 0–8760 小时', true);
  }
  const escUser = document.getElementById('exEscUser').value;
  try {
    await PUT('/execution/config?process_id=' + pid, {
      default_task_due_hours: value,
      default_escalation_hours: escValue,
      default_escalation_user_id: escUser ? Number(escUser) : null,
    });
    toast('任务时限与升级配置已保存');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function runEscalationScan() {
  const pid = state.execution.configProcess
    || (state.executionProcesses && state.executionProcesses[0]
      ? state.executionProcesses[0].id : null);
  if (!pid) return toast('请先选择流程', true);
  try {
    const result = await POST('/execution/escalations/scan?process_id=' + pid, {});
    toast(result.escalated
      ? `已升级 ${result.escalated} 个任务（扫描 ${result.scanned}）`
      : `没有需要升级的任务（扫描 ${result.scanned}）`);
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

function openAssignmentModal(nodeKey) {
  const nodes = state.executionAssignments || [];
  const node = nodes.find((n) => n.node_key === nodeKey);
  if (!node) return toast('节点不存在', true);
  const roles = ((state.executionRoleMeta || {}).roles || []).map((r) =>
    `<option value="${esc(r.value)}"${node.role === r.value ? ' selected' : ''}>${esc(r.label)}</option>`
  ).join('');
  const orgs = (state.executionOrgs || []).map((o) =>
    `<option value="${o.id}"${node.org_unit_id === o.id ? ' selected' : ''}>${esc(o.name)}${
      o.type_label ? ' · ' + esc(o.type_label) : ''}</option>`
  ).join('');
  const users = (state.executionAssignees || []).map((u) =>
    `<option value="${u.id}"${node.default_assignee_user_id === u.id ? ' selected' : ''}>${
      esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`
  ).join('');
  const escUsers = (state.executionAssignees || []).map((u) =>
    `<option value="${u.id}"${node.escalation_user_id === u.id ? ' selected' : ''}>${
      esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`
  ).join('');
  openModal('节点分派 · ' + node.node_key, `
    <div class="note mb">节点：<b>${esc(node.name)}</b> · ${esc(node.node_type)}
      ${node.lane ? ' · 泳道 ' + esc(node.lane) : ''}</div>
    <div class="field"><label>候选角色</label>
      <select id="naRole"><option value="">不限角色</option>${roles}</select>
      <div class="hint">公共任务认领时，账号角色必须匹配； MANAGER+ 始终可处理</div></div>
    <div class="field"><label>限定组织</label>
      <select id="naOrg"><option value="">不限组织</option>${orgs}</select>
      <div class="hint">账号所属组织须为该组织或其下级</div></div>
    <div class="field"><label>默认处理人</label>
      <select id="naUser"><option value="">进入公共队列</option>${users}</select>
      <div class="hint">优先直接指派；停用账号不会生效</div></div>
    <div class="field"><label>节点时限（小时）</label>
      <input id="naDue" type="number" min="0" max="8760" value="${
        node.due_hours === null || node.due_hours === undefined ? '' : node.due_hours}"
        placeholder="留空则跟随流程默认">
      <div class="hint">留空表示沿用「任务时限与升级」里的流程默认值</div></div>
    <div class="row2">
      <div class="field"><label>升级时限（小时）</label>
        <input id="naEscHours" type="number" min="0" max="8760" value="${
          node.escalation_hours === null || node.escalation_hours === undefined
            ? '' : node.escalation_hours}"
          placeholder="留空则跟随流程默认">
        <div class="hint">到期后再过多少小时升级；留空跟随流程</div></div>
      <div class="field"><label>升级处理人</label>
        <select id="naEscUser"><option value="">跟随流程</option>${escUsers}</select>
        <div class="hint">超期后自动改派给该账号</div></div>
    </div>`,
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitAssignment"
       data-node="${esc(node.node_key)}">保存</button>`);
}

async function submitAssignment(nodeKey) {
  const pid = state.execution.configProcess
    || (state.executionProcesses && state.executionProcesses[0]
      ? state.executionProcesses[0].id : null);
  if (!pid) return toast('请先选择流程', true);
  const rawDue = document.getElementById('naDue').value.trim();
  const due = rawDue === '' ? null : Number(rawDue);
  if (due !== null && (!Number.isFinite(due) || due < 0 || due > 8760)) {
    return toast('节点时限应为 0–8760 小时', true);
  }
  const rawEsc = document.getElementById('naEscHours').value.trim();
  const escHours = rawEsc === '' ? null : Number(rawEsc);
  if (escHours !== null
    && (!Number.isFinite(escHours) || escHours < 0 || escHours > 8760)) {
    return toast('升级时限应为 0–8760 小时', true);
  }
  const orgValue = document.getElementById('naOrg').value;
  const userValue = document.getElementById('naUser').value;
  const escUserValue = document.getElementById('naEscUser').value;
  try {
    await PUT('/execution/assignments', {
      process_id: pid,
      node_key: nodeKey,
      role: document.getElementById('naRole').value || null,
      org_unit_id: orgValue ? Number(orgValue) : null,
      default_assignee_user_id: userValue ? Number(userValue) : null,
      due_hours: due,
      escalation_hours: escHours,
      escalation_user_id: escUserValue ? Number(escUserValue) : null,
    });
    closeModal();
    toast('节点分派已保存');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

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
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitEndpoint"
       data-id="${ep ? ep.id : ''}">保存</button>`);
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
  const ok = await confirmDialog('确定删除这个集成端点？其投递记录会一并删除。',
    { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/integrations/endpoints/' + endpointId);
    toast('集成端点已删除');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

function editInboundHookModal(hookId) {
  const hooks = state.executionInboundHooks || [];
  const hook = hookId ? hooks.find((h) => h.id === hookId) : null;
  const processes = state.executionProcesses || [];
  const processOpts = processes.map((p) =>
    `<option value="${p.id}"${hook && hook.process_id === p.id ? ' selected' : ''}>${
      esc(p.code)} ${esc(p.name)}</option>`).join('');
  const users = (state.executionAssignees || []).filter(
    (u) => u.role === 'ADMIN' || u.role === 'MANAGER');
  const userOpts = users.map((u) =>
    `<option value="${u.id}"${hook && hook.run_as_user_id === u.id ? ' selected' : ''}>${
      esc(u.display_name)} · ${esc(u.role_label || u.role)}</option>`).join('');
  const actionDefs = state.executionInboundActions || [];
  const selected = hook ? (hook.actions || []) : actionDefs.map((a) => a.value);
  const actionBoxes = actionDefs.map((a) =>
    `<label class="tiny" style="display:flex;align-items:center;gap:6px">
      <input type="checkbox" class="ihAct" value="${esc(a.value)}"${
      selected.includes(a.value) ? ' checked' : ''}> ${esc(a.label)}</label>`).join('');
  openModal(hook ? '编辑入站 Webhook · ' + hook.code : '新建入站 Webhook', `
    <div class="row2">
      <div class="field"><label>编码 *</label>
        <input id="ihCode" value="${esc(hook ? hook.code : '')}"${hook ? ' readonly' : ''}
          placeholder="ERP-PROD"></div>
      <div class="field"><label>名称 *</label>
        <input id="ihName" value="${esc(hook ? hook.name : '')}" placeholder="ERP 生产入站"></div>
    </div>
    <div class="field"><label>限定流程</label>
      <select id="ihProcess"><option value="">全部流程</option>${processOpts}</select>
      <div class="hint">选择后只能操作该流程；限定流程时必须允许「启动流程」</div></div>
    <div class="field"><label>服务账号 *</label>
      <select id="ihUser"><option value="">请选择</option>${userOpts}</select>
      <div class="hint">入站操作以此账号身份执行，只能是流程管理科或系统管理员</div></div>
    <div class="field"><label>允许动作</label>
      <div class="gap">${actionBoxes || '<span class="muted">没有可用动作</span>'}</div></div>
    <div class="field"><label>状态</label>
      <select id="ihActive">
        <option value="true"${!hook || hook.is_active ? ' selected' : ''}>启用</option>
        <option value="false"${hook && !hook.is_active ? ' selected' : ''}>停用</option>
      </select></div>
    ${hook
      ? `<label class="tiny" style="display:flex;align-items:center;gap:6px">
          <input type="checkbox" id="ihRotate"> 轮换密钥（旧密钥立即失效）</label>`
      : '<div class="hint">保存后生成密钥，只显示这一次，请立即交给对接方。</div>'}`,
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitInboundHook"
       data-id="${hook ? hook.id : ''}">保存</button>`);
}

async function submitInboundHook(hookId) {
  const code = document.getElementById('ihCode').value.trim();
  const name = document.getElementById('ihName').value.trim();
  const userId = document.getElementById('ihUser').value;
  const processValue = document.getElementById('ihProcess').value;
  const actions = [...document.querySelectorAll('.ihAct:checked')].map((el) => el.value);
  if (!name) return toast('名称必填', true);
  if (!hookId && !code) return toast('编码必填', true);
  if (!userId) return toast('请选择服务账号', true);
  if (!actions.length) return toast('至少允许一个动作', true);
  const payload = {
    name,
    process_id: processValue ? Number(processValue) : null,
    run_as_user_id: Number(userId),
    actions,
    is_active: document.getElementById('ihActive').value === 'true',
  };
  try {
    let saved;
    if (hookId) {
      const rotate = document.getElementById('ihRotate');
      payload.rotate_secret = !!(rotate && rotate.checked);
      saved = await PATCH('/integrations/inbound-hooks/' + hookId, payload);
    } else {
      saved = await POST('/integrations/inbound-hooks', { ...payload, code });
    }
    if (saved.secret) {
      showInboundSecret(saved);
    } else {
      closeModal();
      toast('入站 Webhook 已保存');
    }
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

function showInboundSecret(hook) {
  const url = location.origin + hook.inbound_path;
  openModal('入站 Webhook 密钥', `
    <div class="note">密钥只显示这一次。对接方用「timestamp + \".\" + 原始请求体」做
      HMAC-SHA256 签名。</div>
    <div class="field"><label>调用地址</label>
      <input readonly value="${esc(url)}"></div>
    <div class="field"><label>密钥</label>
      <textarea readonly rows="2">${esc(hook.secret || '')}</textarea></div>
    <div class="field"><label>请求头</label>
      <textarea readonly rows="3">X-Logix-Timestamp: <unix 秒>
X-Logix-Signature: sha256=<hex>
Content-Type: application/json</textarea></div>
    <div class="hint">修改配置时勾选「轮换密钥」可生成新密钥；旧密钥立即失效。</div>`,
    '<button class="btn btn-p" data-act="execution.close">我已保存</button>');
}

async function deleteInboundHook(hookId) {
  const ok = await confirmDialog('确定删除这个入站 Webhook？其事件记录会一并删除，旧密钥立即失效。',
    { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/integrations/inbound-hooks/' + hookId);
    toast('入站 Webhook 已删除');
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
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitForm"
       data-id="${form ? form.id : ''}">保存</button>`);
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
  const ok = await confirmDialog('确定删除这个表单定义？已启动实例使用快照，不受影响。',
    { danger: true, okText: '删除' });
  if (!ok) return;
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
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitRule"
       data-id="${rule ? rule.id : ''}">保存</button>`);
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
  const ok = await confirmDialog('确定删除这条分支规则？已启动实例使用快照，不受影响。',
    { danger: true, okText: '删除' });
  if (!ok) return;
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

async function startInstanceModal(initialProcessId = null) {
  openModal('启动流程实例', skeleton(5));
  let processes = state.executionProcesses;
  let projects = [];
  let assignees = [];
  try {
    [processes, projects, assignees] = await Promise.all([
      processes || GET('/execution/processes'),
      GET('/projects?page_size=100'),
      GET('/execution/assignees'),
    ]);
  } catch (e) {
    openModal('加载失败', `<div class="errbar"><div>${esc(e.message)}</div></div>`);
    return;
  }
  state.executionAssignees = assignees;
  const wanted = Number(initialProcessId) || null;
  const selectedId = wanted && processes.some((p) => p.id === wanted)
    ? wanted
    : (processes[0] ? processes[0].id : null);
  const processOpts = processes.map((p) =>
    `<option value="${p.id}"${p.id === selectedId ? ' selected' : ''}>L${p.level} ${esc(p.code)} ${esc(p.name)}（${p.node_count} 节点）</option>`
  ).join('');
  const projectOpts = projects.items.map((p) =>
    `<option value="${p.id}">${esc(p.code)} ${esc(p.name)}</option>`
  ).join('');
  openModal('启动流程实例', `
    <div class="field"><label>流程 *</label>
      <select id="exProcess" data-act="execution.loadStartNodes">${processOpts || '<option value="">没有已建模的流程</option>'}</select>
      <div class="hint">只列出设计器里已有节点的流程</div></div>
    <div class="field"><label>关联项目</label>
      <select id="exProject"><option value="">不关联</option>${projectOpts}</select></div>
    <div id="exAssign" class="mt"></div>
    <div class="field"><label>流程变量（JSON）</label>
      <textarea id="exVars" placeholder='{"申请人":"张三","金额":10000}'>{"source":"manual"}</textarea></div>`,
    `<button class="btn btn-g" data-act="execution.close">取消</button>
     <button class="btn btn-p" data-act="execution.submitStart">启动</button>`);
  if (selectedId) loadStartNodes(selectedId);
}

async function loadStartNodes(processId) {
  const box = document.getElementById('exAssign');
  if (!box || !processId) return;
  box.innerHTML = '<div class="tiny">加载节点…</div>';
  try {
    const model = await GET('/processes/' + processId + '/design');
    if (!box.isConnected) return;
    const nodes = (model.nodes || []).filter(
      (n) => !['START', 'END'].includes(n.node_type));
    if (!nodes.length) {
      box.innerHTML = '<div class="note">该流程没有可执行节点。</div>';
      return;
    }
    const assignees = state.executionAssignees || [];
    const userOpts = assignees.map((a) =>
      `<option value="${a.id}">${esc(a.display_name)} · ${esc(a.role_label || a.role)}${
        a.department ? ' · ' + esc(a.department) : ''}</option>`).join('');
    box.innerHTML = `
      <h3>节点处理人（可选）</h3>
      <div class="tiny mb">不选则进入公共队列，流程管理科会收到待认领提醒。</div>
      <div class="row2">${nodes.map((n) => `
        <div class="field">
          <label>${esc(n.node_key)} ${esc(n.name)}
            <div class="tiny">${esc(n.lane || '')}${
              n.owner_role ? ' · ' + esc(n.owner_role) : ''}</div></label>
          <select class="sel" data-assign-key="${esc(n.node_key)}">
            <option value="">公共队列</option>${userOpts}
          </select>
        </div>`).join('')}</div>`;
  } catch (e) {
    if (box.isConnected) {
      box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
    }
  }
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
  const assignments = {};
  document.querySelectorAll('[data-assign-key]').forEach((el) => {
    if (el.value) assignments[el.dataset.assignKey] = Number(el.value);
  });
  const payload = {
    process_id: Number(processId),
    project_id: projectId ? Number(projectId) : null,
    variables,
  };
  if (Object.keys(assignments).length) payload.assignments = assignments;
  try {
    const instance = await POST('/execution/instances', payload);
    closeModal();
    toast('流程已启动：' + instance.code);
    state.execution.tab = 'tasks';
    setUrlState('execution', { tab: 'tasks' }, { push: false });
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

async function openTask(taskId, forceManual) {
  const gen = openModal('加载中…', skeleton(4));
  let task;
  let events = [];
  let worklogs = [];
  try {
    [task, events, worklogs] = await Promise.all([
      GET('/execution/tasks/' + taskId),
      GET('/execution/tasks/' + taskId + '/events'),
      GET('/execution/tasks/' + taskId + '/worklogs'),
    ]);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal('加载失败', `<div class="errbar"><div>${esc(e.message)}</div></div>`);
    }
    return;
  }
  if (!modalAlive(gen)) return;
  const eventRows = (events || []).map((evt) => `
    <tr><td class="tiny">${dtShort(evt.created_at)}</td>
      <td>${esc(evt.event_label)}</td>
      <td class="tiny">${evt.from_status_label
        ? esc(evt.from_status_label) + ' → ' : ''}${esc(evt.to_status_label || '')}</td>
      <td>${esc(evt.actor_name || '系统')}</td>
      <td class="tiny">${esc((evt.detail && evt.detail.comment) || '')}</td></tr>`).join('')
    || emptyRow(5, '暂无任务事件');
  const worklogRows = (worklogs || []).map((row) => `
    <tr><td class="tiny">${dtShort(row.created_at)}</td>
      <td>${esc(row.user_name || '—')}</td>
      <td>${esc(row.work_type_label || row.work_type)}</td>
      <td>${row.effort_minutes} 分钟</td>
      <td class="tiny">${esc(row.note || '')}</td></tr>`).join('')
    || emptyRow(5, '暂无工时记录');
  const me = AUTH.user ? AUTH.user.id : null;
  const manualMode = !!forceManual || manualBranchTask === task.id;
  const overdue = task.due_at && new Date(task.due_at).getTime() < Date.now();
  const suspended = task.instance_status === 'SUSPENDED';
  const canAct = !suspended && canWrite()
    && (task.assignee_user_id === null || task.assignee_user_id === me || canManage());
  const canLog = canAct || canManage() || task.assignee_user_id === me;
  const options = task.next_options.map((o) =>
    `<option value="${esc(o.node_key)}">${esc(o.node_key)} ${esc(o.name)}${
      o.label ? ' · ' + esc(o.label) : ''}</option>`
  ).join('');

  openModal(task.name + ' · ' + task.instance_code, `
    ${suspended
      ? '<div class="note mb">所属流程实例已挂起，恢复后才能处理任务。</div>' : ''}
    ${task.due_at
      ? `<div class="note mb">任务时限：${dtShort(task.due_at)}${overdue ? ' · <b>已超期</b>' : ''}</div>`
      : ''}
    ${task.escalated_at
      ? `<div class="note mb">已升级：${dtShort(task.escalated_at)}${
        task.escalated_to_name ? ' → ' + esc(task.escalated_to_name) : ''}</div>`
      : ''}
    <div class="row2">
      <div class="field"><label>流程</label><input value="${esc(task.process_name)}" readonly></div>
      <div class="field"><label>节点${
        tipHelp('流程设计器发布模型后，实例启动时把节点、表单、规则和分派配置一起快照；'
          + '之后改设计器不会影响已经启动的实例。')}</label>
        <input value="${esc(task.node_key)} · ${esc(task.task_type_label)}" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>标准工时</label>
        <input value="${task.standard_minutes} 分钟" readonly></div>
      <div class="field"><label>实际工时</label>
        <input value="${task.actual_minutes} 分钟" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>候选角色 / 泳道${
        tipHelp('分派优先级：默认处理人 → 候选角色/限定组织 → 公共队列；'
          + '节点时限与升级规则覆盖流程默认。')}</label>
        <input value="${esc(task.candidate_role || task.lane || '—')}" readonly></div>
      <div class="field"><label>处理人</label>
        <input value="${esc(task.assignee_name || '公共队列')}" readonly></div>
    </div>
    ${task.status === 'COMPLETED' ? `
      <div class="field"><label>完成情况</label>
        <textarea readonly>${esc(task.comment || '—')}</textarea></div>` : ''}
    ${canAct && task.status !== 'COMPLETED' ? `
      ${task.next_options.length > 1 ? `
        <div class="field"><label>分支处理${
          tipHelp('自动模式按本节点规则的条件和优先级匹配；显式手动选择下一步时优先于规则。'
            + '规则目标必须是该节点的出边，否则后端会拒绝。')}</label>
          <select id="exBranchMode" data-act="execution.branchMode">
            <option value="auto" ${manualMode ? '' : 'selected'}>按规则自动</option>
            <option value="manual" ${manualMode ? 'selected' : ''}>手动指定下一步</option>
          </select>
          <div class="hint">自动模式由节点规则决定；没有命中规则时会提示改用手动</div></div>
        <div class="field ${manualMode ? '' : 'hide'}" id="exNextWrap"><label>下一步</label>
          <select id="exNext">${options}</select></div>` : ''}
      ${(task.form_schema && task.form_schema.length)
        ? '<div class="note">表单：' + esc(task.form_name || task.name) + tipHelp(
          '表单在「流程执行 → 表单与规则」按流程/节点定义；节点没有专属表单时回退到流程默认表单。'
          + '实例启动时冻结字段，后续改表单不影响本实例。') + '</div>' +
          renderFormFields(task.form_schema)
        : `<div class="field"><label>表单数据（JSON，可选）</label>
            <textarea id="exForm" placeholder='{"审批意见":"同意","金额":10000}'>{}</textarea></div>`}
      <div class="field"><label>本次实际工时（分钟）</label>
        <input id="exEffort" type="number" min="0" max="10080"
          placeholder="用于工作量统计，可留空"></div>
      <div class="field"><label>处理意见 / 备注</label>
        <input id="exComment" placeholder="处理结论或说明"></div>` : ''}
    <div class="between mt">
      <h3 style="margin:0">工时记录</h3>
      ${canLog
        ? `<button class="btn-sm" data-act="execution.openWorklog" data-id="${task.id}">补录工时</button>` : ''}
    </div>
    <table class="tbl">
      <thead><tr><th>时间</th><th>人员</th><th>类型</th><th>工时</th><th>备注</th></tr></thead>
      <tbody>${worklogRows}</tbody>
    </table>
    <h3 class="mt">任务历史</h3>
    <table class="tbl">
      <thead><tr><th>时间</th><th>事件</th><th>状态</th><th>处理人</th><th>说明</th></tr></thead>
      <tbody>${eventRows}</tbody>
    </table>
    ${canAct && task.status !== 'COMPLETED'
      ? `<div class="note">完成后流程会自动推进到下一节点；没有后续节点时实例结束。${tipHelp(
        '表单值会先校验并写入实例变量，再参与后续节点的规则匹配；'
        + '没有命中规则且存在多个分支时，需要手动指定下一步。')}</div>`
      : suspended
        ? '<div class="note">流程实例已挂起，请先让流程管理科恢复实例。</div>'
        : '<div class="note">只读：任务已指派给其他人，或当前角色没有处理权限。</div>'}`,
    `<button class="btn btn-g" data-act="execution.close">关闭</button>
     ${canAct && task.status !== 'COMPLETED'
       ? `<button class="btn btn-p" data-act="execution.completeTask" data-id="${task.id}">完成并推进</button>` : ''}`);
}

function toggleBranchMode() {
  const mode = document.getElementById('exBranchMode');
  const wrap = document.getElementById('exNextWrap');
  if (mode && wrap) wrap.classList.toggle('hide', mode.value !== 'manual');
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
  const modeEl = document.getElementById('exBranchMode');
  const autoMode = !modeEl || modeEl.value === 'auto';
  const nextEl = document.getElementById('exNext');
  const commentEl = document.getElementById('exComment');
  const effortEl = document.getElementById('exEffort');
  const effort = effortEl && effortEl.value !== '' ? Number(effortEl.value) : null;
  if (effort !== null && (!Number.isFinite(effort) || effort < 0)) {
    return toast('实际工时必须是非负数', true);
  }
  try {
    await POST('/execution/tasks/' + taskId + '/complete', {
      form_data: formData,
      next_node_key: autoMode ? null : (nextEl ? nextEl.value : null),
      comment: commentEl ? commentEl.value.trim() || null : null,
      effort_minutes: effort,
    });
    manualBranchTask = null;
    closeModal();
    toast('任务已完成，流程已推进');
    RENDERERS.execution();
  } catch (e) {
    if (autoMode && /多个分支|next_node_key/.test(e.message)) {
      // 没有命中规则：回到同一个任务，让处理人手动选择分支
      manualBranchTask = taskId;
      toast('没有命中分支规则，请手动指定下一步', true);
      closeModal();
      openTask(taskId, true);
      return;
    }
    toast(e.message, true);
  }
}

async function openWorklogModal(taskId) {
  let labels = state.executionWorklogLabels;
  if (!labels) {
    try {
      const meta = await GET('/execution/meta');
      labels = meta.worklog_type_labels || {};
      state.executionWorklogLabels = labels;
    } catch (e) {
      labels = {};
    }
  }
  const entries = Object.entries(labels);
  const options = entries.length
    ? entries.map(([value, label]) => `<option value="${value}"${
      value === 'HANDLE' ? ' selected' : ''}>${esc(label)}</option>`).join('')
    : '<option value="HANDLE">处理</option>';
  openModal('补录工时', `
    <div class="row2">
      <div class="field"><label>工时类型</label><select id="wlType">${options}</select></div>
      <div class="field"><label>实际工时（分钟）</label>
        <input id="wlMinutes" type="number" min="0" max="10080" placeholder="如 30"></div>
    </div>
    <div class="field"><label>备注</label>
      <input id="wlNote" placeholder="如：返工/等待/额外沟通"></div>
    <div class="note">同一任务多次补录会累加；已完成任务也可以补录。</div>`,
  `<button class="btn btn-g" data-act="execution.close">取消</button>
   <button class="btn btn-p" data-act="execution.submitWorklog" data-id="${taskId}">保存</button>`);
}

async function submitWorklog(taskId) {
  const minutes = Number(document.getElementById('wlMinutes').value);
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return toast('请填写大于 0 的工时', true);
  }
  try {
    await POST('/execution/tasks/' + taskId + '/worklogs', {
      work_type: document.getElementById('wlType').value || 'HANDLE',
      effort_minutes: minutes,
      note: document.getElementById('wlNote').value.trim() || null,
    });
    toast('工时已补录');
    closeModal();
    openTask(taskId);
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
  const compensations = detail.compensations || [];
  const configSnapshot = detail.configuration || {};
  const formSnapshots = configSnapshot.forms || {};
  const ruleSnapshots = configSnapshot.rules || {};
  const configTags = [
    ...Object.entries(formSnapshots).map(([key, row]) =>
      `<span class="tag t-blu">表单 ${esc(key || '默认')} v${row.version || 1}</span>`),
    ...Object.entries(ruleSnapshots).flatMap(([key, rows]) =>
      (rows || []).map((row) =>
        `<span class="tag t-gry">规则 ${esc(key)} v${row.version || 1}</span>`)),
  ].join(' ');
  const compensationRows = compensations.map((row) => `
    <tr>
      <td><b>${esc(row.action_name)}</b><div class="tiny">${esc(row.node_key)}</div></td>
      <td><span class="tag ${row.status === 'DONE' ? 't-grn' : 't-yel'}">${esc(row.status_label)}</span></td>
      <td class="tiny">${esc(row.description || '—')}</td>
      <td>${esc(row.completed_by || '—')}<div class="tiny">${
        row.completed_at ? dtShort(row.completed_at) : '待处理'}</div></td>
      <td>${canManage() && row.status === 'PENDING'
        ? `<button class="btn-sm" data-act="execution.completeCompensation"
            data-id="${row.id}">标记完成</button>` : '—'}</td>
    </tr>`).join('') || emptyRow(5, '没有补偿待办');

  openModal(i.code + ' · ' + i.process_name, `
    ${i.suspended_at
      ? `<div class="note mb">已挂起：${dtShort(i.suspended_at)}${
        i.suspend_reason ? ' · ' + esc(i.suspend_reason) : ''}</div>` : ''}
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
    <div class="field"><label>配置快照（启动时冻结）</label>
      <div class="gap" style="flex-wrap:wrap">${configTags || '<span class="tiny muted">没有表单/规则配置</span>'}</div></div>
    <h3 class="mt">任务时间线</h3>
    <table class="tbl">
      <thead><tr><th>节点</th><th>状态</th><th>处理人</th><th>完成时间 / 备注</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <h3 class="mt">取消补偿（${compensations.length}）</h3>
    <table class="tbl">
      <thead><tr><th>动作</th><th>状态</th><th>说明</th><th>完成人</th><th></th></tr></thead>
      <tbody>${compensationRows}</tbody>
    </table>`,
    `${canManage() && i.status === 'RUNNING'
      ? '<button class="btn btn-g" style="margin-right:auto"'
        + ` data-act="execution.suspend" data-id="${i.id}">挂起实例</button>` : ''}
     ${canManage() && i.status === 'SUSPENDED'
      ? '<button class="btn btn-p" style="margin-right:auto"'
        + ` data-act="execution.resume" data-id="${i.id}">恢复实例</button>` : ''}
     ${canManage() && (i.status === 'RUNNING' || i.status === 'SUSPENDED')
      ? '<button class="btn btn-g" style="color:var(--bad-strong)"'
        + ` data-act="execution.cancel" data-id="${i.id}">取消实例</button>` : ''}
     <button class="btn btn-g" data-act="execution.close">关闭</button>`);
}

async function completeCompensation(recordId) {
  try {
    await POST(`/execution/compensations/${recordId}/complete`, { note: null });
    toast('补偿已标记完成');
    closeModal();
  } catch (e) {
    toast(e.message, true);
  }
}

async function archiveInstances() {
  const days = await promptDialog('归档多少天前完成/取消的实例？（默认 365）', {
    title: '归档旧实例',
    okText: '归档',
    value: '365',
  });
  if (days === null) return;
  try {
    const result = await POST(
      '/execution/instances/archive?older_than_days=' + (Number(days) || 365),
      {},
    );
    toast(`已归档 ${result.archived} 个实例`);
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function suspendInstance(instanceId) {  const reason = await promptDialog('挂起原因（可选；取消则不挂起）', {
    title: '挂起流程实例', okText: '挂起', placeholder: '如：等待客户确认',
  });
  if (reason === null) return;
  try {
    await POST('/execution/instances/' + instanceId + '/suspend', {
      reason: reason.trim() || null,
    });
    closeModal();
    toast('流程实例已挂起');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function resumeInstance(instanceId) {
  try {
    await POST('/execution/instances/' + instanceId + '/resume', {});
    closeModal();
    toast('流程实例已恢复');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}

async function cancelInstance(instanceId) {
  const ok = await confirmDialog('确定取消这个流程实例？未完成的任务会一并取消。',
    { danger: true, okText: '取消实例' });
  if (!ok) return;
  try {
    await POST('/execution/instances/' + instanceId + '/cancel', {});
    closeModal();
    toast('流程实例已取消');
    RENDERERS.execution();
  } catch (e) {
    toast(e.message, true);
  }
}


export { renderExecution };
