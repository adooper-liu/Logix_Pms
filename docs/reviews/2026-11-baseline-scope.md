# 2026-11 基线评审 · 实例附件

> 本附件保留当轮实例清单，按v2.1更正来源与覆盖状态。模板不含当轮计数；本附件数字固定其声明的提交。
> 生成时间 2026-11-03。**用途有二**：(a) 本轮（v1 任务书下完成的）评审的修订验证与增量复审基线；(b) 下一轮全量评审的范围起点——届时必须先重新跑一遍清单命令核对本附件是否已腐化。

## 1. 基线

| 项 | 值 |
|---|---|
| 固定提交 | `340e91e`（docs: 第一批范围基线、可追溯包与独立综合评审产出） |
| 上一提交 | `6ba817f`（PR #13 合并，本轮 v1 评审的实际基线） |
| 分支 | `main`，与 `origin/main` 一致 |
| 工作区 | 未跟踪：`cbpp-prep-main/`（无关项目，非评审对象）；stash@{0}/@{1}（回滚的旧代码实验，非基线） |

基线命令输出（2026-11-03 实测）：

- `git ls-files '*.md'`：**57 份**（docs/ 54 + 根 README.md + CLAUDE.md + web/vendor/bpmn-js/README.md）
- v1的“docs共46份”对应6ba817f当时范围；340e91e的docs为54份，新增8份。同口径为46→54，不是46→57；57包含根目录和第三方3份Markdown。
- 本附件清单固定340e91e，不含bedba23新增的本附件自身。此后的未提交修订/计划不属于原57份基线，不能为保持数字不变而漏报新增资料。

## 2. 范围清单与风险分级

深度定义与时间盒见模板 §3.3。审查重点为方向提示，不构成免检项。

### Tier A（深读 + 源码定向核证，9 份）

| 文件 | 审查重点 |
|---|---|
| `README.md` | 当前能力、双路径启动、环境/演示/生产边界、未来能力是否误称已实现 |
| `docs/bpm-product-principles.md` | 长期流程、改善项目、证据身份、原对象复用与分期约束（约束基线本身） |
| `docs/bpm-lifecycle-gap-and-roadmap.md` | 差距是否仍真实、R0–R5 分组、业务链与依赖方向 |
| `docs/bpm-lifecycle-implementation-spec.md` | 薄轮次、冻结/追加、原记录引用、第一批边界、权限与验收 |
| `docs/bpm-interface-content-standard.md` | 术语/字段/状态/动作/错误/提示唯一来源；现有与未来分开 |
| `docs/page-responsibility-and-decomposition.md` | 23 入口、单主题与组件边界、路由兼容、S1–S5 |
| `docs/bpm-first-batch-brief.md` | 第一批范围/非目标、七项待锁定技术与业务决定；不是用户逐项批准的证据 |
| `docs/bpm-first-batch-dev-plan.md` | 开发切片顺序与验收是否足以实施、与规格落点一致 |
| `docs/bpm-requirements-traceability.md` | 追溯是否真实覆盖、编号是否稳定、有无追溯造假 |

### Tier B（全文，18 份）

| 文件 | 审查重点 |
|---|---|
| `CLAUDE.md` | 工程约束（评审依据）；同时按模板附录 A 开采为缺陷检查单 |
| `docs/document-review-handoff.md` | 任务书自身：流程可执行性、有无让作者自证（本轮已按元规则审过一次，见 §5） |
| `docs/bpm-artifacts-review.md` | 历史修正是否落实；旧验证限制是否被错当当前结论 |
| `docs/process-modeling-repository-gap.md` | 规范/真实业务/算法/引擎分域、模型版本与交换保真 |
| `docs/process-analysis-method-chain.md` | 问题→事实→基线→原因验证→交付接收；无项目场景与未知边界 |
| `docs/process-design-small-loop.md` | 根因到措施、方案比较、风险控制、验证；接收≠上线 |
| `docs/process-performance-decision-loop.md` | 口径/来源/样本/窗口/质量/判断/行动/效果验证 |
| `docs/process-transformation-practice-system.md` | 纵深/融合/组织采用；不用清单计数证明成熟 |
| `docs/bpm-technology-open-contracts.md` | 输出/接入/调用/替换、引擎边界、可靠交互、安全与退出 |
| `docs/process-organization-governance-loop.md` | 任命/授权/资源/职责/冲突；制度≠落实 |
| `docs/enterprise-process-strategy-loop.md` | 战略解码、组合、结果回战略、贡献/因果、HR 边界 |
| `docs/product-language-inventory.md` | 26 项差异、16 组字段、12 组字典来源的准确性（抽样核） |
| `docs/bpm-r1-implementability-review.md` | R1-01～05 可实施性结论是否仍成立 |
| `docs/bpm-review-handoff.md` | 审定交接流程与 v2 模板的关系（合并或退役候选） |
| `docs/integration.md` | HMAC/入站/Outbox/worker 实际支持与可靠性限制 |
| `docs/metrics.md` | 公式、单位、分母、串行/返工模型、实际取数范围 |
| `docs/frontend-architecture.md` | 原生 ES 模块、actions、依赖方向、当前实现与拆分契约 |
| `docs/usage-guide.md` | 实际可办理功能、权限、帮助一致性（面向用户的"现行"主张） |

