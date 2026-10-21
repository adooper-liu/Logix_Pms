# 流程步骤、交付物版本与集团/分公司继承

本文分析三个容易混在一起的问题：

1. 流程由一系列梳理活动和步骤组成，每个步骤用不同工具/模板、产生不同交付物；
2. 这些交付物需要版本管理；
3. 集团标准与分公司标准之间需要统一、继承，又允许必要的本地差异。

核心结论：

> **把「流程标准」「步骤契约」「交付物定义」「交付物实例」拆成四层；
> 版本只追加不覆盖；集团与分公司用「引用 + 受控覆盖」继承，不复制文件。**

---

## 一、先拆清楚四层对象

很多版本管理失败，不是版本号设计得不好，而是把不同层的东西混在一张表里。

| 层 | 对象 | 例子 | 谁维护 | 版本语义 |
|---|---|---|---|---|
| 方法资产 | 工具、模板、检查表、方法论 | 5Why 模板、SIPOC 表、BPMN 模板 | 集团 CoE / 方法专家 | 模板版本，可复用 |
| 流程标准 | 流程定义 + 步骤契约 | 「采购到付款 L3」标准流程 v3 | 集团流程 Owner + 分公司流程 Owner | 标准版本 + 生效日期 |
| 交付物定义 | 某步骤必须产出什么 | 「现状流程清单」「改善方案」「SOP」 | 流程标准维护者 | 定义版本，绑定模板 |
| 交付物实例 | 某个项目/某次执行真正产出的文件 | 2026 年采购流程现状清单.xlsx | 项目组 / 执行人 | 实例版本 + 审批状态 |
| 运行实例 | 流程的一次运行 | 采购申请实例 #20261022-001 | 执行引擎 | 启动时快照，不随标准漂移 |

四层的关系：

```text
方法资产（模板/工具）
      ↓ 被引用
流程标准（步骤 + 步骤契约）
      ↓ 实例化
项目步骤 / 流程实例
      ↓ 产出
交付物实例（文件 + 版本 + 审批）
```

关键区分：

- **模板不是交付物。** 模板是空白骨架；交付物是填好、评审过、可审计的实例。
- **流程标准不是项目。** 标准回答「应该怎么做」；项目回答「这次怎么改」。
- **交付物实例必须记录它用的是哪个模板版本、哪个流程标准版本。** 否则无法回答
  「这份文件是按哪版标准产出的」。

---

## 二、步骤契约：每个步骤到底需要什么

只给步骤起个名字不够。每个步骤应有一份「契约」，至少包含：

| 字段 | 说明 |
|---|---|
| 输入 | 上游交付物、数据、系统权限 |
| 工具 | 本步骤允许/推荐使用的方法工具（引用工具库） |
| 模板 | 产出物使用的模板及版本约束 |
| 输出 | 必须产出的交付物定义（可多个） |
| 验收标准 | 完整性、格式、评审人、通过条件 |
| 责任人 | 角色（不是具体人），如流程 Owner、财务 BP |
| 决策门 | 是否需要评审/审批才能进入下一步 |

这样「每个步骤用不同工具与模板」不再是口头约定，而是可检查的配置：
某一步缺交付物、用了过期模板、没通过评审，系统都能发现。

### 交付物定义 vs 交付物实例

```text
deliverable_definition（定义）
  code, name, type, template_id, required, acceptance_criteria

deliverable_instance（实例）
  project_id / process_instance_id, step_id,
  definition_id, template_version_id,
  current_version_id, status, owner
```

实例创建时**固定**模板版本和流程标准版本。之后模板升级，不会悄悄改变已产出的文件；
需要迁移时走「升级/重审」动作，并留下记录。

---

## 三、版本模型

### 3.1 不可变版本 + 可变指针

```text
document / deliverable
  id, code, title, scope, current_version_id

version
  id, owner_id, version_no, status,
  file_ref, checksum, mime, size,
  author, reviewer, approver,
  base_version_id, change_request_id,
  valid_from, valid_to, created_at
```

规则：

