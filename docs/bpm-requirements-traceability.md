# BPM 需求追溯表（路线 → 规格 → 文案 → 处置）

> **状态：** 供审定模型逐条勾选；**不是**实施授权。  
> **代码基线：** `4607792`（`git pull origin main` 已核对：与远程一致）。  
> **关联：** [Brief](bpm-first-batch-brief.md) · [开发计划](bpm-first-batch-dev-plan.md) · [审定交接](bpm-review-handoff.md) · [文案规范](bpm-interface-content-standard.md)

## 0. 如何使用本表

### 0.1 评审顺序（与 Brief 生成顺序对齐）

| 步 | 文档 | 本表章节 | 产出 |
|---|---|---|---|
| 1 | [bpm-lifecycle-gap-and-roadmap.md](bpm-lifecycle-gap-and-roadmap.md) | **§1** | 差距与 R 分组是否被第一批/Brief 正确裁剪 |
| 2 | [bpm-lifecycle-implementation-spec.md](bpm-lifecycle-implementation-spec.md) | **§2–§3** | 每条 R0–R5 / 契约是否有 disposition |
| 3 | [bpm-interface-content-standard.md](bpm-interface-content-standard.md) | **§4** | 表达与页面规则是否映射到 IA/语言轨 |
| 4 | 综合 | **§5–§6** | 七项技术决定 + 产品语言/页面职责（非同义词表） |
| 5 | [bpm-product-principles.md](bpm-product-principles.md) | **§8** | 原则 §1–§9 是否被下游违反 |
| 6 | [bpm-artifacts-review.md](bpm-artifacts-review.md) | **§9** | C01–C17 与 §4 七项决定 |
| 7 | 八份专项 + README | **§10–§11** | 专项作业深度不 creep 进 B1 |
| 8 | Brief / 开发计划 / 交接 / R1 复审 | **§12** | 实施包与追溯表一致 |
| 9 | 交叉 | **§0.4、§13** | 产物登记 + 汇总勾选 |

**说明：** [Brief](bpm-first-batch-brief.md) 仅是 **B1\*** 子集摘要。**原则 §9 所列每一文件**均须在 **§0.4** 登记，并在对应 §1–§12 有至少一条 TR-ID；不得因 Brief 存在视为全文已评审。

### 0.2 Disposition 图例

| 代码 | 含义 |
|---|---|
| **B1-S1…S6** | 第一批开发计划切片 1–6（见 [dev-plan](bpm-first-batch-dev-plan.md)） |
| **B1-min** | 第一批只交付子集（文档/只读/API 字段），全量在 LATER |
| **LATER** | 后续批次或专项，不阻塞第一批演示链 |
| **DOC-IA** | 产品语言 / 信息架构轨（见 §6）；可与 B1 并行但**不单做词语替换** |
| **PRIN** | 已由 [产品原则](bpm-product-principles.md) 约束，本表不重复开实施项 |
| **N/A** | 纯背景/示例，不要求实现 |

### 0.3 审定列（由审定模型填写）

每条可选：`[ ] 已核对` `[ ] 与 Brief 一致` `[ ] 需改文档` `[ ] 阻塞编码`

### 0.4 产物全覆盖登记（对齐 [产品原则 §9](bpm-product-principles.md)）

| 产物 | 追溯章节 | 评审深度 | 审定 `[ ] 文件已覆盖` |
|---|---|---|---|
| [bpm-product-principles.md](bpm-product-principles.md) | §8（TR-PR-*） | 原则 §1–§10 逐节；§9 产物表含回溯列 | |
| [bpm-lifecycle-gap-and-roadmap.md](bpm-lifecycle-gap-and-roadmap.md) | §1 | TR-RM-01～22 | |
| [bpm-lifecycle-implementation-spec.md](bpm-lifecycle-implementation-spec.md) | §2–§3 | TR-SP + TR-R0～R5 | |
| [bpm-interface-content-standard.md](bpm-interface-content-standard.md) | §4、§6 | TR-UX + TR-IA | |
| [product-language-inventory.md](product-language-inventory.md) | §6 | 重点差异/字段/字典；非全量已实施目录 | |
| [page-responsibility-and-decomposition.md](page-responsibility-and-decomposition.md) | §6 | 23入口及S1–S5候选，不等于B1切片 | |
| [document-review-handoff.md](document-review-handoff.md) | 终审输入 | 全量文档评审范围，不受B1子集裁剪 | |
| [独立评审brief](reviews/document-review-brief.md) / [附录](reviews/document-review-findings.md) / [终审](reviews/document-review-final.md) | 终审输入/裁决 | 实际覆盖与未关闭项分开 | |
| [process-modeling-repository-gap.md](process-modeling-repository-gap.md) | §11.1 | TR-SPC-MDL-* | |
| [process-analysis-method-chain.md](process-analysis-method-chain.md) | §11.2 | TR-SPC-ANA-* | |
| [process-design-small-loop.md](process-design-small-loop.md) | §11.3 | TR-SPC-DES-* | |
| [process-performance-decision-loop.md](process-performance-decision-loop.md) | §11.4 | TR-SPC-PRF-* | |
| [process-transformation-practice-system.md](process-transformation-practice-system.md) | §11.5 | TR-SPC-TRN-* | |
| [bpm-technology-open-contracts.md](bpm-technology-open-contracts.md) | §11.6 | TR-SPC-TEC-* | |
| [process-organization-governance-loop.md](process-organization-governance-loop.md) | §11.7 | TR-SPC-ORG-* | |
| [enterprise-process-strategy-loop.md](enterprise-process-strategy-loop.md) | §11.8 | TR-SPC-ENT-* | |
| [README.md](../README.md) | §10 | TR-README-* | |
| [bpm-artifacts-review.md](bpm-artifacts-review.md) | §9 | TR-AR-* | |
| [bpm-first-batch-brief.md](bpm-first-batch-brief.md) | §12 | TR-META-BRF | |
| [bpm-first-batch-dev-plan.md](bpm-first-batch-dev-plan.md) | §12 | TR-META-PLN | |
| [bpm-review-handoff.md](bpm-review-handoff.md) | §12 | TR-META-HOF | |
| [bpm-r1-implementability-review.md](bpm-r1-implementability-review.md) | §12 | TR-META-R1 | |
| 本文 | §12 | TR-META-TRC | |