### Tier C（浏览分类 + 冲突升级，30 份）

`apqc-ten-elements-gap-analysis`、`attachment-editing-and-distribution`、`bpmn-editor-and-attachments`、`bpmn-js-best-practices`、`bpmn-js-spike`、`bpmn-p2-project`、`execution-p2-project`、`framework-gap-analysis`、`framework-p2-project`、`help/README`、`information-architecture`、`inventory/README`、`knowledge-scenario-upgrade-plan`、`navigation-map`、`pcf-chinese-translation`、`process-deliverable-versioning`、`process-execution-gap-analysis`、`process-management-best-practices`、`resume-capability-map`、`resume`、`reviews/document-review-brief`、`reviews/document-review-findings`、`sketches`、`startup-evidence-example`、`startup-path`、`three-layers-and-page-dependencies`、`toolbox-problem-driven-plan`、`training-zero-to-one`、`ui-information-architecture`、`web/vendor/bpmn-js/README`（第三方旁证，非产品规范）。

重点规则：历史 P2 项目文档（framework/execution/bpmn-p2）只判"是否误导现行实施"，不恢复历史需求；`resume*` 只审主张与证据关系；`reviews/*` 是上轮评审输出，**视为待证主张，禁止继承其结论**（防锚定）。

## 3. 当轮边界约束清单（带来源标注）

模板 §3.4：未标来源的条目无约束力。本轮沿 v1 §4.2 逐条补标：

| # | 边界 | 来源 | 状态/本轮证据 |
|---|---|---|---|
| B1 | 长期流程是主对象；改善项目只交付一轮；普通建模/分析/监控不强迫立项 | **作者设计立场**（principles/spec）；用户决定出处未在本附件提供 | 保留为计划设计前提，不据brief七项待锁定决定冒称用户逐项批准 |
| B2 | 八阶段导航/九知识域/五阶段交付/十层核对，四套不互相套用 | **作者设计立场**（principles）；用户决定出处待补 | DR-003指向技术强迫代码差距；本轮未完成正式仲裁，不标问题关闭 |
| B3 | 治理体系项目当前只有框架边界证据；历史九阶段不得复活 | **代码事实**（setup_program.py:19–27仅1阶段）＋**作者建议**（避免恢复历史叙事） | 治理发现归属是另一条页面设计，不作为本条用户决定来源 |
| B4 | 薄轮次对照四要素（同流程/同轮/前后版本/冻结口径与样本） | **作者设计立场**（spec）；brief §4列的是待锁定决定 | round未实现属正常差距；具体冻结/幂等/样本/授权等仍按七项决定定值 |
| B5 | 前后模型ID可不同；正式引用可变KPI保留当时值/来源 | **作者设计立场**（spec） | 保留方案依据；未挑战不等于用户批准 |
| B6 | 资料就绪/上线就绪/运行有效/改善达标是同轮核验结论非四阶段 | **作者设计立场**（spec） | 原DR-011是演示账号提示，非本条反证；语言/页面S1–S5与BPM B1切片分别登记 |
| B7 | publish更新原运行模型/指针；Flowable方向未接入；引擎归属单一 | **代码事实**（process_model.py:457–477）＋**作者方案**（Flowable/归属）；用户采纳记录未在此提供 | 代码事实与未来方向分别看待，不由发布指针源码证明供应商选择获批 |
| B8 | GateAttestation/ProjectEvidenceClaim受项目上下文约束，不虚构通用核验器 | **代码事实**＋**作者约束** | DR-002自动效果申报是独立问题，不是项目专属核验器的直接实例 |
| B9 | APQC为参照；讲义/政策/标准/算法分别举证 | **作者设计立场**（principles） | 不冒称已核官方原文 |
| B10 | 20项保障核原记录，不自动造平行任务 | **作者设计立场**（principles） | 没有实现验收或业务批准证据 |
| B11 | 一概念一权威源，不建平行模型/项目/指标/审批实现 | **工程约束**（CLAUDE纪律4）＋**作者设计取舍**（principles） | 工程约束可直接引用；DR-001是指标来源误推，不简单归因为双实现，DR-006有标签多源证据 |