- 新版本只追加，历史版本永不覆盖（不要出现 `最终版_v2_真正最终版.docx`）。
- 当前版本只是一个指针；恢复历史版本 = 移动指针，不复制文件。
- 每次保存计算 SHA-256，保证文件内容可校验。
- 删除受控交付物通常只做「作废/归档」，不物理删除；保留期按法规/制度。
- 审批状态至少：`DRAFT → IN_REVIEW → APPROVED → EFFECTIVE → SUPERSEDED → RETIRED`。

### 3.2 版本号怎么定

| 对象 | 建议 |
|---|---|
| 模板/方法资产 | 语义化版本：`major.minor.patch`。结构变更升 major，新增可选字段升 minor，文字/格式修正升 patch |
| 流程标准 | `v3.2` + 生效日期。major 变更需重新审批/培训，minor 可自动通知 |
| 交付物实例 | 单调递增修订号 `R1, R2...` + 状态；不要用语义化版本，业务人员看不懂 |
| 法规/质量记录 | 修订号 + 生效日期 + 批准记录；不要只留「最新版」 |

> 语义化版本适合模板和接口；业务文件更重要的是「修订号 + 状态 + 生效日期 + 审批人」。

### 3.3 基线（baseline）

在关键节点打基线：年度标准发布、项目立项、审计前、集团版本升级前。
基线是一组版本的快照，不是新文件。它回答「当时的标准和交付物到底是什么样」。

---

## 四、集团与分公司的继承

### 4.1 不要复制，要引用

最常见的错误：集团发一套模板，分公司复制到自己的目录改一改。结果是：

- 集团升级后，分公司不知道；
- 同一份模板出现 N 个变体；
- 审计时无法说明哪个是现行有效版本；
- 差异无法合并，只能继续复制。

正确做法是「引用 + 受控覆盖」：

```text
集团标准 v3.2
   └── 分公司 A 变体 v3.2.1（只记录差异）
   └── 分公司 B 变体 v3.2.0（无差异，直接继承）
```

分公司不保存一份完整副本，而是保存：

- `base_standard_version_id`：基于集团哪一版；
- `overrides`：只记录允许修改的字段/步骤；
- `extensions`：允许新增的本地步骤/字段；
- `effective_version`：运行时计算出的有效版本。

### 4.2 覆盖策略要写进模型

每个可继承元素带一个策略，不要用口头约定：

| 策略 | 含义 | 例子 |
|---|---|---|
| `LOCKED` | 集团强制，分公司不能改 | 合规审批节点、法定记录字段 |
| `PARAMETERIZED` | 结构不变，只允许改参数 | 审批金额阈值、时限 |
| `EXTENDABLE` | 允许增加本地步骤/字段 | 分公司额外的设备点检 |
| `OPTIONAL` | 允许关闭 | 非必需的推荐步骤 |
| `LOCAL_ONLY` | 只存在于本地，不向上继承 | 分公司内部报表 |

覆盖粒度要细到「步骤/字段」，而不是整套流程。否则分公司一旦有一个差异，
就会 fork 整个流程，最终失去继承意义。

### 4.3 有效版本解析

运行时按「组织 + 流程 + 日期」解析：

```text
effective(org, process, date)
  = 最近的已批准祖先标准版本
  + 沿途各层 overrides（按优先级）
  + extensions
  - 被禁用且允许禁用的步骤
```

解析结果要可解释：页面上能展开「这一条来自集团 v3.2，这一条被分公司 A 覆盖为 5 天」。
没有可解释性，业务人员不会信任继承结果。

### 4.4 升级、变基与冲突

集团发布新版本时：

1. **影响分析**：哪些分公司变体基于旧版、哪些覆盖字段与新版本冲突；
2. **差异展示**：三方对比（集团旧版 / 集团新版 / 分公司变体）；
3. **处理方式**：
   - major：分公司必须重新审批，不能自动合并；
   - minor：无冲突可自动变基，有冲突转人工；
   - patch：自动跟随，通知即可；
