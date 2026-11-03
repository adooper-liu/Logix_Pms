# BPM 产品基本原则与文档契约

> 状态：综合评审基准。沿用用户已明确的产品边界；本文给出跨文档统一契约，不代表新增能力已经实现或获准上线。
> 基线：`4607792`；2026-11-03。实施前须再核对 HEAD；编码授权以 [审定 Brief](bpm-first-batch-brief.md) 为准。  
> **审定清单：** 本文每条契约在 [需求追溯表 §8](bpm-requirements-traceability.md#8-产品基本原则追溯bpm-product-principlesmd)（TR-PR-*）逐节可勾选；§9 所列产物在追溯表 [§0.4](bpm-requirements-traceability.md#04-产物全覆盖登记对齐-产品原则-9bpm-product-principlesmd) 登记。

## 1. 一条基本原则

**以客户与战略价值为目标，以长期存在的流程为主对象；项目只交付一轮改善。各能力域在原业务记录上完成作业与核验，通过明确的版本、样本和验收引用协作，不重复建立状态机、资产库或任务台账。**

客户价值必须与安全、法律、质量、授权和持续运营约束共同满足，不能用效率收益抵消硬约束。战略由有权方决定，系统提供事实、解释和决定依据，不自动替组织证明因果、接受风险或分配个人奖惩。

## 2. 概念边界

| 概念 | 唯一用途 | 禁止混同 |
|---|---|---|
| 企业级治理 | 解码目标、选择组合、配置资源、依据结果复核战略支持 | 项目进度汇总、APQC覆盖率、自动成熟度等级 |
| 长期流程 / process_id | 客户、边界、责任、有效资产、执行及持续监控的主对象 | 项目、一次实例、复制出来的组织目录 |
| 八阶段 | 流程持续管理的导航与活动分类 | 八阶段项目/流程推进状态机 |
| 九知识模块 | 互相提供专业能力和交付依据 | 九个必须依次完成的工作阶段 |
| 五阶段 / Project.current_stage | 一次改善项目的立项到结项，保持1–5 | 八阶段导航、执行实例状态 |
| 薄轮次对照 / round_id | 固定一轮诊断/改善依据、版本、样本和原验收引用 | 第二个项目、全公司的运行阶段、通用资产库 |
| 四种结论 | 同一轮对照的资料就绪、上线就绪、运行有效、改善达标及核验进度 | 四阶段引擎；仅靠记录数量或模型检查推出的业务成功 |
| 十层核对 | 按用途、风险和版本查看适用条件 | 与八/五阶段并列的强制推进机制 |
| 20项保障 | 原章程、RACI、培训、绩效及复盘记录的核验视图 | 自动生成20条平行任务 |
| 方法/工具/实践 | 指导作业、产生可验证产物和解释限制 | 点击或填表即有效；方法数量即进度 |

流程现状先在业务里发生。战略对齐明确客户、目标、责任和管理价值；项目把其中一轮改法做成可验收版本。项目结束后继续运行的是有效流程，不是项目。流程允许没有项目而建模、分析、执行、监控和复盘。

## 3. 保持既有入口

| 导航 | 当前去向 / 本轮约束 |
|---|---|
| 战略对齐 | strategy |
| 流程架构 | pcf / APQC；企业实际目录经现有入口到map |
| 建模、设计 | 同一designer；现状/方案是待实现的用途模式，不声称当前已自动选中相应版本 |
| 分析 | monitor，tab=analysis |
| 执行 | execution |
| 监控度量 | dashboard / 驾驶舱，再下钻monitor |
| 变革优化 | projects / 项目组合，再进入项目五阶段工作台 |
| 贯穿治理 | authorization；相关组织/RACI/文件/发现仍在原模块 |

当前条实际有八个生命周期跳转加治理入口。可把治理视觉上单列，但不编号为第九工作阶段；不得把改路由或增加新模块说成“对齐当前入口”。如确有信息架构改动，须另行明确、评审和验收。

## 4. 证据身份与时间契约

### 4.1 四身份是同轮一致性，不是要求所有引用从第一天齐全

- process_id明确同一公司流程。
- round_id标识固定依据的对照，project_id立项前可空；正式改善验收须绑定对应Project且流程一致。一个项目内的对照修订不能当成另一个项目；下一次独立改善另开项目。
- 模型按角色分别引用现状、方案、上线版本行，改前改后ID不要求相同；样本分别绑定正确一侧，不能以“同流程”混入不同版本。
- metric_contract_key/hash标识冻结口径；前后样本共用口径/可比较范围规则，各自保留实际窗口。

创建草稿可先有部分输入；确认资料/基线须有可追溯现状和口径；上线就绪须有真实已发布模型行；运行/改善判断须有适用的正式样本及批准依据。缺项显示待补，不能为消除缺项而伪造未来版本，也不能因缺上线版本禁止前置分析。

### 4.2 冻结的不是“最新值”

- 先定义分析问题和基线口径，再解释数据；基线结果可以帮助设定合理改善目标。
- 设计比较标准在比较前确定；正式改善目标、红线、观察规则和有权审核者在后侧正式观察前批准锁定。
- 基线快照、设计决定、验收约定按各自确认时点保存，不要求在还没有诊断结论时预测全部目标；不得见到后侧结果再调目标追认通过。
- 已锁定内容不可原位覆盖。补项目、上线版本、验收引用属于有审计的追加动作；改变已批准依据形成新对照修订，旧引用及决定保留。
- 哈希仅验证内容一致，不代替来源可信、业务授权、独立判断或实际效果。

### 4.3 原事实与样本使用分开

业务实例/原日志不因为被多轮分析使用而复制或反复改project_id。新业务可有创建来源round_id；复用旧业务/标准时，在对照中固定原记录ID、版本、角色、来源和纳入规则。已被正式引用的可变数值还需固定当时值/来源摘要，不能只保存一个会被覆盖的ID。

业务关联键只串外部同一笔业务，不替代流程、轮次、模型、口径身份。组织范围通过原组织/授权及批准过滤表达，不复制流程树。

## 5. 权威来源与核验边界

| 内容 | 权威来源与增量原则 |
|---|---|
| 流程、Owner、组织 | 原ProcessArch/组织/任命与授权；不在多页保存独立副本 |
| 模型及当前发布 | 原ProcessModelVersion；当前发布会更新运行模型，不是“仅审批通过” |
| 根因主张/项目阶段门 | 原ProjectEvidenceClaim/GateAttestation；它们当前需要project_id，不能无项目直接调用 |
| 非项目核验 | 在原ToolSheet、流程文件/章程、异常或治理记录中补必要来源/责任/期限/核验；没有覆盖能力时标缺口，不虚构已有通用核验接口 |
| KPI与样本 | 原KpiDefinition/KpiRecord/来源证据；同轮固定口径和样本使用，日常数据保留当时依据 |
| 标准/模板/培训 | 原版本和记录；对照固定所用版本，通用标准不是项目私产 |
| 运行状态 | 当前原执行器；R3接入后按实例归属由单一引擎推进，PMS投影不再算下一步 |
| 派生视图 | 导航/卡片/核验/保障/汇总只读原事实，不产生影子业务决定 |

正式根因、收益、风险等重大决定需有权且适用的独立核验；低风险草稿保存或普通业务处置不机械要求两人签字。具体职责分离按批准政策执行，法定红线不能豁免。方法记录已核验只表示该产物满足约定，不证明方法对所有场景普遍有效。

## 6. 分期边界：R0–R5不等于执行批次

| 范围 | 定位 |
|---|---|
| 第一批开发候选 | 现有路由说明、薄轮次对照、必要原表引用/快照、只读追溯及本轮核验入口；见 [Brief](bpm-first-batch-brief.md) / [开发计划](bpm-first-batch-dev-plan.md)，**审定通过后再编码** |
| 后续专业能力 | 方法直接操作、ABC/CX、方案验证、治理差距、战略组合、保障/复盘等，分别以原对象扩展，逐项验证 |
| R3引擎接入 | 已采纳Flowable方向；部署/定义映射、可靠命令/事件、并行活动与恢复在接入计划中确定 |
| 未批准结构 | 独立发布包/执行范围/方案库/基线库/指标修订库/验收计划库/控制计划库等，不因文档提过就自动纳入实施 |

“第一批只新增一张薄表”是最小业务增量边界，不是永远禁止必要基础设施，也不是把所有未来需求塞进一个无限JSON对象。后续若原结构不能安全承载，应另证必要性、定义权威来源、迁移和验收，而非先建空表。

R0–R5是改造工作分组及优先方向，不是产品状态机，也不是所有后续工作必须串行依赖Flowable。现有运行数据可先支撑基础异常/改善/效果核验；真正依赖并行事件的分析须等相应事件能力。安全/数据准确性问题可先独立修，不能为等路线完成而延后。

## 7. 模块闭环与共同交接

共同作业契约：**目的/客户结果—输入与版本—动作及适用方法—产物引用—责任/期限—评价依据—核验/接收—下一步与反馈。** M/A/D/P/T/G/E编号只解释工作，不新增推进表。

建模核验技术表达及用途；分析核验事实/原因；设计核验改善机制/风险/可实施性；绩效核验数据/响应/效果；转型核验路径/采用/持续成果；技术核验交换/能力/可靠性；组织核验权责/资源/协调；企业管理复核战略支持。理论和工具服务这些交付，不取代证据。

九知识域不是九个互斥业务模块，小闭环可并行和往返，原产物由相关域引用；同一客户结果不在多个域重复记收益。作业接收≠发布资格≠实际运行有效≠改善达标≠战略因果证明。

## 8. 现状、建议与验证的写法

每份文档标明：代码事实（有文件依据）、已确认原则、待评审方案、实施/验收证据。不得用“已生成文档、链接无错”证明设计可实施或产品已闭环；不得把教程、模板、注册和HTTP成功等同实际算法/执行/业务效果。

BPMN标准、企业风格、业务真实性、引擎/分析支持分域；完整XML字段存在不保证无损。可选APQC的政策与现有强制门禁差异必须作为显式改造，不谎称现状已支持。讲义历史归属、考试分级、统计目标和未解析规范不当成已核官方要求。

能力统一写成独立属性：**参考说明、可填写、直接办理、可计算、外部核验、已验证集成**。属性不是成熟度阶梯；可填写不必可计算，集成成功也不证明业务正确。具体支持范围/版本/限制与验证证据一起展示。

## 9. 产物分工与阅读顺序

| 产物 | 唯一职责 | 追溯表 |
|---|---|---|
| **本文** | 产品语义、证据与分期契约；修改需明确改变哪条原则 | [§8 TR-PR-*](bpm-requirements-traceability.md#8-产品基本原则追溯bpm-product-principlesmd) |
| [总路线](bpm-lifecycle-gap-and-roadmap.md) | 差距和 R0–R5 分组；非 API 清单 | [§1](bpm-requirements-traceability.md#1-路线文档追溯gap-and-roadmap) |
| [落地规格](bpm-lifecycle-implementation-spec.md) | 对象、第一批边界、模块落点 | [§2–§3](bpm-requirements-traceability.md#2-落地规格追溯--总契约13) |
| [文案规范](bpm-interface-content-standard.md) | 产品语言、页面结构、术语、反馈的唯一表达规则 | [§4、§6](bpm-requirements-traceability.md#4-文案规范追溯interface-content-standard) |
| [文字清单](product-language-inventory.md) | 当前差异、重点字段和字典来源；不是全量已实施目录 | DOC-IA；实施前补对应消费点 |
| [页面职责表](page-responsibility-and-decomposition.md) | 23入口、主题边界、兼容和语言/页面S1–S5 | DOC-IA；不等于BPM B1切片 |
| [全量评审任务书](document-review-handoff.md) | 核心16份与配套30份的阅读、证据、brief和终审要求 | 与第一批审定交接不同范围，不互相替代 |
| [独立评审brief](reviews/document-review-brief.md)及[附录](reviews/document-review-findings.md) | 固定6ba817f的评审发现；实际覆盖深度以矩阵为准 | 不据“完成”字样自动视为满足全量任务书 |
| [原助手终审](reviews/document-review-final.md) | DR逐条核证、当前计划差异、修订及未关闭项 | 终审不是编码或业务验收授权 |
| 八份专项 | 见 §9.1；不重定义对象和阶段 | [§11.1–§11.8](bpm-requirements-traceability.md#11-八份专项追溯原则-91) |
| [README](../README.md) | 代码定位与运行；不宣传未实现 | [§10](bpm-requirements-traceability.md#10-readme-追溯readmemd) |
| [综合评审记录](bpm-artifacts-review.md) | 错位修正、未决决定；非新需求源 | [§9](bpm-requirements-traceability.md#9-综合评审记录追溯bpm-artifacts-reviewmd) |
| [主任务实施brief](implementation-next-brief.md) | 三类型/八阶段/治理主体能力的承接矩阵与逐片进度 | 语言页面配套，不被局部修复替代 |
| [三类型分类计划](superpowers/plans/2026-11-03-process-classification.md) | 主线M1a：分类正式维护、继承/例外/未知、查询与原页面消费 | 对应R1-01，不等于八阶段全完成 |
| [工具保存详细计划](superpowers/plans/2026-11-03-tool-sheet-save-integrity.md) | 暂停保留的局部修复与历史验证记录 | 不再作为主线实施优先级 |
| [第一批 Brief](bpm-first-batch-brief.md) | B1总体范围背景与未定依赖 | [§12 TR-META-BRF](bpm-requirements-traceability.md#12-审定与实施包meta) |
| [第一批开发计划](bpm-first-batch-dev-plan.md) | 切片/API/DoD | [§12 TR-META-PLN](bpm-requirements-traceability.md#12-审定与实施包meta) |
| [审定交接说明](bpm-review-handoff.md) | 审定顺序与结论模板 | [§12 TR-META-HOF](bpm-requirements-traceability.md#12-审定与实施包meta) |
| [R1 可实施性复审](bpm-r1-implementability-review.md) | R1 vs 代码 | [§12 TR-META-R1](bpm-requirements-traceability.md#12-审定与实施包meta) |
| [需求追溯表](bpm-requirements-traceability.md) | **审定主清单**（含本文 §1–§9 逐节） | [§0.4 登记](bpm-requirements-traceability.md#04-产物全覆盖登记对齐-产品原则-9bpm-product-principlesmd) |

### 9.1 八份专项（与追溯表 §11 一一对应）

| 专项 | 文件 |
|---|---|
| 建模 | [process-modeling-repository-gap.md](process-modeling-repository-gap.md) |
| 分析 | [process-analysis-method-chain.md](process-analysis-method-chain.md) |
| 设计 | [process-design-small-loop.md](process-design-small-loop.md) |
| 绩效 | [process-performance-decision-loop.md](process-performance-decision-loop.md) |
| 转型 | [process-transformation-practice-system.md](process-transformation-practice-system.md) |
| 技术 | [bpm-technology-open-contracts.md](bpm-technology-open-contracts.md) |
| 组织 | [process-organization-governance-loop.md](process-organization-governance-loop.md) |
| 企业 | [enterprise-process-strategy-loop.md](enterprise-process-strategy-loop.md) |

历史工程文档（如 `process-execution-gap-analysis.md` 等）不是本次 BPM 闭环改造规范；使用时核基线。新评审发现冲突须改正文和相关引用，不能只继续追加免责声明。

## 10. 本文条款与追溯 ID（供审定勾选）

| 本文位置 | 追溯 ID | 要点 |
|---|---|---|
| §1 基本原则 | TR-PR-01 | 流程主对象；一轮改善；原记录协作 |
| §2 概念表（10 行） | TR-PR-02-01～10 | 各概念「唯一用途 / 禁止混同」 |
| §3 导航表（8 行） | TR-PR-03-01～08 | 保留既有去向；治理不编第九阶段 |
| §4.1 四身份 | TR-PR-04-01～05 | 草稿可部分；缺项不伪造 |
| §4.2 冻结 | TR-PR-04-06～10 | 不可原位覆盖；修订留痕 |
| §4.3 样本 | TR-PR-04-11～12 | 不复制实例；关联键≠四身份 |
| §5 权威表（8 行） | TR-PR-05-01～08 | publish/Gate/KPI/派生视图 |
| §5 段末核验 | TR-PR-05-09 | SoD；方法已核验≠普遍有效 |
| §6 分期 | TR-PR-06 | R0–R5≠批次；审定后编码 |
| §7 模块闭环 | TR-PR-07 | 九域非串行；接收≠达标 |
| §8 写法与能力属性 | TR-PR-08 | 四类信息；六属性非阶梯 |
| §9 产物分工 | TR-PR-09 | 下游文档唯一职责；追溯表主清单 |

完整 disposition（PRIN / B1 / LATER / DOC-IA）见追溯表 [§8 明细](bpm-requirements-traceability.md#81-节级明细tr-pr--)。
