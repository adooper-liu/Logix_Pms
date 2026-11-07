# R3 首片：PMS 受控新实例沙箱接入设计

> 状态：待用户确认的具体设计；不是实施完成证明。
> 基线：934b33962afaa4e904002bee115ee48bd973bf0b（PR #24 已合并）；2026-11-05。
> 分支：feat/r3-sandbox-execution；复用现有隔离 worktree，POC 台账与数据保留。
> 承接：docs/bpm-lifecycle-gap-and-roadmap.md §8 R3、docs/bpm-technology-open-contracts.md §9/§11、docs/mainline-acceptance-next.md。

## 1. 已获授权与本设计的选择

用户已授权解除上一片禁止修改 app/web/alembic 的限制，进入 **PMS 的 R3 受控新实例沙箱接入**：可修改后端、必要前端和 Alembic；不连接真实业务库、不迁移 Legacy 在途实例、不部署生产。

上一片已完成提交 e32f0f8、推送与 PR #24 合并；实际合并提交934b339的 SQLite/PostgreSQL CI均通过。POC 的 Java36次测试、Python655项测试及真实恢复证据不等于本片接入证据。本片必须另行验证。

以下是本设计提出的工程选择，不冒称用户已经逐项批准：

- 先交付一个完整纵向闭环，首片开放 **串行人工任务 + 无条件并行分支/汇聚**，不把 POC 全部能力一次开放给 PMS。
- 复用 ProcessModelVersion、ProcessInstance、ProcessTask、原执行配置和页面；只新增无法由原记录表达的引擎映射、持久命令和消费凭据。
- Flowable 是接入实例的运行状态权威；PMS 是业务授权、表单/治理与本地投影权威。绝不两边各算下一步。
- 默认关闭；在独立、合成数据沙箱内按流程及明确模型版本启用。现有库无需开启 Flowable 即可升级和运行。
- 不另起选型或总路线，不重复审查已结束的 POC，不顺手修两项 POC Minor。

## 2. 为什么首片不是“把探针接到 PMS”

当前代码的硬约束：

| 当前事实 | 落点 | 本片必须解决 |
|---|---|---|
| Legacy 最多一个开放任务 | app/models/execution.py 的 uq_process_task_one_open | 仅对 Legacy 保留原约束；Flowable任务用精确引擎task/execution身份 |
| 完成任务会本地选择下一节点并调用 _advance | app/services/execution.py | 按实例固定provider分流；Flowable任务绝不进入Legacy推进器 |
| BPMN导入拒绝parallelGateway | app/services/bpmn.py | 仅在显式Flowable模型支持范围内保留并行语义；Legacy继续拒绝 |
| 发布版本保存完整XML和治理投影 | app/models/process.py / services/process_model.py | 部署固定版本的完整XML/hash，不能从简化节点/连线另造可执行路线 |
| POC只认固定fixture与poc-*身份 | engine/flowable-runner | 新受控沙箱契约不能伪装成fixture，也不能把PMS用户映射成poc-applicant |
| 当前幂等记录与业务写入在一个本地事务 | services/idempotency.py | 跨引擎命令先持久化再发送；本地rollback不能假装撤销远端提交 |
| 原实例详情只有单个“当前节点”摘要 | web/js/views/execution.js | 显示全部活跃任务、引擎来源与同步状态，不只展示第一条 |

## 3. 成功画面

1. 流程管理者在原执行配置中选择当前已发布模型，看到支持范围检查结果。
2. 显式请求部署；成功回执保存到该版本的引擎映射。页面分别显示“已发布”“部署成功”“允许沙箱启动”，不能混为一个状态。
3. 管理者在原准备确认约定下启用本流程的当前部署。启动者从原执行页发起一个合成业务实例，原模型/流程/可选项目与轮次身份不变。
4. 新实例固定provider=FLOWABLE及精确定义，原任务队列出现并行任务。候选人认领/完成，Flowable决定分支与汇聚；PMS不调用本地下一步。
5. 响应丢失时显示“结果待核对”，原command_id保留；恢复后查原回执和引擎事实，更新原实例/任务，不再启动第二个实例。
6. 原详情可看到事件续读位置、最后核对时间与缺口。重复事件不重复创建任务、审计或站内通知。
7. 同时已有Legacy实例仍沿旧快照与原语义完成；停用Flowable新启动不影响在途实例恢复/核对。

## 4. 开放范围与明确不做

### 首片执行子集

