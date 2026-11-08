# 流程资产生产系统 · 第一刀方案

> 上层框架：[企业管理体系图谱](enterprise-management-system-atlas.md)。  
> 状态：方案与原型，不是已实现能力。  
> 第一刀范围：**一条 L3 的已发布 To-Be 模型 → 活动级资产包**。  
> 原型：[prototype/asset-production.html](prototype/asset-production.html)

## 1. 定论摘要

这不是流程管理 OA，也不是报告生成器。它是一个以**稳定活动身份**为骨架、
以**证据等级约束用途**、以**确定性变换生产活动级资产**、以**人工验收作为治理门**
的流程资产生产系统。

四种场景（新体系、单流程优化、项目反推、重组变革）不是四条流程，是
「架构成熟度 × 证据成熟度」的入口组合。第一刀只做一段变换：

```text
已发布 To-Be 模型
  → 活动身份映射（L4 ↔ BPMN 节点）
  → 活动级资产包（SOP / 表单 / 规则 / RACI / 控制点）
  → 人工验收（草稿 → 评审 → 生效）
```

As-Is 抽取、诊断报告、流程挖掘、架构版本、组织版本、批量迁移都后置。

## 2. 产品边界

### 本刀做

- 一条 L3 流程的资产工作台：能产出什么、缺什么、下一步做什么。
- L4 活动与 BPMN 节点的 ArchiMate-lite 关系：多对多、带语义、路径条件与覆盖率。
- 从已发布 To-Be 模型确定性生成活动级资产包。
- 生成前的阻断规则与缺口清单。
- 每个章节/组件的溯源：模型版本、节点、表单/规则版本、内容 hash。
- 关系与证据的录入/裁决 UI：节点↔活动、活动关系、交接、未建模、证据主张、冲突裁决。
- 复用现有流程标准文件版本状态机，完成草稿 → 评审 → 生效。
- HTML 预览；PDF 复用现有 LibreOffice 路径；转换器不可用时明确 503。

### 本刀不做

- As-Is 文档抽取、流程挖掘、访谈结构化。
- 诊断报告 / PCE 报告 / 收益测算。
- 架构版本、组织/岗位版本、批量变更与迁移。
- AI 代写、自动补全、自动判定证据是否成立。
- 新的资产主数据库；不复制表单、规则、RACI 的既有行。

## 3. 核心对象

| 对象 | 复用/新增 | 说明 |
| --- | --- | --- |
| 活动身份 | **复用 `ProcessArch` L4** | v1 以 L4 行作为稳定活动 ID；没有 L4 的节点必须先建或映射，不能生成 |
| 模型版本 | 复用 `ProcessModelVersion` | 只接受 `PUBLISHED` 或已冻结版本；快照不可变 |
| 节点/连线 | 复用 `ProcessNode` / `ProcessEdge` | 只读，不反向修改模型 |
| 架构关系 | **新增 `node_activity_link` / `activity_relation` / `edge_handoff_link` / `unmodeled_activity`** | ArchiMate-lite：8 种关系；节点↔活动、活动层级、连线交接、未建模 |
| 表单/规则/RACI/分派 | 复用 `FormDefinition` / `ProcessRule` / `RaciAssignment` / `NodeAssignment` | 资产包只引用，不复制 |
| 证据 | 复用 `ToolSheet` / `ProcessDocumentVersion` | v1 只接这两类来源；日志窗口后置 |
| 证据主张 | **新增 `evidence_claim` + `evidence_claim_target`** | 主张级；带范围、方法、样本/窗口、质量、冲突组、有效期 |
| 资产包 | 复用 `ProcessDocument/Version` | 流程级资产；新增 `source_kind=COMPILED` 与 `compile_manifest` JSON |
| 组件清单 | **新增 `compiled_asset_component`** | `document_version_id` → 组件引用；支持反向查询「哪些资产用了这个表单」 |
| 治理 | 复用版本状态机 + 审计 + 权限 | 不新建审批引擎 |

**为什么不是 `DeliverableInstance/Version`**：`DeliverableInstance` 是项目步骤级
（`project_id` / `project_step_id` 非空），资产包是流程级；强行复用会破坏既有不变量。
`ProcessDocumentVersion` 已有流程级版本、审批、生效、存储与组织范围，是更合适的载体。
这是对早期方案假设的修正，不是新增概念。

### 3.1 活动身份：ArchiMate-lite 的有类型关系

L4 活动与 BPMN 节点不是 1:1。v1 采用 ArchiMate 的「有类型关系」思想，但**只实现一个受控子集**，
不引入完整 ArchiMate 元模型、元素体系或视图。

| relation | 源 → 目标 | 用途 |
| --- | --- | --- |
| `REALIZES` | 节点 → 活动 | 节点实现活动 |
| `PART_OF` | 节点 → 活动；子活动 → 父活动 | 组成 / 分解 |
| `CONTROLS` | 节点 → 活动 / 控制点 | 控制点 |
| `DECOMPOSES` | 活动 → 子活动 | 架构分解 |
| `TRIGGERS` | 活动 → 活动；节点 → 节点 | 先后触发 |
| `SERVES` | 活动 → 活动 / 服务 | 支撑关系，替代模糊的 `SUPPORTS` |
| `HANDOFF` | 连线 → 交接 | 跨泳道 / 跨活动交接 |
| `UNMODELED` | 活动 → 无 | 电话、邮件、线下签字等未建模活动 |

约束：

- 每个模型活动节点至少一条 `REALIZES` 或 `PART_OF`；否则阻断。
- 每个 L4 活动必须有父级；L1 可显式标记为根；否则阻断。
- 每条跨泳道连线必须有 `HANDOFF`，或显式登记 `NO_HANDOFF`；否则警告。
- 网关/结束节点豁免 `REALIZES`；如承载控制点，必须 `CONTROLS`。
- 映射绑定 `model_version_id` + `node_key` / `edge_key`，不绑可变的数据库 `node_id`；
  模型升版必须重新确认。
- 映射是治理断言：确认人、确认时间、依据必填；合并/拆分走审计。

**lite 的边界**：只实现上表 8 种关系，不实现 ArchiMate 的完整元素、视图、语言扩展。
新增关系类型必须走变更评审，否则会退化成万能标签。

