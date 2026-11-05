# 隔离 Flowable POC（非 PMS 执行接管）

Flowable **8.0.0** / Spring Boot **4.0.2** / Java **21** / PostgreSQL **16**。
只运行仓库固定合成流程，不读取 PMS `.env`/数据库，不调用 PMS、ERP、通知或 KPI。
PMS Legacy 执行器、模型发布及现有 API 保持不变。

## 启动（仓库根目录，Git Bash）

需要 Docker Desktop Linux containers。宿主机不需要 Java/Maven。
专用凭据不要复用 PMS 密钥，不要提交到 git；下面环境变量只保留在当前 shell：

```bash
export FLOWABLE_POC_TOKEN="$(python -I -c 'import secrets; print(secrets.token_urlsafe(40))')"
export FLOWABLE_POC_DB_PASSWORD="$(python -I -c 'import secrets; print(secrets.token_urlsafe(32))')"
export BUILD_REVISION="$(git rev-parse HEAD)"
# 未提交的实现也必须另外核对源码hash及image ID；此SHA仅为基线，不证明提交包含工作区实现。
mkdir -p var/flowable-poc
printf '' > var/flowable-poc/empty.env
# 显式空env文件，避免Compose发现根.env；秘密只从上述进程环境传递。
docker compose --env-file var/flowable-poc/empty.env -f engine/flowable-runner/compose.poc.yml config --quiet
docker compose --env-file var/flowable-poc/empty.env -f engine/flowable-runner/compose.poc.yml up -d --build --wait --wait-timeout 180
```

仅暴露 `127.0.0.1:8135`（可通过FLOWABLE_POC_PORT覆盖），数据库无宿主机端口。
项目 `logix-flowable-poc`，服务 `runner,poc-db`，卷 `logix-flowable-poc_flowable_poc_pgdata`。
不要把本POC接到生产网络；不要对主docker-compose执行同样操作。
启动后需保留原数据库密码/访问token供下次启动，不能每次生成新密码而沿用旧卷。
镜像构建跳过测试不代表测试通过。

## 契约

所有路径在 `/poc/v1` 下，含health/info也必须 `Authorization: Bearer <专用token>`。

| 方法/路径 | 作用 |
|---|---|
| GET /health、/info | DB/引擎就绪；实际版本、源码基线、POC标记；稳定的本次进程boot_id和JVM启动时刻boot_started_at |
| GET /fixtures | 固定样例及实际XML SHA256 |
| POST /commands | `{command_id:UUID,action,target,payload}`，成功返回 `{command_id,action,result}` |
| GET /commands/{command_id} | 查询已提交回执；404表示尚无成功提交，超时先查询原命令 |
| GET /instances/{id} | 运行/历史终态、精确任务ID、订阅、timer/deadletter数；单个实际timer的timer_due_at、历史completed_at（未完成为null） |
| GET /events?after_id=0&limit=100 | events/next_after_id/has_more，limit 1–500 |

动作及payload：

- DEPLOY：target=`serial|parallel-signoff|message-timer`，payload=`{bpmn_sha256}`；不接受上传XML。
- START：target=部署返回的definition_id，payload=`{business_key,context,variables}`。
  business_key严格`poc:<UUID>:<case_name>`；context只能为
  `{source:"POC_FIXTURE",process_id:910001,model_version_id:910001,project_id:null,round_id:null}`。
  这只是合成传递数据，不核验或对应真实PMS记录。
  variables仅message-timer允许waitDuration（ISO时长2–60秒，默认PT5S），其他样例为空。
- CLAIM/COMPLETE：target=精确task_id，payload=`{actor}`；必须是该任务候选/处理人。
  合成人员`poc-applicant,poc-quality,poc-plan,poc-reviewer-a,poc-reviewer-b`，不是SSO/RACI权限体系。
- MESSAGE：target=instance_id，payload=`{message_name:"PocResponse"}`，必须正好一个匹配execution订阅。
- SUSPEND/RESUME/CANCEL：target=instance_id，payload=`{}`。取消不证明业务补偿。

同command_id相同语义回放原回执，不同action/target/payload为409；失败整体回滚、不占成功ID。
同business_key不同command不再次启动。未知字段拒绝，样例变量不允许任意脚本/对象/URL。
新命令可以直接COMPLETE候选任务，不要求先CLAIM；已分派给他人则403。
并行/会签以task_id与execution_id区分，同activity_id不唯一。

