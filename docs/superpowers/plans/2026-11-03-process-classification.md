# M1a 三类型分类闭环 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans原生执行；用户已要求规划并逐个落地，不另启文档评审。下列步骤为本片执行清单，Git提交/推送另需授权。

**Goal:** 将核心/支持/管理正式接入唯一企业流程目录，提供有依据的分类、继承/例外/未知、查询筛选和原页面维护。

**Architecture:** 原ProcessArch扩分类字段，独立process_classification服务负责唯一解析/标签/验证。分类写API原子校验修订，列表树详情与流程卡共用解析；地图独立分类动作，不重写大地图或复制目录。

**Tech Stack:** FastAPI/SQLAlchemy/PostgreSQL＋SQLite、Alembic、pytest、原生ES模块、Playwright。

**Spec:** [主线brief M1a](../../implementation-next-brief.md)、[总规格R1-01](../../bpm-lifecycle-implementation-spec.md)、[路线§3](../../bpm-lifecycle-gap-and-roadmap.md)。

## Global Constraints

- 三类型不是层级/项目阶段/成熟度；不改priority_score，不自动回填历史或PCF。
- 代码CORE/SUPPORT/MANAGEMENT，中文仅后端下发；未知为null，显示未明确，不伪造第四业务类型。
- 原目录唯一，原地图写权限MANAGER/ADMIN；分类动作不修改模型发布、Owner或项目。
- nullable process_type，classification_basis文本，classification_inherit默认true，classification_revision默认0。明确类型必有依据；显式阻断继承也要依据。
- nearest明确祖先继承，遇inherit=false且未明确即阻断；显式跨类型有依据即可，输出例外与来源。循环/缺祖先不无限递归，不猜其他流程。
- 用独立PUT /process-map/{id}/classification，body含全部分类字段及expected_revision；冲突409不覆盖。原通用PATCH不增加分类字段，避免绕过revision。
- 无生产库操作；测试临时SQLite，迁移验证新隔离库；不提交现有文档/暂停修复。

## Review Focus

1. 历史/PCF创建节点均未明确，不按名字推断——Task1迁移/历史测试。
2. 祖先改变后继承实时更新，显式子例外不变——Task1解析与Task2接口。
3. null继承/主动阻断不同，清除明确类型需显式策略——Task2完整body校验。
4. 并发revision冲突及只读/OWNER写拒绝——Task2 API测试。
5. 类型筛选保留祖先路径且祖先不计匹配，刷新恢复——Task2树测试和Task3UI。

## Task 1: 数据与解析

Files: models/process.py、schemas/process.py、services/process_classification.py（新）、alembic/versions/s4d5e6f7a8b9_process_classification.py（新）、tests/test_process_classification.py（新）。

- [ ] 先写树链解析测试：CORE父→继承子；显式SUPPORT子带依据，is_override=true；null/inherit=false阻断；全null未明确；cycle安全失败。
- [ ] 红例因缺字段/服务失败后增原表字段及迁移，不种子分类。
- [ ] 服务 `resolve_all(rows: list[ProcessArch]) -> dict[int, dict]`返回effective_process_type、process_type_label、classification_source_id/code、classification_is_inherited、classification_is_override；标签常量与meta集中该服务。row自身的process_type/basis/inherit/revision为保存事实。
- [ ] 解析测试绿；test_migrations全链升级/对齐/回退通过。

## Task 2: API、原子写与原消费

Files: api/v1/process_map.py、schemas/process.py、schemas/process_card.py、services/process_card.py、tests/test_process_classification.py。

- [ ] 写API红例：GET meta三值中文；PUT正确存储、空依据422、非法类型422、陈旧revision409、viewer/owner403；flat/tree/detail/card解析一致。
- [ ] PUT完整分类输入，服务校验依据/策略；SQL UPDATE where id/revision CAS，revision+1，原审计record并commit。不要先CAS提交后再写其他字段。
- [ ] 读出共用resolve_all，列表/树批量读取，不逐节点请求DB；卡片只透传同一服务结果。
- [ ] flat/tree增加process_type筛选（CORE/SUPPORT/MANAGEMENT/UNCLASSIFIED，仅查询哨兵）；树按命中向上保留祖先；输出classification_matches_filter标记上下文祖先。无筛选全部true，原improvement_only行为不顺手重构。
- [ ] API/权限/冲突/筛选测试绿；旧流程API测试不回归。

## Task 3: 地图与流程卡实际维护

Files: web/js/views/map.js、process_card.js；scripts/verify_process_classification.py（新，轻量专项，用已有隔离app工具但不把旧工具业务测试混入）；scripts/verify_frontend.py仅接入共享检查（若旧全站断言阻塞保留报告，不修改无关断言）。

- [ ] 浏览器先红：地图详情缺分类维护按钮/下拉；seed历史显示未明确。
- [ ] 地图加载meta，类型筛选与URL同步、切换重置路径/清树缓存；GET tree按筛选取，匹配祖先显示“路径上下文”，该标记中文来自meta。
- [ ] 列表/详情显示后端类型标签与继承来源。MANAGER/ADMIN详情“维护分类”打开单一主题modal：选择明确类型/按上级继承/暂不分类、依据、当前revision；PUT成功清缓存刷新，冲突保留输入并提示刷新，不自动重试。
- [ ] 流程卡顶栏显示同一类型/来源，链接原地图，不复制编辑器。
- [ ] 用真实API创建无名义分类的测试父/子，在真实地图维护父CORE、子继承/显式SUPPORT/阻断，核接口、页面、筛选祖先与刷新；finally仅删本次新根。
- [ ] 后端全量pytest/check.py，专项真实浏览器绿，verify_frontend记录实际结果，隔离SQLite Alembic upgrade head/check通过。

## 执行记录

2026-11-03，工作区feat/process-framework-alignment，未提交：

- Task1/Task2已落地，分类/迁移定向11例通过；新增及通用更新返回值也共用继承解析。
- Task3主体已落地，真实UI验证CORE/SUPPORT/MANAGEMENT、继承/例外/阻断、筛选刷新、修订冲突输入保留与流程卡通过；map.js静态文件核当前字节内容。
- scripts/check.py：538 passed,4 warnings，格式/lint通过；临时SQLite Alembic升级/check无漂移。
- 全站verify_frontend确实调用M1a共享检查并PASS，之后其他交互失败；180秒停止，退出124。Task3全站验收未完成，不能标完整交付。
- 没有新增平行目录、未按名称/PCF回填分类、未改优先级/项目阶段；本片不含横向交接主数据及组合排序政策。旧工具保存修复保留但不计M1成果。

## 执行与证据

每任务完成更新主线brief状态，不以该片完成宣称八阶段已全对齐。所有测试PASS是期望，实际输出执行后填入；旧工具保存代码及文档修订不计本片改动。不派新文档评审，不Git发布。
