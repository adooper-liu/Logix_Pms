# “APQC＋十要素”治理体系与 Logix PMS 的能力差距分析

> 对照对象：《集团多组织“APQC＋十要素”流程治理体系设计与试点实施 SOP》
> 分析范围：本仓库当前代码（模型 / 服务 / 接口 / 前端 / 种子数据），基线日期 2026-10-24。
> 结论口径：**✅ 已落地 = 有数据模型 + 接口 + 界面，且能形成闭环；
> ◐ 部分实现 = 有基础模型或接口，但缺关键结构或闭环；
> ○ 缺失 = 没有对应实体、接口或界面。**
>
> 本文只做差距分析，不改代码，也不把附件里的建议设计当成 APQC / ISO 的强制要求。
> 与 [framework-gap-analysis.md](framework-gap-analysis.md) 的分工：那份文档按
> 「战略 → 组织 → 制度 → 流程 → 表单 → 工具」六层看；本文按附件的**十要素因果链**
> 与**九阶段 SOP** 看，并补充治理角色、授权、数据治理、成熟度与门禁。

---

## 一、结论摘要

1. **中段能力不弱，断点在两端。** 流程架构（L1–L4）、BPMN 建模与版本治理、
   标准文件/模板/交付物的版本与审批、执行引擎与工时记录都已落地；
   但**战略目标没有实体**、**治理角色与授权没有实体**、**成熟度与门禁证据没有实体**。
2. **附件最核心的“工作量”闭环只完成了一半。** 已经有统一活动 ID、岗位主数据、
   节点岗位绑定、任务实际工时（处理/等待/返工）和标准工时对比；
   但缺少**标准工时研究**（观测、评定、宽放、样本、适用条件、有效期）与**产能日历**，
   因此“观测 → 标准化 → 验证 → 应用”里的“标准化/验证”无法留证。
3. **KPI 目前是“指标台账”，不是附件要求的“指标定义卡”。** 定义了维度、方向、
   目标值、基线和所属流程，但缺公式/分子分母、粒度、频率、数据来源、质量规则、
   红黄绿阈值、责任人外键、版本与生效期，也缺“结果/过程/健康度”分类。
4. **不建议把附件照搬成第二套体系。** 系统已有五阶段 / 24 步工作流与步骤契约
   （输入、工具、验收、决策门）。正确做法是**在现有五阶段上补门禁证据与字段**，
   而不是再建一套九阶段项目引擎——否则违反“同一个概念只保留一个实现”。
5. **附件的治理建议适合作为“扩展模块”，不适合作为默认强制配置。** 角色清单、
   授权阈值、激励比例、成熟度评分规则都必须由集团批准；系统应提供载体和审计，
   不应内置一套未经验证的“最佳实践默认值”。

---

## 二、十要素能力矩阵

| 要素 | 现有能力（代码证据） | 状态 | 主要缺口 |
|---|---|---|---|
| 战略 | `ProcessArch` 的价值-痛点三维打分（`app/models/process.py:59`）、`Project.objective/metric_name/baseline_value/target_value`（`app/models/project.py:47`）、驾驶舱优先级 | ○ | 无战略目标/举措实体；无“目标→L1/L2→L3 KPI”的分解与追溯；无目标责任人、周期、来源文件 |
| 架构 | L1–L4 架构树（`process.py:34`）、PCF L1–L5 对标树与映射（`app/models/benchmark.py`）、PCF 生成架构草稿、节点→L4 活动外键（`process.py:147`） | ◐ | 企业架构只到 L4，无 L5 任务；无显式的集团扩展层命名空间；编码规范靠人工；无架构变更影响分析 |
| 组织 | 集团/公司/工厂/部门组织树（`app/models/org.py:22`）、岗位主数据（`org.py:56`）、用户组织/岗位（`app/models/user.py:42,47`）、流程组织归属（`process.py:51`）、节点岗位（`process.py:152`）、Owner 外键、节点分派（`app/models/execution.py:315`） | ◐ | 治理角色（委员会/集团所有者/单元所有者/流程管家/BPM 办公室/数据所有者）未建模；RACI 只是工具模板，不是结构化数据；组织/岗位无版本与生效期 |
| 制度 | 标准文件 SOP/FORM/CHECKLIST/TEMPLATE/POLICY/OTHER、版本与审批、生效/失效日期、组织范围与向上继承、变体策略与变体基版本（`app/models/process_document.py`） | ◐ | 无制度层级（集团章程/集团制度/单元细则/工厂 SOP）；无法人/工厂/产品族/语言版本字段；无授权矩阵、控制点、义务、罚则、例外规则 |
| 流程 | BPMN 2.0 设计器、泳道、节点类型、草稿→评审→发布→回滚、版本差异、校验/中文化、表单/规则、分派/SLA、实例快照（`app/models/process.py`、`app/models/execution.py`、`app/services/designer.py`） | ✅ | L5 缺失；并行/子流程/边界事件刻意不支持；无变更申请与跨资产影响分析；无跨 L3 价值流组合 |
| 表单 / 工具 / 工作量 | 节点表单与分支规则（`execution.py:233,261`）；33 个工具、步骤契约、工具等级、工具模板版本/审批/组织范围（`app/models/deliverable.py:36`、`app/models/tool_template.py:32`）；节点级工具绑定（`process.py:183`）；设计工时/等待/成本/返工；任务实际工时（`execution.py:379`）；任务详情标准 vs 实际（`execution.py:1027`） | ◐ | 表单/规则无版本与审批、无字段字典；工具无执行效果评估；**无标准工时研究、产能日历、活动×岗位×频次×FTE、标准 vs 实际聚合界面** |
| 绩效 | KPI 定义（效率/质量/成本/灵活性、方向、目标、基线、所属流程）与月度时序（`app/models/monitor.py:15`）、雷达/趋势、异常闭环、设计器测算（PCE/等待/返工/移交/审批/成本） | ◐ | 无结果/过程/健康度分类；无公式与分子分母；无粒度/频率/来源/质量规则；无红黄绿阈值；`owner` 是字符串而非外键；无版本/生效期；KPI 未绑定 L3/L4 活动 |
| 精益改善 | BPR/BPI/精益/混合项目、五阶段 24 步、方法论匹配、步骤契约与决策门、交付物版本、PDCA/DMAIC 工具、知识库、异常与改善建议 | ◐ | 项目缺“问题/基线/根因/对策/验证/收益/复制”结构化字段；无 DMAIC 阶段跟踪；无复制资产包与拒绝复制理由；无收益观察期与一次投入扣除 |
| 版本 / 变更 | 流程模型版本、标准文件版本、交付物版本、工具模板版本、基线快照、审计日志、治理发现（`process.py:231`、`process_document.py:95`、`baseline.py:18`、`governance.py:15`） | ◐ | 无变更申请实体与影响分析；流程模型用整数版本，文件/模板用 major.minor，语义不一致；无紧急变更、培训签收、回退触发条件 |
| 数据治理 | 审计留痕、实例快照冻结表单/规则/分派/模型、组织与岗位主数据、组织范围继承；`data_domain` 数据所有者/管家、`data_flow` 来源/主键/频率/质量规则/保留期/跨法人可见性 | ◐ | 已覆盖关键数据域与数据流登记；客户/供应商/物料等主数据的**实体级**治理与数据质量执行仍未建模 |
| 成熟度 / 门禁 / 路线 | 治理概览（资产有效性、落后变体、固定旧版交付物、基线覆盖率）、驾驶舱、项目进度、`StepContract.decision_gate`、`ProjectStep.is_milestone` | ○ | 无 0–5 级成熟度模型与证据化评分；无门禁签收/退出条件记录；无路线图与复制决策记录 |

