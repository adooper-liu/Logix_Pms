# 前端组织与交互契约

本文是 `docs/ui-information-architecture.md` 的下半篇。

- **IA 文档**回答「每页为谁解决什么问题、元素是什么关系、用什么可视化」——约束**看起来怎样**。
- **本文**回答「代码怎么组织、交互怎么写、状态放哪、新增一个页面要付多少成本」——约束**代码长成什么样**。

判断一条规则该写进哪份文档：**它约束渲染结果还是约束代码结构**。前者进 IA，后者进本文。

现状体检的结论是：**内容层（IA、主题令牌、枚举口径）已经达标；实现层存在四条现存断裂，
另有一条 IA 覆盖问题已在 Phase 0 修复**（保留在 §2.5 作为回归触发条件）。
本文只描述这些断裂、成因和修复顺序，不改动 IA 已确定的产品决策。

**当前进度**：Phase 0（补 IA 文档）已完成；Phase 1A/1B 已完成；Phase 2 进行中
（11 个视图已迁移，剩余 `deliverables` 与 `designer`）。
本文数字已按 2026-10-24 复核。**Phase 3–4 尚未开始**，
§2 是问题记录（2.4/2.5 已部分修复），§6 是执行顺序。

**测量基线（2026-10-24 复核，Phase 2 进行中）**：25 个手写 JS 模块、11,457 行
（其中 views 10,014 行）；13 个视图共 99 个导出符号（挂到 window 后约 111 个全局键）；
内联事件处理器 126 处（其中 111 处集中在 deliverables / designer，
其余 15 处在框架壳/core）；视图内原生 `confirm`/`prompt` 7 处（全部在 designer）；
`data-act` 键 161 个。复核命令见附录 A。

若与代码现状不符，以代码为准，并回来更新本文。

---

## 一、已经达标的部分（不要重做）

| 项 | 证据 | 状态 |
|---|---|---|
| 分层单向、无循环依赖 | `core/router.js` 不 import 任何视图；`core/api.js` 用 `setUnauthorizedHandler()` 回调注入 401 处理 | 达标 |
| 视图注册表 | `main.js:38-50` 统一 `register()`；视图之间仍有 7 处直接 import（§3），**不是「互不 import」** | 部分达标 |
| 主题令牌 + 测试拦截硬编码颜色 | `tests/test_frontend_structure.py:132-142` | 达标 |
| 枚举中文标签由后端下发 | 前端只读 `methodology_label` / `status_label` | 达标 |
| 零构建且写明重评条件 | `README.md`「为什么不引入 Vue」 | 达标 |
| 逐页信息架构 | `docs/ui-information-architecture.md` 覆盖 13/13 页 | 达标（2026-10-24 复核） |

**这一层的价值是「改一处、全局一致」**：同一类数据在 13 个页面长得一样，是因为
`core/format.js` 统一了转义、数值、时间、标签色板。**不要在补实现层时把这种统一性弄丢。**

---

## 二、五条断裂（2.5 已修复，保留为回归触发条件）

### 2.1 `designer.js` 不是视图，是一个应用

**证据**：`web/js/views/designer.js` — 2,448 行、92 个顶层函数声明（约 106 个命名函数）。
它同时承担 8 类互不相干的责任：

| 责任 | 代表函数 | 行段 |
|---|---|---|
| bpmn-js 脚本加载与画布生命周期 | `loadBpmnJs` / `mountBpmnEditor` / `destroyBpmnModeler` | 209–520 |
| bpmn-js 扩展点（3 个内部子类） | `PmsPaletteProvider` / `PmsContextPadProvider` / `PmsReplaceMenuProvider` | 386–473 |
| BPMN XML 字符串手术 | `appendBpmnLane` / `restoreLanes` / `ensureFlowRefs` / `orthogonalizePath` | 1300–1818 |
| 属性侧栏（4 类元素） | `renderBpmnNodePanel` / `renderBpmnFlowPanel` / `renderBpmnLanePanel` / `renderBpmnProcessPanel` | 635–837 |
| 分派与 SLA 配置 | `renderBpmnAssignment` / `persistAssignment` | 838–913 |
| 校验结果中文化（140 行词典） | `runBpmnLint` 后的翻译表 | 1489–1629 |
| 版本历史与回滚 | `openVersionHistory` / `diffVersion` / `rollbackVersion` | 2105–2180 |
| 导入导出 | `exportBpmn` / `importBpmn` / `downloadBpmn` | 2186–2260 |

**后果**：

1. **实现层与 IA 的「分屏」约定脱节**。IA 第 8 节要求「模型页和指标页分开」——
   产品层用页签已经做到了；但代码层仍是一个 2,448 行的文件，
   读代码的人得不到 IA 承诺的模块边界。**注意：这是代码组织问题，不是 IA 违规**；
   页签已经兑现了产品承诺，拆分是为了可测试性与变更隔离。
