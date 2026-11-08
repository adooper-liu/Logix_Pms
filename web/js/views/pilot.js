/* 视图：十层单页
 *
 * 一条 L3/L4 路径上的十层核对单；一次只展开一层。
 * 退出门复用体系总览的证据口径（第 4 层制度/授权按本流程范围计）；
 * 待办和异常是这条路径上的人工补充。新建路径不造证据、不推动公司阶段。
 */

import { esc, num, tipHelp } from '../core/format.js';
import { viewEl, on, openModal, closeModal, modalAlive, confirmDialog, toast } from '../core/ui.js';
import { renderAsync, go, RENDERERS, urlParams, setUrlState } from '../core/router.js';
import { GET, POST, PATCH, PUT, DEL } from '../core/api.js';
import { canManage } from '../core/auth.js';
import { pageShell } from '../core/layout.js';
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
  if (action.action === 'start.guidedPcf') return 'data-act="start.guidedPcf"';
  if (action.action === 'pilot.openCharter') return 'data-act="pilot.openCharter"';
  if (action.action === 'pilot.openMining') return 'data-act="pilot.openMining"';
  if (action.action === 'pilot.openRpa') return 'data-act="pilot.openRpa"';
  if (action.action === 'pilot.openEvent') return 'data-act="pilot.openEvent"';
  if (action.action === 'pilot.openRun') return 'data-act="pilot.openRun"';
  if (action.action === 'pilot.openCase') return 'data-act="pilot.openCase"';
  if (action.action === 'pilot.openTech') return 'data-act="pilot.openTech"';
  if (action.action === 'pilot.openTraining') return 'data-act="pilot.openTraining"';
  const params = new URLSearchParams(action.view_params || {}).toString();
  return `data-act="pilot.go"${params ? ` data-params="${esc(params)}"` : ''}`;
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

const PROCESS_ID_VIEWS = new Set([
  'designer', 'monitor', 'execution', 'deliverables', 'process_card',
]);

function scopedParams(view, params) {
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  const detail = state.pilot.data;
  if (!detail) return parsed;
  if (detail.process_id && PROCESS_ID_VIEWS.has(view)) parsed.process = String(detail.process_id);
  if (detail.process_code && view === 'map') parsed.process = detail.process_code;
  return parsed;
}

on('pilot.go', ({ view, params }) => {
  if (!view) return;
  const parsed = scopedParams(view, params);
  go(view, Object.keys(parsed).length ? { params: parsed, push: true } : undefined);
});

on('pilot.openMining', () => {
  const detail = state.pilot.data;
  const params = { tab: 'mining' };
  if (detail && detail.process_id) params.process = String(detail.process_id);
  go('monitor', { params, push: true });
});

