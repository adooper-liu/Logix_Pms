# 工具模板保存与效果申报分离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本轮用户结束评审循环，不派新文档评审代理；原生执行即可。提交/推送仍须用户当时授权。

**Goal:** 保存方法模板只产生原业务产物，不再在步骤上下文自动申报任何使用效果，且用真实浏览器请求验证。

**Architecture:** 保留原ToolSheet及显式ToolUsage接口，删除前端保存后的隐式二次usage请求。公共浏览器验证函数同时供独立隔离验证入口和现有verify_frontend使用，避免两套检查。后端行为不变，仅增加契约回归测试，无迁移。

**Tech Stack:** Python 3.12+、FastAPI、SQLAlchemy 2.0、pytest、Playwright sync API；原生ES模块、零构建。

**Spec:** [实施启动brief](../../implementation-next-brief.md) §2–§4；[语言规范](../../bpm-interface-content-standard.md) §2.6；原总体[开发计划](../../bpm-first-batch-dev-plan.md)切片5。代码核对基线bedba23；执行时核当前文件，不覆盖已存在的文档修订。

## Global Constraints

- 不引入构建工具，不新增前端枚举中文表，不在views之间新增互import。
- 保存普通/步骤/项目模板均不得自动POST `/tools/{code}/usage`，不以PARTIAL替代EFFECTIVE。
- 保留原process_id/project_id/step_no及合法目标生成；不改usage接口或已有权限。
- 不删除/改写历史usage，不新增round/验收/附件/幂等平台，不借此修改KPI算法。
- 后端改动跑pytest；前端改动跑scripts/verify_frontend.py；提交前python scripts/check.py。本单元没有schema改动，不新增迁移。
- 所有写入验证先用新建隔离目录/SQLite/服务，检查继承环境；不输出连接串/密钥，不连接现有库/后台旧进程。

## Review Focus

1. 有step且有project：保存原项目/步骤引用，不隐式usage——Task1真实交互断言。
2. 无step：原普通填写照常，不能为防自动效果阻止保存——Task1普通场景。
3. OGSM生成目标：目标/流程挂载保留，不被误删为“自动效果”——Task1生成目标场景和Task2既有pytest。
4. 保存返回400：保留输入与弹窗，没有成功反馈或usage——Task1浏览器响应拦截负例。
5. 显式申报：用户另开“用到当前步骤”并选择结果仍可写usage——Task1显式提交对照，避免删尽usage功能。

## 文件职责

| 文件 | 改动 |
|---|---|
| Create `scripts/verify_tool_sheet.py` | 共享真实浏览器回归函数；独立main只启动本次隔离应用服务，核版本/配置后验证；不执行模块级写库 |
| Modify `web/js/views/shared/tool_sheet.js` | 仅移除隐式usage与相应临时note，收敛保存成功反馈 |
| Modify `tests/test_tool_sheet.py` | sheets API在step/project场景保留产物且不生usage；保留OGSM/SWOT原测试 |
| Modify `scripts/verify_frontend.py` | 导入同一验证函数，增加check条目；不复制浏览器场景 |

## Task 1: 建立真实浏览器回归，先在旧代码看见失败

**Files:** Create `scripts/verify_tool_sheet.py`。

**Interfaces:**
- Consumes: 原POST `/auth/login`、GET `/process-map/flat`、POST `/projects`、GET `/tools/{code}/sheet-form`、GET `/tools/{code}/usage`、GET `/process-card/{id}`及现有UI动作。
- Produces: `verify_tool_sheet_save(page: Page, base: str) -> None`，成功返回None，失败抛AssertionError；不更改全局verify_frontend.failures。
- Produces: `main() -> int`，独立入口 `python scripts/verify_tool_sheet.py`；新隔离环境所有子进程使用 `sys.executable`，退出0只表示全部场景成功。

- [x] **Step 1: 实现隔离运行入口及共享检查函数，不改产品代码。**

独立main用TemporaryDirectory建新SQLite文件/attachments/screenshots，用socket分配空闲localhost端口后启动uvicorn子进程（若绑定失败明确退出）；固定本次cwd=仓库根目录，无reload/worker。子进程env显式设新DATABASE_URL、TEST_DATABASE_URL为空、ALLOW_DEV_SECRET=true、SEED_ON_STARTUP=true、AUTO_MIGRATE=true、ATTACHMENT_BACKEND=local、ATTACHMENT_DIR为临时路径、PREVIEW_CONVERTER=none。清理退出时只终止自己启动的进程并等待，不结束用户服务。

启动前在相同覆盖env下独立进程导入settings，仅assert有效URL等于新路径/SQLite，不打印秘密；轮询health需database=sqlite且database_ok=true，失败输出受控日志位置。用HTTP请求读取 `/static/js/views/shared/tool_sheet.js`，与当前工作区文件比较SHA256，确保不是旧进程。登录admin后才执行共享函数，finally关闭浏览器/本次进程。

- [x] **Step 2: 共享函数使用真实页面和真实API构造以下确定场景。**（显式UI偏差按执行裁定处理）