2. **XML 手术部分是纯函数，被埋在视图里**。`restoreLanes` / `ensureFlowRefs` /
   `orthogonalizePath` 不碰 DOM、不发请求，是最该被单测覆盖的部分，
   现在却无法在不启动画布的情况下测试。
3. **改 BPMN 适配就动整个应用**。bpmn-js 升版或换引擎，受影响的是
   「页面 + 画布 + XML + 校验 + 版本 + 导入导出」全部 8 块，而不是一个独立模块。

**目标结构**（同目录内拆包，不动目录层级，保持 `views/*` 的单向依赖不变）：

```text
web/js/views/designer/
  index.js            # 编排：加载数据 → 画布 → 页签 → 渲染
  canvas.js           # bpmn-js 加载、挂载、销毁、视口适配、自动保存
  providers.js        # PmsPaletteProvider / ContextPad / ReplaceMenu
  xml.js              # 纯函数：BPMN XML 增删改查、泳道恢复、折点正交化
  panels.js           # 属性侧栏（节点/连线/泳道/流程）
  assignment.js       # 分派与 SLA
  lint.js             # bpmnlint 规则 → 中文化映射
  versions.js         # 版本历史 / 差异 / 回滚
  transfer.js         # 导入导出
```

`web/js/views/designer.js` 保留为薄壳，只导出 `renderDesigner` 与真正需要跨视图的
`openDesigner`，让 `main.js` 与 `tests/test_frontend_structure.py` 的注册方式不变。

**子模块接口契约（拆分前必须先定）**：`canvas.js` 持有活的 modeler，
`panels.js` / `assignment.js` / `versions.js` 都要读它。不要互相 import，改为：
`index.js` 创建并持有一个显式的 `ctx`（`getModeler()` / `getElement(key)` /
`select(key)` / `subscribe(event, fn)`），向下传给各子模块；子模块只依赖这个只读接口，
`xml.js` 保持纯函数、不接收 `ctx`。没有这层契约，拆完只是把一个大文件变成九个互相 import 的文件。

### 2.2 `window` 全局面 = 99 个视图导出，没有边界

**证据**：`main.js:69-89` 用 `Object.assign(window, { ...dashboard, ...mapView, ... })`
把**每个视图模块的全部导出**摊到全局。实测 13 个视图共 **99 个导出符号**
（Phase 2 迁移 11 个视图后从 231 降下来），
加上框架级函数与 `templateCopy`，`window` 上约 **111 个全局键**。

**这不是「有风险」，而是已经发生过事故**：`map.js` 与 `pcf.js` 都导出了
`togglePcfNode`，`Object.assign` 后 `pcf.js` 覆盖了 `map.js` 的实现，
导致「从 PCF 生成草稿」向导里的 checkbox 勾选后选择集始终为空，预览一直提示
「请至少勾选一个 L3 分类」。修复方式是 `pcf.js` 改名为 `togglePcfBrowseNode`，
并新增 `tests/test_frontend_structure.py::test_view_exports_do_not_collide`
（解析各视图的 `export {}`，重名即测试失败）。

**这个全局面存在的唯一原因**：`onclick="openProject(3)"` 在全局作用域求值。
实测内联事件处理器 **126 处**（11 个视图已迁移归零；按事件类型分布见 §4.2）：

| 视图 | 内联处理器 | 视图 | 内联处理器 |
|---|---|---|---|
| deliverables.js | 66 | 其余 11 个视图 | **0**（已完成） |
| designer.js | 45 | | |

**后果**：

1. **没有 API 边界**。视图模块的「公开面」= 它的全部导出，
   读者无法分辨 `openDesigner`（跨视图要用）和 `restoreLanes`（纯内部），
   只能全文读 2,448 行才能知道。
2. **无法静态检查**。ES 模块能校验 import 路径，`window` 上挂的 99 个导出不能。
   `tests/test_frontend_structure.py` 原先只能检查「模块文件存在」，检查不了
   「模板里 `onclick="foo()"` 的 foo 是否真实存在」——拼错就是浏览器静默不响应。
   撞名守卫是事后补的；根因仍然是「全部导出即公开面」。
3. **重构成本被锁死**。任何改名都可能在 `window` 上撞名；`Object.assign` 后写覆盖前写，
   `togglePcfNode` 已经撞过一次。守卫只能拦住新增撞名，不能消除根因。
4. **它正在掩盖真实的耦合**。因为「函数挂 window 就能用」，
   视图之间要互相调用时，有两条路可走：import 别的视图，或者都挂到 window 上再调用。
   现状两条都走了——实测有 **7 处视图之间互相 import**（§3），
   而 `toolbox.js` 已经被 designer / knowledge / workflow 三个视图依赖，
   事实上退化成了第二个 core 层，却住在 `views/` 目录里、没有任何规则保护。
   全局面越方便，依赖就越不被记录；依赖不被记录，就迟早成环。

