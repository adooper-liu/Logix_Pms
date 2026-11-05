# 隔离 Flowable POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不触碰 PMS Legacy 执行语义、数据库和业务数据的前提下，用真实 Flowable 验证部署、启动、任务、并行/会签、消息/定时器及重启后事件重读。

**Architecture:** 新建独立 Java/Spring Boot Runner，嵌入 process-only Flowable Engine，通过独立 Compose 项目运行 PostgreSQL 16。API 只接受仓库内固定合成样例；命令回执与事件在引擎相同数据源、同一 Spring 事务中持久化，先验证内部命令/事件契约，不连接 PMS 或 ERP。现有 FastAPI、前端、Legacy 推进器及主 Compose 均不改。

**Tech Stack:** Flowable `8.0.0`、Spring Boot `4.0.2`、Java `21`、Maven `3.9.9`、PostgreSQL `16`、Spring JDBC/Flyway（版本由 Boot BOM 管理）、JUnit（由 Boot BOM 管理）；容器构建不依赖宿主机 Java/Maven。

**Spec:** 用户在本会话已批准“只做隔离 Flowable POC，不改现有 Legacy 执行语义”；承接 `docs/bpm-lifecycle-gap-and-roadmap.md` §8 R3、`docs/bpm-technology-open-contracts.md` §9/§11、`docs/mainline-acceptance-next.md` §下一步。本文锁定的是该方向的隔离技术实验切片，不是全量 R3 接管计划。

## Global Constraints

- 当前核对基线 `b0da044`；本轮规划时工作区干净、位于 `main`；实现先建隔离 worktree/特性分支，不在 main 写产品代码。
- 用户确认边界：**只做隔离 Flowable POC，不改现有 Legacy 执行语义**。
- 不修改 `app/`、`web/`、`alembic/`、主 `docker-compose.yml`、PMS 依赖或当前公开执行 API；不新增 PMS deployment/provider 字段，不删除 `uq_process_task_one_open`。
- 不读写 PMS 数据库，不读取 `.env`，不调用 PMS/ERP，不发送真实业务资料；合成身份明确不是 PMS 中经核验的真实主键。
- Compose 显式 `name: logix-flowable-poc`，只含 `poc-db` 与 `runner`；数据卷 `flowable_poc_pgdata`，不得挂原 pgdata/attachments，数据库不发布宿主机端口。
- Runner 只发布 `127.0.0.1:8135:8080`，端口可通过 `FLOWABLE_POC_PORT` 覆盖；端口被占用则报错，不停止原服务。
- 所有 API（含 health/info）使用专用 Bearer token，`FLOWABLE_POC_TOKEN` 必填且至少32字符；数据库密码由 `FLOWABLE_POC_DB_PASSWORD` 注入。缺省/空值启动失败，日志不回显秘密。
- 仅使用固定合成 BPMN 资源，禁止任意 XML 上传、Java 类/脚本/任意 URL 执行、Flowable REST 管理端、CMMN/DMN、外部服务任务及生产部署。
- 固定依赖版本，不用 latest/SNAPSHOT。初始构建镜像 `maven:3.9.9-eclipse-temurin-21`、运行镜像 `eclipse-temurin:21-jre`、数据库 `postgres:16`；实现时记录实际 image ID/RepoDigest。这些 JDK/PG 标签不声称字节级可复现，正式 R3另锁 digest。
- Flowable 只管理独立 POC 库中的引擎表，`flowable.database-schema-update=true` **仅限本POC**；Runner 自有 `poc_command/poc_event` 由 Flyway 管理。PMS schema 仍只走 Alembic，本轮无 PMS 迁移。
- UTC 存储/输出，输出明确 `+00:00`；不把排序 ID 或接收顺序解释成并行活动的业务因果。
- 不自动提交、推送、创建 PR、合并或删除持久卷；这些须用户另行授权。新建本地 POC 容器属于此实验，不能扩展为发布真实服务。

## Review Focus

1. 相同 command_id 不同对象/动作/参数必须409，不能回放别的任务结果；非法 token 在查幂等回执前拒绝（Task 2测试）。
2. 引擎事务回滚时，命令回执和监听器事件必须一起回滚；绝不能先发 HTTP 或用内存队列充当已持久事件（Task 2测试）。
3. 并行与多实例任务不能按 node key 唯一；一个分支完成不能越过汇聚，早结束会签的剩余任务取消不能误报已完成（Task 3测试）。
4. 定时器/消息竞争与容器重启不能重复推进；结果不明先查原 command，不换 ID 盲重试（Task 3/4测试）。
5. Compose 配置或验证工具不得误连 PMS；样例业务键与本轮 run_id隔离，旧容器/旧镜像不能算当前代码验收（Task 1/4测试）。

