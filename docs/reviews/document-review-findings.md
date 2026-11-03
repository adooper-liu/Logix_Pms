# 全量文档综合评审 — 详细附录

> 基线：`6ba817f46f355c7e6ed0ca92d7ba88d4d8271f12`。Brief：[document-review-brief.md](./document-review-brief.md)。

---

## A. 覆盖矩阵

**图例：** 完整 = 全文或 handoff 要求等深度；摘要 = 首段+结构+与基线冲突扫描；性质 = 现行规格 / 历史提案 / 混合 / 个人证据 / 工程约束。

### A.1 核心产物 C01–C16

| ID | 文件 | 读取深度 | 文档性质 | 主要结论 | 发现 ID |
|---|---|---|---|---|---|
| C01 | README.md | 完整（基线 `git show`） | 现行说明 | 正确区分已实现 vs 待评审；未链 brief/追溯（基线） | DR-010 仅对工作区 |
| C02 | bpm-product-principles.md | 完整（基线） | **既定约束** | 概念/证据/分期清晰；§9 未列 C15/C16/handoff | DR-009 |
| C03 | bpm-lifecycle-gap-and-roadmap.md | 完整 | 现行路线 | §6 断点与代码一致；R0–R5≠批次 | DR-001–003 |
| C04 | bpm-lifecycle-implementation-spec.md | 完整 | 现行规格 | 薄轮次/冻结/第一批边界自洽；footer 元数据过时 | DR-008 |
| C05 | bpm-interface-content-standard.md | 完整 | 现行表达规范 | 与 PR#12 inventory/page 表一致；四结论/publish 分域 | — |
| C06 | bpm-artifacts-review.md | 完整 | 评审记录 | C01–C17 修正叙事合理；§5 验证未含本次 pytest | DR-008 |
| C07 | process-modeling-repository-gap.md | 摘要+§5–§7 | 专项/建议 | 用途/保真/仓库分域；不另建第二模型库 | — |
| C08 | process-analysis-method-chain.md | 摘要+§5–§8 | 专项/建议 | 分析链未落地为单一 API；无项目边界正确 | — |
| C09 | process-design-small-loop.md | 摘要+§3–§6 | 专项/建议 | BPR/ECRS 分轨；接收≠上线 | — |
| C10 | process-performance-decision-loop.md | 摘要+§5–§7 | 专项/建议 | 与 R2-02 同向；代码 KPI 未达标 | DR-001 |
| C11 | process-transformation-practice-system.md | 摘要+§7–§8 | 专项/建议 | 保障不造任务；与 R1-05 一致 | DR-002 |
| C12 | bpm-technology-open-contracts.md | 摘要+§5–§6 | 专项/建议 | Flowable 方向未接入；传输/执行/结果分离 | — |
| C13 | process-organization-governance-loop.md | 摘要+§4–§6 | 专项/建议 | 复盘拟扩原载体；非新任务中心 | — |
| C14 | enterprise-process-strategy-loop.md | 摘要+§9–§10 | 专项/建议 | 九模块交接≠九阶段；战略因果不自动证明 | — |
| C15 | product-language-inventory.md | 完整 | **候选整治清单** | 26 L-* 有源码锚点；均「拟统一」非已实施 | DR-004–007, DR-011 |
| C16 | page-responsibility-and-decomposition.md | 完整 | **候选 IA 方案** | 23 入口+S1–S5；未浏览器验收 | DR-012 |

### A.2 配套/历史 S01–S30

