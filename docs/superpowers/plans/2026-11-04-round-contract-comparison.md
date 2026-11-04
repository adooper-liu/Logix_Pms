# M5 版本、口径与薄轮次对照 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans原生实施。用户要求合并M4后继续M5，不自动发布M5，不重开文档评审循环。

**Goal:** 同轮流程/项目/模型/指标及前后样本当时值可追溯，固定后不覆盖，结果不因项目结项或引用齐全自动通过。
**Architecture:** 单一ProcessImprovementRound薄引用表，原模型沿M4 frozen_at，原KPI/样本不复制主库；轮次JSON只存当时口径/值/来源摘要。确认时间与修订派生可编辑性，不设current_stage/status/advance。原IdempotencyRecord复用；原流程卡提供读写入口。
**Tech Stack:** FastAPI/SQLAlchemy/Pydantic、Alembic、原生ES、pytest、Playwright。
**Spec:** implementation-next-brief.md M5；bpm-lifecycle-implementation-spec.md R2-01/02、§3.2–3.6；bpm-first-batch-dev-plan.md§2.1阻塞需本计划定值。

## 本片契约定值（工程裁定，不伪称业务政策）
- revision是行乐观锁，从0开始；supersedes_id固定前一修订，修订生成新行，旧行不改。新修订只复制前侧草稿依据，清除后侧/验收约定，禁止已有后侧样本后改验收约定。
- baseline_confirmed_at固定现状+口径+前侧样本；acceptance_locked_at在后侧取样窗口开始前固定目标/红线/观察规则/实际指定审核者，均是记录约定，不等于业务批准。
- bind-project、bind-design、bind-published为显式可重试追加动作，expected_revision；不接publish事务hook，不把flush当发布成功。
- 原模型须同流程且冻结，published绑定须published_at真实存在及PUBLISHED/SUPERSEDED。一个版本可同轮多用途，不排斥全局role。
- metric_contracts从原KpiDefinition生成不可变快照+sha256，附用户显式source_semantics/source_evidence、timezone/calendar/filters/exclusions；不按单位推来源，旧取数算法仍列M7待修。未知来源不能确认前侧；声明不冒称数据已独立核实。
- sample_refs选择原KpiRecord IDs；固定period/value/note/project及source_evidence、所用模型角色、质量说明；KpiRecord本身缺模型身份时标“人工核对的来源声明”，不冒称自动运行样本。同一原记录不重复入同侧、不同时作前后；前后窗口互不重叠，全部同流程/同口径，后侧模型取真实发布版本。
- 单轮最多10指标/200样本，窗口日期包含边界；float必须有限；空样本/跨项目/越界/错hash拒绝。前后数值仅并列展示，不自动计算因果、通过率或达标。
- 写沿MANAGER/ADMIN或流程Owner；绑定项目还需可见且与流程一致。ADMIN只管理记录，不天然是业务验收者。GET及幂等重放先校验当前范围；按user/pid/round/action隔离幂等scope。
- 项目/流程/KPI/模型删除受原引用保护（FK RESTRICT+API显式409，SQLite亦测试）；无round删除接口，合法归档不删历史。隐私/法定删除是后续有权专门流程。
- 四结论原有权验收/用途完整能力分别由M6–M8衔接；本片不新增“验收总表”，全部结论显示“待原业务核验”，不以非空字段自动确认。

## Review Focus
1. 固定后KPI定义/数据补录不回写本轮snapshot；修订不洗掉原后侧结果或追认目标。
2. 组织不可见项目/样本/修订/幂等重放不得泄漏，项目绑定不能扩大可见性。
3. 旧revision及同幂等键异载荷冲突；冻结与并发编辑不可双成功覆盖。
4. 非真实发布/跨流程模型、样本窗口/重复/版本混合拒绝，不把人工声明当运行证据。
5. 原页面流程切换、弹窗晚响应、刷新/返回保留round与流程，GET零写。

## Task1 薄轮次模型和固定依据
Files: models/improvement_round.py、schemas/improvement_round.py、services/improvement_round.py、api/v1/improvement_round.py、router.py、migration；tests/test_improvement_round.py。
- [x] RED POST/GET/PATCH /processes/{pid}/improvement-rounds，权限/身份/旧revision/草稿零副作用。
- [x] 表字段：process_id、project_id、supersedes_id RESTRICT；revision；name/scope_note；asis/tobe/released_model_version_id RESTRICT；metric_contracts、baseline_window、baseline_samples、acceptance_snapshot、after_window、after_samples、model_hashes JSON；baseline_confirmed_at/by、acceptance_locked_at/by、created_at/by、updated_at。无独立stage/status。
- [x] lock-baseline核固定现状、原KPI快照/显式语义、前侧样本，CAS写确认时间；固定后PATCH409；revise新行复制前侧，重确认且保留原行。
- [x] 定向红绿及迁移历史/升降级/schema一致。

## Task2 追加项目/方案/发布、验收约定和后侧
- [x] RED bind-project/design/published、lock-acceptance、capture-after；每动作expected_revision及原幂等能力，权限先于重放。
- [x] 验收约定目标/红线/观察/审核者非空，后侧窗口从锁定后开始；capture-after使用原metric hash及发布模型角色，原数值/来源固定。
- [x] 写审计；删除原对象显式409；普通KPI来源不在本片批量重构。只读对照显示当时事实/缺项，无自动四结论通过。
- [x] pytest跨流程/越权/重复/hash/越界/改后反填/原值变化/保留/幂等/冲突红绿。

## Task3 原流程卡对照办理与全量验证
Files: shared/improvement_round.js、process_card.js；scripts/verify_improvement_round.py；verify_frontend登记。
- [x] 模块“轮次对照”：选中明确轮次、四身份摘要/缺项；新建草稿、前侧输入/固定、项目/设计/发布追加、验收约定锁定、后侧取样、修订，全部在原流程卡；不加顶级导航。
- [x] 原KPI/样本选择源数据；来源声明/质量/窗口说明清楚；显示冻结公式与当时值，原值变化不静默覆盖，未知不伪绿。
- [x] 真实UI先红后绿：无项目创建、固定/刷新、已固定不可改、选轮次/返回/跨流程隔离、非法输入保留；API补身份/时间/权限负例。
- [x] 完整check.py/pytest、当前服务verify_frontend、独立SQLite Alembic check和分支复核；brief记录限制，不自动发布M5。
