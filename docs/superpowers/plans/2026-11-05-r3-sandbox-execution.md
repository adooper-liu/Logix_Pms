# R3 Sandbox Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 用户已明确要求计划后原生执行；不再次停在执行方式选择，不派子代理。

**Goal:** 在独立合成数据沙箱内，从原PMS发布版本部署并启动Flowable串行/并行人工任务，经原执行页办理并可恢复、对账；Legacy在途不迁移。

**Architecture:** 原模型/实例/任务增加固定provider身份，新增薄部署映射、持久命令和事件收件/游标。Runner新增默认关闭的沙箱契约，复用原命令回执和事务journal；PMS只投影引擎事实，不计算后继节点。

**Tech Stack:** FastAPI/SQLAlchemy2/Alembic、零构建ES模块、Flowable8.0.0/Boot4.0.2/JDK21/PostgreSQL16。

**Spec:** docs/superpowers/specs/2026-11-05-r3-sandbox-execution-design.md（用户2026-11-05批准完整设计）

## Global Constraints

- 默认关闭；仅独立沙箱合成数据，不读根.env/真实业务库，不部署生产，不迁移Legacy在途。
- 首片单process、无环、start/end/userTask/sequenceFlow/结构化无条件并行fork/join；其余可执行构造明确拒绝。
- 完整XML为执行源；治理投影不计算Flowable路由，哈希固定实际部署字节。
- 原Instance/Task及页面复用；provider固定，Legacy开放任务唯一约束保留。
- 命令发送前持久化；原ID恢复；事件收件/投影/游标同事务；不承诺跨库exactly-once。
- UTC存储输出+00:00；后端下发中文枚举；零构建、无views互相import。
- PMS schema只走Alembic，alembic.ini保持ASCII；引擎表不纳入PMS迁移。
- 不自动提交/推送/合并本片，不删除原POC容器/卷/台账；本片新设施独立命名。

## Review Focus

1. 远端已提交但本地应用失败/重启，恢复必须复用原ID；Task4/5测试覆盖。
2. 任意XML属性/未知namespace绕过允许列表，PMS及Runner均在部署前拒绝；Task2/3测试覆盖。
3. manager身份不能冒名完成非候选任务、禁用用户回放不能越权；Task5/6测试覆盖。
4. 事件迟到/错实例/游标事务回滚不能覆盖新状态或跳过缺口；Task5测试覆盖。
5. 入站/升级/删除等非UI入口不能把Flowable推进到Legacy；Task6测试覆盖。

---

### Task 1: 原对象身份与可靠性持久数据
**Files:** app/models/{execution,process,engine,__init__}.py；alembic/versions/b3f4a5b6c7d8_r3_engine_sandbox.py；tests/test_engine_models.py。
**Interfaces:** provider LEGACY/FLOWABLE；EngineDeployment(id,model_version_id,namespace,xml_hash,basis_hash,definition_id,deployment_id,configuration)；EngineCommand(id UUID string,user_id,action,target,request_hash,request,status,receipt,error,instance_id,task_id,idempotency_key)；EngineInbox(namespace,event_id,journal_id,payload)；EngineCursor(namespace,after_id,error)。实例增加deployment_id/engine_instance_id/sync_status/synced_at；任务增加provider/engine_task_id/execution_id；配置增加engine_deployment_id/engine_enabled。
- [ ] RED：test_legacy_single_open_and_engine_parallel、test_engine_identity_unique、test_provider_parent_mismatch_rejected；原默认LEGACY，多Flowable任务允许，同engine_task_id拒绝，错父provider拒绝。
- [ ] Run `pytest tests/test_engine_models.py -q`；Expected：缺字段/类RED。
- [ ] 实现模型与约束；用复合外键保证task.provider与instance.provider一致，原索引仅LEGACY；迁移旧数据不猜引擎ID，downgrade有引擎记录时拒绝。
- [ ] GREEN `pytest tests/test_engine_models.py tests/test_migrations.py -q`；Expected全部通过。

