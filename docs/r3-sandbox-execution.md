# R3 首片：PMS–Flowable 沙箱执行与验收

> 范围：串行人工任务、结构化无条件并行分支/汇聚；默认关闭，只用于合成数据沙箱。
> 实施基线：`934b33962afaa4e904002bee115ee48bd973bf0b`；实施分支：`feat/r3-sandbox-execution`。提交与合并身份以 Git / PR 记录为准；本地镜像仍须另核源码指纹，合并不等于部署。
> 设计与任务：[批准设计](superpowers/specs/2026-11-05-r3-sandbox-execution-design.md)、[任务计划](superpowers/plans/2026-11-05-r3-sandbox-execution.md)。

## 1. 对应哪条主线

本片承接 M6 执行能力补齐、既有路线 R3。交付链是：

**原发布模型版本 → 明确部署映射 → 原上线准备确认 → 显式启用 → 原执行页启动/办理 → 引擎回执与事件核对。**

- 模型仍是 `ProcessModelVersion`，实例/任务仍是 `ProcessInstance` / `ProcessTask`；没有第二个任务中心。
- Flowable 决定后续活动；PMS 负责当前用户/组织/表单/原授权规则及本地业务投影，不再次计算下一节点。
- 原实例固定 `LEGACY`，新引擎实例固定 `FLOWABLE`；原 Legacy 单开放任务约束保留，Flowable 用精确引擎 task/execution 身份。
- 项目仍五阶段，流程八阶段仍为导航；轮次与四身份不变。
- 本片没有开放消息/定时器、会签、表达式排他、子流程、外部服务任务；不迁移 Legacy，不部署生产。

## 2. 已实现的使用路径

### 原设计器

在原画布选择执行目标，保存完整 BPMN XML。Flowable 沙箱只接受单个可执行 process、普通 start/end、userTask、sequenceFlow 和结构化并行网关。必须无环、连通、并行分支正确汇聚；不支持构造直接拒绝，不删除后悄悄部署。

执行意图随原模型版本保存，冻结后编辑形成新版本；评审/发布仍走原入口。发布不等于部署，部署不等于允许启动。

安全检查包括大小、元素/属性/命名空间、元素位置及图结构；拒绝 DTD/entity、脚本、Java 类、任意 URL、监听器/表达式及未知可执行扩展。PMS 与 Runner 各自验证。原串行概率测算不用于 Flowable 模型，返回无测算结果，不显示伪并行周期。

### 原执行配置

1. 明确当前已发布模型。
2. 为 userTask 配置可核验的实际沙箱用户分派，空候选不能部署。分派/表单/准备依据与候选资格固定进部署指纹。
3. 记录原上线准备约定，由指定的非编辑者本人确认；测试的“不适用”只是合成场景，不是实际业务授权。
4. “部署当前发布版本”后，映射保存源 XML hash、实际执行 XML hash、定义/部署 ID、配置指纹。
5. 再“确认启用沙箱新启动”。新版本、分派或准备依据变化时，不再允许启动；即使依据失效，仍能停止新启动。

### 原任务与实例页

- 从原启动弹窗启动，沙箱不接受临时分派和自由启动变量。
- 原任务队列展示全部并行任务；认领、完成、改派、挂起/恢复/取消使用持久命令。
- 完成动作不接受 `next_node_key`，路径由引擎决定；管理者不是自动候选人，不能冒名办理。
- 完成时表单/备注和工时只在引擎回执核对后落账，重放不重复登记；直接完成未认领任务也记录实际完成人。
- 原实例详情展示 provider、同步状态和全部活跃任务。未决命令显式显示“结果待核对”，不是业务完成。
- 首片禁止对引擎历史做物理删除；原 Legacy 改派/推进及自动升级不能改变引擎实例。本片不把并行完成先后送入串行挖掘路径口径。

## 3. 可靠性边界

### 命令

`Idempotency-Key` 指向发送前已提交的原命令。相同用户/命名空间/键、不同参数返回409。同一实例有结果未核实的写命令时，先恢复原请求，不能并行换ID取消或推进。

- 查询原回执，只有404才发送/重发同一个 command_id。
- 回执查询失败、断连、截断响应或5xx保留 UNKNOWN；不能据查询401/403推断原命令未执行。
- 确定性命令POST拒绝不盲重试。
- 远端成功与本地投影成功分别记录。本地应用失败时保留远端回执，可恢复重做；`local_applied` 与本地落账同事务，避免重复工时。
- 浏览器会话保存未决请求键/原ID，禁止另发替代请求；原恢复入口核对当前身份和权限。

原任务表单可能包含合成字段；命令持久请求保留恢复所需数据，不保存机器 token。浏览器未决请求也会临时保留填写内容，因此本片只允许合成数据，不能用于真实敏感业务。