监听器事件与引擎命令使用相同事务，事件落本POC数据库而非HTTP通知。
journal写入先持有全局PostgreSQL事务锁再分配游标，保证游标不跨越未提交的小ID；这是低吞吐实验策略，非生产事件总线。
ID空洞合法，游标/完成时间不代表并行业务因果。消费者按event_id去重，不能宣称跨系统exactly-once。
异步Job失败事务内的事件会回滚，故障需看引擎Job/deadletter和日志，不只查事件流。

## 真实 PostgreSQL 自动化测试

以下专用测试网络/容器不得与持久POC卷混用；测试不映射数据库端口，不挂Docker socket。
测试会创建/删除仅测试使用的数据库trigger来验证事件写入失败的回滚，不能指向生产库。

```bash
# 在上一节环境变量仍在的shell中：
docker network create logix-flowable-poc-test
docker run -d --name logix-flowable-poc-test-db --network logix-flowable-poc-test \
  -e POSTGRES_DB=flowable_poc -e POSTGRES_USER=flowable_poc \
  -e POSTGRES_PASSWORD="$FLOWABLE_POC_DB_PASSWORD" postgres:16
# 等到ready；最多30次，失败不继续：
ready=0
for i in $(seq 1 30); do
  if docker exec logix-flowable-poc-test-db pg_isready -U flowable_poc -d flowable_poc; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || exit 1
# Git Bash避免MSYS改写容器路径；Linux可不设该变量。
MSYS_NO_PATHCONV=1 docker run --rm --network logix-flowable-poc-test \
  -e FLOWABLE_POC_DB_PASSWORD -e FLOWABLE_POC_TOKEN -e BUILD_REVISION \
  -e FLOWABLE_POC_JDBC_URL=jdbc:postgresql://logix-flowable-poc-test-db:5432/flowable_poc \
  -v "$(pwd -W)/engine/flowable-runner:/workspace" -v logix-flowable-poc-m2:/root/.m2 \
  -w /workspace maven:3.9.9-eclipse-temurin-21 mvn -B test
# Linux将$(pwd -W)替换为$(pwd)。此专用测试容器仅有合成临时数据：
docker rm -f logix-flowable-poc-test-db
docker network rm logix-flowable-poc-test
python -m pytest tests/test_flowable_poc_probe.py -q
python scripts/check.py
```

不使用H2替代PostgreSQL并发/事件证据。Surefire中WorkflowIntegrationTest继承命令测试，报告数量包含复跑，不把34执行次数说成34个不同能力。
已知测试日志包含预期的`injected event failure`异常、框架Java agent警告；不隐去预期负例。

## 重启与卷保留烟测

以下命令会停止/启动**独立POC**；仅在获准操作该POC后执行。保持启动时的专用凭据和
BUILD_REVISION在进程环境中，根目录执行，显式empty.env避免读取PMS `.env`。
每次实验使用全新state文件，不能复用已验收或过期的before状态。

```bash
python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 \
  --expected-revision "$BUILD_REVISION" --state-file var/flowable-poc/restart-new.json --phase before-restart
# 立即执行：探针先确认实际timer仍未到期，再受控stop/观测/wait/start/after。
python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 \
  --expected-revision "$BUILD_REVISION" --state-file var/flowable-poc/restart-new.json --phase restart-runner

# 另一次独立实验：stop runner → 观测 → down（无-v）→ 到期后up → after，保留原卷。
python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 \
  --expected-revision "$BUILD_REVISION" --state-file var/flowable-poc/volume-new.json --phase before-restart
python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 \
  --expected-revision "$BUILD_REVISION" --state-file var/flowable-poc/volume-new.json --phase restart-stack
```

before记录实际Flowable timer due date与原boot。受控阶段核Docker Compose项目/service、容器及镜像身份，
记录inspect的实际FinishedAt、Running=false和daemon SystemTime观测时间；不用宿主机时间冒充daemon时钟。
停机时间/观测必须早于due，due必须早于新JVM boot，历史completed_at不得早于新boot。
全部时间出参为UTC（API明确+00:00，Docker原始时间保留Z）。Docker Desktop时钟偏差会使不可靠证据保守失败。

