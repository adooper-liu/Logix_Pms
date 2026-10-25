/* 视图：十层单页
 *
 * 一条试点路径 = 10 个层状态；一次只展开一层。
 * 退出门由现有 evidence 自动计算；待办和异常是人工维护的补充。
 */

import { esc, num } from '../core/format.js';
import { viewEl, on, openModal, closeModal, confirmDialog, toast } from '../core/ui.js';
import { renderAsync, go, RENDERERS, urlParams, setUrlState } from '../core/router.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { state } from '../core/state.js';

const LAYER_TONE = {
  NOT_STARTED: 't-gry',
  IN_PROGRESS: 't-yel',
  BLOCKED: 't-red',
  DONE: 't-grn',
};
const TASK_TONE = { TODO: 't-gry', DOING: 't-yel', DONE: 't-grn' };
const ISSUE_TONE = {
  OPEN: 't-red', INVESTIGATING: 't-yel', VERIFYING: 't-blu', CLOSED: 't-grn',
};
const SEVERITY_TONE = { BLOCKER: 't-red', MAJOR: 't-yel', MINOR: 't-gry' };

function statusTag(tone, label) {
  return `<span class="tag ${tone || 't-gry'}">${esc(label || '—')}</span>`;
}

function actionAttrs(action) {
  return action.action === 'start.guidedPcf'
    ? 'data-act="start.guidedPcf"'
    : 'data-act="pilot.go"';
}

async function loadUsers() {
  if (state.pilot.users) return state.pilot.users;
  try {
    state.pilot.users = await GET('/execution/assignees');
  } catch (e) {
    state.pilot.users = [];
  }
  return state.pilot.users;
}

function userOptions(users, selectedId) {
  return users.map((user) => `<option value="${user.id}"${
    Number(selectedId) === user.id ? ' selected' : ''}>${
    esc(user.display_name)} · ${esc(user.role_label || user.role)}</option>`).join('');
}

/* -------------------------------------------------- 选择与渲染 */

on('pilot.go', ({ view }) => go(view));

on('pilot.selectPath', (_data, el) => {
  const pathId = Number(el.value) || null;
  if (!pathId) return;
  state.pilot.pathId = pathId;
  state.pilot.layerNo = null;
  go('pilot', { params: { path: pathId }, push: true });
});

on('pilot.selectLayer', ({ layer }) => {
  const layerNo = Number(layer) || null;
  state.pilot.layerNo = layerNo;
  go('pilot', {
    params: { path: state.pilot.pathId, layer: layerNo },
    push: true,
  });
});

on('pilot.advance', async () => {
  const detail = state.pilot.data;
  if (!detail) return;
  try {
    const updated = await POST(`/pilot/paths/${detail.id}/advance`);
    state.pilot.data = updated;
    state.pilot.layerNo = updated.current_layer;
    setUrlState('pilot', { path: updated.id, layer: updated.current_layer }, { push: false });
    paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
    toast(`已进入第 ${updated.current_layer} 层`);
  } catch (e) {
    try {
      const parsed = JSON.parse(e.message);
      toast(`${parsed.message}：${(parsed.missing || []).join('、')}`, true);
    } catch (_) {
      toast(e.message, true);
    }
  }
});