使用page.request带从该页面localStorage取得的 `psm_token`；找种子L3-032（不存在明确fail，不随机用其他流程）。创建名为 `自检用-tool-sheet-<uuid>` 的BPI项目，owner=流程管理科，process_id为该L3；记录返回id。每个场景分配唯一marker，比较usage_events的ID集合而不是有限列表长度；隔离新库每个工具事件必须少于200，否则fail不能误认为全量。

**正常保存参数表（逐场景网络计数清零）：**

| 场景 | 工具/页面上下文 | 核断言 |
|---|---|---|
| 普通填写 | SIPOC；无step/project | 1次sheets POST、0次usage POST；返回step_no/project_id为空 |
| 项目步骤填写（必备红例） | SIPOC；step=2.1；project为新项目 | 1次sheets POST、0次usage POST；响应与流程卡sheet保留process/project/step，usage ID集合与前值相同 |
| 目标生成 | OGSM；step=1.2；project为新项目 | direction=marker，baseline=14，target=5，unit=天，其余合法文本；objective_codes非空且原目标接口可查，0次usage POST |

普通场景直接 `go('toolbox', {params:{open:code, process:String(pid), step:''}, skipOrigin:true})`；项目步骤/目标场景先 `go('projects', {params:{project:String(projectId)}, skipOrigin:true})`，等待该页加载完成，再 `go('toolbox', {params:{open:code, process:String(pid), step:'2.1'}})`（OGSM用1.2）。核state.navTrail中原projects参数含真实projectId，sheetProjectId沿现有来源栈取得该值；不依赖toolbox URL保留project。点击可见的该code `data-act="toolbox.fillSheet"`。不得mock项目引用，也不顺手重写router。工具modal字段按真实sheet-form生成，choice选有效option，普通文本含marker。点击实际 `toolbox.submitSheet`，用 `expect_response`等待sheets 201，待弹窗关闭及networkidle，再核请求计数与usage记录。不得直接调用submit函数替代点击。

请求观察匹配method=POST且精确路径 `/api/v1/tools/{code}/usage`（URL解析去query）；观察从点击前持续到networkidle和保存后渲染完成，不只统计EFFECTIVE载荷。对原代码step场景应捕获真实usage POST，不能通过源码字符串搜索代替红例。

失败场景：在SIPOC模态填marker后，仅对该次sheets POST使用Playwright route.fulfill返回400 `{detail:'测试校验失败'}`（其余请求正常）。断言模态仍开、原输入保留、toast显示测试错误、无usage请求/记录；finally unroute。保存失败对响应做负例拦截可用，但成功回归禁止mock后端。

显式对照：解除所有拦截后，step工具详情的“用到当前步骤”进入现有 `toolbox.applyStep`，明确选择taOutcome=PARTIAL并填唯一note，点击 `toolbox.applyStepSubmit`。断言仅这次显式操作新增1个usage POST，服务器返回PARTIAL、step=2.1且note匹配；它是用户申报，不标正式独立核验。普通保存用例不得触发该动作。

共享函数完成后回到开始页/关闭自己的模态，保留page认证供全量脚本后续使用。独立环境可销毁；在全量脚本使用唯一项目/marker并在finally清理本次项目和生成目标（精确ID，不能批量删他人记录）。服务端无sheet/usage删除接口则明确让它们留在一次性临时库，不新增清理API或生产清理逻辑。

- [x] **Step 3: 运行红例。**

Run: `python scripts/verify_tool_sheet.py`
Expected: 旧代码在项目步骤场景FAIL，明确“保存不得POST usage，实际1次”或usage ID集合增加；先核失败确实来自该缺陷而非浏览器未安装、登录/模板缺失。若环境失败先解决环境，不宣称已得到红例。

## Task 2: 最小产品修复与服务契约回归

**Files:** Modify `web/js/views/shared/tool_sheet.js:77–114`、`tests/test_tool_sheet.py`。

**Interfaces:**
- Consumes: Task1 `verify_tool_sheet_save(page, base)`及现有POST sheets响应。
- Produces: 原 `submitToolSheet(code)` async签名不变；成功只调用原sheets API，失败沿原catch；显式submitToolApply保持原行为。

- [x] **Step 1: 新增 `test_step_sheet_preserves_context_without_usage(client)`。**

使用种子L3-032、新建process_id匹配的BPI项目，读取SIPOC表单填合法values；记录ToolUsage count或ID集合，再POST sheets携带该project_id及step_no=2.1。断言201、返回process/project/step一致、GET流程卡包含该sheet、ToolUsage ID集合未变。finally按精确ID删测试项目，沿现有测试清理方式。不要通过API测试伪称验证到前端第二请求：本用例旧代码也可能已通过，只保护服务契约，真正红例由Task1提供。

- [x] **Step 2: 最小修改 `submitToolSheet(code)`。**

完全移除 `if (state.toolbox.step)`内自动usage和只为它生成的note；不注释留废代码，不以PARTIAL或后台异步调用替代。原sheets payload、make_objectives及sheetProjectId保持。普通成功toast精确为 `方法记录已保存，已关联`＋原流程编码/名称；若objective_codes非空追加 `；已生成目标 `＋编码列表。不出现“已验证/有效/达标”。保留原失败toast、弹窗、刷新；不修改全局API层。

