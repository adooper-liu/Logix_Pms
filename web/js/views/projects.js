/* 视图：projects */
import { esc, num, pct, methodTag, statusTag, bar, emptyRow, skeleton } from '../core/format.js';
import { metricHelp } from '../core/metrics.js';
import { toast, openModal, closeModal, modalAlive, confirmDialog, tab, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { AUTH, role, canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { actions as appActions } from '../core/actions.js';
import { renderRecommendation } from './shared/recommendation.js';

/* ============================================================ 4. 流程项目组合 */

on('projects.open', ({ id }) => openProject(Number(id)));
on('projects.new', () => newProjectWizard());
on('projects.goWorkflow', () => go('workflow'));
on('projects.goExecution', () => go('execution'));
on('projects.filter', ({ key }, el) => setPFilter(key, el.value));
on('projects.newSetup', () => newSetupProgramModal());
on('projects.submitSetup', () => submitSetupProgram());
on('projects.clearFilter', () => clearPFilter());
on('projects.tab', ({ pane }, el) => tab(el, pane));
on('projects.patchStep', ({ id, project }, el) => {
  patchStep(Number(id), el.value, Number(project));
});
on('projects.startStep', ({ id, project }) => {
  patchStep(Number(id), 'IN_PROGRESS', Number(project));
});
on('projects.openStepWork', ({ step, stage, process }) => {
  closeModal();
  const target = stepWorkspace(step, Number(stage), Number(process) || null);
  go(target.view, { params: target.params, push: true });
});
on('projects.openStepTool', ({ step, stage }) => {
  closeModal();
  state.toolbox.step = step;
  state.toolbox.stage = Number(stage);
  state.toolbox.sort = 'fit';
  go('toolbox', {
    params: { step, stage: Number(stage), sort: 'fit' },
    push: true,
  });
});
on('projects.openStepDeliverables', ({ project, step }) => {
  closeModal();
  go('deliverables', {
    params: { tab: 'project', project: Number(project), step },
    push: true,
  });
});
on('projects.logStep', ({ id, project }) => {
  openStepProgress(Number(id), Number(project));
});
on('projects.stepStatusPreview', (_data, el) => {
  toggleStepStatusFields(el.value);
});
on('projects.submitStepProgress', ({ id, project }) => {
  submitStepProgress(Number(id), Number(project));
});
on('projects.delete', ({ id, code }) => deleteProject(Number(id), code));
on('projects.close', () => closeModal());
on('projects.edit', ({ id }) => editProjectModal(Number(id)));
on('projects.closeOpenDesigner', ({ process }) => {
  closeModal();
  appActions['designer.open'](Number(process));
});
on('projects.openExecution', ({ process }) => {
  closeModal();
  go('execution', {
    params: { process: Number(process), tab: 'config' },
    push: true,
  });
});
on('projects.saveEdit', ({ id }) => saveProjectEdit(Number(id)));
on('projects.gate', ({ id }) => openGateModal(Number(id)));
on('projects.submitGate', ({ id }) => submitGate(Number(id)));
on('projects.replication', ({ id }) => openReplicationModal(Number(id)));
on('projects.submitReplication', ({ id }) => submitReplication(Number(id)));
on('projects.publishPack', ({ id, project }) => publishPack(Number(id), Number(project)));
on('projects.wizardRecommend', () => wizardRecommend());
on('projects.submit', () => submitProject());

function applyProjectParams() {
  const params = urlParams();
  const filterKeys = ['methodology', 'status', 'stage', 'type', 'keyword'];
  const hasFilters = filterKeys.some((key) => key in params);
  if (!hasFilters && !params.project && !params.new_process && !params.new_objective) {
    state.projects.filter = { methodology: '', status: '', stage: '', projectType: '' };
    state.projects.keyword = '';
  }
  if ('methodology' in params) state.projects.filter.methodology = params.methodology;
  if ('status' in params) state.projects.filter.status = params.status;
  if ('stage' in params) state.projects.filter.stage = params.stage;
  if ('type' in params) state.projects.filter.projectType = params.type;
  if ('keyword' in params) state.projects.keyword = params.keyword;
}

function projectUrlParams(extra = {}) {
  const f = state.projects.filter;
  return {
    methodology: f.methodology,
    status: f.status,
    stage: f.stage,
    type: f.projectType,
    project: state.projects.openId || '',
    new_process: state.projects.newProcess || '',
    new_name: state.projects.newName || '',
    new_objective: state.projects.newObjective || '',
    ...extra,
  };
}

function syncProjectUrl({ push = false } = {}) {
  setUrlState('projects', projectUrlParams(), { push });
}

const renderProjects = () => {
  applyProjectParams();
  const f = state.projects.filter;
  const qs = [];
  if (f.methodology) qs.push('methodology=' + f.methodology);
  if (f.status) qs.push('status=' + f.status);
  if (f.stage) qs.push('stage=' + f.stage);
  if (f.projectType) qs.push('project_type=' + f.projectType);
  if (state.projects.keyword) qs.push('keyword=' + encodeURIComponent(state.projects.keyword));
  qs.push('page_size=100');

  renderAsync('projects',
    async () => {
      const params = urlParams();
      const newObjectiveId = Number(params.new_objective) || null;
      const [page, meta] = await Promise.all([
        GET('/projects?' + qs.join('&')),
        GET('/projects/meta'),
      ]);
      // 战略目标立项时把目标一并带进来，用于预填改善目标/基线/目标值
      const objective = newObjectiveId
        ? await GET('/strategy/objectives/' + newObjectiveId).catch(() => null)
        : null;
      return {
        page,
        meta,
        openId: Number(params.project) || null,
        newProcess: Number(params.new_process) || null,
        newName: params.new_name || '',
        newObjective: objective,
      };
    },
    (d) => {
      const page = d.page;
      state.projectMeta = d.meta;
      const rows = page.items.map((p) => `
        <tr class="clk">
          <td><button class="project-open" type="button" data-act="projects.open"
              data-id="${p.id}"><b>${esc(p.name)}</b></button>
            <div class="tiny">${esc(p.code)}${p.process_name ? ' · ' + esc(p.process_name) : ''}
              ${p.project_type === 'GOVERNANCE_SETUP'
                ? '<span class="tag t-blu">体系落地</span>' : ''}</div></td>
          <td>${methodTag(p.methodology, state.meta.methodology[p.methodology])}</td>
          <td>阶段${p.current_stage}<div class="tiny">${esc(p.stage_name || '')}</div></td>
          <td>${esc(p.owner)}<div class="tiny">${esc(p.department || '')}</div></td>
          <td style="font-size:12.5px">${p.metric_name
            ? esc(p.metric_name) + '<div class="tiny">' + num(p.baseline_value, 1) + ' → ' + num(p.target_value, 1) +
              ' ' + esc(p.metric_unit || '') + '</div>' : '—'}</td>
          <td style="font-size:12.5px">${num(p.actual_cost, 1)} / ${num(p.budget, 1)}</td>
          <td>${bar(p.progress)}</td>
          <td>${statusTag(p.status, p.status_label)}</td>
        </tr>`).join('') || emptyRow(8, '没有符合条件的项目');

      const opt = (v, label, cur) =>
        '<option value="' + v + '"' + (cur === v ? ' selected' : '') + '>' + label + '</option>';
      // 改善项目 5 阶段、体系落地项目 9 阶段；未筛选类型时同时给出两套阶段名称
      const stageCount = f.projectType === 'IMPROVEMENT' ? 5 : 9;
      const improvementNames = state.meta.stage || {};
      const setupNames = state.meta.setupStage || {};
      const stageOptions = Array.from({ length: stageCount }, (_, index) => {
        const no = index + 1;
        let name = '';
        if (f.projectType === 'IMPROVEMENT') {
          name = improvementNames[no] || '';
        } else if (f.projectType === 'GOVERNANCE_SETUP') {
          name = setupNames[no] || '';
        } else {
          const a = improvementNames[no];
          const b = setupNames[no];
          name = a && b && a !== b ? `${a} / ${b}` : (a || b || '');
        }
        return opt(String(no), '阶段' + no + (name ? ' · ' + name : ''), f.stage);
      }).join('');

      const today = new Date().toISOString().slice(0, 10);
      const activeCount = page.items.filter((p) => p.status === 'ACTIVE').length;
      const closedCount = page.items.filter((p) => p.status === 'CLOSED').length;
      const overdueCount = page.items.filter(
        (p) => p.end_date && p.end_date < today && p.progress < 100).length;
      const avgProgress = page.items.length
        ? Math.round(page.items.reduce((a, p) => a + p.progress, 0) / page.items.length) : 0;

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>流程项目组合<span class="module-badge">改善项目 · 推进循环</span></h2>
              <div class="desc">共 ${page.total} 个项目 · 改善项目走 24 步、体系落地项目走 9 阶段；点击行查看详情与下一步动作</div></div>
            <div class="gap">
              <a class="link-btn" data-act="projects.goWorkflow">查看方法手册</a>
              <a class="link-btn" data-act="projects.goExecution">流程执行 →</a>
              <button class="btn btn-g" data-act="projects.newSetup">+ 体系落地项目</button>
              <button class="btn btn-p" data-act="projects.new">+ 新建流程项目</button>
            </div>
          </div>
          <div class="grid g4 stat-row">
            <div class="kpi stat"><div class="num">${page.total}</div><div class="lab">${metricHelp('project_total', '项目总数')}</div></div>
            <div class="kpi stat"><div class="num">${activeCount}</div><div class="lab">${metricHelp('active_count', '进行中')}</div></div>
            <div class="kpi stat"><div class="num">${closedCount}</div><div class="lab">${metricHelp('closed_count', '已结项')}</div></div>
            <div class="kpi stat ${overdueCount ? 'is-risk' : ''}">
              <div class="num">${avgProgress}<small>%</small></div>
              <div class="lab">${metricHelp('avg_progress', '平均进度')}${overdueCount ? ' · ' + overdueCount + ' 项超期' : ''}</div></div>
          </div>
          <div class="gap mt" style="flex-wrap:wrap">
            <select class="sel" data-act="projects.filter" data-key="methodology">
              ${opt('', '全部方法', f.methodology)}
              ${['BPR', 'BPI', 'LEAN', 'HYBRID'].map((m) =>
                opt(m, state.meta.methodology[m] || m, f.methodology)).join('')}
            </select>
            <select class="sel" data-act="projects.filter" data-key="stage">
              ${opt('', '全部阶段', f.stage)}
              ${stageOptions}
            </select>
            <select class="sel" data-act="projects.filter" data-key="projectType">
              ${opt('', '全部类型', f.projectType)}
              ${opt('IMPROVEMENT', '流程改善', f.projectType)}
              ${opt('GOVERNANCE_SETUP', '治理体系落地', f.projectType)}
            </select>
            <select class="sel" data-act="projects.filter" data-key="status">
              ${opt('', '全部状态', f.status)}
              ${['PLANNING', 'ACTIVE', 'ON_HOLD', 'CLOSED', 'CANCELLED'].map((s) =>
                opt(s, state.meta.status[s] || s, f.status)).join('')}
            </select>
            ${(f.methodology || f.stage || f.projectType || f.status || state.projects.keyword)
              ? '<button class="btn-sm" style="align-self:center" data-act="projects.clearFilter">清空筛选</button>' : ''}
          </div>
        </div>

        <div class="card">
          <table class="tbl">
            <thead><tr><th>项目</th><th>方法</th><th>阶段</th><th>Owner</th>
              <th>${metricHelp('improvement_pct', '改善指标')}</th><th>${metricHelp('budget_usage', '已用/预算(万)')}</th><th>${metricHelp('project_progress', '整体进度')}</th><th>状态</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
      if (d.openId && state.projects.openId !== d.openId) {
        state.projects.openId = d.openId;
        openProject(d.openId, { fromUrl: true });
      } else if (!d.openId && state.projects.openId) {
        state.projects.openId = null;
        closeModal();
      }
      if (d.newProcess
        && (state.projects.newProcess !== d.newProcess
          || (d.newObjective && state.projects.newObjective !== d.newObjective.id))) {
        state.projects.newProcess = d.newProcess;
        state.projects.newName = d.newName;
        state.projects.newObjective = d.newObjective ? d.newObjective.id : null;
        newProjectWizard({
          processId: d.newProcess,
          name: d.newName,
          objective: d.newObjective,
        });
      } else if (!d.newProcess && state.projects.newProcess) {
        state.projects.newProcess = null;
        state.projects.newName = '';
        state.projects.newObjective = null;
        closeModal();
      }
    });
};

if (typeof window !== 'undefined') {
  window.addEventListener('pms:modal-closed', () => {
    if (state.view !== 'projects') return;
    if (document.getElementById('mask').classList.contains('show')) return;
    if (!state.projects.openId && !state.projects.newProcess) return;
    state.projects.openId = null;
    state.projects.newProcess = null;
    state.projects.newName = '';
    state.projects.newObjective = null;
    syncProjectUrl();
  });
}

function setPFilter(key, value) {
  state.projects.filter[key] = value;
  syncProjectUrl();
  RENDERERS.projects();
}
function clearPFilter() {
  state.projects.filter = { methodology: '', status: '', stage: '', projectType: '' };
  state.projects.keyword = '';
  document.getElementById('searchInput').value = '';
  syncProjectUrl();
  RENDERERS.projects();
}

/* -------------------------------------------------- 项目详情 */

async function openProject(id, options = {}) {
  state.projects.openId = id;
  state.projects.newProcess = null;
  state.projects.newName = '';
  state.projects.newObjective = null;
  if (!options.fromUrl) syncProjectUrl({ push: true });
  const gen = openModal('加载中…', skeleton(5), '', true);
  let d;
  let sched = null;
  let dlv = [];
  try {
    [d, sched, dlv] = await Promise.all([
      GET('/projects/' + id),
      GET('/projects/' + id + '/schedule').catch(() => null),
      GET('/projects/' + id + '/deliverables').catch(() => []),
    ]);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    return;
  }
  // 用户在请求返回前关掉了弹窗，就别再把它弹回来
  if (!modalAlive(gen)) return;
  const p = d.project;
  state.projectDetail = d;
  const dlvByStep = {};
  dlv.forEach((row) => {
    (dlvByStep[row.step_no] ||= []).push(row);
  });
  const stepStatusLabels = d.step_status_labels || {};

  const tabs = `
    <div class="tabs">
      <button class="on" data-act="projects.tab" data-pane="pd-ov">概览</button>
      <button data-act="projects.tab" data-pane="pd-kp">KPI 追踪</button>
      <button data-act="projects.tab" data-pane="pd-wk">工作流推进</button>
      <button data-act="projects.tab" data-pane="pd-gt">甘特图</button>
      <button data-act="projects.tab" data-pane="pd-nx">下一步</button>
    </div>`;

  const overview = `
    <div data-pane id="pd-ov">
      <div class="row2">
        <div class="field"><label>项目编号</label><input value="${esc(p.code)}" readonly></div>
        <div class="field"><label>方法论</label>
          <input value="${esc(p.methodology_label || p.methodology)}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>流程 Owner</label><input value="${esc(p.owner)}" readonly></div>
        <div class="field"><label>发起人 / 部门</label>
          <input value="${esc((p.sponsor || '—') + ' · ' + (p.department || '—'))}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>关联流程</label><input value="${esc(p.process_name || '未关联')}" readonly></div>
        <div class="field"><label>当前阶段</label>
          <input value="阶段${p.current_stage} ${esc(p.stage_name || '')}" readonly></div>
      </div>
      <div class="field"><label>改善目标</label><textarea readonly>${esc(p.objective || '—')}</textarea></div>
      <div class="field"><label>范围边界</label><textarea readonly>${esc(p.scope || '—')}</textarea></div>
      ${improvementCardHtml(p)}
      <div class="row2">
        <div class="field"><label>预算 / 已投入（万元）</label>
          <input value="${num(p.budget, 1)} / ${num(p.actual_cost, 1)}" readonly></div>
        <div class="field"><label>预计 ROI</label>
          <input value="${p.roi_estimate === null ? '—' : num(p.roi_estimate, 1) + ' 倍'}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>计划周期</label>
          <input value="${esc(p.start_date || '—')} → ${esc(p.end_date || '—')}" readonly></div>
        <div class="field"><label>整体进度</label><input value="${num(p.progress, 1)}%" readonly></div>
      </div>
      <div class="g3">
        <div class="kpi" style="padding:13px 15px">
          <div class="num" style="font-size:22px">阶段${p.current_stage}</div><div class="lab">当前阶段</div></div>
        <div class="kpi" style="padding:13px 15px">
          <div class="num" style="font-size:22px;color:${
            p.progress >= 70 ? 'var(--ok)' : p.progress >= 30 ? 'var(--warn)' : 'var(--bad)'}">
            ${num(p.progress, 0)}%</div><div class="lab">步骤完成度</div></div>
        <div class="kpi" style="padding:13px 15px">
          <div class="num" style="font-size:22px;color:var(--brand)">${
            p.improvement_pct === null ? '—' : num(p.improvement_pct, 0) + '%'}</div>
          <div class="lab">目标改善幅度</div></div>
      </div>
    </div>`;

  const kpiPane = `
    <div data-pane id="pd-kp" class="hide">
      ${p.metric_name ? `
        <table class="tbl mb">
          <thead><tr><th>指标</th><th>基线</th><th>当前</th><th>目标</th><th>单位</th><th>目标改善</th></tr></thead>
          <tbody><tr>
            <td><b>${esc(p.metric_name)}</b></td>
            <td>${num(p.baseline_value, 1)}</td>
            <td><b>${num(p.current_value, 1)}</b></td>
            <td>${num(p.target_value, 1)}</td>
            <td class="muted">${esc(p.metric_unit || '')}</td>
            <td>${p.improvement_pct === null ? '—' : num(p.improvement_pct, 1) + '%'}</td>
          </tr></tbody>
        </table>` : '<div class="note mb">该项目尚未设定量化指标。</div>'}
      <h3>指标趋势（${d.kpi_trend.length} 个数据点）</h3>
      ${d.kpi_trend.length ? `
        <table class="tbl">
          <thead><tr><th>期间</th><th>数值</th><th>备注</th></tr></thead>
          <tbody>${d.kpi_trend.map((k) => '<tr><td>' + esc(k.period) + '</td><td><b>' +
            num(k.value, 2) + '</b></td><td class="muted">' + esc(k.note || '—') + '</td></tr>').join('')}</tbody>
        </table>` : '<div class="empty">暂无时序数据</div>'}
    </div>`;

  const quickStatuses = ['PENDING', 'IN_PROGRESS', 'DONE', 'SKIPPED'];
  const stepStatusOpts = (cur) => {
    const current = quickStatuses.includes(cur)
      ? ''
      : `<option value="${cur}" selected>${esc(stepStatusLabels[cur] || cur)}</option>`;
    return current + quickStatuses.map(
      (v) => `<option value="${v}"${cur === v ? ' selected' : ''}>${
        esc(stepStatusLabels[v] || v)}</option>`,
    ).join('');
  };

  const wfPane = `
    <div data-pane id="pd-wk" class="hide">
      <div class="note mb">每个步骤都可以直接去工作、记录进度，并查看/上传对应交付物；
        状态是工作结果，不是工作本身。</div>
      ${d.stages.map((s) => {
        const steps = d.steps.filter((x) => x.stage_no === s.stage_no);
        const allDone = s.total > 0 && s.done === s.total;
        return `
        <div class="stageblock">
          <div class="hd ${allDone ? '' : 'todo'}">
            <span>阶段${s.stage_no} ${esc(s.stage_name)}</span>
            <span>${s.done}/${s.total}${allDone ? ' ✓' : ''}</span>
          </div>
          <div class="steplist">
            ${steps.map((st) => {
              const target = stepWorkspace(st.step_no, st.stage_no, p.process_id);
              const stepDlv = dlvByStep[st.step_no] || [];
              const effective = stepDlv.filter((row) => row.status === 'EFFECTIVE').length;
              const done = st.status === 'DONE';
              return `
              <div class="stepitem ${done ? 'done' : ''}">
                <span class="no">${esc(st.step_no)}</span>
                <span class="nm"><b>${esc(st.name)}</b>
                  <i>${esc(st.deliverable || '')}${st.owner ? ' · ' + esc(st.owner) : ''}</i></span>
                <div class="stepacts">
                  <button class="btn-sm" data-act="projects.openStepWork"
                    data-step="${esc(st.step_no)}" data-stage="${st.stage_no}"
                    data-process="${p.process_id || ''}"
                    title="打开本步骤的工作现场">去${esc(target.label)}</button>
                  <button class="btn-sm" data-act="projects.openStepTool"
                    data-step="${esc(st.step_no)}" data-stage="${st.stage_no}"
                    title="查看本步骤推荐的工具与方法">工具</button>
                  ${stepDlv.length ? `<button class="btn-sm"
                    data-act="projects.openStepDeliverables" data-project="${p.id}"
                    data-step="${esc(st.step_no)}"
                    title="查看/上传本步骤交付物，或关联流程模型">交付物 ${effective}/${stepDlv.length}</button>` : ''}
                  ${st.status === 'PENDING' ? `<button class="btn-sm"
                    data-act="projects.startStep" data-id="${st.id}"
                    data-project="${p.id}" title="把状态改为进行中">开始</button>` : ''}
                  <button class="btn-sm" data-act="projects.logStep"
                    data-id="${st.id}" data-project="${p.id}"
                    title="记录进度、受阻或决策">记录进度</button>
                  <select data-act="projects.patchStep" data-id="${st.id}"
                    data-project="${p.id}">${stepStatusOpts(st.status)}</select>
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>`;
      }).join('')}
    </div>`;

  const ganttPane = `
    <div data-pane id="pd-gt" class="hide">
      ${sched ? paintGantt(sched) : '<div class="empty">甘特图数据加载失败</div>'}
    </div>`;

  const stageWord = d.project.project_type === 'GOVERNANCE_SETUP' ? '九个' : '五个';
  const nextPane = `
    <div data-pane id="pd-nx" class="hide">
      ${d.next_action ? `
        <div class="field"><label>下一步动作（阶段${d.next_action.stage_no} · 步骤 ${esc(d.next_action.step_no || '—')}）</label>
          <textarea readonly style="min-height:120px">${esc(d.next_action.name + '\n\n' + d.next_action.suggestion)}</textarea></div>` :
        `<div class="note mb">${stageWord}阶段全部完成，项目已进入运营阶段。</div>`}
      <h3>当前阶段待办步骤</h3>
      ${d.current_steps.length ? `
        <div class="steplist">${d.current_steps.map((st) => `
          <div class="stepitem">
            <span class="no">${esc(st.step_no)}</span>
            <span class="nm"><b>${esc(st.name)}</b><i>交付物：${esc(st.deliverable || '—')}</i></span>
          </div>`).join('')}</div>` : '<div class="empty">当前阶段没有待办步骤</div>'}
    </div>`;

  const canEditThis = canManage()
    || (role() === 'OWNER' && AUTH.user && p.owner_user_id === AUTH.user.id);

  openModal(p.name, tabs + overview + kpiPane + wfPane + ganttPane + nextPane, `
    ${canManage()
      ? '<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"'
        + ` data-act="projects.delete" data-id="${p.id}" data-code="${esc(p.code)}">删除项目</button>`
      : ''}
    <button class="btn btn-g" data-act="ui.copyLink">复制链接</button>
    <button class="btn btn-g" data-act="projects.close">关闭</button>
    ${canEditThis ? `<button class="btn btn-g" data-act="projects.edit" data-id="${p.id}">编辑</button>` : ''}
    ${canManage() ? `<button class="btn btn-g" data-act="projects.gate" data-id="${p.id}">门禁签收</button>` : ''}
    ${canEditThis ? `<button class="btn btn-g" data-act="projects.replication"
      data-id="${p.id}">复制资产包</button>` : ''}
    ${p.process_id ? `<button class="btn btn-g" data-act="projects.openExecution"
      data-process="${p.process_id}">去流程执行</button>` : ''}
    ${p.process_id ? `<button class="btn btn-p" data-act="projects.closeOpenDesigner"
      data-process="${p.process_id}">查看流程模型</button>` : ''}`,
    true);
}

/* -------------------------------------------------- 治理体系落地项目 */

function newSetupProgramModal() {
  openModal('新建治理体系落地项目', `
    <div class="field"><label>项目名称 *</label>
      <input id="spName" placeholder="如 采购域流程治理体系落地"></div>
    <div class="row2">
      <div class="field"><label>项目 Owner *</label>
        <select id="spOwner"><option value="">请选择</option></select></div>
      <div class="field"><label>发起人 / 赞助人</label>
        <input id="spSponsor" placeholder="如 集团总经理"></div>
    </div>
    <div class="field"><label>目标</label>
      <textarea id="spObjective" rows="2" placeholder="建立可运行的流程治理体系"></textarea></div>
    <div class="field"><label>范围</label>
      <textarea id="spScope" rows="2" placeholder="试点流程、法人/工厂、系统范围"></textarea></div>
    <div class="row3">
      <div class="field"><label>开始日期</label><input id="spStart" type="date"></div>
      <div class="field"><label>结束日期</label><input id="spEnd" type="date"></div>
      <div class="field"><label>优先级</label>
        <select id="spPriority">
          ${[1, 2, 3, 4, 5].map((i) => `<option value="${i}"${i === 2 ? ' selected' : ''}>${i}</option>`).join('')}
        </select></div>
    </div>
    <div class="note">会按九阶段模板生成 27 个步骤：立项定界 → 战略基线 → 架构 → 制度授权 →
      流程/表单/工具 → 工时 → 试运行 → 固化 → 改善与复制。</div>`,
    `<button class="btn btn-g" data-act="projects.close">取消</button>
     <button class="btn btn-p" data-act="projects.submitSetup">创建</button>`);

  GET('/execution/assignees').then((users) => {
    const sel = document.getElementById('spOwner');
    if (!sel) return;
    users.forEach((user) => {
      const option = document.createElement('option');
      option.value = String(user.id);
      option.textContent = user.display_name + ' · ' + (user.role_label || user.role);
      sel.appendChild(option);
    });
  }).catch(() => {});
}

async function submitSetupProgram() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const name = val('spName').trim();
  if (!name) return toast('请填写项目名称', true);
  if (!val('spOwner')) return toast('请选择项目 Owner', true);
  const start = val('spStart') || null;
  const end = val('spEnd') || null;
  if (start && end && start > end) return toast('开始日期不能晚于结束日期', true);
  try {
    const created = await POST('/projects/setup-program', {
      name,
      owner_user_id: Number(val('spOwner')),
      sponsor: val('spSponsor').trim() || null,
      objective: val('spObjective').trim() || null,
      scope: val('spScope').trim() || null,
      priority: Number(val('spPriority') || 2),
      start_date: start,
      end_date: end,
    });
    closeModal();
    toast('体系落地项目已创建（9 阶段）');
    openProject(created.id);
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 项目属性的写入口 */

function improvementCardHtml(p) {
  const rows = [
    ['来源', p.source_label
      ? p.source_label + (p.source_kpi_code ? ` · KPI ${p.source_kpi_code} ${p.source_kpi_name || ''}` : '')
      : null],
    ['问题', p.problem_statement],
    ['根因', p.root_cause],
    ['对策', p.countermeasure],
    ['验证', p.verification],
    ['收益', p.benefit],
    ['观察期至', p.observation_until],
    ['一次性投入', p.one_time_cost ? num(p.one_time_cost, 1) + ' 万元' : null],
    ['转移成本', p.transfer_cost ? num(p.transfer_cost, 1) + ' 万元' : null],
    ['复制状态', p.replication_status_label
      ? p.replication_status_label + (p.replication_note ? ' · ' + p.replication_note : '')
      : null],
    ['DMAIC', p.dmaic_stage_label
      ? p.dmaic_stage_label + (p.dmaic_note ? ' · ' + p.dmaic_note : '')
      : null],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '');
  if (!rows.length) {
    return '<div class="note">改善项目卡尚未填写，点「编辑」补充问题、根因、对策与验证。</div>';
  }
  return `
    <div class="card" style="margin-top:10px">
      <h3 style="margin-top:0">改善项目卡</h3>
      <table class="tbl">
        <tbody>${rows.map(([label, value]) =>
          `<tr><td class="tiny muted" style="width:110px">${esc(label)}</td>
            <td>${esc(String(value))}</td></tr>`).join('')}</tbody>
      </table>
    </div>`;
}

async function editProjectModal(projectId) {
  openModal('加载中…', skeleton(4), '', true);
  let p;
  let detail;
  try {
    detail = await GET('/projects/' + projectId);
    p = detail.project;
  } catch (e) {
    openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    return;
  }
  const opt = (v, label, cur) =>
    '<option value="' + v + '"' + (cur === v ? ' selected' : '') + '>' + label + '</option>';
  const stageOptions = (detail.stages || []).map((stage) =>
    opt(String(stage.stage_no), '阶段' + stage.stage_no + ' ' + stage.stage_name,
      String(p.current_stage))).join('');
  const repLabels = (state.projectMeta && state.projectMeta.replication_status_labels) || {};
  const repEntries = Object.entries(repLabels);
  const repOptions = repEntries.length
    ? repEntries.map(([v, label]) => opt(v, label, p.replication_status)).join('')
    : `<option value="${esc(p.replication_status)}" selected>${
      esc(p.replication_status_label || p.replication_status)}</option>`;
  const dmaicLabels = (state.projectMeta && state.projectMeta.dmaic_stage_labels) || {};
  const dmaicOptions = ['', ...Object.keys(dmaicLabels)].map((code) =>
    `<option value="${code}"${(p.dmaic_stage || '') === code ? ' selected' : ''}>${
      code ? esc(dmaicLabels[code]) : '不跟踪 DMAIC'}</option>`).join('');

  openModal('编辑项目 · ' + p.code, `
    <div class="row2">
      <div class="field"><label>项目名称</label><input id="epName" value="${esc(p.name)}"></div>
      <div class="field"><label>方法论</label>
        <select id="epMethod">${['BPR', 'BPI', 'LEAN', 'HYBRID'].map((m) =>
          opt(m, state.meta.methodology[m] || m, p.methodology)).join('')}</select></div>
    </div>
    <div class="row3">
      <div class="field"><label>状态</label>
        <select id="epStatus">${['PLANNING', 'ACTIVE', 'ON_HOLD', 'CLOSED', 'CANCELLED'].map((s) =>
          opt(s, state.meta.status[s] || s, p.status)).join('')}</select></div>
      <div class="field"><label>当前阶段</label>
        <select id="epStage">${stageOptions}</select></div>
      <div class="field"><label>优先级</label>
        <select id="epPriority">${[1, 2, 3, 4, 5].map((i) =>
          opt(String(i), i + (i === 1 ? ' 最高' : i === 5 ? ' 最低' : ''), String(p.priority))).join('')}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>流程 Owner</label>
        <input id="epOwner" value="${esc(p.owner)}"${canManage() ? '' : ' readonly'}>
        ${canManage() ? '' : '<div class="hint">Owner 角色不能修改归属</div>'}</div>
      <div class="field"><label>发起人</label><input id="epSponsor" value="${esc(p.sponsor || '')}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>责任部门</label><input id="epDept" value="${esc(p.department || '')}"></div>
      <div class="field"><label>整体进度（%）</label>
        <input id="epProgress" type="number" min="0" max="100" step="0.1" value="${p.progress}"></div>
    </div>
    <div class="field"><label>改善目标</label><textarea id="epObjective">${esc(p.objective || '')}</textarea></div>
    <div class="field"><label>范围边界</label><textarea id="epScope">${esc(p.scope || '')}</textarea></div>
    <div class="row3">
      <div class="field"><label>指标名称</label><input id="epMetric" value="${esc(p.metric_name || '')}"></div>
      <div class="field"><label>基线值</label>
        <input id="epBase" type="number" step="0.01" value="${p.baseline_value === null ? '' : p.baseline_value}"></div>
      <div class="field"><label>目标值</label>
        <input id="epTarget" type="number" step="0.01" value="${p.target_value === null ? '' : p.target_value}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>当前值</label>
        <input id="epCurrent" type="number" step="0.01" value="${p.current_value === null ? '' : p.current_value}"></div>
      <div class="field"><label>单位</label><input id="epUnit" value="${esc(p.metric_unit || '')}"></div>
      <div class="field"><label>预计 ROI（倍）</label>
        <input id="epRoi" type="number" step="0.1" value="${p.roi_estimate === null ? '' : p.roi_estimate}"></div>
    </div>
    <div class="field"><label>问题描述</label>
      <textarea id="epProblem" rows="2" placeholder="发生了什么、发生多少次、影响多大">${esc(p.problem_statement || '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>根因</label>
        <textarea id="epRoot" rows="2" placeholder="为什么反复发生">${esc(p.root_cause || '')}</textarea></div>
      <div class="field"><label>对策</label>
        <textarea id="epCounter" rows="2" placeholder="谁做什么、何时完成">${esc(p.countermeasure || '')}</textarea></div>
    </div>
    <div class="row2">
      <div class="field"><label>验证</label>
        <textarea id="epVerify" rows="2" placeholder="如何验证改善有效">${esc(p.verification || '')}</textarea></div>
      <div class="field"><label>收益</label>
        <textarea id="epBenefit" rows="2" placeholder="可验证、可持续的收益">${esc(p.benefit || '')}</textarea></div>
    </div>
    <div class="row3">
      <div class="field"><label>观察期至</label>
        <input id="epObservation" type="date" value="${p.observation_until || ''}"></div>
      <div class="field"><label>一次性投入（万元）</label>
        <input id="epOneTime" type="number" step="0.1" value="${p.one_time_cost || 0}"></div>
      <div class="field"><label>转移成本（万元）</label>
        <input id="epTransfer" type="number" step="0.1" value="${p.transfer_cost || 0}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>复制状态</label>
        <select id="epReplication">${repOptions}</select></div>
      <div class="field"><label>复制说明</label>
        <input id="epReplicationNote" value="${esc(p.replication_note || '')}" placeholder="适用条件 / 拒绝复制理由"></div>
    </div>
    <div class="row2">
      <div class="field"><label>DMAIC 阶段</label><select id="epDmaic">${dmaicOptions}</select></div>
      <div class="field"><label>DMAIC 说明</label>
        <input id="epDmaicNote" value="${esc(p.dmaic_note || '')}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>预算（万元）</label><input id="epBudget" type="number" step="0.1" value="${p.budget}"></div>
      <div class="field"><label>已投入（万元）</label><input id="epActual" type="number" step="0.1" value="${p.actual_cost}"></div>
      <div class="field"><label>计划结束</label>
        <input id="epEnd" type="date" value="${p.end_date || ''}"></div>
    </div>
    <label class="gap" style="margin-top:8px">
      <input id="epGate" type="checkbox" ${p.gate_required ? 'checked' : ''}>
      启用阶段门禁（进入下一阶段前必须有 PASS 签收）
    </label>`,
    `<button class="btn btn-g" data-act="projects.close">取消</button>
     <button class="btn btn-p" data-act="projects.saveEdit" data-id="${p.id}">保存</button>`, true);
}

async function openGateModal(projectId) {
  let detail;
  let gates;
  let meta;
  try {
    [detail, gates, meta] = await Promise.all([
      GET('/projects/' + projectId),
      GET('/maturity/gates?project_id=' + projectId),
      GET('/maturity/meta'),
    ]);
  } catch (e) {
    return toast(e.message, true);
  }
  const p = detail.project;
  const rows = (gates || []).map((row) => `
    <tr><td>阶段${row.stage_no}</td>
      <td><span class="tag ${row.conclusion === 'PASS' ? 't-grn' : 't-yel'}">${
        esc(row.conclusion_label || row.conclusion)}</span></td>
      <td class="tiny">${esc(row.exit_criteria || '—')}</td>
      <td class="tiny">${esc(row.evidence_url)}</td>
      <td>${esc(row.signed_by || '—')}</td></tr>`).join('')
    || '<tr><td colspan="5" class="muted">还没有门禁记录</td></tr>';
  const conclusions = (meta && meta.conclusion_labels) || {};
  openModal('阶段门禁 · ' + p.code, `
    <div class="note mb">启用门禁后，进入下一阶段必须有 PASS 签收；
      PATCH/NARROW/STOP 不视为通过。</div>
    <table class="tbl"><thead><tr><th>阶段</th><th>结论</th><th>退出条件</th>
      <th>证据</th><th>签收人</th></tr></thead><tbody>${rows}</tbody></table>
    <h3 class="mt">新增签收</h3>
    <div class="row3">
      <div class="field"><label>阶段</label><select id="gtStage">
        ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}"${
          n === p.current_stage ? ' selected' : ''}>阶段${n}${
          (state.meta.stage || {})[n] ? ' · ' + esc((state.meta.stage || {})[n]) : ''}</option>`).join('')}
      </select></div>
      <div class="field"><label>结论</label><select id="gtConclusion">
        ${Object.entries(conclusions).map(([code, label]) =>
          `<option value="${code}">${esc(label)}</option>`).join('')}
      </select></div>
      <div class="field"><label>证据链接 *</label>
        <input id="gtEvidence" placeholder="报告 / 会议纪要 / 验收单链接"></div>
    </div>
    <div class="field"><label>退出条件</label>
      <input id="gtCriteria" placeholder="本阶段离开前必须满足什么"></div>
    <div class="field"><label>说明</label><input id="gtNote"></div>`,
  `<button class="btn btn-g" data-act="projects.close">取消</button>
   <button class="btn btn-p" data-act="projects.submitGate" data-id="${projectId}">签收</button>`);
}

async function submitGate(projectId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('gtEvidence')) return toast('门禁签收必须填写证据链接', true);
  try {
    await POST('/maturity/gates', {
      project_id: projectId,
      stage_no: Number(val('gtStage')),
      conclusion: val('gtConclusion'),
      evidence_url: val('gtEvidence'),
      exit_criteria: val('gtCriteria') || null,
      note: val('gtNote') || null,
    });
    toast('门禁已签收');
    closeModal();
    openProject(projectId, { fromUrl: true });
  } catch (e) {
    toast(e.message, true);
  }
}