### 事件与投影

引擎 journal 与引擎改变同事务；PMS 收件按 namespace/event_id 去重。投影和游标同一事务，错实例/定义/上下文、集合不一致或本地失败不前移游标。迟到事件触发当前事实核对，不按到达顺序重新计算后继；终态不能被旧运行态复活。

事件核对只处理已知本地实例，不自动把未知引擎事件建成业务记录。换全新 PMS 测试库而继续使用旧引擎历史时，未知上下文会阻止游标推进，这是保守缺口提示，不能手动跳过冒充已同步。日常应成对保留沙箱库，或为新实验使用明确隔离的引擎数据环境。

本机低吞吐 journal 使用全局事务锁；这不是生产事件总线，不承诺跨库 exactly-once、HA 或吞吐。

## 4. 独立运行（仅获准的本地沙箱）

需要现有 Python 开发环境与 Docker Desktop Linux containers。在**没有根 `.env` 的独立 checkout/worktree**运行；`scripts/run_engine_sandbox.py` 检测到根 `.env` 会拒绝启动，不读取真实业务配置。

### 首次创建专用凭据

只在新沙箱执行；若文件已存在，保留原密码与卷，不覆盖。不打印该文件，不提交它。

```bash
python -I -c 'from pathlib import Path; import secrets; p=Path("var/r3-sandbox/runtime.env"); p.parent.mkdir(parents=True,exist_ok=True); f=p.open("x",encoding="utf-8"); f.write("FLOWABLE_POC_TOKEN="+secrets.token_urlsafe(40)+"\nFLOWABLE_POC_DB_PASSWORD="+secrets.token_urlsafe(32)+"\nFLOWABLE_SANDBOX_TOKEN="+secrets.token_urlsafe(40)+"\nBUILD_REVISION=934b33962afaa4e904002bee115ee48bd973bf0b\n"); f.close(); (p.parent/"empty.env").touch(exist_ok=True)'
```

`BUILD_REVISION` 只标源码基线；未提交实现还须以文件hash和实际镜像ID核对，不可把基线SHA说成包含工作树实现。

### 构建独立 Runner

下面将专用文件载入子进程环境，Compose 显式使用空 env 文件，避免自动发现根 `.env`：

```bash
python -c 'import os,subprocess; from pathlib import Path; e=os.environ.copy(); e.update(dict(x.split("=",1) for x in Path("var/r3-sandbox/runtime.env").read_text().splitlines())); subprocess.run(["docker","compose","--env-file","var/r3-sandbox/empty.env","-f","engine/flowable-runner/compose.sandbox.yml","up","-d","--build","--wait","--wait-timeout","180"],env=e,check=True)'
```

| 设施 | 身份 |
|---|---|
| Compose 项目 | `logix-r3-sandbox` |
| Runner | `127.0.0.1:8136`，独立机器认证 |
| 引擎 PostgreSQL | 仅容器网络，无宿主机端口 |
| 引擎数据卷 | `logix-r3-sandbox_r3_engine_pgdata` |
| PMS | `127.0.0.1:8124` |
| PMS 合成库 | `var/r3-sandbox/pms.db`，启动经 Alembic 升级 |
| 独立 PG 测试容器（本轮） | `logix-r3-pms-test-db`，`127.0.0.1:5546`，只用于测试 |

不触碰原 `logix-flowable-poc` 项目、8135端口或其卷；不要用主 `docker-compose.yml` 启动此实验。

### 启动 PMS 与验证

终端A：

```bash
python scripts/run_engine_sandbox.py
```

终端B（Git Bash，仓库根目录）：

```bash
PYTHONPATH=. python scripts/verify_engine_sandbox.py http://127.0.0.1:8124
PYTHONPATH=. python scripts/verify_engine_sandbox.py http://127.0.0.1:8124 --serial
python scripts/verify_frontend.py http://127.0.0.1:8124 var/r3-sandbox/screenshots
python scripts/check.py
```

两个增量 E2E 都沿真实原发布/不同评审者、准备确认和页面操作；测试新建合成流程，不删除引擎历史。本片未提供生产启动命令。验收完成停止自己启动的 PMS 进程，不按广泛进程名杀服务、不删除卷。

### 测试真实引擎恢复

默认全量 pytest 跳过一项需要实际独立引擎的 opt-in 集成测试；必须另行明确运行，不能把跳过称为通过：

```bash
python -c 'import os,subprocess,sys; from pathlib import Path; e=os.environ.copy(); e.update(dict(x.split("=",1) for x in Path("var/r3-sandbox/runtime.env").read_text().splitlines())); e["R3_REAL_ENGINE"]="1"; e["R3_RESTART_ENGINE"]="1"; subprocess.run([sys.executable,"-m","pytest","tests/test_engine_real.py","-q","-s"],env=e,check=True)'
```

