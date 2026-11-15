import { esc } from '../../core/format.js';

export function renderGate5(readiness) {
  if (!readiness) return '<div class="note">责任闭合检查暂不可用。</div>';
  const blockers = readiness.blockers || [];
  const warnings = readiness.warnings || [];
  const tone = readiness.status === 'PASS' ? 't-grn' : 't-yel';
  const item = (row) => `<div class="tiny mt"><span class="tag t-red">${esc(row.code)}</span> ${esc(row.message)}</div>`;
  const activities = (readiness.activities || []).map((row) => `
    <div class="between tiny mt"><span>${esc(row.node_key)} · ${esc(row.activity_code || '未映射')}</span>
      <span class="tag ${row.status === 'PASS' ? 't-grn' : 't-red'}">${esc(row.status)}</span></div>`).join('');
  return `<div class="note gate5-readiness" data-gate5-readiness>
    <div class="between"><b>责任闭合</b><span class="tag ${tone}">${esc(readiness.status)} · ${esc(readiness.evidence_grade)}</span></div>
    <div class="tiny muted mt">模型 v${esc(readiness.model_version || '—')} · Owner ${esc(readiness.process_owner?.label || '未绑定')}</div>
    ${blockers.slice(0, 6).map(item).join('') || '<div class="tiny mt">当前没有责任阻断。</div>'}
    ${warnings.slice(0, 3).map(item).join('')}
    <details class="mt"><summary class="tiny">查看活动责任状态（${activities ? readiness.activities.length : 0}）</summary>${activities}</details>
  </div>`;
}
