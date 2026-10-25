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

const STATUS_TONE = { RED: 't-red', YELLOW: 't-yel', GREEN: 't-grn', GRAY: 't-gry' };
const READY_LABELS = {
  strategy: '战略承接',
  raci: '权责矩阵',
  policy: '制度标准',
  model: '流程模型',
  workload: '标准工时',
  kpi: 'KPI',
  improvement: '改善/变更',
  governance: '治理待办',
};

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
      return { processes, card, assessments, coverage };
    },
    (d) => {
      const options = d.processes.map((row) =>
        `<option value="${row.id}"${row.id === state.processCard.processId ? ' selected' : ''}>L${
          row.level} ${esc(row.code)} ${esc(row.name)}</option>`).join('');
      if (!d.card) {
        viewEl().innerHTML = `<div class="card page-head">
          <div class="between"><h2>流程卡</h2>
          <select class="sel sel-sm" data-act="process_card.select">
            <option value="">请选择流程</option>${options}</select></div>
          <div class="empty">还没有 L3/L4 流程，请先在流程地图中建立架构。</div></div>`;
        return;
      }
      const c = d.card;
      const readiness = Object.entries(c.readiness || {}).map(([key, ok]) =>
        `<span class="tag ${ok ? 't-grn' : 't-gry'}">${esc(READY_LABELS[key] || key)} ${
          ok ? '✓' : '待补'}</span>`).join(' ');
      const chain = c.chain.map((item) =>
        `<span class="tiny">L${item.level} ${esc(item.code)} ${esc(item.name)}</span>`).join(' › ');

      const objectiveRows = c.objectives.map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)} · ${row.year}</div></span>
          <span class="tag t-blu">${row.target_value === null ? '—' : num(row.target_value, 2)}
            ${esc(row.unit || '')}</span>
        </div>`).join('') || '<div class="tiny muted">还没有承接战略目标</div>';

      const raciRows = c.raci.map((matter) => `
        <div class="between bpmn-node-row">
          <span>${esc(matter.matter)}
            ${matter.has_accountable ? '<span class="tag t-grn">A 已明确</span>'
              : '<span class="tag t-red">缺少 A</span>'}</span>
          <span class="tiny">${matter.entries.map((entry) =>
            `${esc(entry.raci)} ${esc(entry.role_name || '—')}`).join(' · ')}</span>
        </div>`).join('') || '<div class="tiny muted">还没有配置权责矩阵</div>';

      const documentRows = c.documents.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.category_label || '')}</div></span>
          <span class="tag t-grn">${esc(row.version_label || '—')}</span>
        </div>`).join('') || '<div class="tiny muted">还没有生效的标准文件</div>';

      const kpiRows = c.kpis.map((row) => `
        <tr>
          <td><b>${esc(row.name)}</b><div class="tiny">${esc(row.code)}</div></td>
          <td>${row.latest_value === null ? '—' : num(row.latest_value, 2)}
            → ${row.target_value === null ? '—' : num(row.target_value, 2)} ${esc(row.unit || '')}</td>
          <td><span class="tag ${STATUS_TONE[row.status] || 't-gry'}">${
            esc(row.status_label || row.status || '—')}</span></td>
        </tr>`).join('') || emptyRow(3, '还没有关联 KPI');

      const changeRows = c.changes.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}<div class="tiny">${esc(row.code)} · ${esc(row.impact_level_label || '')}</div></span>
          <span class="tag t-yel">${esc(row.status_label || '')}</span>
        </div>`).join('') || '<div class="tiny muted">还没有变更申请</div>';

      const improvementRows = c.improvements.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.name)}<div class="tiny">${esc(row.code)} · ${esc(row.source_label || '')}</div></span>
          <span class="tag t-blu">${esc(row.status_label || '')} · ${num(row.progress, 0)}%</span>
        </div>`).join('') || '<div class="tiny muted">还没有改善项目</div>';

      const findingRows = c.findings.map((row) => `
        <div class="between bpmn-node-row">
          <span>${esc(row.title)}</span>
          <span class="tag ${row.severity === 'HIGH' ? 't-red' : 't-yel'}">${
            esc(row.type_label || row.type)}</span>
        </div>`).join('') || '<div class="tiny muted">没有未闭环治理待办</div>';

      const w = c.workload;
      const d2 = d;
      const maturityRows = (d2.assessments || []).slice(0, 8).map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.dimension_label || row.dimension)}</b>
            <div class="tiny">${esc(row.assessed_by || '—')} · ${esc(row.assessed_at || '')}</div></span>
          <span><span class="tag ${row.level >= 4 ? 't-grn' : row.level >= 2 ? 't-yel' : 't-red'}">
            L${row.level}</span></span>
        </div>`).join('') || '<div class="tiny muted">还没有成熟度评估</div>';
      const covRow = d2.coverage
        ? (d2.coverage.rows || []).find((row) => row.process_id === state.processCard.processId)
        : null;
      const coverageHtml = covRow
        ? `<div class="tiny">L4 ${covRow.l4_total} 个 · Owner ${
          num(covRow.owner_coverage_pct, 0)}% · 制度 ${
          num(covRow.document_coverage_pct, 0)}% · KPI ${
          num(covRow.kpi_coverage_pct, 0)}%</div>`
        : '';
      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>流程卡<span class="module-badge">战略 · 权责 · 标准 · 模型 · 工时 · KPI</span></h2>
              <div class="desc">${chain || '—'}</div></div>
            <select class="sel sel-sm" data-act="process_card.select">
              <option value="">切换流程</option>${options}</select>
            <button class="btn-sm" data-act="ui.copyLink">复制链接</button>
          </div>
          <div class="between mt">
            <div><b>${esc(c.process.code)} ${esc(c.process.name)}</b>
              <span class="tiny muted">Owner：${esc(c.process.owner || '—')} ·
                ${esc(c.process.org_unit_name || c.process.department || '—')}</span></div>
            <div class="gap">${readiness}</div>
          </div>
        </div>

        <div class="grid g2">
          <div class="card">
            <div class="between mb"><h3>战略承接（${c.objectives.length}）</h3>
              <button class="btn-sm" data-act="process_card.go" data-view="strategy">战略目标</button></div>
            ${objectiveRows}
          </div>
          <div class="card">
            <div class="between mb"><h3>权责矩阵（${c.raci.length}）</h3>
              <button class="btn-sm" data-act="process_card.raci">维护权责</button></div>
            ${raciRows}
          </div>
          <div class="card">
            <div class="between mb"><h3>制度与标准（${c.documents.length}）</h3>
              <button class="btn-sm" data-act="process_card.go" data-view="deliverables">标准文件</button></div>
            ${documentRows}
          </div>
          <div class="card">
            <div class="between mb"><h3>流程模型</h3>
              <button class="btn-sm" data-act="process_card.designer">打开设计器</button></div>
            <div class="tiny">状态：${esc(c.model.status_label || '—')} ·
              版本：${c.model.version || '—'}</div>
            <div class="tiny">节点 ${c.model.node_count} · 连线 ${c.model.edge_count} ·
              表单 ${c.model.form_count} · 规则 ${c.model.rule_count} ·
              工具 ${c.model.tool_count}</div>
          </div>
          <div class="card">
            <div class="between mb"><h3>工作量与产能</h3>
              <button class="btn-sm" data-act="process_card.workload">工作量</button></div>
            <div class="tiny">已验证标准 ${w.verified_standards} 条
              · 需求 ${num(w.demand_hours, 1)}h/月
              · 实际 ${num(w.actual_hours, 1)}h</div>
            <div class="tiny">可用 ${num(w.capacity_hours, 1)}h
              · 负荷率 ${w.utilization === null ? '—' : num(w.utilization * 100, 1) + '%'}</div>
          </div>
          <div class="card">
            <div class="between mb"><h3>KPI（${c.kpis.length}）</h3>
              <button class="btn-sm" data-act="process_card.go" data-view="monitor">运营监控</button></div>
            <table class="tbl"><tbody>${kpiRows}</tbody></table>
          </div>
          <div class="card">
            <div class="between mb"><h3>变更（${c.changes.length}）</h3>
              <button class="btn-sm" data-act="process_card.changes">变更申请</button></div>
            ${changeRows}
          </div>
          <div class="card">
            <div class="between mb"><h3>改善（${c.improvements.length}）</h3>
              <button class="btn-sm" data-act="process_card.go" data-view="projects">项目组合</button></div>
            ${improvementRows}
          </div>
          <div class="card">
            <div class="between mb"><h3>成熟度（${(d2.assessments || []).length}）</h3>
              ${canManage() ? `<button class="btn-sm" data-act="process_card.newMaturity">+ 评估</button>` : ''}</div>
            ${coverageHtml}
            ${maturityRows}
          </div>
          <div class="card">
            <h3>治理待办（${c.findings.length}）</h3>
            ${findingRows}
          </div>
        </div>`;
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

export { renderProcessCard };