on('pilot.deletePath', async () => {
  const detail = state.pilot.data;
  if (!detail) return;
  const ok = await confirmDialog(`删除「${detail.name}」会同时删除十层备注、待办和异常，确定继续？`,
    { title: '删除试点路径', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await DEL(`/pilot/paths/${detail.id}`);
    state.pilot.pathId = null;
    state.pilot.layerNo = null;
    toast('试点路径已删除');
    go('pilot', { params: {}, push: false });
  } catch (e) {
    toast(e.message, true);
  }
});

/* -------------------------------------------------- 新建路径 */

on('pilot.newPath', () => openPathModal());

async function openPathModal() {
  let processes;
  let users;
  try {
    [processes, users] = await Promise.all([GET('/process-map/flat'), loadUsers()]);
  } catch (e) {
    return toast(e.message, true);
  }
  const options = processes.filter((row) => row.level === 3 || row.level === 4)
    .map((row) => `<option value="${row.id}">L${row.level} ${esc(row.code)} ${esc(row.name)}</option>`)
    .join('');
  openModal('新建试点路径', `
    <div class="field"><label>路径名称 *</label>
      <input id="plName" placeholder="如 采购到付款试点"></div>
    <div class="field"><label>关联流程 *</label>
      <select id="plProcess"><option value="">请选择 L3/L4 流程</option>${options}</select></div>
    <div class="field"><label>负责人</label>
      <select id="plOwner"><option value="">当前用户</option>${userOptions(users)}</select></div>
    <div class="note">创建后会生成 10 层状态；退出门由系统里已有的证据自动判定。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="pilot.savePath">创建</button>`);
}

on('pilot.savePath', async () => {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const name = val('plName');
  const processId = val('plProcess');
  if (!name) return toast('请填写路径名称', true);
  if (!processId) return toast('请选择关联流程', true);
  try {
    const detail = await POST('/pilot/paths', {
      name,
      process_id: Number(processId),
      owner_user_id: val('plOwner') ? Number(val('plOwner')) : null,
    });
    closeModal();
    state.pilot.pathId = detail.id;
    state.pilot.layerNo = detail.current_layer;
    toast('试点路径已创建');
    go('pilot', {
      params: { path: detail.id, layer: detail.current_layer },
      push: true,
    });
  } catch (e) {
    toast(e.message, true);
  }
});

/* -------------------------------------------------- 层备注 / 待办 / 异常 */

function selectedLayer() {
  const detail = state.pilot.data;
  if (!detail) return null;
  const no = state.pilot.layerNo || detail.current_layer;
  return detail.layers.find((layer) => layer.layer_no === no) || detail.layers[0];
}

on('pilot.saveLayer', async () => {
  const detail = state.pilot.data;
  const layer = selectedLayer();
  if (!detail || !layer) return;
  const context = document.getElementById('plContext');
  const notes = document.getElementById('plNotes');
  try {
    const updated = await PATCH(`/pilot/paths/${detail.id}/layers/${layer.layer_no}`, {
      context_summary: context ? context.value.trim() : '',
      notes: notes ? notes.value.trim() : '',
    });
    state.pilot.data = updated;
    paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
    toast('本层备注已保存');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.newTask', async () => {
  const layer = selectedLayer();
  if (!layer) return;
  await openTaskModal(layer.layer_no);
});

async function openTaskModal(layerNo) {
  const users = await loadUsers();
  const meta = state.pilot.meta || {};
  const priorities = Object.entries(meta.priority_labels || {})
    .map(([value, label]) => `<option value="${value}"${
      value === 'MEDIUM' ? ' selected' : ''}>${esc(label)}</option>`).join('');
  openModal(`新增待办 · 第 ${layerNo} 层`, `
    <div class="field"><label>待办标题 *</label>
      <input id="ptTitle" placeholder="如 补充夜班升级接收人"></div>
    <div class="row2">
      <div class="field"><label>优先级</label>
        <select id="ptPriority">${priorities}</select></div>
      <div class="field"><label>负责人</label>
        <select id="ptOwner"><option value="">未指定</option>${userOptions(users)}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>期限</label><input id="ptDue" type="date"></div>
      <div class="field"><label>验收标准</label>
        <input id="ptAccept" placeholder="什么情况算完成"></div>
    </div>
    <div class="note">待办不替代证据；它只记录谁在什么时候补齐什么。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="pilot.saveTask" data-layer="${layerNo}">创建</button>`);
}

on('pilot.saveTask', async ({ layer }) => {
  const detail = state.pilot.data;
  if (!detail) return;
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('ptTitle')) return toast('请填写待办标题', true);
  try {
    await POST(`/pilot/paths/${detail.id}/tasks`, {
      layer_no: Number(layer),
      title: val('ptTitle'),
      priority: val('ptPriority') || 'MEDIUM',
      owner_user_id: val('ptOwner') ? Number(val('ptOwner')) : null,
      due_date: val('ptDue') || null,
      acceptance: val('ptAccept') || null,
    });
    closeModal();
    toast('待办已创建');
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.taskDone', ({ id }) => updateTask(id, 'DONE'));
on('pilot.taskReopen', ({ id }) => updateTask(id, 'TODO'));

async function updateTask(id, status) {
  try {
    await PATCH(`/pilot/tasks/${id}`, { status });
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
}

on('pilot.deleteTask', async ({ id }) => {
  const ok = await confirmDialog('删除这条待办？', { title: '删除待办', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await DEL(`/pilot/tasks/${id}`);
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.newIssue', async () => {
  const layer = selectedLayer();
  if (!layer) return;
  await openIssueModal(layer.layer_no);
});

async function openIssueModal(layerNo) {
  const users = await loadUsers();
  const meta = state.pilot.meta || {};
  const severities = Object.entries(meta.severity_labels || {})
    .map(([value, label]) => `<option value="${value}"${
      value === 'MAJOR' ? ' selected' : ''}>${esc(label)}</option>`).join('');
  openModal(`新增异常 / 改善卡 · 第 ${layerNo} 层`, `
    <div class="field"><label>问题标题 *</label>
      <input id="piTitle" placeholder="如 夜班无升级接收人"></div>
    <div class="row2">
      <div class="field"><label>严重度</label>
        <select id="piSeverity">${severities}</select></div>
      <div class="field"><label>负责人</label>
        <select id="piOwner"><option value="">未指定</option>${userOptions(users)}</select></div>
    </div>
    <div class="field"><label>临时措施</label>
      <textarea id="piWorkaround" rows="2" placeholder="先怎么控制，不让问题扩散"></textarea></div>
    <div class="field"><label>验证标准</label>
      <textarea id="piVerify" rows="2" placeholder="什么证据算解决"></textarea></div>
    <div class="field"><label>期限</label><input id="piDue" type="date"></div>
    <div class="note">阻断异常会让本层退出条件无法通过；关闭后自动恢复按证据判定。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="pilot.saveIssue" data-layer="${layerNo}">创建</button>`);
}

on('pilot.saveIssue', async ({ layer }) => {
  const detail = state.pilot.data;
  if (!detail) return;
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('piTitle')) return toast('请填写问题标题', true);
  try {
    await POST(`/pilot/paths/${detail.id}/issues`, {
      layer_no: Number(layer),
      title: val('piTitle'),
      severity: val('piSeverity') || 'MAJOR',
      owner_user_id: val('piOwner') ? Number(val('piOwner')) : null,
      workaround: val('piWorkaround') || null,
      verification: val('piVerify') || null,
      due_date: val('piDue') || null,
    });
    closeModal();
    toast('异常已创建');
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.issueStart', ({ id }) => updateIssue(id, 'INVESTIGATING'));
on('pilot.issueVerify', ({ id }) => updateIssue(id, 'VERIFYING'));
on('pilot.issueClose', ({ id }) => updateIssue(id, 'CLOSED'));
on('pilot.issueReopen', ({ id }) => updateIssue(id, 'OPEN'));

async function updateIssue(id, status) {
  try {
    await PATCH(`/pilot/issues/${id}`, { status });
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
}

on('pilot.deleteIssue', async ({ id }) => {
  const ok = await confirmDialog('删除这条异常记录？', {
    title: '删除异常', okText: '删除', danger: true,
  });
  if (!ok) return;
  try {
    await DEL(`/pilot/issues/${id}`);
    RENDERERS.pilot();
  } catch (e) {
    toast(e.message, true);
  }
});

/* -------------------------------------------------- 展示片段 */

function layerStrip(detail, selectedNo) {
  return detail.layers.map((layer) => {
    const tone = LAYER_TONE[layer.status] || 't-gry';
    return `
      <button class="pilot-layer ${layer.layer_no === selectedNo ? 'on' : ''}"
        data-act="pilot.selectLayer" data-layer="${layer.layer_no}">
        <span class="pilot-layer-no">${layer.layer_no}</span>
        <b>${esc(layer.title)}</b>
        <span class="tag ${tone}">${esc(layer.status_label)}</span>
        ${layer.current ? '<span class="tag t-blu">当前</span>' : ''}
      </button>`;
  }).join('');
}

function contextList(detail, selectedNo) {
  const previous = detail.layers.filter((layer) => layer.layer_no < selectedNo);
  if (!previous.length) return '';
  return `
    <details class="card pilot-fold">
      <summary><span>前置层（${previous.length}）</span>
        <span class="tiny muted">目标、边界、职责和最近结论</span></summary>
      ${previous.map((layer) => `
        <div class="between pilot-line">
          <span>${statusTag(LAYER_TONE[layer.status], layer.status_label)}
            <b>${layer.layer_no}. ${esc(layer.title)}</b></span>
          <span class="tiny muted">${esc(layer.context_summary || layer.goal)}</span>
        </div>`).join('')}
    </details>`;
}

function nextList(detail, selectedNo) {
  const next = detail.layers.filter((layer) => layer.layer_no > selectedNo);
  if (!next.length) return '';
  return `
    <details class="card pilot-fold">
      <summary><span>后续层（${next.length}）</span>
        <span class="tiny muted">退出当前层后再展开</span></summary>
      ${next.map((layer) => `
        <div class="between pilot-line">
          <span>${statusTag(LAYER_TONE[layer.status], layer.status_label)}
            <b>${layer.layer_no}. ${esc(layer.title)}</b></span>
          <span class="tiny muted">${esc(layer.goal)}</span>
        </div>`).join('')}
    </details>`;
}

function evidenceList(layer) {
  return layer.evidence_items.map((item) => {
    const tone = item.met ? 'ok' : item.required ? 'miss' : 'opt';
    const suffix = item.met ? '' : item.required ? ' · 还缺' : ' · 建议关注';
    return `
      <div class="between pilot-line ${tone}">
        <span>${item.met ? '✓' : '○'} ${esc(item.label)}</span>
        <b>${item.value}${suffix}</b>
      </div>`;
  }).join('') || '<div class="tiny muted">本层没有必需证据</div>';
}

function taskRows(layer) {
  return layer.tasks.map((task) => `
    <div class="pilot-item">
      <div class="between">
        <span><b>${esc(task.title)}</b>
          ${statusTag(TASK_TONE[task.status], task.status_label)}
          ${statusTag('t-gry', task.priority_label)}</span>
        <span class="tiny muted">${esc(task.owner || '未指定')}${
          task.due_date ? ' · ' + esc(task.due_date) : ''}</span>
      </div>
      ${task.acceptance ? `<div class="tiny muted">验收：${esc(task.acceptance)}</div>` : ''}
      <div class="gap mt">
        ${task.status === 'DONE'
          ? `<button class="btn-sm" data-act="pilot.taskReopen" data-id="${task.id}">重新打开</button>`
          : `<button class="btn-sm" data-act="pilot.taskDone" data-id="${task.id}">标为完成</button>`}
        <button class="btn-sm" data-act="pilot.deleteTask" data-id="${task.id}">删除</button>
      </div>
    </div>`).join('') || '<div class="tiny muted">本层还没有待办</div>';
}

function issueRows(layer) {
  return layer.issues.map((issue) => `
    <div class="pilot-item">
      <div class="between">
        <span><b>${esc(issue.title)}</b>
          ${statusTag(SEVERITY_TONE[issue.severity], issue.severity_label)}
          ${statusTag(ISSUE_TONE[issue.status], issue.status_label)}</span>
        <span class="tiny muted">${esc(issue.owner || '未指定')}${
          issue.due_date ? ' · ' + esc(issue.due_date) : ''}</span>
      </div>
      ${issue.workaround ? `<div class="tiny">临时措施：${esc(issue.workaround)}</div>` : ''}
      ${issue.verification ? `<div class="tiny">验证：${esc(issue.verification)}</div>` : ''}
      <div class="gap mt">
        ${issue.status === 'OPEN'
          ? `<button class="btn-sm" data-act="pilot.issueStart" data-id="${issue.id}">开始分析</button>` : ''}
        ${issue.status === 'INVESTIGATING'
          ? `<button class="btn-sm" data-act="pilot.issueVerify" data-id="${issue.id}">进入验证</button>` : ''}
        ${issue.status === 'VERIFYING'
          ? `<button class="btn-sm" data-act="pilot.issueClose" data-id="${issue.id}">关闭</button>` : ''}
        ${issue.status === 'CLOSED'
          ? `<button class="btn-sm" data-act="pilot.issueReopen" data-id="${issue.id}">重新打开</button>` : ''}
        <button class="btn-sm" data-act="pilot.deleteIssue" data-id="${issue.id}">删除</button>
      </div>
    </div>`).join('') || '<div class="tiny muted">本层没有异常</div>';
}

function layerResources(resources) {
  const docs = resources.documents.map((row) => `
    <div class="pilot-resource"><b>${esc(row.title)}</b>
      <div class="tiny">${esc(row.code)} · ${esc(row.category_label || row.category)} · ${
        esc(row.version_label || '')} </div></div>`).join('')
    || '<div class="tiny muted">还没有生效制度/SOP</div>';
  const rules = resources.rules.map((row) => `
    <div class="pilot-resource"><span class="tag t-blu">${esc(row.category_label || row.category)}</span>
      <b>${esc(row.matter)}</b>
      <div class="tiny">审批：${esc(row.approver || '未指定')} · ${esc(row.status_label || row.status)}${
        row.amount_limit !== null ? ' · 限额 ' + num(row.amount_limit, 0) : ''}</div>
      <div class="tiny">例外：${esc(row.exception_path || '—')}</div>
      <div class="tiny">证据：${esc(row.evidence_required || '—')}</div></div>`).join('')
    || '<div class="tiny muted">还没有授权规则</div>';
  const exceptions = resources.exceptions.map((row) => `
    <div class="pilot-resource"><b>${esc(row.title)}</b>
      <div class="tiny">${esc(row.rule_code || '')} · ${esc(row.status_label || row.status)}${
        row.expires_at ? ' · 至 ' + esc(row.expires_at.slice(0, 10)) : ''}</div></div>`).join('')
    || '<div class="tiny muted">没有例外记录</div>';
  return `
    <div class="pilot-section">
      <div class="between mb">
        <h4>制度、授权与例外（本流程范围）</h4>
        <span class="tiny muted">生效制度 ${resources.documents.length} ·
          规则 ${resources.rules.length} · 例外 ${resources.exceptions.length}</span>
      </div>
      <div class="pilot-three">
        <div><span class="ev-h">已生效制度/SOP</span>${docs}</div>
        <div><span class="ev-h">授权规则</span>${rules}</div>
        <div><span class="ev-h">例外台账</span>${exceptions}</div>
      </div>
    </div>`;
}

function workspace(detail, layer) {
  const isCurrent = layer.layer_no === detail.current_layer;
  const missing = layer.evidence_items.filter((item) => !item.met);
  const advance = isCurrent
    ? `<button class="btn btn-p" data-act="pilot.advance"
         ${layer.gate_open ? '' : 'disabled'}>${
         detail.current_layer >= 10 ? '完成这条路径' : '进入下一层'}</button>`
    : `<button class="btn btn-g" data-act="pilot.selectLayer"
         data-layer="${detail.current_layer}">回到当前层</button>`;
  return `
    <div class="card pilot-workspace">
      <div class="between mb">
        <div>
          <div class="tiny muted">第 ${layer.layer_no} 层${isCurrent ? ' · 当前层' : ''}</div>
          <h3>${esc(layer.title)}</h3>
          <div class="desc">${esc(layer.goal)}</div>
        </div>
        <div class="gap">
          ${statusTag(LAYER_TONE[layer.status], layer.status_label)}
          ${layer.gate_open ? '<span class="tag t-grn">退出门已满足</span>'
            : `<span class="tag t-yel">还差 ${missing.length} 项</span>`}
        </div>
      </div>

      <div class="pilot-three">
        <div><span class="ev-h">输入</span>
          ${layer.inputs.map((item) => `<div class="pilot-bullet">· ${esc(item)}</div>`).join('')}</div>
        <div><span class="ev-h">处理</span>
          ${layer.process.map((item) => `<div class="pilot-bullet">· ${esc(item)}</div>`).join('')}</div>
        <div><span class="ev-h">输出</span>
          ${layer.outputs.map((item) => `<div class="pilot-bullet">· ${esc(item)}</div>`).join('')}</div>
      </div>

      <div class="pilot-section">
        <div class="between mb"><h4>退出门</h4>
          <span class="tiny muted">${esc(layer.exit_criteria)}</span></div>
        ${evidenceList(layer)}
      </div>

      ${layer.resources ? layerResources(layer.resources) : ''}

      <div class="pilot-section">
        <div class="between mb"><h4>本层备注</h4>
          <span class="tiny muted">上下文摘要会出现在前置层折叠里</span></div>
        <div class="field"><label>上下文摘要</label>
          <input id="plContext" value="${esc(layer.context_summary || '')}"
            placeholder="一句话说明本层已经确认了什么"></div>
        <div class="field"><label>备注</label>
          <textarea id="plNotes" rows="2"
            placeholder="待补事项、风险、决策记录">${esc(layer.notes || '')}</textarea></div>
        <button class="btn-sm" data-act="pilot.saveLayer">保存本层备注</button>
      </div>

      <div class="pilot-section">
        <div class="between mb"><h4>待办（${layer.tasks.length}）</h4>
          <button class="btn-sm" data-act="pilot.newTask">+ 新增待办</button></div>
        ${taskRows(layer)}
      </div>

      <div class="pilot-section">
        <div class="between mb"><h4>异常与改善（${layer.issues.length}）</h4>
          <button class="btn-sm" data-act="pilot.newIssue">+ 新增异常</button></div>
        ${issueRows(layer)}
      </div>

      <div class="pilot-section">
        <div class="between mb"><h4>本层入口</h4></div>
        <div class="gap">
          ${layer.actions.map((action) => `<button class="btn btn-g"
            ${actionAttrs(action)} data-view="${esc(action.view)}"
            title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
        </div>
      </div>

      <div class="between mt">
        <span class="tiny muted">${layer.gate_open
          ? '退出门已满足，可以进入下一层。'
          : '退出门未满足；先补齐红色项或关闭阻断异常。'}</span>
        ${advance}
      </div>
    </div>`;
}

function paint(payload) {
  const detail = payload.detail;
  const paths = payload.paths || [];
  const meta = payload.meta || {};
  if (!detail) {
    viewEl().innerHTML = `
      <div class="card page-head">
        <h2>十层单页<span class="module-badge">一条流程、十层状态</span></h2>
        <div class="desc">一次只展开一层；当前层退出门满足后才能进入下一层。</div>
      </div>
      <div class="card">
        <div class="empty">还没有试点路径。先选一条 L3/L4 流程，建立第一条十层路径。</div>
        <div class="gap mt"><button class="btn btn-p" data-act="pilot.newPath">+ 新建试点路径</button></div>
      </div>`;
    return;
  }

  state.pilot.paths = paths;
  state.pilot.meta = meta;
  state.pilot.data = detail;
  const selectedNo = state.pilot.layerNo || detail.current_layer;
  const layer = detail.layers.find((row) => row.layer_no === selectedNo)
    || detail.layers.find((row) => row.layer_no === detail.current_layer)
    || detail.layers[0];
  state.pilot.layerNo = layer.layer_no;
  // 默认路径/当前层也写进 URL，复制出去的链接能直接落到同一条路径的同一层
  setUrlState('pilot', { path: detail.id, layer: layer.layer_no }, { push: false });
  const options = paths.map((path) =>
    `<option value="${path.id}"${path.id === detail.id ? ' selected' : ''}>${
      esc(path.name)} · 第${path.current_layer}层</option>`).join('');

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>十层单页<span class="module-badge">一条流程、十层状态</span></h2>
          <div class="desc">一次只展开一层；当前层退出门满足后才能进入下一层。</div>
        </div>
        <div class="gap">
          <select class="sel sel-sm" data-act="pilot.selectPath">${options}</select>
          <button class="btn-sm" data-act="ui.copyLink">复制链接</button>
          <button class="btn btn-p" data-act="pilot.newPath">+ 新建试点路径</button>
        </div>
      </div>
      <div class="between mt">
        <div>
          <b>${esc(detail.name)}</b>
          <span class="tiny muted">${esc(detail.process_code || '')} ${esc(detail.process_name || '')}
            · Owner：${esc(detail.owner || '—')}</span>
        </div>
        <div class="gap">
          ${statusTag('t-blu', detail.status_label)}
          <span class="tag t-gry">当前第 ${detail.current_layer} 层 · ${esc(detail.current_layer_title || '')}</span>
          <span class="tag ${detail.progress >= 100 ? 't-grn' : 't-yel'}">
            可退出 ${num(detail.progress, 0)}%</span>
          <span class="tiny muted">${esc(detail.baseline_version)} → ${esc(detail.draft_version)}</span>
          <button class="btn-sm" data-act="pilot.deletePath">删除路径</button>
        </div>
      </div>
      <div class="pipe" style="margin-top:10px">
        <i class="fill-ok" style="width:${detail.progress}%"></i>
      </div>
    </div>

    <div class="pilot-layers">${layerStrip(detail, layer.layer_no)}</div>
    ${contextList(detail, layer.layer_no)}
    ${workspace(detail, layer)}
    ${nextList(detail, layer.layer_no)}`;
}

const renderPilot = () => {
  renderAsync(
    'pilot',
    async () => {
      const params = urlParams();
      const [paths, meta] = await Promise.all([GET('/pilot/paths'), GET('/pilot/meta')]);
      if (!paths.length) return { paths, meta, detail: null };
      const wantedPath = Number(params.path) || null;
      const wantedLayer = Number(params.layer) || null;
      const pathId = wantedPath && paths.some((row) => row.id === wantedPath)
        ? wantedPath
        : state.pilot.pathId && paths.some((row) => row.id === state.pilot.pathId)
          ? state.pilot.pathId : paths[0].id;
      state.pilot.pathId = pathId;
      if (wantedLayer) state.pilot.layerNo = wantedLayer;
      const detail = await GET(`/pilot/paths/${pathId}`);
      return { paths, meta, detail };
    },
    paint,
  );
};

export { renderPilot };
