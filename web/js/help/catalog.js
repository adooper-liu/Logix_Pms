/* 产品帮助中心内容树（唯一运行时源）。
 *
 * 阅读序：定位 → 价值 → 边界 → 原理 → 场景 → 实操 → 术语。
 * 素材见 docs/help/README.md；勿在视图里另写平行长文。
 */

/** @typedef {{ id: string, title: string, summary?: string,
 *   principle?: string, value?: string, boundary?: string,
 *   scenario?: string, howto?: string[], related?: string[],
 *   openView?: string, openParams?: Record<string, string> }} HelpTopic */

/** 目录分组（侧栏顺序） */
export const HELP_GROUPS = [
  {
    id: 'start',
    title: '入门',
    topics: ['intro'],
  },
  {
    id: 'foundation',
    title: '定位 · 价值 · 边界 · 原理',
    topics: ['positioning', 'value', 'boundaries', 'principles'],
  },
  {
    id: 'modules',
    title: '模块说明',
    topics: [
      'module-workbench', 'module-alignment', 'module-processes',
      'module-start', 'module-orgs', 'module-map', 'module-authorization',
      'module-strategy', 'module-projects', 'module-workflow', 'module-pilot',
      'module-designer', 'module-asset', 'module-traceability', 'module-execution',
      'module-dashboard',
      'module-monitor',
      'module-toolbox', 'module-deliverables', 'module-data', 'module-bpmn',
      'module-pcf', 'module-cbok', 'module-train',
      'module-process-card', 'module-sketches',
    ],
  },
  {
    id: 'scenarios',
    title: '场景手册',
    topics: [
      'scenario-zero-to-one', 'scenario-improve', 'scenario-publish-run',
      'scenario-owner-review',
    ],
  },
  {
    id: 'howto',
    title: '操作实例',
    topics: [
      'howto-execution-config', 'howto-task-queue', 'howto-publish', 'howto-workload',
    ],
  },
  {
    id: 'ref',
    title: '参考',
    topics: ['glossary'],
  },
];

