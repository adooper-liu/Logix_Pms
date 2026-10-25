/* 决策表：查看受控决策表并用一组输入试算。 */

import { esc } from '../../core/format.js';
import { toast, openModal } from '../../core/ui.js';
import { GET, POST } from '../../core/api.js';

export function createDecisions() {
  async function open() {
    let tables = [];
    try {
      tables = await GET('/decisions');
    } catch (e) {
      return toast(e.message, true);
    }
    if (!tables.length) {
      return openModal('决策表', `
        <div class="empty">还没有决策表。流程管理科可以通过
          <code>POST /api/v1/decisions</code> 创建首张表。</div>`,
      '<button class="btn btn-g" data-act="designer.close">关闭</button>');
    }
    const options = tables.map((row) =>
      `<option value="${esc(row.code)}">${esc(row.code)} · ${esc(row.name)} v${row.version}</option>`).join('');
    openModal('决策表试算', `
      <div class="note mb">先选表，再输入 JSON；求值只读，不会改流程状态。</div>
      <div class="field"><label>决策表</label><select id="dmnTable">${options}</select></div>
      <div class="field"><label>输入（JSON）</label>
        <textarea id="dmnInput" rows="4">{}</textarea></div>
      <div id="dmnResult" class="mt"></div>`,
    `<button class="btn btn-g" data-act="designer.close">关闭</button>
     <button class="btn btn-p" data-act="designer.evaluateDecision">求值</button>`);
  }

  async function evaluate() {
    const code = document.getElementById('dmnTable')?.value;
    const raw = document.getElementById('dmnInput')?.value || '{}';
    let inputs;
    try {
      inputs = JSON.parse(raw);
    } catch (_) {
      return toast('输入不是合法 JSON', true);
    }
    try {
      const result = await POST(`/decisions/${encodeURIComponent(code)}/evaluate`, { inputs });
      const box = document.getElementById('dmnResult');
      box.innerHTML = `
        <div class="note ${result.matched ? '' : 'warnbox'}">
          ${result.matched ? '命中 ' + result.matched_count + ' 条规则' : '没有命中规则'}
        </div>
        <div class="field"><label>输出</label>
          <pre>${esc(JSON.stringify(result.outputs, null, 2))}</pre></div>`;
    } catch (e) {
      toast(e.message, true);
    }
  }

  return { open, evaluate };
}
