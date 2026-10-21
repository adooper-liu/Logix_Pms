/* 全局状态。
 *
 * 刻意保持成一个扁平对象：视图之间共享的筛选条件、当前选中项都放这里，
 * 刷新页面即重置。真正的数据永远以服务端为准，这里只存"界面态"。
 */

export const state = {
  view: 'dashboard',
  /** 五个业务枚举的中文标签，首次启动时从后端 meta 接口拉取 */
  meta: { methodology: {}, status: {}, stage: {} },
  map: { code: null, name: null, path: [] },
  projects: { filter: { methodology: '', status: '', stage: '' }, keyword: '' },
  designer: { processId: null, processCode: null, model: null, analysis: null },
  knowledge: { type: '', sort: 'recent', keyword: '', tag: '' },
  monitor: { status: '' },
};

export const TITLES = {
  dashboard: '管理驾驶舱',
  map: '企业流程地图',
  workflow: '五阶段标准工作流',
  projects: '流程项目组合',
  toolbox: '方法论工具箱',
  designer: '流程设计器',
  monitor: '运营监控与KPI',
  knowledge: '流程知识库',
};
