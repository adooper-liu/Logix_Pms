# 产品语言清单与当前差异

> 状态：首版静态盘点与待评审整治清单；2026-11-03，代码基线 `4607792`。本轮不改业务代码、API、字典数据或页面。
> 唯一表达规则见[产品语言规范](bpm-interface-content-standard.md)；业务边界见[产品原则](bpm-product-principles.md)；页面职责见[拆分表](page-responsibility-and-decomposition.md)。本清单不另定义状态机。

## 1. 范围、读法与缺口

本版核对了视图注册、标题/导航、公共格式化与请求层，抽查项目、模型、运行、KPI、资产、组织、帮助及示例。下列是**有源码证据的重点条目**，不是所有中文字符串、数据库字段、报错分支或导出内容已经逐项盘完。

- `L-*`：术语/标题/反馈/样例差异；`F-*`：对象字段；`D-*`：枚举/字典权威来源。编号只是文档追溯，不是拟新增数据表。
- “重复源”表示同一概念多处定义，即使当前字面一致也有漂移风险；不据此断言所有独立字典都应合并。
- “拟统一”是目标而非已实施。改动若涉及语义、校验或权限，不得用批量文案替换完成。
- 建议责任用业务/后端/前端/测试职责描述，尚未指定实际个人。落实状态本版均为已观察、拟统一或待定值，没有“已验证实施”。

## 2. 当前文字差异与处置清单