4. **冻结与追溯**：已启动的项目/实例继续使用启动时固定的版本，不中途换标准；
5. **通知与待办**：把「待升级」变成任务，而不是发一封邮件。

### 4.5 治理边界

- 集团 CoE / 流程管理科：拥有核心标准、方法资产、通用模板、跨公司指标定义；
- 分公司流程 Owner：拥有本地变体、本地参数、本地扩展，并对本地合规负责；
- 质量/合规：拥有 `LOCKED` 元素的否决权；
- 变更控制委员会（CCB）：审批 major 变更和跨公司影响大的变更；
- 审计：按基线检查「标准—项目—交付物—实例」的一致性。

一个实用的治理原则是「共同核心 + 本地尾巴」：
集团锁定 60–80% 的核心结构与合规要求，分公司只保留 20–40% 的本地差异；
差异必须进入系统，不允许存在系统外的「影子流程」。

---

## 五、行业最佳实践对照

| 实践/标准 | 可借鉴的点 | 落到系统里 |
|---|---|---|
| ISO 9001:2015 7.5 成文信息 | 创建/更新需审批；标识版本；分发、访问、存储、保留、处置受控 | 版本状态、审批记录、访问控制、保留期、审计日志 |
| ISO 10007 配置管理 | 配置标识、变更控制、状态记录、配置审核 | 基线、变更单、版本状态、定期一致性审计 |
| APQC PCF | 统一流程分类与层级，便于跨公司对标 | 集团统一 L1–L3 分类；分公司在 L4/活动层扩展 |
| SCOR | 标准流程、标准指标、标准最佳实践 | 集团统一 KPI 定义与计算口径，分公司只填数据 |
| ABPMP CBOK / BPM 生命周期 | 发现→设计→实施→监控→优化，每阶段有交付物 | 五阶段工作流的步骤契约与交付物清单 |
| ITIL 4 / COBIT | 变更使能、发布管理、治理与问责 | CCB、发布节奏、RACI、审计 |
| PLM 变体管理 | 通用核心 + 变体配置，避免一客一版 | `LOCKED/PARAMETERIZED/EXTENDABLE` 覆盖策略 |
| Git / 配置管理 | 不可变提交、分支、标签、三方合并 | 版本不可变、基线标签、升级差异与变基 |
| 知识管理（ISO 30401） | 知识资产有生命周期、复用与归档 | 模板/案例/最佳实践的版本与复用 lineage |

注意：Git 的分支模型适合模板开发团队，不适合直接暴露给业务人员。
业务界面应呈现为「集团标准 / 本地变体 / 我的交付物」，而不是 branch/merge/rebase。

---

## 六、建议的数据模型

在现有系统上分四组表，不要把所有东西塞进 `attachment`：

```text
组织与范围
  org_unit(id, parent_id, code, name, type, path)

方法资产
  asset_template(id, code, name, type, owner_org_id, current_version_id)
  asset_template_version(id, template_id, version_label, document_id,
                         status, valid_from, valid_to, approved_by)

流程标准与步骤
  process_standard(id, process_code, org_unit_id, parent_standard_id,
                   base_version_id, variant_mode, current_version_id)
  process_standard_version(id, standard_id, version_label, status,
                           valid_from, valid_to, approved_by)
  step_definition(id, standard_version_id, step_no, name, sort_order)
  step_contract(id, step_id, inputs, tools, templates, outputs,
                acceptance_criteria, role, decision_gate)

交付物
  deliverable_definition(id, code, name, type, template_id,
                         required, acceptance_criteria, scope_org_id)
  deliverable_instance(id, definition_id, project_id, process_instance_id,
                       step_id, template_version_id, current_version_id, status)
  deliverable_version(id, instance_id, version_no, file_document_id,
                      status, author_id, reviewer_id, approved_at,
                      checksum, base_version_id, change_request_id)

继承
  override(id, standard_version_id, target_path, override_type,
           value_json, locked, note)
```

文件本身仍走上一份方案里的存储抽象（本地卷 / S3），数据库只存元数据。
`file_document_id` 指向统一的文件对象，避免每个域各造一套上传逻辑。

