# 流程经营绑定模型

> **一句话**：流程不是一张图，也不是一份 SOP；流程是把「定目标、搭班子、配资源、开启智慧与绩效落地」绑在同一个经营对象上的机制。
>
> 状态：主模型整合稿 + 现状静态核对（2026-11-09，当前工作树）。本文描述目标形态与缺口，**不代表已实现**；未运行应用与测试。
> 关联专项：战略闭环 [enterprise-process-strategy-loop.md](enterprise-process-strategy-loop.md)、组织治理 [process-organization-governance-loop.md](process-organization-governance-loop.md)、绩效闭环 [process-performance-decision-loop.md](process-performance-decision-loop.md)、资产生产 [asset-production-plan.md](asset-production-plan.md)。本文不替代专项，只统一它们共用的**主键与绑定面**。

## 0. 定论

1. 当前系统是**流程资产生产系统**：能把已发布模型编译成流程级资产包，回答「这条流程的标准是什么」。
2. 目标形态是**流程经营产出系统**：回答「这个岗位每天做什么、受什么控制、产出什么、被谁评价」。
3. 两者不是推翻关系。资产包是原料之一；经营产出是编译结果。
4. 升级的关键不是再加资产类型，而是把四类绑定合拢到 **L4 活动**，并让绑定发生在**设计器**。
5. 五类产物（员工手册 / 岗位责任书 / 流程覆盖度 / 岗位覆盖度 / 工作量）都是绑定的只读投影，不新建源数据。

## 1. 经营主链

企业无论什么战略，最终都分解为两类目标，经过落地与执行，落到流程上：

```text
企业目标
├─ 开源：增长 —— 规模、利润
└─ 节流：降本 —— 费用、成本
        ↓ 落地
├─ 配资源：钱、人、产能流向价值方向
└─ 搭班子：岗位、能力、责任承接目标
        ↓ 执行
├─ 正确的事：关键过程受控
└─ 正确的方法：有结果、可持续
        ↓ 载体
流程（L3 经营对象）
        ↓ 绑定
L4 活动（唯一主键）
  ├─ 定目标：目标 / KPI / 基线 / 目标值
  ├─ 搭班子：Owner / 岗位 / RACI / 唯一 A
  ├─ 配资源：工时 / 预算 / 产能 / 表单 / 规则 / 设备 / IT / 接口
  └─ 开启智慧与绩效：方法 / 知识 / 培训 / SOP / 控制点 / 证据
        ↓ 编译
员工手册 / 岗位责任书 / 流程覆盖度 / 岗位覆盖度 / 工作量
```

**口径说明**：「开启智慧」本文采用你给出的定义——**方法、知识、培训、标准作业**。第四绑定面在数据上对应 SOP/制度、方法工具、培训记录、控制点、证据主张。若定义变化，必须在 P2 门禁前调整，因为 METHOD 面的就绪规则依赖它。

## 2. 主模型：L4 活动 × 四个绑定面

### 2.1 为什么主键是 L4 活动

| 层级 | 适合承载 | 不适合承载 |
| --- | --- | --- |
| L1/L2 | 价值链、能力域、经营结果汇总 | 岗位、工时、表单；太粗 |
| **L3 流程** | **经营对象**：目标承接、预算、Owner、版本 | 具体谁做、做多久、用什么表单 |
| **L4 活动** | **唯一业务主键**：目标、班子、资源、方法、证据 | 单个执行实例 |
| L5 任务 | 可执行步骤、标准工时细分 | 全公司统一口径；只有部分流程需要 |
| BPMN 节点 | 顺序、方向、分支、交接的可视化实现 | 业务主键；同一活动可有多个节点实现 |

L4 活动已经有稳定身份（`app/models/process.py:30` 的 `ProcessArch.level`），并且已被标准工时（`app/models/workload.py:41`）、KPI（`app/models/monitor.py:91`）、任务定义（`app/models/process_task.py:29`）引用。**节点不是主键**：节点与活动是多对多，带关系语义与路径条件（`app/models/asset_graph.py:36`）。

### 2.2 四个绑定面

