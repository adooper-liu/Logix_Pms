/* 视图：monitor */
import { esc, num, dtShort, _p2, SEV_COLOR, SEV_LABEL, EXC_COLOR, EXC_LABEL, KPI_DIM_ICON, bar, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage, role } from '../core/auth.js';
import { cssVar } from '../core/theme.js';
import { GET, POST, PATCH } from '../core/api.js';

/* ============================================================ 7. 运营监控与KPI */

const renderMonitor = () => {
  const qs = state.monitor.status ? '?status=' + state.monitor.status : '';
  return renderAsync('monitor',
    () => Promise.all([
      GET('/monitor/kpi-radar'),
      GET('/monitor/exceptions' + qs),
      GET('/monitor/exceptions/summary'),
    ]).then(([radar, exceptions, summary]) => ({ radar, exceptions, summary })),
    (d) => {
      state.monitorRadar = d.radar;
      const tab = state.monitor.tab || 'overview';
      const s = d.summary;
      const dimColor = {
        EFFICIENCY: 'var(--brand)', QUALITY: 'var(--ok)',
        COST: 'var(--warn)', FLEXIBILITY: 'var(--purple)',
      };
      const dimCards = d.radar.dimensions.map((dim) => `
        <div class="kpi stat">
          <div class="num" style="color:${dimColor[dim.dimension]}">${num(dim.achievement_rate, 0)}<small>%</small></div>
          <div class="lab">${KPI_DIM_ICON[dim.dimension]} ${esc(dim.label)}</div>
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

      const kpiRows = d.radar.series.map((series) => {
        const { latest, delta, reach } = kpiInfo(series);
        return `
          <tr>
            <td><b>${esc(series.name)}</b><div class="tiny">${esc(series.code)} · ${esc(series.unit || '')}</div></td>
            <td>${KPI_DIM_ICON[series.dimension] || ''}</td>
            <td><b>${num(latest, 2)}</b></td>
            <td class="muted">${num(series.target_value, 2)}</td>
            <td>${reach === null ? '—' : bar(Math.min(reach, 130), null, 70)}</td>
            <td>${delta === null ? '<span class="muted">—</span>'
              : '<span class="' + (series.direction === 'LOWER_BETTER'
                  ? (delta < 0 ? 'up' : delta > 0 ? 'down' : '')
                  : (delta > 0 ? 'up' : delta < 0 ? 'down' : '')) + '">'
                + (delta > 0 ? '↑ ' : delta < 0 ? '↓ ' : '→ ') + num(Math.abs(delta), 2) + '</span>'}</td>
            <td><canvas class="spark" width="110" height="26" data-spark="${series.kpi_id}"></canvas></td>
            <td>${canManage()
              ? '<button class="btn-sm" onclick="addKpiRecordModal(' + series.kpi_id + ', \''
                + esc(series.name).replace(/'/g, '') + '\')">录入</button>'
              : ''}</td>
          </tr>`;
      }).join('') || emptyRow(7, '暂无 KPI');

      const quick = d.radar.series.map((series) => ({ series, ...kpiInfo(series) }))
        .filter((row) => row.reach !== null)
        .sort((a, b) => a.reach - b.reach)
        .slice(0, 5);
      const quickRows = quick.map(({ series, latest, reach }) => `
        <tr class="clk" onclick="setMonitorTab('kpi')">
          <td><b>${esc(series.name)}</b><div class="tiny">${esc(series.code)}</div></td>
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
          <td><button class="btn-sm" onclick="openException(${e.id})">${canEdit ? '处理' : '查看'}</button></td>
        </tr>`;
      }).join('') || emptyRow(6, '没有符合条件的异常事件');

      const recent = d.exceptions
        .filter((e) => e.status === 'OPEN' || e.status === 'IN_PROGRESS')
        .slice(0, 3);
      const recentRows = recent.map((e) => `
        <div class="alert-row" onclick="openException(${e.id})">
          <span class="tag ${SEV_COLOR[e.severity]}">${SEV_LABEL[e.severity]}</span>
          <div class="alert-main"><b>${esc(e.title)}</b>
            <div class="tiny">${esc(e.owner || '未指派')}${e.is_overdue ? ' · 已超期' : ''}</div></div>
          <span class="alert-go">›</span>
        </div>`).join('') || '<div class="empty">没有未闭环异常</div>';

      const tabs = `
        <div class="seg">
          <button class="${tab === 'overview' ? 'on' : ''}" onclick="setMonitorTab('overview')">概览</button>
          <button class="${tab === 'kpi' ? 'on' : ''}" onclick="setMonitorTab('kpi')">KPI 明细</button>
          <button class="${tab === 'exceptions' ? 'on' : ''}" onclick="setMonitorTab('exceptions')">异常台账</button>
        </div>`;

      const overview = `
        <div class="grid g4 stat-row">${dimCards}</div>
        <div class="grid g2">
          <div class="card">
            <h3>流程健康度雷达</h3>
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
              <a class="link" onclick="setMonitorTab('exceptions')">全部台账 →</a>
            </div>
            <div class="kpi-strip">
              <div><b>${s.open + s.in_progress}</b><span>未闭环</span></div>
              <div><b class="risk">${s.overdue}</b><span>超期</span></div>
              <div><b>${s.resolved + s.closed}</b><span>已闭环</span></div>
            </div>
            ${recentRows}
          </div>
        </div>
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">KPI 速览</h3>
              <div class="desc" style="margin:2px 0 0">按达成率从低到高，优先处理最弱的 5 项</div></div>
            <a class="link" onclick="setMonitorTab('kpi')">全部 ${d.radar.series.length} 项 →</a>
          </div>
          <table class="tbl">
            <thead><tr><th>指标</th><th>当前值</th><th>目标</th><th>达成率</th></tr></thead>
            <tbody>${quickRows}</tbody>
          </table>
        </div>`;

      const kpiPane = `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">KPI 明细（${d.radar.series.length} 项）</h3>
              <div class="desc" style="margin:2px 0 0">越小越好的指标，达成率取目标与实际的比值</div></div>
          </div>
          <table class="tbl">
            <thead><tr><th>指标</th><th>维度</th><th>当前值</th><th>目标</th>
              <th>达成率</th><th>环比</th><th>6 个月走势</th>${canManage() ? '<th></th>' : ''}</tr></thead>
            <tbody>${kpiRows}</tbody>
          </table>
        </div>`;

      const excPane = `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">异常事件台账</h3>
              <div class="desc" style="margin:2px 0 0">闭环管理：登记 → 处理 → 解决 → 关闭</div></div>
            <select class="sel" onchange="setMonitorStatus(this.value)">
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
            <div><h2>运营监控</h2>
              <div class="desc">综合达成率 <b>${num(d.radar.overall_achievement, 1)}%</b>
                · 未闭环 ${s.open + s.in_progress} 件 · 超期 ${s.overdue} 件</div></div>
            <div class="gap">
              ${canWrite() ? '<button class="btn btn-p" onclick="newExceptionModal()">+ 登记异常</button>' : ''}
              ${canManage() ? '<button class="btn btn-g" onclick="newKpiModal()">+ 新建 KPI</button>' : ''}
            </div>
          </div>
          <div class="mt">${tabs}</div>
        </div>
        ${tab === 'kpi' ? kpiPane : tab === 'exceptions' ? excPane : overview}`;

      if (tab === 'overview') drawRadar(d.radar);
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
      `<button class="btn btn-g" onclick="closeModal()">${canEdit ? '取消' : '关闭'}</button>
       ${canEdit ? '<button class="btn btn-p" onclick="saveException(' + e.id + ')">保存</button>' : ''}`);
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
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitException()">登记</button>`);

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

function newKpiModal() {
  openModal('新建 KPI 定义', `
    <div class="row2">
      <div class="field"><label>KPI 编码 *</label>
        <input id="nkCode" placeholder="如 EFF-06"><div class="hint">全局唯一</div></div>
      <div class="field"><label>指标名称 *</label>
        <input id="nkName" placeholder="如 订单评审平均时长"></div>
    </div>
    <div class="row3">
      <div class="field"><label>维度</label>
        <select id="nkDim">
          <option value="EFFICIENCY">效率</option><option value="QUALITY">质量</option>
          <option value="COST">成本</option><option value="FLEXIBILITY">灵活性</option>
        </select></div>
      <div class="field"><label>方向</label>
        <select id="nkDir">
          <option value="LOWER_BETTER">越小越好</option>
          <option value="HIGHER_BETTER">越大越好</option>
        </select></div>
      <div class="field"><label>单位</label><input id="nkUnit" placeholder="天 / % / 元"></div>
    </div>
    <div class="row3">
      <div class="field"><label>基线值</label><input id="nkBase" type="number" step="0.01"></div>
      <div class="field"><label>目标值</label><input id="nkTarget" type="number" step="0.01"></div>
      <div class="field"><label>归属流程</label>
        <select id="nkProcess"><option value="">不关联</option></select></div>
    </div>
    <div class="row2">
      <div class="field"><label>责任人</label><input id="nkOwner" placeholder="指标 Owner"></div>
      <div class="field"><label>统计口径说明</label><input id="nkDesc" placeholder="数据怎么来的"></div>
    </div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitKpi()">创建</button>`);

  GET('/process-map/flat').then((rows) => {
    const sel = document.getElementById('nkProcess');
    if (!sel) return;
    rows.filter((r) => r.level >= 2).forEach((r) => {
      const o = document.createElement('option');
      o.value = String(r.id);
      o.textContent = 'L' + r.level + ' ' + r.code + ' ' + r.name;
      sel.appendChild(o);
    });
  }).catch(() => {});
}

async function submitKpi() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numOrNull = (id) => (val(id) === '' ? null : Number(val(id)));
  const code = val('nkCode').trim();
  const name = val('nkName').trim();
  if (!code) return toast('请填写 KPI 编码', true);
  if (!name) return toast('请填写指标名称', true);

  try {
    await POST('/monitor/kpis', {
      code,
      name,
      dimension: val('nkDim'),
      direction: val('nkDir'),
      unit: val('nkUnit').trim() || null,
      baseline_value: numOrNull('nkBase'),
      target_value: numOrNull('nkTarget'),
      process_id: val('nkProcess') ? Number(val('nkProcess')) : null,
      owner: val('nkOwner').trim() || null,
      description: val('nkDesc').trim() || null,
    });
    closeModal();
    toast('KPI 已创建');
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
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="submitKpiRecord(${kpiId})">保存</button>`);
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


export { renderMonitor, addKpiRecordModal, drawRadar, drawSpark, newExceptionModal, newKpiModal, openException, saveException, setMonitorStatus, setMonitorTab, submitException, submitKpi, submitKpiRecord };