**关键排序判断**：IA 文档原先把「前端事件委托」排在第 4 位、排在最后；
Phase 0 已把它重排到第 1 位。重排的理由是——它不是第 4 件事，
它是**解锁交互型组件与 designer 拆分的前提**：
不收窄全局面，组件要下发事件处理器还是得挂 window；
不收窄全局面，拆 `designer.js` 后必然出现跨模块调用。
纯展示组件（`pageHead` / `dataTable` / `tag`）不依赖这一点，可以并行做；
但**带行为的组件**必须先有委托根和 actions 注册表。

**目标**：`window` 上只保留三类东西，其余全部收进模块。

```js
// window 面上允许存在的，仅此三类：
window.go          // 路由
window.closeModal  // 模态
window.state       // 只读状态引用
// + 一个显式的 actions 注册表（见 §4.1）
```

### 2.3 状态没有 schema，且泄漏到根部

**证据**：

- `core/state.js` 为 `designer` 声明了 5 个键
  （`processId` / `processCode` / `model` / `analysis` / `tab`），
  实际使用了约 **20 个**（`st.*` 别名 + 直接访问合计）。
  另外 15+ 个（`bpmnModeler` / `bpmnSelection` / `bpmnLint` /
  `savedModel` / `positions` / `tools` / `toolMeta` / `processes` /
  `assignmentCtx` / `assignmentPending` / `bpmnFullscreenHandler` /
  `bpmnImporting` / `bpmnSidebarTab` / `editable` …）全部在运行时动态挂上去。
- **`state.docMeta` 同时被两个视图写、两个视图读**：
  `deliverables.js:48` 写、`designer.js:45` 写，
  `deliverables.js:313/321/467/468/611` 读、`designer.js:1017` 读。
  它是 `/process-documents/meta` 的缓存，却挂在 `state` 根部、没有命名空间。
- 同样在根部、运行时动态生成的还有 `state.dlvProjects`（`deliverables.js:43`）、
  `state.processes`（`deliverables.js:611`）、`state.sketchProjects`（`sketches.js:58`），
  这三个在 `core/state.js` 里根本不存在。
- **活对象混进状态袋**：`state.designer.bpmnModeler` 是活的 bpmn-js 实例，
  `state.designer.bpmnFullscreenHandler` 是 DOM 事件处理器。
  `state` 的注释写的是「只存界面态」，但这两者不是「态」，是「资源句柄」。

**后果**：`state` 事实上是一个**没有 schema 的全局可变对象**。
读 `state.docMeta` 的人必须先去两个文件里确认是谁写的、什么时候写的；
`state.designer.bpmnModeler` 在 `state` 里意味着 clone/序列化/调试打印都会踩到活对象。

**违反 CLAUDE.md 第 4 条**：「同一个概念只保留一个实现」——
`/process-documents/meta` 现在有两个写入点，是两套各自算各的雏形。

### 2.4 列表视图没有分页（knowledge 已修，其余待补）

**证据**：

- `knowledge.js:19` 硬编码 `page_size=50`，`knowledge.js:46` 在标题写
  「流程知识库（N 条）」，但 `:25` 只渲染 `d.page.items`——**第 51 条以后永远无法访问**，
  界面上也没有任何翻页入口。标题说 N 条，屏幕上只有 50 条。
- `execution.js:17-18` 拉 `limit=500` / `limit=200`；
  `deliverables.js:31` 拉 `page_size=200`；`designer.js` 不分页，全量拉。
- 全前端 **0 处**分页控件（`page` / `offset` / `totalPages` 均无命中）。

**后果**：现在数据量小（演示库）看不出来；一旦流程实例、异常、知识条目上量，
要么页面卡死，要么前端静默截断而用户以为看全了。**「总数」与「展示条数」不一致
是数据可信度问题**，不只是体验问题。

**建议先修**：`/knowledge` 后端已经支持 `page` / `page_size`（`app/api/v1/knowledge.py:50-51`），
前端只是没有把 `page` 传下去、也没有渲染翻页控件。这是一处独立、低风险、
用户可见的修复，**不必等 Phase 4**。

**修复状态（2026-10-24）**：`knowledge` 已补 `page` 参数与上一页/下一页控件，
标题总数与展示条数一致；后端分页测试已覆盖 total 不随 page_size 变化。
`execution` / `deliverables` / `projects` / `monitor` 仍是全量或固定上限拉取，待 Phase 4 补。

### 2.5 IA 文档只覆盖 10/13 页 —— **已修复（Phase 0，保留为回归触发条件）**

**原始证据**：`docs/ui-information-architecture.md` 的 §3 只有 10 个「### N.」小节。
导航里的 **PCF 分类框架**、**交付物与模板库**、**组织与人员** 三个页面
在全文中出现次数为 **0**。