async function openReplicationModal(projectId) {
  let packs;
  try {
    packs = await GET('/replication-packs?source_project_id=' + projectId);
  } catch (e) {
    return toast(e.message, true);
  }
  const rows = (packs || []).map((row) => `
    <tr><td><b>${esc(row.title)}</b>
        <div class="tiny">${esc(row.conditions || '—')}</div></td>
      <td><span class="tag ${row.status === 'PUBLISHED' ? 't-grn'
        : row.status === 'REJECTED' ? 't-red' : 't-gry'}">${esc(row.status_label)}</span></td>
      <td class="tiny">知识 ${row.knowledge.length} · 制度 ${row.documents.length}
        · 模板 ${row.templates.length}</td>
      <td class="tiny">${esc(row.benefit_evidence || '—')}</td>
      <td>${row.status === 'DRAFT' ? `<button class="btn-sm"
        data-act="projects.publishPack" data-id="${row.id}" data-project="${projectId}">发布</button>` : '—'}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="muted">还没有复制资产包</td></tr>';
  openModal('复制资产包', `
    <div class="note mb">资产包记录适用条件、收益证据、失败经验与关联资产；
      发布前必须有适用条件和收益证据。</div>
    <table class="tbl"><thead><tr><th>标题 / 条件</th><th>状态</th><th>资产</th>
      <th>收益证据</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>
    <h3 class="mt">新建资产包</h3>
    <div class="field"><label>标题 *</label><input id="rpTitle"></div>
    <div class="field"><label>适用条件 *</label><textarea id="rpConditions" rows="2"></textarea></div>
    <div class="field"><label>收益证据</label><textarea id="rpBenefit" rows="2"></textarea></div>
    <div class="field"><label>失败经验</label><textarea id="rpFailure" rows="2"></textarea></div>
    <div class="row3">
      <div class="field"><label>知识 ID（逗号分隔）</label><input id="rpKnowledge"></div>
      <div class="field"><label>标准文件 ID</label><input id="rpDocuments"></div>
      <div class="field"><label>模板 ID</label><input id="rpTemplates"></div>
    </div>`,
  `<button class="btn btn-g" data-act="projects.close">关闭</button>
   <button class="btn btn-p" data-act="projects.submitReplication"
     data-id="${projectId}">创建草稿</button>`, true);
}

function parseIds(value) {
  return (value || '').split(',').map((row) => Number(row.trim())).filter((row) => row > 0);
}

async function submitReplication(projectId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('rpTitle') || !val('rpConditions')) {
    return toast('标题与适用条件不能为空', true);
  }
  try {
    await POST('/replication-packs', {
      source_project_id: projectId,
      title: val('rpTitle'),
      conditions: val('rpConditions'),
      benefit_evidence: val('rpBenefit') || null,
      failure_notes: val('rpFailure') || null,
      knowledge_ids: parseIds(val('rpKnowledge')),
      document_ids: parseIds(val('rpDocuments')),
      template_ids: parseIds(val('rpTemplates')),
    });
    toast('复制资产包已创建');
    openReplicationModal(projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function publishPack(packId, projectId) {
  try {
    await PATCH('/replication-packs/' + packId, { status: 'PUBLISHED' });
    toast('资产包已发布');
    openReplicationModal(projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function saveProjectEdit(projectId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numOrNull = (id) => (val(id) === '' ? null : Number(val(id)));

  const payload = {
    name: val('epName').trim(),
    methodology: val('epMethod'),
    status: val('epStatus'),
    current_stage: Number(val('epStage')),
    priority: Number(val('epPriority')),
    sponsor: val('epSponsor').trim() || null,
    department: val('epDept').trim() || null,
    progress: Number(val('epProgress') || 0),
    objective: val('epObjective').trim() || null,
    scope: val('epScope').trim() || null,
    metric_name: val('epMetric').trim() || null,
    baseline_value: numOrNull('epBase'),
    target_value: numOrNull('epTarget'),
    current_value: numOrNull('epCurrent'),
    metric_unit: val('epUnit').trim() || null,
    roi_estimate: numOrNull('epRoi'),
    budget: Number(val('epBudget') || 0),
    actual_cost: Number(val('epActual') || 0),
    end_date: val('epEnd') || null,
    problem_statement: val('epProblem').trim() || null,
    root_cause: val('epRoot').trim() || null,
    countermeasure: val('epCounter').trim() || null,
    verification: val('epVerify').trim() || null,
    benefit: val('epBenefit').trim() || null,
    observation_until: val('epObservation') || null,
    one_time_cost: Number(val('epOneTime') || 0),
    transfer_cost: Number(val('epTransfer') || 0),
    replication_status: val('epReplication'),
    replication_note: val('epReplicationNote').trim() || null,
    gate_required: document.getElementById('epGate')?.checked || false,
    dmaic_stage: val('epDmaic') || null,
    dmaic_note: val('epDmaicNote').trim() || null,
  };
  // OWNER 不能改归属，后端也会拦；这里干脆不发这个字段
  if (canManage()) payload.owner = val('epOwner').trim();

  if (!payload.name) return toast('请填写项目名称', true);

  try {
    await PATCH('/projects/' + projectId, payload);
    closeModal();
    toast('项目已更新');
    RENDERERS.projects();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteProject(projectId, code) {
  const ok = await confirmDialog(
    `确定删除项目 ${code}？其全部步骤记录会一并删除，且不可恢复。`,
    { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/projects/' + projectId);
    closeModal();
    toast('项目已删除');
    RENDERERS.projects();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 甘特图 */

function paintGantt(s) {
  const firstStage = s.stages.find((x) => x.start);
  const lastStage = [...s.stages].reverse().find((x) => x.end);
  const start = s.start_date || (firstStage && firstStage.start);
  const end = s.end_date || (lastStage && lastStage.end);
  if (!start || !end) {
    return '<div class="empty">该项目还没有计划起止日期，先在「编辑」里补齐计划开始/结束</div>';
  }

  // 纯日期字符串必须补 T00:00:00 再解析，否则会被当成 UTC 零点，东八区会偏一天
  const toMs = (d) => new Date(d + 'T00:00:00').getTime();
  const t0 = toMs(start);
  const t1 = toMs(end);
  const span = Math.max(1, t1 - t0);
  const pct = (d) => Math.max(0, Math.min(100, ((toMs(d) - t0) / span) * 100));
  const todayPct = (s.today >= start && s.today <= end) ? pct(s.today) : null;
  const todayLine = todayPct === null ? '' : '<div class="gantt-today" style="left:' + todayPct + '%"></div>';

  const rows = s.stages.map((st) => {
    const left = st.start ? pct(st.start) : 0;
    const right = st.end ? pct(st.end) : 0;
    const width = Math.max(1.5, right - left);
    const color = st.progress >= 100 ? 'var(--ok)' : st.progress > 0 ? 'var(--brand)' : 'var(--line-strong)';
    return `
      <div class="gantt-row">
        <span class="gantt-label">阶段${st.stage_no}<i>${esc(st.stage_name)}</i></span>
        <div class="gantt-track">
          <div class="gantt-bar" style="left:${left}%;width:${width}%;border-color:${color}"
               title="${esc(st.stage_name)} ${st.start || ''} → ${st.end || ''}">
            <div class="gantt-fill" style="width:${st.progress}%;background:${color}"></div>
            <span class="gantt-pct">${st.done}/${st.total}</span>
          </div>
          ${todayLine}
        </div>
      </div>`;
  }).join('');

  const diamonds = s.milestones.map((m) => {
    const left = m.due_date ? pct(m.due_date) : 0;
    const color = m.status === 'DONE' ? 'var(--ok)' : m.is_overdue ? 'var(--bad)' : 'var(--warn)';
    return `<div class="gantt-ms" style="left:${left}%"
      title="${esc(m.step_no + ' ' + m.name)} · ${m.due_date || ''}">
      <span class="dia" style="background:${color}"></span>
      <span class="gantt-ms-label">${esc(m.step_no)}</span>
    </div>`;
  }).join('');

  const overdue = s.milestones.filter((m) => m.is_overdue).length;

  return `
    <div class="note mb">
      计划周期 ${esc(s.start_date || '—')} → ${esc(s.end_date || '—')}
      ${s.total_days !== null ? '（' + s.total_days + ' 天）' : ''}
      · 已过 ${s.elapsed_days === null ? '—' : s.elapsed_days} 天
      ${overdue ? ' · <span style="color:var(--bad)">' + overdue + ' 个里程碑逾期</span>' : ''}
      <div class="tiny" style="margin-top:4px">
        绿=已完成 · 蓝=进行中 · 灰=未启动 · 竖线=今天 · ◆=里程碑（阶段决策门）</div>
    </div>
    <div class="gantt">
      <div class="gantt-row">
        <span class="gantt-label">阶段<i>按计划窗口均分</i></span>
        <div class="gantt-track gantt-axis">
          <span style="left:0">${esc(start)}</span>
          <span style="left:100%">${esc(end)}</span>
        </div>
      </div>
      ${rows}
      <div class="gantt-row">
        <span class="gantt-label">里程碑<i>阶段决策门</i></span>
        <div class="gantt-track gantt-track-ms">${diamonds}</div>
      </div>
    </div>
    <table class="tbl mt">
      <thead><tr><th>里程碑</th><th>所属阶段</th><th>计划日期</th><th>状态</th></tr></thead>
      <tbody>${s.milestones.map((m) => `
        <tr><td><b>${esc(m.step_no)}</b> ${esc(m.name)}</td>
          <td>阶段${m.stage_no}</td>
          <td>${esc(m.due_date || '—')}</td>
          <td><span class="tag ${m.status === 'DONE' ? 't-grn' : m.is_overdue ? 't-red' : 't-yel'}">
            ${m.status === 'DONE' ? '已完成' : m.is_overdue ? '已逾期' : '待完成'}</span></td>
        </tr>`).join('') || emptyRow(4, '暂无里程碑')}
      </tbody>
    </table>`;
}

/** 步骤 → 工作现场：直接在原模块开工，而不是只改一个状态。 */
function stepWorkspace(stepNo, stageNo, processId) {
  if (stepNo === '1.4') {
    return { label: '方法匹配', view: 'workflow', params: { tab: 'method' } };
  }
  if (stepNo.startsWith('1.')) {
    return { label: '流程地图', view: 'map', params: {} };
  }
  if (stepNo === '3.3') {
    return { label: '授权矩阵', view: 'authorization', params: {} };
  }
  if (stepNo.startsWith('2.') || stepNo.startsWith('3.')) {
    return processId
      ? { label: '流程设计器', view: 'designer', params: { process: processId } }
      : { label: '流程地图', view: 'map', params: {} };
  }
  if (stepNo.startsWith('4.')) {
    return { label: '十层单页', view: 'pilot', params: {} };
  }
  if (stepNo.startsWith('5.')) {
    return { label: '运营监控', view: 'monitor', params: {} };
  }
  return { label: '交付物', view: 'deliverables', params: { tab: 'project' } };
}

async function reloadProjectWorkflow(projectId) {
  const wk = document.getElementById('pd-wk');
  const onWk = !!wk && !wk.classList.contains('hide');
  await openProject(projectId);
  // 后端可能已推进阶段，重开后停留在「工作流推进」页签上。
  // 若用户在刷新期间关掉了弹窗，这里不能再操作它的 DOM。
  const maskOpen = document.getElementById('mask').classList.contains('show');
  const pane = document.getElementById('pd-wk');
  if (onWk && maskOpen && pane) {
    const btn = [...document.querySelectorAll('#mBody .tabs button')].find(
      (b) => b.textContent.includes('工作流'),
    );
    if (btn) tab(btn, 'pd-wk');
  }
}

/** 切换步骤状态。走工作台接口，保留证据门槛与六状态校验。 */
async function patchStep(stepId, status, projectId) {
  try {
    await PATCH(`/projects/${projectId}/workflow/steps/${stepId}`, { status });
    toast('步骤状态已更新');
    await reloadProjectWorkflow(projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

function openStepProgress(stepId, projectId) {
  const detail = state.projectDetail || {};
  const step = (detail.steps || []).find((row) => row.id === stepId);
  if (!step) return toast('步骤不存在', true);
  const labels = detail.step_status_labels || {};
  const options = Object.entries(labels).map(([code, label]) =>
    `<option value="${code}"${code === step.status ? ' selected' : ''}>${esc(label)}</option>`,
  ).join('');
  openModal(`${step.step_no} ${step.name} · 记录进度`, `
    <div class="note mb">状态是数据字段：已填写不等于已满足；待验证需要接收方确认。</div>
    <div class="field"><label>状态</label>
      <select id="spStatus" data-act="projects.stepStatusPreview">${options}</select></div>
    <div class="field"><label>进度说明</label>
      <textarea id="spNote" rows="3" placeholder="这一步做到哪了、下一步是什么">${
        esc(step.notes || '')}</textarea></div>
    <div class="field"><label>计划完成</label>
      <input id="spDue" type="date" value="${esc(step.due_date || '')}"></div>
    <div class="field hide" data-for="PENDING_VERIFY"><label>接收方（待验证必填）</label>
      <input id="spReceiver" placeholder="谁负责验收"></div>
    <div class="row3 hide" data-for="BLOCKED">
      <div class="field"><label>受阻原因</label><input id="spBlockedReason"></div>
      <div class="field"><label>受阻责任人</label><input id="spBlockedOwner"></div>
      <div class="field"><label>预计解除</label><input id="spBlockedDue" type="date"></div>
    </div>
    <div class="row3 hide" data-for="DECISION">
      <div class="field"><label>决策选项（每行一条）</label>
        <textarea id="spDecisionOptions" rows="2"></textarea></div>
      <div class="field"><label>决策人</label><input id="spDecisionMaker"></div>
      <div class="field"><label>决策时限</label><input id="spDecisionDue" type="date"></div>
    </div>`,
  `<button class="btn btn-g" data-act="projects.close">取消</button>
   <button class="btn btn-p" data-act="projects.submitStepProgress"
     data-id="${step.id}" data-project="${projectId}">保存进度</button>`,
  false, { keepPrevious: true });
  toggleStepStatusFields(step.status);
}

function toggleStepStatusFields(status) {
  document.querySelectorAll('#mBody [data-for]').forEach((el) => {
    el.classList.toggle('hide', el.dataset.for !== status);
  });
}

async function submitStepProgress(stepId, projectId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const status = val('spStatus');
  const payload = {
    status,
    note: val('spNote') || null,
    due_date: val('spDue') || null,
  };
  if (status === 'PENDING_VERIFY') payload.receiver = val('spReceiver') || null;
  if (status === 'BLOCKED') {
    payload.blocked_reason = val('spBlockedReason') || null;
    payload.blocked_owner = val('spBlockedOwner') || null;
    payload.blocked_due = val('spBlockedDue') || null;
  }
  if (status === 'DECISION') {
    payload.decision_options = val('spDecisionOptions')
      .split('\n').map((row) => row.trim()).filter(Boolean);
    payload.decision_maker = val('spDecisionMaker') || null;
    payload.decision_due = val('spDecisionDue') || null;
  }
  try {
    await PATCH(`/projects/${projectId}/workflow/steps/${stepId}`, payload);
    toast('进度已保存');
    closeModal();
    await reloadProjectWorkflow(projectId);
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 立项向导 */

function newProjectWizard(prefill) {
  const pre = prefill || {};
  const goal = pre.objective || null;
  const goalTarget = goal && (goal.baseline_value !== null || goal.target_value !== null)
    ? ` · 目标 ${goal.baseline_value === null ? '—' : num(goal.baseline_value, 2)}
      → ${goal.target_value === null ? '—' : num(goal.target_value, 2)}
      ${esc(goal.unit || '')}`
    : '';
  const nameValue = pre.name
    ? pre.name + '流程优化'
    : (goal ? goal.name + '承接项目' : '');
  const objectiveValue = goal
    ? (goal.description || `承接战略目标「${goal.name}」`)
    : '';
  openModal('新建流程项目 · 立项向导', `
    ${goal ? `<div class="note mb">承接战略目标：<b>${esc(goal.code)} ${esc(goal.name)}</b>${
      goalTarget}。目标值已预填，可在下方调整。</div>` : ''}
    ${pre.name ? `<div class="note mb">从流程地图带入：<b>${esc(pre.name)}</b>。
      请补充 Owner、改善目标与基线数据后立项。</div>` : ''}
    <div class="note mb">
      先描述流程现状与目标，点「匹配方法论」让后端引擎给出推荐（含判断依据与风险提示），
      再确认基本信息提交立项。
    </div>

    <h3>① 匹配方法论</h3>
    <div class="row3">
      <div class="field"><label>流程现状</label>
        <select id="npState">
          <option value="SEVERE_OUTDATED">严重过时、断裂、与战略脱节</option>
          <option value="SOUND_BUT_INEFFICIENT" selected>基本合理但效率不足</option>
          <option value="SHOPFLOOR_WASTE">现场/操作层浪费明显</option>
          <option value="MIXED">混合状态</option>
        </select></div>
      <div class="field"><label>目标改善幅度（%）</label>
        <input id="npPct" type="number" value="30" min="0" max="100"></div>
      <div class="field"><label>范围</label>
        <select id="npScope">
          <option value="END_TO_END">端到端跨职能</option>
          <option value="LOCAL" selected>单一部门内部</option>
          <option value="SHOPFLOOR">现场/操作层</option>
        </select></div>
    </div>
    <div class="row3">
      <div class="field"><label>涉及组织/权责调整</label>
        <select id="npOrg"><option value="false">否</option><option value="true">是</option></select></div>
      <div class="field"><label>有流程数据/日志</label>
        <select id="npData"><option value="true">是</option><option value="false">否</option></select></div>
      <div class="field"><label>计划周期（月）</label>
        <input id="npDur" type="number" value="6" min="1" max="36"></div>
    </div>
    <button class="btn btn-g" id="npRecBtn" data-act="projects.wizardRecommend">匹配方法论</button>
    <div id="npResult" class="mt"></div>

    <h3 class="mt">② 基本信息</h3>
    <div class="row2">
      <div class="field"><label>项目名称 *</label>
        <input id="npName" value="${esc(nameValue)}" placeholder="如：采购需求提报流程重组"></div>
      <div class="field"><label>方法论 *</label>
        <select id="npMethod">
          <option value="BPR">BPR 阶跃式重组</option>
          <option value="BPI" selected>BPI 渐进式优化</option>
          <option value="LEAN">精益改善·消除浪费</option>
          <option value="HYBRID">混合模式</option>
        </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>流程 Owner *</label>
        <input id="npOwner" value="${esc(goal && goal.owner ? goal.owner : '')}"
          placeholder="如：陈经理"></div>
      <div class="field"><label>发起人</label><input id="npSponsor" placeholder="如：采购总监-刘总"></div>
    </div>
    <div class="row2">
      <div class="field"><label>责任部门</label><input id="npDept" placeholder="如：采购部"></div>
      <div class="field"><label>关联流程</label>
        <select id="npProcess"><option value="">不关联</option></select>
        <div class="hint">关联后可到「流程设计器」做泳道建模与测算</div></div>
    </div>
    <div class="field"><label>改善目标</label>
      <textarea id="npObjective" placeholder="如：端到端周期从 14 天压到 5 天，取消 3 层冗余审批">${esc(objectiveValue)}</textarea></div>
    <div class="row3">
      <div class="field"><label>指标名称</label>
        <input id="npMetric" value="${esc(goal ? goal.name : '')}" placeholder="如：端到端周期"></div>
      <div class="field"><label>基线值</label>
        <input id="npBase" type="number" step="0.1" value="${
          goal && goal.baseline_value !== null ? goal.baseline_value : ''}" placeholder="14"></div>
      <div class="field"><label>目标值</label>
        <input id="npTarget" type="number" step="0.1" value="${
          goal && goal.target_value !== null ? goal.target_value : ''}" placeholder="5"></div>
    </div>
    <div class="row3">
      <div class="field"><label>单位</label>
        <input id="npUnit" value="${esc(goal && goal.unit ? goal.unit : '')}" placeholder="天"></div>
      <div class="field"><label>预算（万元）</label><input id="npBudget" type="number" step="0.1" value="0"></div>
      <div class="field"><label>优先级</label>
        <select id="npPriority">
          <option value="1">1 最高</option><option value="2">2 高</option>
          <option value="3" selected>3 中</option><option value="4">4 低</option><option value="5">5 最低</option>
        </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>计划开始</label><input id="npStart" type="date"></div>
      <div class="field"><label>计划结束</label><input id="npEnd" type="date"></div>
    </div>`,
    `<button class="btn btn-g" data-act="projects.close">取消</button>
     <button class="btn btn-p" data-act="projects.submit">立项</button>`, true);

  // 关联流程下拉：取 L3 / L4 流程（项目通常落在这一层）
  GET('/process-map/flat').then((rows) => {
    const sel = document.getElementById('npProcess');
    if (!sel) return;
    rows.filter((r) => r.level >= 3).forEach((r) => {
      const o = document.createElement('option');
      o.value = String(r.id);
      o.textContent = 'L' + r.level + ' ' + r.code + ' ' + r.name;
      sel.appendChild(o);
    });
    if (pre.processId) {
      sel.value = String(pre.processId);
    }
  }).catch(() => { /* 下拉拿不到不影响立项 */ });
}

async function wizardRecommend() {
  const box = document.getElementById('npResult');
  box.innerHTML = skeleton(3);
  try {
    const r = await POST('/projects/recommend-methodology', {
      process_state: document.getElementById('npState').value,
      target_improvement_pct: Number(document.getElementById('npPct').value || 0),
      scope: document.getElementById('npScope').value,
      involves_org_change: document.getElementById('npOrg').value === 'true',
      data_available: document.getElementById('npData').value === 'true',
      duration_target_months: Number(document.getElementById('npDur').value || 6),
    });
    state.wizardRec = r;
    document.getElementById('npMethod').value = r.methodology;
    box.innerHTML = renderRecommendation(r, true) +
      '<div class="note mt">已自动把「' + esc(state.meta.methodology[r.methodology] || r.methodology) +
      '」填入下方方法论字段，可手动改。</div>';
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

async function submitProject() {
  const name = document.getElementById('npName').value.trim();
  const owner = document.getElementById('npOwner').value.trim();
  if (!name) return toast('请填写项目名称', true);
  if (!owner) return toast('请填写流程 Owner', true);

  const val = (id) => document.getElementById(id).value;
  const numOrNull = (id) => {
    const v = val(id);
    return v === '' ? null : Number(v);
  };
  const payload = {
    name,
    owner,
    methodology: val('npMethod'),
    status: 'PLANNING',
    current_stage: 1,
    priority: Number(val('npPriority')),
    process_id: val('npProcess') ? Number(val('npProcess')) : null,
    sponsor: val('npSponsor') || null,
    department: val('npDept') || null,
    objective: val('npObjective') || null,
    metric_name: val('npMetric') || null,
    baseline_value: numOrNull('npBase'),
    target_value: numOrNull('npTarget'),
    metric_unit: val('npUnit') || null,
    budget: numOrNull('npBudget') || 0,
    start_date: val('npStart') || null,
    end_date: val('npEnd') || null,
    seed_workflow: true,
  };

  try {
    const created = await POST('/projects', payload);
    closeModal();
    toast('项目已立项：' + created.code);
    RENDERERS.projects();
  } catch (e) {
    toast(e.message, true);
  }
}


export const actions = {
  'projects.open': openProject,
  'projects.newWizard': newProjectWizard,
};
export { renderProjects };
