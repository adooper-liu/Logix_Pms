# BPM 文档审定交接说明（给审定模型）

> **后续状态：** 用户已结束本轮评审；本文件保留历史第一批审定流程，不再作为当前“另派模型”入口。当前工作见[实施启动brief](implementation-next-brief.md)，待定的round/验收契约随各切片计划落实，不追认本文检查单已全部完成。
> **用途：** 原供另一模型或评审人在编码开始前审定BPM第一批改造，现仅作历史流程参考。
> **当前阶段：** 仅文档与 brief；**禁止**在本阶段提交业务实现 PR（除非用户明确授权「审定与实现并行」）。  
> **代码基线：** 请在只读模式下核对 `4607792`（或用户指定的更新 HEAD），勿假设对话中的未合并 diff 已存在。

## 1. 审定任务

请阅读下列产物，输出**一份审定结论**（使用 §5 模板），并**逐章勾选** [需求追溯表](bpm-requirements-traceability.md) §0.3 / §7 汇总。

重点回答：

1. 追溯表 §1→§4 是否按顺序覆盖路线、规格、文案；Brief 未覆盖行是否已标 disposition。  
2. 产品边界是否与 [产品基本原则](bpm-product-principles.md) 一致，有无残留「双规格」或假链接。  
3. [第一批 Brief](bpm-first-batch-brief.md) 与 [开发计划](bpm-first-batch-dev-plan.md) 的切片、依赖、非目标是否一致。  
4. [综合评审 §4](bpm-artifacts-review.md) 七项决定（追溯表 §5）是否在开发计划 §2 中有**可执行的默认**，仍缺的是否阻塞 Slice 1。  
5. [R1 可实施性复审](bpm-r1-implementability-review.md) 是否与 `4607792` 代码一致；有无遗漏的高风险玩具逻辑。  
6. **追溯表 §6（DOC-IA）**：语言/页面轨是否与文案规范 §9 一致；是否误当成「同义词替换表」或「加菜单」方案。  
7. 第一批是否**真的**可演示最小证据链，还是 scope creep。  
8. 测试与 DoD 是否足够防止「文档 0 error = 功能已闭环」类误判。

## 2. 建议阅读顺序