/** @type {Record<string, HelpTopic>} */
export const TOPICS = {
  intro: {
    id: 'intro',
    title: '30 分钟入门',
    summary: '先看工作台：从流程框架、一条流程或一个项目开始。',
    principle: '流程不是目的，是让目标可控的一种实践；生产入口按手上有什么分三路。',
    value: '工作台只列要办的事；体系图谱是结构基准，不作为操作入口。',
    boundary: '图谱解释「为什么这样组织」；具体办理在工作台和模块页面。',
    scenario: '第一次登录：打开「工作台」→ 选流程框架 / 一条流程 / 一个项目。',
    howto: [
      '点顶栏「?」：任何页面都能打开**本页**对应帮助。',
      '从流程框架开始：建 L1/L2/L3，再回到流程清单。',
      '从一条流程开始：选 L3，进入资产工作台处理模型、证据与日志。',
      '从一个项目开始：新建或打开改善项目，处理阶段与门禁。',
    ],
    related: ['positioning', 'scenario-zero-to-one', 'glossary', 'module-workbench', 'module-start'],
    openView: 'workbench',
  },

  positioning: {
    id: 'positioning',
    title: '产品定位',
    summary: '面向制造业流程管理科的工作台，不是泛 OA，也不是只画 BPMN 的工具。',
    principle: '把「公司有哪些流程、哪条该改、怎么改、改完怎么跑、跑得怎样」放在同一套数据模型里。',
    value: '避免多套台账：地图、项目、模型、运行、KPI 可追溯到同一条流程对象。',
    boundary: '不是 ERP/财务系统；不替代制度原文；不做通用低代码应用搭建。',
    scenario: '流程管理科建家底与改善闭环；流程 Owner 看单条流程健康；业务处理人只看待办。',
    howto: [
      '对照三条主线选入口：建体系 → 工作台；改一条 → 项目组合；跑业务 → 流程执行。',
    ],
    related: ['value', 'boundaries', 'principles'],
  },

  value: {
    id: 'value',
    title: '价值主张',
    summary: '可解释的方法选择、可冻结的模型发布、可审计的运行与改善证据。',
    principle: '方法（BPR/BPI/精益）是五阶段里的可选路径，不是三套孤立软件。',
    value: '立项能推荐方法；设计能量化测算；发布后运行用快照，防止历史漂移；异常与 KPI 闭环。',
    boundary: '价值不靠「功能数量」体现；若页面不能减少一次选择或一次争论，就不该占首屏。',
    scenario: '向管理层说明：家底在地图、工程在项目、图纸在设计器、日常在执行、结果在驾驶舱。',
    howto: [
      '用运营驾驶舱看越线的指标、过期的异常和该继续的项目，再下钻到 KPI、异常台账或地图。',
    ],
    related: ['positioning', 'module-dashboard', 'principles'],
    openView: 'dashboard',
  },

  boundaries: {
    id: 'boundaries',
    title: '边界与模块地图',
    summary: '一句话分清：地图是家底，项目是改善工程，工作流是方法手册，工具箱是工具书，设计器是图纸，执行是跑流程，监控是看结果。',
    principle: '每个页面只回答一个主问题；跨页跳转必须少做一次选择。',
    value: '边界清晰才能培训：新人不会把「改项目进度」和「跑业务待办」混在一起。',
    boundary: [
      '流程地图 ≠ 项目进度；项目组合 ≠ 日常待办；',
      '五阶段步骤页 ≠ 某项目的 24 步实例；',
      '任务表单 ≠ Excel 台账；PCF ≠ 公司 L1–L4 层级。',
    ].join(''),
    scenario: '选错入口时：回到本页对照，或点顶栏「⌂ 工作台」回主入口。',
    howto: [
      '改架构/优先级 → 企业流程地图',
      '推进改善项目 → 流程项目组合',
      '查标准动作/工具 → 五阶段 / 工具箱',
      '画模型并发布 → 流程设计器',
      '认领与完成任务 → 流程执行',
    ],
    related: ['module-map', 'module-projects', 'module-execution', 'module-designer'],
  },

  principles: {
    id: 'principles',
    title: '核心原理',
    summary: '理解四个因果：对象、发布快照、出边路由、分派与 SLA。',
    principle: [
      '对象：流程节点（L1–L4）→ 改善项目 → 流程模型版本 → 运行实例/任务 → KPI/异常。',
      '发布：设计器发布后，新启动的实例冻结该版模型、表单与分派；运行中实例不跟着草稿改。',
      '路由：分支以设计器出边匹配条件为准；执行页只补运行绑定，旧规则仅过渡兜底。',
      '分派：默认处理人 → 候选角色/组织 → 公共队列；时限与升级可按流程/节点配置。',
    ].join('\n'),
    value: '原理清楚后，配置页上的「公共队列」「模型出口」不再是黑话。',
    boundary: '测算（PCE 等）是设计估计，不等于运营实测 KPI。',
    scenario: '上线一条流程前，先问：模型发布了吗？分派谁？表单字段够不够做出边判断？',
    howto: [
      '设计器：出边条件写在连线上并发布。',
      '执行 → 运行配置：分派 / 任务表单 / 时限。',
      '启动实例后在待办处理；实例页看卡点。',
    ],
    related: ['howto-publish', 'howto-execution-config', 'glossary'],
  },

  'module-alignment': {
    id: 'module-alignment',
    title: '目标与承接',
    summary: '客户/市场要求 → 战略目标 → 承接流程/KPI → 四路使能状态。',
    principle: '目标不是流程；先把上游要求挂到目标，再看资源、班子、流程、制度哪一路缺。',
    value: '一页回答：这个目标有没有客户依据、承接流程和四路使能。',
    boundary: '不在本页直接改流程/项目/制度；缺口按钮跳回对应模块。',
    scenario: '年初定目标、季度复盘、立项前检查目标是否真正可落地。',
    howto: [
      '登记客户/市场要求，并挂到一个或多个目标。',
      '选目标，看四张卡：配资源 / 搭班子 / 建流程 / 制度与绩效。',
      '按缺口按钮去对应模块补齐；本页只显示状态。',
    ],
    related: ['module-strategy', 'module-projects', 'module-map', 'module-asset'],
    openView: 'alignment',
  },

  'module-workbench': {
    id: 'module-workbench',
    title: '工作台',
    summary: '从流程框架、一条流程或一个项目开始；只列要办的事。',
    principle: '生产入口按手上有什么分三路，不按方法阶段铺导航。',
    value: '新建框架节点、打开流程、新建项目都在首屏完成。',
    boundary: '不在这里讲方法论；方法内容在帮助中心。',
    scenario: '第一次进入系统：先建框架，或直接选一条流程/项目开始。',
    howto: [
      '流程框架：建 L1/L2/L3，或打开流程地图继续维护。',
      '一条流程：选 L3 进入资产工作台；需要补活动时直接「新建 L4 活动」。',
      '一个项目：新建改善项目，或打开已有项目的阶段与门禁。',
    ],
    related: ['module-map', 'module-asset', 'module-projects'],
    openView: 'workbench',
  },

  'module-processes': {
    id: 'module-processes',
    title: '流程清单',
    summary: '只列已纳入目录的 L3 流程，按编码、名称、Owner 过滤。',
    principle: '流程是工作对象，不是菜单；打开后进入同一流程的资产与证据。',
    value: '缺 Owner、未纳入目录外的情况一眼能看到。',
    boundary: '不在这里修改 L1–L4 结构；结构维护在流程框架。',
    scenario: '日常进入某条流程：搜索 L3，打开资产工作台或设计器。',
    howto: [
      '用搜索或「只看缺 Owner」定位流程。',
      '打开 → 流程资产工作台；设计器 → 模型编辑；加 L4 → 在该 L3 下新建活动。',
      '缺流程时去流程框架新建 L3。',
    ],
    related: ['module-map', 'module-asset', 'module-designer'],
    openView: 'processes',
  },

  'module-start': {
    id: 'module-start',
    title: '体系总览',
    summary: '从客户价值 → 战略目标 → 流程架构 → 流程资产 → 执行 → 度量与反馈。',
    principle: '流程不是目的，是让目标可控的一种实践；治理、证据和产物贯穿全过程。',
    value: '首页图谱与侧栏按同一框架组织，每层可直接进入对应页面。',
    boundary: '本页是体系总览；公司流程地图的边界证据仍在下方「起步条件」。',
    scenario: '第一次登录：先看体系图，再从「价值与目标」或「流程架构」进入。',
    howto: [
      '先看体系图：目标、架构、资产、执行、度量，治理与支持横切。',
      '点某一层的入口按钮进入页面；每页顶栏「⌂ 体系图」可回到这里。',
      '公司流程地图的边界证据在下方「起步条件」，某一条流程去「十层核对」。',
    ],
    related: ['scenario-zero-to-one', 'intro'],
    openView: 'start',
  },

  'module-orgs': {
    id: 'module-orgs',
    title: '组织与人员',
    summary: '主数据：组织层级、账号角色、岗位——给继承范围与分派一个可信来源。',
    principle: '组织编码与层级决定标准文件/模板继承；岗位供运行分派引用。',
    value: '没有正确组织树，后面的 Owner、分派、文件范围都会落错。',
    boundary: '不是业务页面；不产生流程或文档正文。通常仅管理员维护。',
    scenario: '开户、挂岗位、调整分公司/部门后再配分派与标准文件。',
    howto: [
      '先建组织架构，再挂人员与岗位。',
      '角色决定能否进运行配置/组织维护。',
    ],
    related: ['module-execution', 'module-deliverables'],
    openView: 'orgs',
  },

  'module-map': {
    id: 'module-map',
    title: '企业流程地图',
    summary: '公司流程家底：L1–L4 架构、Owner、健康度与痛点。',
    principle: '公司树与 PCF/SCOR 是映射关系，不是上下级替换。',
    value: '回答「我们有哪些流程、哪条该盯」；改善优先级统一在驾驶舱看，避免双榜单。',
    boundary: '不做项目进度、不做日常任务分派。',
    scenario: '年度规划、向管理层汇报家底、选 L3 立项。',
    howto: [
      '左侧树定位，中间表看当前层。',
      '选中 L3 可立项或打开流程卡。',
    ],
    related: ['module-projects', 'module-pcf', 'module-process-card'],
    openView: 'map',
  },

  'module-authorization': {
    id: 'module-authorization',
    title: '授权矩阵',
    summary: '把审批权限变成可查询规则与例外台账。',
    principle: '规则引用制度，不复制制度正文；例外必须可审计。',
    value: '金额/风险分级审批有据可查。',
    boundary: '不替代 SOP/制度文件本身。',
    scenario: '制度设计完成后，把 A/B/C/D 类审批落到矩阵。',
    howto: [
      '维护规则字段（上限、角色、证据要求）。',
      '破例走例外台账并设失效。',
    ],
    related: ['module-deliverables', 'module-pilot'],
    openView: 'authorization',
  },

  'module-strategy': {
    id: 'module-strategy',
    title: '战略目标',
    summary: '可量化目标与基线，并挂到具体流程。',
    principle: '目标要有责任人、目标值与现状基线；承接链服务阶段门校验。',
    value: '改善项目能说清「赢什么」，避免只改流程图无业务结果。',
    boundary: '不是 KPI 看板（看运营驾驶舱/监控）。',
    scenario: '立项前先定基线；阶段 1 退出常检查目标—流程—KPI 承接。',
    howto: [
      '左侧先点目标。流程层级收在目标下面，默认只露出 L1。',
      '整理时打开 OGSM、SWOT、目标树或加权决策矩阵，结果写回这张目标。',
    ],
    related: ['scenario-improve', 'module-projects'],
    openView: 'strategy',
  },

  'module-projects': {
    id: 'module-projects',
    title: '流程项目组合',
    summary: '改善项目的管理容器：立项、24 步实例、阶段与里程碑。',
    principle: '立项时按标准工作流实例化步骤；推进在项目详情，不在方法手册页改状态。',
    value: '把「改流程」变成可交付工程，而不是一张图。',
    boundary: '不跑日常业务实例（那是流程执行）。',
    scenario: '地图选中痛点流程后立项，按五阶段推进到试点与固化。',
    howto: [
      '组合页筛选/新建；详情里更新步骤与交付物。',
      '阶段门若声明改善，必须引用已接收、可比且两次样本 ≥5 的日志对照；对照被退回会阻止推进。',
      '查标准动作去「五阶段」；查工具去工具箱。',
    ],
    related: ['module-workflow', 'module-toolbox', 'scenario-improve'],
    openView: 'projects',
  },

  'module-workflow': {
    id: 'module-workflow',
    title: '五阶段标准工作流',
    summary: '全公司共用的方法手册 / 教学引导（含项目工作台入口）。',
    principle: '步骤页是参考视图；某个项目的完成情况在项目组合的 24 步实例里。',
    value: '统一「下一步做什么、交付什么」。',
    boundary: '不记录单个项目勾选进度（除工作台挂接项目时）。',
    scenario: '新人培训、项目启动对齐方法、卡壳时查关键要点。',
    howto: [
      '先看当前阶段步骤说明，再挑 1–2 个推荐工具。',
    ],
    related: ['module-toolbox', 'module-projects'],
    openView: 'workflow',
  },

  'module-pilot': {
    id: 'module-pilot',
    title: '十层核对',
    summary: '单条试点流程的落地检查表：一层一问，证据出门。',
    principle: '十层管「这条流程对象能不能上线」，项目组合管「改善项目走到哪」。',
    value: '防止「图画了、权没定、表单没有、绩效没有」就宣称上线。',
    boundary: '不替代 24 步项目管理。',
    scenario: '设计完成后到正式运行前的关门核对。',
    howto: [
      '选路径/流程 → 逐层看退出条件与证据跳转。',
    ],
    related: ['scenario-zero-to-one', 'module-execution'],
    openView: 'pilot',
  },

  'module-designer': {
    id: 'module-designer',
    title: '流程设计器',
    summary: 'As-Is / To-Be 建模、测算、权责与发布门禁。',
    principle: '出边条件写在模型上；发布后运行时用该版本快照。',
    value: '图纸与测算同口径；不可信模型会明示，不拿假数充结论。',
    boundary: '不在设计器里处理日常待办；运行绑定回执行页。',
    scenario: '诊断后画 To-Be → 校验 → 评审 → 发布到运行时。',
    howto: [
      '模型页建模；测算看周期/成本；权责定 RACI；变更走门禁。',
      '发布后去流程执行做分派与表单。',
    ],
    related: ['howto-publish', 'module-execution', 'principles'],
    openView: 'designer',
  },

  'module-asset': {
    id: 'module-asset',
    title: '流程资产工作台',
    summary: '把已发布模型、架构关系和证据主张编译成流程级 SOP 资产包。',
    principle: '先有可复核的模型与证据，再生成资产；数字只有一个来源，不拿自由文本拼结论。',
    value: '默认只回答三个问题：能产出什么、还缺什么、下一步做什么。',
    boundary: '资产包是流程级 SOP，不是项目交付物；阻断未清零不提交评审。',
    scenario: '流程 Owner 在 To-Be 模型发布后，补齐关系与证据，生成 R0 草稿并提交评审。',
    howto: [
      '选一条 L3 流程，先看阻断清单。',
      '硬阻断：去设计器发布模型或完成活动映射。',
      '软阻断：去执行运行配置补表单/规则，或去分析页处理证据冲突。',
      '导入 CSV 日志 → 日志前后对照 → 由流程管理科登记接收结论；门禁通过后可写回 KPI 基线/目标。',
      '预览资产包 → 生成草稿 → 提交评审。',
    ],
    related: ['module-designer', 'module-execution', 'module-monitor'],
    openView: 'asset',
  },

  'module-traceability': {
    id: 'module-traceability',
    title: '追溯矩阵',
    summary: '目标 / KPI → L3 → L4 → BPMN 节点 → 资产版本 → 证据。',
    principle: '缺链接显示「未承接」，不推断；本页只读。',
    value: '改目标、改流程、改资产之前，先看影响链。',
    boundary: '不在本页编辑目标/流程/资产；只做反查。',
    scenario: '立项或变更评审前，查目标是否落到 L3/L4，活动是否有节点、资产与证据。',
    howto: [
      '按目标或 L3 筛选；没选时看全部链。',
      '看「缺口」列：未挂 KPI、未映射节点、无编译资产、无证据。',
      '点对应页面补齐；本页不提供编辑。',
    ],
    related: ['module-strategy', 'module-map', 'module-asset'],
    openView: 'traceability',
  },

  'module-execution': {
    id: 'module-execution',
    title: '流程执行',
    summary: '已发布模型的运行时：待办、实例、运行配置、集成。',
    principle: '设计定语义（出边）；执行补绑定（分派/表单/SLA）。待办默认「我的」。',
    value: '把上线流程变成可处理的任务队列与可审计实例。',
    boundary: '不管改善项目进度；「全部」含他人在办，≠ 我的+公共。',
    scenario: '试点与正式运行：启动 → 处理待办 → 看实例卡点；管理员配运行绑定。',
    howto: [
      '待办用 我的/公共/全部 切换；点处理即接办。',
      '运行配置五步：选流程 → 分派 → 表单 → 时限 → 就绪。',
      '实例页角标显示运行中数量。',
    ],
    related: ['howto-execution-config', 'howto-task-queue', 'scenario-publish-run'],
    openView: 'execution',
  },

  'module-dashboard': {
    id: 'module-dashboard',
    title: '运营驾驶舱',
    summary: '今天要处理的三件事：越线的指标、过期的异常、接着推进的项目。',
    principle: '总览只放能点下去处理的数。框架边界在流程框架，指标曲线在 KPI。',
    value: '打开就能决定先处理哪一件。',
    boundary: '单条流程的起止在十层核对。路径、测算和基线在流程分析。',
    scenario: '每日站会先看超期异常和红/黄指标，再看项目的下一步。',
    howto: [
      '点红/黄 KPI 打开 KPI 页签，点未闭环异常打开异常台账。',
      '点继续推进打开该项目。改善优先级进入地图上的那条流程。',
    ],
    related: ['module-monitor', 'module-map', 'module-projects'],
    openView: 'dashboard',
  },

  'module-monitor': {
    id: 'module-monitor',
    title: '运营监控（驾驶舱·KPI）',
    summary: 'KPI 的当前值、目标、红黄绿和达成率趋势。异常台账与标准工时在各自页签。',
    principle: '监控回答「跑得怎样」；异常要闭环。',
    value: '把改善结果从感觉变成可追踪指标。',
    boundary: '不在这里改流程模型或项目 24 步。',
    scenario: '运营例会、异常升级。',
    howto: [
      '从驾驶舱切入监控页签；按状态筛异常。',
      '流程分析先在标题右侧选流程，再在左边点一项，中间只显示这一项。默认是全部流程。',
    ],
    related: ['module-dashboard', 'module-strategy'],
    openView: 'monitor',
  },

  'module-toolbox': {
    id: 'module-toolbox',
    title: '方法论工具箱',
    summary: '方法/工具书：按问题与阶段推荐 SIPOC、VSM、FMEA 等；知识资源已并入。',
    principle: '步骤推荐工具；一次选 1–2 个，不要全上。',
    value: '从「下一步做什么」落到「具体怎么做」。',
    boundary: '填写并挂上会写成目标或挂到流程。下载用的文件模板仍在交付物库。',
    scenario: '项目某一步卡住时，从步骤进入只看推荐。',
    howto: [
      '可用问题描述或痛点快捷入口排序。',
      '点「填写并挂上」，按格子填写。OGSM 和目标树会同时写成战略目标。',
    ],
    related: ['module-workflow', 'module-projects'],
    openView: 'toolbox',
  },

  'module-deliverables': {
    id: 'module-deliverables',
    title: '交付物与模板库',
    summary: '项目交付物、流程标准文件、工具模板与基线审计的统一入口。',
    principle: 'as-built（项目产出）与 as-designed（标准文件）分离，晋升才进标准。',
    value: '标准可追溯、可继承组织范围。',
    boundary: '不是知识案例库（在工具箱资源）。',
    scenario: 'SOP/表单受控发布；项目步骤交卷；模板复用。',
    howto: [
      '标准文件：先选流程再新建/升版。',
      '项目交付物：选项目后上传或从模板建。',
    ],
    related: ['module-projects', 'module-map'],
    openView: 'deliverables',
  },

  'module-data': {
    id: 'module-data',
    title: '数据治理',
    summary: '流程数字化前的最小数据台账：域、流、质量与责任人。',
    principle: '只覆盖「这条流程用到的数据」，不是企业级 MDM。',
    value: '配 KPI、上执行、做挖掘前先确认数据可取得。',
    boundary: '不做全量 DAMA 平台。',
    scenario: '上监控或集成前补数据责任与来源。',
    howto: [
      '登记数据域与数据流，明确 Owner 与质量规则。',
    ],
    related: ['module-monitor', 'module-execution'],
    openView: 'data',
  },

  'module-pcf': {
    id: 'module-pcf',
    title: '流程架构',
    summary: '用 APQC 分类往下建公司地图：先定 L1，留 L2，只把在跑的 L3 生成过去。',
    principle: '分类是类名，不是生命周期的先后，也不是 BPMN 图。',
    value: '对标和跨公司沟通时有同一套类名，并且知道下一步写到哪。',
    boundary: '不代替公司自己的流程地图。活动和任务不从分类树整包抄进地图。',
    scenario: '先看右边的构建顺序，再点一条分类看它该往哪一步走。',
    howto: [
      '左边点分类，中间看定义，右边按 L1、L2、L3 往下建。',
      '用「按 1+3+10 往下建」打开地图上的引导。',
      '生成后回到这一页，看还没对上的 L3。活动写进这条 L3 的设计器。',
    ],
    related: ['module-map', 'module-bpmn', 'module-cbok'],
    openView: 'pcf',
  },

  'module-bpmn': {
    id: 'module-bpmn',
    title: 'BPMN 符号',
    summary: 'OMG 的流程符号。按本系统画布能保存的符号来学一条流程怎么走。',
    principle: '符号表示先后、分支和等待。分类去 PCF，从业范围去 CBOK。',
    value: '画之前就知道哪些符号执行引擎收得下。',
    boundary: '不转载 OMG 规范正文。并行网关、子流程和边界事件不能保存。',
    scenario: '准备在设计器里画一条 L3 之前，先把符号过一遍。',
    howto: [
      '从「这一页管什么」读到「画布上不提供的符号」。',
      '再打开流程设计器画。',
    ],
    related: ['module-designer', 'module-pcf', 'module-cbok'],
    openView: 'bpmn',
  },

  'module-cbok': {
    id: 'module-cbok',
    title: 'CBOK 知识域',
    summary: '生命周期在公司体系。知识域 1 到 7 对一条流程，8 和 9 留在公司体系。流程架构对 APQC。',
    principle: '先看现状再定以后怎么走。技术是帮手，流程还乱就不要先自动化。',
    value: '学一项就能打开系统里对应的那一页。',
    boundary: '不转载手册章节正文。4.0 公告里的技术题目，只接到系统里已经有记录的页面。',
    scenario: '新加入流程管理科的人，先看九项分别落在哪一页。',
    howto: [
      '从「业务流程管理」点到「流程技术」。',
      '用每条上的按钮打开对应页面。',
    ],
    related: ['module-start', 'module-bpmn', 'module-pcf'],
    openView: 'cbok',
  },

  'module-train': {
    id: 'module-train',
    title: 'BPM 实训',
    summary: '九讲按 CBOK 讲义展开：开场、概念、演练、小结。本系统的页面只在每讲末尾作实证。',
    principle: '讲义怎么讲就怎么放。系统里没有的仿真、机器人运行时和个人考核，写在实证里，不写进正文。',
    value: '学完能按讲义复述，并打开对应页面核对这套系统实际做到哪一步。',
    boundary: '不调用外部语言模型。标准工时不用于个人排名或奖金。',
    scenario: '讲完一讲，用末尾的实证打开十层核对、设计器、KPI 或地图。',
    howto: [
      '从左边选一讲，先读开场和概念。',
      '演练按讲师备注的时间做。',
      '最后看本系统实证，再打开对应页面。',
    ],
    related: ['module-cbok', 'module-bpmn', 'module-pcf'],
    openView: 'train',
  },

  'module-process-card': {
    id: 'module-process-card',
    title: '流程卡',
    summary: '单条 L3/L4 的 360°：战略、权责、文件、模型、KPI、变更与治理待办。',
    principle: '聚合入口，不新建第二套数据。',
    value: 'Owner 月度复盘、交接、评审前自查。',
    boundary: '不做跨流程排名（驾驶舱）或项目进度（项目组合）。',
    scenario: '从地图或战略「核对流程」进入。',
    howto: [
      '按模块页签补齐 readiness，再跳原模块深耕。',
    ],
    related: ['module-map', 'scenario-owner-review'],
    openView: 'process_card',
  },

  'module-sketches': {
    id: 'module-sketches',
    title: '架构草图',
    summary: '早期结构讨论的草图空间，正式架构仍以流程地图为准。',
    principle: '草图辅助对齐，不替代受控 L1–L4。',
    value: '低成本试错分层与边界。',
    boundary: '评审通过后应落到地图节点，避免长期双轨。',
    scenario: '工作坊现场勾勒价值链再录入地图。',
    howto: [
      '草图达成一致后，到企业流程地图建正式节点。',
    ],
    related: ['module-map'],
    openView: 'sketches',
  },

  'scenario-zero-to-one': {
    id: 'scenario-zero-to-one',
    title: '场景：从 0 建体系',
    summary: '新体系先划清公司流程地图的框架边界，再改一条流程。',
    principle: '流程框架数这张图；十层核对写这一条的起止；项目工作台管改善工程。',
    value: '培训可复制，完成必须有证据。',
    boundary: '不要一上来选整条价值链当试点；Owner 必须是人。',
    scenario: '先在流程框架划清流程地图，再在十层核对写一条 L3 的起止。',
    howto: [
      '打开流程框架，逐步补证据。',
      '详细带练脚本见仓库 docs/training-zero-to-one.md（素材）。',
    ],
    related: ['module-start', 'module-pilot', 'scenario-publish-run'],
    openView: 'start',
  },

  'scenario-improve': {
    id: 'scenario-improve',
    title: '场景：立一个改善项目',
    summary: '从地图痛点到项目 24 步闭环。',
    principle: '项目实例化标准步骤；方法与工具按阶段选用。',
    value: '改善可管理、可验收。',
    boundary: '项目进度≠流程实例待办。',
    scenario: '驾驶舱/地图看优先级 → 立项 → 诊断设计 → 试点 → 运营移交。',
    howto: [
      '项目组合新建并关联流程与目标。',
      '步骤卡壳时打开五阶段与工具箱。',
    ],
    related: ['module-projects', 'module-workflow', 'module-toolbox'],
    openView: 'projects',
  },

  'scenario-publish-run': {
    id: 'scenario-publish-run',
    title: '场景：发布到跑通',
    summary: '模型发布 → 运行配置 → 启动 → 待办处理 → 实例完成。',
    principle: '未发布不能当真跑；路由看出边；分派决定谁看见任务。',
    value: '打通设计与运营，留下审计轨迹。',
    boundary: '草稿模型上的改动不影响已启动实例。',
    scenario: '演示流程（如采购需求提报）完整跑一单。',
    howto: [
      '设计器发布到运行时。',
      '执行 → 运行配置补分派/表单/时限。',
      '启动流程 → 待办处理 → 实例页确认结束。',
    ],
    related: ['howto-publish', 'howto-execution-config', 'howto-task-queue'],
    openView: 'execution',
  },

  'scenario-owner-review': {
    id: 'scenario-owner-review',
    title: '场景：Owner 月度复盘',
    summary: '用流程卡看一条流程是否健康、缺什么。',
    principle: 'readiness 清单驱动补齐，而不是凭记忆。',
    value: '交接与评审前有同一张检查面。',
    boundary: '不做组合级资源调配。',
    scenario: '每月打开负责 L3 的流程卡，看战略/文件/模型/KPI/治理待办。',
    howto: [
      '从地图进入流程卡，按红项跳到原模块处理。',
    ],
    related: ['module-process-card', 'module-map'],
    openView: 'process_card',
  },

  'howto-execution-config': {
    id: 'howto-execution-config',
    title: '实操：运行配置五步',
    summary: '按流程各自一份：选流程 → 节点分派 → 任务表单 → 时限与升级 → 就绪检查。',
    principle: '分支在设计器出边；这里只读「模型出口」，并绑定谁干、填什么、多久升级。',
    value: '启动前把运行绑定一次配齐，减少公共队列无人认领。',
    boundary: '改走法请回设计器改出边并重新发布。',
    scenario: '管理员在执行页「运行配置」中为 L3-032 配分派与表单。',
    howto: [
      '打开流程执行 → 运行配置，选择目标流程。',
      '节点分派：候选角色 / 组织 / 默认处理人；不配则进公共队列。',
      '任务表单：维护节点字段清单（供填写与出边匹配）。',
      '时限与升级：流程默认 + 节点覆盖；生产用扫描任务升级。',
      '就绪检查通过后，用「+ 启动流程」。',
    ],
    related: ['module-execution', 'howto-task-queue', 'principles'],
    openView: 'execution',
    openParams: { tab: 'config' },
  },

  'howto-task-queue': {
    id: 'howto-task-queue',
    title: '实操：待办队列',
    summary: '默认「我的」；「公共」接无人认领；「全部」含他人在办。',
    principle: '点「处理」即接办并打开表单；挂起实例上的任务不可推进。',
    value: '处理人只看到该看的，管理员用「全部」排查。',
    boundary: '运行中数量在「流程实例」页签角标，不是待办 KPI 卡。',
    scenario: '业务人员每天打开执行页清「我的」；公共池抢单。',
    howto: [
      '顶栏进入流程执行（或侧栏）。',
      '用 我的 / 公共 / 全部 切换范围。',
      '点处理 → 填表单 → 完成；分支按出边或完成时选择。',
    ],
    related: ['module-execution', 'scenario-publish-run'],
    openView: 'execution',
    openParams: { tab: 'tasks' },
  },

  'howto-publish': {
    id: 'howto-publish',
    title: '实操：发布到运行时',
    summary: '设计器完成校验与评审后发布；新实例使用该版本。',
    principle: '发布是门禁动作；驳回改草稿不影响已发布运行时（除非再发新版）。',
    value: '运行与设计解耦，历史可解释。',
    boundary: '运行中实例不自动切换到新版。',
    scenario: '模型待评审 → 发布到运行时 → 去执行页配置并启动。',
    howto: [
      '设计器打开目标流程，处理校验问题。',
      '走评审/发布；确认运行时版本。',
      '到流程执行做运行配置并启动验证一单。',
    ],
    related: ['module-designer', 'scenario-publish-run'],
    openView: 'designer',
  },

  'howto-workload': {
    id: 'howto-workload',
    title: '工作量：怎么用',
    summary: '本月已验证的标准需求，和登记的可用产能差多少。有任务工时之后，再和标准比。',
    principle: '没有产能就不要显示负荷平衡；没有工时记录就不要把实际当成 0 去比标准。',
    value: '看出哪个岗位这个月不够，以及标准工时有没有审过。',
    boundary: '标准工时只做能力基线，不用于个人排名、扣罚或奖金。实际工时不在这页录入。',
    scenario: '排班或加人之前，先看负荷率是不是超过 100%。',
    howto: [
      '选月份。标准需求只加总「已验证」、且在该月有效的标准工时卡。',
      '选一条流程时，只看这条流程的活动和需求。再选一个岗位时，只留这个岗位在这条流程上的标准。可用工时仍是岗位整月，同岗位还服务其他流程。全部流程、全部岗位用来看岗位是否已经不够。',
      '点「+ 标准工时」。标准工时 = 观测 × 评定系数 × (1 + 宽放率)。月需求 = 标准工时 × 月频次。',
      '草稿先记至少 5 条样本，再提交评审。通过之后才进入标准需求和负荷率。「直接验证」跳过样本，只用于补已有标准。',
      '点「+ 产能」，按组织、岗位、月份登记人数、人均可用工时、出勤率、设备可用率。可用工时 = 人数 × 人均可用工时 × 60 × 出勤率 × 设备可用率。同一组织、岗位、月份只能有一条。',
      '理论负荷率 = 已验证标准需求 ÷ 可用产能。没有产能时显示 —。',
      '实际工时来自流程执行里的任务工时。本月没有记录时，页面不展示「标准 vs 实际」。',
      '瓶颈岗位只在已登记产能里、缺口为正（需求大于可用）时列出。未来 3 个月用当前需求和产能原样外推。一边有余量、一边不够时才给出派工建议，不自动改派。',
    ],
    related: ['module-monitor', 'module-execution', 'howto-task-queue'],
    openView: 'monitor',
    openParams: { tab: 'workload' },
  },

  glossary: {
    id: 'glossary',
    title: '术语表',
    summary: '一词一义；与页内 tip、后端标签保持同口径。',
    principle: '枚举中文以后端下发为准（status_label 等），帮助不另造翻译表。',
    value: '减少培训口误。',
    boundary: '术语表不替代模块说明。',
    scenario: '听到「公共队列 / 快照 / 出边」时来查。',
    howto: [
      '见下方术语列表；也可从模块文末「相关」跳回。',
    ],
    related: ['principles', 'intro'],
  },
};

