/* 工具按生命周期挂在对应页面上。点名称先到工具箱看介绍，再从右侧填写。 */

import { esc } from '../../core/format.js';
import { on } from '../../core/ui.js';
import { go, urlParams } from '../../core/router.js';
import { state } from '../../core/state.js';

const TOOL_MOUNTS = {
  strategy: ['OGSM', 'SWOT', 'GOAL-TREE', 'DECISION-MATRIX'],
  analysis: ['SIPOC', 'SWIMLANE', 'VSM', 'FIVE-WHY', 'FISHBONE', 'PARETO', 'CJM', 'QUEUE-MODEL'],
  mining: ['PROCESS-MINING', 'MINING-CONT'],
  design: ['BPR6', 'TOBE', 'RACI', 'FMEA', 'LEAN7', 'KANBAN', 'DESIGN-THINKING', 'BPMN'],
  kpi: ['BALANCED-SCORE', 'BI-DASHBOARD', 'CONTROL-CHART'],
  change: ['ADKAR', 'STAKEHOLDER', 'TRAINING-MATRIX', 'PILOT', 'COMM-PLAN', 'GOLIVE', 'ROLLBACK', 'PDCA', 'DMAIC', 'KAIZEN'],
  knowledge: ['KB'],
};

on('toolmount.open', ({ code, process }) => {
  if (!code) return;
  const params = { open: code, nav: 'tools' };
  const context = urlParams();
  if (context.lifecycle) {
    state.toolbox.step = '';
    params.lifecycle = context.lifecycle;
    if (context.process) params.process = context.process;
    if (context.project) params.project = context.project;
  } else if (process) params.process = process;
  go('toolbox', { params, push: true });
});

function toolMountHtml(tools, host, processId) {
  const codes = TOOL_MOUNTS[host] || [];
  const byCode = new Map((tools || []).map((tool) => [tool.code, tool]));
  const buttons = codes.map((code) => byCode.get(code)).filter(Boolean).map((tool) => `
    <button type="button" class="btn btn-g" data-act="toolmount.open" data-code="${esc(tool.code)}"
      ${processId ? `data-process="${processId}"` : ''}
      title="${esc(tool.when_to_use || '先看介绍，再填写')}">${esc(tool.name)}</button>`).join('');
  if (!buttons) return '';
  return `
    <div class="tool-mount">
      <div class="desc">先看介绍，再从右侧填写并挂上。</div>
      <div class="gap tool-mount-row">${buttons}</div>
    </div>`;
}

export { TOOL_MOUNTS, toolMountHtml };
