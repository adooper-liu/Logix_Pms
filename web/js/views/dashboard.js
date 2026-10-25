/* 视图：dashboard */
import { esc, num, M_ICON, methodTag, statusTag, bar, emptyRow, HEAT_CLASS, HEAT_LABEL } from '../core/format.js';
import { metricHelp } from '../core/metrics.js';
import { viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go } from '../core/router.js';
import { GET } from '../core/api.js';

/* ============================================================ 1. 管理驾驶舱 */

on('dashboard.kpi', ({ key }) => {
  if (key === 'active_projects') openProjects({ status: 'ACTIVE' });
  else if (key === 'improvement_targets') openImprovementMap();
  else if (key === 'open_exceptions') openExceptions();
  else openProjects();
});
on('dashboard.stage', ({ stage }) => openStage(Number(stage)));
on('dashboard.methodology', ({ methodology }) => openMethodology(methodology));
on('dashboard.openProject', ({ id }) => {
  go('projects', { params: { project: Number(id) }, push: true });
});
on('dashboard.openProcess', ({ code }) => openProcessOnMap(code));
on('dashboard.go', ({ view }) => go(view));
on('dashboard.setupProjects', () => {
  state.projects.filter = {
    methodology: '', status: '', stage: '', projectType: 'GOVERNANCE_SETUP',
  };
  state.projects.keyword = '';
  go('projects');
});
on('dashboard.goImprovementMap', () => openImprovementMap());
on('dashboard.goExceptions', () => openExceptions());
on('dashboard.goProjects', () => go('projects'));

const METHOD_COLOR = {
  BPR: 'var(--bad)', BPI: 'var(--warn-strong)', LEAN: 'var(--ok-strong)', HYBRID: 'var(--purple-strong)',
};

function actionAttrs(action) {
  return action.action === 'dashboard.setupProjects'
    ? 'data-act="dashboard.setupProjects"'
    : 'data-act="dashboard.go"';
}