**B1实施范围外不等于综合评审范围外。** `process-execution-gap-analysis.md`、`usage-guide.md`等历史/工程资料可以不产生B1实施项，但仍属[全量评审任务书](document-review-handoff.md)要求的审读/分类范围；实际错误若影响当前安全或业务判断仍单独立项，不因OUT-OF-SCOPE标签消失。

---

## 1. 路线文档追溯（gap-and-roadmap）

| ID | 来源（节） | 要求摘要 | Disposition | Brief/计划锚点 | 基线代码/note |
|---|---|---|---|---|---|
| TR-RM-01 | §1 结论 | 跨阶段证据链是主缺口 | PRIN | Brief §1 | 静态差距陈述 |
| TR-RM-02 | §2 五套概念 | 八阶段导航≠状态机；五阶段 1–5 | PRIN | 原则 §2 | `project_workflow.py` |
| TR-RM-03 | §3 三类流程 | 正式主数据 + 排序依据 | LATER | 非目标 R1-01 | `ProcessArch` 无类型字段 |
| TR-RM-04 | §4 八阶段矩阵 | 能力对照与缺口 | DOC-IA | handoff 背景 | 未逐页验收 |
| TR-RM-05 | §5 五项成功条件 | 系统载体 vs 组织行为 | LATER | R1-05 视图 | 20 项无集中 API |
| TR-RM-06 | §6.1 技术强迫 | 十层第 6 层 RPA/tech 非全员强制 | **B1-S3** | dev-plan §6 | `pilot.py` 计数门禁 |
| TR-RM-07 | §6.2 版本/轮次 | 合格计数须绑 round+版本 | **B1-S1,S3,S4** | Brief 目标链 | `process_evidence` |
| TR-RM-08 | §6.3 KPI 单位 | 显式来源，禁止时长单位推断 | **B1-S2a** | dev-plan §5.1 | `kpi.py` |
| TR-RM-09 | §6.4 结项≠有效 | 独立验收与收益裁决 | **B1-S3,S4** | 四结论「改善达标」 | 项目字段≠达标 |
| TR-RM-10 | §7 业务路径表 | 八阶段试点叙事（示例） | N/A | 演示脚本参考 | 业务确认 |
| TR-RM-11 | §7.1 四身份 | 薄轮次对照 + 四引用 | **B1-S1** | dev-plan §4 | 未实现 round 表 |
| TR-RM-12 | §7.1 部署 ID | 当前=已发布模型行，非 Flowable | PRIN | 文案 §3 术语 | `publish()` |
| TR-RM-13 | §7.2 指标约定 | 业务批准窗口，文档不写死 KPI | **TR-DEC-7** | Brief §2 表 #7 | — |
| TR-RM-14 | §8 R0  bullets | 八入口+方法融合+四结论动态 | B1-min + DOC-IA | R0-01；Slice 4 UI | `tool_lifecycle` 部分 |
| TR-RM-15 | §8 R1  bullets | 主数据+适用性+保障清单 | LATER + **B1-S3** | R1-01/05 vs 04 | 见 R1 复审 |
| TR-RM-16 | §8 R2  bullets | 基线+显式 KPI | **B1-S1,S2** | Slice 1–2 | — |
| TR-RM-17 | §8 R3  bullets | Flowable 全套 | LATER | 非目标 | 无运行时 |
| TR-RM-18 | §8 R4  bullets | 事件驱动异常闭合 | LATER（部分 **B1-S6**） | 异常 round | 无 Flowable 事件 |
| TR-RM-19 | §8 R5  bullets | 收益/复制/绩效 | LATER + **B1-S4** | R5-01 投影 | — |
| TR-RM-20 | §8 段末 | R0–R5≠执行批次 | PRIN | 原则 §6 | — |
| TR-RM-21 | §9 八条最终验收 | 闭环验收契约 | LATER | DoD 演示子集 | 非当前声称通过 |
| TR-RM-22 | §10 边界 | 路线≠实施授权 | PRIN | Brief 状态 | — |

---

## 2. 落地规格追溯 — 总契约（§1–§3）

