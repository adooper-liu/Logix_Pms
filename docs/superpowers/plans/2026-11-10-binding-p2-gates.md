# P2′ 使用入口绑定门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 模型发布允许缺项并告警，执行上线确认检查执行版，资产包和岗位责任书评审／批准／生效检查绩效版，来源改变不能沿用旧绿灯。

**Architecture:** 在现有 binding_readiness 服务增加档位投影，不复制四面判定。所有使用点重算指定原发布模型的绑定完整度和一致性；沿现有执行配置指纹、编译清单及文档状态机实现失效，不新增部署台账、状态表或迁移。

**Tech Stack:** FastAPI、SQLAlchemy 2.0、Pydantic、SQLite/PostgreSQL、原生 ES 模块、pytest、Playwright。

**Spec:** docs/process-binding-dev-plan.md §6；docs/process-operating-binding-model.md §3.2、§7。

## Global Constraints

- 模型发布「不改阻断，只写快照 + 返回告警」，沿用既有评审、变更单与不可变固定依据约束。
- 执行版 EXECUTION：活动映射、岗位、唯一 A、已验证标准工时、表单／记录载体及必要判断规则。原准备适用性不能豁免这些绑定必需项。
- 绩效版 PERFORMANCE：四个面；KPI/SOP/证据沿现有四面规则，不新加全流程一刀切的运行效果证明。控制点或受支持的控制证据仍按原 METHOD 规则处理。
- 草稿与诊断仍允许呈现缺口，原来源身份硬约束不放松。
- ReadinessBlockerOut 保持 code / message / targets；MODEL_NOT_VERSIONED 等原码语义不变。
- 不新建资源／责任主数据，不在前端维护枚举中文，不引入构建工具。
- 不扩大至 P3、职级／能力／人数配置；实际业务库迁移与应用升级独立于本片。
- 保持 pageShell 与单主题 section；只修改既有页面的缺口展示，不重做页面壳。

## Review Focus

- 工作版变化不得替代原发布版本参与门禁；原发布绑定变化必须使确认失效。（Task 1、2）
- 多节点同活动时，节点唯一 A 和岗位不能由其他节点补齐；默认表单不能冒充直接载体。（Task 1）
- 资产包不能通过通用文档 transition 绕过专用 API 门禁；退回草稿与退役不能被完整度卡住。（Task 3）
- 岗位产物只检查该岗位参与活动，但不能遗漏其中缺岗位／责任或受限来源；无关活动不阻断。（Task 4）
- 补齐来源后必须新固定依据、新编译，不能拿旧产物或历史绿灯继续批准；GET 不写业务行。（Task 2、3、4）

---

### Task 1: 共用档位投影与模型发布告警

**Files:**

- Modify: app/schemas/binding_readiness.py
- Modify: app/services/binding_readiness.py
- Modify: app/services/process_model.py
- Modify: app/schemas/process.py
- Modify: app/api/v1/designer.py
- Test: tests/test_publish_gate_bindings.py

**Interfaces:**

- Consumes: activity_bindings(db, process_id, user=None, *, model_version_id=None) -> ActivityBindingsOut。
- Produces: BindingGateOut(profile, profile_label, model_version_id, consistency, consistency_label, blockers: list[ReadinessBlockerOut], warnings: list[str], fingerprint: str, ready: bool)。
- Produces: binding_gate(db, process_id, user=None, *, profile: str, model_version_id=None, activity_ids: Optional[set[int]]=None, require_confirmed: bool=True) -> BindingGateOut。
- Produces: ProcessModelOut.binding_warnings: list[str]；发布预览复用现有 warnings。

- [x] **Step 1: 写失败测试。** test_missing_a_allows_publish_but_blocks_execution_and_performance 断言实际发布 200、binding_snapshot 非空、发布响应和预览有绑定告警、两个档位 ready=False，blockers 有 BINDING_TEAM_INCOMPLETE，targets 含原节点键。test_profile_projection_uses_one_readiness_result 断言 TEAM/RESOURCE 齐而 GOAL/METHOD 缺时执行版 ready=True、绩效版 ready=False。
- [x] **Step 2: 运行 RED。** `python -m pytest tests/test_publish_gate_bindings.py -q`，应因缺档位接口／告警断言失败。
- [x] **Step 3: 实现共用投影。** EXECUTION 取 TEAM/RESOURCE；PERFORMANCE 取全部四面；节点映射使用原 NodeBindingOut.blockers。活动筛选只保留相关节点／活动，未实现活动在全流程绩效版列缺口；空模型不判绿。来源一致性沿 binding_snapshot，不解析中文 gaps 来决定业务状态。指纹对档位、指定模型身份、当前绑定来源内容及投影结果做确定性 hash，排除 captured_at。require_confirmed=False 只用于模型发布告警。更新原“绑定不改变门禁”的说明。
- [x] **Step 4: 补边界并跑 GREEN。** test_node_scope_does_not_cover_sibling、test_default_form_does_not_satisfy_carrier、test_gate_uses_requested_published_not_latest_draft、test_gate_is_read_only 验证节点独立责任、默认表单、显式发布身份、业务表计数不变；定向 pytest 全通过。