| 编号/优先级 | 当前事实与证据 | 建议标准/处置 | 权威来源、消费及验收 |
|---|---|---|---|
| L-01 高 | 项目BPR为“BPR 阶跃式重组”，驾驶舱为“BPR 重组”；BPI/精益也有长短差别。`app/api/v1/projects.py:79`、`app/services/dashboard.py:51` | 标准名建议“业务流程重组（BPR）”“业务流程优化（BPI）”“精益改善”“混合模式”；窄位短名BPR/BPI，解释保留阶跃式/渐进式 | 后端项目域唯一标签定义，明确label/short_label使用；列表、推荐、汇总、帮助同义，不改方法code |
| L-02 高 | 项目CLOSED显示“已完成”；枚举注释为“已结项”。`app/api/v1/projects.py:86`、`app/models/enums.py:18`、`app/services/dashboard.py:58` | `project.CLOSED`拟为“已结项”，不等于改善达标；实例/任务的“已完成”不替换 | 项目域标签单一源，项目卡/驾驶舱/筛选/导出一致；不改关闭门禁 |
| L-03 高 | 同一Project.owner界面同时称“Owner”“流程 Owner”“项目 Owner”。`web/js/views/projects.js:354`、`:461`、`:633`；归属语义见`app/schemas/project.py:82` | 该Project字段为“项目负责人”；ProcessArch字段才是“流程负责人”；首见可加Owner说明 | 字段语义由业务确认；权限仍以现有owner_user_id为准，不自动更改流程Owner，不合并角色 |
| L-04 高 | `monitor`与`dashboard`顶栏均“运营驾驶舱”；monitor内部已有不同h2。`web/js/core/state.js:76`、`:83`、`web/js/views/monitor.js:1227` | 总览“运营驾驶舱”；子主题“流程分析/流程指标/流程异常/工时与产能/过程挖掘” | 前端统一页面标识→标题/页签/帮助；保留monitor旧链接；子主题切换后h1/h2/返回来源一致 |
| L-05 高 | `HEAT_LABEL/SEV_LABEL/EXC_LABEL/KN_LABEL/NODE_LABEL`在前端，流程卡另有severity表。`web/js/core/format.js:92`、`web/js/views/process_card.js:80` | 将业务中文消费收敛到对应后端域；色调/图标可留前端 | 确认每处现有消费者再删定义；meta与列表行标签覆盖全部使用值，不能仅搬到另一份JS |
| L-06 高 | KPI颜色标签在monitor路由与kpi服务重复。`app/api/v1/monitor.py:82`、`app/services/kpi.py:29` | 一域一源；是否由“红/黄/绿”升级为“未达标/预警/达标”先核实际判定 | 后端确认计算/来源质量含义；GRAY不能自动译为“无风险”；新标签不冒称新增质量算法已实现 |
| L-07 高 | 模型状态标签在process_model及deliverable重复。`app/services/process_model.py:29`、`app/services/deliverable.py:61` | 模型标签复用原模型域；映射到交付物状态仍是显式业务投影，不合并两种状态 | 后端避免循环依赖；历史被替代模型可识别，不把PUBLISHED和EFFECTIVE视为同一code |
| L-08 高 | 网络失败提示“确认uvicorn正在运行”并拼异常。`web/js/core/api.js:43` | 用户：“暂时无法连接服务，请重试。”；开发诊断保留在受控日志 | 前端基础设施统一网络反馈，不自动重试写请求；测试断网不泄露内部地址/栈 |
| L-09 高 | 非字符串detail被JSON.stringify，403再加“权限不足”。`web/js/core/api.js:54` | 兼容原detail并渐进接稳定code/field_errors；字段错误就近，顶部概要 | 后端明确安全响应，前端不直接铺422数组或重复前缀；400/409原因不能仅按HTTP码猜 |
| L-10 高 | 技术字段出现在用户报错，如“assignee_user_id 指向的用户不存在”。`app/services/execution.py:257` | 用户：“所选任务处理人不存在或不可用，请重新选择。”；是否“不可用”须与实际检查一致 | code/field定位assignee_user_id，技术名只在API文档；不扩大当前账户有效性校验的宣称 |
| L-11 中 | 顶栏placeholder写“搜索流程/项目/工具/知识”，路由只对projects/toolbox/map/pcf派发。`web/index.html:67`、`web/js/core/router.js:165` | 按当前页声明真实搜索范围；无搜索能力隐藏或禁用并说明，不冒充全局搜索 | 前端页定义声明search能力；输入实际作用于声明对象，换页清理/恢复策略可测 |
| L-12 中 | 返回栏直接拼URL参数key=value。`web/js/core/router.js:112` | 默认显示“返回〔来源主题〕”；必要上下文用可见名称/安全摘要，不铺技术参数 | 页面元数据统一标题；仅在有权限且成功解析后显示对象名，URL不能泄漏不可见对象 |
| L-13 中 | 十层页副标题“这条会不会跑”。`web/js/views/pilot.js:1141` | “核验本流程的上线条件”；层级、适用性与真实证据分开 | 原pilot规则不因改文案而变化；缺证显示待补，不把计数当运行有效 |
| L-14 中 | 流程卡副标题“对象360·模块聚合”，现有规范又曾拟改标题“流程闭环”。`web/js/views/process_card.js:380` | 本轮规范已收敛保留“流程卡”；说明“查看本流程的目标、版本、运行结果和下一步。” | 前端统一导航/帮助/返回名；保留聚合价值，不在卡片复制各模块编辑器 |
| L-15 中 | 交付物页总标题不能体现当前四种不同主题。`web/js/views/deliverables.js:208` | 活动主题分别为“项目交付物/流程标准文件/工具模板/资产基线/治理发现”；最后两项拆分是拟增主题 | 页面表P-12；版本/晋升/复制仍操作原对象，不新建“统一资产”主库 |
| L-16 中 | 执行页作业与运行配置、集成同一层页签。`web/js/views/execution.js:316` | 外壳称“流程执行”，当前页明确“待办任务/流程实例/运行配置/系统集成” | 页面表P-11；“我的待办”为筛选标签，公共队列不是我的任务；权限仍服务端核验 |
| L-17 中 | 组织界面“系统角色/治理角色”都与成员有关，但含义不同。`web/js/views/orgs.js:104`、`app/models/enums.py:151` | “系统角色”表示系统操作资格，“治理角色”表示业务职责；岗位与组织分别命名 | 原auth/governance/positions/org-units来源；不能因一个业务任命自动授MANAGER权限 |
| L-18 中 | “表单/模板”可指运行输入、交付物类型或文件模板。`web/js/views/execution.js:92`、`app/models/enums.py:167`、`:195` | 分别说“任务表单”“表单类交付物”“工具模板/文件模板”；ONLINE为格式非业务成效 | 表单与资产领域分别维护；具体输入提示不把任务表单称Excel模板 |
| L-19 中 | “基线”既用于项目baseline_value，又用于AssetBaseline及分析说明。`app/schemas/project.py:96`、`web/js/views/deliverables.js:1372`、`web/js/views/monitor.js:1227` | “基线值/现状基线/资产基线”按对象使用；现状冻结对照尚未实现 | 后端字段不改；不得靠新标签宣称目前已固定指标口径/正式样本 |
| L-20 中 | 工作流同时提供项目办理与方法手册。`web/js/views/workflow.js:76`、`:155`、`:697` | 项目页“改善工作台”，教学页“五阶段方法手册”；五阶段是项目交付，不是长期流程寿命 | 保留现有workflow tab别名，具体见P-10；历史治理体系项目有独立口径，不能批量改阶段数字 |
| L-21 中 | 专业说明“事例/走法/必须核对”等口语存在。`web/js/views/monitor.js:117`、`:475` | 按真实模型含义选“纳入样本/模型路径/观察路径”；非增值不能自动叫“必须核对” | 业务核分类后才更名，不能通过润色改变增值判定或把模型时间写成实测 |
| L-22 中 | 项目发起人字段有“发起人/部门”“发起人/赞助人”。`web/js/views/projects.js:462`、`:635` | Sponsor统一“项目发起人”；department另标“所属部门”，不把赞助人误解为付款方 | 对照Project.sponsor/department各自值，不拼成一个新字段；清单F-04 |
| L-23 中 | 知识资源用法示例为“审批时长下降40%，连续4周稳定”。`web/js/views/knowledge.js:215` | 标明示例，写“记录观察窗口、样本、前后值与证据来源”，数值仅用于教学 | 无证据不得预填收益；已保存用户说明不重写，样例改动不等于收益算法实现 |
| L-24 中 | 运行变量/备用输入JSON示例用中文key，节点表单常用approved等key。`web/js/views/execution.js:1644`、`:1866`、`:1184` | 示例必须匹配所选表单真实key和类型；无schema时标“技术变量示例”，不诱导填错字段 | schema/表单契约先行；示例不得自动提交，字段切换不覆盖已填草稿 |
| L-25 高 | 登录页直接展示admin等已知演示账号，placeholder为admin。`web/index.html:107`、`:112` | 示例账号仅演示环境显示；正式环境提示“输入用户名/口令”，不承诺这些账号可用 | 前后端共同确定环境安全标识；开发/演示提示不等于禁用认证。当前仅登记，未修改页面 |
| L-26 中 | 顶栏主线为“0→1启动”，帮助intro描述五阶段主线，八阶段治理口径另有定义。`web/index.html:81`、`web/js/help/catalog.js:64` | 主入口“开始使用”，辅助说明八阶段导航/项目五阶段分别用途 | 不删除历史业务类型或改主跳转；帮助与页面用同一概念边界，专业史料不做全文替换 |