---

## 三、逐项差距

### 3.1 战略层：因果链的起点没有落库

现有系统把“战略重要性”压缩成流程节点上的三个 1–5 分（`process.py:59-61`），
项目里只有 `objective` 与一个指标的目标值（`project.py:47-55`）。这能支持优先级排序，
但回答不了附件要求的四个问题：

- 这个流程承接的是哪一条年度经营目标？
- 目标的责任人是谁、目标值是多少、来源文件是什么？
- 删除/新增这条流程，会影响哪些目标与 KPI？
- 目标变化后，哪些 L3/L4 指标需要跟着改？

**差距**：没有 `StrategyObjective` / `Initiative` 实体，也没有
“目标—流程—指标映射卡”的载体。附件的 §11.2 模板目前只能作为文档附件存在。

### 3.2 架构：L1–L4 扎实，L5 与扩展层缺位

- 企业架构 `ProcessArch.level` 明确是 1..4（`process.py:34`），
  而 PCF 对标树本身有 L1–L5（`app/models/benchmark.py`）。两者不是同一套层级。
- 节点已经能指向 L4 活动（`process.py:147`），这是工作量与绩效汇总的关键前提。
- 缺 L5 任务目录，因此“任务级标准工时”没有稳定的主数据锚点。
- 附件建议的 `PCF4.0-G02-P03-A02-T01` 编码只是约定，系统里 `code` 是自由字符串
  （`process.py:32`），既没有格式校验，也没有“集团扩展层 vs APQC 原表”的显式标记。
- `ProcessArch` 有 `model_version`（`process.py:73`），但它服务于 L3 流程模型；
  架构本身的增删改没有独立版本与影响分析。

### 3.3 组织与治理角色：主数据有了，治理权责没有

> **2026-10-24 更新**：P1-1 已补齐治理角色、角色成员与结构化 RACI
> （`governance_role` / `raci_assignment`），并接入治理扫描。
> 仍未解决的是组织/岗位的生效期与历史归属。

已落地的部分：

- 组织树四类：集团/公司/工厂/部门（`app/models/org.py:22`、`enums.py:196`）；
- 岗位主数据，且被人员与流程节点引用时禁止删除（`app/services/position.py`）；
- 流程/项目/异常的 Owner 用 `owner_user_id` 外键判权，不比较姓名字符串
  （`process.py:41`、`project.py:35`、`app/models/user.py`）；
- 节点分派支持角色/组织/默认处理人/时限/升级（`execution.py:315`）。

缺的部分：

- 系统角色只有 `ADMIN / MANAGER / OWNER / VIEWER`（`enums.py:112`），
  无法表达附件中的集团治理委员会、集团端到端所有者、业务单元/工厂所有者、
  流程管理员/管家、BPM/卓越运营办公室、数据治理办公室、风险/法务/内控。
- **RACI 只是工具箱里的一个工具和知识库模板**（`app/seed/corpus.py:1191`），
  没有“事项 × 角色 × A/R/C/I”的结构化表，也没有“A 只能有一个”的约束。
- 组织与岗位没有生效期/版本，组织调整后历史归属不可追溯。