`after-restart`可重试读取已有受控停机证据，但不自行生成证据。不重启直接after、手工stop/start却没有
已观测证据、停机前timer已完成，均不写verified=true，也不消费原待办任务。
受控stop后验证失败仍在finally恢复Runner；失败状态和日志保留供诊断，不算恢复通过。
本机Docker/daemon/JVM证据用于隔离POC，不是防篡改证明或生产HA验证。

探针显式禁用环境代理、拒绝重定向；只允许loopback，不接受PMS8123，身份不符拒绝继续。
state只含本次合成命令、实例、时间、容器身份及事件游标，不含凭据。

### 断连后的原命令恢复

默认在`var/flowable-poc/commands/<command_id>.json`持久化请求及目标URL/revision，**发送前**原子落盘，
不保存token。可用`--journal-dir`选择目录；不能禁用持久化。POSIX临时文件仅owner读写；Windows继承
目录ACL（应将工作区放在当前用户专用目录）。相同ID不同请求/服务不覆盖，磁盘写入失败不发送。

断连/reset/截断响应/JSON解码失败/5xx先查原ID，只有404才重发一次相同请求；确定性4xx不盲重试。
查询仍失败则报告command_id、保留文件、不宣称成功。重新运行before不是恢复命令的办法：

```bash
python scripts/verify_flowable_poc.py --url http://127.0.0.1:8135 \
  --expected-revision "$BUILD_REVISION" --recover-command <原command_id>
```

此命令先核服务身份，再从journal加载**原请求**，先查回执，必要时只复用原ID重发；不生成替代ID。
成功journal仍保留，不能将本机文件当引擎已提交回执。若需要重做整个实验，先核对旧命令结局，再用新state。

正常停止保留卷：

```bash
docker compose --env-file var/flowable-poc/empty.env -f engine/flowable-runner/compose.poc.yml down
```

**不要自动执行 `down -v`、`docker volume prune`。删除POC卷会永久失去本实验历史，须单独确认。**

## 2026-11-05 复核修复验收

当前源码门禁：Python `655 passed, 4 warnings`；Java真实PG `Tests run:36, Failures:0, Errors:0, Skipped:0`
（包含继承复跑）。4项Python警告为既有弃用/表依赖循环；Java保留预期事件故障注入和异步乐观锁重试日志，
测试通过不代表高并发压力已验证。曾出现旧测试首500条事件假设导致3项失败，现已全分页读取，失败日志保留。

当前镜像`sha256:f61d4c75a5db6a30d5f63304a70ee9bd6a36a8a5dfc38d52e61b36d39a3866e7`；
Flowable8.0.0.0/Boot4.0.2/JRE21.0.13/PG16.15。基线SHA仍不含未提交实现，构建前Runner源码hash与当前镜像配对；
探针后续时钟修复另有宿主机hash，不假装已进容器。既有postgres:16缓存image RepoDigest为daocloud路径，
本轮未另选第三方源，未独立验证该旧缓存的上游来源；不能声称供应链字节级可复现。

真实CLI验证：无重启after拒绝；timer停机前已完成拒绝；Runner停机到期恢复；整栈down/up无-v保留卷；
原任务续办、原command回放、timer仅完成一次、事件续读和去重。实际引擎提交后模拟丢响应，新CLI按原ID恢复；
另有本地真实socket断连/截断回归。详细输出在当前worktree忽略目录的`fix-final-{python,java}.log`、
`fix-runtime-2.log`、`fix-command-loss.log`及`var/flowable-poc/fix2-*.json`，由执行台账索引。

待办Minor（本轮不扩大）：业务键UUID段校验不严格；未知路由返回503而非404。
无前端/PMS schema改动，前端E2E与生产Alembic check本片不适用。全部文件未提交，不自动合并或清卷。

## 边界

验证范围：串行、并行汇聚、全员多实例会签、消息/定时器分支、任务候选核对、挂起/恢复/取消、命令回放和事务journal。
未验证：排他网关专项、比例会签/仲裁、子流程/callActivity、外部服务任务、业务补偿、任意XML安全部署、PMS实际身份/投影/通知/KPI、生产HA/容量/升级/备份恢复、在途迁移、组织真实效果。
引擎表仅在隔离POC库自动升级；自有日志由Flyway管理；不能把此配置直接复制到生产或PMS Alembic。

[批准的实施边界与计划](../../docs/superpowers/plans/2026-11-05-isolated-flowable-poc.md)
