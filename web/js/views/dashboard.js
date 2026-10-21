/* 视图：dashboard */
import { esc, num, M_ICON, SEV_COLOR, SEV_LABEL, methodTag, statusTag, bar, emptyRow } from '../core/format.js';
import { viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go } from '../core/router.js';
import { GET } from '../core/api.js';
import { openProject } from './projects.js';

/* ============================================================ 1. 管理驾驶舱 */

const renderDashboard = () => renderAsync('dashboard',
  () => GET('/dashboard/overview?board_limit=8'),
  (d) => {
    const cardColor = { NORMAL: '#1a2233', WATCH: '#f59e0b', RISK: '#ef4444' };
    const cards = d.cards.map((c) => `
      <div class="kpi">
        <div class="num" style="color:${cardColor[c.status] || '#1a2233'}">${num(c.value, 1)}
          <small>${esc(c.unit || '')}</small></div>
        <div class="lab">${esc(c.label)}</div>
        <div class="trend muted">${esc({
          WATCH: '需关注', RISK: '存在风险', NORMAL: '正常',
        }[c.status] || c.status)}</div>
      </div>`).join('');

    const stages = d.stage_health.map((s) => `
      <div class="stagebar">
        <span class="nm">阶段${s.stage_no}</span>
        <span class="bar"><i style="width:${Math.max(s.avg_progress, s.project_count ? 4 : 0)}%;
          background:${s.health === 'RISK' ? '#ef4444' : s.health === 'WATCH' ? '#f59e0b' : '#2f5bea'}"></i></span>
        <span class="pc">${num(s.avg_progress, 0)}%</span>
      </div>
      <div class="tiny" style="margin:-8px 0 12px 84px">${esc(s.stage_name)}
        · ${s.project_count} 个项目在办 · 步骤完成 ${s.done_steps}/${s.total_steps}</div>`).join('');

    const methodTotal = d.methodology_distribution.reduce((a, m) => a + m.count, 0) || 1;
    const methods = d.methodology_distribution.map((m) => `
      <div class="mtr" style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="width:96px;font-size:12.5px">${M_ICON[m.methodology] || ''} ${esc(m.label)}</span>
        <span class="track" style="flex:1;height:7px;background:#eef1f7;border-radius:4px;overflow:hidden">
          <i style="display:block;height:100%;border-radius:4px;width:${num(m.share * 100, 0)}%;
            background:${{ BPR: '#d14343', BPI: '#c5830c', LEAN: '#138a45', HYBRID: '#7038d6' }[m.methodology] || '#2f5bea'}"></i>
        </span>
        <span style="width:52px;text-align:right;font-size:12.5px;font-weight:600">
          ${m.count} 个 · ${num(m.share * 100, 0)}%</span>
      </div>`).join('');

    const board = d.project_board.map((p) => {
      const reach = (p.improvement_pct !== null && p.improvement_pct !== undefined)
        ? p.improvement_pct : 0;
      return `
      <tr class="clk" onclick="openProject(${p.id})">
        <td class="tiny">${esc(p.code)}</td>
        <td><b>${esc(p.name)}</b>
          <div class="tiny">Owner: ${esc(p.owner)}${p.is_overdue ? ' · <span style="color:#ef4444">已超期</span>' : ''}</div></td>
        <td>${methodTag(p.methodology, state.meta.methodology[p.methodology])}</td>
        <td><span class="dot"></span> 阶段${p.current_stage}<div class="tiny">${esc(p.stage_name || '')}</div></td>
        <td style="font-size:12.5px">${p.metric_name
          ? esc(p.metric_name) + '<div class="tiny">' + num(p.current_value, 1) + ' → ' + num(p.target_value, 1) +
            ' ' + esc(p.metric_unit || '') + '</div>'
          : '—'}</td>
        <td>${bar(reach)}</td>
        <td>${statusTag(p.status, p.status_label)}</td>
        <td><button class="btn-sm" onclick="event.stopPropagation();openProject(${p.id})">详情</button></td>
      </tr>`;
    }).join('') || emptyRow(8, '当前没有在办项目');

    const alerts = d.health_alerts.map((a) => `
      <div class="sug ${a.level}">
        <div class="hd"><span>${esc(a.name)} <span class="tiny">${esc(a.code)}</span></span>
          <span class="tag ${a.level === 'HIGH' ? 't-red' : 't-yel'}">
            ${a.health_score === null ? '—' : num(a.health_score, 0)} 分</span></div>
        <div class="bd">${esc(a.reason)}</div>
      </div>`).join('') || '<div class="empty">暂无健康度预警</div>';

    const es = d.exception_summary;
    const summary = `
      <div class="grid g3" style="gap:10px">
        <div class="kpi" style="padding:13px 15px"><div class="num" style="font-size:22px;color:#ef4444">${es.open + es.in_progress}</div><div class="lab">未闭环</div></div>
        <div class="kpi" style="padding:13px 15px"><div class="num" style="font-size:22px;color:#f59e0b">${es.overdue}</div><div class="lab">已超期</div></div>
        <div class="kpi" style="padding:13px 15px"><div class="num" style="font-size:22px;color:#16a34a">${es.closed + es.resolved}</div><div class="lab">已闭环</div></div>
      </div>
      <table class="tbl mt">
        <thead><tr><th>严重度</th><th>未闭环件数</th></tr></thead>
        <tbody>${['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => `
          <tr><td><span class="tag ${SEV_COLOR[s]}">${SEV_LABEL[s]}</span></td>
            <td><b>${es.by_severity[s] || 0}</b></td></tr>`).join('')}
        </tbody>
      </table>`;

    viewEl().innerHTML = `
      <div class="grid g4 mb" style="margin-bottom:20px">${cards}</div>

      <div class="grid g2">
        <div class="card">
          <h2>五阶段推进健康度</h2>
          <div class="desc">按各阶段在办项目的平均进度计算</div>
          ${stages}
        </div>
        <div class="card">
          <h2>方法论分布</h2>
          <div class="desc">BPR / BPI / 精益 / 混合 的项目配比</div>
          ${methods || '<div class="empty">暂无项目</div>'}
          <div class="legend" style="margin-top:10px">
            <span><i style="background:#d14343"></i>BPR 根本性重组</span>
            <span><i style="background:#c5830c"></i>BPI 渐进优化</span>
            <span><i style="background:#138a45"></i>精益 消除浪费</span>
            <span><i style="background:#7038d6"></i>混合模式</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="between mb"><h2 style="margin:0">重点流程项目看板</h2>
          <a class="link" onclick="go('projects')">查看全部 →</a></div>
        <table class="tbl">
          <thead><tr><th>项目编号</th><th>项目名称</th><th>方法</th><th>当前阶段</th>
            <th>改善指标</th><th>目标改善幅度</th><th>状态</th><th></th></tr></thead>
          <tbody>${board}</tbody>
        </table>
      </div>

      <div class="grid g2">
        <div class="card">
          <h2>流程健康度预警</h2>
          <div class="desc">健康度低于 70 分或痛点评分 ≥4 的流程</div>
          ${alerts}
        </div>
        <div class="card">
          <h2>异常事件概览</h2>
          <div class="desc">来自运营监控模块的闭环台账</div>
          ${summary}
          <div class="mt"><a class="link" onclick="go('monitor')">前往处理 →</a></div>
        </div>
      </div>`;
  });


export { renderDashboard };