### 3.4 制度与授权：资产版本能力强，制度层级与授权矩阵缺失

现有标准文件能力相当完整：分类、版本、审批状态机、生效/失效日期、组织范围继承、
变体策略（LOCKED / PARAMETERIZED / EXTENDABLE / OPTIONAL / LOCAL_ONLY）、
变体基版本、治理扫描（落后变体、未生效、复审逾期、固定旧版交付物）。

与附件 §4 的差距：

- **没有制度层级字段**。附件要求一级集团章程（董事会）、二级集团制度（委员会）、
  三级单元细则（会签 + 单元负责人）、四级工厂 SOP（模板内维护）。
  现在只有 `category`（SOP/FORM/CHECKLIST/TEMPLATE/POLICY/OTHER，`enums.py:185`），
  层级与审批主体无法区分。
- **没有授权矩阵**。附件要求按风险/金额/影响/可逆性/频率五维，分 A 类集团批准、
  B 类备案后执行、C 类单元批准、D 类工厂标准执行，并覆盖采购、合同、资本开支、
  招聘、付款、价格、质量放行、变更、数据与 IT 权限。系统里没有任何授权/例外实体。
- **没有控制点与例外的结构化映射**。`POLICY` 文件可以上传，但无法回答
  “这条制度约束哪个流程节点、哪个控制点、例外由谁批、时限多久”。

### 3.5 流程：设计与执行强，变更治理弱

已落地：BPMN 画布、泳道、节点类型、草稿/评审/发布/回滚、版本差异、
`expected_version` 并发控制、BPMN 导入导出、校验与中文化、实例启动快照。

差距：

- 附件 §9 的“为什么变、变成什么、谁受影响、如何回退”没有独立载体。
  `ProcessModelVersion.change_note`（`process.py:254`）只是一个说明字段，
  不是变更申请；没有影响分析清单（人员/系统/数据/权限/控制/培训/指标历史）。
- **版本语义不一致**：流程模型用整数 `version`（`process.py:249`），
  标准文件与模板用 `major.minor`（`process_document.py:104`），
  附件建议统一用主/次/修订三段式。
- 附件明确把“并行网关、子流程、边界事件”排除在执行引擎外；
  系统已经主动隐藏这些构造（`designer/providers.js`），这与附件“只做串行流程”的
  边界一致，**属于已对齐而非缺口**。

### 3.6 表单、工具与工作量

> **2026-10-24 更新**：P0-2 已落地 `work_measurement_standard`、`capacity_calendar`
> 与任务活动归集；下面的“缺口”保留为设计依据，剩余的是 L5 任务级与外部数据接入。

**表单**：`FormDefinition` 按 `process_id + node_key` 定义，`node_key=""` 为流程默认表单；
运行时校验并随实例快照冻结。缺：版本/审批、字段字典、字段级权限、跨字段校验。

**工具**：33 个工具、五步标准操作、步骤契约（输入/工具/等级/验收/责任人/决策门）、
工具模板版本与组织范围、节点级绑定 `NodeTool`。缺：工具执行记录与效果评估
（`TemplateUsage` 只记录下载/使用，不记录改善效果）。

**工作量**——这是附件与系统差距最大的一块：

已有：

- 设计值：节点作业/等待/成本/返工/审批层级（`process.py:158-163`）；
- 统一活动 ID 与岗位：`ProcessNode.process_arch_id` / `owner_position_id`
  （`process.py:147,152`）、`User.position_id`（`user.py:47`）；
- 实际值：`TaskWorklog` 记录 HANDLE / WAIT / REWORK / OTHER
  （`execution.py:379`、`WORKLOG_TYPE_LABELS` 在 `execution.py:532`）；
- 对比：任务详情同时返回 `standard_minutes` 与 `actual_minutes`
  （`execution.py:1027`），其中标准值来自实例快照里的节点设计时长
  （`execution.py:188`）；
- 聚合：`workload_summary` 按人员汇总实际工时，可按日期/组织/流程过滤
  （`execution.py:608`），接口 `GET /execution/workload`（`app/api/v1/execution.py:781`）。

缺口：

1. **没有标准工时研究模型**：观测时间、评定系数、宽放类别与比率、有效样本、
   适用产品/批量/设备/技能/班次、审核人、版本与复审日期都没有字段。
   现有 `duration_minutes` 只是一个设计输入，无法证明“按最佳方法测得”。
2. **没有产能日历**：可用工时、出勤率、设备/工具可用率、计划停机无法维护。
3. **没有活动×岗位×频次×FTE 的标准工作量表**，因此无法做能力预测与负荷率。
4. **标准 vs 实际只在任务详情里对比**，没有按活动/岗位/组织/产品的聚合视图；
   `workload_summary` 只按人员汇总，且前端未使用该接口。
5. 没有“估算/已验证”状态，无法阻止未验证工时进入成本或绩效。

### 3.7 KPI：有台账，没有“定义卡”

> **2026-10-24 更新**：P0-1 已补齐定义卡（类型/公式/分子分母/粒度/频率/来源/质量规则/
> 红黄绿/责任人/版本/L4 活动）；治理规则也已补齐：KPI 数量超限扫描、
> 灰色未取数状态、红/黄改善候选自动扫描。剩余是 DMAIC 阶段跟踪与任务级等待原因码。

`KpiDefinition`（`monitor.py:15`）现有：编码、名称、维度（效率/质量/成本/灵活性）、
方向、单位、目标值、基线值、所属流程、`owner` 字符串、启停；`KpiRecord` 记录期间与值。