on('pilot.openCharter', async () => {
  try {
    state.pilot.charterForm = await GET('/start/charter-options');
    const detail = state.pilot.data;
    if (detail) paint({ detail, paths: state.pilot.paths, meta: state.pilot.meta });
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveCharter', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程，起止记不到某一条 L3 上', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const sponsorId = Number(value('chSponsor'));
  if (!sponsorId) {
    toast('先选择发起人', true);
    return;
  }
  try {
    await POST('/start/charters', {
      process_id: detail.process_id,
      purpose: value('chPurpose'),
      starts_at: value('chStart'),
      ends_at: value('chEnd'),
      in_scope: value('chIn'),
      out_of_scope: value('chOut'),
      stop_condition: value('chStop'),
      sponsor_user_id: sponsorId,
    });
    state.pilot.charterForm = await GET('/start/charter-options');
    const updated = await GET(`/pilot/paths/${detail.id}`);
    state.pilot.data = updated;
    paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
    toast('已保存范围说明');
  } catch (e) {
    toast(e.message, true);
  }
});

function repaintPilot() {
  const detail = state.pilot.data;
  if (detail) paint({ detail, paths: state.pilot.paths, meta: state.pilot.meta });
}

async function refreshPath(message) {
  const detail = state.pilot.data;
  const updated = await GET(`/pilot/paths/${detail.id}`);
  state.pilot.data = updated;
  paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
  toast(message);
}

on('pilot.openRpa', async () => {
  try {
    await loadUsers();
    state.pilot.rpaOpen = true;
    repaintPilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.openEvent', () => {
  state.pilot.eventOpen = true;
  repaintPilot();
});

on('pilot.saveEvent', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!value('evSource') || !value('evCase') || !value('evActivity') || !value('evAt')) {
    toast('来源、案例号、活动和发生时间都要写上', true);
    return;
  }
  try {
    await POST('/pilot/event-logs', {
      process_id: detail.process_id,
      source_name: value('evSource'),
      case_key: value('evCase'),
      activity_name: value('evActivity'),
      occurred_at: value('evAt'),
    });
    await refreshPath('已记入这条日志');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.openRun', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程', true);
    return;
  }
  try {
    state.pilot.runOptions = await GET(`/pilot/rpa-run-options?process_id=${detail.process_id}`);
    state.pilot.runOpen = true;
    repaintPilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveRun', async () => {
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const botId = Number(value('runBot'));
  const endpointId = Number(value('runEndpoint'));
  if (!botId || !endpointId || !value('runAt') || !value('runOutcome')) {
    toast('先选择机器人、结果、时间和集成端点', true);
    return;
  }
  try {
    await POST('/pilot/rpa-runs', {
      bot_id: botId,
      ran_at: value('runAt'),
      outcome: value('runOutcome'),
      endpoint_id: endpointId,
      note: value('runNote'),
    });
    await refreshPath('已记下这次运行');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.openCase', async () => {
  try {
    await loadUsers();
    state.pilot.caseOpen = true;
    repaintPilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveCase', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const ownerId = Number(value('caseOwner'));
  if (!value('caseTitle') || !value('caseSituation') || !ownerId) {
    toast('标题、情形和责任人都要写上', true);
    return;
  }
  try {
    await POST('/pilot/cases', {
      process_id: detail.process_id,
      title: value('caseTitle'),
      situation: value('caseSituation'),
      owner_user_id: ownerId,
    });
    await refreshPath('已登记案例');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.openTech', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程', true);
    return;
  }
  try {
    await loadUsers();
    state.pilot.techKinds = await GET('/pilot/technology-kinds');
    state.pilot.techOpen = true;
    repaintPilot();
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveTech', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const ownerId = Number(value('techOwner'));
  if (!value('techKind') || !value('techName') || !value('techNote') || !ownerId) {
    toast('种类、名称、用在哪一段和责任人都要写上', true);
    return;
  }
  try {
    await POST('/pilot/technology-uses', {
      process_id: detail.process_id,
      kind: value('techKind'),
      name: value('techName'),
      usage_note: value('techNote'),
      owner_user_id: ownerId,
    });
    await refreshPath('已登记技术用途');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveRpa', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程，机器人记不到某一条 L3 上', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const ownerId = Number(value('rpaOwner'));
  if (!ownerId) {
    toast('先选择责任人', true);
    return;
  }
  try {
    await POST('/pilot/rpa', {
      process_id: detail.process_id,
      activity_name: value('rpaActivity'),
      bot_name: value('rpaBot'),
      manual_step: value('rpaManual'),
      owner_user_id: ownerId,
    });
    const updated = await GET(`/pilot/paths/${detail.id}`);
    state.pilot.data = updated;
    paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
    toast('已登记机器人');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.openTraining', async () => {
  try {
    await loadUsers();
    state.pilot.trainingOpen = true;
    const detail = state.pilot.data;
    if (detail) paint({ detail, paths: state.pilot.paths, meta: state.pilot.meta });
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.saveTraining', async () => {
  const detail = state.pilot.data;
  if (!detail || !detail.process_id) {
    toast('这条路径还没有挂上流程，培训到场记不到某一条 L3 上', true);
    return;
  }
  const value = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const traineeId = Number(value('trTrainee'));
  if (!traineeId) {
    toast('先选择听课人', true);
    return;
  }
  if (!value('trDate')) {
    toast('先填写完成日期', true);
    return;
  }
  try {
    await POST('/pilot/training', {
      process_id: detail.process_id,
      trainee_user_id: traineeId,
      topic: value('trTopic'),
      completed_on: value('trDate'),
    });
    const updated = await GET(`/pilot/paths/${detail.id}`);
    state.pilot.data = updated;
    paint({ detail: updated, paths: state.pilot.paths, meta: state.pilot.meta });
    toast('已登记培训到场');
  } catch (e) {
    toast(e.message, true);
  }
});

on('pilot.evidence', ({ view, params }) => {
  if (!view) return;
  go(view, { params: scopedParams(view, params), push: true });
});

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
    { title: '删除十层路径', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await DEL(`/pilot/paths/${detail.id}`);
    state.pilot.pathId = null;
    state.pilot.layerNo = null;
    toast('路径已删除');
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
  const preferred = Number(state.pilot.pendingProcess) || 0;
  const options = processes.filter((row) => row.level === 3 || row.level === 4)
    .map((row) => `<option value="${row.id}"${row.id === preferred ? ' selected' : ''}>L${
      row.level} ${esc(row.code)} ${esc(row.name)}</option>`)
    .join('');
  openModal('新建十层路径', `
    <div class="field"><label>关联流程 *</label>
      <select id="plProcess"><option value="">请选择 L3/L4 流程</option>${options}</select></div>
    <div class="field"><label>负责人</label>
      <select id="plOwner"><option value="">当前用户</option>${userOptions(users)}</select></div>
    <div class="note">路径名就是流程名。一条流程只建一条十层路径。退出门读已有证据，不会新建证据，也不会推动「体系总览」的公司阶段。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="pilot.savePath">创建</button>`);
}

on('pilot.savePath', async () => {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const processId = val('plProcess');
  if (!processId) return toast('请选择关联流程', true);
  try {
    const detail = await POST('/pilot/paths', {
      process_id: Number(processId),
      owner_user_id: val('plOwner') ? Number(val('plOwner')) : null,
    });
    closeModal();
    state.pilot.pathId = detail.id;
    state.pilot.layerNo = detail.current_layer;
    state.pilot.pendingProcess = null;
    toast('路径已创建');
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

let applicabilityForm = null;
on('pilot.editApplicability', () => {
  const detail = state.pilot.data;
  const layer = detail?.layers.find(row => row.layer_no === 6);
  if (!layer || !canManage()) return;
  const labels = state.pilot.meta.applicability_labels;
  const gen = openModal('表单/工具适用性', `<p class="note">只核对原第6层参考项，不能豁免核心发布与执行准备；技术登记不代表业务成功。</p>${layer.evidence_items.map(item => `<div class="field"><label>${esc(item.label)}</label><select id="paMode-${esc(item.key)}">${Object.entries(labels).map(([mode, label]) => `<option value="${mode}"${mode === item.applicability ? ' selected' : ''}>${esc(label)}</option>`).join('')}</select><textarea id="paReason-${esc(item.key)}">${esc(item.applicability_reason)}</textarea></div>`).join('')}`,
    '<button class="btn btn-g" data-act="ui.close">取消</button><button class="btn btn-p" data-act="pilot.saveApplicability">保存适用性</button>', true);
  applicabilityForm = { pathId: detail.id, revision: layer.applicability_revision, layer, gen, busy: false };
});
on('pilot.saveApplicability', async () => {
  const c = applicabilityForm;
  if (!c || !modalAlive(c.gen) || state.view !== 'pilot' || Number(state.pilot.pathId) !== c.pathId || Number(urlParams().path) !== c.pathId || state.pilot.data?.id !== c.pathId) return toast('路径上下文已变化，请重新打开适用性', true);
  if (c.busy) return;
  const requirements = Object.fromEntries(c.layer.evidence_items.map(item => [item.key, {
    mode: document.getElementById('paMode-' + item.key).value,
    reason: document.getElementById('paReason-' + item.key).value.trim(),
  }]));
  c.busy = true;
  try {
    await PUT('/pilot/paths/' + c.pathId + '/layers/6/applicability', { expected_revision: c.revision, requirements });
    if (modalAlive(c.gen)) closeModal();
    if (state.view === 'pilot' && Number(state.pilot.pathId) === c.pathId && Number(urlParams().path) === c.pathId && state.pilot.data?.id === c.pathId) RENDERERS.pilot();
    toast('原层适用性已保存');
  } catch (e) { toast(e.message, true); }
  finally { c.busy = false; }
});

function evidenceList(layer) {
  return layer.evidence_items.map((item) => {
    const tone = item.met ? 'ok' : item.required ? 'miss' : 'opt';
    const suffix = item.met ? '' : item.required ? ' · 还缺' : ' · 建议关注';
    const params = new URLSearchParams(item.view_params || {}).toString();
    const title = item.view ? `打开证据：${item.label}` : item.label;
    const value = item.view
      ? `<button type="button" class="ev-jump" data-act="pilot.evidence"
           data-view="${esc(item.view)}"${params ? ` data-params="${esc(params)}"` : ''}
           title="${esc(title)}">${item.value}</button>`
      : `<b>${item.value}</b>`;
    return `
      <div class="between pilot-line ${tone}">
        <span>${item.met ? '✓' : '○'} ${esc(item.label)}${suffix}
          <small>${esc(item.applicability_label)} · ${esc(item.applicability_reason)}</small></span>
        ${value}
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
        <div class="pilot-kicker">本层要核对的记录</div>
        <span class="tiny muted">生效制度 ${resources.documents.length} ·
          规则 ${resources.rules.length} · 例外 ${resources.exceptions.length}</span>
      </div>
      <div class="pilot-resources">
        <div class="pilot-step"><span class="ev-h">已生效制度/SOP</span>${docs}</div>
        <div class="pilot-step"><span class="ev-h">授权规则</span>${rules}</div>
        <div class="pilot-step"><span class="ev-h">例外台账</span>${exceptions}</div>
      </div>
    </div>`;
}

function charterBox(detail) {
  const form = state.pilot.charterForm;
  if (!form || !detail) return '';
  const saved = (form.charters || []).find(
    (row) => Number(row.process_id) === Number(detail.process_id),
  ) || null;
  const proc = (form.processes || []).find(
    (row) => Number(row.id) === Number(detail.process_id),
  );
  const users = (form.users || []).map((row) => `
    <option value="${row.id}"${
      saved && String(row.id) === String(saved.sponsor_user_id) ? ' selected' : ''
    }>${esc(row.display_name)}</option>`).join('');
  const field = (id, label, value) => `
    <div class="field"><label for="${id}">${label}</label>
      <input id="${id}" maxlength="500" value="${esc(value || '')}"></div>`;
  const ownerNote = !detail.process_id
    ? '<div class="note mb">这条路径还没有挂上流程。新建路径时要选一条 L3，起止才能记到那条流程上。</div>'
    : proc && !proc.has_owner
      ? '<div class="note mb">这条 L3 还没有负责人。先到流程地图指定负责人，再保存起止。</div>'
      : '';
  return `
    <div class="pilot-section" id="charterBox">
      <h4>这条流程的起止</h4>
      ${ownerNote}
      <div class="tiny muted mb">${esc(detail.process_code || '')} ${esc(detail.process_name || '')}</div>
      ${field('chPurpose', '为什么做', saved && saved.purpose)}
      ${field('chStart', '从哪里开始', saved && saved.starts_at)}
      ${field('chEnd', '到哪里结束', saved && saved.ends_at)}
      ${field('chIn', '做什么', saved && saved.in_scope)}
      ${field('chOut', '不做什么', saved && saved.out_of_scope)}
      ${field('chStop', '什么情况停', saved && saved.stop_condition)}
      <div class="field"><label for="chSponsor">发起人（有权批准范围）</label>
        <select id="chSponsor">${users}</select></div>
      <button class="btn btn-p" data-act="pilot.saveCharter">保存范围说明</button>
    </div>`;
}

function rpaBox(detail) {
  if (!state.pilot.rpaOpen) return '';
  if (!detail.process_id) {
    return '<div class="note mb">这条路径还没有挂上流程，机器人记不到某一条 L3 上。</div>';
  }
  const users = userOptions(state.pilot.users || [], null);
  return `
    <div class="pilot-section" id="rpaBox">
      <h4>登记机器人</h4>
      <div class="tiny muted mb">${esc(detail.process_code || '')} ${esc(detail.process_name || '')}</div>
      <div class="field"><label for="rpaActivity">哪一步由机器人做</label>
        <input id="rpaActivity" placeholder="例如：核对入库单字段"></div>
      <div class="field"><label for="rpaBot">机器人名称</label>
        <input id="rpaBot" placeholder="例如：入库单核对机器人"></div>
      <div class="field"><label for="rpaManual">替掉的人工操作</label>
        <textarea id="rpaManual" rows="2" placeholder="原来由人打开系统、逐项核对的哪一段"></textarea></div>
      <div class="field"><label for="rpaOwner">责任人</label>
        <select id="rpaOwner">${users}</select></div>
      <button class="btn btn-p" data-act="pilot.saveRpa">保存机器人</button>
    </div>`;
}

function eventBox(detail) {
  if (!state.pilot.eventOpen) return '';
  if (!detail.process_id) {
    return '<div class="note mb">这条路径还没有挂上流程，日志记不到某一条 L3 上。</div>';
  }
  return `
    <div class="pilot-section" id="eventBox">
      <h4>记一条外部日志</h4>
      <div class="tiny muted mb">写进来源、案例号、活动和发生时间。挖掘会读这些行。
        这里不会自动去 ERP 或 OA 拉取。</div>
      <div class="field"><label for="evSource">来源</label>
        <input id="evSource" placeholder="例如：ERP 采购订单"></div>
      <div class="field"><label for="evCase">案例号</label>
        <input id="evCase" placeholder="同一条路径用同一个案例号"></div>
      <div class="field"><label for="evActivity">活动</label>
        <input id="evActivity" placeholder="例如：创建采购订单"></div>
      <div class="field"><label for="evAt">发生时间（UTC）</label>
        <input id="evAt" type="datetime-local"></div>
      <button class="btn btn-p" data-act="pilot.saveEvent">保存这条日志</button>
    </div>`;
}

function runBox(detail) {
  if (!state.pilot.runOpen) return '';
  const options = state.pilot.runOptions || { bots: [], endpoints: [], outcomes: [] };
  if (!options.bots.length) {
    return '<div class="note mb">先登记机器人，再记一次运行。</div>';
  }
  if (!options.endpoints.length) {
    return '<div class="note mb">还没有集成端点。先登记一个端点，再把这次运行挂上去。</div>';
  }
  const bots = options.bots.map((row) =>
    `<option value="${row.id}">${esc(row.bot_name)} · ${esc(row.activity_name)}</option>`).join('');
  const endpoints = options.endpoints.map((row) =>
    `<option value="${row.id}">${esc(row.name)} · ${esc(row.kind)} · ${esc(row.status_label)}</option>`).join('');
  const outcomes = options.outcomes.map((row) =>
    `<option value="${esc(row.code)}">${esc(row.label)}</option>`).join('');
  return `
    <div class="pilot-section" id="runBox">
      <h4>登记一次运行</h4>
      <div class="tiny muted mb">${esc(detail.process_code || '')} ${esc(detail.process_name || '')}
        这是记下的一次结果，并指向已有的集成端点。这里不代替机器人去执行。</div>
      <div class="field"><label for="runBot">机器人</label><select id="runBot">${bots}</select></div>
      <div class="field"><label for="runOutcome">结果</label><select id="runOutcome">${outcomes}</select></div>
      <div class="field"><label for="runAt">运行时间（UTC）</label>
        <input id="runAt" type="datetime-local"></div>
      <div class="field"><label for="runEndpoint">集成端点</label>
        <select id="runEndpoint">${endpoints}</select></div>
      <div class="field"><label for="runNote">备注</label>
        <input id="runNote" placeholder="这次替掉了哪一段，可空"></div>
      <button class="btn btn-p" data-act="pilot.saveRun">保存这次运行</button>
    </div>`;
}

function caseBox(detail) {
  if (!state.pilot.caseOpen) return '';
  if (!detail.process_id) {
    return '<div class="note mb">这条路径还没有挂上流程。</div>';
  }
  const users = userOptions(state.pilot.users || [], null);
  return `
    <div class="pilot-section" id="caseBox">
      <h4>登记案例</h4>
      <div class="tiny muted mb">没有固定步骤顺序的一件事：标题、当时的情形、责任人。</div>
      <div class="field"><label for="caseTitle">标题</label>
        <input id="caseTitle" placeholder="例如：供应商资质临时例外"></div>
      <div class="field"><label for="caseSituation">情形</label>
        <textarea id="caseSituation" rows="2" placeholder="当时发生了什么，为什么不能按固定步骤走"></textarea></div>
      <div class="field"><label for="caseOwner">责任人</label>
        <select id="caseOwner">${users}</select></div>
      <button class="btn btn-p" data-act="pilot.saveCase">保存案例</button>
    </div>`;
}

function techBox(detail) {
  if (!state.pilot.techOpen) return '';
  if (!detail.process_id) {
    return '<div class="note mb">这条路径还没有挂上流程。</div>';
  }
  const kinds = (state.pilot.techKinds || []).map((row) =>
    `<option value="${esc(row.code)}">${esc(row.label)}</option>`).join('');
  const users = userOptions(state.pilot.users || [], null);
  return `
    <div class="pilot-section" id="techBox">
      <h4>登记技术用途</h4>
      <div class="tiny muted mb">写下区块链、人工智能或物联网具体用在这条流程的哪一段。
        这是一条记录，不是已经接通的外部系统。</div>
      <div class="field"><label for="techKind">种类</label><select id="techKind">${kinds}</select></div>
      <div class="field"><label for="techName">名称</label>
        <input id="techName" placeholder="例如：入库照片识别"></div>
      <div class="field"><label for="techNote">用在哪一段</label>
        <textarea id="techNote" rows="2" placeholder="哪一步用它，替掉或补充了什么"></textarea></div>
      <div class="field"><label for="techOwner">责任人</label>
        <select id="techOwner">${users}</select></div>
      <button class="btn btn-p" data-act="pilot.saveTech">保存技术用途</button>
    </div>`;
}

function trainingBox(detail) {
  if (!state.pilot.trainingOpen) return '';
  if (!detail.process_id) {
    return '<div class="note mb">这条路径还没有挂上流程，培训到场记不到某一条 L3 上。</div>';
  }
  const users = userOptions(state.pilot.users || [], null);
  return `
    <div class="pilot-section" id="trainingBox">
      <h4>登记培训到场</h4>
      <div class="tiny muted mb">${esc(detail.process_code || '')} ${esc(detail.process_name || '')}</div>
      <div class="field"><label for="trTopic">课题</label>
        <input id="trTopic" placeholder="例如：这条流程的起止和停止条件"></div>
      <div class="field"><label for="trTrainee">听课人</label>
        <select id="trTrainee">${users}</select></div>
      <div class="field"><label for="trDate">完成日期</label>
        <input id="trDate" type="date"></div>
      <button class="btn btn-p" data-act="pilot.saveTraining">保存到场记录</button>
    </div>`;
}

function workBand(detail, layer) {
  const parts = [
    layer.resources ? layerResources(layer.resources) : '',
    layer.layer_no === 2 ? charterBox(detail) : '',
    layer.layer_no === 6
      ? (canManage() ? '<button class="btn-sm" data-act="pilot.editApplicability">维护工具适用性</button>' : '') + rpaBox(detail) + eventBox(detail) + runBox(detail) + caseBox(detail) + techBox(detail)
      : '',
    layer.layer_no === 10 ? trainingBox(detail) : '',
  ].join('');
  if (!parts.trim()) return '';
  return `<div class="pilot-work">${parts}</div>`;
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
  const flowStep = (no, label, items) => `
    <div class="pilot-step">
      <span class="pilot-step-no">${no}</span>
      <span class="ev-h">${label}</span>
      ${items.map((item) => `<div class="pilot-bullet">${esc(item)}</div>`).join('')}
    </div>`;
  return `
    <div class="card pilot-workspace">
      <div class="pilot-head">
        <div>
          <div class="tiny muted">第 ${layer.layer_no} 层${isCurrent ? ' · 当前层' : ''}</div>
          <h3>${esc(layer.title)}</h3>
          <p class="pilot-goal">${esc(layer.goal)}</p>
        </div>
        ${statusTag(LAYER_TONE[layer.status], layer.status_label)}
      </div>

      <section class="pilot-band" aria-label="这一层怎么走">
        <div class="pilot-kicker">1 这一层怎么走</div>
        <div class="pilot-three">
          ${flowStep(1, '输入', layer.inputs)}
          <div class="pilot-arrow" aria-hidden="true">→</div>
          ${flowStep(2, '处理', layer.process)}
          <div class="pilot-arrow" aria-hidden="true">→</div>
          ${flowStep(3, '输出', layer.outputs)}
        </div>
      </section>

      <section class="pilot-gate ${layer.gate_open ? 'is-open' : 'is-wait'}" aria-label="退出条件">
        <div class="between mb">
          <div class="pilot-kicker">2 对退出条件</div>
          ${layer.gate_open ? '<span class="tag t-grn">退出门已满足</span>'
            : `<span class="tag t-yel">还差 ${missing.length} 项</span>`}
        </div>
        <p class="pilot-exit">${esc(layer.exit_criteria)}</p>
        ${evidenceList(layer)}
      </section>

      ${workBand(detail, layer)}

      <div class="pilot-record">
        <section class="pilot-section" aria-label="本层备注">
          <div class="between mb">
            <div class="pilot-kicker">3 记下这一层</div>
            <span class="tiny muted">摘要会出现在前置层</span>
          </div>
          <div class="field"><label>上下文摘要</label>
            <input id="plContext" value="${esc(layer.context_summary || '')}"
              placeholder="一句话说明本层已经确认了什么"></div>
          <div class="field"><label>备注</label>
            <textarea id="plNotes" rows="2"
              placeholder="待补事项、风险、决策记录">${esc(layer.notes || '')}</textarea></div>
          <button class="btn-sm" data-act="pilot.saveLayer">保存本层备注</button>
        </section>
        <div class="pilot-follow">
          <section class="pilot-section" aria-label="待办">
            <div class="between mb">
              <h4>待办（${layer.tasks.length}）</h4>
              <button class="btn-sm" data-act="pilot.newTask">+ 新增待办</button>
            </div>
            ${taskRows(layer)}
          </section>
          <section class="pilot-section" aria-label="异常与改善">
            <div class="between mb">
              <h4>异常与改善（${layer.issues.length}）</h4>
              <button class="btn-sm" data-act="pilot.newIssue">+ 新增异常</button>
            </div>
            ${issueRows(layer)}
          </section>
        </div>
      </div>

      <div class="pilot-section">
        <div class="pilot-kicker">去相关页面</div>
        <div class="gap">
          ${layer.actions.map((action) => `<button class="btn btn-g"
            ${actionAttrs(action)} data-view="${esc(action.view)}"
            title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
        </div>
      </div>

      <div class="pilot-advance">
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
        <h2>十层核对<span class="module-badge">这条会不会跑</span></h2>
        <div class="desc">退出门按本流程计数，与「体系总览」的公司能力门拆开。新建路径不造证据、不推公司阶段。</div>
      </div>
      <div class="card">
        <div class="empty">还没有路径。选一条 L3/L4，按本流程建十层核对。</div>
        <div class="gap mt"><button class="btn btn-p" data-act="pilot.newPath">+ 新建路径</button></div>
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
  const pathLabel = (path) => {
    const process = [path.process_code, path.process_name].filter(Boolean).join(' ');
    return process || path.name;
  };
  const options = paths.map((path) =>
    `<option value="${path.id}"${path.id === detail.id ? ' selected' : ''}>${
      esc(pathLabel(path))} · 第${path.current_layer}层</option>`).join('');

  const shell = pageShell({
    title: '十层核对',
    badge: '<span class="module-badge">这条会不会跑</span>',
    subtitle: `${esc(pathLabel(detail))} · Owner ${esc(detail.owner || '—')} · 一次只看一层`,
    tip: tipHelp(
      '退出门按本流程（及祖先链）计数；点数字打开记录。公司能力齐不齐，看「体系总览」。',
      '十层说明',
    ),
    actions: `<select class="sel sel-sm" data-act="pilot.selectPath">${options}</select>
      <button class="btn-sm" data-act="ui.copyLink">复制链接</button>
      <button class="btn btn-p" data-act="pilot.newPath">+ 新建路径</button>`,
    sections: [{
      key: 'main',
      html: `
        <div class="card">
          <div class="between">
            <div class="gap">
              ${statusTag('t-blu', detail.status_label)}
              <span class="tag t-gry">当前第 ${detail.current_layer} 层 · ${esc(detail.current_layer_title || '')}</span>
              <span class="tag ${detail.progress >= 100 ? 't-grn' : 't-yel'}">
                可退出 ${num(detail.progress, 0)}%</span>
              <span class="tiny muted">${esc(detail.baseline_version)} → ${esc(detail.draft_version)}</span>
            </div>
            <button class="btn-sm" data-act="pilot.deletePath">删除路径</button>
          </div>
          <div class="pipe" style="margin-top:10px">
            <i class="fill-ok" style="width:${detail.progress}%"></i>
          </div>
        </div>
        <div class="pilot-shell">
          <aside class="pilot-side">
            <div class="card pilot-nav">
              <div class="tiny muted" style="margin-bottom:8px">十层导航</div>
              <div class="pilot-nav-list">${layerStrip(detail, layer.layer_no)}</div>
            </div>
          </aside>
          <main class="pilot-main">${workspace(detail, layer)}</main>
          <aside class="pilot-aside">
            ${contextList(detail, layer.layer_no)}
            ${nextList(detail, layer.layer_no)}
          </aside>
        </div>`,
    }],
    active: 'main',
    mode: 'plain',
  });
  viewEl().innerHTML = shell.html;
}

const renderPilot = () => {
  renderAsync(
    'pilot',
    async () => {
      const params = urlParams();
      if (params.process) state.pilot.pendingProcess = Number(params.process) || null;
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