**后果**：这三个页面的「主问题 / 元素关系 / 可视化选型 / 价值判定」没有定论，
后续改动没有判据可依。交付物与模板库是 44 个导出函数、1391 行的视图，
规模仅次于设计器，却是**唯一没有 IA 分析的复杂页面**。

**修复**：Phase 0 已补齐三页（并把 §3 重新编号为 13 节），
同时补了跨页面关系图里缺的两条关系（交付物是标准文件与项目之间的桥；
流程地图 ↔ PCF 是映射不是层级）。**现状：13/13 页均有 IA 分析。**
这条保留在文档里，作为「新页面必须同步补 IA」的触发条件——
新增导航项时，若 `docs/ui-information-architecture.md` 的小节数没有同步增加，
说明又漏了。

---

## 三、目标组织结构

```text
web/js/
  core/                    # 与业务无关的基础设施（不依赖任何视图）
    api.js  auth.js  format.js  metrics.js
    router.js  state.js  theme.js  notifications.js
    ui.js                  # 低层原语：toast / modal / tab
    components/            # ← 新增：可复用的 UI 片段（返回 HTML 字符串）
      page-head.js  filter-bar.js  data-table.js  card-grid.js
      tag.js  pager.js  confirm.js
  views/                   # 业务视图，每个视图对应一个页面
    dashboard.js  map.js  pcf.js  workflow.js  projects.js
    execution.js  toolbox.js  deliverables.js  monitor.js
    knowledge.js  orgs.js  sketches.js
    designer/              # ← 新增：designer 拆包（见 §2.1）
  actions.js               # ← 新增：唯一的 window 对外操作面（见 §4.1）
```

**依赖规则（单向，逐层向下）**：

```text
main.js ──→ views/* ──→ core/components/* ──→ core/{ui,format}/*
   │            │
   │            └──→ actions.js        (叶子注册表，只存名字 → 函数，不 import 视图)
   └──────────────→ actions.js
```

> **方向说明（重要）**：`actions.js` 是**叶子**，不得 import `views/*`。
> 视图需要调用别的视图时，import `{ actions }` 并调用 `actions['map.openProject'](...)`；
> `main.js` 作为组合根，import 各视图导出的 action map，调用
> `registerActions()` 注册进 `actions`。如果反过来让 `actions.js` import 所有视图，
> 而视图又 import `actions.js` 去调用别的动作，就会形成 `actions → views → actions` 的环。

- `core/*` **不得** import `views/*`（现状已满足）。
- `core/components/*` **不得** import `views/*`，也不得 import `core/router.js`
  （组件不负责跳转，跳转由调用方传入回调或 `data-act`）。
- `views/*` 之间**不得形成环**。直接 import 只允许指向 `views/shared/`（共享流程/纯逻辑）
  或 `core/*`；跨视图的导航与动作走 `actions`。
- `views/designer/*` 内部子模块只通过 `index.js` 传入的 `ctx` 访问画布，
  纯函数（XML 手术）下沉到 `xml.js`；`xml.js` 不得 import 任何画布相关模块。
- `toolbox.js` 被 3 个视图复用，Phase 3 必须二选一：
  上移到 `core/`（如果它是公共库），或留在 `views/` 但把共享部分移到 `views/shared/`；
  **不允许继续作为「一个视图被其他视图 import」的隐式公共库**。

#### 现状：视图之间已有 7 处互相 import

实测（`web/js/views/*.js`）：

```text
dashboard.js  → projects.js   (openProject)
map.js        → projects.js   (newProjectWizard)
map.js        → designer.js   (openDesigner)
projects.js   → designer.js   (openDesigner)
designer.js   → toolbox.js    (openToolByCode)
knowledge.js  → toolbox.js    (openToolByCode)
workflow.js   → toolbox.js    (openToolByCode)
```

依赖链是 `dashboard/map → projects → designer → toolbox`。
目前**没有成环**，但这是个**一碰就断的结构**：

- `toolbox.js` 被 3 个视图依赖，它已经事实上退化成了**第二个 core 层**——
  但它住在 `views/` 目录里，没有「公共库」的待遇（没有依赖规则保护、没有单测）。
- 成环只需一步：一旦 `toolbox.js` 需要 import `projects.js`
  （例如「从工具箱直接为此步骤立项」），就会形成
  `designer → toolbox → projects → designer` 的真环。

**Phase 3 的处理方式**：目标是**消除环与隐式公共库**，不是机械地清零所有 import。
- 导航/动作类（`openProject`、`newProjectWizard`、`openDesigner`）→ 走 `actions`；
- 共享 helper（`openToolByCode`）→ 上移为 `views/shared/toolbox.js` 或 `core/`；
- 允许 `views/shared/` 作为显式的共享层，但**禁止** `views/a.js → views/b.js → views/a.js`
  这种环，也禁止把业务逻辑塞进 `actions` 成为新的上帝对象。

