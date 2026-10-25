/* 视图：授权矩阵
 *
 * A/B/C/D 分级授权规则 + 例外台账。所有中文标签来自 /authorization/meta，
 * 前端不维护枚举映射；规则生效前必须补齐审批角色、例外路径与审批证据。
 */

import { esc, num, emptyRow } from '../core/format.js';
import { viewEl, on, openModal, closeModal, confirmDialog, promptDialog, toast } from '../core/ui.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { state } from '../core/state.js';

const RULE_TONE = { DRAFT: 't-gry', EFFECTIVE: 't-grn', RETIRED: 't-gry' };
const EXC_TONE = {
  REQUESTED: 't-yel', APPROVED: 't-blu', REJECTED: 't-red', CLOSED: 't-grn',
};

on('authorization.go', ({ view }) => go(view));

on('authorization.tab', (_data, el) => {
  const pane = el.dataset.pane;
  document.querySelectorAll('#view [data-az-pane]').forEach((box) => {
    box.classList.toggle('hide', box.dataset.azPane !== pane);
  });
  el.parentElement.querySelectorAll('button').forEach((btn) => {
    btn.classList.toggle('on', btn === el);
  });
});

on('authorization.newRule', () => openRuleModal(null));
on('authorization.edit', ({ id }) => {
  const row = (state.authorization.rules || []).find((item) => item.id === Number(id));
  if (row) openRuleModal(row);
});
on('authorization.saveRule', ({ id }) => saveRule(id ? Number(id) : null));

on('authorization.activate', async ({ id }) => {
  const ok = await confirmDialog('生效后该规则会进入授权矩阵口径，确定继续？',
    { title: '生效授权规则', okText: '生效' });
  if (!ok) return;
  await runAction(() => POST(`/authorization/rules/${id}/activate`), '规则已生效');
});
on('authorization.retire', async ({ id }) => {
  const ok = await confirmDialog('停用后该规则不再作为审批依据，确定继续？',
    { title: '停用授权规则', okText: '停用', danger: true });
  if (!ok) return;
  await runAction(() => POST(`/authorization/rules/${id}/retire`), '规则已停用');
});
on('authorization.delete', async ({ id }) => {
  const ok = await confirmDialog('只允许删除草稿规则，确定继续？',
    { title: '删除授权规则', okText: '删除', danger: true });
  if (!ok) return;
  await runAction(() => DEL(`/authorization/rules/${id}`), '规则已删除');
});
on('authorization.newException', ({ id }) => openExceptionModal(Number(id) || null));
on('authorization.submitException', () => submitException());

on('authorization.approve', async ({ id }) => {
  const note = await promptDialog('审批意见（可留空）',
    { title: '批准例外', okText: '批准', value: '' });
  if (note === undefined) return;
  await runAction(
    () => POST(`/authorization/exceptions/${id}/approve`, { note: note || null }),
    '例外已批准',
  );
});
on('authorization.reject', async ({ id }) => {
  const note = await promptDialog('驳回原因（必填）',
    { title: '驳回例外', okText: '驳回', value: '' });
  if (note === undefined) return;
  if (!note.trim()) return toast('驳回必须填写原因', true);
  await runAction(
    () => POST(`/authorization/exceptions/${id}/reject`, { note: note.trim() }),
    '例外已驳回',
  );
});
on('authorization.closeException', async ({ id }) => {
  const ok = await confirmDialog('关闭后该例外不再出现在未闭环台账，确定继续？',
    { title: '关闭例外', okText: '关闭' });
  if (!ok) return;
  await runAction(
    () => POST(`/authorization/exceptions/${id}/close`, { note: null }),
    '例外已关闭',
  );
});
on('authorization.reviewException', async ({ id }) => {
  const note = await promptDialog('复盘结论（必填）',
    { title: '例外复盘', okText: '保存复盘', value: '' });
  if (note === undefined) return;
  if (!note.trim()) return toast('复盘必须填写结论', true);
  await runAction(
    () => POST(`/authorization/exceptions/${id}/review`, { note: note.trim() }),
    '例外已复盘',
  );
});