### Task 2: 执行上线确认及原指纹失效

**Files:**

- Modify: app/services/execution_readiness.py
- Modify: tests/test_execution_readiness.py
- Test: tests/test_publish_gate_bindings.py

**Interfaces:**

- Consumes: Task 1 binding_gate(... profile='EXECUTION', model_version_id=原发布主键)。
- Produces: execution_readiness.get 响应新增 binding_gate；missing 汇总绑定阻断，fingerprint 包含 gate.fingerprint。confirm 保留指定本人、修订号与原适用性规则。

- [x] **Step 1: 写失败测试。** test_not_applicable_cannot_waive_execution_bindings 断言原准备三项 NOT_APPLICABLE 时缺 A 仍不能 ACCEPT；RETURN 仍允许。test_binding_change_invalidates_confirmation 先以完整绑定确认，再改变 A／标准工时／载体，断言 confirmed=False、fingerprint 改变、重新 ACCEPT 被拒。
- [x] **Step 2: 运行上述测试验证 RED。** 使用 `python -m pytest tests/test_publish_gate_bindings.py -q`。
- [x] **Step 3: 接入原 get/confirm。** 在 get 计算发布绑定档位、合入 missing 和 fingerprint；不另存绿灯，不改变旧实例身份或无轮次实例启动政策。执行版确认必须绑定原发布固定依据。
- [x] **Step 4: 更新原成功夹具并运行 GREEN。** tests/test_execution_readiness.py 成功路径补真实合成活动、岗位、A、已验证工时与直接载体；保留未配置原结构化表单／分派／时限的既有事实断言（可用生效活动记录文件满足载体而不伪造结构化表单）。运行 `python -m pytest tests/test_execution_readiness.py tests/test_publish_gate_bindings.py -q`。

### Task 3: 资产就绪度与两种状态流转入口

**Files:**

- Modify: app/services/asset_graph.py
- Modify: app/services/asset_package.py
- Modify: app/services/process_document.py
- Modify: tests/test_asset_graph.py
- Test: tests/test_publish_gate_bindings.py

**Interfaces:**

- Consumes: Task 1 PERFORMANCE gate，原 ReadinessBlockerOut。
- Produces: asset_package.validate_for_transition(db, document, version, target, user) -> None，供通用文档状态机与专用资产包入口共用。
- Produces: 新资产清单 binding_fingerprint，保留原清单字段。

- [x] **Step 1: 写失败测试。** test_asset_draft_allowed_review_blocked_missing_a 断言生成草稿成功、专用和通用入口 IN_REVIEW 均 409；test_asset_approval_rechecks_sources 在进入评审后改变来源，APPROVED/EFFECTIVE 均阻断；test_asset_return_and_retire_remain_available 验证 DRAFT／RETIRED 不被完整度卡住。
- [x] **Step 2: 运行定向 pytest 验证 RED。** 失败应是门禁缺失或通用入口绕过，而非夹具错误。
- [x] **Step 3: 合并重复规则。** asset_graph.readiness 的责任／载体／映射完整性改为使用共用 gate 输出，不再把 owner_role 文本当岗位。保留原证据冲突／到期等阻断码和旧指标字段。can_generate_draft 保持原身份／映射硬约束；can_submit_review 使用绩效版。指标取同源绑定结果。资产包编译清单记录门禁指纹；正式流转重算并对清单，历史清单缺指纹须重新生成，禁止悄悄追认。
- [x] **Step 4: 连接共享状态机并运行 GREEN。** 通用 process_document.transition_version 对 COMPILED 流程资产调用同一验证函数；专用入口不复制算法。更新原“可评审”夹具使四面真实齐备，保留证据冲突仲裁独立断言，诊断只沿原硬阻断，不被绩效缺项卡死。运行 `python -m pytest tests/test_asset_graph.py tests/test_publish_gate_bindings.py -q`。