- [x] **Step 3: 验证绿色及现有行为。**

Run（完成下节隔离前置后）：`python -m pytest tests/test_tool_sheet.py -q`
Expected: 全部PASS，含OGSM写目标、SWOT keep、普通挂载、step/project新用例。

Run: `python scripts/verify_tool_sheet.py`
Expected: 普通/步骤项目/目标生成/失败/显式usage场景全部PASS，真实POST计数与数据库记录一致。若红例不转绿不能继续。

## Task 3: 接入项目验证入口并交付证据

**Files:** Modify `scripts/verify_frontend.py`；不新增视图注册。

**Interfaces:**
- Consumes: Task1 `verify_tool_sheet_save(page, base) -> None`。
- Produces: verify_frontend现有 `check(name, fn)`登记 `check('工具模板保存不自动申报效果', lambda: verify_tool_sheet_save(page, base))`，复用同一函数，无复制测试正文。

- [x] **Step 1: 接入导入与调用。**

按现有直接执行脚本import方式，从同目录 `verify_tool_sheet`导入公共函数；不要在import时启动子进程/浏览器。登记在工具箱/步骤上下文相关检查附近，失败纳入原failures列表和最终非零退出，不因该单项失败吞掉其他验证结果。

- [ ] **Step 2: 在核定的新隔离环境运行完整门禁。**

pytest/check子进程必须显式 `TEST_DATABASE_URL=''`，且 `DATABASE_URL`覆盖为新临时SQLite地址，attachments也设临时目录；先核settings再测试，不读取/打印用户.env。Bash示意：`TEST_DATABASE_URL='' DATABASE_URL="sqlite:///<本次新建绝对路径>/test.db" python -m pytest`；测试conftest随后使用自身临时库，禁止继承现有Postgres URL。

`verify_frontend.py`另起本次专属临时SQLite的uvicorn服务（使用Task1同样隔离与版本核验规则，无worker），按新端口运行：

```text
python scripts/verify_tool_sheet.py
python -m pytest
python scripts/verify_frontend.py http://127.0.0.1:<新端口> <本次临时截图目录>
python scripts/check.py
```

Expected: 每个命令退出0；check.py格式/lint/全量测试全部通过；verify_frontend日志包含新检查PASS且无失败。若全量脚本因其他既有问题失败，逐条报告并修复或明确阻塞，不跳过/放宽断言后宣称完整通过。无schema改动不运行生产Alembic，也不修改alembic.ini。

- [ ] **Step 3: 更新实施证据，而不是原评审结论。**

在实施启动brief记录新代码commit/工作区diff、红例和绿例命令输出、实际测试数/退出码、未验证项；先前“未实施”状态只有在实际运行后才更新。不重新写原独立评审报告，不将此单元完成当作KPI或round完成。

- [ ] **Step 4: 提交（仅用户当时授权后）。**

执行前git status确认本单元4个代码/测试文件及当前brief的证据变更；不 `git add -A`混入现有大量文档修订。提交前完整check.py通过，不amend、不force、不跳hook；推送/合并另按用户指示。建议提交名：`fix: 保存工具模板不再自动申报效果`。

## 执行裁定（与实际代码对应，非追加产品范围）

- 在现有checkout的新分支fix/tool-sheet-save-integrity执行，保留未提交文档；未创建worktree、未提交。隔离采用新临时SQLite/附件/端口及当前静态文件hash。
- 原计划误称toolbox.applyStep有可见按钮；当前仅有handler，推荐也过滤tool-kind。故不新增按钮，改用真实usage API做显式PARTIAL对照，并明确没有该UI验收。
- 共享检查重复执行的红例暴露两项测试夹具问题：空step被URL省略后界面态残留；显式usage十分钟去重不看note，SQLite删除项目后ID还可能复用。测试入口清理旧step，显式API使用本轮project与唯一8字符step；实际保存仍核真实2.1/1.2。未修改产品路由或API规则。
- Windows进程退出后临时SQLite偶有文件锁，TemporaryDirectory仅忽略清理错误以保留原测试异常；可能残留本次临时目录，不杀用户进程。
- 全站前端自检首轮600秒超时，第二轮按3600秒执行；已见多个非本单元交互失败。未宣称全站通过，全部失败会保留，不因本修复专项绿而跳过门禁。

## 计划自检与后续边界

- Review Focus五项均由Task1真实浏览器场景覆盖；Task2保留API/目标生成契约。
- 不把Task2旧代码可通过的API测试伪装成缺陷红例；红例只认真实step场景多发usage。
- Task1/3共用函数签名一致；独立runner负责隔离，全量脚本调用函数不得启动/重置其服务。
- 本单元不含KPI来源迁移、S1标签/治理类型、S2错误包、十层适用性、round/四结论。它们在brief队列中保留，分别形成下一独立计划。
- 本文件完成是“计划已写”，不是功能修复、测试通过、历史数据治理或评审仲裁完成。