| ID | 来源 | 要求摘要 | Disposition | 切片/轨 | 备注 |
|---|---|---|---|---|---|
| TR-SP-01 | §1 边界 | 薄表+必要 FK，不建新主库 | **B1-S1** | 全批 | C01 修正 |
| TR-SP-02 | §1 | 四结论非四阶段引擎 | **B1-S3,S4** | verification | — |
| TR-SP-03 | §2 导航表 | 保留 dashboard/projects/pcf 主跳转 | PRIN + **DOC-IA** | TR-IA-03 | 不得改路由冒对齐 |
| TR-SP-04 | §2.1 上下文 | URL `process_id/round_id/...` | **B1-S1,S4** | 流程卡 | GET 不写库 |
| TR-SP-05 | §2.2 作业融合 | 任务—方法—操作—核验 | DOC-IA | §6 页面轨 | 非单页拆菜单 |
| TR-SP-06 | §2.2 | 禁止 auto EFFECTIVE | **B1-S5** | tool_sheet | 代码待改 |
| TR-SP-07 | §3.2 薄轮次字段组 | 身份/模型/口径/样本/验收 | **B1-S1,S2b** | dev-plan §4 | — |
| TR-SP-08 | §3.2 | revision/幂等 | **TR-DEC-2** | **B1-S1** | — |
| TR-SP-09 | §3.3 冻结 | As-Is/To-Be 非运行冻结 | **TR-DEC-1** | **B1-S1** | 未实现 |
| TR-SP-10 | §3.4 四结论表 | 最低条件 vs 不能冒充 | **B1-S3** | round_verification | — |
| TR-SP-11 | §3.5 publish | 当前=更新运行模型 | PRIN + **DOC-IA** | TR-UX-20 | 文案 §8 禁止改写 |
| TR-SP-12 | §3.6 权限/404 | org_access，GET 不推进 | **B1-S1** | API 全批 | — |

---

## 3. 落地规格追溯 — R0–R5 工作项（§4–§7）

| ID | 工作项 | 规格分期 | Disposition | 切片 | 审定备注 |
|---|---|---|---|---|---|
| TR-R0-01 | 导航与用途说明 | 第一批入口+上下文 | B1-min + **DOC-IA** | S4；TR-IA-04~06 | designer 用途模式 LATER |
| TR-R0-02 | 流程卡 round | 第一批 | **B1-S4** | process_card | — |
| TR-R1-01 | 分类排序 | 后续 | LATER | — | — |
| TR-R1-02 | 横向交接 | 后续 | LATER | SIPOC 已有 | — |
| TR-R1-03 | 章程任命资源 | 可增量 | LATER / B1-min | 流程卡缺项 | 不阻塞 S1 |
| TR-R1-04 | 十层适用性 | 第一批引用/缺项 | **B1-S3** | pilot | breaking 待确认 |
| TR-R1-05 | 20 项保障视图 | 后续 resolver | LATER | — | Slice 5 仅停 auto EFFECTIVE |
| TR-R2-01 | 薄轮次对照 | 第一批核心 | **B1-S1** | — | — |
| TR-R2-02 | KPI 来源/样本 | 第一批 | **B1-S2a,S2b** | — | 2a 可先发 |
| TR-R2-03 | 分析/方案交付 | 后续 | LATER | — | — |
| TR-R3-01 | 引擎边界 | R3 | LATER | — | — |
| TR-R3-02 | 部署映射 | R3 | LATER | — | — |
| TR-R3-03 | 任务权限 | R3 | LATER | — | — |
| TR-R3-04 | 命令事件 | R3 | LATER | — | — |
| TR-R3-05 | 迁移恢复 | R3 | LATER | — | — |
| TR-R4-01 | 异常响应 | 批可先引用 | **B1-S6** + LATER | exception round | 规则引擎 LATER |
| TR-R4-02 | 分析可比性 | 部分首批 | B1-min + LATER | 四结论/口径 | 并行分析待 R3 |
| TR-R5-01 | 本轮验收结项 | 第一批 | **B1-S4** | Gate 扩展 | PASS≠达标 |
| TR-R5-02 | 采用/控制 | 后续 | LATER | 培训记录扩展 | — |
| TR-R5-03 | 固化复制 | 后续 | LATER | ReplicationPack | — |

### 3.1 R1-05 二十项（仅追溯，第一批不实现 resolver）

| 代码 | Disposition | 主要来源模块 |
|---|---|---|
| SP-01～04 | LATER | charter / 项目 |
| OW-01～04 | LATER | RACI / 治理 |
| ST-01～04 | LATER | 标准/模板/ToolSheet |
| PF-01～04 | LATER + **B1-S2** | KPI / round 口径 |
| CU-01～04 | LATER | 培训 / 知识 |

---

## 4. 文案规范追溯（interface-content-standard）

