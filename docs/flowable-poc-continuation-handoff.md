# 隔离 Flowable POC：未完成事项转交与续线要求

> 转交日期：2026-11-05。本文件保留原中止交接历史；后续授权与修复结果见下方续线更新，不能只读历史状态重做任务。
> 原交接阶段：主体 POC 已实现，复核发现 3 项 Important；当时回归已写未运行、修复未应用。

## 2026-11-05 续线更新（优先于以下历史记录）

用户已明确授权本会话原生修复与本地Python／专用PostgreSQL测试、独立POC重建和停止重启；不提交推送合并、不删除卷、不碰PMS、不派代理。

- I1显式禁用环境代理；本地真实HTTP目标/假代理回归已观察RED→GREEN。
- I3默认发送前持久化原请求（原子文件、不存token），模糊响应查原command_id；确定性4xx不重试，同ID异请求拒绝覆盖；真实socket断连/截断及真实Flowable提交后丢响应、新CLI恢复已验证。
- I2提供稳定boot_id/JVM启动时刻、实际timer_due_at/历史completed_at；受控restart-runner/restart-stack记录Docker实际停止状态及daemon时间，拒绝手填停机时间作为证明。真实无重启/提前完成负例及两种停机恢复已验证。
- 当前镜像：`sha256:f61d4c75a5db6a30d5f63304a70ee9bd6a36a8a5dfc38d52e61b36d39a3866e7`，Flowable8.0.0.0/Boot4.0.2/JRE21.0.13/PG16.15。基线SHA仍不包含未提交实现。
- 当前命令见`engine/flowable-runner/README.md`；最新执行证据见`.superpowers/sdd/2026-11-05-isolated-flowable-poc/progress.md`，不要使用下方旧公开契约或旧镜像续线。
- 首轮运行暴露旧Java测试首500条事件假设、Docker/宿主机时间偏差，均保留失败日志；已分别改全分页断言和daemon观测，不清数据库或放宽证据校验。
- 两项Minor仍待办；原Legacy/生产边界不变。全部文件未提交，worktree、台账、容器和原持久卷均保留。

---

以下为原始交接快照（非当前待执行清单）：

## 1. 给续线会话的第一句话

继续现有隔离 Flowable POC 的独立复核修复，不重新做选型、脑暴、总设计或新建项目。先读本文件、当前 CLAUDE.md、实施计划和执行台账，再核当前文件及环境。先确认恢复执行权限，再运行此前被拒绝的测试；不得把转交请求当作恢复授权。保持“只做隔离 POC，不改现有 Legacy 执行语义”，不提交、不推送、不合并、不删除卷。

## 2. 工作区和 Git 身份（本轮只读实查）

- 工作区：`D:\Logix_Pms\.claude\worktrees\isolated-flowable-poc`
- 分支：`worktree-isolated-flowable-poc`
- HEAD/基线：`b0da044c779dd769bb9ef6ad379075ef912adf93`
- **尚无本轮提交**；多数实现是 untracked，不能只看 `git diff` 或 `HEAD..HEAD`。
- 主工作区 `D:\Logix_Pms` 中有最初未提交的计划副本；后续实施和最新状态在本 worktree，不能用旧副本覆盖当前内容。
- 已经在 worktree 内，不要再建 worktree，不要切回 main，不要跨回主工作区写代码，不要 stash/clean/reset。

本轮 `git status --short --branch`：

```text
## worktree-isolated-flowable-poc
 M .gitignore
 M README.md
?? docs/superpowers/plans/2026-11-05-isolated-flowable-poc.md
?? engine/
?? scripts/verify_flowable_poc.py
?? tests/test_flowable_poc_probe.py
```

本文件为该状态核对后新增的转交文档。
`git diff --name-only -- app web alembic docker-compose.yml` 无输出。

## 3. 不得改变的范围

- 独立 Runner、独立 PostgreSQL/卷、固定合成 BPMN 样例、本机访问 API。
- 不修改 `app/`、`web/`、`alembic/`、主 `docker-compose.yml` 或 PMS 依赖。
- 不连接 PMS 数据库，不读取根 `.env`，不调用 PMS/ERP/通知/KPI，不发真实资料。
- 不增加 PMS deployment/provider 映射，不删除 `uq_process_task_one_open`，不迁移/接管 Legacy 实例。
- 不开放任意 XML、脚本、Java 类、任意 URL 或外部服务任务。
- 不自动提交、推送、PR、合并、删除 worktree 或持久卷。所有内容未提交，忽略目录内的台账和日志仍是必要恢复记录。

