/* 视图：流程卡
 *
 * 一个 L3/L4 流程对象的 360 视图：战略、权责、制度、模型、工时、KPI、
 * 变更、改善、成熟度、L5 任务与治理待办。
 *
 * 十层层状态、退出门、层内任务和问题由「十层单页」维护；流程卡只展示
 * 当前试点层摘要并提供跳转，不重复实现第二套十层门禁。
 */

import { esc, num, emptyRow } from '../core/format.js';
import { toast, openModal, closeModal, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS, urlParams, setUrlState } from '../core/router.js';
import { GET, POST } from '../core/api.js';
import { canManage } from '../core/auth.js';
import { actions as appActions } from '../core/actions.js';

on('process_card.select', (_data, el) => {
  state.processCard.processId = Number(el.value) || null;
  setUrlState('process_card', {
    process: state.processCard.processId || '',
  }, { push: true });
  RENDERERS.process_card();
});
on('process_card.go', ({ view }) => go(view));
on('process_card.pilot', ({ path, layer }) => {
  go('pilot', { params: { path: Number(path), layer: Number(layer) }, push: true });
});
on('process_card.goPilot', ({ process }) => {
  go('pilot', { params: { process: Number(process) }, push: true });
});
on('process_card.designer', () => {
  state.designer.tab = 'model';
  appActions['designer.open'](state.processCard.processId);
});
on('process_card.raci', () => {
  state.designer.tab = 'raci';
  appActions['designer.open'](state.processCard.processId);
});
on('process_card.changes', () => {
  state.designer.tab = 'change';
  appActions['designer.open'](state.processCard.processId);
});
on('process_card.workload', () => {
  state.monitor.tab = 'workload';
  go('monitor');
});
on('process_card.newMaturity', () => openMaturityModal());
on('process_card.submitMaturity', () => submitMaturity());
on('process_card.newTask', () => openTaskModal());
on('process_card.submitTask', () => submitTask());
on('process_card.findings', () => openFindingsModal());

const STATUS_TONE = { RED: 't-red', YELLOW: 't-yel', GREEN: 't-grn', GRAY: 't-gry' };
const SEVERITY_LABELS = { HIGH: '高', MEDIUM: '中', LOW: '低' };