| ID | 文件 | 读取深度 | 建议处理 | 备注 |
|---|---|---|---|---|
| S01 | apqc-ten-elements-gap-analysis.md | 摘要 | 明确历史+索引 | APQC 对照，易与现行十层混淆 |
| S02 | framework-gap-analysis.md | 摘要 | 历史/修订索引 | 与 C03/C04 部分重叠 |
| S03 | framework-p2-project.md | 摘要 | 历史提案 | P2 预测/挖掘 |
| S04 | process-execution-gap-analysis.md | 摘要 | 历史+引用路线 | 执行语义 |
| S05 | execution-p2-project.md | 摘要 | 历史提案 | 补偿/版本 |
| S06 | bpmn-editor-and-attachments.md | 摘要 | 历史方案 | 模型权威源见 C07 |
| S07 | bpmn-js-best-practices.md | 摘要 | 技术参考 | 非产品规范 |
| S08 | bpmn-js-spike.md | 摘要 | 历史验证 | 不可扩大为全场景保证 |
| S09 | bpmn-p2-project.md | 摘要 | 历史提案 | |
| S10 | attachment-editing-and-distribution.md | 摘要 | 历史/混合 | |
| S11 | process-deliverable-versioning.md | 摘要 | 现行参考 | 与 deliverables 实现相关 |
| S12 | integration.md | 摘要 | 现行参考 | worker/outbox 边界 |
| S13 | metrics.md | 摘要 | 现行参考 | 与 DR-001 相关 |
| S14 | pcf-chinese-translation.md | 摘要 | 参考译文 | |
| S15 | process-management-best-practices.md | 摘要 | 教程/惯例 | 非强制规范 |
| S16 | frontend-architecture.md | 摘要 | 工程参考 | 与 C16 交叉 |
| S17 | information-architecture.md | 摘要 | **可能冲突** | 与 C16 导航需对照 |
| S18 | ui-information-architecture.md | 摘要 | **可能冲突** | 混装风险 |
| S19 | navigation-map.md | 摘要 | 现行参考 | 深链/别名 |
| S20 | usage-guide.md | 摘要 | 使用说明 | 需与页面一致 |
| S21 | sketches.md | 摘要 | 现行 | 草图≠运行模型 |
| S22 | toolbox-problem-driven-plan.md | 摘要 | 历史/混合 | 工具箱 |
| S23 | knowledge-scenario-upgrade-plan.md | 摘要 | 历史提案 | 已并工具箱 |
| S24 | help/README.md | 摘要 | 现行 | catalog 唯一长文 |
| S25 | startup-path.md | 摘要 | 历史叙事 | 0→1 |
| S26 | startup-evidence-example.md | 摘要 | 样例 | 非当前实测 |
| S27 | three-layers-and-page-dependencies.md | 摘要 | 历史口径 | Q1–Q8 |
| S28 | training-zero-to-one.md | 摘要 | 培训 | 与页面一致性 |
| S29 | resume-capability-map.md | 摘要 | 个人证据包 | 不复制 PII |
| S30 | resume.md | 未读正文 | 跳过内容 | 仅主张边界；handoff 允许 |

### A.3 工程与任务书

| ID | 文件 | 读取深度 | 性质 | 发现 |
|---|---|---|---|---|
| — | CLAUDE.md | 摘要 | 工程约束 | 与零构建/Alembic 一致 |
| — | document-review-handoff.md | 完整 | 任务书 | 范围可执行；基线声明含多历史 SHA |
| — | web/vendor/bpmn-js/README.md | 未读 | 第三方 | 按需 |

### A.4 基线外（工作区，非 `6ba817f` 树）

| 路径 | 状态 | 风险 |
|---|---|---|
| docs/bpm-first-batch-*.md, bpm-requirements-traceability.md, bpm-review-handoff.md | 未跟踪 | 与 C04 footer「计划未生成」并存时易双轨 |
| README.md 等 staged | 已暂存未提交 | 链向未跟踪文件 → DR-010 |

---

## B. 发现表（去重排序）