- 单个executable process；普通start/end、userTask、sequenceFlow、无条件parallelGateway。
- 串行人工任务、多个并行userTask、全部分支完成后汇聚；图内多次到达同节点仍以引擎task/execution ID区分，不能以node_key唯一。
- 首片只接受已验证、有限的无环结构；拒绝不能验证的网关配对/结构，不静默降级。
- userTask按固定节点分派快照关联PMS用户/角色/组织；表单字段沿用原定义校验，缺省分派不变成任意用户可办。
- CLAIM、COMPLETE、SUSPEND、RESUME、CANCEL及原ID恢复；完成任务不能传next_node_key干预引擎路由。

### 不在首片开放

- 排他表达式、比例/提前结束多实例、消息/定时器、子流程/callActivity、服务任务、脚本/Java类/任意URL、补偿和任意BPMN扩展。
- POC验证过的能力若不在沙箱支持清单中，不能借POC结果开放。
- 在途Legacy迁移、生产环境部署、HA/容量、跨系统原子提交、真实组织收益。
- 不新增万能连接器平台、第二个流程目录、第二套轮次或独立“引擎任务中心”。

首片串行/并行闭环完成后，再按R3原专项逐项开放等待/消息、会签等；本设计不把它们标为已交付。

## 5. 数据与身份

### 原模型和原执行配置

- ProcessModelVersion增加模型执行意图（LEGACY/FLOWABLE），默认LEGACY；草稿、评审、发布仍走原生命周期。已冻结/发布版本不可原地改意图或XML。
- 当前发布版本不因部署/启用而重建。部署针对明确model_version_id及XML SHA256，不取“最新草稿”。
- 原ProcessExecutionConfig扩沙箱provider与启用的部署引用；启用绑定准备指纹。新发布或配置/权限依据变化使新启动失效，不能静默沿用旧定义。
- 项目仍五阶段，薄轮次仍四身份；有round_id时继续核原released_model_version_id及准备确认。

### 必要的新增映射

新增一个薄引擎部署映射，保存model_version_id、XML hash、受控engine namespace、部署/定义ID、支持清单版本、分派/表单配置指纹、部署command引用和确认人/时间。

- 同引擎/模型/hash/配置指纹部署幂等复用；不同hash或不同定义不覆盖旧映射。
- 映射不是第二个发布主库；只有成功远端回执且身份/hash一致才记部署成功。
- 失败/结果未知保留命令，不伪造definition_id。
- 引擎地址/凭据来自部署环境，不由浏览器传任意URL；映射只引用受控namespace。

### 原实例、原任务

- ProcessInstance增加固定provider、部署引用、engine_instance_id及同步/核对状态；旧数据回填LEGACY，旧实例provider不可切换。
- ProcessTask增加provider、engine_task_id、execution_id、activity_id；Flowable精确task ID在引擎namespace内唯一，本地node_key只作活动定位。
- 保留原task主键、工时、审计/事件引用；不另建一套面向用户的任务表。
- uq_process_task_one_open改为仅约束LEGACY开放任务，不能直接全局删除兜底；任务provider必须与父实例一致。
- 引擎task唯一约束和事件/命令身份约束在SQLite/PostgreSQL上均测试。
- 本地“待同步/待核对”是技术状态，不另造八阶段或业务成功状态；引擎未核实前不能显示已完成。

## 6. 持久命令与双库事务边界

新增专用引擎命令记录，不把原HTTP幂等表假装成跨系统事务日志。

- command_id在PMS发送前与明确目标、本地对象、发起者、规范化参数hash、期望模型/定义/任务版本一起提交。
- 原Idempotency-Key映射到该原命令；相同身份异参数409，回放前重新核用户与对象权限。
- 同一任务的冲突写命令串行；已有结果未知命令时先核旧命令，不换ID完成同一任务。
- 命令状态只表达“已保存待发送/结果待核对/已确认成功/确定拒绝”等技术结局，标签由后端下发。
- 有界超时和重试；先GET原回执，404才可复发原ID。网络异常/5xx不当作业务拒绝，确定性4xx不盲重试。
- 成功远端回执与本地投影应用可重做；本地应用失败后留恢复记录，不假定引擎回滚。
- HTTP可优先尝试快速完成；无法在时限内确认返回202和command_id/status，不返回伪201成功实例。前端保存原ID并轮询。
- 恢复端点和后台重试共用同一命令服务；不在GET列表时偷偷发送业务写命令。
- 不承诺跨库exactly-once。依靠远端幂等、持久原ID、投影去重和对账达到可解释的恢复。

