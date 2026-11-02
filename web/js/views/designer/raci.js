/* 设计器「权责」页签：事项 × 治理角色 × A/R/C/I。
 *
 * 同一事项必须且只能有一个 A；矩阵不完整时会在页面上提示，
 * 治理扫描也会生成 RACI_INVALID 待办。
 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal, on } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { POST, DEL } from '../../core/api.js';
import { canManage } from '../../core/auth.js';
import { RENDERERS, go } from '../../core/router.js';

const RACI_TONE = { A: 't-red', R: 't-blu', C: 't-yel', I: 't-gry' };

on('designer.openRuntime', () => {
  const processId = state.designer.processId;
  go('execution', {
    params: processId ? { tab: 'config', process: processId } : { tab: 'config' },
    push: true,
  });
});

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
              ? '<button class="btn btn-g" data-act="designer.openRuntime">打开运行配置</button>' : ''}
            ${canManage()
              ? '<button class="btn btn-p" data-act="designer.raciNew">+ 事项权责</button>' : ''}
          </div>
        </div>
        <div class="hint mb">权责不派待办。R 只说明谁负责动手，候选人要在运行配置里另行保存。
          权责矩阵是「一条流程一套」，不是全公司共用一张表。
          当前事项只属于本流程；换流程后矩阵可以完全不同。
          治理角色（如「集团战略流程所有者」）是全公司角色库，各流程从里面选来填 A/R/C/I——
          <b>角色可共用，事项怎么分工按流程各自配</b>。事项数量不固定，用「+ 事项权责」按需增加。</div>
        ${raciHelpHtml()}
        ${errors}
        <table class="tbl">
          <thead><tr><th>事项 / 决策</th><th>角色与 RACI</th></tr></thead>
          <tbody>${matters}</tbody>
        </table>
        <div class="note">治理扫描会把“没有 A”或“多个 A”的事项列入 RACI_INVALID 待办。</div>
      </div>`;
  }

  function raciHelpHtml() {
    return `
      <details class="raci-help mb">
        <summary>权责帮助说明（原理 · 用途 · 操作 · 影响）</summary>
        <div class="raci-help-body">
          <p>本页管的是治理上「这件事谁拍板」，<b>不是</b>画布上谁领任务，也<b>不是</b> PCE 计算公式。</p>
          <h4>原理（RACI）</h4>
          <table class="tbl">
            <thead><tr><th>字母</th><th>含义</th><th>本系统规则</th></tr></thead>
            <tbody>
              <tr><td><b>A</b></td><td>Accountable，最终负责、可拍板</td>
                <td>每个事项有且仅有 1 个 A</td></tr>
              <tr><td><b>R</b></td><td>Responsible，动手执行</td><td>可多个</td></tr>
              <tr><td><b>C</b></td><td>Consulted，事先征求意见</td>
                <td>可多个；过多会拖决策</td></tr>
              <tr><td><b>I</b></td><td>Informed，事后知会</td><td>可多个</td></tr>
            </tbody>
          </table>
          <p>表中每一行是「事项 / 决策」（如 KPI 口径确认、例外审批），属于流程治理决策点，
            <b>不是</b> BPMN 活动节点。</p>
          <h4>别和旁边几套「责任」搞混</h4>
          <table class="tbl">
            <thead><tr><th>位置</th><th>回答什么</th></tr></thead>
            <tbody>
              <tr><td><b>权责</b>（本页）</td><td>关键事项上谁 A / R / C / I</td></tr>
              <tr><td>属性「责任」</td><td>活动节点挂哪个 L4、哪个岗位（汇总用）</td></tr>
              <tr><td>属性「执行」分派</td><td>运行时谁领任务</td></tr>
              <tr><td>授权矩阵</td><td>按金额 / 风险谁有权批（规则库）</td></tr>
            </tbody>
          </table>
          <h4>用途</h4>
          <ul>
            <li>把「口头扯皮」写成可检查矩阵：变更谁批、例外谁批、KPI 谁定口径。</li>
            <li>给阶段 3 / 治理扫描提供证据：缺 A 或多 A → RACI_INVALID 待办。</li>
            <li>和授权矩阵配合：权责说「角色关系」，授权说「什么条件下能批」。</li>
          </ul>
          <h4>价值</h4>
          <ul>
            <li><b>决策清晰</b>：出事能问到唯一的 A，而不是「大家都负责」。</li>
            <li><b>减少无效会签</b>：C / I 可控，避免人人签字拖周期（间接有利于等待，但本页不算 PCE）。</li>
            <li><b>上线 / 审计可核</b>：流程卡、启动证据会看权责是否完整。</li>
          </ul>
          <p>没有权责矩阵，模型能画、也能跑实例，但治理不闭环——改善项目和建体系阶段会卡住。</p>
          <h4>如何操作</h4>
          <p>需管理权限；治理角色先在「组织与人员 → 治理角色」维护。</p>
          <ol>
            <li>设计器顶栏打开「权责」。</li>
            <li>点「+ 事项权责」。</li>
            <li>填事项名称（可复用已有）、治理角色、RACI（A/R/C/I）、可选说明。</li>
            <li>同一事项多次添加不同角色，凑齐 A / R / C / I。</li>
            <li>看每行是否「A 已明确」、页头是否「矩阵完整」。</li>
            <li>标签上的 × 可移除错误分配。</li>
          </ol>
          <p>同一「事项 + 角色」再保存会覆盖；同一事项不能有两个 A。</p>
          <h4>影响什么 / 不影响什么</h4>
          <p><b>会影响</b>：治理扫描与待办（RACI_INVALID）；流程卡 / 启动就绪里的权责证据；
            人对「谁说了算」的理解；变更 / 例外类事项常与「变更」页、授权规则一起用。</p>
          <p><b>不会直接影响</b>：BPMN 结构、节点测算与 PCE（PCE 只吃作业 / 等待 / 增值等）；
            执行引擎谁领任务；不会自动改审批流（审批在授权矩阵 / 执行规则）。</p>
          <p class="note" style="margin:8px 0 0">一句话：权责 = 关键决策的责任合同；先定 A，再配 R/C/I；
            保证治理可追责，不直接改 PCE，但能减少「多人拍板」造成的等待与扯皮。</p>
        </div>
      </details>`;
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