---

## 四、交互契约

### 4.1 `window` 面收窄：显式 actions 注册表

**约定**：`main.js` 不再 `Object.assign(window, ...视图导出)`，
改为只挂一个显式注册表。`actions.js` 是**叶子模块**，只存「名字 → 函数」，
不得 import 任何视图。

```js
// web/js/actions.js
export const actions = {};

export function registerActions(map) {
  for (const [name, fn] of Object.entries(map)) {
    if (typeof fn !== 'function') throw new Error(`action ${name} 不是函数`);
    if (actions[name]) throw new Error(`action 重名：${name}`);
    actions[name] = fn;
  }
}
```

每个视图只导出真正需要跨视图调用的动作，键必须带视图前缀：

```js
// web/js/views/map.js
export const actions = {
  'map.openProject': openProject,
  'map.openDesigner': openDesigner,
};
```

`main.js` 作为组合根收集并注册：

```js
import { actions, registerActions } from './actions.js';
import * as mapView from './views/map.js';
// ...
registerActions({ ...mapView.actions, ...pcfView.actions, ... });
Object.assign(window, { go, closeModal, state, actions });
```

模板里写 `onclick="actions['map.openProject'](3)"`——
全局面上只剩 3 个工具 + 一个命名空间。

**注意**：「撞名不可能发生」只在 action 键唯一时成立。`registerActions` 在启动时查重，
静态守卫再补一条「action 键 / `data-act` 键唯一」；`pcf.js` 与 `map.js` 的
`togglePcfNode` 撞名已经证明扁平命名空间不是天然安全的。

**配套静态检查**（见 §7）：模板里 `onclick="actions[...]"` 引用的键，
必须在 `actions` 里或全局白名单里存在，否则测试失败。

### 4.2 事件委托：让组件能自带行为

内联 `onclick` 的根本问题是**行为写在 HTML 里**，于是：
行为无法被组件复用、无法被静态检查、无法被单元测试。

**约定**：新增交互一律用 `data-` 属性 + 委托，行为写在 JS 里。

```html
<!-- 旧：行为在 HTML 里，无法复用、无法检查 -->
<button class="btn btn-p" onclick="openDeliverable(3)">打开</button>

<!-- 新：语义在 HTML，行为在 JS -->
<button class="btn btn-p" data-act="deliverable.open" data-id="3">打开</button>
```

在 `core/ui.js` 统一挂委托根。**不能只监听 `click`**：现存 126 处
处理器的分布是 `click 112` / `change 14`，筛选器和表单主要靠 `change`。
另外 `<select>` / checkbox 会同时触发 `input` 与 `change`，
委托根必须只处理 `change`，否则一次操作会执行两次（已在实现中拦截）。

```js
const DELEGATES = {};               // data-act → handler
export function on(act, handler) { DELEGATES[act] = handler; }

const BUBBLING_EVENTS = ['click', 'change', 'input', 'submit', 'keydown'];
for (const type of BUBBLING_EVENTS) {
  document.addEventListener(type, (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const fn = DELEGATES[el.dataset.act];
    if (!fn) return;
    if (type === 'keydown') {
      // 只为非原生控件补 Enter/Space；原生 button/a 由浏览器处理
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
    }
    fn(el.dataset, el, e);
  });
}
```

例外与边界：

- `toggle` 事件**不冒泡**，`ontoggle` 不能走委托根；`<details>` 的状态变化用直接监听，
  或改用 `click` + class 切换。
- 表单回车提交走 `submit`，不会触发 `click`；分页、搜索、筛选必须有 `submit` 兜底。
- bpmn-js 画布、draw.io iframe、图表库继续用各自的原生监听，不强行套 `data-act`。
- **可访问性**：`data-act` 只允许挂在 `<button>` / `<a>` 上；静态守卫拒绝
  `div/span[data-act]`。这会把现有 126 处里的一部分「可点击 div」顺手修成键盘可用控件。
- **转义**：`data-act` 的值必须是静态字符串，禁止拼接用户输入；
  其余 `data-*` 与文本一律走 `esc`。事件委托消除了 `onclick="...${name}..."` 的注入面，
  但组件返回 HTML 字符串时仍必须统一转义。

**迁移策略**：**不要求一次性改完**。新代码走 `data-act`；
存量 126 处内联处理器在 §6 的 Phase 2 逐视图迁移，
每个视图迁移完即删掉该视图对应的 window 导出与 action 注册。
已完成 11 个视图；剩余 `deliverables`（66 处）与 `designer`（45 处）。
删除类确认统一用 `confirmDialog`；可点击行统一改成「名称按钮」或主按钮；
`execution` 的挂起原因改用 `promptDialog`。

### 4.3 共享组件清单

从现有重复中抽出来的（括号内为当前重复次数，均为实测值）：