| ID | 来源 | 要求摘要 | Disposition | 映射 |
|---|---|---|---|---|
| TR-UX-01 | §1 表达原则 | 对象/动作/结果边界；不靠中文判逻辑 | DOC-IA | §6 TR-IA-01 |
| TR-UX-02 | §2.1 页面六块 | 对象—状态—原因—操作 | DOC-IA | 各 view 审校 |
| TR-UX-03 | §2.2 门禁行 | 条件｜状态｜原因｜操作 | **B1-S3,S4** | 四结论/十层 |
| TR-UX-04 | §2.3–2.4 表单列表 | 分组与列规则 | DOC-IA | LATER 逐页 |
| TR-UX-05 | §2.5 四结论 | 2/4 进度；无「下一阶段」 | **B1-S4** | process_card |
| TR-UX-06 | §2.6 方法工作区 | 四区块；不 auto 有效 | **B1-S5** + DOC-IA | tool/start |
| TR-UX-07 | §2.7 保障清单 | 20 项呈现规则 | LATER | R1-05 |
| TR-UX-08 | §2.8 流程卡边界 | 本轮对照字段组 | **B1-S4** | — |
| TR-UX-09 | §3 术语表 | 统一用词 | DOC-IA | 非批量替换 DB |
| TR-UX-10 | §4 页面标题表 | 每页标题/说明/动作 | DOC-IA | §6 TR-IA-02~08 |
| TR-UX-11 | §5 状态词汇 | 分域 status；后端 meta | DOC-IA + **B1-min** | 去前端平行映射 |
| TR-UX-12 | §6 空态/失败/异步 | 事实+下一步 | DOC-IA | api.js 错误 |
| TR-UX-13 | §6.1 成功等级 | 发布/入队/验收分级 | DOC-IA | 与 publish 一致 |
| TR-UX-14 | §7 确认框 | 发布/验收/不适用 | DOC-IA | designer/projects |
| TR-UX-15 | §8 替换清单 | 模式→目标表述 | DOC-IA | **实施前先盘点** |
| TR-UX-16 | §9 唯一来源 | enum/meta/state/help | DOC-IA | §6 TR-IA-01 |
| TR-UX-17 | §9 审校清单 | 每切片 10 条检查 | 审定 + DoD | check 不含全文案 |

---

## 5. 七项技术决定（artifacts-review §4 ↔ dev-plan §2）

| ID | 决定 | 开发计划默认 | 追溯阻塞的 TR-ID | Disposition |
|---|---|---|---|---|
| TR-DEC-1 | 非运行模型冻结 | role + frozen_at | TR-SP-09, TR-RM-11 | 审定必填 |
| TR-DEC-2 | round revision/幂等 | expected_revision + Idempotency-Key | TR-SP-08 | 审定必填 |
| TR-DEC-3 | GateAttestation 扩展 | round_id, purpose, snapshot | TR-R5-01 | **B1-S4** |
| TR-DEC-4 | KpiRecord vs 验收样本 | 正式样本不可被 auto 覆盖 | TR-RM-08, TR-R2-02 | **B1-S2b** |
| TR-DEC-5 | 删除/归档 | RESTRICT/软删 | TR-R2-01 | **B1-S1** |
| TR-DEC-6 | 权限 | org_access + 项目写对齐 | TR-SP-12 | 全批 |
| TR-DEC-7 | 试点业务窗口 | 业务批准，文档不写死 | TR-RM-13 | 演示前 |

---

## 6. 产品语言与页面职责轨（DOC-IA）

> **原则：** 统一「概念与规则」，不是同义词批量替换；按**用户任务**重组信息，不是增加平级菜单。权威规范正文仍在 [bpm-interface-content-standard.md](bpm-interface-content-standard.md)；本节记录 **2026-11-03 静态代码评估**（未浏览器全页验收）。

### 6.1 语言与来源（概念统一）

| ID | 问题类型 | 证据（基线 `4607792`） | 处置 | 关联 TR-UX |
|---|---|---|---|---|
| TR-IA-01 | 枚举中文多源 | `format.js` 严重程度；`process_card.js` 重复映射 | DOC-IA P1：收拢到后端 meta | TR-UX-11,16 |
| TR-IA-02 | 方法论标签不一致 | `projects.py`「BPR 阶跃式重组」vs `dashboard.py`「BPR 重组」 | DOC-IA P1：标准名+短名契约 | TR-UX-09 |
| TR-IA-03 | 同标题不同任务 | `state.js` monitor 与 dashboard 均「运营驾驶舱」 | DOC-IA P1：按 §4 页签改标题 | TR-UX-10, §8 表 |
| TR-IA-04 | 错误表达混用 | `api.js` uvicorn 提示；detail JSON 字符串化 | DOC-IA P1：稳定 code + 用户句 | TR-UX-12 |
| TR-IA-05 | 状态域混用风险 | 多域 `CLOSED` 等 | DOC-IA P2：禁止全局 label 映射 | TR-UX-11 |
| TR-IA-06 | 发布/生效/结项 | 规格+文案已分域 | DOC-IA P1：高影响词先修 | TR-UX-13,15 |

**DOC-IA 交付物（文档轨，非词语表）：**

1. **文字差异盘点表**（建议路径 `docs/inventory/copy-diff-inventory.md`，审定后建）：当前位置 / 概念 / 冲突 / 标准名 / 权威来源。  
2. **分域清单**：术语、字段、枚举、状态、错误码 — 每条可追到 **唯一运行时来源**（§9 表），不另建平行字典库。  
3. **与 B1 交叉：** 仅 **TR-UX-06/15**（auto EFFECTIVE）、**TR-UX-05/08**（四结论/流程卡）必须在第一批功能切片中验收；其余 IA 可在 **B1 合并后** 小批落地。

### 6.2 页面职责（任务主题，非菜单膨胀）

