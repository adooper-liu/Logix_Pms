/* 视图：monitor */
import { esc, num, dtShort, _p2, SEV_COLOR, SEV_LABEL, EXC_COLOR, EXC_LABEL, KPI_DIM_ICON, bar, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, promptDialog, modalAlive, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go } from '../core/router.js';
import { AUTH, canWrite, canManage, role } from '../core/auth.js';
import { cssVar } from '../core/theme.js';
import { metricHelp } from '../core/metrics.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { actions as appActions } from '../core/actions.js';

/* ============================================================ 7. 运营监控与KPI */

on('monitor.tab', ({ tab }) => setMonitorTab(tab));
on('monitor.status', (_data, el) => setMonitorStatus(el.value));
on('monitor.openException', ({ id }) => openException(Number(id)));
on('monitor.newException', () => newExceptionModal());
on('monitor.newKpi', () => newKpiModal());
on('monitor.editKpi', ({ id }) => editKpiModal(Number(id)));
on('monitor.kind', (_data, el) => setMonitorKind(el.value));
on('monitor.period', (_data, el) => setMonitorPeriod(el.value));
on('monitor.newStandard', () => newWorkloadStandardModal());
on('monitor.submitStandard', () => submitWorkloadStandard());
on('monitor.verifyStandard', ({ id }) => verifyWorkloadStandard(Number(id)));
on('monitor.observations', ({ id }) => openObservationsModal(Number(id)));
on('monitor.addObservation', ({ standard }) => addObservation(Number(standard)));
on('monitor.deleteObservation', ({ id, standard }) =>
  deleteObservation(Number(standard), Number(id)));
on('monitor.submitReview', ({ id }) => submitStandardReview(Number(id)));
on('monitor.approveStandard', ({ id }) => reviewWorkloadStandard(Number(id), true));
on('monitor.rejectStandard', ({ id }) => reviewWorkloadStandard(Number(id), false));
on('monitor.newCapacity', () => newCapacityModal());
on('monitor.submitCapacity', () => submitCapacity());
on('monitor.close', () => closeModal());
on('monitor.saveException', ({ id }) => saveException(Number(id)));
on('monitor.submitException', () => submitException());
on('monitor.submitKpi', ({ kpi }) => submitKpi(kpi ? Number(kpi) : null));
on('monitor.improveKpi', ({ id }) => createImprovement(Number(id)));
on('monitor.addRecord', ({ kpi, name }) => addKpiRecordModal(Number(kpi), name));
on('monitor.submitRecord', ({ kpi }) => submitKpiRecord(Number(kpi)));
on('monitor.goExecution', () => go('execution'));

