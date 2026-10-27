/* 视图：workflow —— 五阶段项目工作台 + 标准方法手册
 *
 * 默认是「项目工作台」：当前阶段、步骤闭环、证据门槛与推进条件；
 * 「五阶段步骤 / 方法论匹配」保留为全公司共用的方法手册视图。
 */
import { esc, num, CAT_ICON, methodTag, skeleton, TOOL_LEVEL_TONE } from '../core/format.js';
import { openModal, closeModal, toast, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { GET, PATCH, POST } from '../core/api.js';
import { canWrite } from '../core/auth.js';
import { openTemplateCopy } from '../core/template-copy.js';
import { renderRecommendation } from './shared/recommendation.js';
import { actions } from '../core/actions.js';

const STAGE_COLORS = [
  'var(--stage-1)', 'var(--stage-2)', 'var(--stage-3)', 'var(--stage-4)', 'var(--stage-5)',
];
const WB_TONE = {
  PENDING: 't-gry', IN_PROGRESS: 't-yel', PENDING_VERIFY: 't-blu',
  DONE: 't-grn', BLOCKED: 't-red', DECISION: 't-pur', SKIPPED: 't-gry',
};

/* -------------------------------------------------- 事件 */

on('workflow.tab', ({ tab }) => setWfTab(tab));
on('workflow.stage', ({ stage }) => setWfStage(Number(stage)));
on('workflow.project', (_data, el) => setWfProject(el.value ? Number(el.value) : null));
on('workflow.refresh', () => RENDERERS.workflow());
on('workflow.step', ({ step }) => openWfStep(step));
on('workflow.editStep', ({ id }) => openStepModal(Number(id)));
on('workflow.saveStep', ({ id }) => saveStep(Number(id)));
on('workflow.editCondition', ({ id }) => openConditionModal(Number(id)));
on('workflow.saveCondition', ({ id }) => saveCondition(Number(id)));
on('workflow.newCondition', () => openNewConditionModal());
on('workflow.createCondition', () => createCondition());
on('workflow.advance', () => advanceStage());
on('workflow.tenLayer', () => go('pilot', {
  params: { project: state.workflow.projectId || '', stage: state.workflow.stage || '' },
  push: true,
}));
on('workflow.close', () => closeModal());
on('workflow.openTool', ({ code }) => {
  closeModal();
  actions['toolbox.openTool'](code);
});
on('workflow.goProjects', () => go('projects'));
on('workflow.goKnowledge', ({ step, scenario }) => {
  closeModal();
  go('knowledge', {
    params: { step: step || '', scenario: scenario || '', sort: 'match' },
    push: true,
  });
});
on('workflow.toolboxStep', () => {
  closeModal();
  openToolboxForStep();
});
on('workflow.goDeliverables', () => {
  closeModal();
  go('deliverables');
});
on('workflow.copyTemplate', ({ id }) => {
  closeModal();
  openTemplateCopy(Number(id));
});

/* -------------------------------------------------- 入口 */

const renderWorkflow = () => {
  const params = urlParams();
  const wf = state.workflow || (state.workflow = {
    tab: 'workbench', projectId: null, stage: null,
  });
  if (params.tab) wf.tab = params.tab;
  if (params.project) wf.projectId = Number(params.project);
  if (params.stage) {
    if (wf.tab === 'workbench') wf.stage = Number(params.stage);
    else wf.stepStage = Number(params.stage);
  }
  if (!wf.tab) wf.tab = 'workbench';

  if (wf.tab === 'workbench') return renderWorkbench(wf);
  return renderManual(wf);
};

function syncWorkflowUrl() {
  const wf = state.workflow || {};
  setUrlState('workflow', {
    tab: wf.tab,
    project: wf.projectId || '',
    stage: wf.tab === 'workbench' ? (wf.stage || '') : (wf.stepStage || ''),
  }, { push: false });
}

function setWfTab(tab) {
  state.workflow = state.workflow || {};
  state.workflow.tab = tab;
  if (tab === 'steps' || tab === 'method') state.workflow.stepStage = state.workflow.stepStage || 1;
  syncWorkflowUrl();
  RENDERERS.workflow();
}

function setWfProject(projectId) {
  state.workflow.projectId = projectId;
  state.workflow.stage = null;
  syncWorkflowUrl();
  RENDERERS.workflow();
}

function setWfStage(stage) {
  if (state.workflow.tab === 'workbench') state.workflow.stage = stage;
  else state.workflow.stepStage = stage;
  syncWorkflowUrl();
  RENDERERS.workflow();
}

/* -------------------------------------------------- 项目工作台 */

function renderWorkbench(wf) {
  return renderAsync('workflow',
    async () => {
      const page = await GET('/projects?page_size=200');
      const projects = page.items || [];
      let projectId = Number(wf.projectId) || (projects[0] ? projects[0].id : null);
      if (!projects.some((row) => row.id === projectId)) {
        projectId = projects[0] ? projects[0].id : null;
      }
      wf.projectId = projectId;
      const query = wf.stage ? '?stage_no=' + wf.stage : '';
      const data = projectId ? await GET('/projects/' + projectId + '/workflow' + query) : null;
      if (data) wf.stage = data.viewing_stage;
      return { projects, data };
    },
    (d) => paintWorkbench(d, state.workflow));
}

function paintWorkbench(d, wf) {
  const projects = d.projects || [];
  const data = d.data;
  state.wfWorkbench = data;
  const projectOptions = projects.map((row) =>
    `<option value="${row.id}"${row.id === wf.projectId ? ' selected' : ''}>${
      esc(row.code)} · ${esc(row.name)}</option>`).join('');
  const tabs = workflowTabs('workbench');
  const head = `
    <div class="card page-head">
      <div class="between">
        <div><h2>五阶段标准工作流<span class="module-badge">项目工作台 · 证据门槛</span></h2>
          <div class="desc">首屏回答：当前在哪、下一步做什么、为什么能/不能推进</div></div>
        <div class="gap">
          ${projects.length ? `<select class="sel sel-sm" data-act="workflow.project">
            <option value="">选择项目</option>${projectOptions}</select>` : ''}
          ${tabs}
        </div>
      </div>
    </div>`;
  if (!projects.length) {
    viewEl().innerHTML = head + `<div class="card"><div class="empty">
      还没有项目。先到 <a class="link" data-act="workflow.goProjects">流程项目组合</a> 立项，
      工作台会按五阶段展开当前阶段与退出门槛。</div></div>`;
    return;
  }
  if (!data) {
    viewEl().innerHTML = head + '<div class="card"><div class="empty">项目数据加载失败。</div></div>';
    return;
  }
  const p = data.project;
  const stage = data.current_stage;
  const gate = data.gate;
  const readOnly = data.read_only;
  const stageNav = data.stages.map((row) => {
    const viewing = row.stage_no === data.viewing_stage;
    const isCurrent = row.stage_no === data.project.current_stage;
    return `<li class="wb-stage-node ${row.status}${viewing ? ' viewing' : ''}">
      <button class="wb-stage-link" type="button" data-act="workflow.stage"
        data-stage="${row.stage_no}" ${isCurrent ? 'aria-current="step"' : ''}>
        <span class="wb-dot" aria-hidden="true">${row.status === 'complete' ? '✓' : row.stage_no}</span>
        <span><b>阶段${row.stage_no} · ${esc(row.name)}</b><small>${esc(row.status_label)}
          · ${row.done_count}/${row.step_count} 步已满足</small></span>
      </button></li>${row.stage_no < 5 ? '<li class="wb-connector" aria-hidden="true"></li>' : ''}`;
  }).join('');

  const hasInProgress = data.steps.some((step) => step.status === 'IN_PROGRESS');
  const stepCards = data.steps.map((step, index) => {
    const statusLabel = step.status_label || step.status;
    const evidence = (step.evidence || []).length
      ? step.evidence.map(esc).join('；') : '—';
    const inputs = (step.inputs || []).length ? step.inputs.map(esc).join('、') : '—';
    const process = (step.process_steps || []).length
      ? step.process_steps.map((item) => `<li>${esc(item)}</li>`).join('')
      : '<li class="muted">尚未填写处理要点</li>';
    const tools = (step.tools || []).length
      ? `<details class="wb-fold"><summary>推荐工具（${step.tools.length}）</summary>
          <div class="wb-fold-body">${step.tools.map((tool) =>
            `<span class="tag t-blu">${esc(tool)}</span>`).join(' ')}</div></details>` : '';
    const blocker = step.status === 'BLOCKED'
      ? `<div class="wb-alert">受阻：${esc(step.blocked_reason || '—')}
          · 责任人 ${esc(step.blocked_owner || '—')}
          ${step.blocked_due ? ' · 预计解除 ' + esc(step.blocked_due) : ''}</div>` : '';
    const decision = step.status === 'DECISION'
      ? `<div class="wb-alert wb-alert-decision">需决策：${(step.decision_options || []).map(esc).join(' / ') || '—'}
          · 决策人 ${esc(step.decision_maker || '—')}
          ${step.decision_due ? ' · 时限 ' + esc(step.decision_due) : ''}</div>` : '';
    const open = step.status === 'IN_PROGRESS' || (!hasInProgress && index === 0);
    const summaryText = step.next_action
      ? `下一步：${step.next_action}`
      : (step.goal || '尚未填写目标');
    const counts = `${(step.evidence || []).length} 项证据 · ${(step.tools || []).length} 个工具`;
    return `<li class="wb-tl-item st-${esc(step.status)}${
      step.status === 'IN_PROGRESS' ? ' current' : ''}">
      <div class="wb-tl-rail" aria-hidden="true">
        <span class="wb-tl-dot">${step.status === 'DONE' ? '✓' : esc(step.step_no.split('.').pop())}</span>
      </div>
      <details class="wb-tl-card"${open ? ' open' : ''}>
        <summary class="wb-tl-head">
          <span class="wb-tl-title"><b>${esc(step.step_no)} ${esc(step.name)}</b>
            <small>${esc(summaryText)}</small></span>
          <span class="tag ${WB_TONE[step.status] || 't-gry'}">${esc(statusLabel)}</span>
          <span class="wb-tl-meta">${esc(step.owner || '未指定')} · ${counts}</span>
          <span class="wb-tl-chev" aria-hidden="true">⌄</span>
        </summary>
        <div class="wb-tl-body">
          <p><strong>目标：</strong>${esc(step.goal || '—')}</p>
          <div class="wb-meta">
            <div><label>输入</label><span>${inputs}</span></div>
            <div><label>输出</label><span>${esc(step.output || '—')}</span></div>
            <div><label>验收证据</label><span>${evidence}</span></div>
            <div><label>责任人 / 下一步</label><span>${esc(step.owner || '—')}
              → ${esc(step.next_action || '—')}</span></div>
          </div>
          <details class="wb-fold"><summary>处理要点（${(step.process_steps || []).length}）</summary>
            <ul class="wb-fold-body">${process}</ul></details>
          ${tools}
          ${blocker}${decision}
          ${!readOnly && canWrite() ? `<div class="wb-tl-act">
            <button class="btn-sm" data-act="workflow.editStep" data-id="${step.id}">更新状态 / 证据</button>
          </div>` : ''}
        </div>
      </details>
    </li>`;
  }).join('') || '<div class="empty">当前阶段还没有步骤模板。</div>';

  const conditionRows = gate.conditions.map((row) => `
    <li class="wb-condition ${row.is_met ? 'met' : 'open'}">
      <span class="wb-cond-icon" aria-hidden="true">${row.is_met ? '✓' : '!'}</span>
      <div>
        <strong>${esc(row.text)}</strong>
        <div class="tiny">${esc(row.evidence || '尚未填写证据')}
          ${row.owner ? ' · 责任人 ' + esc(row.owner) : ''}
          ${row.due_date ? ' · 截止 ' + esc(row.due_date) : ''}</div>
        <div class="tiny muted">${row.is_met ? '已满足' : '未满足'}
          ${row.met_by ? ' · ' + esc(row.met_by) : ''}</div>
      </div>
      ${!readOnly && canWrite() ? `<button class="btn-sm" data-act="workflow.editCondition"
        data-id="${row.id}">更新</button>` : ''}
    </li>`).join('') || '<li class="tiny muted">本阶段还没有配置门槛条件。</li>';

  const blockHtml = gate.block_reasons.length
    ? `<div class="wb-alert"><strong>当前不能推进：</strong>
        <ul>${gate.block_reasons.map((reason) => `<li>${esc(reason)}</li>`).join('')}</ul></div>`
    : '<div class="note">所有关键门槛已满足，可进入下一阶段。</div>';

  const prev = data.previous;
  const next = data.next;
  viewEl().innerHTML = `${head}
    <div class="wb-layout">
      <aside class="wb-stage-side">
        <nav class="card wb-progress" aria-label="项目阶段">
          <div class="wb-eyebrow">阶段</div>
          <ol class="wb-progress-list wb-progress-vertical">${stageNav}</ol>
        </nav>
      </aside>
      <main class="card wb-main">
        <div class="wb-stage-head">
          <span class="wb-pulse">${readOnly ? '只读快照' : '当前决策：' + esc(stage ? stage.summary : '')}</span>
          <h2>阶段${data.viewing_stage}：${esc(stage ? stage.name : '')}</h2>
          <p>${esc((stage && stage.goal) || '')}</p>
          <div class="tiny muted">项目 ${esc(p.code)} · ${esc(p.name)} · Owner ${esc(p.owner)}
            · ${esc(p.status_label)}${readOnly ? ' · 这是历史阶段只读视图' : ''}</div>
        </div>
        <section class="wb-section">
          <div class="wb-eyebrow">上一阶段结果（折叠）</div>
          <details class="wb-fold"><summary>${esc(prev.name || '没有上一阶段')}</summary>
            <div class="wb-fold-body">${prev.items.length
              ? prev.items.map((item) => `<div class="tiny">• ${esc(item)}</div>`).join('')
              : '<div class="tiny muted">—</div>'}</div></details>
        </section>
        <section class="wb-section">
          <div class="wb-eyebrow">当前阶段步骤</div>
          ${data.steps.length
            ? `<ol class="wb-timeline">${stepCards}</ol>`
            : '<div class="empty">当前阶段还没有步骤模板。</div>'}
        </section>
        <section class="wb-section">
          <div class="wb-eyebrow">下一阶段进入条件（折叠）</div>
          <details class="wb-fold"><summary>${esc(next.name || '已是最后阶段')}</summary>
            <div class="wb-fold-body">${next.items.length
              ? next.items.map((item) => `<div class="tiny">• ${esc(item)}</div>`).join('')
              : '<div class="tiny muted">—</div>'}</div></details>
        </section>
      </main>
      <aside class="wb-side">
        <section class="card wb-gate">
          <div class="wb-eyebrow">阶段退出门槛</div>
          <ul class="wb-conditions">${conditionRows}</ul>
          <p class="wb-gate-status" aria-live="polite">
            ${gate.met_count}/${gate.total} 项门槛已满足${gate.can_advance ? '，可以进入下一阶段。' : '；仍有未关闭条件。'}
          </p>
        </section>
        <section class="card wb-gate">
          <div class="wb-eyebrow">阻塞与操作</div>
          ${blockHtml}
          <div class="wb-actions">
            ${!readOnly && canWrite() ? `<button class="btn-sm" data-act="workflow.newCondition">+ 新增门槛</button>` : ''}
            <button class="btn-sm" data-act="workflow.refresh">刷新</button>
            <button class="btn-sm" data-act="workflow.tenLayer">去十层执行</button>
          </div>
          ${!readOnly ? `<button class="btn btn-p wb-advance" data-act="workflow.advance"
            ${gate.can_advance ? '' : 'aria-disabled="true" disabled'}
            title="${gate.can_advance ? '' : esc(gate.block_reasons.join('；'))}">
            ${p.current_stage >= 5 ? '已是最后阶段' : '进入下一阶段'}</button>` : ''}
          <div class="tiny muted mt">${esc(data.hint || '')}</div>
        </section>
      </aside>
    </div>`;
}

/* -------------------------------------------------- 步骤 / 门槛弹窗 */

function linesToList(value) {
  return (value || '').split('\n').map((row) => row.trim()).filter(Boolean);
}

function openStepModal(stepId) {
  const data = state.wfWorkbench;
  const step = data && data.steps.find((row) => row.id === stepId);
  if (!step) return;
  const labels = data.step_status_labels || {};
  const statusOptions = Object.entries(labels).map(([code, label]) =>
    `<option value="${code}"${code === step.status ? ' selected' : ''}>${esc(label)}</option>`).join('');
  openModal(step.step_no + ' ' + step.name + ' · 更新闭环', `
    <div class="note mb">状态是数据字段：已填写不等于已满足；待验证需要接收方确认。</div>
    <div class="field"><label>状态</label><select id="wbStatus">${statusOptions}</select></div>
    <div class="field"><label>目标</label><textarea id="wbGoal" rows="2">${esc(step.goal || '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>输入（每行一条）</label>
        <textarea id="wbInputs" rows="3">${esc((step.inputs || []).join('\n'))}</textarea></div>
      <div class="field"><label>验收证据（每行一条）</label>
        <textarea id="wbEvidence" rows="3">${esc((step.evidence || []).join('\n'))}</textarea></div>
    </div>
    <div class="field"><label>处理要点（每行一条）</label>
      <textarea id="wbProcess" rows="3">${esc((step.process_steps || []).join('\n'))}</textarea></div>
    <div class="row2">
      <div class="field"><label>输出</label><input id="wbOutput" value="${esc(step.output || '')}"></div>
      <div class="field"><label>责任人</label><input id="wbOwner" value="${esc(step.owner || '')}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>接收方（待验证必填）</label><input id="wbReceiver" value="${esc(step.receiver || '')}"></div>
      <div class="field"><label>下一步</label><input id="wbNext" value="${esc(step.next_action || '')}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>受阻原因</label><input id="wbBlockedReason" value="${esc(step.blocked_reason || '')}"></div>
      <div class="field"><label>受阻责任人</label><input id="wbBlockedOwner" value="${esc(step.blocked_owner || '')}"></div>
      <div class="field"><label>预计解除</label><input id="wbBlockedDue" type="date" value="${esc(step.blocked_due || '')}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>决策选项（每行一条）</label>
        <textarea id="wbDecisionOptions" rows="2">${esc((step.decision_options || []).join('\n'))}</textarea></div>
      <div class="field"><label>决策人</label><input id="wbDecisionMaker" value="${esc(step.decision_maker || '')}"></div>
      <div class="field"><label>决策时限</label><input id="wbDecisionDue" type="date" value="${esc(step.decision_due || '')}"></div>
    </div>
    <div class="field"><label>补充说明</label><textarea id="wbNote" rows="2">${esc(step.notes || '')}</textarea></div>`,
  `<button class="btn btn-g" data-act="workflow.close">取消</button>
   <button class="btn btn-p" data-act="workflow.saveStep" data-id="${step.id}">保存</button>`, true);
}

async function saveStep(stepId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const payload = {
    status: val('wbStatus'),
    goal: val('wbGoal') || null,
    inputs: linesToList(document.getElementById('wbInputs')?.value),
    evidence: linesToList(document.getElementById('wbEvidence')?.value),
    process_steps: linesToList(document.getElementById('wbProcess')?.value),
    output: val('wbOutput') || null,
    owner: val('wbOwner') || null,
    receiver: val('wbReceiver') || null,
    next_action: val('wbNext') || null,
    blocked_reason: val('wbBlockedReason') || null,
    blocked_owner: val('wbBlockedOwner') || null,
    blocked_due: val('wbBlockedDue') || null,
    decision_options: linesToList(document.getElementById('wbDecisionOptions')?.value),
    decision_maker: val('wbDecisionMaker') || null,
    decision_due: val('wbDecisionDue') || null,
    note: val('wbNote') || null,
  };
  try {
    await PATCH(`/projects/${state.workflow.projectId}/workflow/steps/${stepId}`, payload);
    closeModal();
    RENDERERS.workflow();
  } catch (e) {
    toast(e.message, true);
  }
}

function openConditionModal(conditionId) {
  const data = state.wfWorkbench;
  const row = data && data.gate.conditions.find((item) => item.id === conditionId);
  if (!row) return;
  openModal('更新阶段门槛', `
    <div class="field"><label>条件</label><input id="wcText" value="${esc(row.text)}"></div>
    <div class="field"><label>证据（标记满足前必填）</label>
      <textarea id="wcEvidence" rows="2">${esc(row.evidence || '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>责任人</label><input id="wcOwner" value="${esc(row.owner || '')}"></div>
      <div class="field"><label>截止日期</label><input id="wcDue" type="date" value="${esc(row.due_date || '')}"></div>
    </div>
    <div class="field"><label>说明</label><textarea id="wcNote" rows="2">${esc(row.note || '')}</textarea></div>
    <label class="gap"><input id="wcMet" type="checkbox" ${row.is_met ? 'checked' : ''}> 标记为已满足</label>`,
  `<button class="btn btn-g" data-act="workflow.close">取消</button>
   <button class="btn btn-p" data-act="workflow.saveCondition" data-id="${row.id}">保存</button>`);
}

async function saveCondition(conditionId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  try {
    await PATCH(
      `/projects/${state.workflow.projectId}/workflow/conditions/${conditionId}`,
      {
        text: val('wcText'),
        evidence: val('wcEvidence') || null,
        owner: val('wcOwner') || null,
        due_date: val('wcDue') || null,
        note: val('wcNote') || null,
        is_met: !!document.getElementById('wcMet')?.checked,
      },
    );
    closeModal();
    RENDERERS.workflow();
  } catch (e) {
    toast(e.message, true);
  }
}

function openNewConditionModal() {
  const stage = state.wfWorkbench ? state.wfWorkbench.viewing_stage : 1;
  openModal('新增阶段门槛', `
    <div class="field"><label>条件</label><input id="wnText"></div>
    <div class="row2">
      <div class="field"><label>责任人</label><input id="wnOwner"></div>
      <div class="field"><label>截止日期</label><input id="wnDue" type="date"></div>
    </div>
    <label class="gap"><input id="wnCritical" type="checkbox" checked> 关键条件（未满足则阻断推进）</label>`,
  `<button class="btn btn-g" data-act="workflow.close">取消</button>
   <button class="btn btn-p" data-act="workflow.createCondition"
     data-stage="${stage}">添加</button>`);
}

async function createCondition() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const text = val('wnText');
  if (!text) return toast('请填写门槛条件', true);
  try {
    await POST(`/projects/${state.workflow.projectId}/workflow/conditions`, {
      stage_no: Number(val('wnStage') || state.wfWorkbench.viewing_stage),
      text,
      owner: val('wnOwner') || null,
      due_date: val('wnDue') || null,
      is_critical: !!document.getElementById('wnCritical')?.checked,
    });
    closeModal();
    RENDERERS.workflow();
  } catch (e) {
    toast(e.message, true);
  }
}

