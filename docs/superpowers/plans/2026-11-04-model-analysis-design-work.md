# M4 建模—分析—设计作业 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans原生实施；用户要求合并M3后继续既定M4。不自动发布M4，不重开文档审定循环。

**Goal:** 原设计器/分析页可直接保存现状确认、分析交付、方案取舍和指定接收方核验，固定原模型及输入产物，不以模板数量证明有效。
**Architecture:** 原ProcessModelVersion加frozen_at，冻结只保护正文/XML不影响运行指针；之后原save_draft新建工作版。原ToolSheet加work_context/review，保存append-only作业引用和本人核验，沿既有revision条件更新；无WorkProject/方案主表/阶段机。只读workbench聚合返回原记录与能力限制。
**Tech Stack:** FastAPI/SQLAlchemy/Pydantic、Alembic、原生ES、pytest、Playwright。
**Spec:** implementation-next-brief.md M4；bpm-lifecycle-implementation-spec.md R2-03/§3.1；process-analysis-method-chain.md；process-design-small-loop.md；process-modeling-repository-gap.md。

## Global Constraints
- 八阶段仅导航、项目五阶段不变；原主跳转、同一设计器保留；无项目可办理。
- M5负责正式轮次/冻结KPI口径与样本；本片只固定原模型和原方法产物，不声称正式改善闭环已实现。
- 数据来源区分实测/访谈/模型估算/演练/未知；模板与算法能力分开。演练/未知不能被接收为真实业务依据。
- 方法作业只追加；接收决定附用户/时间/依据，技术校验不代业务核验；接收不发布/达标。
- 枚举标签后端唯一；schema走Alembic，UTC出参+00:00，不引入构建或视图互import。

## Review Focus
1. 冻结模型后原编辑/导入/回滚不得覆盖或删除原正文/XML；版本号不重用，运行表/发布指针不变。
2. 模型/上游作业/项目身份必须同流程且可见；GET不写冻结/状态。
3. 指定接收者本人决定，不允许作者自验或管理员代签；空依据/旧修订/未知或演练准入拒绝。
4. 分析/设计可先记缺口；接收必须引用对应已接收前序，后续不能因上游后改决定悄悄保持有效。
5. 原页面切流程/异步返回不得串记录；保存失败保留输入；缺模型和无数据指引准确。

## Task 1：原模型不可变作业引用
Files: models/process.py、schemas/process.py、services/process_model.py、api/v1/designer.py；migration；tests/test_workbench.py。
- [x] RED：POST /processes/{id}/design/freeze {expected_version,note}固定当前原版本，frozen_at非空；GET不冻结；越权/旧版本拒绝。
- [x] frozen_at nullable；save_draft只覆盖未冻结DRAFT，否则新工作版；rollback不删冻结草稿，原publish不改冻结snapshot/XML。未冻结草稿删除后的版本号复用是保留次要项，不宣称完整不复用保证。
- [x] 定向模型/迁移测试GREEN，原运行指针和live节点不变。

## Task 2：原ToolSheet作业与核验
Files: models/tool_sheet.py、schemas/workbench.py、services/workbench.py、api/v1/workbench.py、router.py；handoff.require_sheet扩work引用范围；tests/test_workbench.py。
Interfaces: GET /processes/{id}/workbench；POST /processes/{id}/work-records；POST /processes/{id}/work-records/{sheet_id}/review。
- [x] RED：kind MODELING/ANALYSIS/DESIGN，model_version_id必须同流程且已冻结或PUBLISHED/SUPERSEDED；project可空；upstream_sheet_id可空但存在时同流程/权限。
- [x] 原ToolSheet work_context字段：kind、model_version_id、source_kind、customer_result、problem、findings、evidence、limitations、next_action、reviewer_user_id、due_date、upstream_sheet_id；DESIGN补alternatives、choice_reason、controls、validation、rollback。原BPMN/FIVE-WHY/TOBE作为方法归属，模板版本如有固定，不造独立资产。
- [x] review {decision ACCEPT/RETURN/OBSERVE/STOP,evidence,expected_revision}；本人且非作者，条件更新；MODEL接收真实来源，ANALYSIS接收需已接收MODELING，DESIGN需已接收ANALYSIS。模型估算只能记录估算用途，不接收为真实现状；上游后来退回时输出“上游需复核”且下游不能再通过。
- [x] 原详情/聚合组织权限贯通；后端返回kind/source/decision标签及能力限制；GET不更新业务。
- [x] API红绿：错流程、项目不可见、代签/自签、旧revision、演练/未知拒绝、退回与后续影响、正文不改。

## Task 3：原页面作业组件及完整验收
Files: web/js/views/shared/workbench.js、designer/index.js、monitor.js；scripts/verify_workbench.py；verify_frontend登记。
- [x] 同一designer建模/设计模式由lifecycle区别，原普通入口可选用途；原monitor analysis办理ANALYSIS。共享组件展示任务、固定模型、原上游、来源与限制、记录列表/本人核验；方法填写/原专业画布保留。
- [x] 直接“固定当前模型”“记录本步产物”，表单无项目默认；指定核验者、输入原记录，缺证可保存但不报已通过。
- [x] 真实UI先RED后GREEN：同画布两用途、固定不发布、三类产物写入与刷新；追加显式项目与核验弹窗切流程/延迟响应守卫。API补权限/冲突/来源准入负例，M2返回来源继续回归；不冒称所有失败输入UI均已逐项覆盖。
- [x] pytest/check.py、完整verify_frontend、临时SQLite Alembic check，原模型发布回归；文档记录实现与未实现算法/样本边界。

## 裁定
本片fixed_at保护原模型版本是前置作业引用的最小条件，不替代M5薄轮次。原稿可继续编辑为新版本；不自动选未来方案、不新建方案库。ABC/专业仿真/正式根因裁决仍仅按原能力标限制，新增作业接收不能绕过原项目根因门。原生功能分支实施，未经新授权不发布。