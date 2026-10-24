/* 全局状态。
 *
 * 刻意保持成一个扁平对象：视图之间共享的筛选条件、当前选中项都放这里，
 * 刷新页面即重置。真正的数据永远以服务端为准，这里只存"界面态"。
 */

export const state = {
  view: 'dashboard',
  /** 五个业务枚举的中文标签，首次启动时从后端 meta 接口拉取 */
  meta: { methodology: {}, status: {}, stage: {} },
  map: {
    code: null, name: null, path: [], improvementOnly: false,
    pendingJump: null, navCollapsed: false,
    frameworks: null, benchmarkFramework: '', benchmark: null,
  },
  projects: { filter: { methodology: '', status: '', stage: '' }, keyword: '' },
  workflow: { tab: 'steps', stage: 1 },
  /** 从步骤页进入工具箱时只显示该步骤的推荐工具；null 表示显示全部 */
  toolboxFilter: null,
  designer: {
    processId: null, processCode: null, model: null, analysis: null, tab: 'model',
    changes: null, changeMeta: null, raci: null, raciMeta: null, governanceRoles: null,
  },
  knowledge: { type: '', sort: 'recent', keyword: '', tag: '', page: 1 },
  pcf: {
    framework: 'APQC_PCF', frameworks: null, tree: null, treeFramework: null,
    expanded: new Set(), selectedId: null, keyword: '',
  },
  monitor: { status: '', tab: 'overview', kind: '', period: '' },
  strategy: { year: new Date().getFullYear() },
  dataGov: null,
  execution: { tab: 'tasks', filter: 'open' },
  deliverables: {
    tab: 'project', projectId: null, templateTool: '', templateFormat: '',
    documentProcessId: null, documentCategory: '', documentOrgUnitId: null,
    templateOrgUnitId: null,
  },
};

export const TITLES = {
  dashboard: '管理驾驶舱',
  map: '企业流程地图',
  workflow: '五阶段标准工作流',
  projects: '流程项目组合',
  execution: '流程执行',
  toolbox: '方法论工具箱',
  designer: '流程设计器',
  monitor: '运营监控与KPI',
  strategy: '战略目标',
  data: '数据治理',
  knowledge: '流程知识库',
  pcf: 'PCF 分类框架',
  deliverables: '交付物与模板库',
  orgs: '组织与人员',
  sketches: '架构草图',
};
