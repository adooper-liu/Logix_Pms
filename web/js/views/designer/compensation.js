/* 取消补偿动作配置：按流程列出节点补偿动作，Manager 可新增/修改。 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { GET, POST } from '../../core/api.js';

export function createCompensation() {
  async function open() {
    const processId = state.designer.processId;
    if (!processId) return toast('请先选择流程', true);
    let rows = [];
    try {
      rows = await GET(`/processes/${processId}/compensations`);
    } catch (e) {
      return toast(e.message, true);
    }
    const list = rows.length
      ? rows.map((row) => `
        <div class="between bpmn-node-row">
          <span><b>${esc(row.node_key)}</b> · ${esc(row.name)}
            ${row.is_active ? '' : '<span class="tag t-gry">停用</span>'}
            <div class="tiny">${esc(row.description || '—')}</div></span>
        </div>`).join('')
      : '<div class="tiny muted">还没有配置补偿动作</div>';
    openModal('取消补偿动作', `
      <div class="note mb">实例取消时，已执行且配置了补偿动作的节点会生成补偿待办；
        系统不会自动执行补偿，需人工完成并留痕。</div>
      ${list}
      <h3 class="mt">新增 / 修改</h3>
      <div class="row2">
        <div class="field"><label>节点 key *</label><input id="cpNode" placeholder="如 n3"></div>
        <div class="field"><label>动作名称 *</label><input id="cpName" placeholder="如 通知供应商取消订单"></div>
      </div>
      <div class="field"><label>说明</label><textarea id="cpDesc" rows="2"
        placeholder="补偿范围、责任人、证据要求"></textarea></div>`,
    `<button class="btn btn-g" data-act="designer.close">关闭</button>
     <button class="btn btn-p" data-act="designer.saveCompensation">保存动作</button>`);
  }

  async function save() {
    const val = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };
    if (!val('cpNode') || !val('cpName')) return toast('节点 key 与动作名称不能为空', true);
    try {
      await POST(`/processes/${state.designer.processId}/compensations`, {
        node_key: val('cpNode'),
        name: val('cpName'),
        description: val('cpDesc') || null,
      });
      toast('补偿动作已保存');
      await open();
    } catch (e) {
      toast(e.message, true);
    }
  }

  return { open, save, close: closeModal };
}