**与既有 `ProcessNode.process_arch_id` 的关系**：该字段已经存在并被设计器、执行和测试使用。
第一刀不删除它，只把它当作**兼容的主活动指针**；权威关系以 `node_activity_link` 为准，
迁移会把历史 `process_arch_id` 回填为 `REALIZES`。设计器后续新写的 `process_arch_id`，
读取层按 `legacy=true` 的 `REALIZES` 兼容，并在就绪度/架构关系里显式提示「尚未在关系表确认」；
只有进入关系表才视为已确认。删除该字段属于独立的一轮重构，不在第一刀里混做。

### 3.2 证据账本：主张级 + 范围继承

一条证据记录的不是「某个节点的某个字段」，而是一条**可检验的主张 + 它覆盖的范围**。

| 字段 | 说明 |
| --- | --- |
| `claim` | 一条可检验主张，例如「A-04 平均等待 180 分钟」 |
| `claim_type` | `EXISTENCE` / `SEQUENCE` / `TIME` / `CONTROL` / `ROLE` / `RULE` / `OUTCOME` |
| `source_type` | `TOOL_SHEET` / `DOCUMENT_VERSION`（v1）；`OBSERVATION` / `LOG_QUERY` 后置 |
| `source_ref` | 记录 ID + revision/version + 内容 hash |
| `scope` | 目标集合：活动 / 节点 / 边 / 时间字段 / KPI + 标准/异常条件 |
| `method` | `OBSERVED` / `DOCUMENTED` / `STATED` / `ESTIMATED` / `LOGGED` / `UNKNOWN` |
| `samples` | 样本量；没有就留空，不填 0 |
| `window` | 观测/日志的时间窗口 |
| `coverage` | 覆盖比例或样本占总体比例 |
| `quality` | 独立性、时效、可复现性等标记；不用单一 `confidence` 数字 |
| `conflict_group` | 同一主张的冲突组 |
| `status` | `OPEN` / `SUPPORTED` / `CONFLICTED` / `ADJUDICATED` / `EXPIRED` |
| `adjudication` | 裁决人、依据、权限、时间 |
| `valid_from/to` | 证据有效期；过期后资产不能保持生效 |
| `query_ref` / `result_hash` | 日志证据的查询与结果 hash，保证可复算 |

- **继承**：主张覆盖的元素默认继承该主张；只有冲突项和例外项需要单独登记。
- **未知**：没有被任何主张覆盖的元素，显式标 `UNKNOWN`，不能显示为「无问题」。
- **冲突**：同一 `conflict_group` 内保留全部来源，不取平均；裁决前资产只能是草稿。
- **不造 confidence 单数字**：用 method + samples + window + coverage + 独立性/时效标记。

### 3.3 用途就绪度

模型不靠名字 policing，靠用途限制：

| 用途 | 最低条件 |
| --- | --- |
| 范围 / 边界 / 设计讨论 | 有模型 + 架构关系 |
| 定量诊断（PCE、瓶颈、收益） | 有观测或日志主张，达到最低样本与覆盖 |
| 执行 / 自动化 | 已发布模型 + 已确认表单/规则 + 分派 |

第一刀只断言「资产包可生成」，不断言「定量诊断有效」。

## 4. 生成规则

### 4.1 阻断（必须全部满足才允许提交评审）

1. 模型版本为 `PUBLISHED` 或已冻结；
2. 活动节点均有 `REALIZES` / `PART_OF`；每个 L4 有父级，L1 有根标记；跨泳道连线有 `HANDOFF` 或 `NO_HANDOFF`；
3. 每个活动有 Owner 角色；
4. 每个活动有表单或记录载体；
5. 每个判断节点有规则；
6. 每个控制点有标准/证据主张；
7. 资产包内所有数字来自模型测算或已登记证据，且标注口径；
8. 冲突组已裁决，证据未过期，或资产包标记为草稿并单列冲突。

### 4.2 允许草稿但不可生效

缺第 3–6 项时，允许生成「草稿」，缺口以「待补」列出。
缺第 1、2、7 项时，**拒绝生成**。

### 4.3 唯一数字口径

- PCE、等待、返工、成本等只从模型测算服务取；
- 证据来源的观测值单独展示，带样本量、窗口、质量；
- 禁止把观测值和模型估算混成一个数；
- 同一指标只有一个实现，前端不重算。

## 5. 数据模型增量（概念）

```text
node_activity_link
  id, model_version_id, node_key, activity_id -> process_arch(level=4),
  relation (REALIZES|PART_OF|CONTROLS),
  path_condition (STANDARD|EXCEPTION|ALL),
  coverage, confirmed_by, confirmed_at, note
  unique(model_version_id, node_key, activity_id, relation, path_condition)

activity_relation
  id, source_activity_id -> process_arch, target_activity_id -> process_arch,
  relation (PART_OF|DECOMPOSES|TRIGGERS|SERVES), model_version_id,
  confirmed_by, confirmed_at

edge_handoff_link
  id, model_version_id, edge_key,
  from_activity_id, to_activity_id,
  handoff_type (HANDOFF|NO_HANDOFF),
  confirmed_by, confirmed_at

unmodeled_activity
  id, model_version_id, activity_id -> process_arch,
  reason, source_ref, confirmed_by, confirmed_at

evidence_claim
  id, process_id, claim, claim_type,
  source_type, source_id, source_version, source_hash,
  method, samples, window_start, window_end, coverage,
  quality JSON, conflict_group, status,
  valid_from, valid_to, query_ref JSON, result_hash,
  created_by, created_at

evidence_claim_target
  id, claim_id -> evidence_claim,
  target_type (ACTIVITY|NODE|EDGE|TIME_FIELD|KPI|RULE),
  target_id, field, condition (STANDARD|EXCEPTION|ALL)

evidence_adjudication
  id, conflict_group, decision, rationale,
  decided_by, decided_at, authority_ref

process_document_version
  + source_kind = 'UPLOAD' | 'COMPILED'
  + compile_manifest JSON
      { rule_version, model_version_id, activity_count,
        inputs: {links, claims, forms, rules, handoffs, unmodeled},
        blockers: [], warnings: [], generated_at, content_hash }

compiled_asset_component
  document_version_id -> process_document_version,
  component_type (SOP_SECTION|RACI|CONTROL|FORM_REF|RULE_REF|KPI_REF),
  component_ref_id, activity_id, source_hash
```

