/* 视图：monitor */
import { esc, num, dtShort, _p2, SEV_COLOR, SEV_LABEL, EXC_COLOR, EXC_LABEL, KPI_DIM_ICON, bar, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, promptDialog, modalAlive, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { workbenchHtml } from './shared/workbench.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { AUTH, canWrite, canManage, role } from '../core/auth.js';
import { cssVar } from '../core/theme.js';
import { metricHelp } from '../core/metrics.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { cockpitTabBar, cockpitProcessSelect, loadCockpitProcesses } from '../core/cockpit.js';
import { toolMountHtml } from './shared/tool_mount.js';

/* ============================================================ 7. 运营驾驶舱：KPI / 异常 / 工作量 / 过程挖掘 */

on('monitor.tab', ({ tab }) => setMonitorTab(tab));
on('monitor.status', (_data, el) => setMonitorStatus(el.value));
on('monitor.openException', ({ id }) => openException(Number(id)));
on('monitor.newException', () => newExceptionModal());
on('monitor.confirmSuggestion', ({ index }) => {
  const row = (state.monitor.suggestions || [])[Number(index)];
  if (row) newExceptionModal(row);
});
on('monitor.newKpi', () => newKpiModal());
on('monitor.editKpi', ({ id }) => editKpiModal(Number(id)));
on('monitor.kind', (_data, el) => setMonitorKind(el.value));
on('monitor.period', (_data, el) => setMonitorPeriod(el.value));
on('monitor.workloadPosition', (_data, el) => setWorkloadPosition(el.value));
on('monitor.analysisTopic', ({ topic }) => {
  if (!topic) return;
  state.monitor.analysisTopic = topic;
  document.querySelectorAll('[data-act="monitor.analysisTopic"]').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.topic === topic);
  });
  const main = document.getElementById('anMain');
  const parts = state.monitor.analysisParts || {};
  if (main && parts[topic]) main.innerHTML = parts[topic];
});
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
on('monitor.improveException', ({ id }) => createExceptionImprovement(Number(id)));
on('monitor.openProject', ({ id }) => {
  closeModal();
  go('projects', { params: { project: Number(id) }, push: true });
});
on('monitor.addRecord', ({ kpi, name }) => addKpiRecordModal(Number(kpi), name));
on('monitor.submitRecord', ({ kpi }) => submitKpiRecord(Number(kpi)));
const MATCH_OP = {
  eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤', in: '属于', contains: '包含',
};

function matchLine(edge) {
  return (edge.match_conditions || []).map((row) => {
    const field = (row.field || '').trim();
    const op = row.op || 'eq';
    if (op === 'truthy') return field ? field + ' 有值' : '';
    if (op === 'falsy') return field ? field + ' 没值' : '';
    const value = row.value === undefined || row.value === null ? '' : String(row.value);
    if (!field && !value) return '';
    return [field, MATCH_OP[op] || op, value].filter(Boolean).join(' ');
  }).filter(Boolean).join(' 且 ');
}

const DURATION_MINUTES = {
  '天': 1440, '日': 1440, day: 1440, days: 1440,
  '小时': 60, '时': 60, h: 60, hour: 60, hours: 60,
  '分钟': 1, '分': 1, min: 1, minute: 1, minutes: 1,
};

function durationMinutes(unit) {
  const raw = (unit || '').trim();
  if (Object.prototype.hasOwnProperty.call(DURATION_MINUTES, raw)) return DURATION_MINUTES[raw];
  const key = raw.toLowerCase();
  return Object.prototype.hasOwnProperty.call(DURATION_MINUTES, key) ? DURATION_MINUTES[key] : null;
}

/** 当前状态时间线：每步的作业和等待分开。作业只分增值、必须核对。 */
function valueStreamHtml(modelNodes, metrics, mining, kpis) {
  const steps = modelNodes
    .filter((row) => row.node_type !== 'START' && row.node_type !== 'END')
    .slice()
    .sort((a, b) => (a.sequence_order || 0) - (b.sequence_order || 0));
  if (!steps.length) {
    return '<div class="tiny muted">这条流程还没有可排成时间线的步骤。</div>';
  }
  let valueMin = 0;
  let checkMin = 0;
  let waitMin = 0;
  const span = steps.map((row) => {
    const work = Number(row.duration_minutes) || 0;
    const idle = Number(row.wait_minutes) || 0;
    if (row.node_type === 'WAIT') {
      waitMin += work + idle;
      return { row, work: 0, wait: work + idle, kind: 'wait' };
    }
    if (row.is_value_added) valueMin += work;
    else checkMin += work;
    waitMin += idle;
    return { row, work, wait: idle, kind: row.is_value_added ? 'value' : 'check' };
  });
  const maxSpan = Math.max(1, ...span.map((step) => step.work + step.wait));
  const observed = mining && mining.instance_total > 0;
  const source = observed
    ? `纳入路径 ${mining.instance_total} 个。下面仍是模型里填的作业和等待，不是这些事例的实测。`
    : '还没有走完的实例。下面是模型里填的作业和等待，不是现场计时。';
  const rows = span.map((step) => {
    const kindLabel = step.kind === 'value' ? '增值' : (step.kind === 'check' ? '必须核对' : '纯等待');
    return `<div class="vs-step">
      <div><b>${esc(step.row.name)}</b>
        <div class="tiny">${esc(step.row.lane || '')}</div></div>
      <div class="vs-bar">
        <i class="vs-work ${step.kind}" style="width:${(step.work / maxSpan) * 100}%"></i>
        <i class="vs-wait" style="width:${(step.wait / maxSpan) * 100}%"></i>
      </div>
      <div class="tiny">作业 ${num(step.work, 1)} 分 · ${kindLabel}<br>等待 ${num(step.wait, 1)} 分</div>
    </div>`;
  }).join('');
  const straight = valueMin + checkMin + waitMin;
  const targets = (kpis || []).filter((row) =>
    durationMinutes(row.unit) && row.target_value !== null && row.target_value !== undefined);
  const targetHtml = targets.length
    ? targets.map((row) => {
      const scale = durationMinutes(row.unit);
      const folded = straight / scale;
      const how = scale === 1440 ? '按 24 小时折合' : (scale === 60 ? '按 60 分钟折合' : '同单位');
      return `<div class="tiny">目标周期 ${esc(row.name)} ${num(row.target_value, 2)} ${
        esc(row.unit || '')}。各步相加${how} ${num(folded, 1)} ${esc(row.unit || '')}。</div>`;
    }).join('')
    : '<div class="tiny">还没有用时间做单位的目标周期。</div>';
  const expected = metrics
    ? `<div class="tiny muted">含分支和返工的期望周期 ${num(metrics.lead_time_minutes, 1)} 分，其中增值 ${
      num(metrics.value_added_minutes, 1)} 分、等待 ${num(metrics.wait_minutes, 1)} 分。返工不计入增值。</div>`
    : '';
  return `
    <p class="tiny vs-note">${source} 未标成增值的作业先归入必须核对。</p>
    <div class="vs-sum">
      <span>增值作业 ${num(valueMin, 1)} 分</span>
      <span>必须核对 ${num(checkMin, 1)} 分</span>
      <span>纯等待 ${num(waitMin, 1)} 分</span>
      <span>各步相加 ${num(straight, 1)} 分</span>
    </div>
    <div class="vs-list">${rows}</div>
    ${expected}
    ${targetHtml}`;
}

/** 原因里点名的步骤。全名优先；写了前四个字也算落到这一步。 */
function landedSteps(cause, modelNodes) {
  const text = (cause || '').trim();
  if (!text) return [];
  const steps = (modelNodes || []).filter((row) =>
    row.name && row.node_type !== 'START' && row.node_type !== 'END');
  const exact = steps.filter((row) => text.includes(row.name));
  if (exact.length) return exact;
  return steps.filter((row) => row.name.length >= 4 && text.includes(row.name.slice(0, 4)));
}