---

## 文件布局与契约

新增文件限以下范围（README仅加入口与限制，不重写历史分析文档）：

- `engine/flowable-runner/pom.xml`、`Dockerfile`、`.dockerignore`：固定依赖、分层构建、非root运行。
- `engine/flowable-runner/compose.poc.yml`：独立项目/DB/卷/本机端口；源码构建默认 `skipTests` 不作为测试通过证据。
- `engine/flowable-runner/README.md`：命令、契约、清理/恢复、能力和未验证边界。
- `engine/flowable-runner/src/main/java/com/logix/poc/RunnerApplication.java`：应用入口。
- 同目录 `SecurityConfig.java`、`PocController.java`、`PocDtos.java`、`PocExceptionHandler.java`：认证、路由、类型化契约及无秘密错误响应。
- 同目录 `CommandService.java`、`CommandRepository.java`：幂等命令事务和回执。
- 同目录 `FixtureService.java`：固定样例清单、hash与部署复用。
- 同目录 `EngineEventListener.java`、`EventRepository.java`：同事务追加事件和分页重读。
- `src/main/resources/application.yml`、`db/migration/V1__poc_journal.sql`：POC配置及自身日志迁移。
- `src/main/resources/fixtures/{serial,parallel-signoff,message-timer}.bpmn20.xml`：唯一合成执行模型。
- `src/test/java/com/logix/poc/{IsolationConfigTest,CommandIntegrationTest,WorkflowIntegrationTest}.java`：真实 PostgreSQL测试，不用H2替代恢复/并发结论。
- `scripts/verify_flowable_poc.py`、`tests/test_flowable_poc_probe.py`：显式目标的宿主机验证器及解析/分页/轮询回归。
- 根 `.gitignore` 仅补 `engine/flowable-runner/target/`，根 `README.md` 仅新增隔离POC入口。

### HTTP 接口（均位于 `/poc/v1`，均须 token）

- `GET /health`：数据库/引擎 ready，否则503；不输出凭据。
- `GET /info`：`poc:true, build_revision, flowable_version, spring_boot_version, java_version, capability_names`，revision通过构建参数注入，容器实测必须非unknown。
- `GET /fixtures`：固定fixture名、实际XML SHA256、支持限制。
- `POST /commands`：`{command_id, action, target, payload}`，action严格限定 `DEPLOY, START, CLAIM, COMPLETE, MESSAGE, SUSPEND, RESUME, CANCEL`；payload按动作反序列化为record，未知字段拒绝。
- `GET /commands/{command_id}`：仅返回已持久成功回执；不存在404，客户端遇写超时先查此接口。
- `GET /instances/{engine_instance_id}`：运行/终态、definition ID、business_key、活跃用户任务数组、消息订阅和timer job摘要；终态从历史查询，不用运行表404冒充实例丢失。
- `GET /events?after_id=0&limit=100`：`{events,next_after_id,has_more}`，limit范围1–500；ID为交付游标不是业务因果序号，保留 occurred_at、instance/activity/execution/task/definition身份。

`command_id` 为UUID，语义hash覆盖 action、target、规范化payload（含身份与业务键）。事务内先INSERT唯一命令占位→引擎操作→保存成功结果，同ID并发唯一冲突在新事务读取既有结果；同hash重放完全相同回执，不同hash409。失败整体回滚，不伪造成功回执。错误不占成功命令ID，测试明确验证此策略。

DEPLOY只接受 fixture 名和期望XML hash；返回 deployment_id、definition_id、definition_key/version、bpmn_sha256。同fixture/hash部署复用，不能依赖Flowable默认部署去重猜测；在事务内按fixture加PostgreSQL advisory xact lock，按部署名 `poc:<fixture>:<sha256>` 查询后部署，每个文件严格一个process。

