# 流程管理框架缺口分析：战略 → 组织 → 制度 → 流程 → 表单 → 工具

> 范围：Logix PMS 当前代码库（模型、接口、前端）。
> 结论：**模块覆盖不差，差的是跨层主数据、统一活动 ID、活动级绑定，以及战略到执行、
> 工作量与绩效考核的闭环。**
> 本文只做差距分析，不代替实施计划；优先级见最后一节。

## 1. 目标链路

```text
战略目标
  → KPI / 年度目标
  → 流程架构（L1–L4）
  → 活动（统一活动 ID）
  → 组织 / 岗位 / RACI
  → 制度 / 控制点
  → 表单 / 规则
  → 工具 / 模板
  → 执行任务 / 交付物
  → 工作量实绩
  → 绩效考核
  → 改进项目 / 激励
```

这条链路要求每一层既能独立维护，又能被上一/下一层稳定引用。当前项目的问题是：
**每一层大多有模块，但层与层之间靠名称、字符串和可选外键连接。**

## 2. 六层现状与缺口

| 层级 | 已有能力 | 主要缺口 |
| --- | --- | --- |
| 战略地图 | 流程架构 L1–L4、战略重要性/痛点/改善空间、SCOR/APQC 对标、KPI、驾驶舱 | 没有战略目标/主题/举措实体；没有“战略目标→KPI→流程”的分解与追溯；战略重要性是人工评分 |
| 组织架构 | 组织树、用户归属组织、流程 Owner、节点分派组织、制度/模板组织范围 | `ProcessArch.department`、`ProcessNode.lane`、`owner_role` 是自由字符串；流程/节点没有 `org_unit_id`；没有岗位/职位主数据与 RACI |
| 制度 | 标准文件（SOP/表单/清单/模板/制度/其他）、组织继承与变体、版本/审批/生效日期、基线治理 | 制度只挂流程，不挂活动/步骤；`POLICY` 没有控制点、义务、罚则；没有制度→控制点→执行证据的映射 |
| 流程 | L1–L4 架构、bpmn-js 建模、版本治理、执行引擎、表单/规则、分派/SLA、项目与方法论 | **L4 活动目录与 BPMN 节点没有外键**；执行引擎不支持并行/子流程/边界事件；执行数据不回写 KPI |
| 表单 | 按流程+节点定义 JSON 表单、运行时校验、规则、实例快照 | 表单/规则无版本与审批；设计器不暴露绑定；无字段字典、跨字段校验、字段级权限 |
| 工具 | 33 个工具、5 步标准操作、工具模板（版本/审批/占位符/组织范围）、问题匹配 | 工具只挂五阶段工作流步骤，不挂具体流程活动；无工具执行与效果评估 |

## 3. 结构性缺口

### 3.1 L4 活动目录与 BPMN 节点是两套模型

- L4 活动：`ProcessArch` 的 `L4-201 … L4-205`；
- 设计器节点：`ProcessNode` 的 `n1 … n6`；
- `ProcessNode` 没有指向 `ProcessArch` 的字段（`app/models/process.py:96`）。

现状已经不一致：L3-032 的 L4 目录有 5 个活动，设计模型有 6 个节点，
`n6 计划回退与修改`在 L4 目录里没有对应项。  
后果：L4 的 Owner、指标、改善目标无法可靠汇总到 BPMN；执行数据也无法回到 L4。

### 3.2 组织与岗位仍是字符串

- `ProcessArch.department`、`ProcessArch.owner`、`ProcessNode.lane`、`owner_role`
  都是字符串；
- `owner_user_id` 只解决权限，不表达组织归属；
- `NodeAssignment.org_unit_id` 是运行时配置，不是设计模型。

后果：组织/岗位调整后，流程地图、泳道、责任人会漂移；无法按组织稳定汇总流程、
制度、表单、工具、工作量和绩效。

### 3.3 制度、表单、工具没有活动级绑定

- 制度：`ProcessDocument.process_id`，没有 `node_key`（`app/models/process_document.py:31`）；
- 表单：`FormDefinition.process_id + node_key` 已有活动级能力，但设计器不暴露
  （`app/models/execution.py:223`）；
- 工具：`StepContract.step_no` 是五阶段标准工作流步骤，不是流程活动
  （`app/models/deliverable.py:36`）。

后果：一个具体活动无法在一个地方看到“依据哪条制度、用哪个表单、配哪个工具、
产出哪个交付物”。

### 3.4 缺少跨层追溯与影响分析

应有：改一条制度/表单/工具/组织 → 哪些流程、活动、在跑实例受影响。  
现在只有两两关联，没有追溯图、影响分析或跨层治理待办。

### 3.5 主数据版本与生效日期不一致

- 有版本：流程、制度版本、模板版本、交付物版本；
- 无版本/生效日期：组织、岗位、表单、规则、KPI、节点分派。

运行实例已冻结 forms/rules/assignments 快照（`app/services/execution.py:196`），
这是优点；但设计侧无法回答“2026-Q3 的表单/岗位/规则版本是什么”。

