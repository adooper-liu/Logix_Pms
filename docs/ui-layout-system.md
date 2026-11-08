# 生产页面布局规范

> 目标：任何页面一次只回答一个主题；信息按主次分层，不把全部内容一次铺开。
> 实现：`web/js/core/layout.js` + `web/css/views.css` 的 `ws-*` / `fold-card`。

## 0. 纪律（硬性）

以下规则已写入 [CLAUDE.md](../CLAUDE.md) 的「硬性约定」：

1. 新页面/迁移页面**必须用 `pageShell`**；不得在 `views/*` 手写标题、目录/Tab、三栏、吸顶。
2. `views/*` **不得直接 import** `workspaceHtml` / `sectionNav` / `sectionTabs`，也不得复制 `pageShell`。
3. 页面只提供一个主题 section 的内容；默认首屏只放结论、阻断、下一步。
4. 帮助/免责一律 `tipHelp`；次级区块用 `foldCard`。
5. 迁移页面必须登记到 `tests/test_frontend_structure.py` 的 `MIGRATED_PAGE_SHELL`。
6. 静态守卫不过，`python scripts/check.py` 就不会过；不接受“先手写、以后再说”。

## 1. 页面骨架

高密度页面统一使用三栏；中低密度页面使用两栏。

```text
┌ 页面标题 + 一句说明 + 主操作 ──────────────────────┐
├──────────┬────────────────────────┬───────────────┤
│ 左目录   │ 当前主题内容            │ 右上下文       │
│ 200px    │ minmax(0,1fr)          │ 270px         │
│ 可吸顶   │ 只渲染选中的 section    │ 状态/主操作    │
└──────────┴────────────────────────┴───────────────┘
```

- 左目录：`sectionNav(items, active, act)`；每项只写主题名和必要计数。
- 中间：只渲染当前 tab/section，不保留其他 section 的隐藏 DOM。
- 右侧：流程/对象状态、主操作、下一步；不做第二套明细。
- 小于 1200px：右栏落到内容下方；小于 860px：左目录变横向滚动。

## 2. 动线规则

1. **一次一个主题**：高密度页面用左目录（流程资产）；流程型页面用顶部 Tab（监控、项目）。不要在同一屏堆两个主题。
2. **主次分明**：
   - 首屏只放结论、阻断、下一步；
   - 明细放第二个主题页签；
   - 专家项（架构关系、证据账本）放后面的目录项，不进入默认首屏。
3. **左中右职责**：左选主题、中办当前事、右看状态和主操作。
4. **可折叠**：次级区块用 `foldCard(title, body, {open})`；默认展开只给当前最需要的块。
5. **帮助与免责**：一律用 `tipHelp(text, label)`，不写大段行内说明。
6. **卡片化**：任何独立主题用 `card`；卡片内先结论后明细。
7. **不重复**：同一数字只出现一次；右栏和中间不各算一套。

## 3. 代码用法：页面只提供内容

统一入口是 `pageShell`。页面不再手写标题、目录、三栏和 section 选择：

```js
import { pageShell, foldCard, sideCard } from '../core/layout.js';
import { tipHelp } from '../core/format.js';

const shell = pageShell({
  title: '…',
  badge: '<span class="tag t-blu">L3</span>',
  subtitle: '一句话说明',
  tip: tipHelp('免责/帮助说明', '本页说明'),
  actions: '<button class="btn btn-g" …>…</button>',
  sections: [
    { key: 'overview', label: '概览', count: 1, html: overviewHtml() },
    { key: 'detail', label: '明细', html: detailHtml() },
  ],
  active: state.asset.tab,
  tabAct: 'asset.tab',
  mode: 'nav',          // 'nav' 左目录 / 'tabs' 顶部 Tab
  aside: sideCard('状态', '…'),
});
state.asset.tab = shell.active;
viewEl().innerHTML = shell.html;
```

- 页面只负责：数据、`sections[].html`、`aside`、一个 tab 切换 handler。
- 外壳负责：标题、徽标、说明、TopTip、目录/Tab、三栏、吸顶、响应式。
- `workspaceHtml` / `sectionNav` / `sectionTabs` / `foldCard` / `sideCard` 是底层组件；
  新页面优先用 `pageShell`，不要直接拼三栏。

