# 2026-11 基线评审 · 实例附件

> 本附件是 `docs/document-review-handoff.md` v2 第 3 节要求的**当轮实例数据**。模板不含数字，数字全在这里。
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
- v1 任务书称"docs 共 46 份"——**已腐化，以本附件清单为准**。

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
| `docs/bpm-first-batch-brief.md` | 第一批范围/非目标、七项决定原文（用户既定约束的权威出处） |
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
| B1 | 长期流程是主对象；改善项目只交付一轮；普通建模/分析/监控不强迫立项 | **用户既定**（first-batch brief 七项决定） | 有效 |
| B2 | 八阶段导航/九知识域/五阶段交付/十层核对，四套不互相套用 | **用户既定** | 有效；但 DR-003 证实代码违背十层"适用性核对"定位（`pilot.py` 强制 RPA/案例/技术），属代码-约束差距，待用户裁决 breaking change |
| B3 | 治理体系项目当前只有框架边界证据；历史九阶段不得复活 | **代码事实**（`setup_program.py:19-27` 仅 1 阶段）+ **用户既定**（治理发现归属为审定候选） | 有效 |
| B4 | 薄轮次对照四要素（同流程/同轮/前后版本/冻结口径与样本） | **用户既定**（brief 七项决定 + spec） | 有效；round 表未实现属正常差距（DR-014） |
| B5 | 前后模型 ID 可不同；正式引用可变 KPI 必须保留当时值/来源 | **作者设计立场**（spec） | 评审者未挑战；下一轮可挑战 |
| B6 | 资料就绪/上线就绪/运行有效/改善达标是同轮核验结论非四阶段 | **作者设计立场**（spec） | DR-011 相关误读已澄清；S1–S5 是文档修订顺序非上线门禁 |
| B7 | publish 更新原运行模型与指针；Flowable 已采纳未接入；引擎归属单一 | **代码事实**（`process_model.py:457-477`）+ **用户既定**（Flowable 方向） | 有效；DR-015 确认文档与代码一致 |
| B8 | GateAttestation/ProjectEvidenceClaim 受项目上下文约束，不虚构通用核验器 | **代码事实** | 有效；DR-002 的工具自动 EFFECTIVE 恰是此问题的实例 |
| B9 | APQC 是参照非唯一目录；讲义数字/政策/标准/算法分别举证 | **作者设计立场**（principles） | 有效 |
| B10 | 20 项保障是核验要求，不自动生成 20 条平行任务 | **作者设计立场**（principles） | 有效 |
| B11 | 一概念一权威源，不建第二模型库/项目引擎/指标算法/审批台账 | **用户既定**（principles + CLAUDE.md 纪律 4） | 有效；DR-001（KPI 推断回写）与 DR-006（枚举多源）是违反实例 |

**与本轮发现的张力索引**：DR-001↔B11、DR-002↔B8、DR-003↔B2、DR-004~007↔语言规范（用户既定）、DR-010↔流程（未提交内容混入基线的风险已实际发生并已由提交 `340e91e` 消解）。

## 4. 场景走查清单（沿用 v1 §5.1，逐条标注本轮覆盖）

1. 无项目长期流程建模→分析→监控（不得强造项目门禁）— 已走查，DR-001/002 暴露工具上下文问题；
2. 改善基线→立项→发布→样本→独立验收→结项后运营 — 已走查，规格自洽，代码差距为正常差距；
3. 未达标/无样本/口径变化/混合样本/人员变更 — 已走查；
4. 当前发布与未来 Flowable 各一条链 — 已走查（DR-015 排除）；
5. 交付物模板→版本审批→晋升标准→资产引用→旧引用保持 — 已走查；
6. 驾驶舱/流程卡→单主题→换上下文→刷新/后退→脏表单→旧请求晚到→写入未知 — 已走查（DR-007 相关）；
7. 治理项目框架证据 vs 改善五阶段；系统角色 vs 治理任命 — 已走查（DR-013 排除）。

## 5. 源码核对路径（定向，非全仓审计）

- 数据身份：`app/models/{process,project,execution,monitor,deliverable,tool_template,governance}.py` + schemas + Alembic 迁移；
- 业务语义：`app/services/{project_workflow,setup_program,process_model,execution,kpi,simulation,process_mining,deliverable,process_document,governance,pilot}.py`；
- 权限：`app/api/deps.py` 及 org_scope/org_access/ownership 实际存在的模块（先确认存在，不凭名字猜）；
- 运行集成：`app/services/{integrations,inbound}.py`、`scripts/worker.py`、Compose；
- 前端：`web/js/main.js`、`core/{state,router,api,format,cockpit}.js`、`views/shared/tool_sheet.js`、相关 views、`app/seed`；
- 工程约束：后端枚举中文、UTC/纯日期、Alembic、alembic.ini ASCII、零构建、依赖单向。

## 6. 本轮评审状态索引（供增量复审核对）

- v1 任务书下完成的评审产出：`docs/reviews/document-review-brief.md` + `document-review-findings.md`（结论：修订后可进入开发计划细化；DR-001~016）。
- 任务书自身批判与 v2 重写：2026-11-03（批判要点见 v2 变更日志；结构性缺陷：作者终审悖论、约束无来源标注、模板/实例混写）。
- **待办（按 v2 生命周期）**：作者答辩 → 用户仲裁 DR-001~016 → 修订 → 修订验证 + 增量复审（本附件 §2–§4 即复审范围）→ 关闭报告。
- 增量复审触发点：`340e91e` 之后的任何修订提交；下一轮全量评审触发条件：基线文档结构重大变化、新增文档 >5 份、或距本轮超过 3 个月。