async function runAction(action, message) {
  try {
    await action();
    toast(message);
    RENDERERS.authorization();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 规则弹窗 */

async function openRuleModal(rule) {
  let processes;
  let orgs;
  let roles;
  try {
    [processes, orgs, roles] = await Promise.all([
      GET('/process-map/flat'),
      GET('/org-units'),
      GET('/governance/roles'),
    ]);
  } catch (e) {
    return toast(e.message, true);
  }
  const meta = (state.authorization && state.authorization.meta) || {};
  const categoryLabels = meta.category_labels || {};
  const riskLabels = meta.risk_labels || {};
  const processOptions = processes
    .filter((row) => row.level === 3 || row.level === 4)
    .map((row) => `<option value="${row.id}"${rule && rule.process_id === row.id ? ' selected' : ''}>
      L${row.level} ${esc(row.code)} ${esc(row.name)}</option>`).join('');
  const orgOptions = orgs.map((row) =>
    `<option value="${row.id}"${rule && rule.org_unit_id === row.id ? ' selected' : ''}>
      ${esc(row.name)}</option>`).join('');
  const roleOptions = roles.map((row) =>
    `<option value="${row.id}"${rule && rule.approver_role_id === row.id ? ' selected' : ''}>
      ${esc(row.name)}</option>`).join('');
  const categoryOptions = Object.entries(categoryLabels).map(([value, label]) =>
    `<option value="${value}"${rule && rule.category === value ? ' selected' : ''}>
      ${esc(label)}</option>`).join('');
  const riskOptions = Object.entries(riskLabels).map(([value, label]) =>
    `<option value="${value}"${(rule ? rule.risk_level : 'MEDIUM') === value ? ' selected' : ''}>
      ${esc(label)}</option>`).join('');
  const val = (field, fallback = '') => {
    if (!rule) return fallback;
    return rule[field] === null || rule[field] === undefined ? '' : rule[field];
  };

  openModal(rule ? `编辑授权规则 · ${rule.code}` : '新建授权规则', `
    <div class="row2">
      <div class="field"><label>规则名称 *</label>
        <input id="azTitle" value="${esc(val('title'))}" placeholder="如 跨法人流程重构"></div>
      <div class="field"><label>关键事项 *</label>
        <input id="azMatter" value="${esc(val('matter'))}" placeholder="如 采购需求端到端流程重构"></div>
    </div>
    <div class="row3">
      <div class="field"><label>授权类别 *</label>
        <select id="azCategory">${categoryOptions}</select></div>
      <div class="field"><label>风险等级</label>
        <select id="azRisk">${riskOptions}</select></div>
      <div class="field"><label>金额上限</label>
        <input id="azAmount" type="number" min="0" step="0.01"
          value="${val('amount_limit')}" placeholder="留空表示不限"></div>
    </div>
    <div class="row2">
      <div class="field"><label>关联流程</label>
        <select id="azProcess"><option value="">集团/组织通用</option>${processOptions}</select></div>
      <div class="field"><label>适用范围组织</label>
        <select id="azOrg"><option value="">集团通用</option>${orgOptions}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>审批角色</label>
        <select id="azRole"><option value="">未指定</option>${roleOptions}</select></div>
      <div class="field"><label>审批角色说明</label>
        <input id="azApproverLabel" value="${esc(val('approver_label'))}"
          placeholder="没有治理角色时填写，如 集团治理委员会"></div>
    </div>
    <div class="row3">
      <div class="field"><label>影响范围</label>
        <input id="azImpact" value="${esc(val('impact_scope'))}" placeholder="如 跨法人 / 单工厂"></div>
      <div class="field"><label>可逆性</label>
        <input id="azReversibility" value="${esc(val('reversibility'))}" placeholder="如 可回退"></div>
      <div class="field"><label>频率</label>
        <input id="azFrequency" value="${esc(val('frequency'))}" placeholder="如 高频"></div>
    </div>
    <div class="field"><label>例外路径 *</label>
      <textarea id="azException" rows="3"
        placeholder="谁批、多久、需要什么证据">${esc(val('exception_path'))}</textarea></div>
    <div class="field"><label>审批证据 *</label>
      <textarea id="azEvidence" rows="2"
        placeholder="变更单、影响分析、测试证据、会议纪要">${esc(val('evidence_required'))}</textarea></div>
    <div class="row2">
      <div class="field"><label>生效日期</label>
        <input id="azFrom" type="date" value="${esc(val('valid_from'))}"></div>
      <div class="field"><label>失效日期</label>
        <input id="azTo" type="date" value="${esc(val('valid_to'))}"></div>
    </div>
    <div class="note">规则保存为草稿；补齐审批角色、例外路径与审批证据后才能生效。
      已生效规则修改后会自动回到草稿并升版。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="authorization.saveRule" data-id="${rule ? rule.id : ''}">
     ${rule ? '保存' : '创建'}</button>`, true);
}

async function saveRule(ruleId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const payload = {
    title: val('azTitle'),
    matter: val('azMatter'),
    category: val('azCategory'),
    risk_level: val('azRisk'),
    amount_limit: val('azAmount') === '' ? null : Number(val('azAmount')),
    process_id: val('azProcess') ? Number(val('azProcess')) : null,
    org_unit_id: val('azOrg') ? Number(val('azOrg')) : null,
    approver_role_id: val('azRole') ? Number(val('azRole')) : null,
    approver_label: val('azApproverLabel') || null,
    impact_scope: val('azImpact') || null,
    reversibility: val('azReversibility') || null,
    frequency: val('azFrequency') || null,
    exception_path: val('azException') || null,
    evidence_required: val('azEvidence') || null,
    valid_from: val('azFrom') || null,
    valid_to: val('azTo') || null,
  };
  if (!payload.title || !payload.matter) return toast('规则名称与关键事项不能为空', true);
  try {
    if (ruleId) await PATCH(`/authorization/rules/${ruleId}`, payload);
    else await POST('/authorization/rules', payload);
    closeModal();
    toast(ruleId ? '规则已保存（生效规则会回到草稿）' : '规则已创建（草稿）');
    RENDERERS.authorization();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 例外弹窗 */

async function openExceptionModal(ruleId) {
  let rules = ((state.authorization && state.authorization.rules) || [])
    .filter((row) => row.status === 'EFFECTIVE');
  if (!rules.length) {
    try {
      rules = (await GET('/authorization/rules?status=EFFECTIVE'));
    } catch (e) {
      return toast(e.message, true);
    }
  }
  if (!rules.length) return toast('还没有已生效的授权规则，请先创建并生效规则', true);
  const options = rules.map((row) =>
    `<option value="${row.id}"${row.id === ruleId ? ' selected' : ''}>
      ${esc(row.code)} ${esc(row.title)}</option>`).join('');
  openModal('申请授权例外', `
    <div class="field"><label>依据规则 *</label>
      <select id="aeRule">${options}</select></div>
    <div class="field"><label>例外标题 *</label>
      <input id="aeTitle" placeholder="如 试点期间临时保留旧审批层级"></div>
    <div class="field"><label>申请原因 *</label>
      <textarea id="aeReason" rows="3" placeholder="为什么必须破例、影响范围、为什么不能走标准路径"></textarea></div>
    <div class="field"><label>适用范围</label>
      <textarea id="aeScope" rows="2" placeholder="流程/组织/时间窗口"></textarea></div>
    <div class="field"><label>失效日期（批准前必填）</label><input id="aeExpires" type="date"></div>
    <div class="note">例外必须绑定一条已生效规则并设置失效日期；批准后到期需复盘，
      未复盘例外会进入治理待办。</div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="authorization.submitException">提交申请</button>`);
}

async function submitException() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const payload = {
    rule_id: Number(val('aeRule')),
    title: val('aeTitle'),
    reason: val('aeReason'),
    scope: val('aeScope') || null,
    expires_at: val('aeExpires') ? val('aeExpires') + 'T00:00:00' : null,
  };
  if (!payload.title || !payload.reason) return toast('例外标题与原因不能为空', true);
  try {
    await POST('/authorization/exceptions', payload);
    closeModal();
    toast('例外已提交，等待审批');
    RENDERERS.authorization();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 渲染 */

function scopeLabel(row) {
  if (row.process_code) return `流程 ${row.process_code}`;
  if (row.org_unit_name) return `组织 ${row.org_unit_name}`;
  return '集团通用';
}

function ruleRows(rules) {
  return rules.map((row) => `
    <tr>
      <td><b>${esc(row.title)}</b>
        <div class="tiny">${esc(row.code)} · ${esc(row.matter)}</div></td>
      <td><span class="tag t-blu">${esc(row.category_label || row.category)}</span>
        <div class="tiny">${esc(row.risk_level_label || row.risk_level)}风险</div></td>
      <td>${esc(scopeLabel(row))}
        <div class="tiny">${esc(row.approver_role_name || row.approver_label || '未指定审批角色')}</div></td>
      <td>${row.amount_limit === null ? '不限' : num(row.amount_limit, 0)}</td>
      <td><span class="tag ${RULE_TONE[row.status] || 't-gry'}">${esc(row.status_label)}</span>
        <div class="tiny">v${row.version}</div></td>
      <td class="gap">
        <button class="btn-sm" data-act="authorization.edit" data-id="${row.id}">编辑</button>
        ${row.status === 'DRAFT'
          ? `<button class="btn-sm" data-act="authorization.activate" data-id="${row.id}">
               生效</button>
             <button class="btn-sm" data-act="authorization.delete" data-id="${row.id}">
               删除</button>`
          : ''}
        ${row.status === 'EFFECTIVE'
          ? `<button class="btn-sm" data-act="authorization.retire" data-id="${row.id}">
               停用</button>
             <button class="btn-sm" data-act="authorization.newException" data-id="${row.id}">
               申请例外</button>`
          : ''}
      </td>
    </tr>`).join('') || emptyRow(6, '还没有授权规则');
}

function exceptionRows(rows) {
  return rows.map((row) => `
    <tr>
      <td><b>${esc(row.title)}</b>
        <div class="tiny">${esc(row.code)} · ${esc(row.rule_code || '')}</div></td>
      <td>${esc(row.reason)}
        ${row.scope ? `<div class="tiny muted">${esc(row.scope)}</div>` : ''}</td>
      <td><span class="tag ${EXC_TONE[row.status] || 't-gry'}">${esc(row.status_label)}</span>
        ${row.review_due_at ? `<div class="tiny">复盘截止 ${esc(row.review_due_at)}</div>` : ''}
        ${row.reviewed_at ? `<div class="tiny">已复盘</div>` : ''}</td>
      <td>${esc(row.requested_by_name || '—')}
        <div class="tiny">${esc(row.decided_by_name || '待审批')}</div></td>
      <td class="gap">
        ${row.status === 'REQUESTED'
          ? `<button class="btn-sm" data-act="authorization.approve" data-id="${row.id}">
               批准</button>
             <button class="btn-sm" data-act="authorization.reject" data-id="${row.id}">
               驳回</button>`
          : ''}
        ${row.status === 'APPROVED'
          ? `<button class="btn-sm" data-act="authorization.closeException" data-id="${row.id}">
               关闭</button>`
          : ''}
        ${row.review_due_at && !row.reviewed_at
          ? `<button class="btn-sm" data-act="authorization.reviewException" data-id="${row.id}">
               复盘</button>`
          : ''}
      </td>
    </tr>`).join('') || emptyRow(5, '还没有例外记录');
}

const renderAuthorization = () => {
  renderAsync(
    'authorization',
    () => Promise.all([
      GET('/authorization/rules'),
      GET('/authorization/exceptions'),
      GET('/authorization/meta'),
    ]).then(([rules, exceptions, meta]) => ({ rules, exceptions, meta })),
    (data) => {
      state.authorization = { ...(state.authorization || {}), ...data };
      const effective = data.rules.filter((row) => row.status === 'EFFECTIVE').length;
      const openExceptions = data.exceptions.filter(
        (row) => row.status === 'REQUESTED' || row.status === 'APPROVED').length;
      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>授权矩阵<span class="module-badge">A/B/C/D · 例外台账</span></h2>
              <div class="desc">统一原则、分级授权、受控差异；规则生效前必须补齐审批角色、
                例外路径与审批证据</div></div>
            <div class="gap">
              <button class="btn btn-g" data-act="authorization.newException">+ 申请例外</button>
              <button class="btn btn-p" data-act="authorization.newRule">+ 新建规则</button>
            </div>
          </div>
          <div class="gap mt">
            <span class="tag t-grn">已生效规则 ${effective}</span>
            <span class="tag t-yel">未闭环例外 ${openExceptions}</span>
          </div>
        </div>
        <div class="card">
          <div class="seg mb">
            <button class="on" data-act="authorization.tab" data-pane="rules">授权规则</button>
            <button data-act="authorization.tab" data-pane="exceptions">例外台账</button>
          </div>
          <div data-az-pane="rules">
            <table class="tbl">
              <thead><tr><th>规则 / 事项</th><th>类别</th><th>范围 / 审批角色</th>
                <th>金额上限</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>${ruleRows(data.rules)}</tbody>
            </table>
          </div>
          <div data-az-pane="exceptions" class="hide">
            <table class="tbl">
              <thead><tr><th>例外 / 依据规则</th><th>原因 / 范围</th><th>状态</th>
                <th>申请 / 审批</th><th>操作</th></tr></thead>
              <tbody>${exceptionRows(data.exceptions)}</tbody>
            </table>
          </div>
        </div>`;
    },
  );
};

export { renderAuthorization };
