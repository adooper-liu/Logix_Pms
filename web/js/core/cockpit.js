/* 运营驾驶舱：一个入口，五个页签。
 *
 * 总览复用管理驾驶舱，其余页签复用运营监控；视图本身不合并，
 * 只合并导航和页签，避免把两套加载逻辑硬塞进一个巨型函数。
 */
import { on } from './ui.js';
import { go } from './router.js';

export const COCKPIT_TABS = [
  { key: 'overview', label: '总览', view: 'dashboard' },
  { key: 'kpi', label: 'KPI', view: 'monitor', tab: 'kpi' },
  { key: 'exceptions', label: '异常', view: 'monitor', tab: 'exceptions' },
  { key: 'workload', label: '工作量', view: 'monitor', tab: 'workload' },
  { key: 'mining', label: '过程挖掘', view: 'monitor', tab: 'mining' },
];

export function cockpitTabBar(active) {
  return `<div class="card cockpit-tabs"><div class="seg">${
    COCKPIT_TABS.map((tab) => `<button class="${tab.key === active ? 'on' : ''}"
      data-act="cockpit.tab" data-view="${tab.view}"
      data-tab="${tab.tab || ''}">${tab.label}</button>`).join('')}</div></div>`;
}

on('cockpit.tab', ({ view, tab }) => {
  go(view, { params: tab ? { tab } : {}, push: true });
});