| 组件 | 抽取自 | 次数 |
|---|---|---|
| `pageHead({title, badge, desc, actions, tabs})` | 各视图页头 | 12 |
| `dataTable({cols, rows, empty})` | 各视图表格 | 49 |
| `cardGrid(items, renderItem)` | 卡片栅格 | 18 |
| `emptyState(msg, action)` | 空状态 | 27 |
| `tag(kind, text)` | 标签（`format.js` 已有 `methodTag`/`statusTag`，应统一并扩充） | 85 |
| `pager(page, onChange)` | **新增**，配合 §2.4 | 0 |
| `confirmDialog(msg, onOk)` | **新增**，替换原生 `confirm()`（实测 16 处） | 16 |
| `promptDialog(...)` | **新增**，替换原生 `prompt()`（实测 4 处） | 4 |

**原生对话框必须替换**：`confirm()` / `prompt()` 是浏览器原生弹窗，
和本系统自建的模态框（`core/ui.js` 的 `openModal`）视觉、行为、可访问性全不一致，
且不可换肤、不可统一文案。这 19 处是「专业度」上最刺眼的细节。

**组件层纪律**（与 CLAUDE.md「不要在前端硬编码枚举中文」同源）：

- 组件**只负责结构**，不负责业务判断；颜色一律 `var(--token)`。
- 组件**不 fetch 数据**，只接收数据；取数在视图里做。
- 组件**不 import 视图**；需要跳转时由调用方传入回调。

---

## 五、状态约定

**约定**：

1. **每个视图的状态有自己命名空间，且在 `core/state.js` 里一次性声明完整。**
   现在 `state.designer` 声明 5 个、用约 20 个，多出的部分是运行时动态挂的——
   这类「隐式字段」正是拼错字段名不报错的根源。
   **注意**：视图里大量使用 `const st = state.designer` 别名，
   纯正则的「声明键 ⊇ 使用键」检查会漏报；要么写路径感知的分析器，要么在 dev 模式
   用 Proxy 包装 `state`，访问未声明键时 `console.warn`。后者在零构建项目里更可靠。
2. **视图私有状态不放在 `state` 根部。**
   `state.docMeta` → `state.shared.docMeta`（或抽到 `core/doc-meta.js` 做独立缓存模块）；
   `state.dlvProjects` → `state.deliverables.projects`；
   `state.processes` → 明确归属 `state.map` 或 `state.deliverables`；
   `state.sketchProjects` → `state.sketches.projects`。
3. **活对象不进 `state`。**
   `state.designer.bpmnModeler`（bpmn-js 实例）、`bpmnFullscreenHandler`（DOM handler）
   属于**资源句柄**，移到视图模块内的模块级 `let`，或放进 `state.designerHandles`
   这类显式命名的句柄区，并在注释里写明「不入 state 快照、不参与序列化」。
4. **共享缓存单写点。**
   `/process-documents/meta` 这类被多视图使用的缓存，
   收敛到一个 `core/cache.js`（`getDocMeta()`），由它负责取数与写缓存。
   两个视图各写一次 `state.docMeta` 的做法必须合并。

---

## 六、迁移顺序（每阶段可独立提交、独立验证）

> **顺序本身是这份文档最重要的部分。** 前一阶段不落地，后一阶段做不了或者做不对。

### Phase 0 — 补文档 + 冻结基线（不改业务代码）

- 给 IA 文档补 PCF 分类框架、交付物与模板库、组织与人员三页的
  「主问题 / 元素关系 / 可视化选型 / 价值判定」，与既有页面同格式。
- 把 IA 文档「后续优先级」第 4 条（事件委托）移到第 1 位，并说明它是前置解锁项。
- 补 IA 文档的跨页面关系图：补上「交付物与模板库是标准文件与项目之间的桥」
  和「流程地图 ↔ PCF 是映射、不是层级」这两条关系。
- **Phase 0.5：先提交现有未提交改动**（P0 岗位/工时、PCF 集成分别提交），
  冻结基线，再按附录 A 重新测量。工作区有 30+ 个未提交文件时不要开始重构。

**验收**：IA 文档覆盖 13/13 页；优先级顺序与本文 §6 一致；本文数字与当前代码一致；
`git status` 干净或只剩本次文档提交。

> **状态：已完成。** 三页已补齐并重新编号（13/13），优先级已重排，
> 跨页面关系图已补两条。Phase 1A/1B 已完成；Phase 2–4 尚未开始。

### Phase 1 — 交互原语 + 垂直试点（前置解锁）

**1A：只加能力，不动存量视图**

- 新建 `core/actions.js` 叶子注册表（`registerActions` 启动时查重）。
- 新建 `core/ui.js` 的多事件委托根 `on(act, handler)`
  （click / change / input / submit / keydown；`toggle` 不冒泡，单独处理）。