| ID | 模块 | 评估结论 | 建议组织 | 优先级 | 关联规格 |
|---|---|---|---|---|---|
| TR-IA-07 | `deliverables.js` | 项目交付物/标准/模板/基线/治理混装 | 同入口下**主题子页**（非 5 个顶栏菜单） | P1 | TR-SP-03 |
| TR-IA-08 | `execution.js` | 办理+配置+集成同屏 | 办理 vs 运行配置 vs 集成分轨 | P1 | TR-R3-03 LATER |
| TR-IA-09 | monitor/dashboard | 页签已有但总标题混淆 | 总览 vs 分析/指标/异常分标题 | P1 | TR-IA-03 |
| TR-IA-10 | `orgs.js` | 组织/岗位/账号/角色同组 | 保留分组，按子页加载 | P2 | — |
| TR-IA-11 | designer | 专业工作台 | **不拆**多设计器 | N/A | TR-R2-03 |
| TR-IA-12 | `process_card.js` | 聚合入口 | **保留**；细节回原模块 | **B1-S4** | TR-R0-02 |

**验收分三层（IA 轨）：** 信息结构 → URL/状态 → 代码模块边界；只拆文件不拆任务 = 未达标。

### 6.3 IA 与第一批功能关系

| 关系 | 说明 |
|---|---|
| 可并行 | 文档轨盘点（§6.1 表 1–2）与审定可同步 |
| 必须同批 | 四结论/流程卡文案（B1-S4）与 verification 数据一致 |
| 建议顺序 | **先** TR-DEC + B1 证据链 **→** deliverables/execution 标题与子页（IA P1）→ 全站 enum meta（IA P1）→ 保障清单 UI（LATER） |

---

## 7. 汇总统计（供审定勾选）

| 来源 | 追溯条数 | B1 相关 | LATER | DOC-IA | PRIN/N/A |
|---|---:|---:|---:|---:|---:|
| 路线 §1–§10 | 22 | 10 | 8 | 1 | 3 |
| 规格 §1–§3 | 12 | 9 | 0 | 2 | 1 |
| 规格 R0–R5 | 20 | 8 | 12 | — | — |
| 文案 §1–§9 | 17 | 4 | 1 | 12 | — |
| 七项决定 | 7 | 7 | 0 | 0 | 0 |
| IA 评估 | 12 | 2 | 2 | 8 | — |
| 产品原则 §1–§10 | 49 | 18 | 6 | 4 | 21 |
| 综合评审 C01–C17 + §4–§6 | 24 | 4 | 0 | 0 | 20 |
| README 要点 | 6 | 0 | 0 | 2 | 4 |
| 八份专项（各文档 §1–§12） | 94 | 6 | 82 | 4 | 2 |
| 审定/实施包 | 5 | — | — | — | meta |

**产物全覆盖：** 原则 §9 共 **19 个文件**（含 README 与本文）均在 **§0.4** 登记；专项按 **§11.1–§11.8 每章一节** 共 94 条 TR-SPC-*。审定须 **§0.4 逐文件打勾** 且 spot-check 各章 TR-ID。

**Brief 覆盖度：** 仍仅为 B1* 子集；**不能**替代 §0.4 全表评审。

---

## 8. 产品基本原则追溯（bpm-product-principles.md）