## 3. 重点字段清单（对象限定，非全字段目录）

下表是后续完整字段盘点的首批样本。标准名为建议，类型、必填和校验以当前schema/服务为准；未列出的上限、条件、权限需从对应API补齐，不当作已完成契约。

| 编号 | 对象.字段 / 当前依据 | 建议界面名与含义 | 格式、空值及核对要求 |
|---|---|---|---|
| F-01 | Project.name，`app/schemas/project.py:73` | 项目名称；不叫流程名称 | schema max160，前端和API校验一致；实际必填/空串规则再核 |
| F-02 | Project.owner / owner_user_id，同文件`:82` | 项目负责人 / 负责人账号；前者展示，后者归属权限依据 | 未绑定不自动按同名人授权；现有按名绑定兼容须明确提示，不靠文案修改权限 |
| F-03 | ProcessArch.owner_user_id，`app/models/process.py` | 流程负责人账号；负责长期流程 | 与项目负责人可以不同，不建立两套Owner缓存；核当前组织/任命边界 |
| F-04 | Project.sponsor / department / org_unit_id，`app/schemas/project.py:88` | 项目发起人 / 所属部门说明 / 所属组织 | 文本部门不代替组织ID授权；发起人文本不证明授权已确认 |
| F-05 | Project.current_stage，同文件`:78`、`:143` | 项目阶段 | 改善项目1–5；当前Update schema允许到9且有治理体系项目，应核服务按project_type处理，不能直接改全局校验 |
| F-06 | Project.baseline_value / target_value / metric_unit，同文件`:95` | 基线值 / 目标值 / 指标单位 | 缺失不当0；项目卡值不是已冻结的正式验收样本 |
| F-07 | Project.observation_until，同文件`:112` | 观察截止日期 | 纯日期，不new Date解析；截止不自动证明观察通过 |
| F-08 | KpiDefinition.formula / numerator / denominator，`app/schemas/monitor.py:36`、`app/services/kpi.py:46` | 计算公式 / 分子 / 分母 | 当前规则为公式或同时提供分子分母；不是“全部必填”，描述公式不代表存在任意表达式执行器 |
| F-09 | KpiDefinition.unit / direction / frequency，`app/schemas/monitor.py:29` | 指标单位 / 改善方向 / 统计频率 | 单位不决定来源；字典code保留，按原meta展示；比例与百分数约定需补齐 |
| F-10 | KpiRecord.period / value，同文件`:95` | 统计期间 / 指标值 | period是日期字段，按指标频率说明锚点；value=0与无样本不同，不能只靠日期判断可比 |
| F-11 | ProcessTask.assignee_user_id，`app/schemas/execution.py:123` | 任务处理人 | null可能是公共队列；不显示成“无负责人”并误导为缺Owner |
| F-12 | Instance.definition_version，`app/schemas/execution.py:166` | 启动模型版本号 | 整数版本号不是ProcessModelVersion主键；详情保留process身份，历史未知不填最新版本 |
| F-13 | due_at / due_hours，`app/schemas/execution.py:85`、`:127` | 到期时间 / 任务时限（小时） | 时间戳本地显示；小时为时长，0/null语义核原服务，不统一替换为“天” |
| F-14 | ToolTemplate.format / DeliverableVersion.version_label，`app/models/tool_template.py:41`、`app/schemas/deliverable.py:150` | 模板格式 / 版本标识 | 模板语义版本与文件自由版本不是同一校验；不得因统一名强制所有版本major.minor.patch |
| F-15 | GovernanceFinding.type / severity，`app/models/governance.py:19` | 发现类型 / 严重程度 | 两个独立域，不以状态代严重程度；type已扩64，清单禁止据旧32上限生成校验 |
| F-16 | owner / owner_user_id / role各域 | 对象负责人 / 归属账号 / 角色 | 逐对象展开不能用一个全局“负责人”字段表自动覆盖；不同域条件分别登记 |

