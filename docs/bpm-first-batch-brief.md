# BPM 第一批改造 — 审定 Brief

> **状态：总体范围候选；本轮评审已由用户要求停止，转入分片实施计划。** 不再以“再找模型评审”作为下一步。当前实际实施入口见[下一步brief](implementation-next-brief.md)；round/正式核验的七项决定仍未逐项批准，不得按总体草案全量编码或宣称上线。
> **代码基线（核对事实用）：** `4607792`（`origin/main`，含本地运行说明 PR）。  
> **统一契约：** [产品基本原则](bpm-product-principles.md) · [落地规格](bpm-lifecycle-implementation-spec.md) · [综合评审](bpm-artifacts-review.md)。  
> **完整追溯（路线→规格→文案→IA）：** [bpm-requirements-traceability.md](bpm-requirements-traceability.md) — Brief 仅覆盖其中 **B1\*** 子集，审定须以追溯表为准。

## 1. 我们要解决什么

Logix PMS 已有治理、建模、轻量执行、KPI、项目五阶段、十层试点等模块，但**不能证明**同一条流程在同一口径下完成「诊断 → 发布 → 运行 → 可比改善 → 独立验收」的闭环。主要缺口是**跨阶段的可信证据与版本关联**，而不是再堆页面。

**终点（演示级，非全产品）：** 选定一条 L3/L4 流程 → 建立**薄轮次对照**（`round_id`）→ 冻结 As-Is 与指标口径 → 改善项目绑定 → 发布与 round 绑定 → **四种结论只读投影** → 流程卡/试点/异常引用同一 `round_id`。

## 2. 产品边界（不可妥协）

| 坚持 | 不做 |
|---|---|
| 流程（`process_id`）是长期主对象；项目只交付一轮改善 | 八阶段/四结论做成第二套状态机或 `advance` API |
| 四种结论是同轮**核验进度**投影，缺项可显示、不可伪造 | 用计数门禁、工具填表、Gate `PASS` 代替「改善达标」 |
| 当前 `publish()` **会**更新运行模型（SoD 已有）；文案不说「仅审批未部署」 | 第一批建发布包库、方案库、Flowable 运行时 |
| 枚举中文、UTC、Alembic、零构建前端 | 前端硬编码枚举或引入构建链 |
| GET 不写库、不猜另一流程/轮次 | 列表接口默认创建 round 或静默选「最新轮」 |

## 3. 第一批范围（六个切片，切片2分2a/2b）

| 切片 | 对应工作项 | 交付物（摘要） | 可独立先发 |
|---|---|---|---|
| **1** | R2-01 | `ProcessImprovementRound` 表 + CRUD/lock/bind API；与 `publish` 可选绑定 | 否（核心） |
| **2a** | R2-02 | KPI **显式**取数来源；禁止「绑流程 + 时长单位 → 全体回写 E2E」 | **是** |
| **2b** | R2-02 | `KpiRecord` 的 round/contract/hash/样本角色；自动回写不覆盖正式样本 | 依赖 1 |
| **3** | R1-04a | 十层**适用性**（如第 6 层 RPA 非全员强制）+ 四结论只读服务 | 部分可先于 round |
| **4** | R0-02、R5-01 | 流程卡 `round_id`、Gate 扩展字段、verification 投影 | 依赖 1、3 |
| **5** | spec §2.2 | 工具 sheet **不得**自动 `POST …/usage` 且 `outcome=EFFECTIVE` | **是** |
| **6** | R4-01 | `ExceptionEvent.round_id` 可选 FK + API | 依赖 1（可略晚） |

**明确不在第一批：** R1-01/02 全量、R2-03、R3 全系、R1-05 二十项 resolver 全量、独立收益裁决 UI（可占位）。

## 4. 开工前必须锁定的 7 项决定

见 [开发计划 §2](bpm-first-batch-dev-plan.md) 与 [综合评审 §4](bpm-artifacts-review.md)。审定模型须对每一项给出 **已定 / 采纳默认 / 仍阻塞**：

1. 非运行模型（As-Is/To-Be）如何冻结，与 draft/publish/rollback 关系  
2. `round` 的 `expected_revision`、幂等键、范围校验  
3. `GateAttestation` 扩展（`round_id`、`purpose`、快照）与「PASS ≠ 改善达标」  
4. 正式验收样本 vs 日常 `KpiRecord` / 实例自动回写  
5. 删除/归档与 round、项目、证据保留  
6. 权限与 `org_access` 对齐方式  
7. 试点业务窗口与 KPI 目标（业务批准，文档不写死）

## 5. 已知代码事实（基线 `4607792`，供审定核对）

以下来自静态复审，**不是**已修复承诺：

- `app/services/kpi.py`：`intake_kind()` 仍可能仅凭「流程 + 时长单位」推断实例来源；`record_completed_instance()` 仍可能回写该流程下**所有**时长 KPI。  
- `web/js/views/shared/tool_sheet.js`：步骤上下文下仍可能自动提交 `usage` 且 `outcome=EFFECTIVE`。  
- `app/services/pilot.py`：十层 `evidence_met` 多为 count>0；第 6 层对 RPA/技术等偏强制，与「适用性」规格冲突。  
- `app/services/process_model.publish`：已 `_apply_snapshot` 并更新发布指针（产品文案须一致）。  
- Flowable：**仓库无运行时接入**。

细节表见 [R1 可实施性复审](bpm-r1-implementability-review.md)。

## 6. 审定通过标准（Definition of Ready for Implementation）

同时满足方可进入编码：

1. [Brief](bpm-first-batch-brief.md) 与 [开发计划](bpm-first-batch-dev-plan.md) **无内部矛盾**（含切片编号、依赖、API 与「非目标」）。  
2. §4 的 7 项决定均有**明确取值或已批准的默认**，无「TBD 但可开工」。  
3. 每个切片有**可自动化验收**的 pytest /（若改前端）`verify_frontend.py` 条目。  
4. 与 [文案规范](bpm-interface-content-standard.md) 一致：四结论措辞、publish vs R3 部署、能力属性表述。  
5. 审定输出包含：**切片实施顺序**、**是否允许 2a/5 先行合并**、**Breaking change 清单**（如 pilot 第 6 层、KPI 种子行为）。

## 7. 审定后实施纪律

- 按锁定顺序交付；每切片合并前：`pytest` 相关用例、`alembic check`（若改模型）、`python scripts/check.py`。  
- 不凭记忆改代码；结论附命令输出（见仓库 `CLAUDE.md`）。  
- README 不宣传未合并 UI/API 为「已上线」；可在待办链到开发计划。

## 8. 相关文档索引

| 文档 | 用途 |
|---|---|
| [bpm-requirements-traceability.md](bpm-requirements-traceability.md) | 路线/规格/文案/IA 逐条 disposition（审定主清单） |
| [bpm-review-handoff.md](bpm-review-handoff.md) | 交给审定模型的阅读顺序、检查单与输出模板 |
| [bpm-first-batch-dev-plan.md](bpm-first-batch-dev-plan.md) | 字段/API/测试分解 |
| [bpm-r1-implementability-review.md](bpm-r1-implementability-review.md) | R1-01～R1-05 相对代码的可实施性 |
| [bpm-lifecycle-implementation-spec.md](bpm-lifecycle-implementation-spec.md) | R0–R5 总规格 |
| [bpm-interface-content-standard.md](bpm-interface-content-standard.md) | 界面与术语 |

---

*本文保留总体候选范围与依赖；当前实施入口以实施启动brief及其详细任务计划为准，不再要求重复开启已结束的评审轮次。*