对照附件 §8 与 §11.2，缺：

- **结果/过程/健康度**三分法（现有维度是效率/质量/成本/灵活性，口径不同）；
- 公式、分子、分母、时间窗口、汇总粒度、频率；
- 数据来源系统与字段、质量规则、例外处理；
- 红/黄/绿阈值与“单项达标不得抵消其他红线”的约束；
- 责任人外键（现在只有字符串 `owner`）、目标版本与生效期；
- 与 L3/L4 活动、战略目标的绑定；
- 团队/个人激励的关联（**建议只做团队改善收益记录，不接个人薪酬**）。

### 3.8 改善与版本：流程能力有，改善证据链不完整

现有项目模型支持 BPR/BPI/LEAN/HYBRID、24 步、方法论推荐、步骤契约、交付物版本、
PDCA/DMAIC 工具、异常闭环、知识库、流程模型回滚。

缺：

- 改善项目卡的结构化字段：问题陈述、范围、基线、目标、根因、对策、试验证据、
  收益、观察期、一次投入、跨部门转移成本、复制评估；
- DMAIC 五阶段跟踪（现在是通用五阶段，不是 DMAIC 的 D/M/A/I/C）；
- 复制资产包（标准流程/例外/表单/培训/工时/数据字段/系统配置/收益证据/失败经验/
  适用条件）与“拒绝复制并说明理由”的记录；
- 改善后强制更新标准、培训、权限、系统与指标的门禁。

### 3.9 数据治理：只有审计，没有治理结构

> **2026-10-24 更新**：P1-3 已补齐最小集：`data_domain`（所有者/管家）、
> `data_flow`（来源系统/主键/频率/质量规则/保留期/跨法人可见性），
> 并接入治理扫描（无所有者、登记不完整）。仍未做的是客户/供应商/物料等
> **实体级主数据**与数据质量规则的自动执行。

已有审计日志与实例快照，能回答“谁改了什么、当时用的哪版表单/规则/分派”，
这是很好的基础。但附件 §4 要求的：

- 数据所有者 / 数据管家 / IT 系统负责人 / 流程所有者的四类责任；
- 数据流登记（来源系统、提取频率、主键、字段定义、允许值、质量规则、用途、
  保留期、跨法人可见范围、数据主体权利）；
- 客户/供应商/物料/资产/项目等主数据的统一治理；

在现有 48 张表中都没有对应实体（可用
`grep -rh "__tablename__" app/models/*.py` 复核）。

### 3.10 成熟度、门禁与路线图

- 治理发现 `GovernanceFinding` 能跟踪“落后变体 / 未生效 / 复审逾期 / 固定旧版交付物”，
  但扫描范围不含“L4 是否有节点/Owner/制度/表单/工具”“KPI 是否挂流程”
  （`app/services/governance.py:74-244`）。
- 基线 `AssetBaseline` 只快照标准文件与工具模板，不含流程模型、KPI、表单、规则、岗位
  （`app/services/baseline.py:69-166`）。
- `StepContract.decision_gate` 只是布尔配置，`ProjectStep.is_milestone` 只是甘特图标记；
  没有门禁签收、退出条件、证据附件与“未通过只能修补/缩窄/停止”的状态机。
- 没有 0–5 级成熟度模型、评分证据、路线图与复制决策记录。

### 3.11 九阶段 SOP 与现有五阶段的关系

附件 §5 的九阶段与系统现有五阶段不是一一对应关系：

| 附件阶段 | 系统现有能力 | 结论 |
|---|---|---|
| 0 立项定界 | 项目创建、Owner、目标/范围/预算；无章程实体 | ◐ 补章程字段即可 |
| 1 战略与现状基线 | 五阶段第 1 阶段、KPI 基线、流程走查工具 | ◐ 缺战略目标实体 |
| 2 流程架构设计 | L1–L4、PCF 裁剪、架构草稿 | ✅ |
| 3 制度与授权设计 | 标准文件、RACI 工具；无授权矩阵 | ◐ |
| 4 流程/表单/工具设计 | BPMN、表单、规则、工具绑定、交付物 | ✅ |
| 5 工作量测量 | 设计工时 + 实际工时；无标准工时研究 | ◐ |
| 6 试运行与绩效监测 | 执行引擎、KPI、异常、看板 | ✅ |
| 7 评审与固化 | 流程/文件/模板审批发布、培训矩阵工具 | ◐ 缺门禁签收 |
| 8 改善与复制 | 改善项目、知识库、版本回滚；无复制资产包 | ◐ |

**建议**：不要新建九阶段引擎。把附件阶段 0/3/5/7/8 的缺失字段补进现有
`Project` / `ProjectStep` / `StepContract`，用 `decision_gate` + 签收记录表达门禁；
阶段映射表放在文档/前端说明里即可。

---

## 四、结构性缺口（根因）

1. **战略层无实体**：因果链最上游靠人工与文本，导致目标—流程—指标无法追溯。
2. **治理权责未建模**：系统角色是“系统权限”，不是“治理角色”；
   RACI 没有结构化载体，“单点负责”无法校验。
3. **授权与制度层级缺失**：没有 A/B/C/D 授权、阈值、例外、时限，
   制度只能作为文件存在，不能作为控制规则被执行或审计。
4. **标准工时只有结果没有方法**：工时是设计输入或实际记录，
   不是“观测—评定—宽放—验证”的可复核资产；产能与预测因此无法计算。