/** 视图 → 默认帮助章节（顶栏 ?） */
export const PAGE_TOPIC = {
  workbench: 'module-workbench',
  alignment: 'module-alignment',
  processes: 'module-processes',
  start: 'module-start',
  orgs: 'module-orgs',
  map: 'module-map',
  authorization: 'module-authorization',
  strategy: 'module-strategy',
  traceability: 'module-traceability',
  projects: 'module-projects',
  workflow: 'module-workflow',
  pilot: 'module-pilot',
  designer: 'module-designer',
  asset: 'module-asset',
  execution: 'module-execution',
  dashboard: 'module-dashboard',
  monitor: 'module-monitor',
  toolbox: 'module-toolbox',
  knowledge: 'module-toolbox',
  deliverables: 'module-deliverables',
  data: 'module-data',
  pcf: 'module-pcf',
  bpmn: 'module-bpmn',
  cbok: 'module-cbok',
  train: 'module-train',
  process_card: 'module-process-card',
  sketches: 'module-sketches',
  help: 'intro',
};

/** @type {{ term: string, def: string }[]} */
export const GLOSSARY = [
  { term: 'L1–L4', def: '公司流程架构层级：价值链 → 类别 → 流程 → 活动。' },
  { term: 'PCF / SCOR', def: '行业参照分类；与公司树映射，不替换公司树。' },
  { term: '五阶段', def: '识别 → 诊断 → 设计 → 落地 → 运营；下含标准步骤。' },
  { term: '24 步实例', def: '某改善项目立项后生成的步骤进度，落在项目组合。' },
  { term: '发布 / 运行时版本', def: '设计器把模型定为可启动版本；新实例冻结该版。' },
  { term: '快照', def: '实例启动时复制的模型、表单、分派等，启动后不随草稿变。' },
  { term: '出边 / 匹配条件', def: '设计器连线上的路由条件；完成任务时求值决定下一步。' },
  { term: '任务表单', def: '节点待办的输入字段模板，不是 Excel 台账。' },
  { term: '公共队列', def: '无默认处理人时，候选人可点「处理」接办的任务池。' },
  { term: '我的 / 全部', def: '待办筛选：指派给我的；全部含他人在办，不等于我的+公共。' },
  { term: 'SLA / 升级', def: '任务时限；超时可扫描改派升级处理人，通常一任务一次。' },
  { term: '挂起', def: '实例暂停：不可认领/完成，不计 SLA；可恢复。' },
  { term: '流程卡', def: '单条流程的跨模块聚合页（360° readiness）。' },
  { term: 'Owner', def: '流程结果负责人（人），不是部门名。' },
];

export function getTopic(id) {
  return TOPICS[id] || TOPICS.intro;
}

/**
 * 按当前视图与 URL 参数解析帮助章节。
 * @param {string} view
 * @param {Record<string, string>} [params]
 */
export function topicIdForPage(view, params = {}) {
  if (view === 'execution' && params.tab === 'config') return 'howto-execution-config';
  if (view === 'execution' && params.tab === 'tasks') return 'howto-task-queue';
  if (view === 'execution' && params.tab === 'instances') return 'module-execution';
  if (view === 'monitor' && params.tab === 'workload') return 'howto-workload';
  return PAGE_TOPIC[view] || 'intro';
}

export function allTopicIds() {
  return HELP_GROUPS.flatMap((g) => g.topics);
}