### Task 2: 安全BPMN子集与原版本生命周期
**Files:** app/services/engine_bpmn.py；app/services/{bpmn,process_model,designer}.py；app/schemas/process.py；app/api/v1/designer.py；tests/test_engine_bpmn.py。
**Interfaces:** inspect_xml(xml:str)->dict(process_key,tasks,nodes,edges,sha256,contract_version)；import_bpmn(xml,execution_provider='LEGACY')保持原默认；ProcessModelIn/BpmnImportRequest增加execution_provider；版本输出包含provider_label；Flowable草稿保存必须有完整XML且投影与XML身份匹配。
- [ ] RED：串行/结构化并行支持、未知标签/属性/命名空间/DTD/entity/表达式/循环/非结构化fork/join拒绝；Legacy并行仍拒绝；冻结版本变更创建新版本。
- [ ] Run `pytest tests/test_engine_bpmn.py -q`；Expected缺实现RED。
- [ ] 严格允许列表、最多2MiB/500节点；无环连通单start/end；并行fork/join按分支令牌集合验证结构；投影PARALLEL不伪装DECISION。Flowable发布跳过Legacy路由校验，调用本子集校验；不改变原Legacy规则。
- [ ] GREEN目标测试及原BPMN/版本测试。

### Task 3: Runner受控沙箱契约
**Files:** engine/flowable-runner/src/main/java/com/logix/poc/{SandboxController,SandboxService,SandboxXml}.java；SecurityConfig/CommandService/EngineEventListener；src/test/.../SandboxIntegrationTest.java；application.yml。
**Interfaces:** /sandbox/v1/info/commands/commands/{id}/instances/{id}/events；专用FLOWABLE_SANDBOX_ENABLED=false/TOKEN/NAMESPACE；命令动作SB_DEPLOY/SB_START/SB_CLAIM/SB_COMPLETE/SB_ASSIGN/SB_SUSPEND/SB_RESUME/SB_CANCEL，同原UUID回执机制。部署payload xml/hash/context/config；START固定definition/business_key/context；任务actor=pms:<user_id>，候选来自部署配置冻结。
- [ ] RED真实PG：disabled/token隔离、独立XML安全、部署hash/归属、串行/并行汇聚、候选权限、manager不自动候选、同ID回放/冲突、事件事务和历史状态。
- [ ] Run Maven定向测试；Expected404/缺沙箱功能RED。
- [ ] 扩原事务命令dispatcher并复用journal，沙箱定义由部署名namespace校验；受控候选在BPMN模型内注入固定ID（不改路由），源/执行hash返回；实例快照含全部历史task及context，确保迟到事件只触发最新事实核对。
- [ ] GREEN全量 `mvn -B test` 专用PG；Expected POC原用例继续通过。

### Task 4: PMS传输与发送前持久命令
**Files:** app/core/config.py；app/services/{engine_transport,engine_commands}.py；app/schemas/engine.py；tests/test_engine_commands.py。
**Interfaces:** EngineClient.request(method,path,payload=None)->dict，配置URL/namespace/token，禁代理redirect、限制body；prepare(db,user,action,target,payload,key,instance_id=None,task_id=None)->EngineCommand（提交后返回）；dispatch(db,command)->EngineCommand先查回执，404复发同ID，确定拒绝不重试；recover重新核活跃用户及对象权限；状态PREPARED/UNKNOWN/SUCCEEDED/REJECTED。
- [ ] RED本地socket：代理/redirect/错误schema/截断；发送时独立Session可见command；4xx不重试，同ID异参数409，原ID新Session恢复。
- [ ] 最小实现持久请求及目标冲突锁；不存token；禁用默认不联网；本地投影失败时保留远端回执，后续重新应用。
- [ ] GREEN `pytest tests/test_engine_commands.py -q`。

### Task 5: 部署启用、实例投影与事件核对
**Files:** app/services/{engine_execution,engine_projection}.py；execution_readiness.py；schemas/engine.py；tests/test_engine_projection.py。
**Interfaces:** deployment_status(db,user,pid)->dict；deploy(db,user,version_id,key)->command；enable(db,user,pid,deployment_id,enabled)->dict；start/claim/complete/assign/control准备原命令；apply_receipt(db,command)幂等；reconcile(db,instance,user)；consume(db)->dict。
- [ ] RED：只当前发布XML/hash/准备指纹有效可启；错项目/轮次/组织拒绝；原实例provider固定；远端全部task投影，单支完成不越汇聚；重复/迟到事件/错误身份/失败游标/通知去重。
- [ ] 冻结原配置（forms/assignments/用户资格）；首片候选为明确启用用户ID列表，空候选拒绝。claim/complete不沿manager绕过；表单和原授权规则仍核。已提交回执投影与收件/游标同事务，未知实例保存缺口并不前移。
- [ ] GREEN目标回归；注入本地提交失败后按原ID重做，仅一实例/一次通知。