- 新建 `confirmDialog` / `promptDialog`；存量 19 处原生弹窗随 Phase 2 逐视图替换。
- 补静态守卫：视图导出唯一、`data-act` 键带前缀且只挂交互元素、
  原生弹窗数量不增长、actions 叶子不得 import 视图。

**1B：`knowledge` 垂直试点（端到端验证契约）**

- 把 `knowledge` 的 15 处内联处理器（含分页 2 处）改成 `data-act`；
- 分页控件已在快速修复中完成（`page` 参数 + 上一页/下一页）；
- 用这个试点验证「委托 + actions + 分页」的组合，组件抽取留到 Phase 2
  用更多视图的真实重复再定接口。

**验收**：`python scripts/check.py` 与 E2E 通过；`knowledge` 的内联处理器归零；
分页可访问全部数据。

> **状态：1A/1B 已完成（2026-10-24）。**
> `actions.js`、多事件委托、`confirmDialog` / `promptDialog` 已落地；
> `knowledge` 内联处理器归零，window 导出从 8 个降到 1 个，分页 E2E 通过。
> 组件抽取按「不先建齐」原则留到 Phase 2。

### Phase 2 — 逐视图迁移到委托 + 组件（可拆分多个提交）

顺序建议：**从小的、依赖少的视图开始**——
`deliverables` → `designer`（最后）；
其余 11 个视图已完成。

每个视图的迁移动作：
1. 该视图的内联处理器改为 `data-act`（按 §4.2 的事件类型分别处理）；
2. 重复的页头/表格/空状态改用组件；
3. 该视图的 window 导出改为 `export const actions = {...}` 并带视图前缀；
4. 该视图涉及列表的，补分页控件；标题的「N 条」与展示条数必须一致。

**验收**：
- `window` 上的导出数量与内联处理器数量每迁一个视图就降一批；
- 浏览器端到端自检 `python scripts/verify_frontend.py http://127.0.0.1:8123` 通过。

> **状态：进行中（2026-10-24）。** 11 个视图已完成迁移；剩余
> `deliverables`（66 处）与 `designer`（45 处）。
> 删除类确认统一用 `confirmDialog`，挂起原因用 `promptDialog`；
> 可点击行统一改成「名称按钮」或主按钮。
> 本阶段先只保留 `renderX` 与确有跨视图引用的函数
> （`openToolByCode` / `openProject` / `newProjectWizard` / `renderRecommendation` 等），
> 显式 `actions` map 与 `main.js` 收口统一放到 Phase 3，避免中途出现两套入口。

### Phase 3 — 收窄 window 面 + 拆 designer + 清环

- `main.js` 改为只挂 `{ go, closeModal, state, actions }`，并由它收集、注册各视图的 action map。
- **处理 7 处视图间直接 import**（§3），目标是消除环与隐式公共库，不是机械清零：
  - 导航/动作类：`dashboard→projects`、`map→projects`、`map→designer`、`projects→designer`
    改走 `actions`；
  - 共享 helper：`designer/knowledge/workflow→toolbox` 的 `openToolByCode`
    上移到 `views/shared/toolbox.js` 或 `core/`；
  - 允许 `views/shared/` 作为显式共享层，但禁止环，也禁止把业务逻辑塞进 `actions`
    变成新的上帝对象。
- `designer.js` 拆成 `views/designer/` 子目录：先定 `ctx` 接口契约（§2.1），
  再把 `xml.js` 纯函数抽出来并补特征测试；其余模块按职责拆分。
- 拆完后，`toolbox.js` 要么上移到 `core/`，要么共享部分移到 `views/shared/`——
  **二选一，不留两套**。

**验收**：`tests/test_frontend_structure.py` 的注册断言仍然通过（外部契约没变）；
视图之间不存在环；designer 子模块只通过 `ctx` 访问画布，
各文件按职责内聚设上限（`xml.js` 可放宽到约 700 行，但必须有特征测试）。

### Phase 4 — 状态 schema 与其余分页

- `core/state.js` 补全 `state.designer` 的约 20 个字段并标注类型与用途。
- 落实 §5 的四条约定（命名空间、活对象外移、共享缓存单写点）。
- 给 `execution` / `deliverables` / `projects` / `monitor` 补分页控件；
  `knowledge` 的分页已在 Phase 1B 试点完成。标题的「N 条」与实际展示条数必须一致。

**验收**：新增守卫保证
（a）`state` 访问未声明键会告警（dev Proxy 或路径感知分析器，需处理 `st` 别名）；
（b）模板里 `actions[...]` 引用的键在注册表中；
（c）没有残留原生 `confirm(` / `prompt(`；
（d）视图之间无环、`window` 全局键数量低于当前基线（约 111）。

---

## 七、测试守卫补强清单

现有 `tests/test_frontend_structure.py` 检查「文件存在 / import 路径正确 / 视图已注册 /
视图导出符号唯一」。组织方式变复杂后，以下错误仍会静默通过，必须补上：

