/* 设计器「变更」页签：变更申请、影响分析与审批。
 *
 * 变更单是发布门禁的证据：启用门禁的流程必须带着一张已批准的变更单发布。
 */

import { esc } from '../../core/format.js';
import {
  toast,
  openModal,
  closeModal,
  confirmDialog,
  promptDialog,
  on,
} from '../../core/ui.js';
import { state } from '../../core/state.js';
import { GET, POST, PATCH } from '../../core/api.js';
import { canManage } from '../../core/auth.js';
import { RENDERERS } from '../../core/router.js';

const STATUS_TONE = {
  DRAFT: 't-gry',
  SUBMITTED: 't-yel',
  APPROVED: 't-blu',
  REJECTED: 't-red',
  APPLIED: 't-grn',
  CANCELLED: 't-gry',
};

export function createChanges(ctx) {
  function meta() {
    return state.designer.changeMeta || {
      change_type_labels: {},
      impact_level_labels: {},
      status_labels: {},
      impact_keys: [],
      impact_labels: {},
    };
  }

  function paneHtml() {
    const st = state.designer;
    const labels = meta();
    const rows = (st.changes || []).map((row) => {
      const actions = [];
      if (canManage()) {
        if (row.status === 'DRAFT') {
          actions.push(
            `<button class="btn-sm" data-act="designer.changeEdit" data-id="${row.id}">编辑</button>`,
            `<button class="btn-sm btn-p" data-act="designer.changeSubmit" data-id="${row.id}">提交</button>`,
            `<button class="btn-sm btn-g" data-act="designer.changeCancel" data-id="${row.id}">取消</button>`,
          );
        } else if (row.status === 'SUBMITTED') {
          actions.push(
            `<button class="btn-sm btn-p" data-act="designer.changeApprove" data-id="${row.id}">批准</button>`,
            `<button class="btn-sm btn-g" data-act="designer.changeReject" data-id="${row.id}">驳回</button>`,
          );
        } else if (row.status === 'APPROVED') {
          actions.push(
            `<button class="btn-sm btn-g" data-act="designer.changeCancel" data-id="${row.id}">取消</button>`,
          );
        }
      }
      const impactCount = (labels.impact_keys || [])
        .filter((key) => (row.impact && row.impact[key] || '').trim()).length;
      const versions = (row.linked_versions || [])
        .map((item) => 'v' + item.version).join('、') || '—';
      return `
        <tr>
          <td><b>${esc(row.title)}</b>
            <div class="tiny">${esc(row.code)} · ${esc(row.process_code || '')}
              ${esc(row.process_name || '')}</div></td>
          <td>${esc(row.change_type_label)}<div class="tiny">${esc(row.impact_level_label)}
            ${row.version_label ? ' · ' + esc(row.version_label) : ''}</div></td>
          <td>${impactCount}/${(labels.impact_keys || []).length}
            <div class="tiny">${esc(row.requested_by_name || '—')}</div></td>
          <td><span class="tag ${STATUS_TONE[row.status] || 't-gry'}">${
            esc(row.status_label)}</span>
            ${row.approved_by_name ? `<div class="tiny">${esc(row.approved_by_name)}</div>` : ''}</td>
          <td class="tiny">${esc(versions)}</td>
          <td><div class="gap">${actions.join('') || '<span class="muted">—</span>'}</div></td>
        </tr>`;
    }).join('') || emptyChangeRow();

    const gate = st.model && st.model.requires_change_request
      ? '<div class="note mb">该流程启用了变更门禁：发布模型前必须有一张「已批准」的变更申请。</div>'
      : '';

    return `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">变更申请（${(st.changes || []).length}）</h3>
            <div class="desc" style="margin:2px 0 0">重大变更需填写完整影响分析、
              测试证据与回退方案；审批通过后才能用于门禁发布</div></div>
          ${canManage()
            ? '<button class="btn btn-p" data-act="designer.changeNew">+ 变更申请</button>' : ''}
        </div>
        ${gate}
        <table class="tbl">
          <thead><tr><th>变更</th><th>类型 / 级别</th><th>影响分析</th>
            <th>状态</th><th>关联版本</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function emptyChangeRow() {
    return '<tr><td colspan="6"><div class="empty">还没有变更申请</div></td></tr>';
  }

  async function editChange(changeId) {
    try {
      const row = await GET('/changes/' + changeId);
      changeModal(row);
    } catch (e) {
      toast(e.message, true);
    }
  }

  function changeModal(row = null) {
    const labels = meta();
    const value = (key) => (row && row[key] !== null && row[key] !== undefined ? row[key] : '');
    const impact = row ? row.impact || {} : {};
    const typeOptions = Object.entries(labels.change_type_labels).map(([code, label]) =>
      `<option value="${esc(code)}"${code === (value('change_type') || 'STRUCTURE')
        ? ' selected' : ''}>${esc(label)}</option>`).join('');
    const levelOptions = Object.entries(labels.impact_level_labels).map(([code, label]) =>
      `<option value="${esc(code)}"${code === (value('impact_level') || 'MINOR')
        ? ' selected' : ''}>${esc(label)}</option>`).join('');
    const impactFields = (labels.impact_keys || []).map((key) => `
      <div class="field"><label>${esc(labels.impact_labels[key] || key)}</label>
        <input id="ci-${esc(key)}" value="${esc(impact[key] || '')}"
          placeholder="影响范围与应对"></div>`).join('');

    openModal(row ? '编辑变更申请 · ' + row.code : '新建变更申请', `
      <div class="row2">
        <div class="field"><label>变更标题 *</label>
          <input id="chTitle" value="${esc(value('title'))}" placeholder="如 增加供应商准入校验节点"></div>
        <div class="field"><label>目标版本</label>
          <input id="chVersion" value="${esc(value('version_label'))}" placeholder="如 V2.0"></div>
      </div>
      <div class="row2">
        <div class="field"><label>变更类型</label><select id="chType">${typeOptions}</select></div>
        <div class="field"><label>影响级别</label><select id="chLevel">${levelOptions}</select></div>
      </div>
      <div class="row2">
        <div class="field"><label>变更原因</label>
          <textarea id="chReason" rows="2" placeholder="为什么必须变">${esc(value('reason'))}</textarea></div>
        <div class="field"><label>变更范围</label>
          <textarea id="chScope" rows="2" placeholder="涉及的组织、系统、数据与角色">${esc(value('scope'))}</textarea></div>
      </div>
      <div class="grid g2">${impactFields}</div>
      <div class="row2">
        <div class="field"><label>测试证据</label>
          <textarea id="chTest" rows="2" placeholder="测试环境验证与回归结果">${esc(value('test_evidence'))}</textarea></div>
        <div class="field"><label>回退方案</label>
          <textarea id="chRollback" rows="2" placeholder="触发条件、回退步骤与数据补偿">${esc(value('rollback_plan'))}</textarea></div>
      </div>
      <div class="row2">
        <div class="field"><label>生效日期</label>
          <input id="chEffective" type="date" value="${esc(value('effective_date'))}"></div>
        <div class="field"><label>紧急变更</label>
          <select id="chEmergency">
            <option value="false"${value('emergency') ? '' : ' selected'}>否</option>
            <option value="true"${value('emergency') ? ' selected' : ''}>是（事后补齐审批）</option>
          </select></div>
      </div>
      <div class="note">重大变更必须填全 7 项影响分析、测试证据和回退方案，否则不能提交。</div>`,
      `<button class="btn btn-g" data-act="designer.changeClose">取消</button>
       <button class="btn btn-p" data-act="designer.submitChange"
         data-id="${row ? row.id : ''}">${row ? '保存' : '创建'}</button>`);
  }

  async function submitChangeForm(changeId) {
    const val = (id) => {
      const el = document.getElementById(id);
      return el ? el.value : '';
    };
    const labels = meta();
    const title = val('chTitle').trim();
    if (!title) return toast('请填写变更标题', true);
    const impact = {};
    (labels.impact_keys || []).forEach((key) => {
      impact[key] = val('ci-' + key).trim() || null;
    });
    const level = val('chLevel');
    if (level === 'MAJOR') {
      const missing = (labels.impact_keys || []).filter((key) => !impact[key]);
      if (missing.length) return toast('重大变更必须填完整影响分析', true);
      if (!val('chTest').trim()) return toast('重大变更必须填写测试证据', true);
      if (!val('chRollback').trim()) return toast('重大变更必须填写回退方案', true);
    }
    const payload = {
      title,
      reason: val('chReason').trim() || null,
      scope: val('chScope').trim() || null,
      change_type: val('chType'),
      impact_level: level,
      version_label: val('chVersion').trim() || null,
      impact,
      test_evidence: val('chTest').trim() || null,
      rollback_plan: val('chRollback').trim() || null,
      effective_date: val('chEffective') || null,
      emergency: val('chEmergency') === 'true',
    };
    try {
      if (changeId) {
        await PATCH('/changes/' + changeId, payload);
        toast('变更申请已保存');
      } else {
        await POST('/changes', { process_id: state.designer.processId, ...payload });
        toast('变更申请已创建');
      }
      closeModal();
      state.designer.tab = 'change';
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function act(changeId, action, note) {
    try {
      await POST('/changes/' + changeId + '/' + action, note ? { note } : {});
      toast('变更申请已更新');
      state.designer.tab = 'change';
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function approvedForPublish() {
    const cached = (state.designer.changes || []).find((row) => row.status === 'APPROVED');
    if (cached) return cached;
    const pid = state.designer.processId;
    if (!pid) return null;
    try {
      const rows = await GET('/changes?process_id=' + pid + '&status=APPROVED');
      return rows.length ? rows[0] : null;
    } catch (e) {
      toast(e.message, true);
      return null;
    }
  }

  on('designer.changeNew', () => changeModal());
  on('designer.changeEdit', ({ id }) => editChange(Number(id)));
  on('designer.changeClose', () => closeModal());
  on('designer.submitChange', ({ id }) => submitChangeForm(id ? Number(id) : null));
  on('designer.changeSubmit', ({ id }) => act(Number(id), 'submit'));
  on('designer.changeApprove', async ({ id }) => {
    const note = await promptDialog('审批意见（可选）', {
      title: '批准变更', okText: '批准', placeholder: '同意本次变更',
    });
    if (note === null) return;
    act(Number(id), 'approve', note.trim() || null);
  });
  on('designer.changeReject', async ({ id }) => {
    const note = await promptDialog('驳回原因', {
      title: '驳回变更', okText: '驳回', placeholder: '说明需要补充的内容',
    });
    if (note === null) return;
    act(Number(id), 'reject', note.trim() || null);
  });
  on('designer.changeCancel', async ({ id }) => {
    const ok = await confirmDialog('取消这张变更申请？取消后不能再次提交。',
      { title: '取消变更', okText: '取消变更' });
    if (ok) act(Number(id), 'cancel');
  });

  return { paneHtml, approvedForPublish };
}