const renderProcessCard = () => {
  renderAsync(
    'process_card',
    async () => {
      const params = urlParams();
      const processes = (await GET('/process-map/flat')).filter(
        (row) => row.level === 3 || row.level === 4,
      );
      let processId = Number(params.process) || state.processCard.processId;
      if (!processId || !processes.some((row) => row.id === processId)) {
        const preferred = processes.find((row) => row.level === 3) || processes[0];
        processId = preferred ? preferred.id : null;
      }
      state.processCard.processId = processId;
      // 把默认选中的流程也写进 URL，分享/刷新后落到同一条流程
      setUrlState('process_card', { process: processId || '' }, { push: false });
      if (!processId) {
        return { processes, card: null };
      }
      const [card, assessments, coverage, paths] = await Promise.all([
        GET('/process-card/' + processId),
        GET('/maturity/assessments?process_id=' + processId),
        canManage() ? GET('/maturity/coverage').catch(() => null) : Promise.resolve(null),
        GET('/pilot/paths').catch(() => []),
      ]);
      const tasks = await GET(
        card.process.level === 4
          ? '/process-tasks?activity_id=' + processId
          : '/process-tasks?process_id=' + processId,
      ).catch(() => []);
      state.processCard.level = card.process.level;
      const pilot = (paths || []).find((row) => row.process_id === processId) || null;
      return { processes, card, assessments, coverage, tasks, pilot };
    },
    (d) => {
      const options = d.processes.map((row) =>
        `<option value="${row.id}"${row.id === state.processCard.processId ? ' selected' : ''}>${
          esc(row.code)} · ${esc(row.name)}</option>`).join('');
      if (!d.card) {
        viewEl().innerHTML = `<div class="card page-head">
          <div class="between"><h2>流程卡</h2>
          <select class="sel sel-sm" data-act="process_card.select">
            <option value="">请选择流程</option>${options}</select></div>
          <div class="empty">还没有 L3/L4 流程，请先在流程地图中建立架构。</div></div>`;
        return;
      }
      const c = d.card;
      state.processCard.data = c;
      state.processCard.pilot = d.pilot;
      const assessments = d.assessments || [];
      const tasks = d.tasks || [];
      const chain = c.chain.map((item) =>
        `<span class="tiny">L${item.level} ${esc(item.code)} ${esc(item.name)}</span>`).join(' › ');
      const covRow = d.coverage
        ? (d.coverage.rows || []).find((row) => row.process_id === state.processCard.processId)
        : null;
      const coverageHtml = covRow
        ? `<div class="tiny">L4 ${covRow.l4_total} 个 · Owner ${
          num(covRow.owner_coverage_pct, 0)}% · 制度 ${
          num(covRow.document_coverage_pct, 0)}% · KPI ${
          num(covRow.kpi_coverage_pct, 0)}%</div>`
        : '';

      const objectiveRows = c.objectives.map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)} · ${row.year}</div></span>
          <span class="tag t-blu">${row.target_value === null ? '—' : num(row.target_value, 2)}
            ${esc(row.unit || '')}</span>
        </div>`).join('');
      const raciRows = c.raci.map((matter) => `
        <div class="between bpmn-node-row">
          <span>${esc(matter.matter)}
            ${matter.has_accountable ? '<span class="tag t-grn">A 已明确</span>'
              : '<span class="tag t-red">缺少 A</span>'}</span>
          <span class="tiny">${matter.entries.map((entry) =>
            `${esc(entry.raci)} ${esc(entry.role_name || '—')}`).join(' · ')}</span>
        </div>`).join('');
      const documentRows = c.documents.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.category_label || '')}</div></span>
          <span class="tag t-grn">${esc(row.version_label || '—')}</span>
        </div>`).join('');
      const kpiRows = c.kpis.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td>${row.latest_value === null ? '—' : num(row.latest_value, 2)}
            → ${row.target_value === null ? '—' : num(row.target_value, 2)} ${esc(row.unit || '')}</td>
          <td><span class="tag ${STATUS_TONE[row.status] || 't-gry'}">${
            esc(row.status_label || row.status || '—')}</span></td>
        </tr>`).join('');
      const changeRows = c.changes.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.impact_level_label || '')}</div></span>
          <span class="tag t-yel">${esc(row.status_label || '')}</span>
        </div>`).join('');
      const improvementRows = c.improvements.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.name)}<div class="tiny">${esc(row.code)} · ${esc(row.source_label || '')}</div></span>
          <span class="tag t-blu">${esc(row.status_label || '')} · ${num(row.progress, 0)}%</span>
        </div>`).join('');
      const maturityRows = assessments.slice(0, 8).map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.dimension_label || row.dimension)}</b>
            <div class="tiny">${esc(row.assessed_by || '—')} · ${esc(row.assessed_at || '')}</div></span>
          <span><span class="tag ${row.level >= 4 ? 't-grn' : row.level >= 2 ? 't-yel' : 't-red'}">
            L${row.level}</span></span>
        </div>`).join('');
      const taskRows = tasks.slice(0, 12).map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.code)} ${esc(row.name)}</b>
            <div class="tiny">${esc(row.activity_code || '')} ${esc(row.position_name || '未绑岗位')}
              ${row.frequency ? ' · ' + esc(row.frequency) : ''}</div></span>
          <span class="tag ${row.standard_minutes ? 't-grn' : 't-gry'}">${
            row.standard_minutes ? num(row.standard_minutes, 1) + ' 分' : '待补工时'}</span>
        </div>`).join('');
      const findingRows = c.findings.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.type_label || row.type)}</div></span>
          <span class="tag ${row.severity === 'HIGH' ? 't-red' : 't-yel'}">${
            esc(SEVERITY_LABELS[row.severity] || row.severity || '—')}</span>
        </div>`).join('') || '<div class="tiny muted">没有未闭环治理待办</div>';

      const canDesign = c.readiness.strategy && c.readiness.raci && c.readiness.policy;
      const pilot = d.pilot;
      const readyCount = Object.values(c.readiness || {}).filter(Boolean).length;
      const readyTotal = Object.keys(c.readiness || {}).length;
      const moduleCard = (title, count, action, body, guide) => `
        <div class="card pc-module">
          <div class="between mb"><h3 style="margin:0">${title}${
            count === null ? '' : `（${count}）`}</h3>${action || ''}</div>
          ${guide ? `<div class="pc-empty">${guide}</div>` : ''}
          ${body || ''}
        </div>`;
      const group = (title, cards) => `
        <section class="pc-group">
          <div class="pc-group-hd">${title}</div>
          <div class="grid g2">${cards.join('')}</div>
        </section>`;
      const modelAction = canDesign
        ? '<button class="btn-sm" data-act="process_card.designer">打开设计器</button>'
        : '<button class="btn-sm" disabled title="建议先完成战略、权责、制度">打开设计器</button>';
      const modelGuide = c.readiness.model
        ? ''
        : (canDesign
          ? '模型还未发布 → 打开设计器完成建模并发布'
          : '先完成战略、权责、制度，再打开设计器建模');
      const pilotHtml = pilot
        ? `<section class="card pc-pilot">
            <div class="between">
              <div><h3>试点落地 · 第 ${pilot.current_layer} 层 ${
                esc(pilot.current_layer_title || '')}</h3>
                <div class="desc">${esc(pilot.name)} · ${esc(pilot.status_label || '')}
                  · 进度 ${num(pilot.progress, 0)}%</div></div>
              <button class="btn btn-p" data-act="process_card.pilot"
                data-path="${pilot.id}" data-layer="${pilot.current_layer}">进入十层执行</button>
            </div>
            <div class="pipe"><i class="fill-brand" style="width:${
              Math.max(0, Math.min(100, Number(pilot.progress) || 0))}%"></i></div>
          </section>`
        : `<section class="card pc-pilot">
            <div class="between">
              <div><h3>试点落地</h3>
                <div class="desc">这条流程还没有试点路径。十层执行的层状态、退出门、任务和问题
                  都在「十层单页」维护。</div></div>
              <button class="btn btn-g" data-act="process_card.goPilot"
                data-process="${c.process.id}">去十层单页</button>
            </div>
          </section>`;
      const strategyCard = moduleCard(
        '战略承接', c.objectives.length,
        '<button class="btn-sm" data-act="process_card.go" data-view="strategy">战略目标</button>',
        c.objectives.length ? objectiveRows : '',
        c.objectives.length ? '' : '年度经营计划需承接 ≥1 项战略指标 → 去关联',
      );
      const raciCard = moduleCard(
        '权责矩阵', c.raci.length,
        '<button class="btn-sm" data-act="process_card.raci">维护权责</button>',
        c.raci.length ? raciRows : '',
        c.raci.length ? '' : '每个关键事项必须有唯一 A → 维护权责',
      );
      const documentCard = moduleCard(
        '制度与标准', c.documents.length,
        '<button class="btn-sm" data-act="process_card.go" data-view="deliverables">标准文件</button>',
        c.documents.length ? documentRows : '',
        c.documents.length ? '' : '至少一份生效 SOP 才能支撑流程 → 去标准文件',
      );
      const modelCard = moduleCard(
        '流程模型', null, modelAction,
        `<div class="tiny">状态：${esc(c.model.status_label || '—')} ·
          版本：${c.model.version || '—'}</div>
         <div class="tiny">节点 ${c.model.node_count} · 连线 ${c.model.edge_count} ·
          表单 ${c.model.form_count} · 规则 ${c.model.rule_count} ·
          工具 ${c.model.tool_count}</div>`,
        modelGuide,
      );
      const workloadCard = moduleCard(
        '工作量与产能', null,
        '<button class="btn-sm" data-act="process_card.workload">工作量</button>',
        `<div class="tiny">已验证标准 ${c.workload.verified_standards} 条
          · 需求 ${num(c.workload.demand_hours, 1)}h/月
          · 实际 ${num(c.workload.actual_hours, 1)}h</div>
         <div class="tiny">可用 ${num(c.workload.capacity_hours, 1)}h
          · 负荷率 ${c.workload.utilization === null ? '—'
            : num(c.workload.utilization * 100, 1) + '%'}</div>`,
        c.readiness.workload ? '' : '完成现场观测并验证标准工时，才能计算产能 → 去登记工时',
      );
      const kpiCard = moduleCard(
        'KPI', c.kpis.length,
        '<button class="btn-sm" data-act="process_card.go" data-view="monitor">运营监控</button>',
        c.kpis.length ? `<table class="tbl"><tbody>${kpiRows}</tbody></table>` : '',
        c.kpis.length ? '' : '年度经营计划需承接 ≥1 项战略指标 → 去关联 KPI',
      );
      const changeCard = moduleCard(
        '变更', c.changes.length,
        '<button class="btn-sm" data-act="process_card.changes">变更申请</button>',
        c.changes.length ? changeRows : '',
        c.changes.length ? '' : '制度、模型或授权发生变化时提变更申请',
      );
      const improvementCard = moduleCard(
        '改善', c.improvements.length,
        '<button class="btn-sm" data-act="process_card.go" data-view="projects">项目组合</button>',
        c.improvements.length ? improvementRows : '',
        c.improvements.length ? '' : '流程运行满一个完整周期后可发起首次改善复盘',
      );
      const maturityCard = moduleCard(
        '成熟度', assessments.length,
        canManage() ? '<button class="btn-sm" data-act="process_card.newMaturity">+ 评估</button>' : '',
        `${coverageHtml}${assessments.length ? maturityRows : ''}`,
        assessments.length ? '' : '至少运行一个完整周期后才可评估',
      );
      const taskCard = moduleCard(
        'L5 任务', tasks.length,
        c.process.level === 4 && canManage()
          ? '<button class="btn-sm" data-act="process_card.newTask">+ 任务</button>'
          : '<button class="btn-sm" data-act="process_card.go" data-view="map">去流程地图</button>',
        tasks.length ? taskRows : '',
        tasks.length ? ''
          : (c.process.level === 4
            ? '流程模型定稿后拆解为可执行任务 → 新增任务'
            : 'L5 任务在 L4 活动下维护；先进入具体 L4 流程'),
      );
      const findingCard = moduleCard(
        '治理待办', c.findings.length,
        '<button class="btn-sm" data-act="process_card.findings">查看全部</button>',
        findingRows, '',
      );
      const groups = [
        group('战略与设计', [strategyCard, raciCard, documentCard, modelCard]),
        group('运行与结果', [workloadCard, kpiCard, changeCard, improvementCard]),
        group('治理与执行', [maturityCard, taskCard, findingCard]),
      ].join('');

      viewEl().innerHTML = `
        <div class="card page-head pc-head">
          <div class="between">
            <div><h2>流程卡<span class="module-badge">对象 360 · 模块聚合</span></h2>
              <div class="tiny">${chain || '—'}</div></div>
            <div class="gap">
              <select class="sel sel-sm" data-act="process_card.select">
                <option value="">切换流程</option>${options}</select>
              <button class="btn-sm" data-act="ui.copyLink">复制链接</button>
            </div>
          </div>
          <div class="between mt">
            <div><b>${esc(c.process.code)} ${esc(c.process.name)}</b>
              <span class="tiny muted">层级 L${c.process.level} · Owner ${esc(c.process.owner || '—')}
                · ${esc(c.process.org_unit_name || c.process.department || '—')}</span></div>
            <div class="gap">
              <span class="tag t-blu">模块就绪 ${readyCount}/${readyTotal}</span>
              <button class="btn-sm" data-act="process_card.findings">治理待办 ${c.findings.length}</button>
            </div>
          </div>
        </div>
        ${pilotHtml}
        ${groups}`;
    },
  );
};