function causeHtml(exceptions, modelNodes, kpis, mining, pid) {
  const events = (exceptions || [])
    .filter((row) => row.process_id === pid)
    .slice()
    .sort((a, b) => {
      const aw = (a.root_cause || '').trim() ? 0 : 1;
      const bw = (b.root_cause || '').trim() ? 0 : 1;
      if (aw !== bw) return aw - bw;
      return String(b.detected_at || '').localeCompare(String(a.detected_at || ''));
    });
  if (!events.length) {
    return '<div class="tiny muted">这条流程还没有登记异常。</div>';
  }
  const observed = mining && mining.instance_total > 0;
  const source = observed
    ? `纳入路径 ${mining.instance_total} 个。下面仍是异常台账里写下的内容，不是从这些事例自动追出来的。`
    : '还没有走完的实例。下面来自异常台账，不是从实例里追出来的。';
  const shown = events.slice(0, 6);
  const cards = shown.map((row) => {
    const cause = (row.root_cause || '').trim();
    const lines = cause.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    const why = !lines.length
      ? '<div class="tiny muted">还没写下原因。</div>'
      : (lines.length === 1
        ? `<div>${esc(lines[0])}</div>
           <div class="tiny muted">还是一整句。一行写一个为什么，才能看出追问停在哪里。</div>`
        : `<ol class="rc-why">${lines.map((line) => `<li>${esc(line)}</li>`).join('')}</ol>`);
    const steps = landedSteps(cause, modelNodes);
    const stepText = !cause
      ? '先写下原因，才能对到节点。'
      : (steps.length
        ? steps.map((step) => esc(step.name)).join('、')
        : '还没落到模型上的某一步。');
    const action = (row.action_taken || '').trim();
    const kpi = row.source_kpi_id
      ? (kpis || []).find((item) => item.id === row.source_kpi_id)
      : null;
    let watch = '还没有指定改完要看的指标。';
    if (row.source_kpi_id && kpi) {
      const unit = kpi.unit ? ' ' + kpi.unit : '';
      const bits = [esc(kpi.code) + ' ' + esc(kpi.name)];
      if (kpi.latest_value !== null && kpi.latest_value !== undefined) {
        bits.push('当前 ' + num(kpi.latest_value, 2) + unit);
      }
      if (kpi.target_value !== null && kpi.target_value !== undefined) {
        bits.push('目标 ' + num(kpi.target_value, 2) + unit);
      }
      watch = bits.join('，');
    } else if (row.source_kpi_id) {
      watch = '来源指标已不在列表里。';
    }
    const symptom = (row.description || '').trim();
    return `<article class="rc-card">
      <div class="rc-head">
        <div>
          <b>${esc(row.code)} ${esc(row.title)}</b>
          <div class="tiny">${esc(EXC_LABEL[row.status] || row.status)}</div>
        </div>
        <button type="button" class="btn-sm" data-act="monitor.openException" data-id="${row.id}">打开这条异常</button>
      </div>
      <div class="rc-line"><span>现象</span><div>${symptom ? esc(symptom) : '<span class="muted">还没写下现象。</span>'}</div></div>
      <div class="rc-line"><span>原因</span><div>${why}</div></div>
      <div class="rc-line"><span>落在哪一步</span><div>${stepText}</div></div>
      <div class="rc-line"><span>措施</span><div>${action ? esc(action) : '<span class="muted">还没写下措施。</span>'}</div></div>
      <div class="rc-line"><span>改完看</span><div>${watch}</div></div>
      ${row.project_id
        ? `<div class="rc-actions"><button type="button" class="btn-sm" data-act="monitor.openProject" data-id="${row.project_id}">打开改善项目</button></div>`
        : ''}
    </article>`;
  }).join('');
  const rest = events.length - shown.length;
  return `
    <p class="tiny vs-note">${source}</p>
    ${cards}
    ${rest > 0 ? `<div class="tiny muted">还有 ${rest} 条，到异常台账看。</div>` : ''}`;
}

/** 同一节点出去的多条边是一个判断；回到更早节点的边单独算退回。 */
function ruleView(modelNodes, edges, mining) {
  const byKey = new Map((modelNodes || []).map((row) => [row.node_key, row]));
  const nameOf = (key) => (byKey.get(key) ? byKey.get(key).name : key);
  const orderOf = (key) => (byKey.get(key) ? byKey.get(key).sequence_order : null);
  const interesting = (edges || []).filter((edge) => Boolean(
    (edge.condition || '').trim()
    || (edge.label || '').trim()
    || (edge.match_conditions || []).length
    || edge.is_default
    || Number(edge.probability) < 1
  ));
  const isReturn = (edge) => {
    const from = orderOf(edge.source_key);
    const to = orderOf(edge.target_key);
    return from !== null && to !== null && to < from;
  };
  const returns = interesting.filter(isReturn);
  const groups = new Map();
  interesting.filter((edge) => !isReturn(edge)).forEach((edge) => {
    if (!groups.has(edge.source_key)) groups.set(edge.source_key, []);
    groups.get(edge.source_key).push(edge);
  });
  const decisions = [];
  groups.forEach((list, key) => {
    const real = list.filter((edge) =>
      (edge.condition || '').trim()
      || (edge.match_conditions || []).length
      || edge.is_default
      || Number(edge.probability) < 1
      || list.length > 1);
    if (real.length) decisions.push({ key, edges: real });
  });
  if (!decisions.length && !returns.length) {
    return {
      html: '<div class="tiny muted">连线上还没有分支条件。</div>',
      decisions: 0,
      returns: 0,
    };
  }
  const observed = mining && mining.instance_total > 0;
  const source = observed
    ? `纳入路径 ${mining.instance_total} 个。下面的比例是模型里填的，不是这些事例走出的占比。`
    : '还没有走完的实例。下面是模型里的判断和退回，不是实例走出的占比。';
  const decisionHtml = decisions.map(({ key, edges: list }) => {
    const fields = [...new Set(list.flatMap((edge) =>
      (edge.match_conditions || []).map((row) => (row.field || '').trim()).filter(Boolean)))];
    const context = fields.length
      ? `走这一步时看 ${fields.map(esc).join('、')}。`
      : '这些分支还没有对应的字段，走单时只能靠人看说明。';
    const sum = list.reduce((acc, edge) => acc + (Number(edge.probability) || 0), 0);
    const cover = Math.abs(sum - 1) <= 0.02
      ? '这几条合起来 100%。'
      : `这几条合起来 ${num(sum * 100, 0)}%，还有没写上的情况。`;
    const defaults = list.filter((edge) => edge.is_default);
    const defaultNote = defaults.length
      ? `没对上的走 ${defaults.map((edge) => esc(edge.label || nameOf(edge.target_key))).join('、')}。`
      : '';
    const rows = list.slice().sort((a, b) => (b.probability || 0) - (a.probability || 0)).map((edge) => {
      const judge = matchLine(edge);
      const prose = (edge.condition || '').trim();
      const title = edge.label || (edge.is_default ? '默认' : '未命名');
      const gap = !judge && prose && fields.length
        ? '<div class="tiny muted">还只有一句说明，没有对应字段。</div>' : '';
      const bare = !judge && !prose ? '<div class="tiny muted">这条还没有判断说明。</div>' : '';
      return `<div class="ru-branch">
        <div><b>${esc(title)}</b> ${num((Number(edge.probability) || 0) * 100, 0)}%
          <div class="tiny">到 ${esc(nameOf(edge.target_key))}</div></div>
        <div>
          ${prose ? `<div>${esc(prose)}</div>` : ''}
          ${judge ? `<div class="tiny">判断 ${esc(judge)}</div>` : ''}
          ${gap}${bare}
        </div>
      </div>`;
    }).join('');
    return `<article class="rc-card">
      <div class="rc-head"><b>判断点 ${esc(nameOf(key))}</b></div>
      <div class="tiny">${context}</div>
      ${rows}
      <div class="tiny muted">${cover}${defaultNote ? ' ' + defaultNote : ''}</div>
    </article>`;
  }).join('');
  const returnHtml = returns.length
    ? `<div class="ru-label">退回</div>${returns.map((edge) => `
      <article class="rc-card">
        <div><b>${esc(nameOf(edge.source_key))} → ${esc(nameOf(edge.target_key))}</b></div>
        <div class="tiny">${esc((edge.label || edge.condition || '回到前面').trim())}</div>
        <div class="tiny muted">这一步回到前面的节点，不是另一条判断。</div>
      </article>`).join('')}`
    : '';
  return {
    html: `<p class="tiny vs-note">${source}</p>${decisionHtml}${returnHtml}`,
    decisions: decisions.length,
    returns: returns.length,
  };
}

/** 没有实例时画出模型走法。有实例时，拿出现最多的路径去对模型主走法。 */
function modelWalk(modelNodes, edges) {
  const visible = (node) => node && node.node_type !== 'START' && node.node_type !== 'END';
  const byKey = new Map((modelNodes || []).map((row) => [row.node_key, row]));
  const nameOf = (key) => {
    const node = byKey.get(key);
    return node ? node.name : key;
  };
  const orderOf = (key) => {
    const node = byKey.get(key);
    return node ? node.sequence_order : null;
  };
  const allEdges = edges || [];
  const isReturn = (edge) => {
    const from = orderOf(edge.source_key);
    const to = orderOf(edge.target_key);
    return from !== null && to !== null && to < from;
  };
  const returns = allEdges.filter(isReturn);
  const forward = allEdges.filter((edge) => !isReturn(edge));
  const out = new Map();
  forward.forEach((edge) => {
    if (!out.has(edge.source_key)) out.set(edge.source_key, []);
    out.get(edge.source_key).push(edge);
  });
  const incoming = new Set(forward.map((edge) => edge.target_key));
  const starts = (modelNodes || [])
    .filter((row) => !incoming.has(row.node_key))
    .sort((a, b) => (a.sequence_order || 0) - (b.sequence_order || 0));
  const start = starts[0] || (modelNodes || []).slice()
    .sort((a, b) => (a.sequence_order || 0) - (b.sequence_order || 0))[0];
  if (!start) return null;
  const trunk = [];
  const seen = new Set();
  let cursor = start;
  let split = null;
  while (cursor && !seen.has(cursor.node_key)) {
    seen.add(cursor.node_key);
    if (visible(cursor)) trunk.push(cursor);
    const nexts = out.get(cursor.node_key) || [];
    if (!nexts.length) break;
    if (nexts.length > 1) {
      split = cursor;
      break;
    }
    cursor = byKey.get(nexts[0].target_key);
  }
  if (!trunk.length) return null;
  const follow = (edge) => {
    const names = [];
    let node = byKey.get(edge.target_key);
    const local = new Set(trunk.map((row) => row.node_key));
    while (node && visible(node) && !local.has(node.node_key)) {
      names.push(node.name);
      local.add(node.node_key);
      const nexts = out.get(node.node_key) || [];
      if (nexts.length !== 1) break;
      node = byKey.get(nexts[0].target_key);
    }
    return names.length ? names : [nameOf(edge.target_key)];
  };
  const splitEdges = split
    ? (out.get(split.node_key) || []).slice().sort((a, b) =>
      (orderOf(a.target_key) || 0) - (orderOf(b.target_key) || 0))
    : [];
  const mainEdge = splitEdges.slice().sort((a, b) => {
    const diff = (Number(b.probability) || 0) - (Number(a.probability) || 0);
    if (Math.abs(diff) > 0.001) return diff;
    return (orderOf(a.target_key) || 0) - (orderOf(b.target_key) || 0);
  })[0];
  return {
    trunk,
    split,
    splitEdges,
    returns,
    follow,
    nameOf,
    mainNames: trunk.map((row) => row.name).concat(mainEdge ? follow(mainEdge) : []),
  };
}