const renderDashboard = () => renderAsync('dashboard',
  () => Promise.all([
    GET('/dashboard/overview?board_limit=5'),
    GET('/process-map/heatmap?level=3&limit=5'),
    GET('/dashboard/home'),
  ]).then(([overview, priority, home]) => ({ overview, priority, home })),
  (payload) => {
    const d = payload.overview;
    const priority = payload.priority;
    const home = payload.home;
    const homeHtml = `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">${esc(home.headline)}</h3>
            <div class="desc" style="margin:2px 0 0">当前角色：${esc(home.role_label)}</div></div>
          <button class="btn btn-g" data-act="dashboard.go" data-view="start">启动向导</button>
        </div>
        <div class="grid g3">
          ${home.blocks.map((block) => `
            <div class="card" style="margin:0">
              <div class="between mb"><b>${esc(block.title)}</b>
                <span class="tiny muted">${esc(block.description || '')}</span></div>
              ${block.items.map((item) => `
                <div class="between tiny"><span>${esc(item.label)}</span>
                  <b>${esc(item.value)}</b></div>
                ${item.hint ? `<div class="tiny muted">${esc(item.hint)}</div>` : ''}`).join('')}
              <div class="gap mt">
                ${block.actions.map((action) => `<button class="btn-sm"
                  ${actionAttrs(action)} data-view="${esc(action.view)}"
                  title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
              </div>
            </div>`).join('')}
        </div>
      </div>`;
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
          <div class="gap">
            <span class="tag t-gry">在办改善 ${home.active_project_count || 0}</span>
            <span class="tag t-gry">体系落地 ${home.setup_project_count || 0}</span>
            <button class="btn-sm" data-act="dashboard.setupProjects">体系落地项目</button>
            <a class="link-btn" data-act="dashboard.goProjects">项目组合 →</a>
          </div>
        </div>
        ${nextActions || '<div class="empty">还没有在推进的改善项目</div>'}
      </div>`;
    const byKey = Object.fromEntries(d.cards.map((c) => [c.key, c]));
    const primary = ['active_projects', 'improvement_targets', 'open_exceptions', 'avg_improvement']
      .map((key) => byKey[key]).filter(Boolean);
    const tone = { NORMAL: '', WATCH: 'is-watch', RISK: 'is-risk' };
    const kpiInfo = {
      active_projects: {
        icon: '▦', tone: 'brand',
        sub: `今年结项 ${num(byKey.closed_this_year ? byKey.closed_this_year.value : 0, 0)} 个`,
      },
      improvement_targets: {
        icon: '◎', tone: 'warn',
        sub: `占流程资产 ${byKey.process_total && byKey.process_total.value
          ? num((byKey.improvement_targets.value / byKey.process_total.value) * 100, 1) : '—'}%`,
      },
      open_exceptions: {
        icon: '!', tone: 'bad',
        sub: `超期 ${d.exception_summary.overdue} 件`,
      },
      avg_improvement: {
        icon: '✓', tone: 'ok', sub: '在办项目平均目标',
      },
    };
    const kpis = primary.map((c) => {
      const info = kpiInfo[c.key] || { icon: '·', tone: 'brand', sub: '' };
      return `
      <a class="kpi stat clickable ${tone[c.status] || ''}" href="#"
         data-act="dashboard.kpi" data-key="${esc(c.key)}">
        <div class="glow ${info.tone}"></div>
        <div class="row">
          <div class="ico ${info.tone}">${info.icon}</div>
          <div>
            <div class="lab">${metricHelp(c.key, c.label)}</div>
            <div class="num">${num(c.value, 1)}<small>${esc(c.unit || '')}</small></div>
          </div>
        </div>
        <div class="sub">${info.sub}</div>
        <span class="card-go">查看 ›</span>
      </a>`;
    }).join('');

    const stages = d.stage_health.map((s) => {
      const pct = s.project_count ? s.avg_progress : null;
      return `
      <a class="stage-row clickable" href="#" data-act="dashboard.stage" data-stage="${s.stage_no}">
        <div class="stagebar">
          <span class="nm">${metricHelp('stage_progress', '阶段' + s.stage_no)}</span>
          <span class="bar"><i class="fill-${s.health === 'RISK' ? 'bad' : s.health === 'WATCH' ? 'warn' : 'brand'}"
            style="width:${pct === null ? 0 : Math.max(pct, 4)}%"></i></span>
          <span class="pc">${pct === null ? '—' : num(pct, 0) + '%'}</span>
        </div>
        <div class="tiny stage-sub">${esc(s.stage_name)} ·
          ${s.project_count ? s.project_count + ' 个项目在办' : '暂无在办项目'}
          · 步骤完成 ${s.done_steps}/${s.total_steps}</div>
      </a>`;
    }).join('');

    const methods = d.methodology_distribution.map((m) => `
      <a class="method-item" href="#" data-act="dashboard.methodology"
        data-methodology="${esc(m.methodology)}">
        <span class="sw" style="background:${METHOD_COLOR[m.methodology] || 'var(--brand)'}"></span>
        <span>${M_ICON[m.methodology] || ''} ${esc(m.label)}</span>
        <b>${m.count} · ${num(m.share * 100, 0)}%</b>
      </a>`).join('');
    const methodTotal = d.methodology_distribution.reduce((a, m) => a + m.count, 0);
    let methodAcc = 0;
    const donutStops = d.methodology_distribution.map((m) => {
      const start = methodAcc;
      methodAcc += m.share * 100;
      return `${METHOD_COLOR[m.methodology] || 'var(--brand)'} ${start}% ${methodAcc}%`;
    }).join(', ');
    const methodDonut = methodTotal
      ? `<div class="donut" style="background:conic-gradient(${donutStops})">
           <div class="donut-hole"><b>${methodTotal}</b><span>项目</span></div></div>`
      : `<div class="donut" style="background:var(--line)">
           <div class="donut-hole"><b>0</b><span>项目</span></div></div>`;

    const board = d.project_board.map((p) => `
      <tr class="clk">
        <td><button class="project-open" type="button" data-act="dashboard.openProject"
            data-id="${p.id}"><b>${esc(p.name)}</b></button>
          <div class="tiny">${esc(p.code)} · Owner: ${esc(p.owner)}${
            p.is_overdue ? ' · <span style="color:var(--bad)">已超期</span>' : ''}</div></td>
        <td>${methodTag(p.methodology, state.meta.methodology[p.methodology])}</td>
        <td><span class="dot"></span> 阶段${p.current_stage}
          <div class="tiny">${esc(p.stage_name || '')}</div></td>
        <td>${bar(p.progress)}</td>
        <td>${statusTag(p.status, p.status_label)}</td>
      </tr>`).join('') || emptyRow(5, '当前没有在办项目');

    const priorityRows = priority.map((p) => `
      <tr class="clk">
        <td><button class="project-open" type="button" data-act="dashboard.openProcess"
            data-code="${esc(p.code)}"><b>${esc(p.name)}</b></button>
          <div class="tiny">${esc(p.code)} · Owner: ${esc(p.owner || '未指定')}</div></td>
        <td><span class="tag ${HEAT_CLASS[p.heat_level] || 'heat-low'}">
          ${HEAT_LABEL[p.heat_level] || p.heat_level} ${num(p.priority_score, 0)}</span></td>
        <td>${p.health_score === null ? '<span class="muted">未评估</span>'
          : bar(p.health_score, null, 66)}</td>
        <td>${p.project_count}</td>
      </tr>`).join('') || emptyRow(4, '暂无待改善流程');

    const alerts = d.health_alerts.slice(0, 4).map((a) => `
      <button class="alert-row ${a.level === 'HIGH' ? 'ri-high' : 'ri-medium'}"
        type="button" data-act="dashboard.go" data-view="map">
        <span class="tag ${a.level === 'HIGH' ? 't-red' : 't-yel'}">
          ${a.health_score === null ? '—' : num(a.health_score, 0)}</span>
        <div class="alert-main"><b>${esc(a.name)}</b>
          <div class="tiny">${esc(a.reason)}</div></div>
        <span class="alert-go">›</span>
      </button>`).join('') || '<div class="empty">暂无健康度预警</div>';

    const es = d.exception_summary;
    const meta = `${metricHelp('closed_this_year', '今年结项')} <b>${num(byKey.closed_this_year ? byKey.closed_this_year.value : 0, 0)}</b>
      · ${metricHelp('process_total', '流程资产')} <b>${num(byKey.process_total ? byKey.process_total.value : 0, 0)}</b>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>管理驾驶舱<span class="module-badge">全局概览</span></h2>
            <div class="desc">先看需要关注的事，再看项目推进</div></div>
          <a class="link-btn" data-act="dashboard.goProjects">项目组合 →</a>
        </div>
        <div class="grid g4 stat-row">${kpis}</div>
        <div class="meta-line">${meta}</div>
      </div>

      ${homeHtml}
      ${nextActionsHtml}

      <div class="grid g2">
        <div class="card">
          <h3>五阶段推进健康度</h3>
          <div class="desc">按各阶段在办项目的平均进度计算</div>
          ${stages}
        </div>

        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">${metricHelp('health_alert', '风险提醒')}</h3>
              <div class="desc" style="margin:2px 0 0">健康度低于 70 分或痛点 ≥ 4</div></div>
            <a class="link-btn" data-act="dashboard.go" data-view="map">流程地图 →</a>
          </div>
          ${alerts}
          <button class="alert-row ri-bad" type="button"
            data-act="dashboard.go" data-view="monitor">
            <span class="tag t-red">${es.open + es.in_progress}</span>
            <div class="alert-main"><b>${metricHelp('open_exceptions', '未闭环异常')}</b>
              <div class="tiny">超期 ${es.overdue} · 已闭环 ${es.resolved + es.closed}</div></div>
            <span class="alert-go">›</span>
          </button>
        </div>
      </div>

      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">${metricHelp('methodology_share', '方法论分布')}</h3>
            <div class="desc" style="margin:2px 0 0">BPR / BPI / 精益 / 混合 的项目配比</div></div>
        </div>
        <div class="donut-wrap">
          ${methodDonut}
          <div class="donut-legend">${methods}</div>
          <div class="donut-note">方法论分布只统计项目当前选择的方法；项目方法变更后自动更新。
            用它判断团队的方法能力结构与改善路径偏好。</div>
        </div>
      </div>

      <div class="grid g2">
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">改善优先级</h3>
              <div class="desc" style="margin:2px 0 0">该改什么 · L3 流程综合得分 Top 5</div></div>
            <a class="link-btn" data-act="dashboard.goImprovementMap">进入地图 →</a>
          </div>
          <table class="tbl">
            <thead><tr><th>流程</th><th>优先级</th><th>${metricHelp('health_score', '健康度')}</th><th>项目</th></tr></thead>
            <tbody>${priorityRows}</tbody>
          </table>
        </div>

        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">重点项目</h3>
              <div class="desc" style="margin:2px 0 0">正在做什么 · 在办项目推进情况</div></div>
            <a class="link-btn" data-act="dashboard.goProjects">查看全部 →</a>
          </div>
          <table class="tbl">
            <thead><tr><th>项目</th><th>方法</th><th>当前阶段</th>
              <th>${metricHelp('project_progress', '整体进度')}</th><th>状态</th></tr></thead>
            <tbody>${board}</tbody>
          </table>
        </div>
      </div>`;
  });


function openProjects(filter) {
  state.projects.filter = Object.assign(
    { methodology: '', status: '', stage: '', projectType: '' }, filter || {},
  );
  state.projects.keyword = '';
  const f = state.projects.filter;
  go('projects', {
    params: {
      methodology: f.methodology,
      status: f.status,
      stage: f.stage,
      type: f.projectType,
    },
    push: true,
  });
}

function openStage(stage) {
  openProjects({ stage: String(stage) });
}

function openMethodology(methodology) {
  openProjects({ methodology });
}

function openExceptions() {
  state.monitor.tab = 'exceptions';
  go('monitor');
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