5. **KPI 定义不足以防“同名异义”**：缺公式、粒度、来源、质量规则与版本。
6. **变更与影响分析缺失**：版本能回滚，但不能回答“谁受影响、如何验证、如何回退”。
7. **数据治理曾缺位**：已补数据所有者/管家、数据流与质量规则最小集；
   实体级主数据与质量规则执行仍未做。
8. **成熟度与门禁缺证据**：有发现清单与里程碑，没有评分、签收与退出条件。
9. **L5 缺失**：任务级标准工时没有主数据锚点。
10. **跨层追溯只有两两外键**：没有统一的依赖/影响查询；
    基线也只覆盖文件和模板。

---

## 五、实施优先级

> 原则：**先补闭环、后扩范围；能扩展现有实体就不新建平行体系；
> 每个优先级都必须能独立提交、独立验证。**

### P0：补齐因果链的关键断点

| # | 交付物 | 具体改动 | 验收标准 | 依赖 |
|---|---|---|---|---|
| P0-1 ✅ | KPI 定义卡 | `kpi_definition` 增加：`kind`（RESULT/PROCESS/HEALTH）、`formula`、`numerator`、`denominator`、`granularity`、`frequency`、`source_system`、`quality_rule`、`red/yellow/green`、`owner_user_id`、`version`、`valid_from/to`、`activity_id`；API/前端补维护与校验 | 同名 KPI 不能有两种公式；看板能按结果/过程/健康度筛选；审计能回答指标口径何时变过 | 无 |
| P0-2 ✅ | 标准工时与产能 | 新增 `work_measurement_standard`（活动×岗位×方法×设备×产品族×标准工时×频次×FTE×宽放×样本×状态×有效期）与 `capacity_calendar`（组织×岗位×期间×可用工时）；复用 `ProcessNode.process_arch_id` / `owner_position_id` / `User.position_id` | 能按活动/岗位/组织输出“标准 vs 实际”；未验证工时不进入成本/绩效；负荷率可算 | 现有活动+岗位绑定 |
| P0-3 ✅ | 战略目标与映射 | 新增 `strategy_objective`（目标、年度目标值、责任人、来源、周期）与 `objective_process_link`（目标→L1/L2/L3→KPI）；前端新增「战略目标」视图，支持按流程/KPI 反查 | 任意 L3 可反查承接的战略目标；删除目标/流程时提示受影响对象 | P0-1 的 KPI 外键 |
| P0-4 ✅ | 变更申请与影响分析 | 新增 `process_change_request`：原因、范围、影响清单（人员/系统/数据/权限/控制/培训/指标）、测试证据、回退方案、生效日；与 `process_model_version.change_request_id` 关联；文件/模板版本沿用既有审批链（后续再挂变更单） | 每次流程模型发布都能追溯到变更单；重大变更缺影响分析不能提交；启用门禁的流程缺已批准变更单不能发布 | 现有版本体系 |

### P1：治理结构与证据

| # | 交付物 | 具体改动 | 验收标准 |
|---|---|---|---|
| P1-1 ✅ | 治理角色与 RACI | 新增 `governance_role` / `governance_role_member`（委员会/集团所有者/单元所有者/流程管家/BPM 办公室/数据所有者/风险法务）与 `raci_assignment`（事项 × 角色 × A/R/C/I）；同一事项唯一 A；治理扫描新增 `RACI_INVALID` | 每个 L3/L4 关键事项能查到唯一 A；RACI 冲突能被治理扫描发现 |
| P1-2 ✅ | 制度层级与授权矩阵 | `process_document` 增加制度层级、适用法人/工厂/产品族/语言、控制点与例外；授权矩阵复用既有 A/B/C/D 规则 + 例外台账 | 制度能按层级筛选；例外必须有时限/审批人/复盘；越权写入被拒绝 |
| P1-3 ✅ | 数据治理最小集 | 新增 `data_domain`（类型/所有者/管家）与 `data_flow`（来源系统、主键、频率、字段定义、允许值、质量规则、保留期、跨法人可见性、数据主体权利）；与流程/KPI 关联；治理扫描新增 `DATA_DOMAIN_NO_OWNER` / `DATA_FLOW_INCOMPLETE` | 每个关键数据流有责任人与质量规则；缺口能被治理扫描发现 |
| P1-4 ✅ | 成熟度与门禁证据 | 新增 `maturity_assessment`（0–5 级、证据链接、评审人、周期）与 `gate_attestation`（门禁、退出条件、证据、签收人、结论：通过/修补/缩窄/停止）；扩展治理扫描到“L4 节点/Owner/制度/表单/工具/KPI 覆盖率” | 成熟度评分必须有证据链接；门禁未通过不能进入下一阶段；治理概览能显示跨层覆盖率 |
| P1-5 ✅ | L5 任务目录 | 独立 `process_task_definition`（L4 活动 × 任务 × 岗位 × 标准工时 × 频次），标准工时卡可绑定 `task_id` | 标准工时能挂到 L5；L4 汇总能下钻到 L5 |

### P2：改善与复制