| ID | 类别 | 严重 | 置信 | 位置 | 场景→后果 | 性质 | 最小修订 | 验证 |
|---|---|---|---|---|---|---|---|---|
| DR-001 | KPI | P1 | confirmed | 规格 R2-02；`kpi.py:112–114,367–382` | 配置两个「天」KPI 仅一个语义却被同一 E2E 回写 → 错误达标/改善候选 | **代码+规格差距** | 显式 `intake_source`；回写仅标记 cycle 的 KPI | 只读 grep；未 pytest |
| DR-002 | 工具 | P1 | confirmed | 规格 §2.2；`tool_sheet.js:93–102` | 填 sheet 即 EFFECTIVE → 违背「保存≠有效」、污染保障/采用证据 | **代码违反约束** | 删除 auto usage 或改为显式 PARTIAL+用户确认 | 只读 |
| DR-003 | 十层 | P1 | confirmed | 路线 §6.1；`pilot.py:180–199` | 无 RPA 流程无法 honest N/A → 误导向「补造技术登记」 | **代码违反约束** | 适用性 JSON + evidence_met 尊重 N/A | 只读 |
| DR-004 | 语言 | P1 | confirmed | C15 L-01；`projects.py:79`,`dashboard.py:52` | 同一方法论不同中文 → 报表/帮助/导出分裂 | 文档+代码 | 后端 label/short_label 契约 | inventory 已列 |
| DR-005 | IA/语言 | P1 | confirmed | C15 L-04；`state.js:76,83` | 用户以为在总览 vs 分析却同标题 → 误操作 | 文档+代码 | dashboard/monitor 分标题 | 只读 |
| DR-006 | 语言 | P1 | confirmed | 文案 §9；`format.js`,`process_card.js` | 枚举中文漂移；违反「后端 meta」 | **代码违反约束** | 收敛到各域 API meta | 只读 |
| DR-007 | 错误 UX | P1 | confirmed | 文案 §6；`api.js:43–50` | 用户见 uvicorn/401 混用 → 泄露环境、422 难定位 | 文档+代码 | 稳定 code+用户句；401 与会话分开 | 未浏览器 |
| DR-008 | 元数据 | P2 | confirmed | C04 末段 @6ba817f | 读者以为无文档/无计划，实际已有 handoff+inventory | **文档事实错误** | 更新 footer：已实现文档列表；计划=handoff 或待并入 dev-plan | git show |
| DR-009 | 索引 | P2 | confirmed | C02 §9 @6ba817f | 产物分工缺 C15/C16/任务书 → 评审漏读 | 文档不一致 | principles §9 增行+链 handoff | git show |
| DR-010 | 仓库 | P2 | confirmed | 工作区 README staged | 合并后链 404 brief/追溯 | 流程 | 提交全套或移除链接 | status |
| DR-011 | 安全/示例 | P2 | plausible | C15 L-25；`index.html` | 演示账号占位 → 误用于非演示环境 | 建议 | 环境标识+隐藏 demo 账号 | 未读全 html |
| DR-012 | IA | P2 | plausible | C16 全文 | S1–S5 被误读为已实施 → 范围 creep | 建议 | 全文标「候选」；与 S 切片绑定 DoD | 未 E2E |
| DR-013 | 项目类型 | P2 | plausible | C16 P-10；`project_workflow.py:147` | 治理项目进五阶段工作台 → 错误阶段叙事 | 代码+建议 | workflow 按 project_type；setup 走详情 | 只读部分 |
| DR-014 | 轮次 | P2 | confirmed | C04 §3.2；models grep | 文档描述 round → 代码无表 | **正常差距** | 实施第一批；非文档错 | grep 无 round |
| DR-015 | Flowable | P2 | confirmed | C12；代码库 | 文档写已采纳未接入 → 一致 | 正常 | R3 计划单列 | — |
| DR-016 | 综合评审 | P2 | plausible | C06 §5 | 旧「链接 0 error」易被当成本次业务验收 | 证据边界 | artifacts 增「独立评审 DR-*」 | — |

**已反证排除（不升为 P1）：**

- 「规格仍要求发布包库」—— `6ba817f` 规格已删冲突建表指令（C06 C01 修正已落实）。  
- 「README 宣称闭环已实现」—— 基线 README 明确未实现（C01）。

---

## C. 契约对照（权威来源 × 时间点）