| 绑定面 | 回答的问题 | 绑定对象 | 现有主数据来源 | 必需性 |
| --- | --- | --- | --- | --- |
| 定目标 | 这个活动为哪个经营结果负责？ | KPI、目标值、基线、口径 | `KpiDefinition`（流程/活动级）、`StrategyObjective` + `ObjectiveProcessLink` | 绩效版必需 |
| 搭班子 | 谁负责、谁执行、谁咨询、谁知会？ | 岗位、Owner、治理角色、RACI-A | `Position`、`ProcessNode.owner_position_id`、`RaciAssignment` | 执行版必需 |
| 配资源 | 靠什么完成、花多少时间/钱、占多少产能？ | 工时、表单、规则、接口、设备、技术 | `WorkMeasurementStandard`、`CapacityCalendar`、`FormDefinition`、`ProcessRule`、`IntegrationEndpoint`、`ProcessTechnologyUse` | 执行版必需 |
| 开启智慧与绩效 | 按什么标准做、如何证明有效？ | SOP/制度、方法工具、培训、控制点、证据 | `ProcessDocument`、`NodeTool`、`ProcessTrainingRecord`、`NodeActivityLink(CONTROLS)`、`EvidenceClaim` | 绩效版必需 |

### 2.3 继承规则

继承只对**已有流程级语义**的对象成立，不做名称猜测：

| 绑定面 | 可继承的对象 | 继承方式 |
| --- | --- | --- |
| 定目标 | 流程级 KPI（`activity_id IS NULL`） | 节点/活动无专属 KPI 时显示为「继承」，计部分就绪 |
| 搭班子 | 无隐式继承 | 必须在活动/节点上明确 RACI-A；流程级 RACI 只算「流程事项」 |
| 配资源 | 默认表单（`FormDefinition.node_key=""`）、流程级标准文件（`ProcessDocument.node_key IS NULL`） | 已有明确语义，可直接回退 |
| 开启智慧 | 流程级 SOP/制度 | 同标准文件；培训记录仍是流程级，只计部分就绪 |

规则：**缺口就是缺口，不用「默认值」掩盖责任空缺**。继承来的绑定必须在界面上标明来源，不能与直接绑定混在一起。

### 2.4 五条绑定原则

1. **一次录入，多处只读**：其他页面只显示「已绑/未绑」，缺口的按钮回到设计器对应节点。
2. **绑定发生在图上**：只有图能同时回答「谁、在什么顺序、用什么、产出什么、被谁接收」。
3. **绑定跟版本走**：键用 `process_id + node_key + activity_id`，发布时冻结快照；升版未确认的绑定不能生成正式产物。
4. **活动是语义主键，节点是画布主键**：资源/责任优先落活动；确属节点特有的表单/规则才落 `node_key`。
5. **产物不复制源数据**：只保存引用、快照 hash 与生成清单。

## 3. 绑定台：设计器

### 3.1 交互形态

```text
画布节点角标
  红：缺必需绑定（活动 / 岗位 / RACI-A / 工时 / 表单或记录）
  黄：有绑定但不完整（缺 KPI / SOP / 证据）
  绿：当前发布档位所需绑定齐全

右侧抽屉（目标形态）
  基本 | 目标 | 班子 | 资源 | 智慧绩效 | 执行 | 校验
```

落地分两步，避免第一刀就重构抽屉：

- **P0**：在现有 5 个页签（基本 / 责任 / 测算 / 文件 / 执行）后增加一个只读「绑定」页签，内含四个分组；画布角标与流程级四面包裹条同步上线。
- **P1**：当四个面都有可编辑动作后，再把「绑定」拆成「目标 / 班子 / 资源 / 智慧绩效」四个页签。URL/state 只认页签 id，拆分不影响后端契约。

### 3.2 三个发布点，不要混成一个门禁

| 发布点 | 现有实现 | 应检查的档位 | 建议行为 |
| --- | --- | --- | --- |
| 模型发布（设计冻结） | `app/api/v1/designer.py:555` 的 `publish_model`；只查模型版本/变更单 | 不阻断 | 记录绑定快照 + 提示缺口；设计阶段允许不完整 |
| 执行上线确认 | `ProcessExecutionConfig.readiness`（`app/models/execution.py:340`） | 执行版 | 硬阻断：活动映射、岗位、RACI-A、工时、表单/记录载体 |
| 资产包/产物评审 | `asset_graph.readiness` 的 `can_submit_review`（`app/services/asset_graph.py:694`） | 绩效版 | 硬阻断四绑定；KPI/SOP/证据按用途分级 |

「发布前做绑定性门禁」如果指模型发布，会把设计过程卡死；建议把硬门禁放在**使用点**，模型发布只做快照与告警。这是本文的明确建议，需你确认（见 §9 决策点 4）。