START必须指定实际 definition_id、唯一 `business_key=poc:<run_uuid>:<case_name>` 与合成 `context`：`{source:POC_FIXTURE,process_id:910001,model_version_id:910001,project_id:null,round_id:null}`；定义须属于本服务固定样例。禁止同business_key重复启动（事务advisory lock+运行/历史查询），幂等只重放原command。上下文是传递实验，不证明真实PMS版本/轮次存在。普通变量只允许本fixture定义的白名单与JSON原始类型；禁止任意Java对象反序列化。

CLAIM/COMPLETE target均为精确引擎task ID；合成人员只允许 `poc-applicant,poc-quality,poc-plan,poc-reviewer-a,poc-reviewer-b`，候选/处理人核对后再执行，不能以持有机器token跳过样例任务参与者检查。MESSAGE target为engine instance ID，payload含消息名与变量；服务端查唯一execution订阅，0或多个拒绝，不按business_key盲选。SUSPEND/RESUME/CANCEL target为精确instance ID，错误状态409；状态重试可重放原command回执。

### 事件最低集

同步监听 `PROCESS_STARTED, PROCESS_COMPLETED, PROCESS_CANCELLED, TASK_CREATED, TASK_ASSIGNED, TASK_COMPLETED, ACTIVITY_STARTED, ACTIVITY_COMPLETED, JOB_EXECUTION_SUCCESS, JOB_EXECUTION_FAILURE`（实现时按8.0.0实际枚举核对，不存在的枚举不以同名假事件替代）。记录 `event_id(UUID),journal_id,contract_version=1,type,occurred_at,engine_instance_id,definition_id,activity_id,execution_id,task_id,business_key,context`；job事件缺少可解析实例时保留真实job引用，不伪造身份。

监听器为同步fail-on-exception，使可回滚命令的事件和引擎变更在相同事务。追加journal时先取统一PostgreSQL advisory transaction lock，再分配journal_id并INSERT；所有事件写入口都使用此锁，使游标不会越过尚未提交的较小ID；回滚造成ID空洞合法，不要求连续。这个全局串行点仅用于低吞吐POC，不宣称生产扩展性。异步Job最终状态以引擎job/deadletter查询和历史为准，不把失败事务中回滚掉的监听事件当永久故障证据。事件只落POC库；不推送PMS、Webhook或通知。Task 4重读以event_id去重，至少一次契约，不宣称跨系统exactly-once。

---

### Task 1: 隔离服务与可验证运行环境

**Files:** 创建pom/Dockerfile/compose/application/入口与SecurityConfig/health+info；`IsolationConfigTest.java`；修改`.gitignore`。

**Interfaces:** 输入专用环境变量和 `BUILD_REVISION`；输出本机认证health/info、真实Flowable ProcessEngine与共享DataSource/TransactionManager；不自动部署样例。

- [x] **Step 1: 建worktree并写失败测试。** 使用 `superpowers:using-git-worktrees`；`IsolationConfigTest`断言token缺失/短于32字符启动失败，匿名/错误token返回401，正确token可读health/info；process引擎存在、CMMN/DMN不存在；DB地址不存在PMS连接；compose只暴露loopback Runner端口且无外部卷。
- [x] **Step 2: 运行RED。** 通过 Maven 3.9.9/JDK21测试容器挂载新源码，连接一次性PostgreSQL16测试容器；预期缺项目/入口失败。测试项目用 `logix-flowable-poc-test`，绝不复用现有PMS db，实际命令固定写入POC README。
- [x] **Step 3: 实现最小服务。** `RunnerApplication.main(String[]):void`、`SecurityConfig`及`PocController.health()/info()`；process-only starter `org.flowable:flowable-spring-boot-starter-process:8.0.0`，Boot parent4.0.2。异步执行器显式开启，history使用full以保留会签/取消证据；Spring Security无会话、无浏览器表单登录、无跨域开放；优雅停机和就绪超时。实际info读取引擎/Boot/JVM版本，不仅回显配置。
- [x] **Step 4: 运行GREEN和隔离核对。** Maven定向测试通过；`docker compose -f engine/flowable-runner/compose.poc.yml config --quiet`退出0；渲染配置只在本地内存验证，不把含秘密的完整配置打印或保存。展示服务/卷/网络名称及测试计数，不启动PMS服务。

### Task 2: 合成样例、幂等命令与事务事件

**Files:** FixtureService、CommandService/Repository、PocDtos/ExceptionHandler、EngineEventListener/EventRepository、journal迁移、serial样例；`CommandIntegrationTest.java`。

