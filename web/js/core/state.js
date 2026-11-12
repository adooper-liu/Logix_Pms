/* 全局状态。
 *
 * 刻意保持成一个扁平对象：视图之间共享的筛选条件、当前选中项都放这里，
 * 刷新页面即重置。真正的数据永远以服务端为准，这里只存"界面态"。
 */

export const state = {
  view: 'dashboard',
  /** 五个业务枚举的中文标签，首次启动时从后端 meta 接口拉取 */
  meta: { methodology: {}, status: {}, stage: {}, setupStage: {} },
  map: {
    code: null, name: null, path: [], improvementOnly: false,
    pendingJump: null, navCollapsed: false, tab: 'architecture',
    coverage: null, coverageError: null, coverageLoading: false, coverageRequest: 0,
    frameworks: null, benchmarkFramework: '', benchmark: null, openCode: null,
    openGuidedPcf: false, guidedPcfExternal: '', guidedPcfFramework: '',
    guidedPcfActivities: true,
  },
  projects: { filter: { methodology: '', status: '', stage: '', projectType: '' },
    keyword: '', openId: null, tab: 'list', newProcess: null, newName: '', newObjective: null },
  workflow: { tab: 'workbench', projectId: null, stage: null, stepStage: 1 },
  /** 从步骤页进入工具箱时只显示该步骤的推荐工具；null 表示显示全部 */
  toolboxFilter: null,
  toolboxCat: null,
  toolboxKeyword: '',
  toolbox: {
    q: '', scenario: '', categories: [], stage: null, step: '', sort: 'fit', open: '', status: '',
    selected: '', segment: '',
    /** 主区展开哪一块：reco = ① 问题匹配，resources = ② 全部资源，'' = 都折叠 */
    section: 'reco',
    /** 旧链接里的折叠组标记，左侧已改成常显索引 */
    navSection: 'problem',
  },
  designer: {
    processId: null, processCode: null, model: null, analysis: null, tab: 'model',
    changes: null, changeMeta: null, raci: null, raciMeta: null, governanceRoles: null,
    binding: null, bindingError: null, bindingLocate: null,
  },
  knowledge: {
    type: '', sort: 'recent', page: 1, status: '', tool: '', tag: '', step: '',
  },
  pcf: {
    framework: 'APQC_PCF', frameworks: null, tree: null, treeFramework: null,
    expanded: new Set(), selectedId: null, keyword: '',
  },
  bpmn: { lesson: 'place' },
  cbok: { area: 'read' },
  train: { module: 'bpm', reveal: false, revealedFor: '', coach: null },
  cockpit: { processId: null },
  monitor: { status: '', tab: 'kpi', kind: '', period: '', miningProcess: null,
    workloadProcess: '', workloadPosition: '', analysisTopic: 'path' },
  strategy: { year: new Date().getFullYear(), selectedId: null },
  dataGov: null,
  dataGovTab: 'domains',
  processCard: { processId: null, activeModule: 'strategy' },
  /** 跨页面跳转来源栈：供「返回来源」按钮使用，侧栏切换时清空 */
  navTrail: [],
  start: { data: null },
  pilot: { pathId: null, layerNo: null, data: null, paths: null, meta: null, users: null,
    pendingProcess: null, charterForm: null, rpaOpen: false, trainingOpen: false,
    eventOpen: false, runOpen: false, caseOpen: false, techOpen: false,
    runOptions: null, techKinds: null },
  execution: { tab: 'tasks', filter: 'mine', configStep: 'process' },
  asset: { processId: null, package: null, preview: null },
  deliverables: {
    tab: 'project', projectId: null, templateTool: '', templateFormat: '',
    documentProcessId: null, documentCategory: '', documentOrgUnitId: null,
    documentLevel: '', items: [], stepFilter: '',
    templateOrgUnitId: null,
  },
};

export const TITLES = {
  workbench: '工作台',
  alignment: '目标与承接',
  processes: '流程',
  map: '流程框架',
  workflow: '五阶段标准工作流',
  projects: '流程项目组合',
  execution: '流程执行',
  asset: '流程资产',
  toolbox: '方法论工具箱',
  designer: '流程设计器',
  monitor: '度量',
  strategy: '战略目标',
  traceability: '追溯矩阵',
  data: '数据治理',
  start: '体系总览',
  pilot: '十层核对',
  process_card: '流程卡',
  authorization: '授权矩阵',
  dashboard: '运营驾驶舱',
  knowledge: '方法论工具箱',
  pcf: '流程架构',
  bpmn: 'BPMN 符号',
  cbok: 'CBOK 知识域',
  train: 'BPM 实训',
  deliverables: '交付物与模板库',
  orgs: '组织与人员',
  handbook: '员工手册',
  responsibility: '岗位职责',
  sketches: '架构草图',
  help: '帮助中心',
};
