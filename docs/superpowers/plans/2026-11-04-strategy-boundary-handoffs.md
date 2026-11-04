# M3 战略、边界与交接 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans原生实施。用户已要求合并M2后继续既定M3；不重开文档评审循环、不自动发布M3。步骤复选项用于实际进度。

**Goal:** 同一流程从客户/战略结果进入原章程及SIPOC横向交接，记录责任、质量、期限、例外与实际双方确认，流程卡能读到原产物。
**Architecture:** 扩原ProcessCharter与ToolSheet，不建ProcessHandoff/第二任务引擎。章程用结构化details及修订号，原审计保留完整变更快照；交接是SIPOC产物的可选结构化用途，原表保留不可变正文/模板版本及独立双方确认。原目标/Owner/RACI/标准版本只引用。
**Tech Stack:** FastAPI/Pydantic/SQLAlchemy、Alembic、原生ES、pytest、Playwright。
**Spec:** docs/implementation-next-brief.md M3；docs/bpm-lifecycle-implementation-spec.md R1-02/03；enterprise-process-strategy-loop.md §4；process-organization-governance-loop.md。

## Global Constraints
- 八阶段导航、项目五阶段及原主跳转不变；流程长期存在，无项目也能办理。
- Owner只读ProcessArch.owner_user_id，不复制编辑；系统角色不证明实际资源授权。
- 原数据不自动补客户/授权/确认；缺项为未记录，不回填批准。声明与本人确认分开。
- schema只走Alembic，UTC存储/出参+00:00，日期不按JS Date解析。
- 交接可成环/可同流程，不当目录父子关系；共享标准只固定版本ID，不复制文件。
- 不将模板保存写成EFFECTIVE，不新建项目或推动阶段；原SIPOC普通填写兼容。

## Review Focus
1. 旧章程更新不清空新字段；并发旧修订409，审计保留修改前后。
2. SIPOC交接接收流程/账号/模板/标准引用非法拒绝；组织不可见404，不泄露原数据。
3. 管理员代填不代双方签收；只允许指定本人确认，拒绝/待确认不报通过。
4. 同一产物两方确认并发不丢失；固定正文/模板不被确认修改。
5. 原方法/章程入口与流程卡刷新返回不串流程；无项目可用。

## 文件职责
- models/startup.py、schemas/startup.py、services/startup.py：章程扩details/revision，旧API兼容；新增GET/PUT /start/charters/{process_id}，原POST共同写逻辑。
- schemas/tool_sheet.py、models/tool_sheet.py、services/tool_sheet.py、services/handoff.py：SIPOC可选交接契约、来源模板版本、双方确认与可见性；不新增主表。
- api/v1/startup.py、tools.py、schemas/process_card.py、services/process_card.py：原入口写入与只读聚合。
- web/js/views/shared/process_context.js：流程章程与交接操作共享组件；process_card.js呈现，strategy/map提供正确流程入口，原tool_sheet.js可选交接字段。
- tests/test_process_context.py、tests/test_migrations.py；scripts/verify_process_context.py；verify_frontend登记。

## Task 1：章程与原身份承接
- [x] RED：新GET章程返回原字段、details、revision、当前Owner；无章程明确空态；PUT需要expected_revision；旧POST不丢新details；非L3/无Owner/非法目标/不可见标准拒绝。
- [x] 增量字段details JSON nullable、revision default0；details包含customer/customer_result、objective_id、mandate_version_id/resource_version_id、resource_commitment、review_due、verification_evidence。有值只表示已记录，不派生批准。
- [x] 原审计summary保留before/after JSON；条件UPDATE expected_revision防旧覆盖。新增PUT管理权限沿原章程MANAGER+。
- [x] pytest定向GREEN；migration旧行保留/upgrade/downgrade/schema一致。

## Task 2：SIPOC横向交接与双方本人确认
- [x] RED：普通SIPOC无交接仍兼容；handoff可选字段接收流程、提供/接收账号、质量、时间、例外、可选标准版本；来源模板版本固定；错/不可见引用拒绝。
- [x] 扩ToolSheet template_version_id nullable、handoff JSON nullable、revision default0；保存时校验SIPOC及核心输入输出内容，不复制流程树；项目必须属于所选流程且可见。
- [x] GET /tools/{code}/sheets/{id}只读原记录；POST同路径/confirm：{side,decision,evidence,expected_revision}，decision ACCEPT/REJECT，只有指定本人可写，server记录UTC/身份；条件UPDATE防并发丢另一方。
- [x] 接收确认是声明/交接接受，不证明授权充分或运行效果；输出后端标签“待双方确认/待提供方确认/待接收方确认/存在异议/双方已确认”。
- [x] pytest RED→GREEN：管理员不能代确认、viewer无写权、正确本人可拒绝/修订决定、并发冲突409、正文不变、GET不写。

## Task 3：原页面办理和流程卡汇总
- [x] 原流程卡增加“边界与交接”模块，原章程编辑/客户战略链接、固定授权/资源版本、SIPOC交接列表和本人确认。无数据给明确动作；只显示声明事实。
- [x] 原SIPOC填写modal可选启用“记录横向交接”，原流程预填，账号/接收流程/质量/期限/例外/标准选择；成功仍仅保存方法产物。
- [x] 战略/地图进入同流程流程卡边界模块；RACI/组织/授权动作进入原模块，不新界面主库。
- [x] 专项真实UI先红后绿：无项目、章程保存刷新、交接创建、本人确认、跨流程列表；追加旧弹窗跨流程零写入。管理员不能代签/非法身份/修订冲突由API负例核验，不冒称为UI全覆盖；M2来源返回专项继续通过。
- [x] 完整check.py/pytest、verify_frontend、独立临时SQLite Alembic check，更新brief与限制；M3未获新发布授权不自动提交/推送。

## 最终验证与保留

- M2已提交20fbb92，经PR#16合并c26ac3c，双数据库CI通过。
- M3最终`check.py`557 passed,4 warnings in127.44s，格式/lint通过；完整前端exit0；Alembic临时SQLite无漂移。M3未提交。
- 复核6项Important均有API/浏览器红绿回归；受限章程引用/流程卡摘要、目标原承接、模板换版409、旧弹窗身份及历史标准保留已修正。全站日志偶发流程列表500另补真实DB插入复现并最小修复查询顺序，最终日志未再出现500。
- 保留次要项：模板生效版原函数未核有效期；每方决定未单列标签，见README。真实PostgreSQL并发/业务授权/组织效果未验证；只读调色板因无评审中流程跳过，draw.io协议不代表外部集成验收。

## 裁定
details是原章程字段组而非新事实库；确认只在原SIPOC行留本人决定。任命/资源批准固定原ProcessDocumentVersion，不把文本证据当授权结论。真实组织目标/政策不由开发者设定。原生实施，复用现有工作区功能分支，不创建另一个工作树。
