# M7 监控—异常—改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 用户已要求合并后继续下一步，沿既有主线实施，不再开启总路线评审。

**Goal:** 在原KPI/样本/异常上贯通显式取数、质量/身份、责任行动与核验，向薄轮次提供可回查后侧正式样本。
**Architecture:** KpiDefinition补原测量约定JSON；KpiRecord补原来源/窗口/模型/round与质量快照及revision，沿原表保存修订依据，不建指标/样本主库。ExceptionEvent扩处置核验字段组/revision，原状态更新不能绕核验；保留人工确认候选、原改善入口及项目五阶段。
**Tech Stack:** FastAPI、SQLAlchemy2、Alembic、SQLite/PostgreSQL、原生ES模块；零构建。
**Spec:** docs/implementation-next-brief.md M7；docs/bpm-lifecycle-implementation-spec.md R4/§3.2；docs/process-performance-decision-loop.md §5–7/11–12。

## Global Constraints
- 唯一目录三类型、八阶段导航、项目current_stage1–5不变；不新增Decision/Action/指标台账。
- 不按单位猜来源；现有同为小时的周期/等待/投入不应被写成同一个值。
- 历史来源UNKNOWN，不猜模型/轮次，不将seed/demo记录当运行实测。
- 正式前后对照取冻结口径与各侧真实模型/窗口；数据质量与绩效状态分开。
- 原图表不重做；当前黄阈值作为红绿区间参考，不假称独立统计控制限。
- 真外部ERP/Flowable/生产组织效果未验证不说完成；正式四结论仍M8有权核验。

## Review Focus
- 多个相同时间单位但不同事件语义的指标：只有显式实例历时绑定可回写；测试Task1。
- 空/零/过期/来源不明：不得未知洗绿；测试Task1/2。
- 混合模型/round/project月均：不能固定成单一后侧正式样本；测试Task2。
- 旧revision关闭/重复候选/关闭后复发：原异常保留本次判断、行动/核验，不绕门；测试Task3。
- 原页面切指标/流程/modal旧响应：输入不串、晚响应不关闭新表单；测试Task4。

### Task 1: 显式原测量约定与来源判断
**Files:** app/models/monitor.py、schemas/monitor.py、services/kpi.py、api/v1/monitor.py、migration；tests/test_monitor_decision_loop.py。
**Interfaces:** KpiDefinition.measurement JSON（source_kind=EXECUTION_ELAPSED/INBOUND/MANUAL/UNKNOWN，event=instance.completed，aggregation=MEAN，timezone=UTC，calendar=ELAPSED，minimum_samples>=1，freshness_days>=1，purpose/response_note）；原GET/meta返回后端来源/质量标签。
- [x] RED：未配置小时KPI intake DRAFT；显式EXECUTION_ELAPSED且单位时间/月频可接受；等待/工时等不支持绑定拒绝，不回落按单位。
- [x] RED：更新原定义对测量契约的修订保留在原审计，历史原样本不换口径；给新字段Alembic nullable，不猜回填。
- [x] 实施intake_kind仅显式测量约定允许EXECUTION，兼容既有INBOUND配置但质量未知；更新种子展示为演示/未知（不以回填假称正式来源）。
- [x] Run pytest tests/test_monitor_decision_loop.py tests/test_kpi_definition.py，Expected业务行为断言通过；旧“时长自动正式”断言按新契约更新并实测。

### Task 2: 原样本来源/质量/身份与薄轮次承接
**Files:** 原monitor模型/schema/API、services/kpi.py、services/improvement_round.py、tests。
**Interfaces:** KpiRecord.provenance JSON + revision；样本快照包含source_kind、original_instance_ids（有界）、window_start/end、process/project/model_version_id/round_id、contract_snapshot/hash、quality状态/原因。旧记录为UNKNOWN。
- [x] RED：显式实例周期仅写对应KPI；来源实例不足/混合模型或round拒作正式同轮样本，保留原值与不可信原因；未完积压另展示不混入完结周期。
- [x] RED：相同期间修订保留前值/依据于原审计，冻结round快照不变；原实例在途不受采集更改。
- [x] RED：improvement_round取样使用可核原provenance，匹配本侧模型/项目/round/口径/窗口；人工声明仍明确待核，错身份拒绝。
- [x] 实施来源快照及质量读取；不把钩子启用当质量有效；质量未有效时presentation灰，不把数据故障候选当业务红黄。
- [x] Run pytest tests/test_monitor_decision_loop.py tests/test_improvement_round.py tests/test_inbound.py，Expected通过。

### Task 3: 原异常判断—行动—核验与改善
**Files:** models/monitor.py、schemas/monitor.py、api/v1/monitor.py、services/exception_intake.py、services/improvement.py，新增services/exception_review.py如原文件职责需要；tests。
**Interfaces:** ExceptionEvent.resolution JSON/revision；保存原当次KPI/样本/窗口快照、decision/action_ref/evidence/expected_result/review_due、核验人/本人决定；POST /monitor/exceptions/{id}/review带expected_revision。
- [x] RED：措施执行但无核验不能CLOSED；指定非作者本人按约定核验；退回/重开不留有效旧结论，revision冲突409。
- [x] RED：来源/组织范围先核，写入锁原流程后同来源在途去重；原关闭后允许复发，不每次红黄自动立项。更细“仅新样本才算复发”规则仍后续，不冒称本片已交付。
- [x] 实施沿原权限/Owner、原项目draft动作，同轮/项目显式验证；不另建行动任务中心。
- [x] Run pytest tests/test_monitor_decision_loop.py tests/test_breakpoints.py tests/test_improvement.py，Expected通过。

### Task 4: 原页面办理及全门禁
**Files:** views/monitor.js、views/shared/measurement.js按需、scripts/verify_monitor_decision_loop.py、verify_frontend.py、README/implementation brief。
- [x] RED真实浏览器原KPI定义卡维护取数语义、质量/来源与缺项显示；异常原弹窗处置/本人核验，错误保留输入；显式流程/任务/modal代号。
- [x] GREEN原页面办理/刷新与前后样本可回查，不新导航/看板。
- [x] Run python scripts/check.py、独立Alembic upgrade/check、当前隔离服务完整verify_frontend，Expected exit0并逐项记录未验证外部/生产能力。
- [x] 原生执行一次整分支复核；Important红绿修正，Minor记README；未经用户本片发布授权不额外推送合并。