### 3.3 批量与继承

- 选中多个节点，一次绑同一岗位 / 表单 / 规则 / 标准文件。
- 从相似活动复制绑定（只复制引用，不复制正文）。
- 流程级默认绑定只对 §2.3 列出的对象生效，界面标注「继承」。
- 升版后，与快照不一致的绑定标「待确认」，不阻断草稿，阻断正式产物。

## 4. 五类产物：都是编译结果

| 产物 | 回答的问题 | 编译输入 | 版本与审批 |
| --- | --- | --- | --- |
| 员工手册 | 这个岗位/角色要遵守哪些流程、用什么表单、看什么标准？ | 岗位/治理角色 → 流程 → 活动 → SOP/表单/规则/工具/控制点 | 复用文档版本状态机 |
| 岗位责任书 | 这个岗位承担哪些活动、负什么责、多少工作量、看什么指标？ | 岗位 → 活动 → RACI / 工时 / 表单 / 控制点 / KPI | 复用文档版本状态机 |
| 流程覆盖度 | 公司有哪些关键过程？流程覆盖了哪些？哪里重复、交叉、断点？ | `ProcessArch` + `NodeActivityLink` + `UnmodeledActivity` + 同级边界 + 文档/KPI | 快照 + 人工确认 |
| 岗位覆盖度 | 每个岗位参与哪些流程/活动，RACI 与工时负荷如何？ | 岗位 → 节点/活动 → RACI / 工时 / 任务 | 只读查询，可按期快照 |
| 工作量 | 按岗位、按流程的需求/产能/实际工时是多少？ | 标准工时 × 频次 + 产能日历 + 实际工时 | 期间口径，按月重算 |

### 4.1 岗位责任书

```text
岗位
  ├─ 参与流程 / 关键活动
  ├─ 每个活动的 RACI（尤其唯一 A）
  ├─ 表单、规则、控制点
  ├─ KPI 与目标值
  └─ 工作量：标准工时 × 频次、实际工时、负荷率
        ↓ 编译
责任书草稿（可回溯到每个活动与源对象）
```

### 4.2 员工手册

不是行政规范汇编，而是**按岗位/角色重排的作业规范**：这条流程的哪一段由你执行、用什么表单、遵守哪条规则、看哪个控制点、异常找谁。它与岗位责任书的区别：责任书回答「你负什么责、多少量」，手册回答「你具体怎么做」。

### 4.3 流程覆盖度

需要先定义「关键过程」。当前系统没有这个字段（全仓检索 `关键过程 / critical_process / is_key` 无匹配）。建议在 `ProcessArch` 上增加 `is_key_process` 与 `key_basis`，由业务显式勾选并写依据，**不从名称或 PCF 类别自动推断**。

覆盖度矩阵至少回答：

- 关键活动清单（L4）；
- 每个关键活动被哪些流程/节点实现（`NodeActivityLink`）；
- 哪些关键活动未建模（`UnmodeledActivity`）；
- 哪些活动被多条流程同时实现（重复/交叉）；
- 同级流程边界是否已评审、是否声明重叠（`SiblingBoundaryReview` / `SiblingBoundaryLine`）；
- 缺口对应哪个岗位、制度、系统。

### 4.4 岗位覆盖度

数据零件已经存在，但没有汇总：

- `ProcessNode.owner_position_id`（`app/models/process.py:178`）
- `WorkMeasurementStandard.activity_id + position_id`（`app/models/workload.py:41`、`:51`）
- `ProcessTaskDefinition.activity_id + position_id`（`app/models/process_task.py:29`、`:36`）
- `ProcessTask.activity_id` + 处理人 `User.position_id`（`app/models/execution.py:128`、`:150`）
- `RaciAssignment.role_id` → `GovernanceRoleMember.user_id` → `User.position_id`（`app/models/raci.py:67`）

**注意**：RACI 绑的是治理角色，不是岗位（`app/models/raci.py:91`）。角色到岗位只能经由成员反推，存在「一个角色多人、多岗位」与「角色无人」两种歧义。岗位覆盖度必须把这两种情况显式标为「角色无法归位」，不能静默分摊。

### 4.5 工作量

`app/services/workload.py:548` 的 `summary` 已经返回：

- 标准工时行（活动 × 岗位 × 频次 × 需求分钟）；
- 实际工时行（活动 × 岗位 × 任务数 × 实际分钟）；
- 产能行（组织 × 岗位 × 可用/需求/缺口/负荷率）；
- 总计。