## 7. 引擎服务边界与XML安全

- 保留/poc/v1的fixture契约；新增默认关闭的受控沙箱契约，只有专用PMS适配服务能调用。其启用开关、token、引擎namespace与POC身份区分。
- 共用同一套已验证的命令幂等/事务journal机制，扩展类型化动作及namespace，不复制第二套去重算法。
- 不复用POC固定context；沙箱context明确process_id/model_version_id、本地实例关联及可选project_id/round_id，并核定义归属。
- actor从PMS当前登录用户产生，浏览器不能提供替代actor。适配器按PMS候选/组织/原授权规则判断，Runner同时核其引擎任务候选/处理人，不因机器token跳过任务参与者检查。
- MANAGER可治理/核对不等于可冒名完成。首片完成动作须满足明确候选/本人处理范围，管理者需显式改派后本人办理；改派也是可审计引擎命令。
- 分派来自部署时冻结的受控映射，在引擎任务创建时应用；不将自由文本泳道名当用户ID，也不允许客户端覆盖冻结身份。
- 完整XML先在PMS做尺寸、实体/外部引用、命名空间、单process、节点/网关/流结构及支持清单检查，Runner部署前再次独立校验。
- 拒绝DTD/entity、script、service/taskListener/executionListener、class/delegateExpression/expression、连接器/任意URL、未知可执行扩展和Java对象变量；只保留明确无执行含义的DI/文档/PMS治理元数据。
- 不通过删除危险元素后继续部署；不支持则明确拒绝并列出位置。
- 不从简化投影重新生成另一个执行XML。哈希绑定实际提交字节；如需固定身份/元数据，转换规则版本和源/执行hash均固定并可核对，不能悄悄改路由。
- HTTP客户端禁环境代理、拒绝重定向，限制响应大小及schema，凭据不出现在前端/命令/事件/日志。未启用时不连接引擎。

## 8. 事件、投影与对账

- 引擎事务journal继续同数据源/同事务；本片低吞吐验证不宣称全局journal锁适于生产。
- PMS按engine namespace和journal游标拉取，校验契约版本及模型/实例身份；事件event_id持久去重。
- 一个本地事务内保存收件、原任务/实例投影及游标；失败不能前移游标。重启后从持久位置重读。
- 未知实例、错定义、错上下文事件留拒绝/缺口证据，不能自动创建跨流程业务记录；不直接跳过后假装同步完成。
- 事件和快照核对协同：事件保留历史，受控快照用于核实当前事实；防止旧事件覆盖新状态。核对不产生虚假TASK_COMPLETED。
- 并行实例的活跃任务为集合，待办列表及详情显示全部；current_node_*只作兼容摘要，不是引擎令牌权威。
- 命令回执应用、事件消费和显式核对走同一投影合并入口；同一转换只记录一次原任务事件及站内通知。
- 不新建通知系统。复用原通知，但Flowable副作用只能由已确认的投影转换产生；未知/回放不重复发通知。
- 出站外部Webhook默认不为沙箱启用；原入站Webhook若未实现相同provider权限与持久命令路径，明确拒绝操作Flowable实例，不能落回Legacy推进器。
- 工时保持原本地事实；不假冒引擎已完成任务。删除/归档、超期升级、挖掘/KPI等入口必须检查provider适用范围，不得对引擎实例执行本地推进或用单任务假设静默改状态。
- 停用新启动不停止已在途的消费/命令恢复；彻底停用前须对账并保留历史。

## 9. 页面与用户反馈（沿原入口）

不增加主导航、不加构建步骤，不在views之间互相import；新增小模块放原execution的shared子模块，枚举标签由后端下发。

| 位置 | 增量 | 直接文案 |
|---|---|---|
| 原设计器版本区 | 模型执行意图、支持检查、明确版本/hash；保留同画布 | “执行目标：Flowable沙箱”“不支持的构造，尚未部署” |
| 原执行配置/上线准备 | 当前发布版本、部署结果、指纹、允许沙箱启动开关；部署/启用分开 | “已发布，尚未部署”“部署成功，待确认启用” |
| 原启动弹窗 | 固定provider/模型与环境标识；无有效映射禁启 | “仅沙箱合成数据，不代表生产上线” |
| 原任务队列/办理弹窗 | 显示精确任务身份，复用表单/权限；Flowable不显示下一节点选择 | “由引擎决定后续路径” |
| 原实例详情 | provider、模型/定义、全部活跃任务、同步时间/差异 | “并行办理中：2项待办”“当前状态待核对” |
| 原执行状态反馈 | 展示原command_id与恢复动作，禁重复提交 | “请求已保存，结果待核对；请勿重新发起” |
| 无权限/引擎不可用 | 后端安全摘要，不暴露token/堆栈 | “无权办理此任务”“引擎暂不可用，原请求已保留” |

