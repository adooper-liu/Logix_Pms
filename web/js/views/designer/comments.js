/* BPMN 元素评论：选中节点/连线后查看讨论、添加评论并解决。 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { GET, POST } from '../../core/api.js';

export function createComments(ctx) {
  function currentElement() {
    const selected = (state.designer.bpmnSelection || [])[0];
    if (!selected || !selected.businessObject) return null;
    return selected;
  }

  async function open() {
    const element = currentElement();
    if (!element) return toast('先在画布上选中一个节点或连线', true);
    const processId = state.designer.processId;
    const bo = element.businessObject;
    const elementId = bo.id;
    let rows = [];
    try {
      rows = await GET(
        `/processes/${processId}/comments?element_id=${encodeURIComponent(elementId)}`,
      );
    } catch (e) {
      return toast(e.message, true);
    }
    const list = rows.length
      ? rows.map((row) => `
        <div class="between bpmn-node-row">
          <div><b>${esc(row.author_name || '—')}</b>
            <span class="tag ${row.status === 'RESOLVED' ? 't-grn' : 't-yel'}">${esc(row.status_label)}</span>
            <div class="tiny">${esc(row.body)}</div>
            <div class="tiny muted">${esc(row.created_at || '')}</div></div>
          ${row.status === 'OPEN'
            ? `<button class="btn-sm" data-act="designer.resolveComment"
                data-id="${row.id}">解决</button>` : ''}
        </div>`).join('')
      : '<div class="tiny muted">这个元素还没有评论</div>';
    openModal('元素评论 · ' + (bo.name || elementId), `
      <div class="note mb">评论只围绕当前元素；解决后保留历史。</div>
      <div id="bpmnCommentList">${list}</div>
      <h3 class="mt">添加评论</h3>
      <div class="field"><textarea id="bpmnCommentBody" rows="3"
        placeholder="说明问题、建议或评审意见"></textarea></div>`,
    `<button class="btn btn-g" data-act="designer.close">关闭</button>
     <button class="btn btn-p" data-act="designer.addComment"
       data-element="${esc(elementId)}"
       data-name="${esc(bo.name || '')}"
       data-type="${esc(String(bo.$type || '').replace('bpmn:', ''))}">提交评论</button>`);
  }

  async function add(elementId, elementName, elementType) {
    const body = (document.getElementById('bpmnCommentBody')?.value || '').trim();
    if (!body) return toast('评论内容不能为空', true);
    try {
      await POST(`/processes/${state.designer.processId}/comments`, {
        element_id: elementId,
        element_name: elementName || null,
        element_type: elementType || null,
        body,
      });
      toast('评论已添加');
      await open();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function resolve(commentId) {
    try {
      await POST(
        `/processes/${state.designer.processId}/comments/${commentId}/resolve`,
        {},
      );
      toast('评论已解决');
      await open();
    } catch (e) {
      toast(e.message, true);
    }
  }

  return { open, add, resolve, close: closeModal };
}