缺的不是数据，而是**汇总口径**：按岗位、按流程/关键过程的分组小计，以及与 RACI/岗位责任书的联动。

## 5. 现状核对（证据）

> 核对方式：读取当前工作树源码与全仓检索，未启动服务、未跑测试。日期 2026-11-09。

### 5.1 已有零件

| 能力 | 现有实现 | 状态 | 证据 |
| --- | --- | --- | --- |
| 流程骨架 L1–L4 | `ProcessArch` | 已有 | `app/models/process.py:30` |
| 节点 / 连线 / 模型版本 | `ProcessNode` / `ProcessEdge` / `ProcessModelVersion` | 已有 | `app/models/process.py:152`、`:240`、`:267` |
| 节点 → L4 活动 | `NodeActivityLink`（版本、关系、路径、覆盖率） | 已有 | `app/models/asset_graph.py:36` |
| 未建模活动 | `UnmodeledActivity` | 已有 | `app/models/asset_graph.py:186` |
| 岗位主数据 | `Position` | 已有 | `app/models/org.py:56` |
| 节点责任岗位 | `ProcessNode.owner_position_id` | 已有 | `app/models/process.py:178` |
| 节点责任角色文本 | `ProcessNode.owner_role` | 已有但未统一 | `app/models/process.py:170` |
| RACI | `RaciAssignment(process_id, matter, role_id, raci)` | 半成品 | `app/models/raci.py:80` |
| 标准工时 | `WorkMeasurementStandard`（活动 × 岗位） | 已有 | `app/models/workload.py:31` |
| 产能日历 | `CapacityCalendar` | 已有 | `app/models/workload.py:164` |
| 实际工时 | `ProcessTask.activity_id` + `TaskWorklog` | 已有 | `app/models/execution.py:112`、`:128` |
| KPI | `KpiDefinition`（可绑流程/活动） | 已有 | `app/models/monitor.py:26`、`:87`、`:91` |
| 战略目标与承接 | `StrategyObjective` + `ObjectiveProcessLink` | 部分（无目标类型） | `app/models/strategy.py:30`、`:70` |
| SOP / 制度 | `ProcessDocument`（流程级、可按 `node_key`） | 已有（流程级） | `app/models/process_document.py:32`、`:56` |
| 表单 / 规则 | `FormDefinition` / `ProcessRule`（可绑节点） | 已有 | `app/models/execution.py:283`、`:312` |
| 节点分派 / 时限 | `NodeAssignment` | 已有 | `app/models/execution.py:374` |
| 同级边界评审 | `SiblingBoundaryReview` / `SiblingBoundaryLine` | 已有 | `app/models/adoption.py:30`、`:53` |
| 公司工作清单 | `MapCoverageItem` | 已有 | `app/models/adoption.py:75` |
| 培训记录 | `ProcessTrainingRecord`（流程级） | 部分 | `app/models/adoption.py:117` |
| 技术使用 | `ProcessTechnologyUse`（流程级） | 部分 | `app/models/adoption.py:210` |
| 资产就绪度 | `asset_graph.readiness` 的阻断码 | 已有（非四绑定） | `app/services/asset_graph.py:528` |
| 四路使能度 | `alignment._enablers` | 已有（目标级） | `app/services/alignment.py:33`、`:226` |
| 工作量汇总 | `workload.summary` 行级 + 总计 | 部分（无分组汇总） | `app/services/workload.py:548` |
| 设计器节点抽屉 | 基本 / 责任 / 测算 / 文件 / 执行 | 部分 | `web/js/views/designer/panels.js:90` |
| 设计器页签 | 流程模型 / 测算分析 / 权责 / 变更 | 部分 | `web/js/views/designer/index.js:194` |

### 5.2 四绑定真实状态

| 绑定面 | 是否绑到 L4 活动 | 判断 | 主要缺口 |
| --- | --- | --- | --- |
| 定目标 | KPI 可以；目标主要到 L3 | 部分 | 目标无「开源/节流」类型；目标到活动不完整 |
| 搭班子 | 岗位可以；RACI 不可以 | **断的** | RACI 的「事」是自由文本；`owner_role` 与 `owner_position_id` 两套口径 |
| 配资源 | 工时可以；表单/规则到节点；预算到项目 | 部分 | 没有统一的「活动靠什么完成」引用；设备/IT/接口散落 |
| 开启智慧与绩效 | 文档到流程/节点；培训到流程 | 部分 | 方法/培训/SOP 没有按活动合拢；证据未与责任链对齐 |

