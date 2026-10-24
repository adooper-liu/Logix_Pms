/* 设计器「权责」页签：事项 × 治理角色 × A/R/C/I。
 *
 * 同一事项必须且只能有一个 A；矩阵不完整时会在页面上提示，
 * 治理扫描也会生成 RACI_INVALID 待办。
 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal, on } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { POST, DEL } from '../../core/api.js';import { canManage } from '../../core/auth.js';
import { RENDERERS } from '../../core/router.js';

const RACI_TONE = { A: 't-red', R: 't-blu', C: 't-yel', I: 't-gry' };

export function createRaci(ctx) {
  function meta() {
    return state.designer.raciMeta || { role_type_labels: {}, raci_labels: {} };
  }

  function paneHtml() {
    const matrix = state.designer.raci;
    if (!matrix) {
      return '<div class="card"><div class="empty">正在加载权责矩阵…</div></div>';
    }
    const labels = meta();
    const matters = (matrix.matters || []).map((matter) => {
      const entries = matter.entries.map((entry) => `
        <span class="tag ${RACI_TONE[entry.raci] || 't-gry'}" title="${esc(entry.note || '')}">
          ${esc(entry.raci)} · ${esc(entry.role_name || '—')}
          ${canManage()
            ? `<button class="btn-sm" data-act="designer.raciRemove"
                data-id="${entry.id}" title="移除">×</button>` : ''}
        </span>`).join(' ') || '<span class="muted">还没有角色</span>';
      return `
        <tr>
          <td><b>${esc(matter.matter)}</b>
            ${matter.has_accountable
              ? '<span class="tag t-grn">A 已明确</span>'
              : '<span class="tag t-red">缺少 A</span>'}</td>
          <td>${entries}</td>
        </tr>`;
    }).join('') || emptyRow();

    const errors = (matrix.errors || []).length
      ? `<div class="warnbox mb">${matrix.errors.map((item) => esc(item)).join('；')}</div>`
      : '';

    return `
      <div class="card">
        <div class="between mb">
          <div><h3 style="margin:0">权责矩阵（${(matrix.matters || []).length} 个事项）</h3>
            <div class="desc" style="margin:2px 0 0">
              ${esc(matrix.process_code || '')} ${esc(matrix.process_name || '')} ·
              A 唯一负责 / R 执行 / C 咨询 / I 知会</div></div>
          <div class="gap">
            <span class="tag ${matrix.valid ? 't-grn' : 't-red'}">${
              matrix.valid ? '矩阵完整' : '矩阵不完整'}</span>
            ${canManage()
              ? '<button class="btn btn-p" data-act="designer.raciNew">+ 事项权责</button>' : ''}
          </div>
        </div>
        ${errors}
        <table class="tbl">
          <thead><tr><th>事项 / 决策</th><th>角色与 RACI</th></tr></thead>
          <tbody>${matters}</tbody>
        </table>
        <div class="note">治理扫描会把“没有 A”或“多个 A”的事项列入 RACI_INVALID 待办。</div>
      </div>`;
  }

  function emptyRow() {
    return '<tr><td colspan="2"><div class="empty">还没有配置事项权责</div></td></tr>';
  }

  function raciModal() {
    const labels = meta();
    const roles = (state.designer.governanceRoles || []).map((role) =>
      `<option value="${role.id}">${esc(role.name)} · ${esc(role.role_type_label)}</option>`)
      .join('');
    const raciOptions = Object.entries(labels.raci_labels || {}).map(([value, label]) =>
      `<option value="${esc(value)}">${esc(label)}</option>`).join('');
    const matters = (state.designer.raci && state.designer.raci.matters || [])
      .map((matter) => `<option value="${esc(matter.matter)}"></option>`).join('');
    openModal('配置事项权责', `
      <div class="field"><label>事项 / 决策 *</label>
        <input id="raMatter" list="raMatterList" placeholder="如 流程变更审批 / KPI 口径确认">
        <datalist id="raMatterList">${matters}</datalist></div>
      <div class="row2">
        <div class="field"><label>治理角色 *</label>
          <select id="raRole"><option value="">请选择</option>${roles}</select></div>
        <div class="field"><label>RACI *</label>
          <select id="raRaci">${raciOptions}</select></div>
      </div>
      <div class="field"><label>说明</label>
        <input id="raNote" placeholder="如 由集团端到端所有者最终拍板"></div>
      <div class="note">同一事项只能有一个 A；重复提交同一「事项 + 角色」会覆盖原值。</div>`,
      `<button class="btn btn-g" data-act="designer.raciClose">取消</button>
       <button class="btn btn-p" data-act="designer.raciSubmit">保存</button>`);
  }

  async function submitRaci() {
    const val = (id) => {
      const el = document.getElementById(id);
      return el ? el.value : '';
    };
    const matter = val('raMatter').trim();
    if (!matter) return toast('请填写事项', true);
    if (!val('raRole')) return toast('请选择治理角色', true);
    try {
      await POST('/governance/raci', {
        process_id: state.designer.processId,
        matter,
        role_id: Number(val('raRole')),
        raci: val('raRaci'),
        note: val('raNote').trim() || null,
      });
      closeModal();
      toast('权责矩阵已更新');
      state.designer.tab = 'raci';
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function removeRaci(raciId) {
    try {
      await DEL('/governance/raci/' + raciId);
      toast('权责记录已移除');
      state.designer.tab = 'raci';
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  }

  on('designer.raciNew', () => raciModal());
  on('designer.raciClose', () => closeModal());
  on('designer.raciSubmit', () => submitRaci());
  on('designer.raciRemove', ({ id }) => removeRaci(Number(id)));

  return { paneHtml };
}
