/* 路径模拟：按当前草稿模型枚举路径，展示概率、周期与成本。 */

import { esc, num } from '../../core/format.js';
import { toast, openModal } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { POST } from '../../core/api.js';

export function createSimulation() {
  async function open() {
    const processId = state.designer.processId;
    if (!processId) return toast('请先选择流程', true);
    let result;
    try {
      result = await POST(`/processes/${processId}/design/simulate`, { max_paths: 50 });
    } catch (e) {
      return toast(e.message, true);
    }
    const rows = result.paths.length
      ? result.paths.map((row) => `
        <tr>
          <td>${num(row.probability * 100, 1)}%</td>
          <td class="tiny">${row.node_names.map(esc).join(' → ')}</td>
          <td>${num(row.cycle_minutes, 1)} 分</td>
          <td>${num(row.wait_minutes, 1)} 分</td>
          <td>${num(row.cost, 2)}</td>
        </tr>`).join('')
      : '<tr><td colspan="5" class="muted">没有可枚举的路径</td></tr>';
    openModal('路径模拟', `
      <div class="note mb">基于当前草稿快照做静态路径枚举，不改变运行时；
        概率来自连线配置，未配置时按出边均分或默认分支兜底。</div>
      <div class="grid g4 stat-row">
        <div class="kpi stat"><div class="num">${result.path_count}</div><div class="lab">路径数</div></div>
        <div class="kpi stat"><div class="num">${num(result.total_probability * 100, 1)}<small>%</small></div>
          <div class="lab">已枚举概率</div></div>
        <div class="kpi stat"><div class="num">${num(result.expected_cycle_minutes, 1)}</div>
          <div class="lab">期望周期（分）</div></div>
        <div class="kpi stat"><div class="num">${num(result.expected_cost, 2)}</div>
          <div class="lab">期望单次成本</div></div>
      </div>
      <table class="tbl">
        <thead><tr><th>概率</th><th>路径</th><th>周期</th><th>其中等待</th><th>成本</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`,
    '<button class="btn btn-g" data-act="designer.close">关闭</button>', true);
  }
  return { open };
}