async function openMaturityModal() {
  const processId = state.processCard.processId;
  if (!processId) return toast('请先选择流程', true);
  let meta;
  try {
    meta = await GET('/maturity/meta');
  } catch (e) {
    return toast(e.message, true);
  }
  const dimensions = meta.dimension_labels || {};
  openModal('新增成熟度评估', `
    <div class="note mb">评分必须附证据链接；同一维度以最新一次评估为准。</div>
    <div class="row2">
      <div class="field"><label>维度 *</label><select id="maDimension">
        ${Object.entries(dimensions).map(([code, label]) =>
          `<option value="${code}">${esc(label)}</option>`).join('')}
      </select></div>
      <div class="field"><label>等级（0–5）*</label><select id="maLevel">
        ${[0, 1, 2, 3, 4, 5].map((n) => `<option value="${n}">L${n}</option>`).join('')}
      </select></div>
    </div>
    <div class="field"><label>证据链接 *</label>
      <input id="maEvidence" placeholder="评估报告 / 现场照片 / 系统截图链接"></div>
    <div class="field"><label>有效期至</label><input id="maValid" type="date"></div>
    <div class="field"><label>说明</label><textarea id="maNote" rows="2"></textarea></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="process_card.submitMaturity">保存评估</button>`);
}

async function submitMaturity() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('maEvidence')) return toast('成熟度评分必须附证据链接', true);
  try {
    await POST('/maturity/assessments', {
      process_id: state.processCard.processId,
      dimension: val('maDimension'),
      level: Number(val('maLevel')),
      evidence_url: val('maEvidence'),
      valid_until: val('maValid') || null,
      note: val('maNote') || null,
    });
    toast('成熟度评估已保存');
    closeModal();
    RENDERERS.process_card();
  } catch (e) {
    toast(e.message, true);
  }
}

