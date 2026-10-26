/* 视图：流程卡
 *
 * 一条 L3/L4 流程的跨模块聚合：战略、权责、制度、模型、工时、KPI、
 * 变更、改善与治理待办。所有区块都能跳回原模块处理。
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
      const [card, assessments, coverage] = await Promise.all([
        GET('/process-card/' + processId),
        GET('/maturity/assessments?process_id=' + processId),
        canManage() ? GET('/maturity/coverage').catch(() => null) : Promise.resolve(null),
      ]);
      const tasks = await GET(
        card.process.level === 4
          ? '/process-tasks?activity_id=' + processId
          : '/process-tasks?process_id=' + processId,
      ).catch(() => []);
      state.processCard.level = card.process.level;
      return { processes, card, assessments, coverage, tasks };
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
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const raciRows = c.raci.map((matter) => `
        <div class="between bpmn-node-row">
          <span>${esc(matter.matter)}
            ${matter.has_accountable ? '<span class="tag t-grn">A 已明确</span>'
              : '<span class="tag t-red">缺少 A</span>'}</span>
          <span class="tiny">${matter.entries.map((entry) =>
            `${esc(entry.raci)} ${esc(entry.role_name || '—')}`).join(' · ')}</span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const documentRows = c.documents.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.category_label || '')}</div></span>
          <span class="tag t-grn">${esc(row.version_label || '—')}</span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const kpiRows = c.kpis.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td>${row.latest_value === null ? '—' : num(row.latest_value, 2)}
            → ${row.target_value === null ? '—' : num(row.target_value, 2)} ${esc(row.unit || '')}</td>
          <td><span class="tag ${STATUS_TONE[row.status] || 't-gry'}">${
            esc(row.status_label || row.status || '—')}</span></td>
        </tr>`).join('') || emptyRow(3, '—');

      const changeRows = c.changes.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.impact_level_label || '')}</div></span>
          <span class="tag t-yel">${esc(row.status_label || '')}</span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const improvementRows = c.improvements.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.name)}<div class="tiny">${esc(row.code)} · ${esc(row.source_label || '')}</div></span>
          <span class="tag t-blu">${esc(row.status_label || '')} · ${num(row.progress, 0)}%</span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const maturityRows = assessments.slice(0, 8).map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.dimension_label || row.dimension)}</b>
            <div class="tiny">${esc(row.assessed_by || '—')} · ${esc(row.assessed_at || '')}</div></span>
          <span><span class="tag ${row.level >= 4 ? 't-grn' : row.level >= 2 ? 't-yel' : 't-red'}">
            L${row.level}</span></span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const taskRows = tasks.slice(0, 12).map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.code)} ${esc(row.name)}</b>
            <div class="tiny">${esc(row.activity_code || '')} ${esc(row.position_name || '未绑岗位')}
              ${row.frequency ? ' · ' + esc(row.frequency) : ''}</div></span>
          <span class="tag ${row.standard_minutes ? 't-grn' : 't-gry'}">${
            row.standard_minutes ? num(row.standard_minutes, 1) + ' 分' : '待补工时'}</span>
        </div>`).join('') || '<div class="tiny muted">—</div>';

      const canDesign = c.readiness.strategy && c.readiness.raci && c.readiness.policy;
      const layers = [
        {
          no: 1, title: '战略承接', goal: '回答为什么做、做成什么样',
          ready: c.readiness.strategy && c.objectives.length > 0
            && c.objectives.some((row) => row.target_value !== null),
          summary: `${c.objectives.length} 项战略目标`,
          empty: '年度经营计划需承接 ≥1 项战略指标 → 去关联',
          action: '<button class="btn-sm" data-act="process_card.go" data-view="strategy">去关联目标</button>',
          conditions: [
            { text: '已关联至少 1 项战略目标', ok: c.objectives.length > 0 },
            { text: '目标值已定义', ok: c.objectives.some((row) => row.target_value !== null) },
          ],
          body: c.objectives.length ? objectiveRows : '',
        },
        {
          no: 2, title: '权责矩阵', goal: '谁输入、谁处理、谁决策、谁负责',
          ready: c.readiness.raci && c.raci.length > 0,
          summary: `${c.raci.length} 个关键事项`,
          empty: '每个关键事项必须有唯一 A → 维护权责',
          action: '<button class="btn-sm" data-act="process_card.raci">维护权责</button>',
          conditions: [
            { text: '已配置关键事项', ok: c.raci.length > 0 },
            { text: '每个事项恰好一个 A', ok: c.raci.length > 0 && c.raci.every((row) => row.has_accountable) },
          ],
          body: c.raci.length ? raciRows : '',
        },
        {
          no: 3, title: '制度与标准', goal: '必须做、禁止做什么',
          ready: c.readiness.policy && c.documents.length > 0,
          summary: `${c.documents.length} 份生效文件`,
          empty: '至少一份生效 SOP 才能支撑流程 → 去标准文件',
          action: '<button class="btn-sm" data-act="process_card.go" data-view="deliverables">标准文件</button>',
          conditions: [{ text: '至少一份生效 SOP/标准文件', ok: c.documents.length > 0 }],
          body: c.documents.length ? documentRows : '',
        },
        {
          no: 4, title: '流程模型', goal: '先做什么后做什么，何时升级',
          ready: c.readiness.model,
          summary: c.model.status === 'PUBLISHED'
            ? `已发布 v${c.model.version || '—'} · ${c.model.node_count} 节点`
            : (c.model.status_label || '未建模'),
          empty: '先完成第 1–3 层，再打开设计器建模',
          action: canDesign
            ? '<button class="btn-sm" data-act="process_card.designer">打开设计器</button>'
            : '<button class="btn-sm" disabled title="先完成第 1–3 层">打开设计器</button>',
          conditions: [
            { text: '模型节点已建立', ok: c.model.node_count > 0 },
            { text: '模型已发布', ok: c.model.status === 'PUBLISHED' },
          ],
          body: `<div class="tiny">状态：${esc(c.model.status_label || '—')} ·
              版本：${c.model.version || '—'}</div>
            <div class="tiny">节点 ${c.model.node_count} · 连线 ${c.model.edge_count} ·
              表单 ${c.model.form_count} · 规则 ${c.model.rule_count} ·
              工具 ${c.model.tool_count}</div>`,
        },
        {
          no: 5, title: '工作量与产能', goal: '标准时间与有效产出',
          ready: c.readiness.workload,
          summary: `${c.workload.verified_standards} 条已验证工时`,
          empty: '完成现场观测并验证标准工时，才能计算产能 → 去登记工时',
          action: '<button class="btn-sm" data-act="process_card.workload">工作量</button>',
          conditions: [
            { text: '至少一条已验证标准工时', ok: c.workload.verified_standards > 0 },
            { text: '已登记可用产能', ok: c.workload.capacity_hours > 0 },
          ],
          body: `<div class="tiny">已验证标准 ${c.workload.verified_standards} 条
              · 需求 ${num(c.workload.demand_hours, 1)}h/月
              · 实际 ${num(c.workload.actual_hours, 1)}h</div>
            <div class="tiny">可用 ${num(c.workload.capacity_hours, 1)}h
              · 负荷率 ${c.workload.utilization === null ? '—'
                : num(c.workload.utilization * 100, 1) + '%'}</div>`,
        },
        {
          no: 6, title: 'KPI', goal: '质量、效率、交付、成本',
          ready: c.readiness.kpi,
          summary: `${c.kpis.length} 个关联指标`,
          empty: '年度经营计划需承接 ≥1 项战略指标 → 去关联 KPI',
          action: '<button class="btn-sm" data-act="process_card.go" data-view="monitor">运营监控</button>',
          conditions: [
            { text: '已关联至少 1 个 KPI', ok: c.kpis.length > 0 },
            { text: '已有数据点', ok: c.kpis.some((row) => row.latest_value !== null) },
          ],
          body: c.kpis.length ? `<table class="tbl"><tbody>${kpiRows}</tbody></table>` : '',
        },
        {
          no: 7, title: '变更', goal: '什么情况触发版本更新',
          operating: true, ready: c.changes.length > 0,
          summary: `${c.changes.length} 条变更`,
          empty: '制度、模型或授权发生变化时提变更申请',
          action: '<button class="btn-sm" data-act="process_card.changes">变更申请</button>',
          conditions: [{ text: '已有变更记录', ok: c.changes.length > 0 }],
          body: c.changes.length ? changeRows : '',
        },
        {
          no: 8, title: '改善', goal: '删浪费、固化更好方法',
          operating: true, ready: c.improvements.length > 0,
          summary: `${c.improvements.length} 个改善项目`,
          empty: '流程运行满一个完整周期后可发起首次改善复盘',
          action: '<button class="btn-sm" data-act="process_card.go" data-view="projects">项目组合</button>',
          conditions: [{ text: '已有改善项目', ok: c.improvements.length > 0 }],
          body: c.improvements.length ? improvementRows : '',
        },
        {
          no: 9, title: '成熟度', goal: '本流程当前达到什么水平',
          operating: true, ready: assessments.length > 0,
          summary: assessments.length ? `${assessments.length} 项评估` : '未评估',
          empty: '至少运行一个完整周期后才可评估',
          action: canManage()
            ? '<button class="btn-sm" data-act="process_card.newMaturity">+ 评估</button>' : '',
          conditions: [{ text: '已有成熟度评估', ok: assessments.length > 0 }],
          body: assessments.length ? `${coverageHtml}${maturityRows}` : coverageHtml,
        },
        {
          no: 10, title: 'L5 任务', goal: '最底层可执行任务',
          operating: true, ready: tasks.length > 0,
          summary: `${tasks.length} 个任务`,
          empty: c.process.level === 4
            ? '流程模型定稿后拆解为可执行任务 → 新增任务'
            : 'L5 任务在 L4 活动下维护；先进入具体 L4 流程',
          action: c.process.level === 4 && canManage()
            ? '<button class="btn-sm" data-act="process_card.newTask">+ 任务</button>'
            : '<button class="btn-sm" data-act="process_card.go" data-view="map">去流程地图</button>',
          conditions: [{ text: '已有 L5 任务', ok: tasks.length > 0 }],
          body: tasks.length ? taskRows : '',
        },
      ];

      const coreLayers = layers.filter((layer) => !layer.operating);
      const activeLayer = coreLayers.find((layer) => !layer.ready) || null;
      const activeNo = activeLayer ? activeLayer.no : 7;
      const coreReady = coreLayers.filter((layer) => layer.ready).length;
      const statusFor = (layer) => {
        if (layer.ready) return layer.operating ? 'operating' : 'ready';
        if (layer.operating) return 'operating';
        if (activeLayer && layer.no === activeLayer.no) return 'current';
        return layer.no > activeNo ? 'locked' : 'ready';
      };
      const tone = { ready: 't-grn', current: 't-blu', locked: 't-gry', operating: 't-pur' };
      const label = { ready: '已完成', current: '当前层', locked: '未解锁', operating: '持续运营' };
      const layerHtml = layers.map((layer) => {
        const status = statusFor(layer);
        const conditions = layer.conditions.map((item) => `
          <li class="${item.ok ? 'ok' : 'todo'}">
            <span aria-hidden="true">${item.ok ? '✓' : '○'}</span>${esc(item.text)}</li>`).join('');
        return `<details class="pc-layer ${status}"${layer.no === activeNo ? ' open' : ''}>
          <summary class="pc-layer-hd">
            <span class="pc-no">${layer.no}</span>
            <span class="pc-title"><b>${esc(layer.title)}</b>
              <small>${esc(layer.goal)}</small></span>
            <span class="pc-meta">${esc(layer.summary)}</span>
            <span class="tag ${tone[status]}">${label[status]}</span>
          </summary>
          <div class="pc-layer-body">
            <div class="between pc-layer-top">
              <div class="pc-exit"><b>退出条件</b><ul>${conditions}</ul></div>
              <div class="gap">${status === 'locked' ? '' : (layer.action || '')}</div>
            </div>
            ${status === 'locked'
              ? `<div class="note">先完成第 ${activeNo} 层的退出条件，再进入本层。</div>`
              : (!layer.ready && layer.empty ? `<div class="pc-empty">${esc(layer.empty)}</div>` : '')}
            ${status === 'locked' ? '' : layer.body}
          </div>
        </details>`;
      }).join('');

      viewEl().innerHTML = `
        <div class="card page-head pc-head">
          <div class="between">
            <div><h2>流程卡<span class="module-badge">一个流程 · 十层治理</span></h2>
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
              <span class="tag t-blu">核心层 ${coreReady}/${coreLayers.length}</span>
              <button class="btn-sm" data-act="process_card.findings">治理待办 ${c.findings.length}</button>
            </div>
          </div>
        </div>
        <div class="pc-layers">${layerHtml}</div>`;
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