### 5.3 七个结构性断点

#### 断点 1：RACI 的「事」不是活动 ID

`RaciAssignment` 是 `process_id + matter`（自由文本）+ `role_id` + `raci`（`app/models/raci.py:80`–`:106`）。这导致：

- 无法计算岗位 RACI 负荷；
- 无法生成岗位责任书；
- 无法判断「每个活动是否唯一 A」；
- 历史 `matter` 与活动之间只能人工映射。

#### 断点 2：责任口径分裂

- 设计器「责任」页保存的是 `owner_position_id`（`web/js/views/designer/panels.js:198`–`:207`）；
- 资产就绪度检查的是 `owner_role` 文本（`app/services/asset_graph.py:568`、`:643`）。

结果：只填了岗位、没填角色文本的节点，会被资产就绪度判为「没有责任角色」。这是同一概念的两套实现，必须合并。

#### 断点 3：资源没有统一引用

表单、规则、标准文件、集成端点、技术使用、设备/量具分散在不同表，且各自用 `process_id` / `node_key` / 自由字段表达归属。没有一张表能回答「这个活动靠什么完成」。全仓检索 `activity_resource_link` 无匹配。

#### 断点 4：绑定不进入版本冻结

`ProcessModelVersion.snapshot` 只保存节点与连线（`app/services/process_model.py:84`–`:97`），包含 `process_arch_id`、`owner_position_id` 等节点字段；**不包含** RACI、表单、文档、资源链接。`NodeActivityLink` 有 `model_version_id`（`app/models/asset_graph.py:44`），RACI 与资源没有。升版后无法判断哪些绑定需要重新确认。

#### 断点 5：目标没有开源/节流类型

`StrategyObjective` 只有年度/期间/基线/目标值（`app/models/strategy.py:30`–`:58`），没有「增长 / 降本」类型。`KpiDefinition` 的四维度（效率/质量/成本/灵活性，`app/models/monitor.py:39`）不能替代目标类型。无法按两类目标看资源配置。

#### 断点 6：没有产物编译层

`ProcessDocument` 是流程级容器（`process_id` 非空，`app/models/process_document.py:38`）；岗位责任书与员工手册是跨流程/岗位级产物。现有 `CompiledAssetComponent` 只记录资产包引用了哪些对象（`app/models/process_document.py:166`），不能承载岗位级产物。全仓检索「岗位责任书 / 员工手册 / job_description」无匹配。

#### 断点 7：关键过程没有定义，岗位与治理角色没有显式映射

- 没有 `is_key_process` 之类的字段，流程覆盖度无法自动回答「覆盖了哪些关键过程」。
- `RaciAssignment.role_id` 指向 `GovernanceRole`，角色只有 `org_unit_id`（`app/models/raci.py:39`），没有 `position_id`；岗位负荷只能经成员反推。

## 6. 目标数据模型（只补连接，不建第二套主数据）

### 6.1 `RaciAssignment` 扩活动作用域

新增字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `activity_id` | FK `process_arch.id`，可空，`ON DELETE CASCADE` | 绑定到 L4 活动；与 `node_key` 至少一个非空 |
| `node_key` | `String(64)`，可空 | 画布锚点；用于定位到具体节点 |
| `scope_key` | `String(160)`，非空，索引 | 统一作用域键，替代 `matter` 作为唯一约束的一部分 |

`scope_key` 的生成规则：

```text
matter 行      → MATTER:<matter>
activity 行    → ACTIVITY:<activity_id>
node 行        → NODE:<node_key>
```

唯一约束从 `(process_id, matter, role_id)` 改为 `(process_id, scope_key, role_id)`。这样做的好处：

- PostgreSQL 下 `NULL` 在唯一约束中互不相等，直接加 `activity_id` 无法保证唯一；
- 历史数据回填 `scope_key = 'MATTER:' || matter`，行为不变；
- 同一作用域的「唯一 A」校验仍由服务层执行，并补数据库层可查的索引。

历史 `matter` 不自动猜映射。迁移只生成一份「待映射清单」，由业务在设计器或治理页人工挂到活动。

### 6.2 `activity_resource_link`：活动资源引用