**Interfaces:** `FixtureService.deploy(String fixture,String expectedSha256):DeploymentResult`；`CommandService.execute(CommandRequest):CommandReceipt`；`CommandRepository.find(UUID):Optional<CommandReceipt>`；`EventRepository.after(long afterId,int limit):EventPage`。DTO字段完全遵循上节，Java record定义，时间输出UTC。

- [x] **Step 1: 写RED用例。** `deploy_fixed_fixture_and_reuse_hash`断言两个不同command的相同fixture/hash只生成一份部署；`reject_arbitrary_resource_or_hash`断言未知fixture/错hash400且无部署；`serial_claim_complete`断言实际Flowable实例创建→task认领→完成→历史终态COMPLETED，且context/definition/business_key贯穿事件。
- [x] **Step 2: 补命令/事件负例并运行RED。** `same_command_replays_exact_receipt`、`same_id_different_action_target_payload_conflicts`、`invalid_token_cannot_replay`、`concurrent_start_same_command_creates_one_instance`、`different_command_same_business_key_conflicts`；用两个独立连接/事务并发实测。`event_listener_failure_rolls_back_engine_and_receipt`注入事件写入失败，断言任务未完成、后续任务/成功回执均不存在。`events_page_replay_is_stable`验证分页/重复读取不丢event_id、非法游标和limit拒绝；`event_cursor_does_not_skip_uncommitted_lower_id`用两个事务控制提交次序，断言游标前移后仍能读全已提交事件（事件写入必须先拿统一事务锁再分配ID）。
- [x] **Step 3: 实现同事务命令及事件。** `CommandService.execute`由Spring代理的事务服务调用，处理唯一冲突的外层与回执查询不复用已失败事务；canonical hash使用固定序列化键序并包含target；listener使用同一DataSource/事务。Flyway仅建立自有poc前缀表。样例部署不启用启动时扫描自动部署，所有命令均走统一记录与状态校验。
- [x] **Step 4: 运行GREEN。** 容器内 `mvn -B -Dtest=IsolationConfigTest,CommandIntegrationTest test`，真实PG用例全部通过；保留Surefire计数与RED/GREEN摘要。证明事件与任务改变在同一提交，不用mock引擎或仅HTTP200验收。

### Task 3: 并行、会签、等待与控制能力验证

**Files:** parallel-signoff/message-timer XML、剩余命令/查询实现、`WorkflowIntegrationTest.java`。

**Interfaces:** 沿Task 2命令接口不新增第二套路由；`PocController.instance(String):InstanceView`返回活跃任务集合、消息/定时器及历史终态。样例BPMN元素id即活动定位键，task_id/execution_id区分同节点多实例。

- [x] **Step 1: 写RED用例。** `parallel_join_waits_for_both_branches`：quality与plan两个同时OPEN；只完成一个不能生成review；两个完成后才创建review多实例。`all_reviewers_required`：两位reviewer并行会签，完成一位不能结束，全部完成一次结束。样例只支持全员通过，不宣称比例会签/仲裁。
- [x] **Step 2: 写等待/控制RED用例并运行。** `message_before_timer_completes_once`、`timer_without_message_completes_timeout`：同一个用户任务边界定时器不适用于此等待图；使用event-based gateway竞争message catch与timer catch，消息分支结束后timer不得再次推进。定时器表达式 `${waitDuration}`、START白名单只允许ISO时长且2–60秒（测试默认PT5S），事件后变量标记MESSAGE/TIMEOUT。`suspend_resume_and_cancel`断言挂起拒绝COMPLETE、恢复可完成、取消关闭活跃任务但不冒称业务补偿；`wrong_candidate_unknown_message_and_unknown_variable_rejected`必须不推进实例。
- [x] **Step 3: 实现三个固定模型与命令。** 以真实标准BPMN执行网关/多实例/消息/定时器，不在Java模拟下一步。全员会签后结束；message-timer单独流程，降低失败定位难度。服务层核任务候选人及白名单；Flowable负责运行态和令牌。消息后再次关联409，异步等待测试轮询截止而非固定长sleep。取消/会签遗留取消状态按真实历史记录，缺TASK_COMPLETED不补造。
- [x] **Step 4: 运行GREEN。** PostgreSQL上的全量Maven测试，包括异步执行器真实触发，逐项输出通过的fixture/能力；若竞争场景只覆盖先后次序，明确“不等于生产高并发竞争验证”。子流程、call activity、服务任务/自动业务补偿仍未验证，不在info支持列表列出。

