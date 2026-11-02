/* 视图：dashboard
 *
 * 总览只回答今天处理哪一件：越线的指标、过期的异常、接着推进的项目。
 * 下一条该改的流程用地图上的优先级。框架边界留在开始使用。
 */
import { esc, num, HEAT_CLASS, HEAT_LABEL } from '../core/format.js';
import { metricHelp } from '../core/metrics.js';
import { viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, urlParams } from '../core/router.js';
import { GET } from '../core/api.js';
import { cockpitTabBar, cockpitProcessSelect, loadCockpitProcesses } from '../core/cockpit.js';

on('dashboard.kpi', ({ key }) => {
  if (key === 'open_exceptions') openExceptions();
  else if (key === 'kpi_alert') openKpi();
});
on('dashboard.openProject', ({ id }) => {
  go('projects', { params: { project: Number(id) }, push: true });
});
on('dashboard.openProcess', ({ code }) => openProcessOnMap(code));
on('dashboard.goImprovementMap', () => openImprovementMap());
on('dashboard.goProjects', () => go('projects'));

const renderDashboard = () => {
  state.cockpit.processId = Number(urlParams().process) || null;
  return renderAsync('dashboard',
  () => Promise.all([
    GET('/dashboard/overview?board_limit=5'),
    GET('/process-map/heatmap?level=3&limit=5'),
    GET('/dashboard/home'),
    loadCockpitProcesses(),
  ]).then(([overview, priority, home, flowList]) => ({ overview, priority, home, flowList })),
  (payload) => {
    const d = payload.overview;
    const selected = state.cockpit.processId;
    const priority = selected
      ? payload.priority.filter((row) => row.id === selected)
      : payload.priority;
    const home = payload.home;
    const nextActions = (home.next_actions || []).map((item) => `
      <div class="next-action">
        <div style="min-width:0">
          <b>${esc(item.code)} ${esc(item.name)}</b>
          <div class="tiny">阶段 ${item.current_stage} ${esc(item.stage_name)} ·
            进度 ${num(item.progress, 0)}%</div>
          <div class="tiny">下一步：${esc(item.next_step_no || '—')} ${
            esc(item.next_step_name || '')}</div>
          ${item.next_suggestion
            ? `<div class="tiny muted">${esc(item.next_suggestion)}</div>` : ''}
        </div>
        <div class="gap">
          ${item.open_exceptions
            ? `<span class="tag t-red">${item.open_exceptions} 项异常</span>` : ''}
          ${item.is_overdue ? '<span class="tag t-yel">已逾期</span>' : ''}
          <button class="btn-sm" data-act="dashboard.openProject"
            data-id="${item.project_id}">继续推进</button>
        </div>
      </div>`).join('');
    const nextActionsHtml = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">我的当前推进</h3>
            <div class="desc" style="margin:2px 0 0">按当前阶段和下一步继续；
              点“继续推进”打开项目详情</div></div>
          <a class="link-btn" data-act="dashboard.goProjects">项目组合 →</a>
        </div>
        ${nextActions || '<div class="empty">还没有在推进的改善项目</div>'}
      </div>`;
    const es = d.exception_summary;
    const openCount = (es.open || 0) + (es.in_progress || 0);
    const priorityList = priority.map((p) => `
      <button class="db-pri" type="button" data-act="dashboard.openProcess"
          data-code="${esc(p.code)}">
        <span class="tag ${HEAT_CLASS[p.heat_level] || 'heat-low'}">
          ${HEAT_LABEL[p.heat_level] || p.heat_level} ${num(p.priority_score, 0)}</span>
        <b>${esc(p.name)}</b>
        <span class="tiny">${esc(p.code)} · ${esc(p.owner || '未指定')} · 健康 ${
          p.health_score === null ? '未评估' : num(p.health_score, 0) + '%'} · ${
          p.project_count} 个项目</span>
      </button>`).join('') || `<div class="empty">${
        selected ? '这条流程不在前 5。' : '暂无待改善流程'}</div>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>运营驾驶舱<span class="module-badge">总览</span></h2>
            <div class="desc">左边选下一条流程，中间接着推进，右边看今天越线的指标和异常</div></div>
          ${cockpitProcessSelect(payload.flowList)}
        </div>
        <div class="mt">${cockpitTabBar('overview')}</div>
      </div>
      <div class="db-shell">
        <aside class="card db-side">
          <div class="between mb">
            <h3 style="margin:0">改善优先级</h3>
            <a class="link-btn" data-act="dashboard.goImprovementMap">地图</a>
          </div>
          <div class="tiny muted mb">战略 × 痛点 × 改善空间，前 5</div>
          <div class="db-pri-list">${priorityList}</div>
        </aside>
        <main class="db-main">${nextActionsHtml}</main>
        <aside class="card db-aside">
          <h3 style="margin:0 0 8px">今天</h3>
          <button type="button" class="db-alert" data-act="dashboard.kpi" data-key="kpi_alert">
            <b>${num(home.kpi_red_yellow, 0)}<small>/${num(home.kpi_total, 0)}</small></b>
            <span>${metricHelp('kpi_red_yellow', '红/黄 KPI')}</span>
            <span class="tiny">最新点落在红线或黄线</span>
          </button>
          <button type="button" class="db-alert" data-act="dashboard.kpi" data-key="open_exceptions">
            <b>${num(openCount, 0)}<small>件</small></b>
            <span>${metricHelp('open_exceptions', '未闭环异常')}</span>
            <span class="tiny">超期 ${num(es.overdue, 0)} 件</span>
          </button>
        </aside>
      </div>`;
  });
};

function openExceptions() {
  state.monitor.tab = 'exceptions';
  const params = { tab: 'exceptions' };
  if (state.cockpit.processId) params.process = state.cockpit.processId;
  go('monitor', { params, push: true });
}

function openKpi() {
  state.monitor.tab = 'kpi';
  const params = { tab: 'kpi' };
  if (state.cockpit.processId) params.process = state.cockpit.processId;
  go('monitor', { params, push: true });
}

function openImprovementMap() {
  state.map.improvementOnly = true;
  go('map');
}

/** 驾驶舱优先级 → 地图：定位到该流程并打开详情 */
function openProcessOnMap(code) {
  state.map.improvementOnly = false;
  state.map.pendingJump = code;
  go('map');
}

export { renderDashboard };