**关联索引不是裁决证据**：DR-001为指标来源/回写风险，DR-002为填表自动效果申报，DR-003为适用性差距，DR-004～007为语言/错误整治；DR-010原风险已因目标文件在340e91e入库而失去当前前提，不据此说原评审把未提交文件混入已合并基线。

## 4. 场景走查清单（沿用 v1 §5.1，逐条标注本轮覆盖）

以下只记录原报告声称的场景范围，**缺逐步证据，不认定已完成走查**。用户已要求结束本轮评审，未完成部分作为限制保留，不继续启动新评审，也不伪补观察。

| 场景 | 当前可定位材料 | 状态 |
|---|---|---|
| 无项目建模→分析→监控 | 原附录E仅简列对象链，没有逐权限/输入/失败观察 | 未充分举证 |
| 改善基线→验收→结项后运营 | 原附录E指出round缺实现，不能由此证明所有设计契约自洽 | 未充分举证 |
| 未达标/口径/模型/人员变化 | 原附录E关联DR-001，未覆盖其余分支 | 部分定位，未完成 |
| 当前发布与未来引擎 | process_model.py:457/476支持当前发布副作用，DR-015说明未来未接入 | 局部源码事实，非全链走查 |
| 模板→交付物→晋升→资产引用 | 原附录E无逐版本/审批/旧引用记录 | 未充分举证 |
| 单主题导航/草稿/竞态/写入未知 | DR-005/007只能支持部分标题/错误代码观察 | 未充分举证，未浏览器验收 |
| 治理类型与系统/业务角色 | setup阶段源码可定位；原DR-013是未排除发现 | 局部事实，未完成全场景 |

## 5. 源码核对路径（定向，非全仓审计）

- 数据身份：`app/models/{process,project,execution,monitor,deliverable,tool_template,governance}.py` + schemas + Alembic 迁移；
- 业务语义：`app/services/{project_workflow,setup_program,process_model,execution,kpi,simulation,process_mining,deliverable,process_document,governance,pilot}.py`；
- 权限：`app/api/deps.py` 及 org_scope/org_access/ownership 实际存在的模块（先确认存在，不凭名字猜）；
- 运行集成：`app/services/{integrations,inbound}.py`、`scripts/worker.py`、Compose；
- 前端：`web/js/main.js`、`core/{state,router,api,format,cockpit}.js`、`views/shared/tool_sheet.js`、相关 views、`app/seed`；
- 工程约束：后端枚举中文、UTC/纯日期、Alembic、alembic.ini ASCII、零构建、依赖单向。

## 6. 本轮评审状态索引（供增量复审核对）

- v1历史报告仍保留原结论“修订后可进入开发计划细化”，不冒充按v2门禁重新通过。
- v2改写的是规则文本，未证明原DR已仲裁/关闭；本附件现已纠正来源、覆盖与编号错误，也不表示业务代码风险已修复。
- **用户已结束本轮评审并要求修正、进入下一步计划与brief。** 因此不再安排补全量/仲裁循环；未读范围和未完成验证作为限制归档。具体业务决定及实施完成仍不能追认。
- 当前主线见[实施brief](../implementation-next-brief.md)：三类型/八阶段/治理主体能力逐片落地，首片M1a分类。此前自动效果申报修复暂停保留，不再作为主线优先项。计划与代码实际状态分别记录，不追认为已完成。