function pathDiff(mainNames, seenNames) {
  const mainSet = new Set(mainNames);
  const seenSet = new Set(seenNames || []);
  const missing = mainNames.filter((name) => !seenSet.has(name));
  const extra = [];
  (seenNames || []).forEach((name) => {
    if (!mainSet.has(name) && !extra.includes(name)) extra.push(name);
  });
  const counts = {};
  (seenNames || []).forEach((name) => { counts[name] = (counts[name] || 0) + 1; });
  const repeated = Object.keys(counts).filter((name) => counts[name] > 1);
  return {
    missing,
    extra,
    repeated,
    same: !missing.length && !extra.length && !repeated.length,
  };
}

function pathCompareText(top, mainNames) {
  const diff = pathDiff(mainNames, top.node_names || []);
  if (diff.same) return '出现最多的路径和模型主走法一致。';
  return `出现最多的路径有 ${top.instance_count} 个，占 ${num(top.share_pct, 1)}%。`
    + (diff.missing.length ? ' 没有走到：' + diff.missing.map(esc).join('、') + '。' : '')
    + (diff.extra.length ? ' 多出来：' + diff.extra.map(esc).join('、') + '。' : '')
    + (diff.repeated.length ? ' 同一节点出现了多次：' + diff.repeated.map(esc).join('、') + '。' : '');
}

function pathView(modelNodes, edges, mining) {
  const walk = modelWalk(modelNodes, edges);
  if (!walk) {
    return { html: '<div class="tiny muted">这条流程还没有可排成走法的步骤。</div>', modeled: false };
  }
  const trunkHtml = `<div class="path-line">${walk.trunk.map((row) => esc(row.name)).join(' → ')}</div>`;
  const splitHtml = walk.splitEdges.length
    ? `<div class="tiny path-split">到 ${esc(walk.split.name)} 分开：</div>
      ${walk.splitEdges.map((edge) => `
        <div class="path-branch"><b>${esc(edge.label || edge.condition || '另一条')}</b>
          <span>→ ${walk.follow(edge).map(esc).join(' → ')}</span></div>`).join('')}`
    : '';
  const returnHtml = walk.returns.length
    ? `<div class="ru-label">退回</div>${walk.returns.map((edge) => `
      <div class="path-branch"><b>${esc(walk.nameOf(edge.source_key))} → ${esc(walk.nameOf(edge.target_key))}</b>
        <span>${esc((edge.label || edge.condition || '回到前面').trim())}</span></div>`).join('')}`
    : '';
  const variants = ((mining && mining.variants) || []).slice()
    .sort((a, b) => (b.instance_count || 0) - (a.instance_count || 0));
  const observed = mining && mining.instance_total > 0 && variants.length;
  const note = observed
    ? `纳入路径 ${mining.instance_total} 个。上面是模型里的走法，下面是走出的路径。`
    : '还没有能排成路径的事例。下面是模型里的走法，不是现场走出来的。';
  let compare = '';
  if (observed) {
    const top = variants[0];
    const rows = variants.slice(0, 6).map((row) => `
      <tr>
        <td class="tiny">${(row.node_names || []).map(esc).join(' → ')}</td>
        <td>${esc(row.source_label || '实例')}</td>
        <td>${row.instance_count}</td>
        <td>${num(row.share_pct, 1)}%</td>
        <td>${row.avg_cycle_minutes === null || row.avg_cycle_minutes === undefined
          ? '—' : num(row.avg_cycle_minutes, 1) + ' 分'}</td>
      </tr>`).join('');
    compare = `
      <div class="tiny path-split">模型主走法：${walk.mainNames.map(esc).join(' → ')}</div>
      <table class="tbl"><thead><tr><th>路径</th><th>来源</th><th>次数</th><th>占比</th><th>平均周期</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <div class="tiny">${pathCompareText(top, walk.mainNames)}</div>`;
  }
  return {
    html: `<p class="tiny vs-note">${note}</p>${trunkHtml}${splitHtml}${returnHtml}${compare}`,
    modeled: true,
  };
}

function analysisHtml(d) {
  const pid = state.cockpit.processId;
  if (!pid) {
    return `<div class="card"><p class="tiny muted">先在上面选一条流程。</p></div>`;
  }
  const mining = d.mining;
  const metrics = d.analysis && d.analysis.metrics;
  const modelNodes = (d.model && d.model.nodes) || [];
  const paths = pathView(modelNodes, (d.model && d.model.edges) || [], mining);
  const flagged = ((d.analysis && d.analysis.nodes) || []).filter((row) => row.is_bottleneck);
  const ranked = ((d.analysis && d.analysis.nodes) || [])
    .slice()
    .sort((a, b) => b.weighted_minutes - a.weighted_minutes)
    .slice(0, 5);
  const bottleneckRows = (flagged.length ? flagged : ranked).map((row) => `
    <tr>
      <td>${esc(row.name)}</td>
      <td>${esc(row.lane || '—')}</td>
      <td>${num(row.wait_share * 100, 0)}%</td>
      <td>${num(row.weighted_minutes, 1)} 分</td>
    </tr>`).join('');
  const processEvents = (d.exceptions || []).filter((row) => row.process_id === pid);
  const writtenCauses = processEvents.filter((row) => (row.root_cause || '').trim());
  const rules = ruleView(modelNodes, (d.model && d.model.edges) || [], mining);
  const kpis = (d.kpis || []).filter((row) => row.process_id === pid);
  const kpiRows = kpis.slice(0, 8).map((row) => `
    <tr>
      <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
      <td>${row.baseline_value === null || row.baseline_value === undefined
        ? '—' : num(row.baseline_value, 2)} ${esc(row.unit || '')}</td>
      <td>${row.latest_value === null || row.latest_value === undefined
        ? '—' : num(row.latest_value, 2)}</td>
      <td>${row.target_value === null || row.target_value === undefined
        ? '—' : num(row.target_value, 2)}</td>
    </tr>`).join('');
  const pce = metrics ? metrics.pce * 100 : null;
  const wait = metrics ? metrics.wait_ratio * 100 : null;
  const parts = {
    path: `
      <h3 style="margin:0 0 8px">现状拆解</h3>
      ${paths.html}`,
    bottleneck: `
      <h3 style="margin:0 0 8px">瓶颈识别</h3>
      <div class="tiny muted mb">${flagged.length
        ? `测算标出 ${flagged.length} 个瓶颈节点。`
        : '测算没有把节点标成瓶颈。下表是对期望周期贡献最大的节点。'}</div>
      ${bottleneckRows
        ? `<table class="tbl"><thead><tr><th>节点</th><th>泳道</th><th>等待占比</th><th>期望贡献</th></tr></thead>
           <tbody>${bottleneckRows}</tbody></table>`
        : '<div class="tiny muted">这条流程还没有可测算的模型。</div>'}`,
    value: `
      <h3 style="margin:0 0 8px">价值流分析</h3>
      ${valueStreamHtml(modelNodes, metrics, mining, kpis)}`,
    cause: `
      <h3 style="margin:0 0 8px">根因分析</h3>
      ${causeHtml(d.exceptions, modelNodes, d.kpis || [], mining, pid)}`,
    rule: `
      <h3 style="margin:0 0 8px">规则与上下文</h3>
      ${rules.html}`,
    baseline: `
      <h3 style="margin:0 0 8px">绩效基线</h3>
      ${kpiRows
        ? `<table class="tbl"><thead><tr><th>指标</th><th>基线</th><th>当前</th><th>目标</th></tr></thead>
           <tbody>${kpiRows}</tbody></table>`
        : '<div class="tiny muted">这条流程还没有挂 KPI，所以没有基线。</div>'}`,
  };
  state.monitor.analysisParts = parts;
  const topic = parts[state.monitor.analysisTopic] ? state.monitor.analysisTopic : 'path';
  state.monitor.analysisTopic = topic;
  const marks = {
    path: mining && mining.variant_count
      ? mining.variant_count + ' 条路径'
      : (paths.modeled ? '模型走法' : '还没记'),
    bottleneck: (flagged.length || ranked.length)
      ? (flagged.length || ranked.length) + ' 个节点' : '还没记',
    value: modelNodes.some((row) => row.node_type !== 'START' && row.node_type !== 'END')
      ? modelNodes.filter((row) => row.node_type !== 'START' && row.node_type !== 'END').length + ' 步'
      : '还没记',
    cause: writtenCauses.length
      ? writtenCauses.length + ' 条根因'
      : (processEvents.length ? processEvents.length + ' 条还没追' : '还没记'),
    rule: rules.decisions
      ? rules.decisions + ' 个判断'
      : (rules.returns ? rules.returns + ' 条退回' : '还没记'),
    baseline: kpis.length ? kpis.length + ' 个指标' : '还没记',
  };
  const topics = [
    ['path', '现状拆解'],
    ['bottleneck', '瓶颈识别'],
    ['value', '价值流分析'],
    ['cause', '根因分析'],
    ['rule', '规则与上下文'],
    ['baseline', '绩效基线'],
  ];
  const topicButtons = topics.map(([key, label]) => `
    <button type="button" class="an-topic${key === topic ? ' on' : ''}"
      data-act="monitor.analysisTopic" data-topic="${key}">
      <b>${label}</b>
      <span class="tiny">${marks[key]}</span>
    </button>`).join('');
  return `
    <div class="an-shell">
      <aside class="card an-side">
        <h3 style="margin:0 0 8px">分析项</h3>
        <div class="an-topics">${topicButtons}</div>
      </aside>
      <main class="card an-main" id="anMain">${parts[topic]}</main>
      <aside class="card an-aside">
        <h3 style="margin:0 0 8px">这条流程</h3>
        <div class="an-num"><b>${mining ? mining.instance_total : 0}</b><span>纳入路径</span></div>
        <div class="an-num"><b>${mining ? mining.variant_count : 0}</b><span>实际路径</span></div>
        <div class="an-num"><b>${pce === null ? '—' : num(pce, 1) + '%'}</b><span>增值占期望周期</span></div>
        <div class="an-num"><b>${wait === null ? '—' : num(wait, 0) + '%'}</b><span>等待占期望周期</span></div>
      </aside>
    </div>`;
}