| # | 交付物 | 具体改动 |
|---|---|---|
| P2-1 ◐ | 改善项目卡与 DMAIC | ✅ 已扩展 `Project`：来源与来源 KPI、问题陈述、根因、对策、验证、收益、观察期、一次投入、转移成本、复制状态；✅ 红/黄 KPI 一键生成草稿并去重；◐ DMAIC 阶段跟踪与自动扫描未做 |
| P2-2 | 复制资产包 | 新增 `replication_pack`（适用条件、资产清单、收益证据、失败经验、拒绝理由），与知识库/标准文件/工具模板关联 |
| P2-3 | 工作量与产能看板 | 前端新增标准 vs 实际、负荷率、瓶颈、按活动/岗位/组织聚合；复用 `GET /execution/workload` 并扩展维度 |
| P2-4 | 外部数据接入 | ERP/MES/WMS/HR/OA 的订单、工单、考勤、工位事件接入，替代抽样观测；沿用现有 Outbox/Webhook 集成层 |

---

## 六、明确不建议做的事

- **不新建九阶段项目引擎。** 现有五阶段 / 24 步已经承载了大部分阶段；
  再建一套会出现两套进度、两套门禁、两套权限。
- **不把十要素做成十个独立模块。** 它们是一条因果链；按要素建模块会制造重复主数据。
- **不做个人薪酬/扣罚联动。** 标准工时可用于排程、成本、能力预测与团队改善激励；
  直接接个人扣罚会诱发瞒报异常，附件也明确反对。
- **不把附件里的阈值、比例、角色清单写成系统默认值。** 这些必须由集团批准；
  系统只提供字段、校验与审计。
- **不把 PCF L5 直接当成企业 L5。** PCF 是参考分类，企业 L5 必须由现场方法与
  标准工时研究产生。
- **不声称符合 APQC / ISO。** 系统借鉴其方法论与分类思路，不构成认证或强制合规。
- **不重复建模工作量。** 已有 `ProcessNode.process_arch_id` + `Position` + `TaskWorklog`；
  新能力应扩展这三者，而不是再造一套“活动/岗位/工时”概念。

---

## 七、证据索引

| 主题 | 代码位置 |
|---|---|
| 流程架构 L1–L4、Owner、组织、战略打分、模型版本 | `app/models/process.py:26-115,231-298` |
| 设计器节点、活动 ID、岗位、工时/返工/审批 | `app/models/process.py:127-180` |
| 组织树与岗位 | `app/models/org.py:22-85` |
| 用户角色、组织/岗位、审计 | `app/models/user.py:22-99`、`app/models/enums.py:112-118` |
| 标准文件与版本/变体/生效期 | `app/models/process_document.py:31-145` |
| 表单、规则、分派、实例、任务、工时 | `app/models/execution.py:33-410` |
| KPI 与异常 | `app/models/monitor.py:15-105`、`app/models/enums.py:79-89` |
| 改善项目与 24 步 | `app/models/project.py:15-130` |
| 步骤契约与决策门 | `app/models/deliverable.py:36-81` |
| 工具模板与版本 | `app/models/tool_template.py:32-140` |
| 基线、治理发现 | `app/models/baseline.py:18-41`、`app/models/governance.py:15-39` |
| 设计器测算（PCE/等待/返工/移交/审批/成本） | `app/services/designer.py:273-410` |
| 工时记录与汇总 | `app/services/execution.py:532-660,1010-1035`、`app/api/v1/execution.py:740-795` |
| 治理扫描范围 | `app/services/governance.py:74-244` |
| 基线快照范围 | `app/services/baseline.py:69-166` |
| 岗位引用保护 | `app/services/position.py` |

复核“缺什么”的命令：

```bash
# 全部表名（48 张）；没有 strategy / raci / authorization / maturity / data_flow 等表
grep -rh "__tablename__" app/models/*.py

# 现有 KPI 字段
sed -n '15,45p' app/models/monitor.py

# 现有工时字段与汇总维度
sed -n '379,410p' app/models/execution.py
sed -n '608,660p' app/services/execution.py
```

---

## 八、按“管理闭环”的最终评价标准

> 评价口径：战略 → 工作 → 标准 → 执行 → 状态 → 异常 → 改善 → 绩效；
> 以及“工作单元六句话”“四类可视信号”“工作量三层”“每岗 3–5 个指标”。