## 4. 必须先读的材料

1. `CLAUDE.md`：以当前 worktree 内容为准。
2. `docs/superpowers/plans/2026-11-05-isolated-flowable-poc.md`：用户批准的实施边界、四任务和后续未完成状态。
3. `engine/flowable-runner/README.md`：构建/运行/API/测试命令；**其中恢复验收仍是复核前方案，须随修复更新**。
4. `.superpowers/sdd/2026-11-05-isolated-flowable-poc/progress.md`：已执行任务、Ruling、复核结论、权限中止点。
5. `.superpowers/sdd/2026-11-05-isolated-flowable-poc/review-package.md`：复核范围与证据包；不是最终复核结论全文。
6. 当前 `scripts/verify_flowable_poc.py`、`tests/test_flowable_poc_probe.py`、`engine/flowable-runner/src/main/java/com/logix/poc/PocController.java`、`src/test/java/com/logix/poc/IsolationConfigTest.java`。

原计划和台账中的 Task1–4 complete 是**复核前任务执行状态**，不等于最终交付；台账末尾“复核尚未返回”是历史记录，顶部已明确复核返回及修复阻塞，不能据旧句重新派一轮审查。

## 5. 已有实现，不要重建

- Flowable `8.0.0` process-only starter、Spring Boot `4.0.2`、Java21 容器构建。
- 实际引擎版本返回 `8.0.0.0`，实际运行 JRE `21.0.13`，测试构建 JDK 镜像曾为21.0.7；PG实际 `16.15`。
- `engine/flowable-runner/`：pom、Dockerfile、独立 Compose、认证、health/info、固定样例部署、命令回执、实例查询、事务事件 journal。
- 固定样例：serial、parallel-signoff（全部人员会签）、message-timer（事件网关竞争）。
- 命令：DEPLOY/START/CLAIM/COMPLETE/MESSAGE/SUSPEND/RESUME/CANCEL；UUID command_id、规范化参数hash、成功回放、同ID异参数409。
- Flowable 与 journal 同数据源/事务；事件失败使引擎变更和回执一起回滚；PG全局事务锁在journal ID分配前取得，避免游标越过未提交的小ID。仅低吞吐POC策略。
- Python 探针及测试；探针存在下节已确认缺陷。

## 6. 必须完成的 3 项 Important（同一轮修复，不重开设计）

### I1：环境代理可能转发 loopback token

- 文件：`scripts/verify_flowable_poc.py`，Client构造中的 `build_opener(NoRedirect())`。
- 原因：urllib默认 ProxyHandler 读取环境变量；URL是loopback不代表实际连接不经代理。身份检查之前已发送Authorization。
- 最小修复：显式 `ProxyHandler({})` 禁用环境代理，继续禁止重定向。
- 已写待运行回归：`test_proxy_environment_cannot_route_loopback_token`。
- 续线补强：用离线handler或本地HTTP服务实际证明设置http_proxy/no_proxy后仍直连，不发送到外部测试代理；不能仅用“hostname是localhost”断言代替。

### I2：未重启/停机前已结束也能被验收为恢复

- 文件：探针before/after；Runner `/info`和实例timer/历史时间出参需要最小增量。
- 原因：after只核TIMEOUT终态及一条完成事件，未核新的进程启动身份，也未核timer停机前仍待触发。`timer_started_at`在事件读取后写入，非真实引擎到期时间。
- 已写待运行回归：`test_restart_evidence_rejects_false_positive`（same_boot/no_stop/expired_before_stop/completed_before_boot）、`test_restart_evidence_accepts_observed_offline_expiry`。
- 已写Java待运行回归：`runtime_identity_exposes_boot_and_actual_timer_deadline`。**当前它仅断言boot_id/boot_started_at，尚未断言真实timer deadline，名称不等于覆盖，需补timer出参回归。**
- 建议最小方案：Runner提供稳定的本次进程boot_id及进程启动时刻，实例查询提供实际timer due_at/历史completed_at；before固定这些真实值。
- 明确获取停机证据：用受控的独立POC编排记录容器停止事件/时间，并验证timer到期前Runner已停止；after要求boot_id改变、deadline位于停机和重启之间、完成不早于重启。不要仅新增一个可随意填入的“stop_observed_at”参数就当成已观测。
- 若不自动编排，必须将“持久结果核对”和“已验证停机恢复”拆开，缺外部检查证据时不能写verified=true。
- 当前待执行测试提到 `validate_restart(state,info,timer)` 和 epoch秒字段，是未实施的测试期望，不是已经批准的新公开契约；可在不扩大边界下做最小一致修订，记录Ruling。
- 必须有“before后不重启直接after”和“timer在停止前已完成”的真实负例，不只测试辅助函数。