空、加载、超时、确定拒绝、版本失效分别有反馈；不把技术待核对显示为业务完成或允许用户凭猜测换ID重试。

## 10. 迁移、默认与退出

- PMS模型、约束和新增表只走Alembic，alembic.ini保持ASCII；真实引擎表不纳入PMS Alembic。
- 迁移旧实例/任务默认LEGACY，保留旧数据、开放任务唯一性和原运行快照；不为旧历史猜engine_instance_id。
- 新代码默认关闭沙箱，不配置token/引擎时原应用照常启动。
- 独立沙箱PMS DB、独立引擎DB、独立端口/network/卷；不读取根.env，不复用真实业务凭据，不更改原POC持久卷数据。
- 回退首选关闭新启动并保留恢复和消费。存在Flowable在途/历史时禁止破坏性降级丢弃映射；没有引擎数据的测试环境验证完整downgrade。
- 不能将已经远端执行的命令用本地rollback或删除记录当作撤销；业务取消需要明确引擎CANCEL及原回执。

## 11. 实施落点与完成门槛

### 文件落点（计划阶段可拆分，不作为提前建全部实体的要求）

- app/models/execution.py、相关新增薄映射模型、app/schemas/execution.py、app/core/config.py。
- app/services/execution.py与execution_flow.py按provider显式分流；新增受控engine transport/command/projection服务。
- app/api/v1/execution.py原启动/任务/控制入口及受权限保护的部署、命令核对接口。
- app/services/process_model.py / bpmn.py原模型生命周期和支持范围；不再生成第二套执行图。
- 原后台入口、inbound、通知/超期等provider触点；只做避免双算所需增量。
- engine/flowable-runner增加默认关闭的沙箱契约及测试，复用journal。
- web/js/views/execution.js、designer及其shared小模块；tests/test_frontend_structure.py在新增视图时同步。
- Alembic迁移、双库测试、Java真实PG集成、专用沙箱启动/端到端验证脚本和README。

### 必须逐项通过

1. 原Legacy全量测试及旧实例恢复通过；默认不开启、不请求引擎；不能因并行支持放开Legacy约束。
2. 版本/部署hash/配置指纹一致；错流程、错项目/轮次、未发布、被替代或已失效启用均拒绝；回放不绕过当前权限。
3. 串行及真实并行分支→汇聚完成；多个任务身份不混淆，一支完成不越过汇聚；本地_advance不被调用。
4. 同command_id异参数409、并发同ID只执行一次；远端已提交/响应丢失/本地应用失败/双方重启后可按原ID恢复。
5. 跨用户/组织拒绝、VIEWER拒绝、停用身份拒绝、机器token不能冒名；管理权限不自动转换为任意任务候选。
6. 重复/迟到事件、消费中断、错定义/实例、游标回滚与快照核对有可复现用例，不重复投影/通知。
7. 任意XML执行、外部实体/引用、脚本/表达式、未知扩展、错误消息结构、代理/重定向均被拒绝。
8. 模型/约束迁移在临时SQLite和专用PostgreSQL通过；alembic check对当前代码无漂移。
9. 当前源码镜像/服务身份核对后，沿真实PMS API和原页面做沙箱E2E；前端修改运行scripts/verify_frontend.py及本片增量验收。
10. python scripts/check.py、全量Java真实PG测试、保护范围/凭据扫描通过；真实样本/生产HA等未验证项继续单列。

## 12. 设计自检与待批准项

按构建者视角自检：POC成功不等于可直接接入；XML源、候选身份、跨库命令、并行约束、触点分流、页面异步反馈和恢复均有明确落点。此次不再派代理做文档评审，尊重原生执行及停止重复评审循环的约定。

**需用户确认的是本片完整范围**：先在独立沙箱交付串行/并行人工任务纵向闭环，接受新增薄映射/命令/消费凭据及原对象增量，后续能力不假装已开放。确认后写任务级实施计划并原生TDD执行；本文件尚未授权生产启用，也不自动授权下一片再次推送/合并。