| 评价项 | 标准 | 系统现状（P0-1 后） | 判定 |
|---|---|---|---|
| 工作单元六句话 | 谁做 / 什么触发 / 做什么 / 做到什么标准 / 什么时间交 / 留下什么证据 | KPI 定义卡已覆盖：`owner_user_id`、`frequency`、`formula` 与分子分母、红黄绿 + 目标、`frequency` + `valid_from/to`、`source_system` + `quality_rule`；流程节点/任务只覆盖部分 | ✅ KPI / ◐ 其他 |
| 战略承接可反查 | 目标 → L1/L2/L3 → KPI，能按流程或 KPI 反查 | `strategy_objective` + `objective_process_link`；流程按祖先继承，KPI 按所属流程反查；前端「战略目标」视图可维护 | ✅ |
| 四类可视信号 | 计划 / 进度 / 质量 / 改善；绿黄红灰 | 项目步骤 = 计划，任务状态 = 进度，KPI 红/黄/绿 = 质量、灰（未取数）= 等待上游，异常台账与改善候选 = 改善 | ✅ 4/4 |
| 工作量三层 | 工作清单 / 标准工时 / 实际工时 | 流程架构与活动 = 工作清单；`work_measurement_standard` = 观测/评定/宽放/样本/验证状态；`TaskWorklog` = 实际工时并按任务冻结的 L4 活动归集 | ✅ 3/3（L4；L5 任务级仍缺） |
| 每岗 3–5 个指标 | 结果为主、状态为辅、红线一票否决 | 定义卡支持结果/过程/健康度与红线；治理扫描对“流程 > 5 个”与“责任人 > 5 个”生成 `KPI_OVER_CAP` 待办 | ✅ |
| 改善单一链条 | 异常 → 根因 → 对策 → 验证 → 改标准 | 异常闭环、改善项目卡（问题/根因/对策/验证/收益/复制）、版本发布、知识库已存在；改善候选自动扫描红/黄且无进行中项目的 KPI，一键生成草稿 | ✅（候选自动扫描；建单需确认） |
| 变更与影响分析 | 为什么变、变成什么、谁受影响、如何回退 | `process_change_request` 覆盖 7 类影响、测试证据与回退方案；重大变更未填全不能提交；启用门禁的流程必须带已批准变更单发布 | ✅ |
| 角色与 RACI | 每项关键事项有唯一 A，R 可多个 | `governance_role` 覆盖委员会/集团与单元所有者/流程管家/BPM 办公室/数据所有者/风险法务；`raci_assignment` 按事项维护 A/R/C/I；治理扫描拦截缺少/重复 A | ✅ |
| 数据治理最小集 | 数据域有所有者，数据流有来源/主键/质量规则 | `data_domain` + `data_flow` 覆盖关键数据域与数据流；治理扫描标记无所有者与登记不完整；实体级主数据与质量规则执行仍未做 | ◐ |
| 管工作异常 | 先问任务/标准/材料/授权/系统/流程，再问人 | 任务队列、异常台账、KPI 红/黄/灰状态已能暴露工作异常；任务级“等待/缺料/缺授权”原因码仍缺 | ◐ |
| 一张流程卡 | 编号/对象/Owner/输入输出/步骤/异常/指标/红线/改善 | 架构、Owner、标准文件、KPI、工具分散在多个模块，没有一个聚合的“流程卡”视图 | ◐ |
| 周五闭环 | 周一计划、周三异常、周五结果 | 系统提供数据与台账，但不承载会议节奏；属于管理例行，不建议做成硬流程 | ○（不建） |

**最终结论**：P0-1 让 KPI 从“指标台账”变成了可审计的“定义卡”，
P0-2 补齐了“标准工时—实际工时—产能负荷”的闭环，P0-3 补上了
“战略目标 → 流程 → KPI”的追溯起点，P0-4 把变更影响分析与发布门禁接上，
P2-1 又把“红/黄 KPI → 改善项目卡 → 验证/收益/复制”接了起来。
管理闭环里的“战略”“标准”“证据”“状态”“变更”“改善”“权责”“数据”八环已经有了数据载体。
仍缺的是：成熟度评估、DMAIC 阶段跟踪、文件/模板版本的变更单关联、
L5 任务级标准工时、任务级等待/缺料原因码、实体级主数据与质量规则执行，
以及聚合的“一张流程卡”视图。
它们应作为后续的治理规则与主数据扩展，而不是继续给现有表加字段。

**P0-1 落地证据**（2026-10-24）：

- `kpi_definition` 新字段与迁移 `c65dd55aaff2`；
- `GET /monitor/meta`、`GET/PATCH /monitor/kpis/{id}`、按类型/频率/活动过滤；
- 前端 KPI 明细的类型筛选、红黄绿状态、`by_kind` 汇总、新建/编辑定义卡；
- `tests/test_kpi_definition.py`（9 个用例）+ `test_migrations.py`；
- `python scripts/check.py` → 328 passed；`scripts/verify_frontend.py` → 全绿。

**P0-2 落地证据**（2026-10-24）：

- `work_measurement_standard` / `capacity_calendar` 与 `process_task.activity_id`，
  迁移 `df082b8d9358`；
- `GET /workload/meta|standards|capacity|summary`、`POST/PATCH /workload/standards`、
  验证/停用、`POST/PATCH /workload/capacity`；
- 前端「运营监控 → 工作量」页：标准需求、可用产能、实际工时、理论负荷率，
  标准工时卡与产能维护弹窗；
- `tests/test_workload.py`（7 个用例，含实际工时归集与验证门禁）；
- `python scripts/check.py` → 335 passed；`scripts/verify_frontend.py` → 全绿。

**P0-3 落地证据**（2026-10-24）：

- `strategy_objective` / `objective_process_link`，迁移 `d9a46136b3fe`；
- `GET /strategy/meta|summary|objectives|processes/{id}/objectives|kpis/{id}/objectives`、
  `POST/PATCH/DELETE /strategy/objectives`、承接关系新增/移除；
- 前端新增「战略目标」视图（第 14 个视图）；
- `tests/test_strategy.py`（5 个用例，含祖先继承、KPI 反查、承接错位拦截）；
- `python scripts/check.py` → 340 passed；`scripts/verify_frontend.py` → 全绿。

**P0-4 落地证据**（2026-10-24）：

- `process_change_request`、`process_arch.requires_change_request`、
  `process_model_version.change_request_id`，迁移 `dd95d8cd60f7`；
- `GET /changes/meta|changes`、`POST/PATCH /changes`、提交/批准/驳回/取消，
  发布接口支持 `change_request_id` 门禁；
- 设计器新增「变更」页签；启用门禁的流程发布前会自动要求已批准变更单；
- `tests/test_changes.py`（6 个用例，含影响分析门禁、发布门禁、驳回/取消、权限）；
- `python scripts/check.py` → 346 passed；`scripts/verify_frontend.py` → 全绿。