不新建资源主数据，只建引用索引：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `activity_id` | FK `process_arch.id`，非空，`ON DELETE CASCADE` | 资源归属的 L4 活动 |
| `resource_type` | `String(16)`，索引 | `FORM` / `RULE` / `DOCUMENT` / `INTEGRATION` / `TECH` / `RPA` / `EQUIPMENT` / `MEASURE` |
| `ref_id` | `Integer`，可空 | 有实体表时的主键 |
| `ref_key` | `String(128)`，非空 | 统一引用键，如 `FORM:12`、`DOC:34`、`EQUIP:PUMP-01` |
| `org_scope` | `String(16)`，默认 `GLOBAL` | 组织范围；避免 `NULL` 唯一性问题 |
| `node_key` | `String(64)`，可空 | 确属节点特有的资源才填 |
| `note` / `is_active` / `created_by_id` / `created_at` | | 审计与停用 |

唯一约束：`(activity_id, ref_key, org_scope)`。

引用校验按类型执行：`ref_id` 非空时必须在对应表中存在；外部登记（设备/量具）只校验 `ref_key` 格式。与 `CompiledAssetComponent` 一样，只存引用与 hash，不复制正文。

### 6.3 绑定快照

在 `ProcessModelVersion` 增加 `binding_snapshot` JSON（可空）。发布/冻结时写入：

```json
{
  "captured_at": "2026-11-09T00:00:00+00:00",
  "model_version_id": 12,
  "activities": {
    "101": {
      "goal": {"kpi_ids": [3], "target": 95, "source": "DIRECT"},
      "team": [{"role_id": 2, "raci": "A", "source": "DIRECT"}],
      "resource": [{"ref_key": "FORM:12", "source": "DIRECT"}],
      "method": [{"ref_key": "DOC:34", "source": "INHERITED"}]
    }
  },
  "hashes": {"101": "sha256:..."}
}
```

就绪度服务比较「当前绑定」与「最近发布快照」：

- 一致 → `CONFIRMED`；
- 新增/变更 → `PENDING_CONFIRM`；
- 删除 → `STALE`。

草稿可编辑，正式产物不得引用未确认绑定。

### 6.4 关键过程

在 `ProcessArch` 增加：

- `is_key_process: bool`（默认 `false`）；
- `key_basis: String(200)`，可空；为 `true` 时服务层要求填写依据。

关键过程由业务勾选，主要落在 L3；L4 关键活动通过父级继承或单独勾选。不新建「关键过程名录」表，避免两套清单。

### 6.5 目标类型

在 `StrategyObjective` 增加：

- `goal_type: String(16)`，可空；值 `GROWTH`（开源/增长）或 `COST`（节流/降本）；
- 后端下发 `goal_type_label`，前端不维护中文映射。

未知类型不猜，保持空值。KPI 不复制类型，经 `ObjectiveProcessLink` 继承。

### 6.6 产物容器

岗位责任书、员工手册需要一个「可版本、可审批、可溯源」的容器。两个选项：

| 方案 | 做法 | 优点 | 风险 |
| --- | --- | --- | --- |
| A（推荐先验证） | 扩展现有 `ProcessDocument`：`process_id` 改为可空，增加 `scope`（`PROCESS`/`POSITION`/`ROLE`）、`position_id`、`governance_role_id`，加检查约束 | 复用版本状态机、变体、组件、存储、打印包 | 现有约 20 处 `document.process_id` 假定非空，需逐处加作用域守卫 |
| B | 新建 `OperatingDeliverable` 系列表 | 不影响现有流程文档 | 出现第二套版本状态机，违反「一个概念一个实现」 |

本文推荐 **A**，但 P3 先用**只读编译预览**验证产物形状，再落持久化；不要在 P3 一开始就改 `ProcessDocument` 的约束。

## 7. 绑定就绪度口径

### 7.1 四个面的判定

| 面 | READY | PARTIAL | MISSING |
| --- | --- | --- | --- |
| 定目标 `GOAL` | 活动有启用中的 KPI，且 `target_value`、`measurement`、`direction` 齐全 | 只有流程级 KPI，或 KPI 缺目标值/口径 | 无 KPI 且无承接目标 |
| 搭班子 `TEAM` | 有岗位（`owner_position_id`）且该活动/节点有唯一 RACI-A | 只有岗位、只有角色、或 RACI 只在流程级 | 两者都没有 |
| 配资源 `RESOURCE` | 有标准工时（`VERIFIED`）或有明确设计时长；有表单或记录载体；判断节点有规则 | 只有设计估计值，或只有流程级默认表单 | 无工时、无载体 |
| 开启智慧 `METHOD` | 有生效 SOP/标准文件（节点或流程级）；有控制点或证据要求 | 只有方法工具绑定，或只有流程级培训记录 | 无标准、无控制点、无证据 |