async function advanceStage() {
  try {
    const result = await POST(
      `/projects/${state.workflow.projectId}/workflow/advance`, {},
    );
    toast(result.message || '已进入下一阶段');
    state.workflow.stage = result.current_stage;
    RENDERERS.workflow();
  } catch (e) {
    toast(e.message, true);
    RENDERERS.workflow();
  }
}

/* -------------------------------------------------- 方法手册（五阶段步骤 / 方法论匹配） */

function workflowTabs(active) {
  return `<div class="seg wb-tabs">
    <button class="${active === 'workbench' ? 'on' : ''}"
      data-act="workflow.tab" data-tab="workbench">项目工作台</button>
    <button class="${active === 'steps' ? 'on' : ''}"
      data-act="workflow.tab" data-tab="steps">五阶段步骤</button>
    <button class="${active === 'method' ? 'on' : ''}"
      data-act="workflow.tab" data-tab="method">方法论匹配</button>
  </div>`;
}

function renderManual(wf) {
  return renderAsync('workflow',
    () => GET('/workflow/stages'),
    (stages) => {
      state.wf = stages;
      const stepStage = wf.stepStage || 1;
      const current = stages.find((s) => s.stage_no === stepStage) || stages[0];
      const stageIndex = stages.indexOf(current);
      const stageColor = STAGE_COLORS[stageIndex] || STAGE_COLORS[0];
      const total = stages.reduce((a, s) => a + s.steps.length, 0);
      const pills = stages.map((s, i) => `
        <button class="stage-pill${s.stage_no === current.stage_no ? ' on' : ''}"
          style="--pill:${STAGE_COLORS[i]}" data-act="workflow.stage" data-stage="${s.stage_no}">
          <b>阶段${s.stage_no}</b><span>${esc(s.stage_name)}</span>
          <em>${s.steps.length} 步${s.knowledge_count ? ' · ' + s.knowledge_count + ' 条知识' : ''}</em>
        </button>`).join('');
      const steps = current.steps.map((st) => `
        <button class="step wf-step" type="button" style="--step-color:${stageColor};border-left-color:${stageColor}"
          data-act="workflow.step" data-step="${esc(st.step_no)}">
          <div class="wf-step-hd"><span class="wf-step-no"
            style="background:linear-gradient(135deg,${stageColor},var(--brand2))">${esc(st.step_no)}</span>
            <b>${esc(st.name)}</b></div>
          <span>${esc(st.deliverables)}</span>
          ${st.tools ? `<div class="wf-step-tools">推荐工具：${esc(st.tools)}</div>` : ''}
          ${st.knowledge_count ? `<div class="wf-step-tools">推荐知识：${st.knowledge_count} 条</div>` : ''}
        </button>`).join('');
      const methodPane = renderMethodPane();
      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>五阶段标准工作流<span class="module-badge">方法手册 · 教学引导</span></h2>
              <div class="desc">全公司共用的方法手册 · ${total} 个标准步骤；项目实际推进请用「项目工作台」</div></div>
            ${workflowTabs(wf.tab)}
          </div>
        </div>
        ${wf.tab === 'method' ? methodPane : `
          <div class="stage-pills">${pills}</div>
          <div class="wf-hero" style="background:linear-gradient(120deg,${stageColor},var(--brand2))">
            <div class="wf-hero-ring">${current.stage_no}</div>
            <div class="wf-hero-tx"><h3>阶段${current.stage_no} · ${esc(current.stage_name)}</h3>
              <p>${esc(current.stage_goal || '')}</p></div>
            <div class="wf-hero-kpis">
              <div><b>${current.steps.length}</b><span>本阶段步骤</span></div>
              <div><b>${total}</b><span>全流程步骤</span></div>
              <div><b>${stages.length}</b><span>阶段数</span></div>
            </div>
          </div>
          <section class="wf-section"><div class="ch"><span class="dot"></span>
            <h3>阶段${current.stage_no} 步骤清单</h3><div class="sp"></div>
            <span class="tiny">${current.steps.length} 个步骤 · 点击查看方法、工具与交付物</span>
          </div><div class="wf-grid">${steps}</div></section>`}`;
    });
}

function renderMethodPane() {
  return `<div class="card">
    <h3>决策门：方法论选择矩阵</h3>
    <div class="desc">方法论是步骤内部的支持资源，不是独立审批步骤；匹配结果只作为建议。</div>
    <table class="tbl mb">
      <thead><tr><th>流程现状</th><th>改善目标</th><th>推荐方法</th><th>典型周期</th><th>风险等级</th></tr></thead>
      <tbody>
        <tr><td>流程严重过时、断裂、与战略脱节</td><td>阶跃式突破（≥50%）</td>
          <td>${methodTag('BPR', 'BPR 重组')}</td><td>6–18 个月</td><td><span class="tag t-red">高</span></td></tr>
        <tr><td>流程基本合理但局部堵点</td><td>渐进改善（10–30%）</td>
          <td>${methodTag('BPI', 'BPI 优化')}</td><td>1–3 个月</td><td><span class="tag t-yel">中低</span></td></tr>
        <tr><td>现场/操作层浪费明显</td><td>持续流动、消除浪费</td>
          <td>${methodTag('LEAN', '精益改善')}</td><td>持续改善</td><td><span class="tag t-grn">低</span></td></tr>
        <tr><td>混合状态（多数实际情况）</td><td>架构 + 执行 + 操作分层改善</td>
          <td>${methodTag('HYBRID', '组合拳')}</td><td>持续</td><td><span class="tag t-yel">中</span></td></tr>
      </tbody>
    </table>
    <h3>实时试算</h3>
    <div class="row3">
      <div class="field"><label>流程现状</label><select id="rcState">
        <option value="SEVERE_OUTDATED">严重过时、断裂、与战略脱节</option>
        <option value="SOUND_BUT_INEFFICIENT">基本合理但效率不足、局部堵点</option>
        <option value="SHOPFLOOR_WASTE">现场/操作层浪费明显、波动大</option>
        <option value="MIXED">混合状态</option></select></div>
      <div class="field"><label>目标改善幅度（%）</label>
        <input id="rcPct" type="number" value="30" min="0" max="100"></div>
      <div class="field"><label>范围</label><select id="rcScope">
        <option value="END_TO_END">端到端跨职能</option>
        <option value="LOCAL" selected>单一部门内部</option>
        <option value="SHOPFLOOR">现场/操作层</option></select></div>
    </div>
    <div class="row3">
      <div class="field"><label>是否涉及组织/权责调整</label>
        <select id="rcOrg"><option value="false">否</option><option value="true">是</option></select></div>
      <div class="field"><label>是否有流程数据/日志</label>
        <select id="rcData"><option value="true">是</option><option value="false">否</option></select></div>
      <div class="field"><label>计划周期（月）</label>
        <input id="rcDur" type="number" value="6" min="1" max="36"></div>
    </div>
    <button class="btn btn-p" id="rcBtn" data-act="workflow.recommend">运行匹配引擎</button>
    <div id="rcResult" class="mt"></div>
  </div>`;
}

on('workflow.recommend', () => runRecommend('rcResult'));

function openWfStep(stepNo) {
  let found = null;
  (state.wf || []).forEach((s) => s.steps.forEach((st) => { if (st.step_no === stepNo) found = st; }));
  if (!found) return;
  openModal(found.step_no + ' ' + found.name + ' · 方法说明', `
    <div class="field"><label>标准动作</label><textarea readonly>${esc(found.action)}</textarea></div>
    <div class="row2">
      <div class="field"><label>方法手册里的工具</label><input value="${esc(found.tools)}" readonly></div>
      <div class="field"><label>关键交付物</label><input value="${esc(found.deliverables)}" readonly></div>
    </div>
    <div class="field"><label>关键要点 / 踩坑提示</label><textarea readonly>${esc(found.key_points)}</textarea></div>
    <div class="field"><label>所属阶段</label><input value="阶段${found.stage_no}" readonly></div>
    <div id="wfRec">${skeleton(3)}</div>`,
  `<button class="btn btn-g" data-act="workflow.close">关闭</button>
   <button class="btn btn-g" data-act="workflow.toolboxStep">去工具箱看推荐工具</button>
   <button class="btn btn-p" data-act="workflow.goDeliverables">去模板库</button>`, true);
  paintStepRecommendations(stepNo);
}

function openToolboxForStep() {
  const rec = state.wfStepRec;
  if (!rec || !rec.tools.length) {
    state.toolboxFilter = null;
    go('toolbox');
    return;
  }
  state.toolboxFilter = {
    label: rec.step_no + ' ' + rec.step_name,
    codes: rec.tools.map((t) => t.code),
    meta: Object.fromEntries(rec.tools.map((t) => [t.code, t])),
  };
  state.toolbox.step = rec.step_no;
  state.toolbox.stage = rec.stage_no;
  state.toolbox.sort = 'fit';
  go('toolbox', { params: { step: rec.step_no, stage: rec.stage_no }, push: true });
}

async function paintStepRecommendations(stepNo) {
  const box = document.getElementById('wfRec');
  if (!box) return;
  try {
    const rec = await GET('/workflow/steps/' + encodeURIComponent(stepNo) + '/recommendations');
    if (!box.isConnected) return;
    state.wfStepRec = rec;
    box.innerHTML = renderStepRecommendations(rec);
  } catch (e) {
    if (box.isConnected) box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

function renderTemplateChips(templates) {
  if (!templates.length) return '<span class="tiny">暂无预制模板</span>';
  return templates.map((t) => `
    <div class="between" style="gap:8px;margin-bottom:6px">
      <span>${esc(t.name)} <span class="tag t-gry">${esc(t.format_label)}</span>
        ${t.effective_version ? '<span class="tag t-grn">现行 ' + esc(t.effective_version.version_label) + '</span>'
          : '<span class="tag t-gry">无生效版本</span>'}</span>
      <span>${t.effective_version
        ? `<button class="btn-sm" data-act="workflow.copyTemplate" data-id="${t.id}">复制到项目</button>` : ''}</span>
    </div>`).join('');
}

function renderStepRecommendations(rec) {
  const rows = rec.tools.map((t) => `
    <tr><td><a class="link" data-act="workflow.openTool" data-code="${esc(t.code)}"><b>${esc(t.name)}</b></a>
      <div class="tiny">${esc(t.code)} · ${esc(t.category_label || '')}</div></td>
      <td><span class="tag ${TOOL_LEVEL_TONE[t.level] || 't-gry'}">${esc(t.level_label)}</span></td>
      <td><div class="tiny">${esc(t.why || t.verification_standard || '—')}</div>
        ${t.verification_standard ? `<div class="tiny"><b>验证：</b>${esc(t.verification_standard)}</div>` : ''}
        <div class="tiny">难度 ${esc(t.difficulty_label || '—')}
          ${t.typical_duration ? ' · 周期 ' + esc(t.typical_duration) : ''}</div></td>
      <td>${renderTemplateChips(t.templates)}</td></tr>`).join('');
  const extras = rec.deliverable_templates.length
    ? `<h3 class="mt">本步骤交付物可用模板</h3>${renderTemplateChips(rec.deliverable_templates)}` : '';
  const knowledge = rec.knowledge || [];
  const knowledgeHtml = knowledge.length
    ? `<h3 class="mt">本步骤推荐知识</h3><div class="kb-step-list">${knowledge.map((item) => {
      const rate = item.effectiveness_rate === null || item.effectiveness_rate === undefined
        ? '暂无使用记录'
        : `有效率 ${item.effectiveness_rate}%（${item.effective_count}/${item.used_count}）`;
      const scenario = item.scenarios && item.scenarios.length ? item.scenarios[0].code : '';
      return `<div class="kb-step-item"><div><b>${esc(item.title)}</b>
        <span class="tag t-blu">${esc(item.type_label || item.type)}</span>
        ${item.is_best_practice ? '<span class="tag t-grn">最佳实践</span>' : ''}
        <div class="tiny">${esc(item.applicable_when || item.summary)} · ${esc(rate)}</div></div>
        <div class="gap"><button class="btn-sm" data-act="knowledge.open" data-id="${item.id}">查看</button>
        <button class="btn-sm" data-act="workflow.goKnowledge"
          data-step="${esc(rec.step_no)}" data-scenario="${esc(scenario)}">在知识库查看</button></div></div>`;
    }).join('')}</div>`
    : '<h3 class="mt">本步骤推荐知识</h3><div class="note">本步骤还没有挂知识，流程管理科可以在知识条目里关联步骤。</div>';
  return `<h3 class="mt">推荐工具与预制模板</h3>
    <div class="desc">使用要求来自步骤契约；模板复制到项目后会固定来源版本</div>
    ${rec.tools.length ? `<table class="tbl"><thead><tr><th>工具</th><th>使用要求</th>
      <th>为什么用 / 验证标准</th><th>预制模板</th></tr></thead><tbody>${rows}</tbody></table>`
      : '<div class="note">该步骤还没有配置工具。</div>'}
    ${extras}${knowledgeHtml}`;
}

async function runRecommend(targetId) {
  const box = document.getElementById(targetId);
  if (!box) return;
  box.innerHTML = skeleton(3);
  try {
    const r = await POST('/projects/recommend-methodology', {
      process_state: document.getElementById('rcState').value,
      target_improvement_pct: Number(document.getElementById('rcPct').value || 0),
      scope: document.getElementById('rcScope').value,
      involves_org_change: document.getElementById('rcOrg').value === 'true',
      data_available: document.getElementById('rcData').value === 'true',
      duration_target_months: Number(document.getElementById('rcDur').value || 6),
    });
    box.innerHTML = renderRecommendation(r);
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

export { renderWorkflow };