**P2-1 改善项目卡落地证据**（2026-10-24）：

- `project` 新增来源/来源 KPI、问题/根因/对策/验证/收益、观察期、一次性投入、
  转移成本、复制状态与说明，迁移 `98e8e5c8d921`；
- `POST /monitor/kpis/{id}/improvement-draft`：红/黄 KPI 一键生成 24 步改善项目，
  预填基线/目标/问题描述，同一 KPI 不允许并行多张；
- `GET /projects/meta`、项目概览「改善项目卡」、编辑弹窗补齐字段；
- `tests/test_improvement.py`（5 个用例，含去重、闭环后重开、绿色/无数据/无目标拦截）；
- `python scripts/check.py` → 351 passed；`scripts/verify_frontend.py` → 全绿。

**治理规则落地证据**（2026-10-24）：

- `kpi_service.status_for` 对“无数据/阈值不全”返回 `GRAY`（未取数），雷达 `by_kind` 同步灰档；
- 治理扫描新增 `KPI_OVER_CAP`：流程或责任人的活跃 KPI 超过 5 个时生成 MEDIUM 待办；
- `GET /monitor/improvement-candidates` 自动扫描红/黄且无进行中改善项目的 KPI；
- 前端 KPI 明细新增「改善候选」卡，保留一键「转改善」；
- `tests/test_governance.py`（KPI 上限）与 `tests/test_improvement.py`（候选/排除）；
- `python scripts/check.py` → 353 passed；`scripts/verify_frontend.py` → 全绿。

**P1-1 治理角色与 RACI 落地证据**（2026-10-24）：

- `governance_role` / `governance_role_member` / `raci_assignment`，迁移 `059920fb9d9f`；
- `GET/POST/PATCH/DELETE /governance/roles`、成员增删；
- `GET/POST/DELETE /governance/raci`：按流程分组、唯一 A 校验、完整性错误；
- 治理扫描新增 `RACI_INVALID`，缺少 A 时生成待办，补齐后自动关闭；
- 前端「组织与人员 → 治理角色」与设计器「权责」页签；
- `tests/test_raci.py`（5 个用例，含唯一 A、成员、删除保护、扫描联动）；
- `python scripts/check.py` → 358 passed；`scripts/verify_frontend.py` → 全绿。

**P1-2 制度层级与例外复盘落地证据**（2026-10-25）：

- `process_document` 增加 `level`（集团/公司/工厂/产线/流程）、`legal_entity`、`plant`、
  `product_family`、`language`、`control_points`、`exception_terms`，迁移 `a4b5c6d7e8f9`；
- 标准文件清单支持 `level/legal_entity/plant/product_family/language` 筛选；
- 授权矩阵继续复用既有 A/B/C/D 规则；例外增加 `review_due_at` / `reviewed_at` /
  `reviewed_by_user_id` / `review_note`；
- 批准例外必须设置失效时间；到期未复盘的例外由治理扫描生成
  `AUTHORIZATION_EXCEPTION_DUE_REVIEW`；
- 前端标准文件新建/详情展示层级与适用范围；例外台账支持「复盘」；
- `tests/test_document_hierarchy.py`、`tests/test_authorization.py`。

**P1-4 成熟度与门禁证据落地证据**（2026-10-25）：

- `maturity_assessment`（维度 × 0–5 级 × 证据链接 × 评审人 × 有效期）与
  `gate_attestation`（阶段 × 退出条件 × 证据 × 结论 × 签收人），迁移 `b5c6d7e8f9a0`；
- `/maturity/assessments`、`/maturity/gates`、`/maturity/coverage`；
- 项目启用 `gate_required` 后，阶段推进必须存在该阶段 PASS 签收，否则 400；
- 治理扫描新增 `L4_NO_OWNER` / `L4_NO_DOCUMENT` / `L4_NO_KPI`；
- 流程卡展示成熟度评估与 L4 覆盖率；项目详情支持门禁签收；
- `tests/test_maturity.py`。

**P1-5 L5 任务目录落地证据**（2026-10-25）：

- 新增 `process_task_definition`（L4 × 任务 × 岗位 × 标准工时 × 频次），迁移 `c6d7e8f9a0b1`；
- `work_measurement_standard.task_id` 可绑定 L5 任务；绑定任务必须属于所选 L4 活动；
- `/process-tasks` 支持清单、创建、修改、停用；`/process-tasks/rollup` 按 L4 汇总任务与工时；
- 流程卡展示 L5 任务并支持在 L4 下新增；标准工时弹窗可选择 L5 任务；
- `tests/test_process_tasks.py`。

**P1-3 数据治理最小集落地证据**（2026-10-24）：

- `data_domain` / `data_flow`，迁移 `4d2fcd650024`；
- `GET/POST/PATCH/DELETE /data-governance/domains` 与 `/flows`，`GET /meta|summary`；
- 治理扫描新增 `DATA_DOMAIN_NO_OWNER`（HIGH）与 `DATA_FLOW_INCOMPLETE`（MEDIUM），
  补齐后自动关闭；
- 前端新增「数据治理」视图（第 15 个视图）：缺口概览、数据域/数据流维护；
- `tests/test_data_governance.py`（5 个用例，含所有者必填、扫描联动、删除保护、引用校验）；
- `python scripts/check.py` → 363 passed；`scripts/verify_frontend.py` → 全绿。