### 组件边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| `pageShell` | 页面骨架、目录/Tab、当前 section、右栏 | 业务数据、section 内容 |
| `foldCard` | 可折叠卡片 | 业务表格与表单 |
| `sideCard` | 右栏状态/主操作 | 明细数据 |
| `tipHelp` | 帮助/免责 TopTip | 页面正文说明 |
| `card` / `kpi` / `tbl` | 内容卡片、指标、表格 | 页面布局 |

## 4. 迁移检查清单

- [ ] 页面是否有明确的“当前主题”？没有就拆。
- [ ] 默认首屏是否只有结论、阻断、下一步？
- [ ] 明细是否在第二个目录项/Tab？
- [ ] 专家内容是否默认收在后面？
- [ ] 帮助/免责是否已改成 `tipHelp`？
- [ ] 次级区块是否可折叠？
- [ ] 右侧是否只放状态和主操作？
- [ ] 小屏是否退化为两栏/单栏？
- [ ] 同一数字是否只出现一次？

## 5. 已迁移页面

| 页面 | 布局 | 备注 |
|---|---|---|
| 流程资产 `asset` | 左目录 + 中内容 + 右上下文 | 概览 / 资产包 / 来源画像 / 诊断 R1 / 架构关系 / 证据账本 / 变更影响 |
| 流程框架 `map` | 顶部 Tab + 单栏内容 | 架构 / 对标 / 优先级；树导航留在架构内容区 |
| 项目组合 `projects` | 顶部 Tab + 单栏内容 | 项目列表 / 项目详情；完整工作台仍为显式弹窗 |
| 流程分析 `monitor` | 顶部 Tab + 单栏内容 + 右栏 | 保留既有 KPI/异常/工作量/分析/挖掘页签 |
| 流程执行 `execution` | 顶部 Tab + 单栏内容 + 右栏 | 待办 / 实例 / 运行配置 / 集成 |
| 战略目标 `strategy` | 统一头部 + 专用三栏内容 | 左目标树 / 中详情 / 右行动 |
| 交付物与模板库 `deliverables` | 顶部 Tab + 单栏内容 | 项目交付物 / 标准文件 / 模板 / 基线 |
| 组织与人员 `orgs` | 顶部 Tab + 单栏内容 | 组织 / 人员 / 岗位 / 治理角色 |
| 数据治理 `data` | 顶部 Tab + 单栏内容 + 右栏 | 数据域 / 数据流 |
| 流程设计器 `designer` | 统一头部 + 全宽画布 | 属性/校验在右侧抽屉；版本历史弹窗；RACI/变更为独立主题 |
| 学习页 `bpmn` / `cbok` / `train` | 统一头部 + 左讲次/右正文 | 学习导航留在内容区 |
| 架构草图 `sketches` | 统一头部 + 单栏表格 | 新建草图 |
| PCF `pcf` | 统一头部 + 专用三栏 | 分类树 / 详情 / 说明 |
| 流程卡 `process_card` | 统一头部 + 专用三栏 | 模块导航 / 详情 / 试点与就绪 |
| 十层核对 `pilot` | 统一头部 + 专用三栏 | 十层导航 / 当前层 / 上下文与下一步 |
| 方法论工具箱 `toolbox` | 统一头部 + 专用三栏 | 问题/阶段索引 / 工具详情 / 操作与校验 |
| 运营驾驶舱 `dashboard` | 统一头部 + 专用三栏 | 优先级 / 推进 / 今日告警 |

知识库 `knowledge` 已并入工具箱，只做重定向，不再单独渲染。
| 目标与承接 `alignment` | 左目录 + 中内容 + 右上下文 | 客户/市场要求 / 目标与四路；右栏年度汇总与缺口 |
| 工作台 `workbench` | 三入口卡 + 待办/最近 | 入口页不适用左目录 |

后续迁移：流程框架 `map`、项目组合 `projects`、流程分析 `monitor`、流程执行 `execution`。