const renderMonitor = () => {
  const qs = state.monitor.status ? '?status=' + state.monitor.status : '';
  return renderAsync('monitor',
    () => Promise.all([
      GET('/monitor/kpi-radar'),
      GET('/monitor/exceptions' + qs),
      GET('/monitor/exceptions/summary'),
      GET('/monitor/meta'),
      GET('/workload/summary' + (state.monitor.period ? '?period=' + state.monitor.period + '-01' : '')),
      GET('/workload/meta'),
      GET('/monitor/improvement-candidates'),
    ]).then(([radar, exceptions, summary, meta, workload, workloadMeta, candidates]) => ({
      radar, exceptions, summary, meta, workload, workloadMeta, candidates,
    })),
    (d) => {
      state.monitorRadar = d.radar;
      state.monitorMeta = d.meta;
      state.workloadMeta = d.workloadMeta;
      const tab = state.monitor.tab || 'overview';
      const s = d.summary;
      const dimColor = {
        EFFICIENCY: 'var(--brand)', QUALITY: 'var(--ok)',
        COST: 'var(--warn)', FLEXIBILITY: 'var(--purple)',
      };
      const dimCards = d.radar.dimensions.map((dim) => `
        <div class="kpi stat">
          <div class="num" style="color:${dimColor[dim.dimension]}">${num(dim.achievement_rate, 0)}<small>%</small></div>
          <div class="lab">${KPI_DIM_ICON[dim.dimension]} ${metricHelp('dimension_achievement', dim.label)}</div>
          <div class="trend ${dim.status === 'GOOD' ? 'up' : dim.status === 'WATCH' ? '' : 'down'}">
            ${dim.kpi_count} 个指标 · ${dim.status === 'GOOD' ? '达标' : dim.status === 'WATCH' ? '需关注' : '未达标'}</div>
          <div class="pipe"><i class="fill-${dim.status === 'GOOD' ? 'ok' : dim.status === 'WATCH' ? 'warn' : 'bad'}"
            style="width:${Math.min(100, dim.achievement_rate)}%"></i></div>
        </div>`).join('');

      const kpiInfo = (series) => {
        const latest = series.points.length ? series.points[series.points.length - 1].value : null;
        const prev = series.points.length > 1 ? series.points[series.points.length - 2].value : null;
        const delta = (latest !== null && prev !== null) ? latest - prev : null;
        let reach = null;
        if (latest !== null && series.target_value) {
          reach = series.direction === 'LOWER_BETTER'
            ? (latest > 0 ? (series.target_value / latest) * 100 : (latest === 0 ? 100 : null))
            : (latest / series.target_value) * 100;
        }
        return { latest, delta, reach };
      };

      const kindLabels = (d.meta && d.meta.kind_labels) || {};
      const kindFilter = state.monitor.kind || '';
      const visibleSeries = kindFilter
        ? d.radar.series.filter((series) => series.kind === kindFilter)
        : d.radar.series;
      const statusTone = { RED: 't-red', YELLOW: 't-yel', GREEN: 't-grn' };

      const kpiRows = visibleSeries.map((series) => {
        const { latest, delta, reach } = kpiInfo(series);
        return `
          <tr>
            <td><b>${esc(series.name)}</b><div class="tiny">${esc(series.code)} · ${esc(series.unit || '')}
              <span class="tag t-blu">${esc(series.kind_label)}</span></div></td>
            <td>${KPI_DIM_ICON[series.dimension] || ''}</td>
            <td><b>${num(latest, 2)}</b></td>
            <td class="muted">${num(series.target_value, 2)}</td>
            <td>${reach === null ? '—' : bar(Math.min(reach, 130), null, 70)}</td>
            <td>${series.status
              ? `<span class="tag ${statusTone[series.status] || 't-gry'}">${
                esc(series.status_label || series.status)}</span>`
              : '<span class="muted">—</span>'}</td>
            <td>${delta === null ? '<span class="muted">—</span>'
              : '<span class="' + (series.direction === 'LOWER_BETTER'
                  ? (delta < 0 ? 'up' : delta > 0 ? 'down' : '')
                  : (delta > 0 ? 'up' : delta < 0 ? 'down' : '')) + '">'
                + (delta > 0 ? '↑ ' : delta < 0 ? '↓ ' : '→ ') + num(Math.abs(delta), 2) + '</span>'}</td>
            <td><canvas class="spark" width="110" height="26" data-spark="${series.kpi_id}"></canvas></td>
            <td>${canManage()
              ? `<div class="gap">
                  ${series.status === 'RED' || series.status === 'YELLOW'
                    ? `<button class="btn-sm btn-p" data-act="monitor.improveKpi"
                        data-id="${series.kpi_id}">转改善</button>` : ''}
                  <button class="btn-sm" data-act="monitor.addRecord" data-kpi="${series.kpi_id}"
                    data-name="${esc(series.name)}">录入</button>
                  <button class="btn-sm" data-act="monitor.editKpi"
                    data-id="${series.kpi_id}">编辑</button>
                </div>`
              : ''}</td>
          </tr>`;
      }).join('') || emptyRow(9, kindFilter ? '该类型下暂无 KPI' : '暂无 KPI');

      const quick = d.radar.series.map((series) => ({ series, ...kpiInfo(series) }))
        .filter((row) => row.reach !== null)
        .sort((a, b) => a.reach - b.reach)
        .slice(0, 5);
      const quickRows = quick.map(({ series, latest, reach }) => `
        <tr class="clk">
          <td><button class="project-open" type="button" data-act="monitor.tab"
              data-tab="kpi"><b>${esc(series.name)}</b></button>
            <div class="tiny">${esc(series.code)}</div></td>
          <td>${num(latest, 2)} ${esc(series.unit || '')}</td>
          <td class="muted">${num(series.target_value, 2)}</td>
          <td>${bar(Math.min(reach, 130), null, 80)}</td>
        </tr>`).join('') || emptyRow(4, '暂无达成率数据');

      const excRows = d.exceptions.map((e) => {
        const canEdit = canManage()
          || (role() === 'OWNER' && AUTH.user && e.owner_user_id === AUTH.user.id);
        return `
        <tr>
          <td class="tiny">${dtShort(e.detected_at)}</td>
          <td>${esc(e.title)}<div class="tiny">${esc(e.code)}${
            e.is_overdue ? ' · <span style="color:var(--bad)">已超期</span>' : ''}</div></td>
          <td><span class="tag ${SEV_COLOR[e.severity]}">${SEV_LABEL[e.severity]}</span></td>
          <td>${e.owner ? esc(e.owner) : '<span class="muted">未指派</span>'}</td>
          <td><span class="tag ${EXC_COLOR[e.status]}">${EXC_LABEL[e.status]}</span></td>
          <td><button class="btn-sm" data-act="monitor.openException"
            data-id="${e.id}">${canEdit ? '处理' : '查看'}</button></td>
        </tr>`;
      }).join('') || emptyRow(6, '没有符合条件的异常事件');

      const recent = d.exceptions
        .filter((e) => e.status === 'OPEN' || e.status === 'IN_PROGRESS')
        .slice(0, 3);
      const recentRows = recent.map((e) => `
        <button class="alert-row" type="button" data-act="monitor.openException" data-id="${e.id}">
          <span class="tag ${SEV_COLOR[e.severity]}">${SEV_LABEL[e.severity]}</span>
          <div class="alert-main"><b>${esc(e.title)}</b>
            <div class="tiny">${esc(e.owner || '未指派')}${e.is_overdue ? ' · 已超期' : ''}</div></div>
          <span class="alert-go">›</span>
        </button>`).join('') || '<div class="empty">没有未闭环异常</div>';

      const periods = (d.radar.series.find((series) => series.points.length) || { points: [] })
        .points.map((p) => p.period);
      // 与雷达图同口径：先按维度求平均，再对维度求平均，避免指标多的维度权重过大
      const trend = periods.map((_, idx) => {
        const byDimension = {};
        d.radar.series.forEach((series) => {
          const point = series.points[idx];
          if (!point || !series.target_value) return;
          const reach = series.direction === 'LOWER_BETTER'
            ? (point.value > 0 ? (series.target_value / point.value) * 100
              : (point.value === 0 ? 100 : null))
            : (point.value / series.target_value) * 100;
          if (reach === null) return;
          (byDimension[series.dimension] = byDimension[series.dimension] || []).push(reach);
        });
        const averages = Object.values(byDimension)
          .map((values) => values.reduce((a, b) => a + b, 0) / values.length);
        return averages.length ? averages.reduce((a, b) => a + b, 0) / averages.length : null;
      });

      state.monitorTrend = { trend, periods };

      const wl = d.workload;
      state.monitorWorkload = wl;
      const hours = (minutes) => num((minutes || 0) / 60, 1);
      const periodValue = state.monitor.period
        || (wl.period ? wl.period.slice(0, 7) : '');
      const utilization = wl.totals.utilization;
      const workloadCards = `
        <div class="grid g4 stat-row">
          <div class="kpi stat"><div class="num">${hours(wl.totals.demand_minutes)}<small>h</small></div>
            <div class="lab">标准需求</div><div class="trend">仅已验证标准</div></div>
          <div class="kpi stat"><div class="num">${hours(wl.totals.available_minutes)}<small>h</small></div>
            <div class="lab">可用产能</div><div class="trend">人数 × 工时 × 出勤 × 设备</div></div>
          <div class="kpi stat"><div class="num">${hours(wl.totals.actual_minutes)}<small>h</small></div>
            <div class="lab">实际工时</div><div class="trend">来自任务工时记录</div></div>
          <div class="kpi stat"><div class="num">${utilization === null ? '—' : num(utilization * 100, 1)}<small>%</small></div>
            <div class="lab">理论负荷率</div><div class="trend">标准需求 ÷ 可用产能</div></div>
        </div>`;
      const standardRows = wl.standards.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.activity_code || '')} ${
            esc(row.activity_name || '')}</div></td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${num(row.standard_minutes, 2)}</td>
          <td>${num(row.monthly_frequency, 1)}</td>
          <td>${hours(row.demand_minutes)}</td>
          <td><span class="tag ${row.status === 'VERIFIED' ? 't-grn'
            : row.status === 'IN_REVIEW' ? 't-blu'
            : row.status === 'RETIRED' ? 't-gry' : 't-yel'}">${esc(row.status_label)}</span>
            <div class="tiny">样本 ${row.observation_count} 条 · ${esc(row.source_label)}</div></td>
          <td class="gap">
            <button class="btn-sm" data-act="monitor.observations"
              data-id="${row.standard_id}">样本</button>
            ${canManage() && row.status === 'DRAFT' && row.sample_size >= 5
              ? `<button class="btn-sm" data-act="monitor.submitReview"
                  data-id="${row.standard_id}">提交评审</button>` : ''}
            ${canManage() && row.status === 'DRAFT'
              ? `<button class="btn-sm" data-act="monitor.verifyStandard"
                  data-id="${row.standard_id}">直接验证</button>` : ''}
            ${canManage() && row.status === 'IN_REVIEW'
              ? `<button class="btn-sm" data-act="monitor.observations"
                  data-id="${row.standard_id}">审核</button>` : ''}
          </td>
        </tr>`).join('') || emptyRow(7, '还没有标准工时卡');
      const capacityRows = wl.capacity.map((row) => `
        <tr>
          <td>${esc(row.org_unit_name || '—')}</td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${num(row.headcount, 1)}</td>
          <td>${hours(row.available_minutes)}</td>
          <td>${hours(row.demand_minutes)}</td>
          <td>${hours(row.gap_minutes)}</td>
          <td>${row.utilization === null ? '—' : num(row.utilization * 100, 1) + '%'}</td>
        </tr>`).join('') || emptyRow(7, '还没有产能记录');
      const actualRows = wl.actual.map((row) => `
        <tr>
          <td>${esc(row.activity_code || '—')} ${esc(row.activity_name || '')}</td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${row.task_count}</td>
          <td>${hours(row.effort_minutes)}</td>
        </tr>`).join('') || emptyRow(4, '本期还没有实际工时记录');

      const boundaryNote = (state.workloadMeta && state.workloadMeta.boundary_note) || '';
      const workloadPane = `
        ${boundaryNote ? `<div class="note mb">${esc(boundaryNote)}</div>` : ''}
        ${workloadCards}
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">标准工时卡（${wl.standards.length} 条）</h3>
              <div class="desc" style="margin:2px 0 0">标准工时 = 观测 × 评定系数 × (1 + 宽放率)；
                只有「已验证」进入产能口径</div></div>
            <div class="gap">
              <input class="sel sel-sm" type="month" data-act="monitor.period" value="${periodValue}">
              ${canManage()
                ? '<button class="btn btn-g" data-act="monitor.newStandard">+ 标准工时</button>' : ''}
            </div>
          </div>
          <table class="tbl">
            <thead><tr><th>活动 / 标准</th><th>岗位</th><th>标准工时（分）</th>
              <th>月频次</th><th>需求（h/月）</th><th>状态 / 来源</th><th></th></tr></thead>
            <tbody>${standardRows}</tbody>
          </table>
        </div>
        <div class="grid g2">
          <div class="card">
            <div class="between mb">
              <div><h3 style="margin:0">产能与负荷</h3>
                <div class="desc" style="margin:2px 0 0">可用工时扣除出勤与设备可用率</div></div>
              ${canManage()
                ? '<button class="btn-sm" data-act="monitor.newCapacity">+ 产能</button>' : ''}
            </div>
            <table class="tbl">
              <thead><tr><th>组织</th><th>岗位</th><th>人数</th><th>可用（h）</th>
                <th>需求（h）</th><th>缺口（h）</th><th>负荷率</th></tr></thead>
              <tbody>${capacityRows}</tbody>
            </table>
          </div>
          <div class="card">
            <h3>实际工时（按活动）</h3>
            <div class="desc">来自任务工时记录；未关联活动的工时单独列示</div>
            <table class="tbl">
              <thead><tr><th>活动</th><th>岗位</th><th>任务数</th><th>实际（h）</th></tr></thead>
              <tbody>${actualRows}</tbody>
            </table>
          </div>
        </div>`;

      const tabs = `
        <div class="seg">
          <button class="${tab === 'overview' ? 'on' : ''}" data-act="monitor.tab" data-tab="overview">概览</button>
          <button class="${tab === 'kpi' ? 'on' : ''}" data-act="monitor.tab" data-tab="kpi">KPI 明细</button>
          <button class="${tab === 'exceptions' ? 'on' : ''}" data-act="monitor.tab" data-tab="exceptions">异常台账</button>
          <button class="${tab === 'workload' ? 'on' : ''}" data-act="monitor.tab" data-tab="workload">工作量</button>
        </div>`;

      const overview = `
        <div class="grid g4 stat-row">${dimCards}</div>
        <div class="grid g2">
          <div class="card">
            <h3>${metricHelp('dimension_achievement', '流程健康度雷达')}</h3>
            <div class="desc">实线为当前达成率，虚线为 100% 目标线</div>
            <canvas id="radar" width="380" height="300"></canvas>
            <div class="legend chart-legend">
              <span><i style="background:var(--ok)"></i>当前达成率</span>
              <span><i style="background:var(--brand)"></i>100% 目标线</span>
            </div>
          </div>
          <div class="card">
            <div class="between mb">
              <div><h3 style="margin:0">异常概览</h3>
                <div class="desc" style="margin:2px 0 0">未闭环 ${s.open + s.in_progress} 件 · 超期 ${s.overdue} 件</div></div>
              <a class="link-btn" data-act="monitor.tab" data-tab="exceptions">全部台账 →</a>
            </div>
            <div class="kpi-strip">
              <div><b>${s.open + s.in_progress}</b><span>${metricHelp('open_exceptions', '未闭环')}</span></div>
              <div><b class="risk">${s.overdue}</b><span>${metricHelp('exception_overdue', '超期')}</span></div>
              <div><b>${s.resolved + s.closed}</b><span>${metricHelp('closed_exceptions', '已闭环')}</span></div>
            </div>
            ${recentRows}
          </div>
        </div>
        <div class="grid g2" style="align-items:start">
          <div class="card">
            <h3>${metricHelp('overall_trend', '整体达成率趋势')}</h3>
            <div class="desc">按月度汇总各 KPI 达成率的平均值，100% = 达标</div>
            <canvas id="overallTrend" class="trend-canvas" width="440" height="180"></canvas>
          </div>
          <div class="card">
            <div class="between mb">
              <div><h3 style="margin:0">${metricHelp('achievement_rate', '最弱 5 项')}</h3>
                <div class="desc" style="margin:2px 0 0">按达成率从低到高，优先处理</div></div>
              <a class="link-btn" data-act="monitor.tab" data-tab="kpi">全部 ${d.radar.series.length} 项 →</a>
            </div>
            <table class="tbl">
              <thead><tr><th>指标</th><th>${metricHelp('latest_value', '当前值')}</th><th>${metricHelp('target_value', '目标')}</th><th>${metricHelp('achievement_rate', '达成率')}</th></tr></thead>
              <tbody>${quickRows}</tbody>
            </table>
          </div>
        </div>`;

      const kindOptions = Object.entries(kindLabels).map(([value, label]) =>
        `<option value="${value}"${state.monitor.kind === value ? ' selected' : ''}>${
          esc(label)}</option>`).join('');
      const kindStats = (d.radar.by_kind || []).map((k) =>
        `<span class="tag ${k.red ? 't-red' : k.yellow ? 't-yel' : 't-gry'}">${
          esc(k.label)} ${k.kpi_count} · 红 ${k.red} / 黄 ${k.yellow} / 绿 ${k.green} / 灰 ${k.gray}</span>`).join('');
      const candidateRows = (d.candidates || []).map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td><span class="tag ${row.status === 'RED' ? 't-red' : 't-yel'}">${
            esc(row.status_label)}</span></td>
          <td>${num(row.latest_value, 2)} → ${num(row.target_value, 2)} ${esc(row.unit || '')}</td>
          <td class="tiny">${esc(row.process_code || '—')} ${esc(row.process_name || '')}</td>
          <td>${esc(row.owner || '—')}</td>
          <td>${canManage()
            ? `<button class="btn-sm btn-p" data-act="monitor.improveKpi"
                data-id="${row.kpi_id}">转改善</button>` : ''}</td>
        </tr>`).join('');
      const candidateCard = `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">改善候选（${(d.candidates || []).length}）</h3>
              <div class="desc" style="margin:2px 0 0">自动扫描红/黄 KPI，
                已排除有进行中改善项目的指标</div></div>
          </div>
          ${candidateRows ? `
            <table class="tbl">
              <thead><tr><th>指标</th><th>状态</th><th>当前 → 目标</th>
                <th>流程</th><th>责任人</th><th></th></tr></thead>
              <tbody>${candidateRows}</tbody>
            </table>` : '<div class="tiny muted">当前没有需要立项的红/黄 KPI。</div>'}
        </div>`;

      const kpiPane = `
        ${candidateCard}
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">KPI 明细（${visibleSeries.length} 项）</h3>
              <div class="desc" style="margin:2px 0 0">按定义卡判定红/黄/绿；越小越好的指标，达成率取目标与实际的比值</div></div>
            <select class="sel sel-sm" data-act="monitor.kind">
              <option value="">全部类型</option>${kindOptions}
            </select>
          </div>
          <div class="gap mb">${kindStats}</div>
          <table class="tbl">
            <thead><tr><th>指标</th><th>维度</th><th>${metricHelp('latest_value', '当前值')}</th><th>${metricHelp('target_value', '目标')}</th>
              <th>${metricHelp('achievement_rate', '达成率')}</th><th>红/黄/绿</th><th>${metricHelp('kpi_trend', '环比')}</th><th>${metricHelp('kpi_series', '6 个月走势')}</th>${canManage() ? '<th></th>' : ''}</tr></thead>
            <tbody>${kpiRows}</tbody>
          </table>
        </div>`;

      const excPane = `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">异常事件台账</h3>
              <div class="desc" style="margin:2px 0 0">闭环管理：登记 → 处理 → 解决 → 关闭</div></div>
            <select class="sel" data-act="monitor.status">
              <option value="">全部状态</option>
              ${['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'].map((v) =>
                '<option value="' + v + '"' + (state.monitor.status === v ? ' selected' : '') + '>' +
                EXC_LABEL[v] + '</option>').join('')}
            </select>
          </div>
          <table class="tbl">
            <thead><tr><th>发现时间</th><th>异常</th><th>级别</th><th>责任人</th><th>状态</th><th></th></tr></thead>
            <tbody>${excRows}</tbody>
          </table>
        </div>`;

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>运营监控<span class="module-badge">运营结果 · KPI 与异常</span></h2>
              <div class="desc">${metricHelp('overall_achievement', '综合达成率')} <b>${num(d.radar.overall_achievement, 1)}%</b>
                · 未闭环 ${s.open + s.in_progress} 件 · 超期 ${s.overdue} 件</div></div>
            <div class="gap">
              <a class="link-btn" data-act="monitor.goExecution">任务队列 →</a>
              ${canWrite() ? '<button class="btn btn-p" data-act="monitor.newException">+ 登记异常</button>' : ''}
              ${canManage() ? '<button class="btn btn-g" data-act="monitor.newKpi">+ 新建 KPI</button>' : ''}
            </div>
          </div>
          <div class="mt">${tabs}</div>
        </div>
        ${tab === 'kpi' ? kpiPane
          : tab === 'exceptions' ? excPane
            : tab === 'workload' ? workloadPane : overview}`;

      if (tab === 'overview') {
        drawRadar(d.radar);
        drawOverallTrend(trend, periods);
      }
      d.radar.series.forEach((series) =>
        drawSpark(series.kpi_id, series.points.map((p) => p.value), series.direction));
    });
};

function setMonitorTab(tab) {
  state.monitor.tab = tab;
  RENDERERS.monitor();
}

function setMonitorStatus(status) {
  state.monitor.status = status;
  RENDERERS.monitor();
}

function setMonitorKind(kind) {
  state.monitor.kind = kind;
  RENDERERS.monitor();
}

function setMonitorPeriod(period) {
  state.monitor.period = period;
  state.monitor.tab = 'workload';
  RENDERERS.monitor();
}

function drawRadar(radar) {
  const c = document.getElementById('radar');
  if (!c) return;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  const cx = W / 2, cy = H / 2 + 6, r = Math.min(W, H) / 2 - 52;
  const dims = radar.dimensions;
  const n = dims.length;
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  ctx.clearRect(0, 0, W, H);

  // 网格
  const gridColor = cssVar('--chart-grid');
  const subColor = cssVar('--sub');
  const brandColor = cssVar('--brand');
  const okColor = cssVar('--ok');
  for (let g = 1; g <= 4; g++) {
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const a = angle(i), rr = (r * g) / 4;
      const x = cx + rr * Math.cos(a), y = cy + rr * Math.sin(a);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = gridColor;
    ctx.stroke();
  }
  // 轴线 + 标签
  dims.forEach((d, i) => {
    const a = angle(i);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
    ctx.strokeStyle = gridColor;
    ctx.stroke();
    ctx.fillStyle = subColor;
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(d.label + ' ' + num(d.achievement_rate, 0) + '%',
      cx + (r + 26) * Math.cos(a), cy + (r + 26) * Math.sin(a) + 4);
  });

  // 目标线（100%）
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const a = angle(i);
    const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = brandColor;
  ctx.globalAlpha = 0.07;
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.strokeStyle = brandColor;
  ctx.setLineDash([4, 3]);
  ctx.stroke();
  ctx.setLineDash([]);

  // 当前值
  ctx.beginPath();
  dims.forEach((d, i) => {
    const a = angle(i);
    const rr = (r * Math.max(0, Math.min(130, d.achievement_rate))) / 100;
    const x = cx + rr * Math.cos(a), y = cy + rr * Math.sin(a);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = okColor;
  ctx.globalAlpha = 0.18;
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.strokeStyle = okColor;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.lineWidth = 1;


}

function drawOverallTrend(trend, periods) {
  const c = document.getElementById('overallTrend');
  if (!c) return;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  const pad = { l: 36, r: 14, t: 14, b: 24 };
  const w = W - pad.l - pad.r, h = H - pad.t - pad.b;
  const grid = cssVar('--chart-grid');
  const sub = cssVar('--sub');
  const brand = cssVar('--brand');
  const ok = cssVar('--ok');
  const maxY = 130;
  ctx.clearRect(0, 0, W, H);

  [0, 50, 100, 130].forEach((v) => {
    const y = pad.t + h - (v / maxY) * h;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(W - pad.r, y);
    ctx.strokeStyle = grid;
    ctx.stroke();
    if (v % 50 === 0) {
      ctx.fillStyle = sub;
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(v + '%', pad.l - 6, y + 3);
    }
  });

  // 100% 目标线
  const targetY = pad.t + h - (100 / maxY) * h;
  ctx.beginPath();
  ctx.moveTo(pad.l, targetY);
  ctx.lineTo(W - pad.r, targetY);
  ctx.strokeStyle = ok;
  ctx.setLineDash([4, 3]);
  ctx.stroke();
  ctx.setLineDash([]);

  const points = trend.map((v, i) => {
    if (v === null || v === undefined) return null;
    return [
      pad.l + (trend.length > 1 ? (i / (trend.length - 1)) * w : w / 2),
      pad.t + h - (Math.min(v, maxY) / maxY) * h,
    ];
  });

  // 面积
  ctx.beginPath();
  let started = false;
  points.forEach((pt) => {
    if (!pt) return;
    if (!started) { ctx.moveTo(pt[0], pt[1]); started = true; } else ctx.lineTo(pt[0], pt[1]);
  });
  if (started) {
    const last = points.filter(Boolean).slice(-1)[0];
    const first = points.filter(Boolean)[0];
    ctx.lineTo(last[0], pad.t + h);
    ctx.lineTo(first[0], pad.t + h);
    ctx.closePath();
    ctx.fillStyle = brand;
    ctx.globalAlpha = 0.08;
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // 折线
  ctx.beginPath();
  started = false;
  points.forEach((pt) => {
    if (!pt) return;
    if (!started) { ctx.moveTo(pt[0], pt[1]); started = true; } else ctx.lineTo(pt[0], pt[1]);
  });
  ctx.strokeStyle = brand;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.lineWidth = 1;

  // 数据点 + 月份
  points.forEach((pt, i) => {
    if (!pt) return;
    ctx.beginPath();
    ctx.arc(pt[0], pt[1], 2.6, 0, Math.PI * 2);
    ctx.fillStyle = brand;
    ctx.fill();
    const label = periods[i] ? String(periods[i]).slice(5, 7) + '月' : '';
    ctx.fillStyle = sub;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(label, pt[0], H - 7);
  });
}

function drawSpark(kpiId, values, direction) {
  const c = document.querySelector('canvas[data-spark="' + kpiId + '"]');
  if (!c || values.length < 2) return;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  const min = Math.min(...values), max = Math.max(...values);
  const span = (max - min) || 1;
  const improved = direction === 'LOWER_BETTER'
    ? values[values.length - 1] <= values[0]
    : values[values.length - 1] >= values[0];
  ctx.clearRect(0, 0, W, H);
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = (i / (values.length - 1)) * (W - 6) + 3;
    const y = H - 5 - ((v - min) / span) * (H - 10);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = improved ? cssVar('--ok') : cssVar('--bad');
  ctx.lineWidth = 1.6;
  ctx.stroke();
  const lx = W - 3;
  const ly = H - 5 - ((values[values.length - 1] - min) / span) * (H - 10);
  ctx.beginPath();
  ctx.arc(lx, ly, 2.4, 0, Math.PI * 2);
  ctx.fillStyle = improved ? cssVar('--ok') : cssVar('--bad');
  ctx.fill();
}

async function openException(id) {
  const gen = openModal('加载中…', skeleton(4));
  try {
    const e = await GET('/monitor/exceptions/' + id);
    if (!modalAlive(gen)) return;
    state.currentException = e;
    const canEdit = canManage()
      || (role() === 'OWNER' && AUTH.user && e.owner_user_id === AUTH.user.id);
    const manager = canManage();
    const statusOpts = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'].map((v) =>
      '<option value="' + v + '"' + (e.status === v ? ' selected' : '') + '>' + EXC_LABEL[v] + '</option>').join('');
    openModal(e.title, `
      <div class="row2">
        <div class="field"><label>事件编号</label><input value="${esc(e.code)}" readonly></div>
        <div class="field"><label>严重度</label><input value="${SEV_LABEL[e.severity]}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>发现时间</label><input value="${dtShort(e.detected_at)}" readonly></div>
        <div class="field"><label>要求闭环时间</label>
          <input value="${dtShort(e.due_at)}${e.is_overdue ? '（已超期）' : ''}" readonly></div>
      </div>
      <div class="field"><label>异常描述</label><textarea readonly>${esc(e.description || '—')}</textarea></div>
      <div class="row2">
        <div class="field"><label>责任人</label>
          <input id="exOwner" value="${esc(e.owner || '')}" placeholder="指派处理人"${manager ? '' : ' readonly'}></div>
        <div class="field"><label>状态</label>
          <select id="exStatus"${canEdit ? '' : ' disabled'}>${statusOpts}</select></div>
      </div>
      <div class="field"><label>根因分析</label>
        <textarea id="exCause" placeholder="用 5 Why 追到可干预的根因"${canEdit ? '' : ' readonly'}>${esc(e.root_cause || '')}</textarea></div>
      <div class="field"><label>采取的措施</label>
        <textarea id="exAction" placeholder="做了什么、效果如何"${canEdit ? '' : ' readonly'}>${esc(e.action_taken || '')}</textarea></div>
      ${e.resolved_at ? '<div class="note">解决时间：' + esc(dtShort(e.resolved_at)) +
        (e.closed_at ? ' · 关闭时间：' + esc(dtShort(e.closed_at)) : '') + '</div>' : ''}
      ${canEdit ? '' : '<div class="note">只读：仅流程管理科、系统管理员或该异常的责任人可以处理。</div>'}`,
      `<button class="btn btn-g" data-act="monitor.close">${canEdit ? '取消' : '关闭'}</button>
       ${canEdit ? `<button class="btn btn-p" data-act="monitor.saveException" data-id="${e.id}">保存</button>` : ''}`);
  } catch (err) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(err.message) + '</div></div>');
  }
}

async function saveException(id) {
  const g = (x) => document.getElementById(x).value;
  try {
    await PATCH('/monitor/exceptions/' + id, {
      owner: g('exOwner') || null,
      status: g('exStatus'),
      root_cause: g('exCause') || null,
      action_taken: g('exAction') || null,
    });
    closeModal();
    toast('异常事件已更新');
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 异常 / KPI 的写入口 */

async function newExceptionModal() {
  openModal('登记异常事件', `
    <div class="field"><label>异常标题 *</label>
      <input id="neTitle" placeholder="如：采购需求审批连续超时"></div>
    <div class="field"><label>异常描述</label>
      <textarea id="neDesc" placeholder="现象、影响范围、首次发现时间"></textarea></div>
    <div class="row3">
      <div class="field"><label>严重度</label>
        <select id="neSeverity">
          <option value="LOW">低</option><option value="MEDIUM" selected>中</option>
          <option value="HIGH">高</option><option value="CRITICAL">紧急</option>
        </select></div>
      <div class="field"><label>责任人</label><input id="neOwner" value="${
        role() === 'OWNER' && AUTH.user ? esc(AUTH.user.display_name) : ''
      }" placeholder="处理人"${role() === 'OWNER' ? ' readonly' : ''}></div>
      <div class="field"><label>要求闭环时间</label><input id="neDue" type="datetime-local"></div>
    </div>
    <div class="field"><label>关联流程</label>
      <select id="neProcess"><option value="">不关联</option></select></div>
    <div class="note">要求闭环时间会按浏览器本地时区提交，后端统一转成 UTC 存储。</div>`,
    `<button class="btn btn-g" data-act="monitor.close">取消</button>
     <button class="btn btn-p" data-act="monitor.submitException">登记</button>`);

  try {
    const rows = await GET('/process-map/flat');
    const sel = document.getElementById('neProcess');
    if (!sel) return;
    rows.filter((r) => r.level >= 3).forEach((r) => {
      const o = document.createElement('option');
      o.value = String(r.id);
      o.textContent = 'L' + r.level + ' ' + r.code + ' ' + r.name;
      sel.appendChild(o);
    });
  } catch (e) { /* 流程下拉拿不到不影响登记 */ }
}

async function submitException() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const title = val('neTitle').trim();
  if (!title) return toast('请填写异常标题', true);

  // datetime-local 给的是本地时间字符串，转成带时区的 ISO 再提交
  let dueAt = null;
  if (val('neDue')) {
    const d = new Date(val('neDue'));
    if (!isNaN(d.getTime())) dueAt = d.toISOString();
  }

  try {
    await POST('/monitor/exceptions', {
      title,
      description: val('neDesc').trim() || null,
      severity: val('neSeverity'),
      owner: val('neOwner').trim() || null,
      due_at: dueAt,
      process_id: val('neProcess') ? Number(val('neProcess')) : null,
    });
    closeModal();
    toast('异常事件已登记');
    state.monitor.tab = 'exceptions';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

let editingKpi = null;

async function editKpiModal(kpiId) {
  try {
    const kpi = await GET('/monitor/kpis/' + kpiId);
    newKpiModal(kpi);
  } catch (e) {
    toast(e.message, true);
  }
}

function newKpiModal(kpi = null) {
  editingKpi = kpi;
  const meta = state.monitorMeta
    || { kind_labels: {}, frequency_labels: {}, dimension_labels: {} };
  const value = (key) => (kpi && kpi[key] !== null && kpi[key] !== undefined ? kpi[key] : '');
  const options = (labels, selected) => Object.entries(labels || {}).map(([code, label]) =>
    `<option value="${esc(code)}"${code === selected ? ' selected' : ''}>${esc(label)}</option>`)
    .join('');
  const numValue = (key) => (kpi && kpi[key] !== null && kpi[key] !== undefined
    ? kpi[key] : '');

  openModal(kpi ? '编辑 KPI 定义卡 · ' + kpi.code : '新建 KPI 定义卡', `
    <div class="row2">
      <div class="field"><label>KPI 编码 *</label>
        <input id="nkCode" value="${esc(value('code'))}" placeholder="如 EFF-06">
        <div class="hint">全局唯一</div></div>
      <div class="field"><label>指标名称 *</label>
        <input id="nkName" value="${esc(value('name'))}" placeholder="如 订单评审平均时长"></div>
    </div>
    <div class="row3">
      <div class="field"><label>维度</label>
        <select id="nkDim">${options(meta.dimension_labels, value('dimension') || 'EFFICIENCY')}</select></div>
      <div class="field"><label>指标类型</label>
        <select id="nkKind">${options(meta.kind_labels, value('kind') || 'PROCESS')}</select></div>
      <div class="field"><label>统计频率</label>
        <select id="nkFreq">${options(meta.frequency_labels, value('frequency') || 'MONTHLY')}</select></div>
    </div>
    <div class="row3">
      <div class="field"><label>方向</label>
        <select id="nkDir">
          <option value="LOWER_BETTER"${value('direction') === 'LOWER_BETTER' ? ' selected' : ''}>越小越好</option>
          <option value="HIGHER_BETTER"${value('direction') === 'HIGHER_BETTER' ? ' selected' : ''}>越大越好</option>
        </select></div>
      <div class="field"><label>单位</label>
        <input id="nkUnit" value="${esc(value('unit'))}" placeholder="天 / % / 元"></div>
      <div class="field"><label>粒度</label>
        <input id="nkGran" value="${esc(value('granularity'))}" placeholder="如 每张订单 / 月"></div>
    </div>
    <div class="field"><label>计算公式 *</label>
      <textarea id="nkFormula" rows="2" placeholder="Σ(结束时间 − 开始时间) ÷ 单数">${esc(value('formula'))}</textarea>
      <div class="hint">公式与分子分母至少填一组；同一流程下同名 KPI 不允许出现两种公式</div></div>
    <div class="row2">
      <div class="field"><label>分子</label>
        <input id="nkNumerator" value="${esc(value('numerator'))}" placeholder="如 按时交付订单数"></div>
      <div class="field"><label>分母</label>
        <input id="nkDenominator" value="${esc(value('denominator'))}" placeholder="如 总订单数"></div>
    </div>
    <div class="row3">
      <div class="field"><label>数据来源系统</label>
        <input id="nkSource" value="${esc(value('source_system'))}" placeholder="ERP / MES / OA"></div>
      <div class="field"><label>口径说明</label>
        <input id="nkDesc" value="${esc(value('description'))}" placeholder="数据怎么算、排除什么"></div>
      <div class="field"><label>质量规则</label>
        <input id="nkQuality" value="${esc(value('quality_rule'))}" placeholder="如 剔除撤销单"></div>
    </div>
    <div class="row3">
      <div class="field"><label>基线值</label>
        <input id="nkBase" type="number" step="0.01" value="${numValue('baseline_value')}"></div>
      <div class="field"><label>目标值</label>
        <input id="nkTarget" type="number" step="0.01" value="${numValue('target_value')}"></div>
      <div class="field"><label>生效版本</label>
        <input value="${kpi ? 'v' + kpi.version + '（保存后自动 +1）' : 'v1'}" readonly></div>
    </div>
    <div class="row3">
      <div class="field"><label>红线</label>
        <input id="nkRed" type="number" step="0.01" value="${numValue('red_threshold')}"></div>
      <div class="field"><label>黄线</label>
        <input id="nkYellow" type="number" step="0.01" value="${numValue('yellow_threshold')}"></div>
      <div class="field"><label>绿线</label>
        <input id="nkGreen" type="number" step="0.01" value="${numValue('green_threshold')}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>生效日期</label>
        <input id="nkValidFrom" type="date" value="${esc(value('valid_from'))}"></div>
      <div class="field"><label>失效日期</label>
        <input id="nkValidTo" type="date" value="${esc(value('valid_to'))}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>归属流程（L2–L4）</label>
        <select id="nkProcess"><option value="">不关联</option></select></div>
      <div class="field"><label>绑定 L4 活动</label>
        <select id="nkActivity"><option value="">不绑定</option></select></div>
    </div>
    <div class="field"><label>责任人</label>
      <select id="nkOwner"><option value="">未指派</option></select>
      ${kpi && kpi.owner && !kpi.owner_user_id
        ? `<div class="hint">当前展示名「${esc(kpi.owner)}」未绑定账号；选择人员后会同步绑定</div>`
        : ''}</div>
    <div class="note">红/黄/绿必须同时填写：越大越好时 红 ≤ 黄 ≤ 绿，越小越好时 红 ≥ 黄 ≥ 绿。
      保存定义会让版本 +1，追加数据点不会。</div>`,
    `<button class="btn btn-g" data-act="monitor.close">取消</button>
     <button class="btn btn-p" data-act="monitor.submitKpi"
       data-kpi="${kpi ? kpi.id : ''}">${kpi ? '保存' : '创建'}</button>`);

  Promise.all([GET('/process-map/flat'), GET('/execution/assignees')])
    .then(([rows, users]) => {
      const procSel = document.getElementById('nkProcess');
      if (procSel) {
        rows.filter((r) => r.level >= 2).forEach((r) => {
          const o = document.createElement('option');
          o.value = String(r.id);
          o.textContent = 'L' + r.level + ' ' + r.code + ' ' + r.name;
          o.selected = kpi && kpi.process_id === r.id;
          procSel.appendChild(o);
        });
      }
      const actSel = document.getElementById('nkActivity');
      if (actSel) {
        rows.filter((r) => r.level === 4).forEach((r) => {
          const o = document.createElement('option');
          o.value = String(r.id);
          o.textContent = r.code + ' ' + r.name;
          o.selected = kpi && kpi.activity_id === r.id;
          actSel.appendChild(o);
        });
      }
      const ownerSel = document.getElementById('nkOwner');
      if (ownerSel) {
        users.forEach((user) => {
          const o = document.createElement('option');
          o.value = String(user.id);
          o.textContent = user.display_name + ' · ' + (user.role_label || user.role);
          o.selected = kpi && kpi.owner_user_id === user.id;
          ownerSel.appendChild(o);
        });
      }
    })
    .catch(() => {});
}

async function submitKpi(kpiId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numOrNull = (id) => (val(id).trim() === '' ? null : Number(val(id)));
  const textOrNull = (id) => val(id).trim() || null;
  const code = val('nkCode').trim();
  const name = val('nkName').trim();
  if (!code) return toast('请填写 KPI 编码', true);
  if (!name) return toast('请填写指标名称', true);
  if (!val('nkFormula').trim()
    && !(val('nkNumerator').trim() && val('nkDenominator').trim())) {
    return toast('请填写计算公式，或同时填写分子与分母', true);
  }

  const thresholds = ['nkRed', 'nkYellow', 'nkGreen'].map((id) => numOrNull(id));
  if (thresholds.some((v) => v !== null) && thresholds.some((v) => v === null)) {
    return toast('红/黄/绿阈值必须同时填写或同时留空', true);
  }
  const validFrom = val('nkValidFrom') || null;
  const validTo = val('nkValidTo') || null;
  if (validFrom && validTo && validFrom > validTo) {
    return toast('生效日期不能晚于失效日期', true);
  }

  const ownerId = val('nkOwner');
  const payload = {
    code,
    name,
    dimension: val('nkDim'),
    kind: val('nkKind'),
    direction: val('nkDir'),
    frequency: val('nkFreq'),
    unit: textOrNull('nkUnit'),
    granularity: textOrNull('nkGran'),
    formula: textOrNull('nkFormula'),
    numerator: textOrNull('nkNumerator'),
    denominator: textOrNull('nkDenominator'),
    source_system: textOrNull('nkSource'),
    description: textOrNull('nkDesc'),
    quality_rule: textOrNull('nkQuality'),
    baseline_value: numOrNull('nkBase'),
    target_value: numOrNull('nkTarget'),
    red_threshold: thresholds[0],
    yellow_threshold: thresholds[1],
    green_threshold: thresholds[2],
    valid_from: validFrom,
    valid_to: validTo,
    process_id: val('nkProcess') ? Number(val('nkProcess')) : null,
    activity_id: val('nkActivity') ? Number(val('nkActivity')) : null,
    owner_user_id: ownerId ? Number(ownerId) : null,
  };
  // 旧数据只有展示名、没有账号绑定：未选人时保留原文，避免保存后被清空
  if (!ownerId && editingKpi && editingKpi.owner) payload.owner = editingKpi.owner;

  try {
    if (kpiId) {
      await PATCH('/monitor/kpis/' + kpiId, payload);
      toast('KPI 定义已更新');
    } else {
      await POST('/monitor/kpis', payload);
      toast('KPI 已创建');
    }
    editingKpi = null;
    closeModal();
    state.monitor.tab = 'kpi';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

function addKpiRecordModal(kpiId, kpiName) {
  const today = new Date();
  const ym = today.getFullYear() + '-' + _p2(today.getMonth() + 1) + '-01';
  openModal('录入数据点 · ' + kpiName, `
    <div class="row2">
      <div class="field"><label>期间 *</label>
        <input id="nrPeriod" type="date" value="${ym}">
        <div class="hint">同一期间重复提交会覆盖，不会产生重复数据</div></div>
      <div class="field"><label>数值 *</label><input id="nrValue" type="number" step="0.01"></div>
    </div>
    <div class="field"><label>备注</label><input id="nrNote" placeholder="如：口径调整 / 异常月份"></div>`,
    `<button class="btn btn-g" data-act="monitor.close">取消</button>
     <button class="btn btn-p" data-act="monitor.submitRecord" data-kpi="${kpiId}">保存</button>`);
}

async function submitKpiRecord(kpiId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  if (!val('nrPeriod')) return toast('请选择期间', true);
  if (val('nrValue') === '') return toast('请填写数值', true);
  try {
    await POST('/monitor/kpis/' + kpiId + '/records', {
      period: val('nrPeriod'),
      value: Number(val('nrValue')),
      note: val('nrNote').trim() || null,
    });
    closeModal();
    toast('数据点已保存');
    state.monitor.tab = 'kpi';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}


async function createImprovement(kpiId) {
  try {
    const draft = await POST('/monitor/kpis/' + kpiId + '/improvement-draft');
    toast('已生成改善项目 ' + draft.code);
    appActions['projects.open'](draft.id);
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 工作量：标准工时与产能 */
function newWorkloadStandardModal() {
  const meta = state.workloadMeta || { source_labels: {} };
  const sourceOptions = Object.entries(meta.source_labels).map(([value, label]) =>
    `<option value="${esc(value)}">${esc(label)}</option>`).join('');
  openModal('新建标准工时卡', `
    <div class="row2">
      <div class="field"><label>名称 *</label>
        <input id="wsName" placeholder="如 采购需求汇总与归并"></div>
      <div class="field"><label>来源方法</label>
        <select id="wsSource">${sourceOptions}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>L4 活动 *</label>
        <select id="wsActivity"><option value="">请选择</option></select></div>
      <div class="field"><label>岗位 *</label>
        <select id="wsPosition"><option value="">请选择</option></select></div>
    </div>
    <div class="field"><label>方法说明 *</label>
      <input id="wsMethod" placeholder="动作序列、设备、物料、检验"></div>
    <div class="row3">
      <div class="field"><label>观测时间（分钟）*</label>
        <input id="wsObserved" type="number" step="0.01" min="0" placeholder="原始观测均值"></div>
      <div class="field"><label>评定系数</label>
        <input id="wsRating" type="number" step="0.01" min="0.5" max="2" value="1"></div>
      <div class="field"><label>宽放率（0–1）</label>
        <input id="wsAllowance" type="number" step="0.01" min="0" max="1" value="0.1"></div>
    </div>
    <div class="row3">
      <div class="field"><label>有效样本</label>
        <input id="wsSample" type="number" min="0" value="0"></div>
      <div class="field"><label>月频次</label>
        <input id="wsFrequency" type="number" step="0.1" min="0" value="0"></div>
      <div class="field"><label>适用组织</label>
        <select id="wsOrg"><option value="">集团通用</option></select></div>
    </div>
    <div class="row2">
      <div class="field"><label>生效日期</label><input id="wsFrom" type="date"></div>
      <div class="field"><label>失效日期</label><input id="wsTo" type="date"></div>
    </div>
    <div class="note">标准工时 = 观测 × 评定系数 × (1 + 宽放率)。
      新建为草稿；估算来源不能直接验证，验证后才进入产能口径。
      标准工时只作为能力基线，不用于个人考核、扣罚或奖金分配。</div>`,
    `<button class="btn btn-g" data-act="monitor.close">取消</button>
     <button class="btn btn-p" data-act="monitor.submitStandard">创建</button>`);

  Promise.all([GET('/process-map/flat?level=4'), GET('/positions'), GET('/org-units')])
    .then(([activities, positions, orgs]) => {
      const actSel = document.getElementById('wsActivity');
      if (actSel) {
        activities.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.code + ' ' + row.name;
          actSel.appendChild(o);
        });
      }
      const posSel = document.getElementById('wsPosition');
      if (posSel) {
        positions.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.name + (row.org_unit_name ? ' · ' + row.org_unit_name : '');
          posSel.appendChild(o);
        });
      }
      const orgSel = document.getElementById('wsOrg');
      if (orgSel) {
        orgs.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.name;
          orgSel.appendChild(o);
        });
      }
    })
    .catch(() => {});
}

async function submitWorkloadStandard() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numVal = (id) => Number(val(id) || 0);
  const textOrNull = (id) => val(id).trim() || null;
  const name = val('wsName').trim();
  if (!name) return toast('请填写标准名称', true);
  if (!val('wsActivity')) return toast('请选择 L4 活动', true);
  if (!val('wsPosition')) return toast('请选择岗位', true);
  if (numVal('wsObserved') <= 0) return toast('观测时间必须大于 0', true);
  try {
    await POST('/workload/standards', {
      name,
      activity_id: Number(val('wsActivity')),
      position_id: Number(val('wsPosition')),
      org_unit_id: val('wsOrg') ? Number(val('wsOrg')) : null,
      method_description: textOrNull('wsMethod'),
      source: val('wsSource'),
      observed_minutes: numVal('wsObserved'),
      rating_factor: numVal('wsRating'),
      allowance_rate: numVal('wsAllowance'),
      sample_size: Number(val('wsSample') || 0),
      monthly_frequency: numVal('wsFrequency'),
      valid_from: val('wsFrom') || null,
      valid_to: val('wsTo') || null,
    });
    closeModal();
    toast('标准工时卡已创建（草稿）');
    state.monitor.tab = 'workload';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

async function verifyWorkloadStandard(standardId) {
  const ok = await confirmDialog('验证后该标准工时会进入产能与负荷口径，确定继续？',
    { title: '验证标准工时', okText: '验证' });
  if (!ok) return;
  try {
    await POST('/workload/standards/' + standardId + '/verify');
    toast('标准工时已验证');
    state.monitor.tab = 'workload';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

function workloadStandard(standardId) {
  return ((state.monitorWorkload || {}).standards || [])
    .find((row) => row.standard_id === standardId) || null;
}

async function openObservationsModal(standardId) {
  const standard = workloadStandard(standardId);
  let observations;
  try {
    observations = await GET(`/workload/standards/${standardId}/observations`);
  } catch (e) {
    return toast(e.message, true);
  }
  const rows = observations.map((row) => `
    <tr>
      <td>${row.sequence}</td>
      <td>${dtShort(row.observed_at)}</td>
      <td>${num(row.observed_minutes, 2)}</td>
      <td>${esc(row.observer_name || '—')}</td>
      <td>${esc(row.note || '')}</td>
      <td>${canManage() ? `<button class="btn-sm" data-act="monitor.deleteObservation"
        data-id="${row.id}" data-standard="${standardId}">删除</button>` : ''}</td>
    </tr>`).join('') || emptyRow(6, '还没有观测记录');
  const info = standard
    ? `样本 ${standard.sample_size} 条 · 均值 ${num(standard.observed_minutes, 2)} 分钟`
      + ` · ${standard.status_label}`
    : '';
  const addForm = canManage() && standard && standard.status !== 'RETIRED' ? `
    <div class="row3">
      <div class="field"><label>观测时间（分钟）*</label>
        <input id="obsMinutes" type="number" step="0.01" min="0"></div>
      <div class="field"><label>观测时刻</label>
        <input id="obsAt" type="datetime-local"></div>
      <div class="field"><label>备注</label>
        <input id="obsNote" placeholder="可选"></div>
    </div>
    <div class="gap mb"><button class="btn-sm" data-act="monitor.addObservation"
      data-standard="${standardId}">+ 添加观测</button></div>` : '';
  const footer = [
    canManage() && standard && standard.status === 'DRAFT' && standard.sample_size >= 5
      ? `<button class="btn btn-p" data-act="monitor.submitReview"
          data-id="${standardId}">提交评审</button>` : '',
    canManage() && standard && standard.status === 'IN_REVIEW'
      ? `<button class="btn btn-g" data-act="monitor.rejectStandard"
          data-id="${standardId}">退回</button>
         <button class="btn btn-p" data-act="monitor.approveStandard"
          data-id="${standardId}">通过</button>` : '',
    '<button class="btn btn-g" data-act="monitor.close">关闭</button>',
  ].join('');
  openModal(`标准工时样本 · ${esc(standard ? standard.name : standardId)}`, `
    <div class="note mb">${info}<br>
      先定方法，再观测；至少 5 条有效样本才能提交评审。均值与样本量由记录自动计算。
      ${standard && standard.review_note
        ? `<br>上次评审意见：${esc(standard.review_note)}` : ''}</div>
    ${addForm}
    <table class="tbl">
      <thead><tr><th>#</th><th>观测时刻</th><th>分钟</th><th>观测人</th>
        <th>备注</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`, footer, true);
}

async function addObservation(standardId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const minutes = Number(val('obsMinutes'));
  if (!minutes || minutes <= 0) return toast('请填写大于 0 的观测时间', true);
  try {
    await POST(`/workload/standards/${standardId}/observations`, {
      observed_minutes: minutes,
      observed_at: val('obsAt') ? val('obsAt') + ':00' : null,
      note: val('obsNote').trim() || null,
    });
    toast('观测已记录');
    await RENDERERS.monitor();
    openObservationsModal(standardId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteObservation(standardId, observationId) {
  const ok = await confirmDialog('删除后均值和样本量会自动重算，确定继续？',
    { title: '删除观测', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await DEL(`/workload/standards/${standardId}/observations/${observationId}`);
    toast('观测已删除');
    await RENDERERS.monitor();
    openObservationsModal(standardId);
  } catch (e) {
    toast(e.message, true);
  }
}

async function submitStandardReview(standardId) {
  const ok = await confirmDialog('提交后进入待审核；评审通过才进入产能口径。',
    { title: '提交评审', okText: '提交' });
  if (!ok) return;
  try {
    await POST(`/workload/standards/${standardId}/submit-review`);
    toast('已提交评审');
    closeModal();
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

async function reviewWorkloadStandard(standardId, approved) {
  const note = await promptDialog(
    approved ? '审核意见（可留空）' : '退回原因（必填）',
    {
      title: approved ? '通过标准工时' : '退回标准工时',
      okText: approved ? '通过' : '退回',
      value: '',
    },
  );
  if (note === undefined) return;
  if (!approved && !note.trim()) return toast('退回必须填写原因', true);
  try {
    await POST(`/workload/standards/${standardId}/review`, {
      approved,
      note: note.trim() || null,
    });
    toast(approved ? '已通过评审' : '已退回');
    closeModal();
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}

function newCapacityModal() {
  const now = new Date();
  const month = state.monitor.period || now.getFullYear() + '-' + _p2(now.getMonth() + 1);
  openModal('登记产能', `
    <div class="row2">
      <div class="field"><label>组织 *</label>
        <select id="capOrg"><option value="">请选择</option></select></div>
      <div class="field"><label>岗位 *</label>
        <select id="capPosition"><option value="">请选择</option></select></div>
    </div>
    <div class="row3">
      <div class="field"><label>期间 *</label><input id="capPeriod" type="month" value="${month}"></div>
      <div class="field"><label>人数</label>
        <input id="capHeadcount" type="number" step="0.1" min="0" value="1"></div>
      <div class="field"><label>人均可用工时</label>
        <input id="capHours" type="number" step="1" min="0" value="168"></div>
    </div>
    <div class="row2">
      <div class="field"><label>出勤率（0–1）</label>
        <input id="capAttendance" type="number" step="0.01" min="0" max="1" value="1"></div>
      <div class="field"><label>设备可用率（0–1）</label>
        <input id="capEquipment" type="number" step="0.01" min="0" max="1" value="1"></div>
    </div>
    <div class="field"><label>备注</label><input id="capNote" placeholder="如 班次调整 / 计划停机"></div>
    <div class="note">可用工时 = 人数 × 人均可用工时 × 60 × 出勤率 × 设备可用率。</div>`,
    `<button class="btn btn-g" data-act="monitor.close">取消</button>
     <button class="btn btn-p" data-act="monitor.submitCapacity">保存</button>`);

  Promise.all([GET('/org-units'), GET('/positions')])
    .then(([orgs, positions]) => {
      const orgSel = document.getElementById('capOrg');
      if (orgSel) {
        orgs.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.name;
          orgSel.appendChild(o);
        });
      }
      const posSel = document.getElementById('capPosition');
      if (posSel) {
        positions.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.name + (row.org_unit_name ? ' · ' + row.org_unit_name : '');
          posSel.appendChild(o);
        });
      }
    })
    .catch(() => {});
}

async function submitCapacity() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  if (!val('capOrg')) return toast('请选择组织', true);
  if (!val('capPosition')) return toast('请选择岗位', true);
  if (!val('capPeriod')) return toast('请选择期间', true);
  try {
    await POST('/workload/capacity', {
      org_unit_id: Number(val('capOrg')),
      position_id: Number(val('capPosition')),
      period: val('capPeriod') + '-01',
      headcount: Number(val('capHeadcount') || 0),
      available_hours_per_person: Number(val('capHours') || 0),
      attendance_rate: Number(val('capAttendance') || 1),
      equipment_availability: Number(val('capEquipment') || 1),
      note: val('capNote').trim() || null,
    });
    closeModal();
    toast('产能已登记');
    state.monitor.tab = 'workload';
    RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  }
}


export { renderMonitor, drawOverallTrend, drawRadar, drawSpark };