| 检查 | 拦截的问题 | 阶段 |
|---|---|---|
| 视图导出符号唯一 | `window` 覆盖（**已有真实事故**：`togglePcfNode`） | **已实现** |
| action 键 / `data-act` 键唯一且带视图前缀 | 注册表互相覆盖 | Phase 1 |
| 模板中 `actions[...]` 引用的键在注册表或全局白名单 | 拼错 / 漏注册 → 按钮静默无反应 | Phase 1 |
| `data-act` 只出现在 `<button>` / `<a>` 上 | 键盘不可用、可点击 div | Phase 1 |
| 视图文件不得含原生 `confirm(` / `prompt(` | 弹窗风格不一致 | Phase 1 |
| 每种事件类型的剩余内联处理器数量 | 迁移漏项（`change` / `input` 最易漏） | Phase 2 |
| `window` 全局键数量预算（当前约 111） | 全局面在迁移中反弹 | Phase 2 |
| 视图之间**无环**；直接 import 只指向 `views/shared/` 或 `core/` | 循环依赖、隐式公共库 | Phase 3 |
| `core/*` 不得 import `views/*` | 分层倒置 | Phase 3 |
| designer 子模块只通过 `ctx` 访问画布、XML 纯函数有特征测试 | 拆包后互相 import | Phase 3 |
| `state` 访问未声明键会告警（dev Proxy 或路径感知分析） | 拼错状态键 → 静默 undefined | Phase 4 |
| 单文件职责/行数上限（按内聚设置，不搞一刀切） | `designer.js` 再次膨胀 | Phase 3 |

---

## 八、明确不做的事

- **不引入 Vue / React / 任何构建工具。** 现有痛点是组织问题，不是框架能力问题。
  详见 README「为什么不引入 Vue」；若日后引入，设计令牌与组件层可原样复用，
  本文 §4.3 的组件契约就是迁移到框架组件的自然接口。
- **不重写 IA 已确定的产品决策。** 本文只管组织，不推翻「一页一主问题」等既有结论。
- **不做一次性大改写。** 按 §6 分阶段，每阶段独立提交、独立验证；
  尤其 Phase 2 按视图逐个推进，不做「全量替换内联处理器」这种不可 review 的改动。
- **不在 `core/` 里写业务。** `core/components/` 只做结构，不懂「流程」「项目」「交付物」。
- **不在前端维护枚举中文映射。** 沿用 CLAUDE.md 约定：标签一律由后端下发。

---

## 附录 A：测量基线与复核命令（2026-10-24）

| 指标 | 当前值 |
|---|---|
| 手写 JS 模块 | 25 |
| JS 总行数 / views 行数 | 11,457 / 10,014 |
| `designer.js` | 2,448 行；92 个顶层函数声明（约 106 个命名函数） |
| 视图导出符号 / `window` 全局键 | 99 / 约 111 |
| 内联事件处理器 | 126（click 112、change 14） |
| `data-act` 键 | 161（11 个已迁移视图） |
| 视图内原生 `confirm` / `prompt` | 7（全部在 designer） |
| 组件重复 | 页头 12、表格 49、栅格 18、空状态 27、标签 85 |
| 视图间直接 import | 7 条边 |

复核命令（在仓库根目录执行）：

```bash
# 模块与行数
find web/js -name '*.js' | wc -l
find web/js -name '*.js' -print0 | xargs -0 cat | wc -l
wc -l web/js/views/*.js
wc -l web/js/views/designer.js
grep -cE '^(async )?function ' web/js/views/designer.js

# 内联处理器（总数与按事件类型）
grep -roE 'on(click|change|input|submit|keydown|keyup|blur|focus|toggle)="' web/js web/index.html | wc -l
for ev in click change input submit keydown toggle; do
  printf '%-8s ' "$ev"; grep -roE "on$ev=\"" web/js web/index.html | wc -l
done

# 原生对话框（只数视图；core/ui.js 的实现和注释不算）
grep -roE '\b(confirm|prompt|alert)\(' web/js/views | wc -l

# data-act 键（应带视图前缀）
grep -rhoE 'data-act="[^"]+"' web/js/views | sort -u | wc -l

# 组件重复次数
grep -roE 'class="[^"]*page-head[^"]*"' web/js/views | wc -l
grep -roE '<table class="tbl[^"]*"' web/js/views | wc -l
grep -roE 'class="grid g[0-9]' web/js/views | wc -l
grep -roE 'class="empty"' web/js/views | wc -l
grep -roE 'class="tag ' web/js/views | wc -l

# 视图导出重名守卫（真实事故：togglePcfNode）
python -m pytest tests/test_frontend_structure.py::test_view_exports_do_not_collide
```

> 这些数字会随业务改动变化。**每个 Phase 开始前重跑一遍**；若与本文不符，
> 以代码为准并更新本文，不要拿旧基线做验收。