| 顺序 | 文件 | 预计关注点 |
|---|---|---|
| 0 | [bpm-requirements-traceability.md](bpm-requirements-traceability.md) | **主清单**：先 **§0.4 十九文件登记**，再 §1–§12 逐 TR-ID |
| 1 | [bpm-first-batch-brief.md](bpm-first-batch-brief.md) | B1 子集摘要（不能替代追溯表） |
| 2 | [bpm-product-principles.md](bpm-product-principles.md) | 上位契约；对照追溯 [§8.0–§8.1](bpm-requirements-traceability.md#8-产品基本原则追溯bpm-product-principlesmd) TR-PR-* |
| 3 | [bpm-artifacts-review.md](bpm-artifacts-review.md) | 已修正错位、§4 未决项 |
| 4 | [bpm-first-batch-dev-plan.md](bpm-first-batch-dev-plan.md) | 模型/API/测试、§2 决定表 |
| 5 | [bpm-r1-implementability-review.md](bpm-r1-implementability-review.md) | R1-xx vs 代码 |
| 6 | [bpm-lifecycle-gap-and-roadmap.md](bpm-lifecycle-gap-and-roadmap.md) | 对照追溯表 §1 |
| 7 | [bpm-lifecycle-implementation-spec.md](bpm-lifecycle-implementation-spec.md) | 对照追溯表 §2–§3 |
| 8 | [bpm-interface-content-standard.md](bpm-interface-content-standard.md) | 对照追溯表 §4；§8–§9 与 §6 IA |

八份专项仅做“第一批实现范围裁剪”时可定向抽查；这不满足[全量文档评审任务书](document-review-handoff.md)要求的核心16份完整阅读。两种任务分开报告，不能用本文件较窄范围替代全量评审。

## 3. 审定检查单（逐项打勾 / 注明风险）

### 3.1 语义与一致性

- [ ] 「四结论」 nowhere 被写成四阶段引擎或 `current_stage` 扩展  
- [ ] 「publish = 运行模型更新」在全文档统一；无「发布成功但未部署」对**当前**行为的描述  
- [ ] `GateAttestation.PASS` 与「改善达标」隔离  
- [ ] 导航表：dashboard/projects/pcf 主跳转未被偷偷改成 map/monitor/workflow  
- [ ] 第一批「只新增薄表 + 必要 FK」与开发计划中的 JSON/字段增量无冲突  

### 3.2 可实施性

- [ ] `ProcessImprovementRound` 字段组覆盖 spec §3.2 最小集  
- [ ] `publish` + 可选 `round_id` 钩子不破坏现有 SoD 与 `_apply_snapshot` 语义  
- [ ] KPI 2a：枚举/字段名与 monitor API、种子数据、dashboard 过滤一致  
- [ ] 十层适用性改动是否标注 breaking（种子/demo 路径）  
- [ ] 前端零构建：新增视图是否仍符合 `main.js` 注册 + `test_frontend_structure` 约定  

### 3.3 七项决定（§4 artifacts-review）

对每一项记录：**状态**（已定 / 采纳计划默认 / 阻塞）+ **理由**：

1. 非运行模型冻结  
2. round revision / 幂等  
3. GateAttestation 扩展  
4. KpiRecord 与验收样本  
5. 删除/归档  
6. 权限  
7. 试点业务窗口  

### 3.4 追溯表与 IA 轨

- [ ] [bpm-requirements-traceability.md](bpm-requirements-traceability.md) §1–§4 每条 B1\* 与 Brief/开发计划一致  
- [ ] §6 DOC-IA：区分 P1 盘点/子页 vs 第一批必测项（S4/S5）  
- [ ] 未创建 `docs/inventory/copy-diff-inventory.md` 不视为缺口（审定后再建）

### 3.5 验证边界

- [ ] 审定结论不声称已跑 pytest / E2E / Flowable，除非附真实输出  
- [ ] 明确「静态文档检查 ≠ 产品闭环已实现」  

## 4. 代码核对指引（可选但推荐）

在基线 `4607792` 上只读查看（路径供 grep/read，非实施）：

| 主题 | 路径 |
|---|---|
| KPI 取数/回写 | `app/services/kpi.py` |
| 工具 auto EFFECTIVE | `web/js/views/shared/tool_sheet.js` |
| 十层 evidence | `app/services/pilot.py` |
| publish | `app/services/process_model.py` |
| 根因门 | `app/services/evidence.py` |
| 单 OPEN 任务约束 | `app/models/execution.py` |

若 HEAD 已前进，请在审定结论中注明**实际核对 commit**。

## 5. 审定输出模板（请复制填写）

```markdown
## BPM 第一批文档审定结论

- 审定人/模型：
- 日期：
- 代码基线 commit：
- 总体结论：APPROVED / APPROVED WITH CONDITIONS / NOT READY

### 阻塞项（NOT READY 或 CONDITIONS 必填）
1. ...

### 七项决定状态
| # | 决定 | 状态 | 备注 |
|---|---|---|---|

### 建议实施顺序
1. ...

### 允许先行合并的切片（若有）
- ...

### Breaking change 与迁移注意
- ...

### 文档修订建议（不阻塞时可列）
- ...

### 验证声明
- [ ] 本次审定未运行测试 / 已运行：...
```

## 6. 审定通过后的交接

用户确认审定结论后，实施模型应：

1. 从 [开发计划](bpm-first-batch-dev-plan.md) 与审定记录的**实施顺序**开工。  
2. 每切片 PR 引用审定 commit 与对应检查项。  
3. 更新 [综合评审](bpm-artifacts-review.md) §5 验证记录（附 `check.py` / pytest 输出）。

---

*本文件不参与产品语义定义；冲突以 [产品基本原则](bpm-product-principles.md) 为准。*