### Task 6: 原API与非UI入口provider分流
**Files:** app/api/v1/{execution,designer}.py；services/{execution,execution_flow,inbound,escalation,process_mining,kpi}.py；scripts/worker.py；schemas/execution.py；tests/test_engine_api.py。
**Interfaces:** 原启动/任务/控制API识别固定provider，Flowable命令未决202；新增/execution/engine/{status,deploy,enable,commands/{id},commands/{id}/recover,instances/{id}/reconcile}；列表/详情为本地只读，active_tasks数组/同步标签后端提供。
- [ ] REDAPI：默认Legacy不联网；Flowable不调用_advance；202可恢复；viewer/跨人拒绝；原入站Flowable写明确拒绝；删除/升级不能本地改变引擎实例，原Legacy继续通过。
- [ ] 仅必要触点分流；原worker调用恢复和消费入口，未启用无连接；外部Webhook默认不为沙箱生成。Flowable任务next_options空，不接受next_node_key。
- [ ] GREEN目标测试及完整pytest。

### Task 7: 原页面办理与技术状态
**Files:** web/js/views/{designer,execution}.js；web/js/views/shared/engine_execution.js；tests/test_frontend_structure.py；scripts/verify_engine_sandbox.py。
**Interfaces:** 后端provider/status labels；shared模块导出配置HTML/绑定和command轮询，不import views。启动/办理保留原command_id，未决不重复POST。原详情全部active_tasks，隐藏Flowable下一步选择，原设计器选择execution_provider及完整XML。
- [ ] RED前端结构/行为回归：无本地枚举映射，202分支保存ID而非重启，全部活跃任务展示。
- [ ] 沿现有按钮和模态接入；不新增主视图/导航/构建工具。完整loading/拒绝/待核对/版本失效反馈。
- [ ] GREEN结构测试及当前服务 `python scripts/verify_frontend.py URL`，本片沙箱脚本验证原入口部署→启用→串行/并行办理。

### Task 8: 独立沙箱、迁移与完整验收
**Files:** engine/flowable-runner/compose.sandbox.yml；scripts/verify_engine_sandbox.py；README和engine/flowable-runner/README.md；台账。
- [ ] 当前源hash/镜像身份；新项目logix-r3-sandbox、Runner127.0.0.1:8136、PMS127.0.0.1:8124，独立PMS临时DB/引擎PG与卷，不读根.env或修改原POC卷。
- [ ] 真实PMS API/页面：版本发布→部署→准备确认→启用→启动→两并行任务→汇聚，串行、权限拒绝、模糊响应/本地应用失败/双方重启原ID恢复、事件续读去重。
- [ ] 完整 `python scripts/check.py`、Java真实PG、SQLite/专用PG迁移/`alembic check`、`scripts/verify_frontend.py`；命令/退出码/原输出保留。
- [ ] 按设计自检完整代码与边界，修Important需RED→GREEN；不再审已合并POC。未获另行授权不提交/推送/合并本片，不删除持久卷。

## 收尾状态（2026-11-07）

Task1–8软件实现与沙箱验收已收尾，详细原输出及限制见[运行与验收说明](../../r3-sandbox-execution.md)。当前原生执行，不提交、推送或合并。下方步骤是原计划保留，不以旧未勾选项反复重做。

- Python完整门禁：686 passed,1 skipped,4 warnings；专用新鲜PG同计数；opt-in真实引擎项单独显式通过。
- Java真实PG：51次执行，0失败/错误/跳过（含继承复跑）。
- 当前页面串行/并行与全站前端通过；真实丢响应后双方进程重启、浏览器刷新、原键恢复仅一实例通过。
- SQLite及专用PG迁移/漂移检查通过；旧测试库drop_all失败未隐去，以新库重跑、不删原库。
- 独立复核调用被中断，无审查结论；原作者自查不能冒称独立审查通过。
- 不扩消息/定时器、生产接管、Legacy迁移；独立POC两个Minor仍保留。

## Pre-flight / 自检

共享接口：Task1→4/5命令持久字段；Task2→3 XML子集/源hash与执行hash；Task3→4统一UUID回执；Task5→6/7原实例/任务+202命令状态。差异以本设计为准记录Ruling。
规范覆盖：§1–5→Task1/2/5；§6→Task4；§7→Task2/3/4；§8→Task5/6；§9→Task7；§10→Task1/8；§11验收→Task8。已获用户“计划并原生执行”指示，计划交付后直接执行，不再重复请求执行方式或范围批准。每任务完成记录台账；提交步骤按本片不自动提交约束保留工作树，不自动创建远程PR。
