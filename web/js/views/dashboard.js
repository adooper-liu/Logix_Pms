/* 视图：dashboard */
import { esc, num, M_ICON, methodTag, statusTag, bar, emptyRow } from '../core/format.js';
import { viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go } from '../core/router.js';
import { GET } from '../core/api.js';
import { openProject } from './projects.js';

/* ============================================================ 1. 管理驾驶舱 */

const METHOD_COLOR = {
  BPR: 'var(--bad)', BPI: 'var(--warn-strong)', LEAN: 'var(--ok-strong)', HYBRID: 'var(--purple-strong)',
};

const renderDashboard = () => renderAsync('dashboard',
  () => GET('/dashboard/overview?board_limit=5'),
  (d) => {
    const byKey = Object.fromEntries(d.cards.map((c) => [c.key, c]));
    const primary = ['active_projects', 'improvement_targets', 'open_exceptions', 'avg_improvement']
      .map((key) => byKey[key]).filter(Boolean);
    const tone = { NORMAL: '', WATCH: 'is-watch', RISK: 'is-risk' };
    const kpis = primary.map((c) => `
      <div class="kpi stat ${tone[c.status] || ''}">
        <div class="num">${num(c.value, 1)}<small>${esc(c.unit || '')}</small></div>
        <div class="lab">${esc(c.label)}</div>
      </div>`).join('');

    const stages = d.stage_health.map((s) => `
      <div class="stage-row">
        <div class="stagebar">
          <span class="nm">阶段${s.stage_no}</span>
          <span class="bar"><i class="fill-${s.health === 'RISK' ? 'bad' : s.health === 'WATCH' ? 'warn' : 'brand'}"
            style="width:${Math.max(s.avg_progress, s.project_count ? 4 : 0)}%"></i></span>
          <span class="pc">${num(s.avg_progress, 0)}%</span>
        </div>
        <div class="tiny stage-sub">${esc(s.stage_name)} · ${s.project_count} 个项目在办
          · 步骤完成 ${s.done_steps}/${s.total_steps}</div>
      </div>`).join('');

    const methods = d.methodology_distribution.map((m) => `
      <span><i style="background:${METHOD_COLOR[m.methodology] || 'var(--brand)'}"></i>
        ${M_ICON[m.methodology] || ''} ${esc(m.label)} <b>${m.count}</b></span>`).join('');
    const methodBar = d.methodology_distribution.map((m) =>
      `<i style="width:${num(m.share * 100, 2)}%;background:${
        METHOD_COLOR[m.methodology] || 'var(--brand)'}" title="${esc(m.label)}"></i>`).join('');

    const board = d.project_board.map((p) => `
      <tr class="clk" onclick="openProject(${p.id})">
        <td><b>${esc(p.name)}</b>
          <div class="tiny">${esc(p.code)} · Owner: ${esc(p.owner)}${
            p.is_overdue ? ' · <span style="color:var(--bad)">已超期</span>' : ''}</div></td>
        <td>${methodTag(p.methodology, state.meta.methodology[p.methodology])}</td>
        <td><span class="dot"></span> 阶段${p.current_stage}
          <div class="tiny">${esc(p.stage_name || '')}</div></td>
        <td style="font-size:12.5px">${p.metric_name
          ? esc(p.metric_name) + '<div class="tiny">' + num(p.current_value, 1) + ' → ' +
            num(p.target_value, 1) + ' ' + esc(p.metric_unit || '') + '</div>'
          : '—'}</td>
        <td>${bar(p.progress)}</td>
        <td>${statusTag(p.status, p.status_label)}</td>
      </tr>`).join('') || emptyRow(6, '当前没有在办项目');

    const alerts = d.health_alerts.slice(0, 4).map((a) => `
      <div class="alert-row" onclick="go('map')">
        <span class="tag ${a.level === 'HIGH' ? 't-red' : 't-yel'}">
          ${a.health_score === null ? '—' : num(a.health_score, 0)}</span>
        <div class="alert-main"><b>${esc(a.name)}</b>
          <div class="tiny">${esc(a.reason)}</div></div>
        <span class="alert-go">›</span>
      </div>`).join('') || '<div class="empty">暂无健康度预警</div>';

    const es = d.exception_summary;
    const meta = `今年结项 <b>${num(byKey.closed_this_year ? byKey.closed_this_year.value : 0, 0)}</b>
      · 流程资产 <b>${num(byKey.process_total ? byKey.process_total.value : 0, 0)}</b>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>管理驾驶舱</h2>
            <div class="desc">先看需要关注的事，再看项目推进</div></div>
          <a class="link" onclick="go('projects')">查看项目组合 →</a>
        </div>
        <div class="grid g4 stat-row">${kpis}</div>
        <div class="meta-line">${meta}</div>
      </div>

      <div class="grid g2">
        <div class="card">
          <h3>五阶段推进健康度</h3>
          <div class="desc">按各阶段在办项目的平均进度计算</div>
          ${stages}
        </div>

        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">风险提醒</h3>
              <div class="desc" style="margin:2px 0 0">健康度低于 70 分或痛点 ≥ 4</div></div>
            <a class="link" onclick="go('map')">流程地图 →</a>
          </div>
          ${alerts}
          <div class="alert-row" onclick="go('monitor')">
            <span class="tag t-red">${es.open + es.in_progress}</span>
            <div class="alert-main"><b>未闭环异常</b>
              <div class="tiny">超期 ${es.overdue} · 已闭环 ${es.resolved + es.closed}</div></div>
            <span class="alert-go">›</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">方法论分布</h3>
            <div class="desc" style="margin:2px 0 0">BPR / BPI / 精益 / 混合 的项目配比</div></div>
        </div>
        <div class="method-bar">${methodBar || '<i style="width:100%;background:var(--line)"></i>'}</div>
        <div class="legend">${methods}</div>
      </div>

      <div class="card">
        <div class="between mb">
          <h3 style="margin:0">重点项目</h3>
          <a class="link" onclick="go('projects')">查看全部 →</a>
        </div>
        <table class="tbl">
          <thead><tr><th>项目</th><th>方法</th><th>当前阶段</th>
            <th>改善指标</th><th>整体进度</th><th>状态</th></tr></thead>
          <tbody>${board}</tbody>
        </table>
      </div>`;
  });


export { renderDashboard };