const renderMonitor = () => {
  const params = urlParams();
  if (params.tab) state.monitor.tab = params.tab;
  state.cockpit.processId = Number(params.process) || null;
  // 旧默认 overview 已并入 KPI；总览由 dashboard 承担。
  const tab = state.monitor.tab === 'overview' ? 'kpi' : (state.monitor.tab || 'kpi');
  state.monitor.tab = tab;
  const needKpi = tab === 'kpi';
  const needExceptions = tab === 'exceptions';
  const needWorkload = tab === 'workload';
  const needAnalysis = tab === 'analysis';
  const needMining = tab === 'mining' || needAnalysis;
  const qs = state.monitor.status ? '?status=' + state.monitor.status : '';
  const cockpitPid = state.cockpit.processId;
  const loadMining = () => needMining && cockpitPid
    ? Promise.all([
      GET('/execution/mining?process_id=' + cockpitPid).catch(() => null),
      needAnalysis
        ? POST('/processes/' + cockpitPid + '/design/analyze').catch(() => null)
        : Promise.resolve(null),
      GET('/processes/' + cockpitPid + '/design').catch(() => null),
    ]).then(([mining, analysis, model]) => ({ mining, analysis, model }))
      .catch(() => ({ mining: null, analysis: null, model: null }))
    : Promise.resolve({ mining: null, analysis: null, model: null });
  return renderAsync('monitor',
    () => Promise.all([
      GET('/monitor/kpi-radar' + (cockpitPid ? '?process_id=' + cockpitPid : '')),
      (needExceptions || needAnalysis)
        ? GET('/monitor/exceptions' + (needAnalysis ? '' : qs))
        : Promise.resolve([]),
      GET('/monitor/exceptions/summary'),
      GET('/monitor/meta'),
      needWorkload
        ? GET('/workload/summary' + (state.monitor.period
          ? '?period=' + state.monitor.period + '-01' : ''))
        : Promise.resolve(null),
      needWorkload ? GET('/workload/meta') : Promise.resolve(null),
      needKpi ? GET('/monitor/improvement-candidates') : Promise.resolve([]),
      needExceptions
        ? GET('/monitor/exception-suggestions').catch(() => [])
        : Promise.resolve([]),
      needWorkload ? GET('/workforce/forecast?months=3').catch(() => null) : Promise.resolve(null),
      needWorkload && canManage()
        ? GET('/workforce/balance').catch(() => null) : Promise.resolve(null),
      loadMining(),
      (needAnalysis || needKpi) ? GET('/monitor/kpis').catch(() => []) : Promise.resolve([]),
      loadCockpitProcesses(),
      GET('/tools').catch(() => []),
      needAnalysis && cockpitPid ? GET('/processes/'+cockpitPid+'/workbench') : Promise.resolve(null),
    ]).then(([radar, exceptions, summary, meta, workload, workloadMeta, candidates, suggestions, forecast, balance, miningData, kpis, flowList, tools, workbench]) => ({
      workbench,
      radar, exceptions, summary, meta, workload, workloadMeta, candidates, suggestions, forecast, balance,
      flowList, mining: miningData.mining,
      analysis: miningData.analysis, model: miningData.model, kpis, tools,
    })),
    (d) => {
      state.monitorRadar = d.radar;
      state.monitor.suggestions = state.cockpit.processId
        ? (d.suggestions || []).filter((row) => row.process_id === state.cockpit.processId)
        : (d.suggestions || []);
      state.monitorMeta = d.meta;
      state.workloadMeta = d.workloadMeta;
      const tab = state.monitor.tab || 'kpi';
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
        if (series.status !== 'GRAY' && series.intake !== 'DRAFT' && latest !== null && series.target_value) {
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
      const statusRank = { RED: 0, YELLOW: 1, GREEN: 2 };
      const candidateIds = new Set((d.candidates || []).map((row) => row.kpi_id));
      const orderedSeries = visibleSeries.slice().sort((a, b) =>
        (statusRank[a.status] ?? 3) - (statusRank[b.status] ?? 3));

      const kpiRows = orderedSeries.map((series) => {
        const { latest, delta, reach } = kpiInfo(series);
        return `
          <tr>
            <td><b>${esc(series.name)}</b><div class="tiny">${esc(series.code)} · ${esc(series.unit || '')}
              <span class="tag t-blu">${esc(series.kind_label)}</span>
              <span class="tag t-gry">${esc(series.intake_label || '')}</span></div></td>
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
                  ${candidateIds.has(series.kpi_id)
                    ? `<button class="btn-sm btn-p" data-act="monitor.improveKpi"
                        data-id="${series.kpi_id}">转改善</button>` : ''}
                  <button class="btn-sm" data-act="monitor.addRecord" data-kpi="${series.kpi_id}"
                    data-name="${esc(series.name)}">补录</button>
                  <button class="btn-sm" data-act="monitor.editKpi"
                    data-id="${series.kpi_id}">编辑</button>
                </div>`
              : ''}</td>
          </tr>`;
      }).join('') || emptyRow(9, state.cockpit.processId
        ? '这条流程还没有 KPI' : (kindFilter ? '该类型下暂无 KPI' : '暂无 KPI'));

      const exceptionList = state.cockpit.processId
        ? (d.exceptions || []).filter((row) => row.process_id === state.cockpit.processId)
        : (d.exceptions || []);
      const excOpen = state.cockpit.processId
        ? exceptionList.filter((row) => row.status === 'OPEN' || row.status === 'IN_PROGRESS').length
        : s.open + s.in_progress;
      const excOverdue = state.cockpit.processId
        ? exceptionList.filter((row) => row.is_overdue).length
        : s.overdue;
      const excRows = exceptionList.map((e) => {
        const canEdit = canManage()
          || (role() === 'OWNER' && AUTH.user && e.owner_user_id === AUTH.user.id);
        const canImprove = canEdit
          && !e.project_id
          && (e.status === 'OPEN' || e.status === 'IN_PROGRESS');
        return `
        <tr>
          <td class="tiny">${dtShort(e.detected_at)}</td>
          <td>${esc(e.title)}<div class="tiny">${esc(e.code)}${
            e.is_overdue ? ' · <span style="color:var(--bad)">已超期</span>' : ''}</div></td>
          <td><span class="tag ${SEV_COLOR[e.severity]}">${SEV_LABEL[e.severity]}</span></td>
          <td>${e.owner ? esc(e.owner) : '<span class="muted">未指派</span>'}</td>
          <td><span class="tag ${EXC_COLOR[e.status]}">${EXC_LABEL[e.status]}</span>
            ${e.project_id ? '<span class="tag t-blu">已转改善</span>' : ''}</td>
          <td><div class="gap">
            ${canImprove
              ? `<button class="btn-sm btn-p" data-act="monitor.improveException"
                  data-id="${e.id}">转改善</button>` : ''}
            <button class="btn-sm" data-act="monitor.openException"
              data-id="${e.id}">${canEdit ? '处理' : '查看'}</button>
          </div></td>
        </tr>`;
      }).join('') || emptyRow(6, '没有符合条件的异常事件');

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

      const wl = d.workload || {
        period: '',
        totals: {
          demand_minutes: 0, available_minutes: 0, actual_minutes: 0, utilization: null,
        },
        standards: [], capacity: [], actual: [],
      };
      state.monitorWorkload = wl;
      const workloadPositions = [];
      const seenPosition = new Set();
      [...wl.standards, ...wl.actual, ...wl.capacity].forEach((row) => {
        if (!row.position_id || seenPosition.has(row.position_id)) return;
        seenPosition.add(row.position_id);
        workloadPositions.push(row);
      });
      workloadPositions.sort((a, b) =>
        String(a.position_name || '').localeCompare(String(b.position_name || ''), 'zh'));
      if (state.monitor.workloadPosition
        && !seenPosition.has(Number(state.monitor.workloadPosition))) {
        state.monitor.workloadPosition = '';
      }
      const workloadProcessId = state.cockpit.processId;
      const workloadPositionId = Number(state.monitor.workloadPosition) || null;
      const wlView = scopeWorkload(
        wl, state.cockpit.processId, state.monitor.workloadPosition);
      const hours = (minutes) => num((minutes || 0) / 60, 1);
      const periodValue = state.monitor.period
        || (wl.period ? wl.period.slice(0, 7) : '');
      const utilization = wlView.totals.utilization;
      const demandHint = workloadProcessId && workloadPositionId
        ? '本流程在这个岗位上的已验证标准'
        : workloadPositionId
          ? '本岗位已验证标准'
          : workloadProcessId
            ? '本流程已验证标准'
            : '仅已验证标准';
      const availableHint = workloadPositionId
        ? '这个岗位的整月可用，含其他流程'
        : workloadProcessId
          ? '这些岗位的整月可用，含其他流程'
          : '人数 × 工时 × 出勤 × 设备';
      const rateHint = workloadPositionId
        ? '筛出的需求 ÷ 这个岗位的整月可用'
        : workloadProcessId
          ? '本流程需求 ÷ 这些岗位的整月可用'
          : '标准需求 ÷ 可用产能';
      const workloadCards = `
        <div class="grid g4 stat-row">
          <div class="kpi stat"><div class="num">${hours(wlView.totals.demand_minutes)}<small>h</small></div>
            <div class="lab">标准需求</div><div class="trend">${demandHint}</div></div>
          <div class="kpi stat"><div class="num">${hours(wlView.totals.available_minutes)}<small>h</small></div>
            <div class="lab">可用产能</div><div class="trend">${availableHint}</div></div>
          <div class="kpi stat"><div class="num">${hours(wlView.totals.actual_minutes)}<small>h</small></div>
            <div class="lab">实际工时</div><div class="trend">来自任务工时记录</div></div>
          <div class="kpi stat"><div class="num">${utilization === null ? '—' : num(utilization * 100, 1)}<small>%</small></div>
            <div class="lab">理论负荷率</div><div class="trend">${rateHint}</div></div>
        </div>`;
      const standardRows = wlView.standards.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.activity_code || '')} ${
            esc(row.activity_name || '')}${
            !workloadProcessId && row.process_name
              ? ' · ' + esc(row.process_code || '') + ' ' + esc(row.process_name) : ''}</div></td>
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
        </tr>`).join('') || emptyRow(7, workloadPositionId
          ? '这个岗位还没有标准工时卡' : '还没有标准工时卡');
      const capacityRows = wlView.capacity.map((row) => `
        <tr>
          <td>${esc(row.org_unit_name || '—')}</td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${num(row.headcount, 1)}</td>
          <td>${hours(row.available_minutes)}</td>
          <td>${hours(row.demand_minutes)}</td>
          <td>${hours(row.gap_minutes)}</td>
          <td>${row.utilization === null ? '—' : num(row.utilization * 100, 1) + '%'}</td>
        </tr>`).join('') || emptyRow(7, '还没有产能记录');
      const actualRows = wlView.actual.map((row) => `
        <tr>
          <td>${esc(row.activity_code || '—')} ${esc(row.activity_name || '')}</td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${row.task_count}</td>
          <td>${hours(row.effort_minutes)}</td>
        </tr>`).join('') || emptyRow(4, '本期还没有实际工时记录');

      const stdByActivity = {};
      wlView.standards.filter((row) => row.status === 'VERIFIED').forEach((row) => {
        const key = row.activity_id || 0;
        const bucket = stdByActivity[key] || (stdByActivity[key] = {
          code: row.activity_code || '未关联活动',
          name: row.activity_name || '',
          demand: 0,
        });
        bucket.demand += row.demand_minutes || 0;
      });
      const actualByActivity = {};
      wlView.actual.forEach((row) => {
        const key = row.activity_id || 0;
        const bucket = actualByActivity[key] || (actualByActivity[key] = {
          code: row.activity_code || '未关联活动',
          name: row.activity_name || '',
          actual: 0,
        });
        bucket.actual += row.effort_minutes || 0;
      });
      const compareKeys = [...new Set([
        ...Object.keys(stdByActivity), ...Object.keys(actualByActivity),
      ])];
      const compareRows = compareKeys.map((key) => {
        const std = stdByActivity[key] || { code: actualByActivity[key].code, name: actualByActivity[key].name, demand: 0 };
        const act = actualByActivity[key] || { actual: 0 };
        const variance = act.actual - std.demand;
        const rate = std.demand ? act.actual / std.demand : null;
        return { ...std, actual: act.actual, variance, rate };
      }).sort((a, b) => (b.variance - a.variance));
      const compareHtml = compareRows.map((row) => `
        <tr>
          <td><b>${esc(row.code)}</b> ${esc(row.name)}</td>
          <td>${hours(row.demand)}</td>
          <td>${hours(row.actual)}</td>
          <td><span class="tag ${row.variance > 0 ? 't-red' : 't-grn'}">${
            row.variance > 0 ? '+' : ''}${hours(row.variance)}</span></td>
          <td>${row.rate === null ? '—' : num(row.rate * 100, 1) + '%'}</td>
        </tr>`).join('') || emptyRow(5, '本期没有可比较的工时数据');
      const bottlenecks = wlView.capacity.filter((row) => row.gap_minutes > 0);
      const bottleneckRows = bottlenecks.map((row) => `
        <tr class="is-risk">
          <td>${esc(row.org_unit_name || '—')}</td>
          <td>${esc(row.position_name || '—')}</td>
          <td>${hours(row.gap_minutes)}</td>
          <td>${row.utilization === null ? '—' : num(row.utilization * 100, 1) + '%'}</td>
        </tr>`).join('') || emptyRow(4, '已登记的岗位，需求都没有超过可用工时');

      const forecast = d.forecast;
      const forecastScoped = forecast
        ? forecast.rows.filter((row) =>
          !workloadPositionId || row.position_id === workloadPositionId)
        : [];
      const forecastShortCount = forecastScoped
        .filter((row) => row.gap_minutes < 0).length;
      const forecastRows = forecastScoped
        .filter((row) => row.gap_minutes < 0)
        .slice(0, 8)
        .map((row) => `
          <tr>
            <td class="tiny">${esc(row.period)}</td>
            <td>${esc(row.org_unit_name || '—')}</td>
            <td>${esc(row.position_name || '—')}</td>
            <td>${hours(row.demand_minutes)}</td>
            <td>${hours(row.available_minutes)}</td>
            <td><span class="tag t-red">${hours(-row.gap_minutes)}</span></td>
            <td>${row.utilization === null ? '—' : num(row.utilization * 100, 1) + '%'}</td>
          </tr>`).join('') || '<tr><td colspan="7" class="muted">未来 3 个月没有缺口</td></tr>';
      const balance = d.balance;
      const balanceSuggestions = (balance ? balance.suggestions : []).filter((row) =>
        !workloadPositionId
        || row.from_position_id === workloadPositionId
        || row.to_position_id === workloadPositionId);
      const balanceRows = balanceSuggestions.slice(0, 8).map((row) => `
        <tr>
          <td>${esc(row.from_org_unit_name || '—')} · ${esc(row.from_position_name || '—')}</td>
          <td>${esc(row.to_org_unit_name || '—')} · ${esc(row.to_position_name || '—')}</td>
          <td>${num(row.hours, 1)} h</td>
        </tr>`).join('') || '<tr><td colspan="3" class="muted">当前没有可调拨的余量</td></tr>';

      const mining = d.mining;
      const minuteCell = (value) => (value === null || value === undefined
        ? '—' : num(value, 1) + ' 分');
      const miningRows = (mining ? mining.variants : []).map((row) => `
        <tr>
          <td class="tiny">${(row.node_names || []).map(esc).join(' → ')}</td>
          <td>${esc(row.source_label || '实例')}</td>
          <td>${row.instance_count}</td>
          <td>${num(row.share_pct, 1)}%</td>
          <td>${minuteCell(row.avg_cycle_minutes)}</td>
          <td>${minuteCell(row.avg_actual_minutes)}</td>
          <td>${minuteCell(row.avg_wait_minutes)}</td>
        </tr>`).join('') || '<tr><td colspan="7" class="muted">还没有能排成路径的事例</td></tr>';
      const walk = modelWalk((d.model && d.model.nodes) || [], (d.model && d.model.edges) || []);
      const topVariant = mining && mining.variants && mining.variants[0];
      const conformance = topVariant && walk
        ? `<div class="tiny path-split">出现最多的路径占 ${num(topVariant.share_pct, 1)}%，${
          topVariant.instance_count} 个。</div>
          <div class="tiny">模型主走法：${walk.mainNames.map(esc).join(' → ')}</div>
          <div class="tiny">${pathCompareText(topVariant, walk.mainNames)}</div>`
        : (topVariant
          ? '<div class="tiny muted">这条流程还没有可对照的模型走法。</div>'
          : '');
      const handoffs = (mining && mining.handoffs) || [];
      const handoffHtml = handoffs.length
        ? `<div class="tiny path-split">步骤之间等得最久</div>
          ${handoffs.map((row) => `
            <div class="path-branch"><b>${esc(row.from_name)} → ${esc(row.to_name)}</b>
              <span>平均等待 ${num(row.avg_wait_minutes, 1)} 分 · ${row.case_count} 次</span></div>`).join('')}`
        : '<div class="tiny muted">还没有前后两步的完成时间，看不出步骤之间的等待。整单等待见下表「平均等待」，等于周期减去作业。</div>';
      const unsequenced = mining ? mining.unsequenced_instances || 0 : 0;
      const hiddenVariants = mining
        ? Math.max(0, (mining.variant_count || 0) - ((mining.variants || []).length))
        : 0;

      const boundaryNote = (state.workloadMeta && state.workloadMeta.boundary_note) || '';
      const workloadPane = `
        ${boundaryNote ? `<div class="note mb">${esc(boundaryNote)}</div>` : ''}
        ${workloadCards}
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">标准工时卡（${wlView.standards.length} 条）</h3>
              <div class="desc" style="margin:2px 0 0">标准工时 = 观测 × 评定系数 × (1 + 宽放率)；
                只有「已验证」进入产能口径</div></div>
            <div class="gap">
              <select class="sel sel-sm" data-act="monitor.workloadPosition" title="按岗位">
                <option value="">全部岗位</option>
                ${workloadPositions.map((row) =>
                  `<option value="${row.position_id}"${
                    workloadPositionId === row.position_id ? ' selected' : ''}>${
                    esc(row.position_name || '未命名岗位')}</option>`).join('')}
              </select>
              <input class="sel sel-sm" type="month" data-act="monitor.period" value="${periodValue}">
              ${canManage()
                ? '<button class="btn btn-p" data-act="monitor.newStandard">+ 标准工时</button>' : ''}
            </div>
          </div>
          <table class="tbl">
            <thead><tr><th>活动 / 标准</th><th>岗位</th><th>标准工时（分）</th>
              <th>月频次</th><th>需求（h/月）</th><th>状态 / 来源</th><th></th></tr></thead>
            <tbody>${standardRows}</tbody>
          </table>
        </div>
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">产能与负荷</h3>
              <div class="desc" style="margin:2px 0 0">可用工时 = 人数 × 人均工时 × 出勤率 × 设备可用率。缺口 = 需求 − 可用，正数表示不够。</div></div>
            ${canManage()
              ? '<button class="btn btn-p" data-act="monitor.newCapacity">+ 产能</button>' : ''}
          </div>
          <table class="tbl">
            <thead><tr><th>组织</th><th>岗位</th><th>人数</th><th>可用（h）</th>
              <th>需求（h）</th><th>缺口（h）</th><th>负荷率</th></tr></thead>
            <tbody>${capacityRows}</tbody>
          </table>
        </div>
        ${wlView.actual.length ? `
        <div class="card">
          <h3>实际工时（按活动）</h3>
          <div class="desc">来自任务工时记录；未关联活动的工时单独列示</div>
          <table class="tbl">
            <thead><tr><th>活动</th><th>岗位</th><th>任务数</th><th>实际（h）</th></tr></thead>
            <tbody>${actualRows}</tbody>
          </table>
        </div>` : ''}
        ${wlView.totals.actual_minutes > 0 ? `
        <div class="card">
          <div class="between mb">
            <h3 style="margin:0">标准 vs 实际（按活动）</h3>
            <span class="tag ${compareRows.some((row) => row.variance > 0) ? 't-yel' : 't-grn'}">
              超标准 ${compareRows.filter((row) => row.variance > 0).length} 个活动</span>
          </div>
          <div class="desc">只在本月已有任务工时时比较。差值为正表示实际超出已验证标准。</div>
          <table class="tbl">
            <thead><tr><th>活动</th><th>标准（h）</th><th>实际（h）</th>
              <th>差异（h）</th><th>实际/标准</th></tr></thead>
            <tbody>${compareHtml}</tbody>
          </table>
        </div>` : ''}
        ${wlView.capacity.length ? `
        <div class="card">
          <div class="between mb">
            <h3 style="margin:0">瓶颈岗位（${bottlenecks.length}）</h3>
            <span class="tag ${bottlenecks.length ? 't-red' : 't-grn'}">${
              bottlenecks.length ? '需求超过可用' : '未超过可用'}</span>
          </div>
          <div class="desc">只看已登记产能。缺口为正的岗位需要加人、加时，或接受派工建议。</div>
          <table class="tbl">
            <thead><tr><th>组织</th><th>岗位</th><th>缺口（h）</th><th>负荷率</th></tr></thead>
            <tbody>${bottleneckRows}</tbody>
          </table>
        </div>` : ''}
        ${!workloadProcessId && forecastScoped.length ? `
        <div class="card">
          <div class="between mb">
            <h3 style="margin:0">未来 3 个月缺口</h3>
            <span class="tag ${forecastShortCount ? 't-red' : 't-grn'}">
              ${forecastShortCount} 个岗位月不够</span>
          </div>
          <div class="desc">用本月已验证需求和已登记产能原样外推，不放大需求。缺口 = 需求 − 可用。</div>
          ${forecastRows.trim() && !forecastRows.startsWith('<tr><td colspan') ? `
          <table class="tbl">
            <thead><tr><th>月份</th><th>组织</th><th>岗位</th><th>需求（h）</th>
              <th>可用（h）</th><th>缺口（h）</th><th>负荷率</th></tr></thead>
            <tbody>${forecastRows}</tbody>
          </table>` : '<div class="muted">按当前产能外推，未来 3 个月需求都没有超过可用工时。</div>'}
        </div>` : ''}
        ${!workloadProcessId && balanceSuggestions.length ? `
        <div class="card">
          <div class="between mb">
            <h3 style="margin:0">派工均衡建议</h3>
            <span class="tag t-yel">${balanceSuggestions.length} 条</span>
          </div>
          <div class="desc">把有余量的岗位小时调到不够的岗位。只给建议，不自动改派。</div>
          <table class="tbl">
            <thead><tr><th>从</th><th>到</th><th>可调拨</th></tr></thead>
            <tbody>${balanceRows}</tbody>
          </table>
        </div>` : ''}`;

      const miningPane = state.cockpit.processId ? `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">流程挖掘</h3>
              <div class="desc">任务按完成时间排成路径。活动名称对上模型节点名的手记日志，并进同一条走法。</div></div>
          </div>
          <div class="tiny">纳入路径 ${mining ? mining.instance_total : 0} 个 ·
            变体 ${mining ? mining.variant_count : 0} 种</div>
          ${unsequenced
            ? `<div class="tiny muted">另有 ${unsequenced} 条实例还没有已完成任务，不在下表。</div>`
            : ''}
          ${conformance}
          ${handoffHtml}
          <table class="tbl">
            <thead><tr><th>路径变体</th><th>来源</th><th>次数</th><th>占比</th>
              <th>平均周期</th><th>平均作业</th><th>平均等待</th></tr></thead>
            <tbody>${miningRows}</tbody>
          </table>
          ${hiddenVariants
            ? `<div class="tiny muted">还有 ${hiddenVariants} 种变体没有列在这张表里。</div>`
            : ''}
        </div>` : '<div class="card"><p class="tiny muted">先在上面选一条流程。</p></div>';

      const kpiSummary = `
        <div class="grid g4 stat-row">${dimCards}</div>
        <div class="card">
          <h3>${metricHelp('overall_trend', '整体达成率趋势')}</h3>
          <div class="desc">按月先对每个维度求平均，再对维度求平均。100% 是达标。</div>
          <canvas id="overallTrend" class="trend-canvas" width="440" height="180"></canvas>
        </div>`;

      const kindOptions = Object.entries(kindLabels).map(([value, label]) =>
        `<option value="${value}"${state.monitor.kind === value ? ' selected' : ''}>${
          esc(label)}</option>`).join('');
      const kindStats = (d.radar.by_kind || []).map((k) =>
        `<span class="tag ${k.red ? 't-red' : k.yellow ? 't-yel' : 't-gry'}">${
          esc(k.label)} ${k.kpi_count} · 红 ${k.red} / 黄 ${k.yellow} / 绿 ${k.green} / 灰 ${k.gray}</span>`).join('');
      const kpiPane = `
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">KPI 明细（${visibleSeries.length} 项）</h3>
              <div class="desc" style="margin:2px 0 0">按定义卡判定红/黄/绿；越小越好的指标，达成率取目标与实际的比值</div></div>
            <div class="gap">
              ${canManage() ? '<button class="btn btn-p" data-act="monitor.newKpi">+ 新建 KPI</button>' : ''}
              <select class="sel sel-sm" data-act="monitor.kind">
                <option value="">全部类型</option>${kindOptions}
              </select>
            </div>
          </div>
          <div class="gap mb">${kindStats}</div>
          <table class="tbl">
            <thead><tr><th>指标</th><th>维度</th><th>${metricHelp('latest_value', '当前值')}</th><th>${metricHelp('target_value', '目标')}</th>
              <th>${metricHelp('achievement_rate', '达成率')}</th><th>红/黄/绿</th><th>${metricHelp('kpi_trend', '环比')}</th><th>${metricHelp('kpi_series', '6 个月走势')}</th>${canManage() ? '<th></th>' : ''}</tr></thead>
            <tbody>${kpiRows}</tbody>
          </table>
        </div>`;

      const suggestionRows = (state.monitor.suggestions || []).map((row, index) => `
        <div class="between mb">
          <div><b>${esc(row.title)}</b><div class="tiny">${esc(row.description)}</div></div>
          ${canWrite()
            ? `<button class="btn btn-g" data-act="monitor.confirmSuggestion" data-index="${index}">确认登记</button>`
            : ''}
        </div>`).join('');
      const excPane = `
        ${(state.monitor.suggestions || []).length ? `
        <div class="card">
          <h3>待确认</h3>
          <div class="desc">红黄指标和超时待办只在这里列出。点确认后才写入台账。</div>
          ${suggestionRows}
        </div>` : ''}
        <div class="card">
          <div class="between mb">
            <div><h3 style="margin:0">异常事件台账</h3>
              <div class="desc" style="margin:2px 0 0">登记后在同一行处理、解决、关闭</div></div>
            <div class="gap">
              ${canWrite() ? '<button class="btn btn-p" data-act="monitor.newException">+ 登记异常</button>' : ''}
              <select class="sel" data-act="monitor.status">
                <option value="">全部状态</option>
                ${['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'].map((v) =>
                  '<option value="' + v + '"' + (state.monitor.status === v ? ' selected' : '') + '>' +
                  EXC_LABEL[v] + '</option>').join('')}
              </select>
            </div>
          </div>
          <table class="tbl">
            <thead><tr><th>发现时间</th><th>异常</th><th>级别</th><th>责任人</th><th>状态</th><th></th></tr></thead>
            <tbody>${excRows}</tbody>
          </table>
        </div>`;

      const headMain = tab === 'analysis'
        ? `<div><h2>流程分析<span class="module-badge">现状 · 瓶颈 · 根因 · 价值流 · 规则 · 基线</span></h2>
            <div class="desc">左边点一项，中间只看这一项。右边是这条流程的实例和测算。</div></div>`
        : tab === 'kpi'
          ? `<div><h2>KPI<span class="module-badge">当前值 · 目标 · 红黄绿</span></h2>
              <div class="desc">${metricHelp('overall_achievement', '综合达成率')} <b>${num(d.radar.overall_achievement, 1)}%</b></div></div>`
          : tab === 'exceptions'
            ? `<div><h2>异常<span class="module-badge">未闭环 · 超期</span></h2>
                <div class="desc">未闭环 ${excOpen} 件 · 超期 ${excOverdue} 件</div></div>`
            : tab === 'workload'
              ? `<div><h2>工作量<span class="module-badge">标准需求 · 可用产能 · 负荷率</span></h2>
                  <div class="desc">按流程或岗位看标准需求。岗位可用工时是整月的，一条流程只用其中一部分。</div></div>`
              : `<div><h2>运营驾驶舱<span class="module-badge">KPI · 异常 · 工作量 · 过程挖掘</span></h2>
              <div class="desc">${metricHelp('overall_achievement', '综合达成率')} <b>${num(d.radar.overall_achievement, 1)}%</b>
                · 未闭环 ${s.open + s.in_progress} 件 · 超期 ${s.overdue} 件</div></div>`;
      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            ${headMain}
            ${cockpitProcessSelect(d.flowList)}
          </div>
          <div class="mt">${cockpitTabBar(tab)}</div>
          ${toolMountHtml(d.tools, monitorToolHost(tab), state.cockpit.processId)}
        </div>
        ${tab === 'analysis' ? workbenchHtml(d.workbench,'ANALYSIS','monitor')+analysisHtml(d)
          : tab === 'kpi' ? `${kpiSummary}${kpiPane}`
          : tab === 'exceptions' ? excPane
            : tab === 'workload' ? workloadPane
              : tab === 'mining' ? miningPane
                : `${kpiSummary}${kpiPane}`}`;

      if (tab === 'kpi' || !['exceptions', 'workload', 'mining', 'analysis'].includes(tab)) {
        drawOverallTrend(trend, periods);
      }
      d.radar.series.forEach((series) =>
        drawSpark(series.kpi_id, series.points.map((p) => p.value), series.direction));
    });
};

function monitorToolHost(tab) {
  if (tab === 'analysis') return 'analysis';
  if (tab === 'mining') return 'mining';
  if (tab === 'exceptions' || tab === 'workload') return '';
  return 'kpi';
}

function setMonitorTab(tab) {
  state.monitor.tab = tab === 'overview' ? 'kpi' : tab;
  const params = { tab: state.monitor.tab };
  if (state.cockpit.processId) params.process = state.cockpit.processId;
  setUrlState('monitor', params, { push: false });
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

function setWorkloadPosition(positionId) {
  state.monitor.workloadPosition = positionId || '';
  state.monitor.tab = 'workload';
  RENDERERS.monitor();
}

/** 选中流程或岗位时只收对应需求和实际。可用工时仍是岗位整月。 */
function scopeWorkload(wl, processValue, positionValue) {
  const processId = Number(processValue) || null;
  const positionId = Number(positionValue) || null;
  if (!processId && !positionId) return wl;
  let standards = wl.standards;
  let actual = wl.actual;
  if (processId) {
    standards = standards.filter((row) => row.process_id === processId);
    actual = actual.filter((row) => row.process_id === processId);
  }
  if (positionId) {
    standards = standards.filter((row) => row.position_id === positionId);
    actual = actual.filter((row) => row.position_id === positionId);
  }
  let capacity = wl.capacity;
  if (positionId) {
    capacity = capacity.filter((row) => row.position_id === positionId);
  }
  capacity = capacity.map((row) => {
    const demand = standards
      .filter((std) => std.included
        && std.position_id === row.position_id
        && std.org_unit_id === row.org_unit_id)
      .reduce((sum, std) => sum + Number(std.demand_minutes || 0), 0);
    const available = Number(row.available_minutes || 0);
    return {
      ...row,
      demand_minutes: Math.round(demand * 100) / 100,
      gap_minutes: Math.round((demand - available) * 100) / 100,
      utilization: available > 0 ? demand / available : null,
    };
  });
  if (processId) {
    capacity = capacity.filter((row) => standards.some((std) =>
      std.position_id === row.position_id && std.org_unit_id === row.org_unit_id));
  }
  const demandMinutes = standards
    .filter((row) => row.included)
    .reduce((sum, row) => sum + Number(row.demand_minutes || 0), 0);
  const availableMinutes = capacity
    .reduce((sum, row) => sum + Number(row.available_minutes || 0), 0);
  const actualMinutes = actual
    .reduce((sum, row) => sum + Number(row.effort_minutes || 0), 0);
  return {
    ...wl,
    standards,
    actual,
    capacity,
    totals: {
      demand_minutes: demandMinutes,
      available_minutes: availableMinutes,
      actual_minutes: actualMinutes,
      utilization: availableMinutes > 0 ? demandMinutes / availableMinutes : null,
    },
  };
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

let exceptionForm = null;
async function openException(id) {
  const processId=state.cockpit.processId;
  const originView=state.view;
  const gen = openModal('加载中…', skeleton(4));
  try {
    const [e,users] = await Promise.all([GET('/monitor/exceptions/' + id),GET('/execution/assignees')]);
    if (!modalAlive(gen)) return;
    if(state.view!==originView || state.cockpit.processId!==processId){closeModal();return;}
    state.currentException = e;
    const canEdit = canManage()
      || (role() === 'OWNER' && AUTH.user && e.owner_user_id === AUTH.user.id);
    const canImprove = canEdit
      && !e.project_id
      && (e.status === 'OPEN' || e.status === 'IN_PROGRESS');
    const manager = canManage();
    const statusOpts = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'].map((v) =>
      '<option value="' + v + '"' + (e.status === v ? ' selected' : '') + '>' + EXC_LABEL[v] + '</option>').join('');
    const formGen = openModal(e.title, `
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
      <details${e.resolution ? ' open' : ''}><summary>处置与效果核验约定</summary><p class="note">措施执行不等于有效；保存改动清原核验，关闭须指定本人确认。</p>
      <div class="field"><label>指定非编辑者核验</label><select id="exReviewer"${canEdit?'':' disabled'}><option value="">请选择</option>${users.filter(u=>u.id!==AUTH.user?.id || u.id===e.resolution?.reviewer_user_id).map(u=>`<option value="${u.id}"${u.id===e.resolution?.reviewer_user_id?' selected':''}>${esc(u.display_name)}</option>`).join('')}</select></div>
      ${[['Decision','处置选择','decision'],['ActionRef','原动作引用','action_ref'],['Evidence','执行依据','evidence'],['Expected','预期效果','expected_result']].map(([id,label,key])=>`<div class="field"><label>${label}</label><textarea id="ex${id}"${canEdit?'':' readonly'}>${esc(e.resolution?.[key] || '')}</textarea></div>`).join('')}
      <div class="field"><label>复核日期</label><input id="exReviewDue" type="date" value="${esc(e.resolution?.review_due || '')}"${canEdit?'':' readonly'}></div></details>
      ${e.resolution?.review ? `<p class="note">${esc(e.resolution.review.name)} · ${esc(e.resolution.review.evidence)} · ${esc(e.resolution.review.result)}</p>` : ''}
      ${canWrite() && e.resolution?.reviewer_user_id===AUTH.user?.id ? '<div class="field"><label>本人核验依据</label><textarea id="exReviewEvidence"></textarea></div><div class="field"><label>实际核验结果</label><textarea id="exReviewResult"></textarea></div>' : ''}
      ${e.resolved_at ? '<div class="note">解决时间：' + esc(dtShort(e.resolved_at)) +
        (e.closed_at ? ' · 关闭时间：' + esc(dtShort(e.closed_at)) : '') + '</div>' : ''}
      ${canEdit ? '' : '<div class="note">只读：仅流程管理科、系统管理员或该异常的责任人可以处理。</div>'}
      ${e.project_id ? '<div class="note">已关联改善项目。</div>' : ''}`,
      `${e.project_id
        ? `<button class="btn btn-g" data-act="monitor.openProject"
            data-id="${e.project_id}">查看改善项目</button>` : ''}
       <button class="btn btn-g" data-act="monitor.close">${canEdit ? '取消' : '关闭'}</button>
       ${canImprove ? `<button class="btn btn-g" data-act="monitor.improveException"
         data-id="${e.id}">转改善</button>` : ''}
       ${canEdit ? `<button class="btn btn-p" data-act="monitor.saveException" data-id="${e.id}">保存</button>` : ''}
       ${canWrite() && e.resolution?.reviewer_user_id===AUTH.user?.id && e.status==='RESOLVED' ? '<button class="btn btn-p" data-act="monitor.reviewException">本人确认效果并关闭</button><button class="btn btn-g" data-act="monitor.reviewException" data-decision="RETURN">退回补证</button>' : ''}`);
    exceptionForm={id:e.id,revision:e.revision,gen:formGen,processId,busy:false};
  } catch (err) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(err.message) + '</div></div>');
  }
}

on('monitor.reviewException',async ({decision})=>{
  const c=exceptionForm;
  if(!c || !modalAlive(c.gen) || state.view!=='monitor' || state.cockpit.processId!==c.processId || c.busy)return;
  c.busy=true;
  try {await POST('/monitor/exceptions/'+c.id+'/review',{expected_revision:c.revision,decision:decision || 'ACCEPT',evidence:document.getElementById('exReviewEvidence').value,result:document.getElementById('exReviewResult').value});if(modalAlive(c.gen))closeModal();toast('本人核验已记录');if(state.view==='monitor')RENDERERS.monitor();}catch(e){toast(e.message,true);}finally{c.busy=false;}
});
async function saveException(id) {
  const c=exceptionForm;
  if(!c || c.id!==id || !modalAlive(c.gen) || state.view!=='monitor' || state.cockpit.processId!==c.processId || c.busy)return toast('上下文已变化，请重新打开异常',true);
  const g = (x) => document.getElementById(x).value;
  const reviewer=Number(g('exReviewer'));
  c.busy=true;
  try {
    await PATCH('/monitor/exceptions/' + id, {
      expected_revision:c.revision,
      ...(reviewer?{resolution:{reviewer_user_id:reviewer,decision:g('exDecision'),action_ref:g('exActionRef'),evidence:g('exEvidence'),expected_result:g('exExpected'),review_due:g('exReviewDue')}}:{}),
      owner: g('exOwner') || null,
      status: g('exStatus'),
      root_cause: g('exCause') || null,
      action_taken: g('exAction') || null,
    });
    if(modalAlive(c.gen))closeModal();
    toast('异常事件已更新');
    if(state.view==='monitor' && state.cockpit.processId===c.processId)RENDERERS.monitor();
  } catch (e) {
    toast(e.message, true);
  } finally {c.busy=false;}
}

/* -------------------------------------------------- 异常 / KPI 的写入口 */

async function newExceptionModal(prefill) {
  const suggested = prefill || {};
  openModal('登记异常事件', `
    <div class="field"><label>异常标题 *</label>
      <input id="neTitle" value="${esc(suggested.title || '')}" placeholder="如：采购需求审批连续超时"></div>
    <div class="field"><label>异常描述</label>
      <textarea id="neDesc" placeholder="现象、影响范围、首次发现时间">${esc(suggested.description || '')}</textarea></div>
    <input id="neKpi" type="hidden" value="${suggested.kpi_id || ''}">
    <input id="neInstance" type="hidden" value="${suggested.instance_id || ''}">
    <div class="row3">
      <div class="field"><label>严重度</label>
        <select id="neSeverity">
          <option value="LOW">低</option><option value="MEDIUM"${
            !suggested.severity || suggested.severity === 'MEDIUM' ? ' selected' : ''}>中</option>
          <option value="HIGH"${suggested.severity === 'HIGH' ? ' selected' : ''}>高</option>
          <option value="CRITICAL"${suggested.severity === 'CRITICAL' ? ' selected' : ''}>紧急</option>
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
      if (suggested.process_id === r.id) o.selected = true;
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
      source_kpi_id: val('neKpi') ? Number(val('neKpi')) : null,
      source_instance_id: val('neInstance') ? Number(val('neInstance')) : null,
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
let kpiForm = null;
let kpiLoad = 0;

async function editKpiModal(kpiId) {
  const request=++kpiLoad,processId=state.cockpit.processId;
  const gen=openModal('加载中…',skeleton(3));
  try {
    const kpi = await GET('/monitor/kpis/' + kpiId);
    if(request!==kpiLoad || !modalAlive(gen) || state.view!=='monitor' || state.cockpit.processId!==processId)return;
    newKpiModal(kpi);
  } catch (e) {
    toast(e.message, true);
  }
}

function newKpiModal(kpi = null) {
  ++kpiLoad;
  editingKpi = kpi;
  const meta = state.monitorMeta
    || { kind_labels: {}, frequency_labels: {}, dimension_labels: {} };
  const value = (key) => (kpi && kpi[key] !== null && kpi[key] !== undefined ? kpi[key] : '');
  const options = (labels, selected) => Object.entries(labels || {}).map(([code, label]) =>
    `<option value="${esc(code)}"${code === selected ? ' selected' : ''}>${esc(label)}</option>`)
    .join('');
  const numValue = (key) => (kpi && kpi[key] !== null && kpi[key] !== undefined
    ? kpi[key] : '');

  const gen=openModal(kpi ? '编辑 KPI 定义卡 · ' + kpi.code : '新建 KPI 定义卡', `
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
    <div class="row2">
      <div class="field"><label>数据流</label>
        <select id="nkFlow"><option value="">不从台账选</option></select>
        <div class="hint">选定后，来源系统跟这条数据流走。</div></div>
      <div class="field"><label>入站钩子</label>
        <select id="nkHook"><option value="">不指定</option></select>
        <div class="hint">时长并不决定取数，须显式约定来源；启用钩子只证明入口配置，不证明样本可信。补录仍标人工待核实。</div></div>
    </div>
    <div class="field"><label>显式测量来源</label><select id="nkMeasureSource">${options(meta.measurement_labels, kpi?.measurement?.source_kind || 'UNKNOWN')}</select><div class="hint">单位不决定取数。实例仅支持UTC自然历时月均，不支持等待/投入/分位数；质量另核。</div></div>
    <div class="row2"><div class="field"><label>最小样本数</label><input id="nkMinSamples" type="number" min="1" value="${kpi?.measurement?.minimum_samples || 3}"></div><div class="field"><label>窗口结束后有效天数</label><input id="nkFreshness" type="number" min="1" value="${kpi?.measurement?.freshness_days || 45}"></div></div>
    <div class="field"><label>为何测</label><textarea id="nkPurpose">${esc(kpi?.measurement?.purpose || '')}</textarea></div><div class="field"><label>偏差由谁如何响应</label><textarea id="nkResponse">${esc(kpi?.measurement?.response_note || '')}</textarea></div>
    <div class="row2">
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

  const context={gen,processId:state.cockpit.processId,id:kpi?.id || null,busy:false};
  kpiForm=context;
  Promise.all([
    GET('/process-map/flat'),
    GET('/execution/assignees'),
    GET('/data-governance/flows?active_only=true').catch(() => []),
    GET('/integrations/inbound-hooks').catch(() => []),
  ])
    .then(([rows, users, flows, hooks]) => {
      if(kpiForm!==context || !modalAlive(gen) || state.view!=='monitor' || state.cockpit.processId!==context.processId)return;
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
      const flowSel = document.getElementById('nkFlow');
      if (flowSel) {
        (flows || []).forEach((flow) => {
          const o = document.createElement('option');
          o.value = String(flow.id);
          o.textContent = flow.code + ' ' + flow.name
            + (flow.source_system ? ' · ' + flow.source_system : '');
          o.selected = kpi && kpi.data_flow_id === flow.id;
          flowSel.appendChild(o);
        });
      }
      const hookSel = document.getElementById('nkHook');
      if (hookSel) {
        (hooks || []).filter((hook) => hook.is_active
          && (hook.actions || []).includes('record_kpi')).forEach((hook) => {
          const o = document.createElement('option');
          o.value = String(hook.id);
          o.textContent = hook.code + ' ' + hook.name;
          o.selected = kpi && kpi.inbound_webhook_id === hook.id;
          hookSel.appendChild(o);
        });
      }
    })
    .catch(() => {});
}

async function submitKpi(kpiId) {
  const c=kpiForm;
  if(!c || c.id!==kpiId || !modalAlive(c.gen) || state.view!=='monitor' || state.cockpit.processId!==c.processId || c.busy)return toast('指标上下文已变化，请重新打开',true);
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
    data_flow_id: val('nkFlow') ? Number(val('nkFlow')) : null,
    inbound_webhook_id: val('nkHook') ? Number(val('nkHook')) : null,
    description: textOrNull('nkDesc'),
    measurement: val('nkMeasureSource')==='UNKNOWN' ? null : {source_kind:val('nkMeasureSource'),event:'instance.completed',aggregation:'MEAN',timezone:'UTC',calendar:'ELAPSED',minimum_samples:Number(val('nkMinSamples')),freshness_days:Number(val('nkFreshness')),purpose:val('nkPurpose'),response_note:val('nkResponse')},
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

  c.busy=true;
  try {
    if (kpiId) {
      await PATCH('/monitor/kpis/' + kpiId, payload);
      toast('KPI 定义已更新');
    } else {
      await POST('/monitor/kpis', payload);
      toast('KPI 已创建');
    }
    if(kpiForm===c && modalAlive(c.gen)){editingKpi=null;closeModal();}
    if(state.view==='monitor' && state.cockpit.processId===c.processId && kpiForm===c){state.monitor.tab='kpi';RENDERERS.monitor();}
  } catch (e) {
    toast(e.message, true);
  } finally {c.busy=false;}
}

function addKpiRecordModal(kpiId, kpiName) {
  const today = new Date();
  const ym = today.getFullYear() + '-' + _p2(today.getMonth() + 1) + '-01';
  openModal('补录数据点 · ' + kpiName, `
    <div class="row2">
      <div class="field"><label>期间 *</label>
        <input id="nrPeriod" type="date" value="${ym}">
        <div class="hint">同一期间重复提交会覆盖，不会产生重复数据</div></div>
      <div class="field"><label>数值 *</label><input id="nrValue" type="number" step="0.01"></div>
    </div>
    <div class="field"><label>备注</label><input id="nrNote" placeholder="如：口径调整 / 异常月份"></div>
    <div class="note">补录只改正已有的数，不作为正式来源。</div>`,
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
    go('projects', { params: { project: draft.id }, push: true });
  } catch (e) {
    toast(e.message, true);
  }
}

async function createExceptionImprovement(exceptionId) {
  try {
    const draft = await POST('/monitor/exceptions/' + exceptionId + '/improvement-draft');
    toast('已生成改善项目 ' + draft.code);
    closeModal();
    go('projects', { params: { project: draft.id }, push: true });
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
    <div class="field"><label>L5 任务（可选）</label>
      <select id="wsTask"><option value="">不绑定任务</option></select></div>
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
      const taskSel = document.getElementById('wsTask');
      const loadTasks = async (activityId) => {
        if (!taskSel) return;
        taskSel.innerHTML = '<option value="">不绑定任务</option>';
        if (!activityId) return;
        try {
          const rows = await GET('/process-tasks?activity_id=' + activityId);
          rows.forEach((row) => {
            const o = document.createElement('option');
            o.value = String(row.id);
            o.textContent = row.code + ' ' + row.name;
            taskSel.appendChild(o);
          });
        } catch (e) {
          /* 任务目录不可用时保持不绑定 */
        }
      };
      if (actSel) {
        actSel.addEventListener('change', () => loadTasks(actSel.value));
        if (actSel.value) loadTasks(actSel.value);
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
      task_id: val('wsTask') ? Number(val('wsTask')) : null,
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