---

## 七、工具预制模板：让「用工具」变成一键动作

工具（5Why、SIPOC、FMEA、VSM、鱼骨图…）是方法；**模板是方法落到具体交付物的载体**。
同一个工具通常需要多种格式的预制模板，并支持快速调用与复制。

### 7.1 模板库怎么组织

每个模板至少要有：

| 字段 | 说明 |
|---|---|
| `tool_code` | 归属工具，如 `FIVE-WHY`、`SIPOC` |
| `format` | `XLSX` / `DOCX` / `PPTX` / `BPMN` / `ONLINE` / `PDF` |
| `scope_org` | 集团 / 区域 / 分公司 / 部门 |
| `deliverable_definition` | 这个模板产出哪类交付物 |
| `version` / `status` | 版本号、草稿/评审/生效/废弃 |
| `owner` / `review_date` | 模板负责人与复审日期 |
| `placeholders` | 可自动填充的字段及来源 |
| `instructions` / `sample` | 使用说明与填写示例 |
| `is_default` | 同一工具/格式下的默认模板 |

组织方式建议：

```text
工具 → 模板（按格式/场景）→ 模板版本
                  └── 集团标准 / 分公司变体
```

一个工具可以有多个模板（如 FMEA 有 Excel 版和在线表单版），但必须指定一个默认模板，
避免同一个工具出现十几个「最终版」。

### 7.2 四种调用方式，语义要分清

| 模式 | 行为 | 适用场景 |
|---|---|---|
| **下载副本** | 生成文件下载，记录一次使用 | 离线填写、外部协作 |
| **在线填写** | 基于 `FormDefinition` 创建在线交付物实例 | 结构化数据、需要审批 |
| **服务端生成** | 用占位符填充 DOCX/XLSX/PPTX，直接生成交付物实例 | 格式要求高的正式文件 |
| **引用查看** | 只读打开模板，不创建副本 | 学习、对照、评审 |

**「复制」不是把文件另存为。** 复制应创建一个交付物实例，并记录：

```text
source_template_id + source_template_version_id
project_id / process_instance_id / step_id
mode = DOWNLOAD | ONLINE | GENERATE | LINK
created_by, created_at
```

模板升级后，已经复制的实例保持不变；需要升级时走「重新生成/重审」，并保留旧版本。
默认固定当前模板版本，另提供「跟随最新版」选项，但必须显式选择。

### 7.3 占位符与自动填充

统一一套实例上下文，避免每个模板自己问一遍：

```text
group_name, company_name, department, process_name,
project_name, step_name, owner, date,
kpi_baseline, kpi_target, ...
```

模板里声明占位符：

```json
[
  {"key": "project_name", "label": "项目名称", "source": "project.name", "required": true},
  {"key": "owner", "label": "流程 Owner", "source": "process.owner", "required": true},
  {"key": "date", "label": "编制日期", "source": "today", "format": "YYYY-MM-DD"}
]
```

落地方式：

- **Excel**：命名区域/指定单元格；保留公式、数据验证、条件格式与打印区域；
- **Word**：内容控件（content control）或书签；保留样式与页眉页脚；
- **PPT**：占位符/命名形状；保留母版；
- **BPMN**：流程模式参数（如审批层级、SLA），由 bpmn-js 模板生成；
- **在线表单**：直接映射 `FormDefinition` 字段。

生成前校验必填项；生成后记录模板版本、上下文快照与文件 SHA-256。
**不在服务端执行 Office 宏**；`.xlsm` 只做原样复制，不做自动填充。

### 7.4 快速调用的交互

- 工具卡片 →「模板」列表 → 预览、下载、在线使用、复制到当前项目；
- 五阶段步骤页展示「本步骤推荐工具」及其模板，标注「必用 / 推荐 / 可选」；
- 一键带入当前项目上下文，减少重复填写；
- 最近使用、收藏、按阶段/格式/适用范围筛选；
- 复制前显示「将固定模板 v3.2」；模板过期时给出提示；
- 一个步骤需要多个交付物时，支持一次生成清单。