### Task 4: 当前镜像烟测、重启与交付说明

**Files:** `scripts/verify_flowable_poc.py`、`tests/test_flowable_poc_probe.py`、POC README、根README入口。

**Interfaces:** `python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 --expected-revision <sha> --state-file <var/path.json> --phase before-restart|after-restart`；token只从 `FLOWABLE_POC_TOKEN`读取，不放CLI或state文件。标准库urllib；禁止redirect，URL只允许loopback且强制info.poc=true/revision相符，拒绝PMS8123与未知服务。

- [x] **Step 1: 写RED探针测试。** `reject_non_loopback_or_redirect`、`reject_revision_or_poc_marker_mismatch`、`drain_all_event_pages_and_deduplicate`、`deadline_expires_with_last_state`、`reuse_original_command_after_timeout`；测试state不含token/DB密码，任务轮询按task ID不是node key。运行 `pytest tests/test_flowable_poc_probe.py -q`确认失败。
- [x] **Step 2: 实现分段烟测。** before阶段为唯一run_uuid部署三个fixtures，验串行/并行/会签、消息分支；保存一个待办实例、一个等待timer实例、命令/事件游标（默认timer 60秒）后退出。after阶段核同一revision和原实例，验证任务可继续、过期timer恢复后最终触发一次、原command回放不重复实例、事件从原游标可继续读且从0重读可去重。若timer在停机前已经触发，重建新的本轮等待实例后重做，不把原已结束实例当恢复证据。
- [x] **Step 3: 实测当前代码。** 构建前记录源码diff与revision，`BUILD_REVISION=$(git rev-parse HEAD)`注入镜像；未提交源码另记录工作区文件hash/镜像ID，并明确revision只标基线而非声称提交含未提交实现。新建POC项目→认证health/info→before→仅停止/启动本POC runner→after；另外一次 `docker compose down`（不带-v）再up验证PG卷保留。核数据库/引擎日志、image ID和info版本；任何未完成步骤标“未验证”。不使用遗留后台服务验收。
- [x] **Step 4: 文档和全库门禁。** README提供专用env注入、不读根.env、容器测试和烟测命令、正常停止（不删卷）、手工删除POC卷的警告、不自动清理原设施；根README只加入口。运行 `python scripts/check.py` 和全量Maven测试，保存原输出/退出码；核 `git diff --name-only`未触及app/web/alembic/主compose。无前端/PMS schema修改，说明verify_frontend/Alembic check本片不适用；不宣称生产迁移或全站真实UI已验证。

## 执行/验收命令约定

实现后的POC README必须给出可直接执行的完整命令（包括临时测试容器/network/env），不得要求读者自行猜网络名；不得通过Docker socket挂进测试容器。可使用宿主机Docker CLI编排专用临时PG，Maven容器通过专用网络连接，测试完只清理本次明确命名的容器/网络。持久POC卷不随测试删除。

本地POC启动使用隔离文件且 `--env-file` 指向专用无秘密模板或空文件，实际秘密从进程环境注入，防止Compose默认发现根.env。执行阶段如需拉镜像/下载Maven依赖，仅允许标准官方仓库；网络失败如实报告，不改用未知第三方镜像或降低安全校验。

## 完成报告必须分别列出

1. 当前构建identity、Flowable/Boot/JDK与PG版本、容器和卷身份。
2. Java/PostgreSQL实际测试计数及Python check.py原输出，失败/跳过不能隐去。
3. 串行、排他（如未单设排他样例则标未验证）、并行汇聚、全员会签、消息/定时器、挂起/恢复/取消、重启恢复的逐项结论。
4. 命令幂等、同ID异参数、事件回滚、分页重读及重启后的原实例证据。
5. 现有PMS未改动、未接管Legacy实例；context仅合成数据，事件仅POC日志，**未验证PMS业务投影/通知/KPI/真实授权/真实收益**。
6. 尚未验证生产HA/容量/升级/备份恢复、跨系统原子性、任意XML安全部署、服务任务和在途迁移；本地重启不等于这些能力已完成。

## 官方依据（2026-11-05公开只读核对）

