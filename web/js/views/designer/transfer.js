/* BPMN 导入 / 导出：文件下载、文件选择与后端覆盖提交。
 *
 * 导入后整页重绘（RENDERERS.designer），因为 BPMN 结构变化会重建画布。
 */

import { toast } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { API_BASE, POST, getToken } from '../../core/api.js';
import { RENDERERS } from '../../core/router.js';

export function createTransfer(ctx) {
  function downloadBpmn(xml) {
    const blob = new Blob([xml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (state.designer.processCode || 'process') + '.bpmn';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function exportBpmn() {
    const id = state.designer.processId;
    if (!id) return toast('请先选择一条流程', true);
    try {
      if (state.designer.bpmnModeler) {
        const ok = await ctx.saveNow();
        if (!ok) return;
      }
      const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
        headers: { Authorization: 'Bearer ' + getToken() },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || ('导出失败（' + res.status + '）'));
      }
      const xml = await res.text();
      downloadBpmn(xml);
      toast('BPMN 已导出');
    } catch (e) {
      toast(e.message, true);
    }
  }

  function importBpmn() {
    const id = state.designer.processId;
    if (!id) return toast('请先选择一条流程', true);
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.bpmn,.xml,text/xml,application/xml';
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      try {
        const xml = await file.text();
        const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + getToken(),
          },
          body: JSON.stringify({
            xml,
            expected_version: state.designer.model ? state.designer.model.version : null,
          }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || ('导入失败（' + res.status + '）'));
        state.designer.model = body;
        state.designer.savedModel = ctx.cloneModel(body);
        state.designer.analysis = await POST(
          '/processes/' + id + '/design/analyze', {});
        toast('BPMN 已导入并更新模型');
        RENDERERS.designer();
      } catch (e) {
        toast(e.message, true);
      }
    };
    input.click();
  }

  return { exportBpmn, importBpmn };
}
