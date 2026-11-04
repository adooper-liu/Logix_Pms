/* 运营驾驶舱：一个入口。
 *
 * 总览复用管理驾驶舱。流程分析只列六项已有记录。
 * 其余页签复用运营监控；视图本身不合并。
 */
import { esc } from './format.js';
import { on } from './ui.js';
import { state } from './state.js';
import { GET } from './api.js';
import { go, urlParams, setUrlState, RENDERERS } from './router.js';

export const COCKPIT_TABS = [
  { key: 'overview', label: '总览', view: 'dashboard' },
  { key: 'analysis', label: '流程分析', view: 'monitor', tab: 'analysis' },
  { key: 'kpi', label: 'KPI', view: 'monitor', tab: 'kpi' },
  { key: 'exceptions', label: '异常', view: 'monitor', tab: 'exceptions' },
  { key: 'workload', label: '工作量', view: 'monitor', tab: 'workload' },
  { key: 'mining', label: '过程挖掘', view: 'monitor', tab: 'mining' },
];

export function cockpitProcessSelect(processes) {
  const selected = state.cockpit.processId;
  const options = (processes || []).map((row) =>
    `<option value="${row.id}"${row.id === selected ? ' selected' : ''}>${
      esc(row.code)} ${esc(row.name)}</option>`).join('');
  return `<select class="sel cockpit-process" data-act="cockpit.process" title="按流程">
    <option value="">全部流程</option>${options}</select>`;
}

export function cockpitTabBar(active) {
  return `<div class="card cockpit-tabs"><div class="seg">${
    COCKPIT_TABS.map((tab) => `<button class="${tab.key === active ? 'on' : ''}"
      data-act="cockpit.tab" data-view="${tab.view}"
      data-tab="${tab.tab || ''}">${tab.label}</button>`).join('')
  }</div></div>`;
}

/** L3 清单。地址里的流程不在 L3 里时，补上这一条。 */
export function loadCockpitProcesses() {
  const selected = state.cockpit.processId;
  return GET('/process-map/flat?level=3').then(async (rows) => {
    const list = rows || [];
    if (selected && !list.some((row) => row.id === selected)) {
      const one = await GET('/process-map/' + selected).catch(() => null);
      if (one) return [one, ...list];
    }
    return list;
  }).catch(() => []);
}

function cockpitParams(extra) {
  const params = { ...(extra || {}) };
  if (state.cockpit.processId) params.process = state.cockpit.processId;
  return params;
}

on('cockpit.tab', ({ view, tab }) => {
  const current = urlParams();
  const params = cockpitParams(tab ? { tab } : {});
  if (current.lifecycle) {
    params.lifecycle = current.lifecycle;
    if (current.project) params.project = current.project;
  }
  go(view, { params, push: true });
});

on('cockpit.process', (_data, el) => {
  state.cockpit.processId = Number(el.value) || null;
  const params = urlParams();
  if (state.cockpit.processId) params.process = String(state.cockpit.processId);
  else {
    params.process = '';
    params.project = '';
    params.lifecycle = '';
  }
  const view = state.view === 'monitor' ? 'monitor' : 'dashboard';
  setUrlState(view, params, { push: false });
  if (RENDERERS[view]) RENDERERS[view]();
});