function openTaskModal() {
  const processId = state.processCard.processId;
  const level = state.processCard.level;
  if (!processId || level !== 4) {
    return toast('请在 L4 活动下新增 L5 任务', true);
  }
  openModal('新增 L5 任务', `
    <div class="note mb">L5 是 L4 下的可执行任务；标准工时可以后续挂到任务上。</div>
    <div class="row2">
      <div class="field"><label>任务编码 *</label><input id="ptCode" placeholder="如 T-01"></div>
      <div class="field"><label>任务名称 *</label><input id="ptName" placeholder="如 汇总采购需求"></div>
    </div>
    <div class="row3">
      <div class="field"><label>标准工时（分）</label>
        <input id="ptMinutes" type="number" step="0.1" min="0"></div>
      <div class="field"><label>频次</label><input id="ptFrequency" placeholder="如 2 次/周"></div>
      <div class="field"><label>排序</label><input id="ptSort" type="number" value="0"></div>
    </div>
    <div class="field"><label>说明</label><textarea id="ptDesc" rows="2"></textarea></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="process_card.submitTask">创建任务</button>`);
}

async function submitTask() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  if (!val('ptCode') || !val('ptName')) return toast('任务编码与名称不能为空', true);
  const minutes = val('ptMinutes');
  try {
    await POST('/process-tasks', {
      activity_id: state.processCard.processId,
      code: val('ptCode'),
      name: val('ptName'),
      description: val('ptDesc') || null,
      standard_minutes: minutes ? Number(minutes) : null,
      frequency: val('ptFrequency') || null,
      sort_order: Number(val('ptSort') || 0),
    });
    toast('L5 任务已创建');
    closeModal();
    RENDERERS.process_card();
  } catch (e) {
    toast(e.message, true);
  }
}

function openFindingsModal() {
  const card = state.processCard.data;
  if (!card) return;
  const rows = (card.findings || []).map((row) => `
    <div class="between bpmn-node-row">
      <span><b>${esc(row.title)}</b>
        <div class="tiny">${esc(row.type_label || row.type)} ·
          严重度 ${esc(SEVERITY_LABELS[row.severity] || row.severity || '—')}</div></span>
    </div>`).join('') || '<div class="note">没有未闭环治理待办。</div>';
  openModal(`治理待办（${(card.findings || []).length}）`, rows,
    '<button class="btn btn-g" data-act="ui.close">关闭</button>');
}

export { renderProcessCard };