### 7.5 模板版本与集团继承

模板本身就是受控资产，沿用前面的版本与继承规则：

- 模板版本不可变；集团模板的合规区域可设为 `LOCKED`；
- 分公司变体只保存差异，不复制整份模板；
- 集团模板升级时，展示「哪些分公司变体受影响、哪些交付物实例仍固定旧版」；
- 模板有 owner、评审、复审日期、废弃状态，过期模板在调用时提示；
- 监控指标：模板采用率、变体数量、过期模板使用率、复制后未提交率。

### 7.6 建议的数据模型

```text
tool_template
  id, tool_code, code, name, format, scope_org_id,
  deliverable_definition_id, owner_id, is_default, status,
  current_version_id

tool_template_version
  id, template_id, version_label, file_document_id,
  placeholders_json, instructions_document_id, sample_document_id,
  status, valid_from, valid_to, approved_by, base_version_id

template_usage
  id, template_version_id, mode, project_id, process_instance_id,
  step_id, deliverable_instance_id, created_by, created_at
```

文件仍走统一存储层；模板版本只存元数据与文件引用，不把二进制塞进数据库。

### 7.7 反模式

- 每个项目把模板复制一份到自己的文件夹，最后不知道哪份是现行版；
- 同一个工具维护多套互不相关的 Excel，公式和口径不一致；
- 「复制」后直接改模板原件，导致历史交付物被篡改；
- 模板没有 owner 和复审日期，过期多年仍在用；
- 用宏模板自动填充，带来安全与兼容性问题；
- 只提供下载，不记录用了哪个模板版本，审计时无法追溯。

---

## 八、与当前系统的映射

| 当前对象 | 建议演进 |
|---|---|
| `WorkflowTemplate`（24 步） | 增加版本、适用范围、状态；作为集团方法标准的一版 |
| `Tool`（33 个工具） | 增加版本与适用范围；步骤通过引用使用，不复制说明 |
| `ProjectStep` | 增加 `standard_version_id`、交付物实例链接；项目固定标准版本 |
| `ProcessArch`（L1–L4） | 作为集团统一分类骨架；分公司扩展 L4/活动 |
| `KnowledgeItem` | 已批准的交付物可晋升为案例/模板，保留来源与版本 lineage |
| `ProcessInstance.snapshot` | 已固定流程模型；再固定标准版本与模板版本 |
| 规划的 `process_document` | 作为通用文件存储层；交付物域有自己的定义/实例/版本表 |

---

## 九、实施顺序

1. **步骤契约 + 交付物定义/实例/版本**：先让每个步骤的产出可登记、可追溯；
2. **工具预制模板库 + 快速调用**：模板元数据、格式、占位符、下载/在线使用/复制、使用记录；
3. **模板/工具版本化**：模板有版本、状态、审批，交付物记录所用版本；
4. **组织范围 + 覆盖策略**：引入 `org_unit`、`LOCKED/PARAMETERIZED/...`；
5. **有效版本解析 + 差异/升级**：集团升级影响分析、分公司变基；
6. **基线与审计 + 治理看板**：采用率、变体数、覆盖比例、升级延迟、审计发现。

前三步不依赖集团/分公司模型，可以先落地；第四步开始涉及组织主数据，
需要先确认集团的组织编码体系（公司、事业部、工厂、部门）由谁维护。

---

## 十、常见反模式

- **用文件夹和文件名做版本**：无法审计、无法合并、无法知道现行版本。
- **集团模板复制到分公司再改**：必然漂移，最终谁也不敢升级。
- **只版本化文件，不版本化流程标准与步骤契约**：文件有了版本，但不知道按哪版标准产出。
- **所有差异都允许**：变体爆炸，集团失去统一性。
- **所有差异都禁止**：分公司搞影子流程，系统里看不到真实做法。
- **模板升级后自动替换进行中项目的文件**：破坏可追溯性。
- **把 Git 分支模型直接给业务用户**：学习成本高，且业务需要的是生效日期与审批，不是 commit。