### Task 4: 岗位责任书绩效版门禁

**Files:**

- Modify: app/services/job_description.py
- Modify: app/schemas/job_description.py
- Modify: tests/test_job_description.py
- Test: tests/test_publish_gate_bindings.py

**Interfaces:**

- Consumes: Task 1 PERFORMANCE gate，activity_ids 为 coverage.activities 中该岗位同流程活动集合。
- Produces: JobDescriptionPreviewOut.binding_gates 列出参与来源的档位结果；can_submit_review 独立于 can_compile。

- [x] **Step 1: 写失败测试。** test_job_draft_allowed_but_review_blocked_missing_bindings 验证固定身份可编译草稿但缺 A／KPI／标准文件不能评审；test_job_gate_ignores_unrelated_activity 验证同流程其他无关活动缺项不阻断；test_job_transition_rechecks_each_stage 验证 IN_REVIEW、APPROVED、EFFECTIVE 均重算。
- [x] **Step 2: 运行定向 pytest 验证 RED。** `python -m pytest tests/test_job_description.py tests/test_publish_gate_bindings.py -q`。
- [x] **Step 3: 接入预览与原状态守卫。** 绑定缺项加入可追溯 gaps，不加入 identity_blockers；保持缺项草稿可编译。正式流转先核原 input_hash 与权限，再核岗位相关活动绩效版；返回 code/message/targets，受限来源不输出隐藏正文。原 role_position 歧义与 SOURCE_RESTRICTED 检查不删。
- [x] **Step 4: 运行 GREEN。** 原责任书全生命周期成功夹具补齐四面；来源变动必须重新固定原模型、新预览、新编译才可继续。运行责任书、岗位覆盖、P2复核及新增门禁测试。

### Task 5: 使用入口提示、浏览器专项与整片验收

**Files:**

- Modify: web/js/views/shared/execution_readiness.js
- Modify: web/js/views/responsibility.js
- Modify: scripts/verify_binding_p2.py
- Modify: scripts/verify_execution_readiness.py
- Create: scripts/verify_binding_gates.py
- Modify: scripts/verify_frontend.py
- Modify: docs/process-binding-dev-plan.md

**Interfaces:**

- Consumes: 后端档位标签、blockers 的 code/message/targets、责任书 can_submit_review。
- Produces: verify_binding_gates(page, base)，接入全站验证。复用原设计器深链，不新增页面／录入入口。

- [x] **Step 1: 写浏览器失败场景并观察 RED。** 合成缺 A 流程发布成功且有告警，执行页与岗位页显示阻断并能回原节点；通过真实 API 尝试不能提交。修补来源并新工作版固定后成功；来源再变化显示待复核。只读账号仍无写入口。
- [x] **Step 2: 增加最小提示。** 执行页展示档位阻断及原节点入口；责任书预览分开“可生成草稿”和“可提交评审”，缺口点回已有设计器；不重排页面壳、不新增前端枚举表。原合成浏览器成功路径补齐真实绑定，不删结果断言。
- [x] **Step 3: 跑专项 GREEN。** `python scripts/verify_binding_gates.py`，使用 isolated_app 临时 SQLite／动态端口，验证当前静态源码，记录页面异常与服务器 500。覆盖 1440／1024、刷新与只读。
- [x] **Step 4: 完整工程检查。** `python scripts/check.py` 必须退出 0，保存完整输出；另核定向测试。若基线或既有场景失败，逐项定位，不以跳过换绿。
- [x] **Step 5: 完整前端检查。** 使用 isolated_app 启动当前工作树新服务，在上下文中运行 `python scripts/verify_frontend.py <base> <证据目录>`；完整执行到底，退出 0 才算通过。只清理本次创建的进程与临时数据。
- [x] **Step 6: 迁移漂移与收尾。** 无 ORM 变更；仅专用 SQLite 执行 `alembic upgrade head` / `alembic check`，应输出 `No new upgrade operations detected.`，不连接业务库。按可用性补专用 PostgreSQL验证，不把 SQLite 冒称 PG 验证。更新 P2′ 实施记录及限制，保存命令证据，检查最终差异；本片通过独立 PR 集成，业务环境升级另行管理。