- [Flowable releases](https://github.com/flowable/flowable-engine/releases)：稳定版8.0.0；8迁移到Spring7/Boot4，不支持Boot3。
- [8.0.0 root pom](https://github.com/flowable/flowable-engine/blob/flowable-8.0.0/pom.xml)：jdk.version=17最低基线；本POC工程选择21，不宣称官方要求21。
- [8.0.0 dependencies](https://github.com/flowable/flowable-engine/blob/flowable-8.0.0/modules/flowable-dependencies/pom.xml)：spring.boot.version=4.0.2。
- [process-only starter](https://github.com/flowable/flowable-engine/blob/flowable-8.0.0/modules/flowable-spring-boot/flowable-spring-boot-starters/flowable-spring-boot-starter-process/pom.xml)：org.flowable:flowable-spring-boot-starter-process。
- [Spring Boot guide](https://www.flowable.com/open-source/docs/bpmn/ch05a-Spring-Boot/)：properties仅作导航，具体API/枚举以8.0.0源码与编译实测为准，不混用跨版本示例。

## 计划自检

- 范围：隔离Runner/固定合成样例/内部日志与恢复；真实PMS适配、生产接管和业务效果均留在后续R3。
- 契约：Task 2定义command/receipt/event，Task 3/4复用；无公开API兼容承诺，无第二套路由。
- 五项Review Focus均有归属测试；真实引擎/PG和当前镜像是验收对象。
- 四项任务已实现并完成首轮实测；当前工作区未提交，最终独立复核单列于执行台账。初始规划文档留在主工作区的副本不自动覆盖。

## 独立复核后状态（2026-11-05 续线）

以下为历史中止记录：独立复核确认3项Important（环境代理、恢复假阳性、模糊响应命令丢失）；当时新增测试执行被拒绝，未应用修复。

本次续线经用户明确授权后，已原生应用3项最小修复，未派代理或重复审查：

- 显式ProxyHandler({})；本地假代理/目标服务实证RED→GREEN，不把loopback hostname当直连保证。
- Runner实际boot_id/JVM启动时刻、真实timer due date/历史completed_at；受控Docker stop观察与新boot校验。
  时间用UTC字符串而非暂定epoch测试格式，Docker观测使用daemon SystemTime，避免宿主机时钟偏差。
- 请求在发送前fsync并原子持久化；断连/截断响应查原ID，新CLI从journal恢复，同ID不同请求拒绝覆盖。

已重建镜像`sha256:f61d4c75a5db6a30d5f63304a70ee9bd6a36a8a5dfc38d52e61b36d39a3866e7`。
真实CLI负例：before后不重启直接after拒绝且未消费待办；timer已结束后请求restart拒绝且不停止容器。
真实正例：Runner停机恢复、整栈down/up无-v保留原卷均通过原实例/原回执/单次timer完成/事件续读。
详见执行台账、`fix-runtime-2.log`、`fix-command-loss.log`和`var/flowable-poc/fix2-*.json`。

Minor仍待后续：业务键UUID格式校验不严格；未知路由被统一返回503。
不提交/推送/合并/删卷，保留未提交worktree及恢复记录；其余生产/真实PMS/扩展BPMN能力仍未验证。

## 2026-11-05 执行证据（复核前）

- Legacy保护范围 `git diff -- app web alembic docker-compose.yml` 无改动；不连接PMS库，不接真实身份/数据。
- PostgreSQL Java测试：`Tests run: 34, Failures: 0, Errors: 0, Skipped: 0`，包含继承复跑（12命令+4隔离+18工作流）。事件故障注入的ERROR日志为预期负例，非隐去失败。
- `python scripts/check.py`：`629 passed, 4 warnings`，格式/lint通过；警告为原FastAPI客户端弃用及原表依赖循环。
- 当前镜像SHA `23b4887da04fc7b8c8e756405645e407fc3d6f360c081b975a8f986f084f6517`；实际Flowable `8.0.0.0`、Boot `4.0.2`、运行JRE `21.0.13`、PostgreSQL `16.15`。基线SHA不包含未提交实现，另以源码hash与image ID核对。
- Runner停机65秒后恢复及Compose down/up保留卷两组均成功续办原任务/原timer、回放原command、继续事件游标并去重。
- 无前端/PMS schema改动，本片未运行前端E2E/生产Alembic；不宣称PMS引擎适配、生产HA/容量/备份恢复、真实业务效果已经验证。