## 4. 固定字典与可配置字典来源

| 编号 | 域 / 现有来源 | 整治边界 |
|---|---|---|
| D-01 | methodology、project.status：`app/models/enums.py`、`app/api/v1/projects.py`、`app/services/dashboard.py`、`app/services/improvement.py` | 核全部输出消费后收敛同域标签；不全局合并名为STATUS_LABELS的不同字典 |
| D-02 | model.status/publish_policy：`app/services/process_model.py`；资产映射`app/services/deliverable.py` | 模型状态与发布策略不同；模型到资产状态是显式投影 |
| D-03 | instance/task/event：`app/services/execution.py` | 三域分开；事件“已改派”不等于任务终态，不把所有PENDING统一叫“待处理” |
| D-04 | deliverable.status/type/tool_level：`app/services/deliverable.py`；template.format/mode：`app/services/tool_template.py` | 文件、模板共享原审批规则；格式、调用方式、能力属性不是一个等级 |
| D-05 | kpi.status/intake：`app/services/kpi.py`，dimension/kind/frequency：`app/api/v1/monitor.py` | 状态/来源/维度/分类/频率分别登记；同为“PROCESS”不合并到流程目录 |
| D-06 | exception.status/severity：`app/models/enums.py`及monitor meta；governance.type/status/severity：`app/services/governance.py` | 业务异常与治理发现不同处置对象；严重程度即使同标签也先核支持范围 |
| D-07 | tool.category/status/difficulty/level：`app/api/v1/tools.py`、`app/services/tool_match.py` | 目录属性不同于方法有效性，旧DEPLOY code不改成引擎部署含义 |
| D-08 | knowledge.type/status/outcome：`app/services/knowledge_match.py` | 兼容旧值与当前CASE/TEMPLATE资源边界分开；kind+id才是混合推荐身份 |
| D-09 | 系统角色：`app/models/user.py`、`app/api/v1/auth.py`；治理角色类型/RACI：`app/services/raci.py` | 后端标签下发；业务任命不自动转系统权限；RACI字母解释固定但不能自动授API权 |
| D-10 | 可配置组织/岗位/治理角色：`app/api/v1/orgs.py`、`app/api/v1/positions.py`、`app/api/v1/raci.py` | 原CRUD保留；启停/继承/历史引用不迁到新通用字典库 |
| D-11 | 标准文件category/level/policy：`app/services/process_document.py` | 受控文件的级别、类别、变体策略是三域；不混入流程L1–L5或成熟度级别 |
| D-12 | 变更、授权、数据治理、工时、试点、复制包、补偿、集成、通知 | 分别从现有对应service/meta补全到code级；本版仅登记域，未逐值审定，不声称已全覆盖 |