### I3：断连/截断响应未完整恢复原命令

- 文件：探针 `submit()`、`command()`及before状态写入。
- 原因：只捕获URLError/TimeoutError；RemoteDisconnected、ConnectionResetError、IncompleteRead、截断JSON可能发生于提交之后，直接退出并遗失新生成的command_id。
- 最小修复：发送前持久化命令请求/ID（不存token），遇明确的模糊传输/响应错误先查原回执；必要重试复用原ID。确定性4xx不盲重试，查询也失败须保留恢复记录并清楚报告command_id。
- 已写待运行回归：`test_ambiguous_response_queries_original_receipt`、`test_command_is_durable_before_transmission`。
- 当前测试期望 `Client(..., journal_dir=tmp_path)`，构造尚无该参数；落地时确保CLI默认也持久化，而不是只有显式测试参数才保存。
- 持久文件需原子写/合适权限、拒绝不同请求覆盖同ID；不把秘密写入状态或异常。不把模糊失败当成功，也不无限自动重试。

## 7. 精确中止点与权限

已新增以上Python和Java回归，**没有运行**。用户拒绝了一个同时执行Python回归和Java IsolationConfigTest的组合命令；拒绝后未重试、未应用修复。

因此：

- 当前代码**未验证，不能说全绿**；新增回归尚未观察RED。
- `boot_id`、`boot_started_at`、`validate_restart`、`journal_dir`等实现尚不存在。
- 当前新增Python测试尚未重新格式化/lint，不应把格式错误当目标RED。
- 本轮只请求转交，不构成恢复执行许可。下一会话先请求用户明确“继续修复并运行本地Python/专用PG容器测试”，获准后再执行；不能通过拆命令、换工具或派子代理绕过此前拒绝。
- 不要重新派实现代理；用户选择原生执行。独立整分支复核已完成，按既有技能同一轮修复→RED/GREEN→完整验证即可，不再付费重审。

## 8. 复核前证据及其限制

历史输出（不是当前树通过结果）：

```text
基线 check.py：615 passed, 4 warnings
复核前 Java全量：Tests run: 34, Failures: 0, Errors: 0, Skipped: 0
复核前 Python全量：629 passed, 4 warnings
```

34为执行次数，含WorkflowIntegrationTest继承的命令测试重复，不是34项独立能力。4警告是既有FastAPI客户端弃用和表依赖循环。事件回滚测试有预期 `injected event failure` ERROR日志，不是实际测试失败。

实际停机实验：

- 初始Runner重启停止发生于timer创建486.67秒后，**不证明停机期间过期**。
- 后续有效Runner重做：创建后0.8027秒停止，停机65秒后启动，原任务/timer/command/事件续读检查通过。
- 整栈down/up不带-v：创建后1.85秒移除容器，65秒后重建，保留卷及原实例通过。
- 这些有独立编排日志，但当前探针自身仍有I2假阳性缺陷，修复后必须重新验收。

证据在忽略目录：

- `.superpowers/sdd/2026-11-05-isolated-flowable-poc/task-{1,2,3,4}-tests.log`
- 同目录 `flowable-*.log`，尤其 `flowable-runner-restart-verified.log`、`flowable-volume-restart.log`。
- `var/flowable-poc/{runner-restart-verified.json,volume-restart.json,source-hashes.json,verification.json}`。
- 旧source-hashes早于复核新增测试，**不是当前树完整指纹**。

旧镜像：`sha256:23b4887da04fc7b8c8e756405645e407fc3d6f360c081b975a8f986f084f6517`；BUILD_REVISION只是基线SHA，不含未提交实现。修复后必须重建并重核image ID/源码hash，不可用当前容器冒充新代码。

## 9. 转交时环境

本轮 `docker ps`只读输出：

```text
logix-flowable-poc-runner-1   healthy   127.0.0.1:8135->8080/tcp
logix-flowable-poc-poc-db-1   healthy   5432/tcp（未发布宿主机端口）
logix-flowable-poc-test-db    running   5432/tcp（未发布宿主机端口）
```