补充规则：

- **只在流程级有绑定** → `PARTIAL`，并在界面标「继承 / 未到活动」。
- **数据冲突**（同一活动多个 A、活动不属于该流程、角色无法归位到岗位）→ 单独状态 `CONFLICT`，不并入 `MISSING`。
- 设计估计值（`ProcessNode.duration_minutes`）与标准工时（`WorkMeasurementStandard`）必须分开展示，不能把估计值当已验证。

### 7.2 两个发布档位

| 档位 | 必需面 | 用途 |
| --- | --- | --- |
| 执行版 `EXECUTION` | 搭班子 + 配资源 | 上线执行、分派、表单、时限 |
| 绩效版 `PERFORMANCE` | 四个面 | 资产包、岗位责任书、员工手册、KPI 评价 |

流程覆盖度与岗位覆盖度是**诊断产物**，不阻断发布；它们只报告缺口。

### 7.3 门禁位置

沿用 §3.2：模型发布记录快照并提示；执行上线确认卡执行版；资产包/产物评审卡绩效版。门禁规则由服务计算，不落冗余字段；发布时冻结快照。

## 8. 边界与不做

1. **不为五类产物各建一套主数据**。产物是绑定的投影，不是新的源。
2. **不用 AI 自动生成 RACI 或责任书结论**。可以辅助草拟，但必须人工确认。
3. **不先做更多仪表盘**。先把 L4 活动、岗位、RACI、工时绑起来。
4. **不做完整 HR/ERP 集成**。先用手工主数据跑通一个 L3。
5. **不自动猜历史 `matter` 到活动的映射**。迁移只出清单，映射由人做。
6. **不在前端维护枚举中文**。`goal_type`、`resource_type`、就绪状态标签都由后端下发。
7. **不引入构建工具**。前端保持零构建、原生 ES 模块。
8. **不把节点当业务主键**。节点是画布实现，活动才是语义主键。
9. **不在产物页提供第二套录入**。缺口的唯一补录入口是设计器。
10. **不把流程级默认值当责任**。继承必须显式、可见、可追溯。

## 9. 需要拍板的决策

| # | 决策 | 本文建议 | 影响 |
| --- | --- | --- | --- |
| 1 | 「关键过程」由谁定、怎么定 | `ProcessArch.is_key_process` + 必填依据；业务勾选，不从名称推断 | 决定流程覆盖度能否自动生成 |
| 2 | RACI 是否直接绑岗位 | 保持治理角色为主，岗位经成员反推；角色无法归位时显式标 `CONFLICT` | 决定岗位覆盖度口径；不建议同时维护两套 |
| 3 | 产物容器 | 先用只读编译预览，再按方案 A 扩展 `ProcessDocument` | 决定 P3 是否触碰现有文档模型 |
| 4 | 绑定性门禁放在哪 | 模型发布只告警；执行上线卡执行版；资产包/产物评审卡绩效版 | 决定是否会把设计过程卡死 |
| 5 | 历史 `matter` 映射责任人 | 流程 Owner + 流程管理科，迁移后 30 天内完成；未映射的 RACI 不参与岗位负荷 | 决定岗位覆盖度何时可用 |

## 10. 术语

| 术语 | 含义 |
| --- | --- |
| L3 经营对象 | 承接目标、预算、Owner 与产物的流程节点 |
| L4 活动 | 绑定的唯一业务主键；稳定身份、可被工时/KPI/任务引用 |
| 绑定面 | 目标、班子、资源、方法四类绑定之一 |
| 绑定台 | 流程设计器；一次绑完，其他页面只读 |
| 就绪度 | 某个面在某个档位上是否具备可发布条件 |
| 版本冻结 | 发布时把绑定固化为快照，升版后需确认 |
| 编译 | 从绑定数据生成产物的确定性过程，不复制源数据 |
| 产物 | 员工手册、岗位责任书、流程覆盖度、岗位覆盖度、工作量 |

---

**下一步**：按 [process-binding-dev-plan.md](process-binding-dev-plan.md) 的 P0 先做只读就绪度；不改现有诊断与资产包行为。