| 概念 | 文档权威 | 代码权威 @6ba817f | 时间点/策略 | 冲突 |
|---|---|---|---|---|
| 长期流程 | ProcessArch | `app/models/process.py` | 持续 | — |
| 改善项目 | Project 1–5 | `project_workflow.py` | 立项→结项 | 治理类型 UI 未隔离 DR-013 |
| 薄轮次 | ProcessImprovementRound（拟） | **无** | 冻结/追加 | 计划内 DR-014 |
| 模型发布 | ProcessModelVersion PUBLISHED | `publish()` 更新运行表 | 发布瞬间 | 文档正确 |
| KPI 正式来源 | R2-02 显式 | 时长推断 | 实例完成 | **DR-001** |
| 四结论 | round 投影 | **无** round 服务 | 只读 GET | 未实现 |
| Gate 改善达标 | 独立验收 purpose | GateAttestation project-bound | PASS≠达标 | 文档一致 |
| 枚举中文 | 后端 meta | 前端 format/card | 响应时 | **DR-006** |
| 页面标题 | C05+C16 | state.js | 渲染时 | **DR-005** |
| 工具有效 | 不 auto EFFECTIVE | tool_sheet auto | 保存时 | **DR-002** |

---

## D. 历史文档处理建议

| 处理 | 对象 | 原因 |
|---|---|---|
| **保持现行** | C02–C06, C15, C16, handoff, CLAUDE | 本轮基线 |
| **修订正文** | C04 footer；C02 §9 | DR-008/009 |
| **明确历史+链路线** | S01–S05, S25–S28 | 避免当规格 |
| **参考不升格** | S07–S08, S15, S29–S30 | 技术/个人 |
| **对照合并** | S17–S19 vs C16 | 减少 IA 双轨 |
| **退役索引** | S23 knowledge-scenario | 已并工具箱 |

---

## E. 场景走查（handoff §5.1）

| # | 场景 | 权威对象链 | 文档 | 代码 | 缺口 |
|---|---|---|---|---|---|
| 1 | 无项目建模→运行 | process_id；无 round | 原则§3 允许 | 可执行/监控 | 无强制项目 ✓ |
| 2 | 改善全链 | round+project+版本+样本 | C04 §3.2 | 无 round | **链未实现** |
| 3 | 未达标/口径混 | 冻结样本 | C04 §3.4 | KPI 回写混 | DR-001 |
| 4 | publish vs Flowable | 模型行 vs 部署 ID | C05/C12 | publish 有 | R3 未接入 ✓ |
| 5 | 交付物晋升 | DeliverableVersion | S11,C16 §3 | deliverable 服务 | 治理发现归属 C16 候选 |
| 6 | 驾驶舱→单主题 | URL+标题 | C16 §5 | router/state | DR-005/007 |
| 7 | 治理 vs 改善项目 | project_type | C16,L-20 | setup 1 阶段 | DR-013 |

---

## F. 验证记录

| 活动 | 环境 | 结果 |
|---|---|---|
| git 基线命令 | 本地仓库 | 见 Brief §1.1 |
| 源码 grep/read | `6ba817f` 工作树 | KPI/tool_sheet/pilot/publish/setup |
| pytest / check.py | — | **未执行** |
| verify_frontend | — | **未执行** |
| 浏览器逐页 | — | **未执行** |
| 外部标准 APQC/BPMN | — | **未核原文** |

---

## G. 决策日志（待用户 / 待技术 / 已约束）

| 项 | 状态 | 影响文档/范围 |
|---|---|---|
| 七项 TR-DEC（冻结/幂等/Gate/KPI样本/删除/权限/试点窗口） | 待技术定值 | C04 §3.2, artifacts §4 |
| 十层第 6 层 breaking | 待用户 | DR-003, 种子/demo |
| 是否合并本地 dev-plan/追溯表 | 待用户 | DR-010, C04 footer |
| publish 语义 | **已约束** | 不可改为「仅审批」 |
| 四结论非阶段机 | **已约束** | — |
| S1–S5 实施 | 建议方案 | C16，非已批准批次 |

---

## H. 基线外修订说明（供终审）

工作区 **staged** 修改试图：链追溯表/brief、扩展 principles §9–§10、更新 spec 基线语句。这些**不在** `6ba817f` 合并历史中。终审时应：

1. 要么 `git commit` 全套（含 reviews 本文 + 未跟踪计划文档）；  
2. 要么 `git restore --staged` 回到纯 `6ba817f` 再重新应用修订。

本评审 **DR-* 结论对 `6ba817f` 成立**；对 staged 文本未单独重审全文。

---

*独立评审完成；等待原助手终审，不执行修订建议。*