- Compose：`engine/flowable-runner/compose.poc.yml`，项目 `logix-flowable-poc`。
- 持久卷：`logix-flowable-poc_flowable_poc_pgdata`，不得删除。
- 专用测试网络：`logix-flowable-poc-test`；Maven缓存卷 `logix-flowable-poc-m2`。
- 凭据在本地忽略文件 `var/flowable-poc/test.env`，仅POC测试/运行使用，**不要Read显示其内容，不要贴到聊天/日志/提交**。可由程序载入进程环境；不读根.env。
- Compose显式 `--env-file var/flowable-poc/empty.env`；实际秘密从进程环境注入，保留旧数据库密码对应现有卷。
- 既有Python虚拟环境：`D:/Logix_Pms/.venv/Scripts/python.exe`。跑check.py需把该Scripts目录放PATH，否则ruff找不到。不要为此修改PMS依赖。
- 宿主机此前未找到Java/Maven，测试用 `maven:3.9.9-eclipse-temurin-21` 容器；Java tests使用真实专用PostgreSQL，不用H2假装并发/恢复验收。
- 当前Runner仍是复核前镜像，探针未修复前不要在有环境代理的条件下发送token。

## 10. 获得恢复权限后的执行顺序

1. 只读核当前分支/改动/容器和文件，确认没有其他会话新增工作；不撤销现有内容。
2. 接受3项Important并保留2项Minor待办；原生执行本轮修复，不重新脑暴或改范围。
3. 修整回归测试格式并补齐真实行为边界，逐项运行，记录**因目标缺陷而RED**；不要把拼写/配置错误当RED证据。
4. I1→I3→I2逐项最小实现和GREEN；顺序可按依赖调整，记录决定。
5. 全量Java `mvn -B test`（专用PG）和 `python scripts/check.py`。命令模板在Runner README及台账；路径必须为当前worktree，MSYS_NO_PATHCONV=1避免Git Bash改写容器路径。
6. 新源码hash/构建身份→重建独立Runner→认证health/info。不得连接旧服务后声称新版本成功。
7. 新state与命令journal，重跑串行/并行/会签/消息，并验证：无重启拒绝、停机前已过期拒绝、真实停机过期恢复、整栈重建保留卷、模糊响应查原ID及持久恢复。
8. 最终全量回归和源码保护范围核对；生产/业务/前端/PMS schema检查适用性逐项说明。
9. 更新README、计划与ledger，记录3项修复各自RED→GREEN和命令原输出；不删历史失败或修正记录。
10. 明确全部完成或剩余阻塞；未获新授权不commit/push/merge/清卷。保留worktree和执行台账供用户决定。

## 11. 暂不处理的Minor及未验证范围

Minor（本轮独立复核已登记，不顺手扩大修复）：

- `CommandService.java`业务键UUID段 `[0-9a-fA-F-]{36}`接受36个连字符；不破坏当前business_key锁唯一性，但不满足严格UUID格式。
- `PocExceptionHandler.java`未知路由被catch-all转换503，应保留404；当前诊断误导但非执行推进缺陷。

未验证/不在此次范围：比例/提前结束会签、同时message/timer及不同分支高并发压力、子流程/callActivity、服务任务/业务补偿、任意XML安全部署、PMS真实授权和投影/通知/KPI、跨系统事务、生产HA/性能/升级/备份恢复、Legacy在途迁移、真实组织效果。无前端或PMS schema变更，本片前端E2E和生产Alembic不适用；后续若改到这些范围须补对应验证。

## 12. 可直接粘贴给下一会话的续线请求

```text
请原生续线当前隔离 Flowable POC，不重新选型或建项目。先读
D:\Logix_Pms\.claude\worktrees\isolated-flowable-poc\docs\flowable-poc-continuation-handoff.md
以及该worktree的CLAUDE.md、计划和ledger。

本轮目标仅完成独立复核的3项Important：禁用探针环境代理、可靠的重启/过期恢复证据、模糊响应下持久保留并恢复原command_id。
2项Minor保留待办。不改Legacy、不接PMS数据库/真实数据、不提交推送合并、不删卷。

前一会话测试执行被拒绝，新增回归尚未运行，当前树不能声称全绿。
请先确认我是否授权恢复运行本地Python和专用PostgreSQL容器测试，确认后从RED→GREEN继续，
最终重建当前镜像，重跑真实重启/卷保留和全部门禁；不要重复派独立审查。
```
