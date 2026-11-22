import { esc } from '../../core/format.js';

const GATE5_LABELS = {
  OWNER_ACCOUNT_MISSING: '责任人账号未绑定',
  OWNER_ACCOUNT_INVALID: '责任人账号不可用',
  OWNER_ACCEPTANCE_MISSING: '责任人尚未确认职责',
  VERSIONED_ACTIVITY_MAPPING_REQUIRED: '活动尚未完成版本化映射',
  LEGACY_ACTIVITY_MAPPING: '活动仍使用旧版兼容映射',
  ACTIVITY_A_NOT_UNIQUE: '活动缺少唯一负责角色',
  ACCOUNTABLE_ROLE_INVALID: '负责角色成员或岗位不可用',
  NODE_ASSIGNMENT_MISSING: '节点还没有责任配置',
  ASSIGNMENT_UNVERSIONED: '责任配置尚未绑定模型版本',
  EXECUTOR_MISSING: '执行人账号未配置',
  APPROVER_MISSING: '审批人账号未配置',
  APPROVAL_SELF_CONFLICT: '执行人与审批人不能是同一人',
  BACKUP_MISSING: '备用责任人未配置',
  ESCALATION_MISSING: '升级责任人未配置',
  ACCOUNTABILITY_ACCEPTANCE_MISSING: '负责角色尚未确认职责',
  EXECUTOR_ACCEPTANCE_MISSING: '执行人尚未确认职责',
  BACKUP_ACCEPTANCE_MISSING: '备用责任人尚未确认职责',
  ESCALATION_ACCEPTANCE_MISSING: '升级责任人尚未确认职责',
};

function gate5Label(item) {
  return GATE5_LABELS[item.code] || item.message || '责任闭合待核对';
}
function gate5Action(row, readiness) {
  const code = row.code;
  const node = row.node_key || '';
  const process = row.process_id || readiness.process_id || '';
  const model = row.model_version_id || readiness.model_version_id || '';
  if (code === 'OWNER_ACCOUNT_MISSING' || code === 'OWNER_ACCOUNT_INVALID') {
    return `<button class="btn-sm mt" data-act="gate5.go" data-view="map" data-process="${esc(process)}">去绑定流程 Owner</button>`;
  }
  if (code === 'VERSIONED_ACTIVITY_MAPPING_REQUIRED' || code === 'LEGACY_ACTIVITY_MAPPING') {
    return `<button class="btn-sm mt" data-act="gate5.go" data-view="designer" data-tab="model" data-process="${esc(process)}" data-model="${esc(model)}">去确认活动映射</button>`;
  }
  if (code === 'NODE_ASSIGNMENT_MISSING' || code === 'EXECUTOR_MISSING' || code === 'APPROVER_MISSING'
    || code === 'BACKUP_MISSING' || code === 'ESCALATION_MISSING') {
    return `<button class="btn-sm mt" data-act="gate5.go" data-view="execution" data-tab="config" data-focus="assign" data-process="${esc(process)}" data-node="${esc(node)}">去补节点责任配置</button>`;
  }
  if (code === 'ACTIVITY_A_NOT_UNIQUE' || code === 'ACCOUNTABLE_ROLE_INVALID') {
    return `<button class="btn-sm mt" data-act="gate5.go" data-view="responsibility" data-process="${esc(process)}" data-node="${esc(node)}">去核对岗位职责</button>`;
  }
  if (code.endsWith('_ACCEPTANCE_MISSING')) {
    return `<button class="btn-sm mt" data-act="gate5.acceptance" data-process="${esc(process)}" data-model="${esc(model)}" data-node="${esc(node)}" data-scope="${esc(code.replace('_ACCEPTANCE_MISSING', ''))}">查看责任接受要求</button>`;
  }
  return '';
}


export function renderGate5(readiness) {
  if (!readiness) return '<div class="note">责任闭合检查暂不可用。</div>';
  const blockers = readiness.blockers || [];
  const warnings = readiness.warnings || [];
  const tone = readiness.status === 'PASS' ? 't-grn' : 't-yel';
  const item = (row) => {
    const action = gate5Action(row, readiness);
    return `<div class="tiny mt"><span class="tag t-red">${esc(gate5Label(row))}</span>${action}</div>`;
  };
  const activities = (readiness.activities || []).map((row) => `
    <div class="between tiny mt"><span>${esc(row.node_key)} · ${esc(row.activity_code || '未映射')}</span>
      <span class="tag ${row.status === 'PASS' ? 't-grn' : 't-red'}">${esc(row.status)}</span></div>`).join('');
  return `<div class="card gate5-readiness" data-gate5-readiness>
    <div class="between"><div><div class="tiny muted">责任闭合</div><h3 style="margin:4px 0">Gate 5 · 组织与责任</h3></div><span class="tag ${tone}">${esc(readiness.status)} · ${esc(readiness.evidence_grade)}</span></div>
    <div class="tiny muted mt">模型 v${esc(readiness.model_version || '—')} · Owner ${esc(readiness.process_owner?.label || '未绑定')}</div>
    ${blockers.slice(0, 6).map(item).join('') || '<div class="tiny mt">当前没有责任阻断。</div>'}
    ${warnings.slice(0, 3).map(item).join('')}
    <details class="mt"><summary class="tiny">查看活动责任状态（${readiness.activities.length}）</summary>${activities}</details>
  </div>`;
}