迁移只做新增列/表，不改既有语义；`alembic check` 必须通过。

## 6. API 草图

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/processes/{id}/asset-readiness` | 能产出什么、缺什么、下一步（已实现） |
| GET | `/processes/{id}/architecture-map` | 节点↔活动、活动层级、连线交接、未建模（已实现） |
| POST | `/processes/{id}/architecture-map/links` | 新增/合并节点↔活动（已实现） |
| POST | `/processes/{id}/architecture-map/relations` | 新增/合并活动↔活动（已实现） |
| POST | `/processes/{id}/architecture-map/handoffs` | 新增/合并连线交接（已实现） |
| POST | `/processes/{id}/architecture-map/unmodeled` | 登记未建模活动（已实现） |
| DELETE | `/processes/{id}/architecture-map/links/{link_id}` | 撤销节点↔活动；同步清理兼容指针（已实现） |
| DELETE | `/processes/{id}/architecture-map/relations/{relation_id}` | 撤销活动关系（已实现） |
| DELETE | `/processes/{id}/architecture-map/handoffs/{handoff_id}` | 撤销交接（已实现） |
| DELETE | `/processes/{id}/architecture-map/unmodeled/{unmodeled_id}` | 撤销未建模登记（已实现） |
| GET | `/processes/{id}/evidence-claims` | 主张、范围、覆盖、冲突、过期（已实现） |
| POST | `/processes/{id}/evidence-claims` | 登记主张与范围（已实现） |
| POST | `/processes/{id}/evidence-claims/{claim_id}/adjudicate` | 裁决冲突组（已实现） |
| POST | `/processes/{id}/asset-packages/compile` | 预览：阻断 + HTML + 生成清单，不写库（已实现） |
| GET | `/processes/{id}/asset-packages/print-pack` | 合并多个已生成版本；HTML/PDF（已实现） |
| POST | `/processes/{id}/asset-packages` | 生成 `ProcessDocumentVersion` 草稿（已实现） |
| GET | `/asset-packages/impact` | 反向查询：活动/表单/规则被哪些资产包引用（已实现） |
| GET | `/asset-packages/{version_id}` | 资产包详情与溯源（已实现） |
| GET | `/asset-packages/{version_id}/pdf` | 资产包 PDF；需 LibreOffice，不可用返回 503（已实现） |
| POST | `/asset-packages/{version_id}/transition` | 评审/批准/生效/作废；阻断未清零拒绝（已实现） |

生成接口返回 `preview_html` 与 `manifest`；提交接口只接受已通过阻断的 manifest，
服务端重新计算，不信任前端。

## 7. 前端信息架构

### 默认界面只回答三个问题

1. 这条流程现在能产出什么？
2. 还缺什么？
3. 下一步做什么？

资产图、证据账本、覆盖矩阵、冲突表都放在专家页签，不进入默认首屏。

### 页面

| 页面 | 内容 |
| --- | --- |
| 流程资产工作台 | 流程头、就绪度、缺失项、主按钮「生成资产包」 |
| 生成预览 | 阻断清单、将生成的章节、溯源摘要 |
| 资产包详情 | SOP 正文、活动表、RACI、控制点、表单/规则引用、版本状态 |
| 架构关系（专家） | 节点↔活动、活动层级、连线交接、未建模活动、覆盖率；可登记四类关系 |
| 证据（专家） | 主张表、范围、method/样本/窗口、冲突组、未知项；可登记主张、裁决冲突 |
| 治理 | 版本状态、审批人、生效日期、变更影响 |

### 入口文案

新建流程时不问「选哪个场景」，只问「你手上有什么」：

- 从公司架构开始
- 从一条流程开始
- 从一个问题开始

## 8. 验收

### 机器可验

- 阻断规则逐条可测试；
- 每个节点有 `REALIZES`/`PART_OF`，每个 L4 有父级、L1 有根标记，每条跨泳道边有 `HANDOFF` 或 `NO_HANDOFF`；
- 每条证据主张有 claim_type、scope、method、样本/窗口（适用时）；
- 未被主张覆盖的目标显式标 `UNKNOWN`；
- 过期证据或未裁决冲突阻断「生效」；
- 预览 HTML 的章节与 manifest 一致；
- 每个章节/组件都有来源引用；
- 同一数字只有一个来源；
- 缺项不填 0、不编造；
- `pytest`、`alembic check`、`scripts/verify_frontend.py` 通过。

### 人工验收

- 一个真实流程 Owner 能独立走完「查看缺口 → 生成草稿 → 补项 → 提交」；
- 另一个真实接收者能依据资产包判断是否可用；
- 资产包能回溯到模型版本和证据来源。

### 失败判据

- 用户仍然绕过系统，用 Word + 共享盘交付；
- 生成的资产包「看起来完整」但没人能说清数字来源；
- 架构关系维护成本高到没人愿意做；
- 系统产出的只是模型的打印版，没有新增可执行信息。

## 9. 后续三刀

1. **As-Is 与证据**：文档 → 候选活动；访谈 → 陈述；日志 → 实际路径与时间。
2. **诊断资产**：模型 + 观测 → 证据包；严格区分模型估算与实测。
3. **架构与变革**：架构/组织版本、影响分析、批量迁移；支撑场景 ①③④。

## 10. 风险

| 风险 | 应对 |
| --- | --- |
| **ArchiMate-lite 长成完整 ArchiMate** | 冻结 8 种关系；第一刀只强制 `REALIZES` / `PART_OF` / `HANDOFF`；`DECOMPOSES` / `TRIGGERS` / `SERVES` 可选；新增关系走变更评审 |
| 关系录入变成新主数据负担 | 默认继承 + 批量导入/复制；网关豁免；只对例外逐条确认；先用「未建模」显式登记，不强迫画全 |
| 证据登记太重 | 主张级 + 范围继承；只对冲突逐元素；UI 给主张模板；覆盖由系统计算，不让人手填百分比 |
| 证据过期导致资产大面积失效 | 有效期 + 到期提醒；过期只降级为草稿，不删除历史；支持批量续证 |
| 关系类型成为万能标签 | `SERVES` 只用于明确的支撑关系；禁止用 `PART_OF` 代替 `DECOMPOSES`；审计可查 |
| 资产包变成模型打印版 | 必须包含模型没有的信息：责任、载体、控制点、验收 |
| 治理后置导致废品 | 第一刀即接版本状态机与审批 |
| 新概念泄漏到 UI | 默认三问；专家页签收纳；不让用户先选「关系类型」 |

## 11. 当前实现状态

### 已落地（第一刀地基）

- 模型：[`app/models/asset_graph.py`](../app/models/asset_graph.py)
  - `node_activity_link`
  - `activity_relation`
  - `edge_handoff_link`
  - `unmodeled_activity`
  - `evidence_claim`
  - `evidence_claim_target`
  - `evidence_adjudication`
- 迁移：
  - [`alembic/versions/a2f3b4c5d6e7_asset_relations_and_claims.py`](../alembic/versions/a2f3b4c5d6e7_asset_relations_and_claims.py)
    - 历史 `process_node.process_arch_id` 回填为 `REALIZES`；模型版本未知时留空。
  - [`alembic/versions/b4c5d6e7f8a9_compiled_asset_components.py`](../alembic/versions/b4c5d6e7f8a9_compiled_asset_components.py)
    - `process_document_version.source_kind` / `compile_manifest`
    - `compiled_asset_component`
- 查询服务：[`app/services/asset_graph.py`](../app/services/asset_graph.py)
  - 架构关系查询
  - 证据主张查询、冲突组、未知覆盖
  - 生成就绪度、阻断清单、下一步
- 写入服务：[`app/services/asset_graph_write.py`](../app/services/asset_graph_write.py)
  - 节点↔活动、活动↔活动、连线交接、未建模活动的 upsert
  - 证据主张录入（来源 hash、目标归属校验）与冲突裁决
  - 每次写入接入审计哈希链
- API：[`app/api/v1/asset_graph.py`](../app/api/v1/asset_graph.py)
  - `GET /api/v1/processes/{id}/architecture-map`
  - `GET /api/v1/processes/{id}/evidence-claims`
  - `GET /api/v1/processes/{id}/asset-readiness`
  - `POST /api/v1/processes/{id}/architecture-map/links`
  - `POST /api/v1/processes/{id}/architecture-map/relations`
  - `POST /api/v1/processes/{id}/architecture-map/handoffs`
  - `POST /api/v1/processes/{id}/architecture-map/unmodeled`
  - `POST /api/v1/processes/{id}/evidence-claims`
  - `POST /api/v1/processes/{id}/evidence-claims/{claim_id}/adjudicate`
  - `POST /api/v1/processes/{id}/asset-packages/compile`
  - `POST /api/v1/processes/{id}/asset-packages`
  - `GET /api/v1/asset-packages/{version_id}`
  - `POST /api/v1/asset-packages/{version_id}/transition`
- 生成器：[`app/services/asset_package.py`](../app/services/asset_package.py)
  - 复用 `ProcessDocument/Version` 的流程级生命周期
  - HTML 资产包：SOP 正文、活动与责任、流程级 RACI、控制点、表单与记录、证据与未决
  - `compile_manifest` + `compiled_asset_component`（表单/规则/控制点/RACI/KPI 引用）
  - 提交/流转前重新跑阻断，模型升版拒绝使用旧包
- 日志导入：[`app/models/log_import.py`](../app/models/log_import.py)、[`app/services/log_import.py`](../app/services/log_import.py)、[`app/schemas/log_import.py`](../app/schemas/log_import.py)
  - CSV（case_id/activity/timestamp[/resource]）→ 事件落库 → 人工活动映射 → 实测指标
  - 提交生成 `LOG_IMPORT` + `LOGGED` 证据主张，目标为 `PROCESS.lead_time`
  - API：`GET/POST /processes/{id}/log-imports*`
  - 迁移：`d6e7f8a9b0c1_log_imports.py`
  - 前端「导入 CSV 日志」弹窗：上传、映射、指标预览、提交
  - 双样本只读对照：`GET /processes/{id}/log-imports/compare?before_id&after_id`
    - 校验两次均 COMMITTED、活动映射一致、模型版本一致
    - 比较平均/中位/P90 周期、单量、事件数、映射覆盖与 Top 变体
    - 样本 <5、覆盖 <90%、窗口重叠显式提示；不自动写回目标
  - 对照接收与改善宣称门禁：`LogComparisonReceipt`、[`e7f8a9b0c1d2_log_comparison_receipts.py`](../alembic/versions/e7f8a9b0c1d2_log_comparison_receipts.py)
    - 只记录人工结论（接收/退回/观察）与依据，不修改日志或指标
    - `claim_allowed = 接收 + 可比 + 两次单量均 ≥5`；接收小样本对照只能作为观察
    - `GET /processes/{id}/log-imports/compare/claim-readiness`：能否据此宣称改善及原因
    - `POST /processes/{id}/log-imports/compare/receipt`（MANAGER+）；`GET .../receipts` 查历史
    - 每次登记写审计哈希链；门禁结果不替代收益测算
- 文档候选活动：[`app/models/document_candidate.py`](../app/models/document_candidate.py)、[`app/services/document_extract.py`](../app/services/document_extract.py)、[`app/schemas/document_candidate.py`](../app/schemas/document_candidate.py)
  - 从已生效文档读取 txt/md/csv/docx，解析编号/项目符号步骤
  - 候选暂存 PROPOSED/CONFIRMED/REJECTED；确认只创建 L4 活动，不自动改 BPMN
  - API：`GET/POST /processes/{id}/document-candidates*`
  - 迁移：`c5d6e7f8a9b0_document_candidate_activities.py`
  - 前端「从文档提取候选活动」弹窗
- As-Is 来源画像：[`app/services/source_profile.py`](../app/services/source_profile.py)、[`app/services/model_source.py`](../app/services/model_source.py)、[`app/schemas/model_source.py`](../app/schemas/model_source.py)
  - 与诊断证据包共用来源统计，不再各算一套
  - 方法、来源类型、覆盖活动、观测/日志时间、缺口与用途就绪度
  - `GET /processes/{id}/model-source-profile`
  - 证据目标（活动/时间字段）写入时绑定当前模型版本
  - 前端资产页「As-Is 来源画像」卡片 + 多活动来源登记
- 追溯矩阵：[`app/services/traceability.py`](../app/services/traceability.py)、[`app/schemas/traceability.py`](../app/schemas/traceability.py)
  - `GET /traceability`（objective_id / kpi_id / process_id / activity_id）
  - 目标/KPI → L3/L4 → 节点 → 资产版本 → 证据；缺链接显示「未承接」
  - 前端「追溯矩阵」视图（价值与目标）
- 诊断证据包：[`app/services/diagnosis.py`](../app/services/diagnosis.py)、[`app/schemas/diagnosis.py`](../app/schemas/diagnosis.py)
  - 来源画像从证据账本推导（方法、覆盖活动、观测/日志时间主张）
  - 用途就绪度：范围/设计、定量诊断、根因与收益
  - 模型指标只从 `designer.analyze` 取，明确标「估算」
  - 预览/生成 `DG-` 报告；复用 `ProcessDocumentVersion` 生命周期
  - API：`GET /processes/{id}/diagnosis-readiness`、`POST /processes/{id}/diagnosis-packet/compile`、`POST /processes/{id}/diagnosis-packet`
  - R1 编译：`GET /processes/{id}/r1-readiness`、`POST /processes/{id}/r1/compile`、`POST /processes/{id}/r1`
    - 2.1 SIPOC、2.2 VSM/观测时间、2.3 5Why/帕累托为必填；2.4 瓶颈可选
    - 必填未齐可出草稿；提交评审由 R1 门禁拦截（409）
  - 前端资产页「诊断证据包 R1」卡片：来源画像、R1 输入清单、用途就绪度、预览、生成、HTML/PDF
- 测试：[`tests/test_asset_graph.py`](../tests/test_asset_graph.py)
- 前端：[`web/js/views/asset.js`](../web/js/views/asset.js)
  - 侧栏「流程资产」入口；工作台/流程清单选中 L3 后进入；SPA 深链 `/asset`；帮助中心 `module-asset`
  - 默认三问：能产出什么 / 缺什么 / 下一步
  - 阻断清单可直接跳到设计器、执行运行配置、分析页
  - 预览 modal（iframe）、生成草稿、HTML 下载、提交评审
  - 架构关系：登记/撤销节点↔活动、活动关系、交接、未建模
  - 证据：登记主张（来源、目标、样本/窗口/有效期）；MANAGER 可裁决冲突
  - 资产包 HTML 预览 / HTML 下载 / PDF 下载；PDF 按钮只在转换器可用时显示
  - 变更影响：选活动/表单/规则，查哪些资产包版本引用；结果可打开对应 HTML
  - 打印包：合并本流程多个已生成版本，支持 HTML / PDF；可选版本范围

### 验证结果

- `pytest`：全量通过（1 条跳过）。
- `alembic check`：在临时 PostgreSQL 库上通过，无 schema 漂移。
- `ruff format --check app tests scripts`、`ruff check app tests scripts`：通过。
- `pytest tests/test_frontend_structure.py`：通过（含新视图注册、import 解析、侧栏顺序、帮助目录）。
- `node --check web/js/views/asset.js`：通过。
- 资产页专项 Playwright 检查：选择 L3-032 后三问与就绪度渲染正常；五个编辑器按钮可见；
  节点↔活动与证据主张弹窗可打开；无 page error、无失败 API 请求。
- 资产包 PDF：转换器不可用时 503；mock 转换器时返回 `application/pdf` 与 PDF 字节，测试通过。
- 关系撤销：四类 DELETE 均通过；撤销 REALIZES 会清掉兼容指针并重新出现未映射阻断；重复删除 404；只读角色 403。
- 浏览器专项：L3-032 架构关系显示删除按钮，确认框可打开；取消后没有写请求；无 page error、无失败 API 请求。
- 组件反向查询：按活动与按表单查询均 200；无过滤器 400；非法组件类型 400；
  浏览器卡片能加载活动/表单选项并返回结果，无 page error、无失败 API 请求。
- 打印包：两个版本合并 HTML 均包含版本号；按 version_ids 过滤生效；PDF 转换器不可用 503、
  mock 转换器返回 `application/pdf`；无资产包 404；非法 version_ids 400。
- `python scripts/verify_frontend.py` **未全绿**：失败项包括 `pilot`、M3–M7 等既有路径和
  `BPMN 导入导出` 超时；默认落地已改为「工作台」、体系总览深链断言已同步，但尚未完整跑绿；
  `view:asset` 不在失败列表。本轮没有宣称全量通过。
- `python scripts/check.py --fast` 仍会被未跟踪目录 `cbpp-prep-main/` 的 Python 文件拖失败；
  与本方案代码无关，需单独决定是否清理该目录。

### 尚未落地

- 边 / KPI / 规则目标的证据录入 UI：当前编辑器支持活动、时间字段、节点；其余目标走 API。
- 关系直接编辑：当前用「撤销 + 重新登记」改错；单条 PATCH 后置。
- 种子：仅回填 `process_arch_id`；`DECOMPOSES` / `TRIGGERS` / `SERVES` / 交接 / 主张的演示数据尚未灌入。
- 跨流程批量打印包：单流程多版本已实现；一次导出多个流程的打印包未做。
- 访谈/日志自动结构化：文档候选活动与 CSV 日志导入已实现；访谈记录仍未自动抽取。
- 日志活动同义词表：已支持名称/编码匹配与历史映射建议；可维护的同义词表后置。
- 外部日志系统接入：当前是 CSV 导入，没有 API/增量同步。
- 改善前后对照与收益测算：两日志只读对照、接收结论、改善宣称门禁、KPI 基线/目标写回与
  阶段门引用已实现；资产基线写回、收益测算、阶段自动推进、轮次结论引用未做。
- 诊断的根因验证与收益测算：当前只列模型候选与证据状态，不宣称已验证根因或收益。
- 诊断证据包的独立 PDF 路径：复用 `/asset-packages/{version_id}/pdf`，路径名仍叫 asset-packages。

## 12. 第二条产线：诊断证据包（第一刀已实现）

### 诊断输入

- 一个已发布模型版本
- 证据账本里的有效主张：方法、样本、窗口、目标（活动/时间字段/节点）

### 诊断输出

- 来源画像：各方法主张数、覆盖活动数、观测/日志时间主张数
- 用途就绪度：范围/设计、定量诊断、根因与收益
- 模型估算指标：PCE、期望周期、等待占比、返工损失、单次成本
- 节点瓶颈候选与周期贡献
- 有效证据、未裁决冲突、未被覆盖目标
- 模型提示的候选问题与下一步

### 硬规则

1. 数字只从 `designer.analyze` 取；证据里的观测值单独展示，不并入模型数值。
2. 没有观测/日志时间主张时，允许生成草稿，但「定量诊断」必须显示不可用，报告处处标「模型估算」。
3. 硬阻断只有两个：模型未发布、活动未映射。缺 Owner/表单/规则不阻断诊断。
4. 生成物是 `DG-<process.code>` 的 `ProcessDocumentVersion`：`source_kind=COMPILED`；通用诊断 `manifest.kind=DIAGNOSIS`，R1 `manifest.kind=DIAGNOSIS_R1`，复用标准文件版本状态机。
5. R1 必填输入：2.1 SIPOC、2.2 VSM/观测时间、2.3 5Why/帕累托；2.4 瓶颈可选。必填未齐可出草稿，不能提交评审。
6. 诊断证据包不是设计批准或上线批准；接收后才进入设计。

### 诊断本刀不做

- 文档 / 访谈 / 日志抽取与候选模型生成
- 根因验证、收益测算、自动写结论
- 独立的诊断证据包 PDF 路径（当前复用 `/asset-packages/{version_id}/pdf`）

### 诊断验证

- 无观测时间：定量用途不可用，阻断包含 `OBSERVED_TIME_MISSING`，仍可预览/生成草稿。
- 补一条 `OBSERVED + TIME_FIELD + samples>=1` 主张并裁决冲突后：定量用途可用，诊断预览含 PCE 与「模型估算」。
- 生成物 `kind=DIAGNOSIS`、`DG-` 编码、`DRAFT`；`GET /asset-packages/{version_id}` 可回读。
- 活动未映射：`can_compile=false`，提交 409。
- 浏览器专项：L3-032 诊断卡片渲染，进入预览弹窗，无 page error / 失败 API。
- R1 门禁：缺 SIPOC/VSM/5Why 时 `can_submit_review=false`、`missing_inputs` 三条、草稿可生成；
  补齐三类 ToolSheet 主张并裁决冲突后 `can_submit_review=true`；R1 草稿转评审在缺输入时 409，补齐后 200。
- R1 浏览器专项：资产页显示「诊断证据包 R1」、四行输入清单、「缺必填输入」标签；
  点击「预览 R1」打开弹窗，无 page error / 失败 API。
- 追溯矩阵：目标/KPI/流程/活动四种查询均 200；行含 KPI 最新值、节点、资产版本、证据；
  未承接目标进入 orphans；浏览器视图可打开，无 page error / 失败 API。
- 日志对照：两次已提交日志平均周期 90 → 45 分钟，delta -50%；映射不同/未提交显式不可比；
  同一 id 400、缺失 id 404；浏览器打开「日志前后对照」弹窗，dev 库无两次已提交日志时显示空提示。
- 对照接收与门禁：ACCEPT 后 `claim_allowed=true` 且最新接收记录可回读；RETURN 后重新关闭；
  不可比 ACCEPT 400；两次各 2 单可接收但不可宣称改善；只读 403、空依据 400、非法结论 422、
  不存在导入 404；前端弹窗显示门禁原因、接收记录与登记表单。
- 接收门禁浏览器专项（mock 两次已提交日志）：比较后显示「不可据此宣称改善」与原因；
  登记 ACCEPT 后显示「可据此宣称改善」与接收记录，时间按浏览器时区换算；toast 正常；
  无 page error、无失败 API。dev 库无两次已提交日志时显示「至少需要两次已提交的日志导入」。
- KPI 写回：未接收 409；基线/目标更新且 KPI 版本 +1；同值重复不升版；小时单位换算；
  非时长/活动级/周频 400；跨月 409；同期正式数据点 409；provenance 含对照与接收记录。
- 阶段门引用：声明改善无对照 400；他流程/失效对照 400；有效对照签收并冻结快照；
  退回后推进被「对照已失效」阻止；可引用清单同步移除。
- As-Is 来源画像：初始方法/覆盖/缺口正确；多活动来源登记后目标绑定当前模型版本；
  补观测时间并裁决冲突后定量用途可用；浏览器卡片与登记弹窗可打开，无 page error / 失败 API。
- 文档候选活动：txt 提取 3 条、重复提取幂等；force 保留已确认/驳回；确认创建 L4 活动并用
  `L4C...` 编码；驳回后不能再确认；只读 403；缺失版本 404；迁移在临时 PostgreSQL 上通过
  `alembic check`。浏览器打开提取弹窗；dev 库 L3-032 没有已生效文档，显示空来源提示，
  表单路径由后端测试覆盖。
- 日志导入：4 事件/2 单上传成功；未映射提交 400；映射后平均周期 90 分钟；提交生成
  `LOG_IMPORT` + `LOGGED` 证据；来源画像出现 LOG_IMPORT 且观测时间 ≥1；裁决冲突后诊断
  定量用途可用；只读 403；缺列 CSV 400；迁移 `alembic check` 通过。
  映射建议：名称/编码匹配；第二次导入的未匹配标签复用历史映射。
  浏览器打开日志导入弹窗、文件输入可见，无 page error / 失败 API；上传/映射/提交路径由后端测试覆盖。
- 首页入口：默认「工作台」或「流程」清单选中 L3 后进入资产工作台；页面标题切到「流程资产」；
  页面标题切到「流程资产」，无 page error / 失败 API。

## 13. As-Is 来源画像（第二刀已实现）

### 来源输入

- 当前已发布模型版本
- 证据主张：方法、来源、样本、目标（活动/时间字段/节点）

### 来源输出

- 有效主张 / 总主张、各方法主张数、来源类型数
- 覆盖活动 / 活动总数、观测或日志时间主张数
- 每个活动的方法覆盖与缺口
- 用途就绪度：范围/设计、定量诊断、根因与收益
- 下一步

### 来源登记

- 复用 `evidence_claim` 写入，不新建来源表；一条主张可覆盖多个活动。
- 方法：`DOCUMENTED / STATED / OBSERVED`；`LOGGED` 可走 API。
- 可同时登记 `TIME_FIELD` 的 `wait` / `duration`。
- 活动与时间字段目标在写入时绑定当前 `model_version_id`；未绑定的历史目标按 legacy 计入并警告。

### 规则

1. 制度/访谈能支撑范围与设计讨论，不能支撑实测时间。
2. 只有 `OBSERVED / LOGGED` + `TIME_FIELD` + `samples >= 1` 才算观测时间。
3. 来源画像与诊断证据包共用 `app/services/source_profile.py`，不各算一套。
4. 模型升版后，旧的版本绑定目标不计入新版本画像。

### 来源本刀不做

- 文档 / 访谈 / 日志的自动抽取与候选活动生成
- 日志查询/接入 UI
- 来源质量评分（当前只有方法维度，没有独立性/时效评分）

### 来源验证

- 初始画像：方法数、覆盖活动、来源类型与缺口正确。
- 多活动来源登记后：新增活动/时间字段目标均绑定当前模型版本。
- 补观测时间并裁决冲突后：定量用途从不可用变为可用。
- 浏览器专项：L3-032 来源画像卡片、登记弹窗可打开；活动与来源选项非空；无 page error / 失败 API。

## 14. 文档 → 候选活动（已实现）

### 文档输入

- 已生效的 `ProcessDocumentVersion`，且文档适用于当前流程。
- 支持 txt / md / csv / docx 文本读取；docx 只取段落文本，不解析表格、图片、批注。
- 解析编号步骤（`1.` `1)` `一、`）与项目符号行，去重，最多 200 条。

### 候选输出

- `DocumentCandidateActivity`：行号、原文、候选名、识别方式、状态。
- 状态：`PROPOSED / CONFIRMED / REJECTED`。
- 重复提取不重复插入；`force=true` 只清理 `PROPOSED`，保留已确认/已驳回。

### 确认规则

1. 确认只创建 `ProcessArch` L4 活动，不自动创建或修改 BPMN 节点。
2. 编码默认 `L4C<process.id>-NNN`，可人工覆盖；重复编码 409。
3. 活动描述标注来源文档、版本与行号，并写明「尚未映射到 BPMN 节点」。
4. 驳回后不能再确认；只读角色 403。

### API

```text
GET  /api/v1/processes/{id}/document-candidates?document_version_id=...
POST /api/v1/processes/{id}/document-candidates/extract
POST /api/v1/processes/{id}/document-candidates/{candidate_id}/confirm
POST /api/v1/processes/{id}/document-candidates/{candidate_id}/reject
```

### 前端

资产页「As-Is 来源画像」卡片新增「从文档提取候选活动」：

- 选择已生效文档版本
- 开始提取 → 候选表
- 逐条确认/驳回；确认后显示新 L4 活动编码
- 完成关闭并刷新资产页

### 文档本刀不做

- 访谈记录、日志变体的自动结构化
- 候选活动 → BPMN 节点的自动映射
- PDF/扫描件 OCR、docx 表格/图片解析
- 自动发布或把候选冒充实测 As-Is

### 文档验证

- txt 文档提取 3 条；重复提取幂等。
- `force` 重新提取保留已确认/已驳回，只重算未处理。
- 确认创建 L4 活动：`level=4`、`parent_id=流程`、编码 `L4C...`。
- 驳回后不能再确认；只读 403；缺失版本 404。
- 新迁移在临时 PostgreSQL 上通过 `alembic check`。
- 浏览器打开提取弹窗；dev 库 L3-032 无已生效文档，显示空来源提示；表单路径由后端测试覆盖。

## 15. CSV 事件日志导入（已实现）

### 日志输入

- CSV 列：`case_id`、`activity`、`timestamp`，可选 `resource`。
- 支持常见别名（工单号/活动/时间/处理人等）；UTF-8（含 BOM）。
- 限制：≤20MB、≤5 万事件；时间需 ISO 可解析；无效行直接 400，不静默跳过。
- 上传后先落库为 `DRAFT`，不直接生成证据。

### 活动映射与指标

- 人工把日志活动标签映射到 L4 活动，或选择忽略。
- 映射建议（只做建议，不自动提交）：
  - 标签与 L4 活动名称/编码完全匹配 → 建议「名称/编码匹配」
  - 本流程历史导入里已映射过的标签 → 建议「历史映射」
  - 前端预选建议，仍需人工点「计算指标」确认
- 映射后计算：
  - 单量、事件数、映射覆盖率、未映射事件
  - 每单周期（最后事件 - 首事件）的均值/中位/P90/最小/最大
  - 活动计数与 Top 变体序列
  - 数据窗口
- 重复映射会先清空本导入的映射再写入，避免残留旧映射。

### 证据提交

- 提交时生成一条 `EvidenceClaim`：
  - `claim_type=TIME`、`method=LOGGED`、`source_type=LOG_IMPORT`
  - `samples=case_count`、窗口、映射覆盖率、来源 checksum、结果 hash
  - 目标：`PROCESS` / `field=lead_time`
- 只有映射事件 > 0 才能提交；提交后导入状态 `COMMITTED`，claim id 回写。
- 来源画像与诊断证据包把这条主张计入「观测/日志时间」，但报告仍标模型估算与日志实测分开。

### 前后对照与改善宣称门禁

两次已提交日志先做只读对照，再由人登记接收结论；系统只做门禁，不替人下结论。

```text
GET  /api/v1/processes/{id}/log-imports/compare?before_id=&after_id=
GET  /api/v1/processes/{id}/log-imports/compare/claim-readiness?before_id=&after_id=
POST /api/v1/processes/{id}/log-imports/compare/receipt        # MANAGER+
GET  /api/v1/processes/{id}/log-imports/compare/receipts?before_id=&after_id=
GET  /api/v1/processes/{id}/log-imports/compare/accepted
GET  /api/v1/processes/{id}/log-imports/compare/write-back-options?before_id=&after_id=
POST /api/v1/processes/{id}/log-imports/compare/write-back     # MANAGER+
```

- 结论：`ACCEPT` 接收 / `RETURN` 退回 / `OBSERVE` 观察；依据必填。
- `ACCEPT` 只接受「可比较」的对照；不可比返回 400。
- `claim_allowed = ACCEPT + 可比 + 两次单量均 ≥ 5`。样本不足仍可接收为方向性观察，
  但不能据此宣称改善。
- `claim-readiness` 取该对照对的最新一条结论；给出不可宣称的原因（不可比、样本不足、
  尚未接收、未被接收）。
- 接收记录保存当时的指标快照、提示与结论，写审计哈希链；接收本身不改日志、目标或资产基线。
- 前端「日志前后对照」弹窗：比较后显示门禁状态、最近接收记录；MANAGER 可登记结论。

### 写回 KPI 基线/目标

写回是接收之后的独立动作，不是接收的自动副作用；只有门禁通过的对照才允许写回。

- 仅月频、流程级（`activity_id` 为空）、启用中的时长单位 KPI 可写回；分钟按 KPI 单位换算
  （`app/services/kpi.py` 的时长单位表），不做第二套换算。
- 改善后数据窗口必须落在同一自然月；跨月窗口拒绝写回，避免把一个多月的均值塞进单期数据点。
- 基线取「改善后平均周期」，换算到 KPI 单位后写入 `kpi_definition.baseline_value`；
  目标值必须由人显式填写，不能由实测值自动顶替。
- 基线或目标实际变化时 `kpi.version + 1`，并写审计哈希链；同值重复提交不重复升版。
- 同时写一条 `KpiRecord`，`provenance.source_kind = LOG_COMPARISON`，带接收记录 id、
  前后导入 id / 证据主张 id、样本量、映射覆盖、窗口、模型版本、完整对照指标与结论。
- 同一 KPI 同一期间已有非日志对照数据点时拒绝覆盖（409）；日志对照数据点可重复写回同一期。
- 写回只改 KPI 定义与数据点，不改项目阶段、资产版本或轮次结论；挂着该 KPI 的开放项目
  当前值按既有 `align_open_projects` 规则跟随最新数据点。
- `LOG_COMPARISON` 数据点不作为 KPI 的正式取数来源；监控红黄绿仍按 `measurement` 配置的
  `EXECUTION_ELAPSED` / `INBOUND_VERIFIED` 判定。
- 阶段门已接入本门禁：声明「本次门禁依据改善对照」时必须引用当前有效的已接收对照；
  引用时冻结指标快照。进入下一阶段时重新核验，对照被退回或失效会阻止推进。
- 轮次结论（`DATA_READY` / `RUN_EFFECTIVE` / `IMPROVEMENT_MET`）仍走既有正式样本与
  口径 hash 校验，尚未改为引用本门禁；接入时必须以 `claim-readiness` 为准。
- 前端：「可据此宣称改善」后显示「写回 KPI 基线」；弹窗列出可写回 KPI、换算后的观测值、
  当前基线/目标，目标留空表示不改。

### 阶段门引用对照

阶段门（`POST /maturity/gates`，`purpose=STAGE_GATE`）新增两个可选字段：

```text
claims_improvement: bool          # 本次门禁是否依据改善对照
comparison_receipt_id: int        # 引用的已接收对照
```

- 声明改善（`claims_improvement=true`）时必须提供对照；提供对照也视为声明改善，否则 400。
- 未声明、未引用对照的普通门禁行为不变；自由文本里的改善断言不解析，不视为已核验结论。
- 对照必须属于项目关联的流程，且是**该对照对的最新结论**、已 ACCEPT、可比、两次
  单量 ≥5；否则 400，并列出不可用原因。
- 签收时把对照指标、样本、接收人冻结进 `evidence_snapshot`，后续数据变化不改历史签收。
- 进入下一阶段时（`ensure_advance_allowed`）重新核验引用对照；若之后被退回或不再满足
  门禁，阶段推进被拒绝。未引用对照的普通门禁行为不变。
- 前端「门禁签收」新增「本次门禁依据改善对照」；只列出当前可引用的对照
  （`GET /processes/{id}/log-imports/compare/accepted`），签收后记录标记「改善对照」。

### 日志本刀不做

- 外部系统 API / 增量同步
- 活动标签自动映射（同义词、历史映射）
- 活动级开始/结束配对、资源产能与排队仿真
- 收益测算、资产基线写回、项目阶段/轮次自动推进

### 日志验证

- 4 事件 / 2 单上传成功；未映射提交 400。
- 映射后平均周期 90 分钟；提交生成 `LOG_IMPORT` + `LOGGED` 证据。
- 来源画像出现 `LOG_IMPORT` 且观测时间 ≥1；裁决冲突后诊断定量用途可用。
- 只读 403；缺列 CSV 400；迁移在临时 PostgreSQL 上通过 `alembic check`。
- 前后对照接收：初始 `claim_allowed=false` 且原因含「尚未接收」；只读角色登记 403；
  空依据 400；ACCEPT 后门禁通过且最新接收记录回读一致；RETURN 后门禁重新关闭；
  不可比对照 ACCEPT 400；非法结论 422；不存在导入 404。
- 小样本：两次各 2 单可比较但 `sample_ok=false`；ACCEPT 成功但 `claim_allowed=false`，
  门禁原因含「样本量不足 5 单」。
- 写回门禁：未接收时 `write-back-options.claim_allowed=false`，写回 409 并给出原因。
- 写回结果：基线 `null → 45`、目标 `null → 30`、KPI `v1 → v2`；`KpiRecord` 值 45、
  期间 `2026-11-01`，provenance 含 `LOG_COMPARISON`、接收记录 id、前后导入 id、
  `mean_lead_minutes` 完整对照；同值重复提交不升版、不增 revision。
- 写回边界：小时单位 KPI 换算为 0.75；非时长单位 400；活动级 KPI 400；周频 KPI 400；
  跨月窗口 409；空依据 400；同期已有正式数据点 409。
- 写回浏览器专项（mock）：门禁通过后出现「写回 KPI 基线」；弹窗显示换算后观测值与当前
  基线/目标，切换 KPI 提示同步更新；提交后 toast 显示新版本、基线、目标；无 page error、
  无失败 API。
- 阶段门对照：声明改善但不选对照 400；引用不存在/他流程对照 400；引用有效对照签收 201，
  快照含 `LOG_COMPARISON`、指标与 `sample_ok`；对照被退回后再次引用 400，
  `ensure_advance_allowed` 以「对照已失效」阻止推进；可引用清单同步移除该对照。
- 阶段门浏览器专项（mock）：勾选「依据改善对照」后出现对照下拉，选项显示前后文件名、
  周期与变化%；签收请求带 `claims_improvement=true` 与 `comparison_receipt_id`；
  无 page error、无失败 API。
- 浏览器打开日志导入弹窗、文件输入可见；上传/映射/提交路径由后端测试覆盖。
