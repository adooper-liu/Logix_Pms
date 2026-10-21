/* 视图：projects */
import { esc, num, pct, methodTag, statusTag, bar, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, tab, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { AUTH, role, canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { openDesigner } from './designer.js';

/* ============================================================ 4. 流程项目组合 */

const renderProjects = () => {
  const f = state.projects.filter;
  const qs = [];
  if (f.methodology) qs.push('methodology=' + f.methodology);
  if (f.status) qs.push('status=' + f.status);
  if (f.stage) qs.push('stage=' + f.stage);
  if (state.projects.keyword) qs.push('keyword=' + encodeURIComponent(state.projects.keyword));
  qs.push('page_size=100');

  renderAsync('projects',
    () => GET('/projects?' + qs.join('&')),
    (page) => {
      const rows = page.items.map((p) => `
        <tr class="clk" onclick="openProject(${p.id})">
          <td><b>${esc(p.name)}</b>
            <div class="tiny">${esc(p.code)}${p.process_name ? ' · ' + esc(p.process_name) : ''}</div></td>
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

      viewEl().innerHTML = `
        <div class="card">
          <div class="between mb">
            <div><h2 style="margin:0">流程项目组合管理</h2>
              <div class="desc" style="margin:0">共 ${page.total} 个项目 · 点击行查看详情、KPI 与下一步动作</div></div>
            <button class="btn btn-p" onclick="newProjectWizard()">+ 新建流程项目</button>
          </div>
          <div class="gap mb" style="flex-wrap:wrap">
            <select class="sel" onchange="setPFilter('methodology', this.value)">
              ${opt('', '全部方法', f.methodology)}
              ${['BPR', 'BPI', 'LEAN', 'HYBRID'].map((m) =>
                opt(m, state.meta.methodology[m] || m, f.methodology)).join('')}
            </select>
            <select class="sel" onchange="setPFilter('stage', this.value)">
              ${opt('', '全部阶段', f.stage)}
              ${[1, 2, 3, 4, 5].map((i) => opt(String(i), '阶段' + i + ' ' +
                (state.meta.stage[i] || ''), f.stage)).join('')}
            </select>
            <select class="sel" onchange="setPFilter('status', this.value)">
              ${opt('', '全部状态', f.status)}
              ${['PLANNING', 'ACTIVE', 'ON_HOLD', 'CLOSED', 'CANCELLED'].map((s) =>
                opt(s, state.meta.status[s] || s, f.status)).join('')}
            </select>
            ${(f.methodology || f.stage || f.status || state.projects.keyword)
              ? '<button class="btn-sm" style="align-self:center" onclick="clearPFilter()">清空筛选</button>' : ''}
          </div>
          <table class="tbl">
            <thead><tr><th>项目</th><th>方法</th><th>阶段</th><th>Owner</th>
              <th>改善指标</th><th>已用/预算(万)</th><th>整体进度</th><th>状态</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    });
};

function setPFilter(key, value) {
  state.projects.filter[key] = value;
  RENDERERS.projects();
}
function clearPFilter() {
  state.projects.filter = { methodology: '', status: '', stage: '' };
  state.projects.keyword = '';
  document.getElementById('searchInput').value = '';
  RENDERERS.projects();
}

/* -------------------------------------------------- 项目详情 */

async function openProject(id) {
  const gen = openModal('加载中…', skeleton(5), '', true);
  let d;
  let sched = null;
  try {
    [d, sched] = await Promise.all([
      GET('/projects/' + id),
      GET('/projects/' + id + '/schedule').catch(() => null),
    ]);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    return;
  }
  // 用户在请求返回前关掉了弹窗，就别再把它弹回来
  if (!modalAlive(gen)) return;
  const p = d.project;
  state.projectDetail = d;

  const tabs = `
    <div class="tabs">
      <button class="on" onclick="tab(this,'pd-ov')">概览</button>
      <button onclick="tab(this,'pd-kp')">KPI 追踪</button>
      <button onclick="tab(this,'pd-wk')">工作流推进</button>
      <button onclick="tab(this,'pd-gt')">甘特图</button>
      <button onclick="tab(this,'pd-nx')">下一步</button>
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
            p.progress >= 70 ? '#16a34a' : p.progress >= 30 ? '#f59e0b' : '#ef4444'}">
            ${num(p.progress, 0)}%</div><div class="lab">步骤完成度</div></div>
        <div class="kpi" style="padding:13px 15px">
          <div class="num" style="font-size:22px;color:#2f5bea">${
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

  const stepStatusOpts = (cur) => [
    ['PENDING', '未开始'], ['IN_PROGRESS', '进行中'], ['DONE', '已完成'], ['SKIPPED', '已跳过'],
  ].map(([v, l]) => '<option value="' + v + '"' + (cur === v ? ' selected' : '') + '>' + l + '</option>').join('');

  const wfPane = `
    <div data-pane id="pd-wk" class="hide">
      <div class="note mb">步骤状态由「标准工作流模板」自动生成。阶段内步骤全部完成后，项目会自动推进到下一阶段。</div>
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
            ${steps.map((st) => `
              <div class="stepitem ${st.status === 'DONE' ? 'done' : ''}">
                <span class="no">${esc(st.step_no)}</span>
                <span class="nm"><b>${esc(st.name)}</b>
                  <i>${esc(st.deliverable || '')}${st.owner ? ' · ' + esc(st.owner) : ''}</i></span>
                <select onchange="patchStep(${st.id}, this.value, ${p.id})">${stepStatusOpts(st.status)}</select>
              </div>`).join('')}
          </div>
        </div>`;
      }).join('')}
    </div>`;

  const ganttPane = `
    <div data-pane id="pd-gt" class="hide">
      ${sched ? paintGantt(sched) : '<div class="empty">甘特图数据加载失败</div>'}
    </div>`;

  const nextPane = `
    <div data-pane id="pd-nx" class="hide">
      ${d.next_action ? `
        <div class="field"><label>下一步动作（阶段${d.next_action.stage_no} · 步骤 ${esc(d.next_action.step_no || '—')}）</label>
          <textarea readonly style="min-height:120px">${esc(d.next_action.name + '\n\n' + d.next_action.suggestion)}</textarea></div>` :
        '<div class="note mb">五个阶段全部完成，项目已进入运营阶段。</div>'}
      <h3>当前阶段待办步骤</h3>
      ${d.current_steps.length ? `
        <div class="steplist">${d.current_steps.map((st) => `
          <div class="stepitem">
            <span class="no">${esc(st.step_no)}</span>
            <span class="nm"><b>${esc(st.name)}</b><i>交付物：${esc(st.deliverable || '—')}</i></span>
          </div>`).join('')}</div>` : '<div class="empty">当前阶段没有待办步骤</div>'}
    </div>`;

  const canEditThis = canManage()
    || (role() === 'OWNER' && AUTH.user && AUTH.user.display_name === p.owner);

  openModal(p.name, tabs + overview + kpiPane + wfPane + ganttPane + nextPane, `
    ${canManage()
      ? '<button class="btn btn-g" style="margin-right:auto;color:#d14343"'
        + ' onclick="deleteProject(' + p.id + ', \'' + esc(p.code) + '\')">删除项目</button>'
      : ''}
    <button class="btn btn-g" onclick="closeModal()">关闭</button>
    ${canEditThis ? '<button class="btn btn-g" onclick="editProjectModal(' + p.id + ')">编辑</button>' : ''}
    ${p.process_id ? '<button class="btn btn-p" onclick="closeModal();openDesigner(' + p.process_id + ')">查看流程模型</button>' : ''}`,
    true);
}

/* -------------------------------------------------- 项目属性的写入口 */

async function editProjectModal(projectId) {
  openModal('加载中…', skeleton(4), '', true);
  let p;
  try {
    p = (await GET('/projects/' + projectId)).project;
  } catch (e) {
    openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    return;
  }
  const opt = (v, label, cur) =>
    '<option value="' + v + '"' + (cur === v ? ' selected' : '') + '>' + label + '</option>';

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
        <select id="epStage">${[1, 2, 3, 4, 5].map((i) =>
          opt(String(i), '阶段' + i + ' ' + (state.meta.stage[i] || ''), String(p.current_stage))).join('')}</select></div>
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
    <div class="row3">
      <div class="field"><label>预算（万元）</label><input id="epBudget" type="number" step="0.1" value="${p.budget}"></div>
      <div class="field"><label>已投入（万元）</label><input id="epActual" type="number" step="0.1" value="${p.actual_cost}"></div>
      <div class="field"><label>计划结束</label>
        <input id="epEnd" type="date" value="${p.end_date || ''}"></div>
    </div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveProjectEdit(${p.id})">保存</button>`, true);
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
  if (!confirm('确定删除项目 ' + code + '？其全部步骤记录会一并删除，且不可恢复。')) return;
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
    const color = st.progress >= 100 ? '#16a34a' : st.progress > 0 ? '#2f5bea' : '#c3cbe0';
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
    const color = m.status === 'DONE' ? '#16a34a' : m.is_overdue ? '#ef4444' : '#f59e0b';
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
      ${overdue ? ' · <span style="color:#ef4444">' + overdue + ' 个里程碑逾期</span>' : ''}
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

/** 切换步骤状态。后端会自动回算项目进度与阶段推进。 */
async function patchStep(stepId, status, projectId) {
  try {
    await PATCH('/projects/steps/' + stepId, { status });
    toast('步骤状态已更新');
    const onWk = !document.getElementById('pd-wk').classList.contains('hide');
    await openProject(projectId);
    // 后端可能已推进阶段，重开后停留在「工作流推进」页签上。
    // 若用户在刷新期间关掉了弹窗，这里不能再操作它的 DOM。
    const maskOpen = document.getElementById('mask').classList.contains('show');
    const pane = document.getElementById('pd-wk');
    if (onWk && maskOpen && pane) {
      const btn = [...document.querySelectorAll('#mBody .tabs button')].find((b) => b.textContent.includes('工作流'));
      if (btn) tab(btn, 'pd-wk');
    }
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 立项向导 */

function newProjectWizard() {
  openModal('新建流程项目 · 立项向导', `
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
    <button class="btn btn-g" id="npRecBtn" onclick="wizardRecommend()">匹配方法论</button>
    <div id="npResult" class="mt"></div>

    <h3 class="mt">② 基本信息</h3>
    <div class="row2">
      <div class="field"><label>项目名称 *</label>
        <input id="npName" placeholder="如：采购需求提报流程重组"></div>
      <div class="field"><label>方法论 *</label>
        <select id="npMethod">
          <option value="BPR">BPR 阶跃式重组</option>
          <option value="BPI" selected>BPI 渐进式优化</option>
          <option value="LEAN">精益改善·消除浪费</option>
          <option value="HYBRID">混合模式</option>
        </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>流程 Owner *</label><input id="npOwner" placeholder="如：陈经理"></div>
      <div class="field"><label>发起人</label><input id="npSponsor" placeholder="如：采购总监-刘总"></div>
    </div>
    <div class="row2">
      <div class="field"><label>责任部门</label><input id="npDept" placeholder="如：采购部"></div>
      <div class="field"><label>关联流程</label>
        <select id="npProcess"><option value="">不关联</option></select>
        <div class="hint">关联后可到「流程设计器」做泳道建模与测算</div></div>
    </div>
    <div class="field"><label>改善目标</label>
      <textarea id="npObjective" placeholder="如：端到端周期从 14 天压到 5 天，取消 3 层冗余审批"></textarea></div>
    <div class="row3">
      <div class="field"><label>指标名称</label><input id="npMetric" placeholder="如：端到端周期"></div>
      <div class="field"><label>基线值</label><input id="npBase" type="number" step="0.1" placeholder="14"></div>
      <div class="field"><label>目标值</label><input id="npTarget" type="number" step="0.1" placeholder="5"></div>
    </div>
    <div class="row3">
      <div class="field"><label>单位</label><input id="npUnit" placeholder="天"></div>
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
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitProject()">立项</button>`, true);

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
    box.innerHTML = renderRecommendation(r) +
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


export { renderProjects, clearPFilter, deleteProject, editProjectModal, newProjectWizard, openProject, paintGantt, patchStep, saveProjectEdit, setPFilter, submitProject, wizardRecommend };