`R3_RESTART_ENGINE=1` 会重启**此独立 Runner**；只在已授权环境执行。该测试使用临时 PMS 测试库与真实沙箱引擎，覆盖远端已提交后响应丢失、本地投影失败、原ID恢复和事件核对。双方真实进程重启与浏览器刷新恢复另有本轮有界编排证据，见下节。

Java真实PG测试命令沿 [Runner说明](../engine/flowable-runner/README.md) 的专用网络/测试数据库方案，不用H2代替；PMS PostgreSQL 测试必须指向全新的独立测试库，`conftest` 会重建表，绝不能传真实业务库地址。

## 5. 当前验收证据与缺口

执行原输出在本 worktree 的 `.superpowers/sdd/2026-11-05-r3-sandbox-execution/`；该目录和 `var/` 不提交。

| 验证 | 已观察结果 | 原输出 |
|---|---|---|
| `python scripts/check.py` | `686 passed, 1 skipped, 4 warnings`，format/lint通过 | `final-python.log` |
| 新鲜独立 PostgreSQL PMS 全量 | `686 passed, 1 skipped, 4 warnings` | `final-postgres-fresh.log` |
| Java真实 PostgreSQL 全量 | `Tests run: 51, Failures: 0, Errors: 0, Skipped: 0` | `final-java-current.log` |
| 当前真实 PMS API→Runner | 并行汇聚、权限、模糊响应/本地失败恢复、重放、工时、事件去重/游标拒绝通过 | `final-real-current.log`及定向RED/GREEN日志 |
| 原页面串行／并行 | 均PASS，不是一支HTTP200冒充闭环 | `final-browser-{serial,parallel}.log` |
| 全站前端 | exit0；预期负例请求及少量条件跳过保留 | `final-frontend.log` |
| SQLite Alembic upgrade/check | exit0，`No new upgrade operations detected.` | 当前CLI输出及`alembic-upgrade-final.log` |
| 独立 PG 迁移 upgrade/check/downgrade | PASS | `pg-migration.log` |

Java51为执行次数，包含继承复跑。4项Python警告是既有FastAPI客户端弃用及data_flow/kpi_definition表依赖循环。Java日志包括预期事件故障注入和乐观锁重试，不能据测试绿宣称生产高并发已验证。

本轮曾对重复使用的PG测试库运行失败：`drop_all`遭已有依赖阻止，exit4，尚未进入业务断言；没有删除旧库，改用专用容器的新数据库名重跑通过（`final-postgres.log`与`final-postgres-fresh.log`均保留）。Windows PATH、编码和脚本引用错误不当作业务RED证据。

当前 Runner 镜像为 `sha256:b3f8215d9149013fcacee6e32b90e48c2aebf827a09726ac2f8a2b3accefb77f`；基线SHA仍为934b339，不含未提交本片。源码指纹见`var/r3-sandbox/final-source-hashes.json`，重建/更改后必须重新核对，不能把健康旧容器当新代码。

### 收尾补验与审查限制

- `browser-restart-result.log`：真实浏览器的START请求已在远端提交后丢失响应；停止自己拥有的PMS进程、重启独立Runner、以新PID启动PMS、刷新同一浏览器后，原会话键仍在；恢复只得到一个原实例，无重复启动。结束后停止自有PMS，保留全部引擎卷。
- `final-control-auth.log`：原API改派、挂起、恢复、取消及任务取消状态均通过；原命令发起者停用后恢复403，组织范围不符404。manager非候选拒绝与VIEWER拒绝另有回归，不能据此宣称完整生产权限策略已验收。
- 浏览器未决交互为人工触发“核对原请求”，没有引入自动重发策略；它保留原ID，不等于完成生产离线作业调度。
- 独立复核调用被中断，没有产出复核结论；后续为原作者逐文件自查，不称独立审查通过，也不自动推送/合并。

**本片的软件实现与已批准沙箱验收已完成收尾；生产/真实业务能力未验证，独立代码复核没有完成结论。** 下一次提交或合并前仍须由用户决定，不能将本说明当自动发布许可。

## 6. 停用、恢复与明确不做

关闭原配置的新启动不删除在途命令、事件或映射。worker恢复命令及事件消费需保留原专用配置；来源不明/游标缺口保留待核对，不自动跳过。升级/降级经Alembic；存在引擎记录时降级保护拒绝丢弃映射。

不执行`down -v`、卷清理、Legacy迁移或生产接管。消息/定时器、服务任务/补偿、生产HA/容量/升级恢复、真实组织收益均不属于本片验收结果。原POC两个Minor继续保留，不以其挤掉主体闭环。下一步是补齐本片已列门槛，不是扩大支持清单。