## 5. 错误与示例的首批交付契约

以下标识是**拟定代码**，不是已存在API字段。实施应先选一个域兼容验证，不全仓一次更换错误包。

| 拟代码 / 场景 | 用户表达 | 参数/操作/安全边界 |
|---|---|---|
| `common.network_unavailable` | 暂时无法连接服务，请重试。 | 前端网络层；不拼内部异常，不自动重发写操作 |
| `common.validation_failed` | 请检查标记的字段。 | field_errors逐项定位，保留列表索引，不回显敏感input |
| `model.version_conflict` | 模型版本已更新，本次修改未保存。 | 提供已获授权的最新版本入口，保留草稿；仅真实版本冲突使用 |
| `task.already_processed` | 任务状态已变化，请刷新后查看。 | 当前任务权限核验；不能同时弹“已完成” |
| `common.record_unavailable` | 未找到该记录，或你无权查看。 | 不显示不可见对象名；沿原404策略 |
| `common.unknown_write_result` | 操作结果待确认，请先查看原记录。 | 只有存在可查原操作/记录时给具体入口；不能编造请求进度 |
| `example.execution_variables` | 示例：使用所选表单的字段编码填写变量。 | 依据真实schema生成/核验，JSON key/type合法，不自动写入 |
| `example.effect_evidence` | 示例：记录样本范围、观察窗口、前后值及证据来源。 | 示例结果不参与正式验收；字段不支持结构化证据时仍标能力缺口 |

## 6. 完整清单怎样补齐，不再产生第二个真相源

后续可做本地只读提取报告：枚举类及域内标签定义、schema字段、HTTPException/业务异常、页面标题/label/placeholder/toast/confirm、帮助/种子/模板、下载文件名及无障碍标签。输出必须包含相对路径、符号/行号、基线、原文、类别与使用场景。

1. 机器只定位候选，不能凭同名code或中文相似自动合并语义；动态模板参数、服务端拼接、第三方BPMN翻译分别处理。
2. 业务审定标准与例外，落实到原代码源；清单保存来源/差异/决定，不再人工复制所有运行时枚举值。
3. 验证列表、详情、meta、汇总、导出和帮助的实际结果；未定位到的消费点保留“待查”，不能宣称已消除重复。
4. 定位字符串不等于运行测试；报错触发、示例有效性、权限和单主题页面另做行为验收。

## 7. 执行顺序与验收状态

- 第一片：项目名称/负责人/状态/方法标签，清除同域重复来源；同时核页面标题能力，不改变状态流转。
- 第二片：公共错误解析及一个表单的字段错误，兼容原detail；覆盖断网、401/403/404、422、不同409原因、未知写结果。
- 第三片：页面表优先的资产与执行主题拆分，逐主题按需加载；文字随主题一起收敛，不先建立新业务库。
- 第四片：其余领域逐code/逐字段/逐示例完成清单，再加入持续检查。

本版没有实施以上切片。后端改动pytest，前端改动verify_frontend并确认当前代码服务，schema变更Alembic check；提交前scripts/check.py。全绿只证明相应测试，不能证明全部专业语义/示例/真实业务效果正确。