### 3.6 缺少跨层一致性审计

基线/治理扫描覆盖制度、模板、交付物（`app/models/baseline.py`、`app/services/governance.py`），
未审计：
- 每个 L4 是否都有 BPMN 节点、Owner、制度、表单、工具；
- 每条制度是否有对应流程版本；
- 每个 KPI 是否挂到流程；
- 每个岗位是否有工作量标准与绩效目标。

## 4. 工作量（新增维度）

### 4.1 当前有什么

- `ProcessNode.duration_minutes` / `wait_minutes`：设计时的作业/等待时间；
- `ProcessTask`：`created_at / claimed_at / due_at / completed_at`、处理人、状态；
- `NodeAssignment`：角色/组织/默认处理人/时限/升级；
- `Project`：预算、实际成本、ROI；
- `ProcessTaskEvent`：任务生命周期事件。

### 4.2 缺什么

1. **标准工作量**：活动 × 岗位 × 标准工时 × 频次 × FTE × 有效期；
2. **实际投入**：任务级 worklog/effort（处理/等待/返工），目前只有时间戳；
3. **产能**：工作日历、岗位可用工时、并发任务上限；
4. **聚合口径**：按活动/流程/组织/岗位汇总标准 vs 实际、利用率、负载均衡；
5. **预测与排班**：根据频次和标准工时预测工作量，支撑派工与人员配置；
6. **与项目成本联动**：人力投入 → 项目人天/成本 → ROI。

### 4.3 建议数据模型

- `position`（岗位/职级）+ `user.position_id`；
- `activity_workload_standard`：`activity_id, position_id, standard_minutes, frequency,
  fte, valid_from, valid_to, source`；
- `task_worklog`：`task_id, user_id, started_at, ended_at, effort_minutes, work_type`；
- `capacity_calendar`：`org_unit_id, position_id, period, available_hours`；
- 看板：标准工时 vs 实际工时、利用率、超载/空闲、部门/岗位分布（聚合展示）。

## 5. 绩效考核（新增维度）

### 5.1 当前有什么

- `KpiDefinition` / `KpiRecord`：流程/项目级指标与时序；
- `Project`：基线/目标/当前值/改善幅度/ROI；
- 任务超期、升级、异常、返工率等执行数据；
- 审计日志、通知。

### 5.2 缺什么

1. **考核对象**：人员/岗位/团队维度的目标与结果；
2. **考核周期**：月/季/年，状态机（草稿→自评→上级评→校准→确认→归档）；
3. **指标来源与权重**：流程 KPI、项目结果、任务及时率/质量、工作量、协作；
4. **评分与校准**：公式、等级、分布、评语、申诉、确认；
5. **与工作量/能力联动**：负载、岗位职责、技能矩阵；
6. **审计与隐私**：个人明细仅本人/直属上级可见，聚合口径对外。

### 5.3 建议数据模型

- `performance_cycle`：周期、状态、适用范围；
- `performance_objective`：考核对象 × 活动/KPI × 权重 × 目标值 × 数据来源；
- `performance_result` / `scorecard`：实际值、得分、等级、评语；
- `appraisal_review`：自评/上级评/校准/申诉/确认，append-only；
- 指标来源优先级：执行系统自动取数 → KPI 记录 → 项目结果 → 人工评价。

## 6. 优先级

### P0（数据地基）

1. `ProcessNode → ProcessArch L4` 统一活动 ID；
2. 岗位/角色主数据，`ProcessArch/ProcessNode` 增加组织外键；
3. 制度、工具增加活动级绑定；表单/规则在设计器侧绑定；
4. `ProcessTask` 增加实际工时采集（worklog/effort）。

### P1（闭环）

1. 活动标准工时、岗位产能、工作日历；
2. 工作量看板与负载预警；
3. 绩效周期/目标/自动取数/评分/校准/确认；
4. 跨层追溯视图与一致性审计。

### P2（优化）

1. 工作量预测与派工均衡；
2. 能力矩阵与岗位匹配；
3. 绩效与改进项目/激励联动；
4. 过程挖掘与 what-if；
5. 并行网关/子流程/边界事件（先做令牌引擎）。

## 7. 证据索引

- `app/models/process.py:15`（ProcessArch，字符串 department/owner）
- `app/models/process.py:96`（ProcessNode，无 arch 外键，lane/owner_role 字符串）
- `app/models/process_document.py:31`（制度只挂 process_id）
- `app/models/execution.py:223`（表单按 process + node_key）
- `app/models/execution.py:76`（任务只有时间戳，无工时字段）
- `app/models/deliverable.py:36`（StepContract 挂 workflow step_no）
- `app/models/tool_template.py:32`（工具模板挂 deliverable definition/org）
- `app/models/monitor.py:15`（KPI 可挂 process，未挂人员/岗位）
- `app/models/user.py:22`（用户只有系统角色和组织，无岗位/绩效）
- `app/services/execution.py:196`（实例快照冻结 forms/rules）
- `app/seed/corpus.py:590` 与 `app/seed/corpus_data.py:767`（L4 目录与设计节点是两套数据）