> **上位契约：** 冲突以本文为准。原则文内 [§10](bpm-product-principles.md#10-本文条款与追溯-id供审定勾选) 与下表 TR-PR-* 一一对应。

### 8.0 章级摘要

| ID | 节 | 要求摘要 | Disposition | 下游追溯 |
|---|---|---|---|---|
| TR-PR-01 | §1 | 流程主对象；项目一轮；原记录协作 | PRIN | 全文 |
| TR-PR-02 | §2 | 十概念边界 | PRIN | 见 §8.1 |
| TR-PR-03 | §3 | 八入口导航 | PRIN + DOC-IA | TR-SP-03, TR-IA-03 |
| TR-PR-04 | §4 | 四身份/冻结/样本 | **B1-S1,S2,S3** | TR-RM-11, TR-DEC-* |
| TR-PR-05 | §5 | 权威来源与核验 | **B1** 多处 | TR-SP-11, TR-R2-02 |
| TR-PR-06 | §6 | R0–R5≠批次；审定后编码 | meta | TR-META-* |
| TR-PR-07 | §7 | 模块闭环交接 | LATER | 八专项 §11 |
| TR-PR-08 | §8 | 写法；六能力属性 | DOC-IA | TR-UX-01, TR-IA-01 |
| TR-PR-09 | §9 | 产物分工；§0.4 登记 | meta | §0.4 |

### 8.1 节级明细（TR-PR-*）

**§2 概念边界**

| ID | 概念 | 禁止混同（摘要） | Disposition |
|---|---|---|---|
| TR-PR-02-01 | 企业级治理 | ≠项目进度/APQC覆盖率/自动成熟度 | LATER |
| TR-PR-02-02 | process_id | ≠项目/实例/复制目录 | **B1-S1** |
| TR-PR-02-03 | 八阶段 | ≠八阶段状态机 | PRIN + DOC-IA |
| TR-PR-02-04 | 九知识模块 | ≠九工作阶段 | PRIN |
| TR-PR-02-05 | 五阶段 | ≠八阶段/实例状态 | PRIN |
| TR-PR-02-06 | round_id | ≠第二项目/运行阶段/资产库 | **B1-S1** |
| TR-PR-02-07 | 四种结论 | ≠四阶段引擎/计数门禁 | **B1-S3,S4** |
| TR-PR-02-08 | 十层核对 | ≠八/五阶段推进 | **B1-S3** |
| TR-PR-02-09 | 20项保障 | ≠20条平行任务 | LATER |
| TR-PR-02-10 | 方法/工具 | ≠填表即有效 | **B1-S5** + DOC-IA |

**§3 导航（各行保留去向）**

| ID | 导航 | Disposition |
|---|---|---|
| TR-PR-03-01 | strategy | PRIN |
| TR-PR-03-02 | pcf/map | PRIN |
| TR-PR-03-03 | designer 现状/方案 | B1-min + TR-DEC-1 |
| TR-PR-03-04 | monitor analysis | PRIN |
| TR-PR-03-05 | execution | PRIN + DOC-IA TR-IA-08 |
| TR-PR-03-06 | dashboard→monitor | PRIN + DOC-IA TR-IA-03 |
| TR-PR-03-07 | projects→workflow | PRIN |
| TR-PR-03-08 | authorization 贯穿 | PRIN |

**§4 证据契约**

| ID | 条款 | Disposition |
|---|---|---|
| TR-PR-04-01 | process_id 同一流程 | **B1-S1** |
| TR-PR-04-02 | round_id；立项前 project 可空 | **B1-S1** |
| TR-PR-04-03 | 模型分 As-Is/To-Be/上线角色 | **B1-S1** + TR-DEC-1 |
| TR-PR-04-04 | metric_contract hash | **B1-S2b** |
| TR-PR-04-05 | 草稿可部分；缺项不伪造 | **B1-S3,S4** |
| TR-PR-04-06 | 基线口径先于解释 | **B1-S2** |
| TR-PR-04-07 | 改善目标后侧锁定 | LATER + **B1-S4** |
| TR-PR-04-08 | 各时点快照 | **B1-S1** |
| TR-PR-04-09 | 锁定不可原位覆盖 | **B1-S1,S2b** |
| TR-PR-04-10 | hash≠授权/效果 | PRIN |
| TR-PR-04-11 | 实例不因分析改 project_id | PRIN |
| TR-PR-04-12 | 业务关联键≠四身份 | PRIN |

**§5 权威来源表**

| ID | 内容行 | Disposition |
|---|---|---|
| TR-PR-05-01 | 流程/Owner/组织 | LATER + DOC-IA |
| TR-PR-05-02 | 模型 publish 更新运行 | PRIN + DOC-IA |
| TR-PR-05-03 | Gate/Evidence 需 project | **B1-S4** |
| TR-PR-05-04 | 非项目核验扩原对象 | LATER |
| TR-PR-05-05 | KPI/样本 | **B1-S2** |
| TR-PR-05-06 | 标准/模板/培训版本 | LATER |
| TR-PR-05-07 | 运行/R3 单一推进 | LATER (R3) |
| TR-PR-05-08 | 派生视图只读 | **B1-S3,S4** |
| TR-PR-05-09 | 独立核验；方法≠普遍有效 | **B1-S5** |

---

## 9. 综合评审记录追溯（bpm-artifacts-review.md）

| ID | 来源 | 要求摘要 | Disposition | 备注 |
|---|---|---|---|---|
| TR-AR-01 | §1 | 设计基线≠已实现 | PRIN | — |
| TR-AR-C01 | §2 C01 | 薄表 vs 新主库冲突已收敛 | PRIN | 规格 §1 |
| TR-AR-C02 | §2 C02 | publish 语义统一 | PRIN + DOC-IA | TR-UX-15 |
| TR-AR-C03 | §2 C03 | 对照时点非一次齐全 | **B1-S1** | TR-RM-11 |
| TR-AR-C04 | §2 C04 | 四结论非四阶段 | **B1-S3,S4** | — |
| TR-AR-C05 | §2 C05 | R0–R5 分组非批次 | PRIN | TR-RM-20 |
| TR-AR-C06 | §2 C06 | 导航不改主跳转 | PRIN + DOC-IA | TR-SP-03 |
| TR-AR-C07 | §2 C07 | Gate 项目约束 | **B1-S4** | TR-R5-01 |
| TR-AR-C08 | §2 C08 | 复盘无专用库 | LATER | R5-02 |
| TR-AR-C09 | §2 C09 | KPI 样本不漂移 | **B1-S2b** | TR-DEC-4 |
| TR-AR-C10 | §2 C10 | 四身份模型/口径 | **B1-S1** | — |
| TR-AR-C11 | §2 C11 | BPR/ECRS 不分叉 | LATER | TR-SPC-DES-03 |
| TR-AR-C12 | §2 C12 | 能力六属性 | DOC-IA | TR-PR-08 |
| TR-AR-C13 | §2 C13 | 小闭环非新工作流 | LATER | 八专项 |
| TR-AR-C14 | §2 C14 | 20 项不造任务 | LATER | TR-R1-05 |
| TR-AR-C15 | §2 C15 | README 事实描述 | DOC-IA | TR-README-* |
| TR-AR-C16 | §2 C16 | 标准/样本/引擎分域 | PRIN | — |
| TR-AR-C17 | §2 C17 | 虚假计划链接已移除 | meta | §0.4 已补全 |
| TR-AR-D1 | §4 #1 | 非运行模型冻结 | TR-DEC-1 | 阻塞 S1 |
| TR-AR-D2 | §4 #2 | round  revision/幂等 | TR-DEC-2 | 阻塞 S1 |
| TR-AR-D3 | §4 #3 | Gate 扩展 | TR-DEC-3 | S4 |
| TR-AR-D4 | §4 #4 | KpiRecord 样本 | TR-DEC-4 | S2b |
| TR-AR-D5 | §4 #5 | 删除/归档 | TR-DEC-5 | S1 |
| TR-AR-D6 | §4 #6 | 权限 | TR-DEC-6 | 全批 |
| TR-AR-D7 | §4 #7 | 试点窗口 | TR-DEC-7 | 演示 |
| TR-AR-06 | §6 | 另一模型审定流程 | meta | handoff |

---

## 10. README 追溯（../README.md）

| ID | 来源 | 要求摘要 | Disposition | 备注 |
|---|---|---|---|---|
| TR-README-01 | 开篇 | 五阶段 vs 八阶段边界 | PRIN | 与原则一致 |
| TR-README-02 | 开篇 | 待评审设计≠已实现 | PRIN | 链追溯表/Brief |
| TR-README-03 | 三层体系 | 24 步/工具箱为产品描述 | N/A | 非 B1 契约 |
| TR-README-04 | API 文档体 | 当前能力说明 | LATER | 不全文进追溯 |
| TR-README-05 | 第二阶段待办 | 不把旧待办当规范 | OUT-OF-SCOPE | 读前核日期 |
| TR-README-06 | 本地运行 | PowerShell/ worker（若已写） | DOC-IA | C15 相关 |

---

## 11. 八份专项追溯（原则 §9.1）

> 专项**不重定义**对象/阶段（原则 §9）；下列 disposition 默认 **LATER**，仅标出与 **B1** / **DOC-IA** 交叉项。综合评审 §3 逐份摘要见 TR-AR 与各专项首段。

### 11.1 建模 — process-modeling-repository-gap.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-MDL-01 | 1 | 四种「能用」分层 | LATER |
| TR-SPC-MDL-02 | 2–3 | 讲义校准；用途 vs 运行 | DOC-IA + LATER |
| TR-SPC-MDL-03 | 4 | 能力与差距 | LATER |
| TR-SPC-MDL-04 | 5 | 标准校验后端权威 | DOC-IA |
| TR-SPC-MDL-05 | 6 | 仓库复用存储 | LATER |
| TR-SPC-MDL-06 | 7 | 建模作业链 | LATER |
| TR-SPC-MDL-07 | 8–9 | 场景验收/落点 | LATER |
| TR-SPC-MDL-08 | 10 | 优先顺序 | LATER |
| TR-SPC-MDL-B1 | 5–7 | designer 现状/方案用途模式 | B1-min + **TR-DEC-1** | 

### 11.2 分析 — process-analysis-method-chain.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-ANA-01 | 1 | 完整分析作业链未成 | LATER |
| TR-SPC-ANA-02 | 2 | 四链合一 | LATER |
| TR-SPC-ANA-03 | 3 | 能力对照 | LATER |
| TR-SPC-ANA-04 | 4 | 分析委托起点 | LATER |
| TR-SPC-ANA-05 | 5 | 逐步交付 | LATER |
| TR-SPC-ANA-06 | 6 | 选路同目标 | LATER |
| TR-SPC-ANA-07 | 7 | ABC/CX 等口径 | LATER |
| TR-SPC-ANA-08 | 8 | 分析交付包 | LATER |
| TR-SPC-ANA-09 | 9 | 页面/后端落地 | LATER |
| TR-SPC-ANA-10 | 10 | 演练示例 | N/A |
| TR-SPC-ANA-B1 | 4–5 | 可早于项目/上线（无项目核验边界） | B1-min；TR-R2-03 |

### 11.3 设计 — process-design-small-loop.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-DES-01 | 1 | 设计有效性未证明 | LATER |
| TR-SPC-DES-02 | 2 | 能力对标 | LATER |
| TR-SPC-DES-03 | 3 | BPR 原则 vs ECRS | LATER；TR-AR-C11 |
| TR-SPC-DES-04 | 4 | 小闭环作业链 | LATER |
| TR-SPC-DES-05 | 5 | 最小贯通实例 | LATER |
| TR-SPC-DES-06 | 6 | 设计交付标准 | LATER |
| TR-SPC-DES-07 | 7–8 | 理论/UI；后端增量 | LATER |
| TR-SPC-DES-08 | 9 | 验证清单 | LATER |
| TR-SPC-DES-B1 | 6 | 接收≠发布≠达标 | PRIN；TR-PR-07 |

### 11.4 绩效 — process-performance-decision-loop.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-PRF-01 | 1–2 | 目标与差距 | LATER |
| TR-SPC-PRF-02 | 3 | CSF→KPI 决策用途 | LATER |
| TR-SPC-PRF-03 | 4 | 四维/计分卡不混 | LATER |
| TR-SPC-PRF-04 | 5 | 数据可信可复算 | **B1-S2a,S2b**；TR-RM-08 |
| TR-SPC-PRF-05 | 6 | 绩效小闭环 | LATER |
| TR-SPC-PRF-06 | 7 | 红灯≠自动立项 | LATER |
| TR-SPC-PRF-07 | 8 | 三层监控 | LATER |
| TR-SPC-PRF-08 | 9 | 总分≠有效 | LATER |
| TR-SPC-PRF-09 | 10 | 界面与统一文案 | DOC-IA |
| TR-SPC-PRF-10 | 11–12 | 落点与验收顺序 | LATER |

### 11.5 转型 — process-transformation-practice-system.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-TRN-01 | 1–2 | 定位与差距 | LATER |
| TR-SPC-TRN-02 | 3 | 三路径非套餐 | LATER |
| TR-SPC-TRN-03 | 4–5 | 三层分类；实践纵深 | LATER |
| TR-SPC-TRN-04 | 6 | 一套事实多视角 | PRIN |
| TR-SPC-TRN-05 | 7 | 转型小闭环 | LATER |
| TR-SPC-TRN-06 | 8 | 保障原记录核验 | LATER；TR-R1-05 |
| TR-SPC-TRN-07 | 9 | 能力契约先于连接器 | LATER |
| TR-SPC-TRN-08 | 10 | 恢复非备份即过 | LATER；R3 |
| TR-SPC-TRN-09 | 11 | 界面落点 | DOC-IA |
| TR-SPC-TRN-10 | 12 | 实施顺序 | LATER |
| TR-SPC-TRN-B1 | 8 | 保存记录≠方法有效 | **B1-S5**；TR-SP-06 |

### 11.6 技术 — bpm-technology-open-contracts.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-TEC-01 | 1–2 | 原则与差距 | LATER |
| TR-SPC-TEC-02 | 3–4 | 输出/输入资产 | LATER |
| TR-SPC-TEC-03 | 5 | 四通道 | LATER |
| TR-SPC-TEC-04 | 6 | 传输/执行/结果分离 | LATER；R3 |
| TR-SPC-TEC-05 | 7 | RPA/挖掘/AI 边界 | LATER；TR-RM-06 |
| TR-SPC-TEC-06 | 8 | 安全治理 | LATER |
| TR-SPC-TEC-07 | 9 | 接入小闭环 | LATER |
| TR-SPC-TEC-08 | 10 | 练习场景 | N/A |
| TR-SPC-TEC-09 | 11 | 模块落点分批 | LATER |
| TR-SPC-TEC-10 | 12 | 验收与边界 | LATER |
| TR-SPC-TEC-B1 | 11–12 | Flowable 不在第一批 | PRIN；非目标 |

### 11.7 组织 — process-organization-governance-loop.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-ORG-01 | 1 | 治理=有权有责有资源 | LATER |
| TR-SPC-ORG-02 | 2 | 项目对标 | LATER |
| TR-SPC-ORG-03 | 3 | 目标治理模型 | LATER |
| TR-SPC-ORG-04 | 4 | 缺口评估预警 | LATER |
| TR-SPC-ORG-05 | 5 | 冲突协调 | LATER |
| TR-SPC-ORG-06 | 6 | 组织文化小闭环 | LATER |
| TR-SPC-ORG-07 | 7 | 界面呈现合力 | DOC-IA |
| TR-SPC-ORG-08 | 8 | 工程边界 | LATER |
| TR-SPC-ORG-09 | 9 | 顺序与验收 | LATER |
| TR-SPC-ORG-B1 | 4–6 | 20 项保障不造任务 | LATER；TR-R1-05 |

### 11.8 企业 — enterprise-process-strategy-loop.md

| ID | § | 要求摘要 | Disposition |
|---|---|---|---|
| TR-SPC-ENT-01 | 1 | 战略闭环原则 | LATER |
| TR-SPC-ENT-02 | 2 | 对标 | LATER |
| TR-SPC-ENT-03 | 3 | 三口径统一 | LATER |
| TR-SPC-ENT-04 | 4 | 战略地图带证据 | LATER |
| TR-SPC-ENT-05 | 5 | 企业小闭环 | LATER |
| TR-SPC-ENT-06 | 6 | 组合管理 | LATER |
| TR-SPC-ENT-07 | 7 | APQC 关系 | LATER |
| TR-SPC-ENT-08 | 8 | 端到端治理 | LATER |
| TR-SPC-ENT-09 | 9 | 九模块交接总表 | PRIN；非九阶段 |
| TR-SPC-ENT-10 | 10 | 证据跨层不累加收益 | PRIN |
| TR-SPC-ENT-11 | 11 | 界面后端接续 | LATER |
| TR-SPC-ENT-12 | 12 | 优先顺序 | LATER |
| TR-SPC-ENT-B1 | 12 | 第一批不变全量 | PRIN；Brief 非目标 |

---

## 12. 审定与实施包（meta）

| ID | 文档 | 要求 | 与追溯表关系 |
|---|---|---|---|
| TR-META-BRF | bpm-first-batch-brief.md | B1 范围/非目标/通过标准 | §2–§3 B1* 摘要 |
| TR-META-PLN | bpm-first-batch-dev-plan.md | 六切片/API/DoD | 实现 TR-DEC + B1 |
| TR-META-HOF | bpm-review-handoff.md | 审定顺序与 §5 模板 | 须勾选 §0.4 |
| TR-META-R1 | bpm-r1-implementability-review.md | R1 vs 代码 | TR-R1-* |
| TR-META-TRC | 本文 | 全覆盖主清单 | §0.4 自指 |

---

## 13. 文档维护

- 原则 §9 增删产物时：**先改 §0.4**，再增 TR 行。  
- 规格/文案/路线/专项正文变更时：同步对应 §1–§12。  
- 实施切片合并时：在 B1 相关 TR 行追加 commit/测试引用。  
- IA 盘点：`docs/inventory/`（审定通过后建表）。

---

*远程：`4607792` Already up to date。本表不包含业务代码改动。*
