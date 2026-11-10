# 流程经营绑定模型 · 开发计划

> 依据：[流程经营绑定模型](process-operating-binding-model.md)。本文只排期与定验收，不改主模型口径。
> 状态：计划稿（2026-11-09）。每阶段验收以**命令输出**为准，未跑过的步骤不得标记完成。
> 基线：`main` @ `57143f4`。

## 0. 总原则

1. **先只读，后写入。** P0 只加查询与展示，改不到任何现有写入路径，可独立回滚。
2. **先修断点，后做产物。** 岗位责任书排在 P2，因为 P1 不把 RACI 绑到活动，它只能是人工填表。
3. **一次一层 schema，一条 Alembic。** 每个阶段最多一次模型变更，随附 `alembic check`。
4. **每阶段一条独立分支 + 一个 PR。** 不合并多阶段到同一 PR。
5. **不引入第二套主数据。** 出现"两套各算各的"立即合并，不留兼容层。

## 1. 阶段与依赖

```text
P0 只读就绪度（设计器绑定页签 + 画布角标）
     │
     ├─→ P1 绑定数据模型（RACI 绑活动 / activity_resource_link / binding_snapshot）
     │        │
     │        ├─→ P2 岗位责任书 + 岗位覆盖度（第一个产物）
     │        │        │
     │        │        └─→ P3 员工手册 + 流程覆盖度矩阵
     │        │
     │        └─→ P2′ 就绪度升级为发布门禁（执行版 / 绩效版）
     │
     └─→ P4 目标类型（开源/节流）与经营视图
```

P4 与 P1–P3 无强依赖，可并行，但排在最后以免分散 P0 的注意力。

## 2. P0 · 只读绑定就绪度

**目标**：让缺口在设计器上可见，不改任何写入路径。

### 2026-11-09 实施与验收记录

- 基线 `1e273ec`，分支 `worktree-binding-p0`；细化执行与回归清单见 [P0 实施计划](superpowers/plans/2026-11-09-binding-p0.md)。
- 已增加只读 `GET /api/v1/processes/{process_id}/binding-readiness`，返回当前已保存设计模型身份、活动/节点四面来源与缺口、流程汇总；GET 不补建模型基线、不写审计/业务行。
- 原设计器增加顶层「绑定」及节点属性「绑定」，角标可进入对应节点；明细用折叠卡，标签与就绪结论由后端下发，不改原发布/执行/资产门禁。
- 当前 RACI 仍只有流程事项；P0 显示「未到活动」，不按事项名称猜活动唯一 A。TEAM 因此最多部分就绪，活动作用域与冻结留给 P1。
- 设计估计与已验证标准工时分开；本片保守采用「适用岗位的已验证标准 + 直接载体 + 必要规则」才判 RESOURCE 齐全。仅估计/默认表单标部分，不证明实际资源到位。
- 公司设计图沿原设计器可见性，岗位、标准工时、RACI 原角色及文件/证据来源仍单独核对原组织范围；跨流程错误映射标冲突，不输出外部活动名称。
- 初轮定向 API 15 项、与前端结构合计 71 项通过；独立复核后补来源作用域/节点证据/同流程重入回归，当前 P0 测试 21 项，与结构合计 `77 passed, 1 warning`。复核修复后完整 `check.py` 输出 `757 passed, 1 skipped, 4 warnings in 197.24s`，格式/静态检查/测试均通过、退出 0。独立 SQLite `alembic upgrade head` / `alembic check` 退出 0，输出 `No new upgrade operations detected.`；未新增 ORM/迁移。
- 浏览器专项已观察缺入口、离屏画布定位、属性保存后绑定版本滞后等 RED→GREEN；管理员/只读来源、实际红角标、节点面板、刷新、切流程与延迟响应离页通过。独立复核发现的兄弟设计节点同名文档误配、NODE 证据遗漏、同流程返回旧刷新覆盖已补 RED→GREEN；默认检查表遗漏按重要项处理，受限日志来源加保守负例。修复后以新 SQLite/端口核静态源码再运行专项通过；这不等于独立二次复核或真实业务核验。**全站未绿前不标 P0 完成交付**。
- 最终修复版全站 `verify_frontend.py` 已完整执行到底：退出 1、15 项失败，P0 项通过。与 `git archive 1e273ec` 独立副本、新 SQLite/独立端口的基线比对，失败名称集合完全相同，新增/消失均为空。此为仲裁前历史时点，不等于全站通过。
- 用户要求继续后逐项仲裁：校正折叠八阶段入口、项目列表→摘要→完整工作台、对标主题页签、默认登录断言时机与顶栏标题；业务结果断言保留。另实测修复两项产品回归：执行配置表格溢出被右栏遮挡、流程卡换壳丢分类与继承来源。两项均观察 RED→GREEN，M1/M2/M8 独立专项退出 0。最终以全新 SQLite/端口8143、静态源码核对后完整执行 `verify_frontend.py`：`全部检查通过。`、退出 0，原15失败全部消除；工程门禁 `757 passed, 1 skipped, 4 warnings in 151.60s`、退出 0。
- **P0 软件切片与本轮自动化验收完成。** 2026-11-10用户授权提交并本地合入main，不推送远端；提交前重跑完整门禁 `757 passed, 1 skipped, 4 warnings in 200.49s`、退出0，提交与合并身份以Git记录为准。保留边界：只读调色板因无评审中模型跳过；外部 diagrams.net 返回403，只验证 draw.io 消息协议；预期负例404/403/422/409/400及受保护实例清理409保留；不代表 PostgreSQL 生产并发、真实组织授权或业务效果验收。证据为本轮 `bjiui62e1.output`、`b3z7obcvp.output`，截图及原输出在隔离工作树 `.superpowers/sdd/2026-11-09-binding-p0/`。

仲裁口径（保留原结果断言，不跳过失败场景）：

| 类别 | 原失败 | 处理 |
| --- | --- | --- |
| 脚本入口过期 | 八阶段入口/承接、M8、项目详情/推进/甘特/去执行、驾驶舱项目入口、异常转改善 | 按当前可见入口展开/选中/打开完整工作台；仍验证原身份、产物、步骤写入与结果 |
| 脚本主题/时机过期 | 默认落地、对标切换、PCF引导、立项列表、地图/度量标题 | 默认断言移到登录后；显式切主题再查内容；顶栏与页内标题分别核对 |
| 产品回归 | 流程卡分类消失 | pageShell副标题恢复后端下发分类和继承来源，分类专项先红后绿 |
| 产品回归 | 执行分派按钮被遮挡 | 现有中栏加横向滚动约束；1440/1024宽度真实点击可到达，无force点击 |

### 交付

1. **服务**：`app/services/binding_readiness.py`（新）
   - `activity_bindings(db, process_id) -> ActivityBindingsOut`
   - `process_bindings(db, process_id) -> ProcessBindingSummaryOut`
   - 四个面的判定按主模型 §7.1；只读，无副作用。
2. **Schema**：`app/schemas/binding_readiness.py`（新）
   - `BindingFacetOut(key, label, status, source, refs, gaps)`
   - `ActivityBindingOut(activity_id, activity_code, activity_name, node_keys, facets, blockers)`
   - `ProcessBindingSummaryOut(process_id, overall, facets_ready, conflicts, counts)`
   - 状态标签（`READY` / `PARTIAL` / `MISSING` / `CONFLICT`）由后端下发中文。
3. **API**：挂到现有 `app/api/v1/asset_graph.py` 的 `router`（`prefix="/processes"`），避免新增前缀：
   - `GET /processes/{process_id}/binding-readiness`
   - 只读，`CurrentUser` 权限即可。
4. **前端**：
   - `web/js/views/designer/binding.js`（新）：只读页签，四分组明细 + 缺口清单，参考 `web/js/views/designer/raci.js` 的结构。
   - `web/js/views/designer/index.js`：抽屉页签加 `绑定`；`state.designer.binding`。
   - `web/js/views/designer/panels.js`：`NODE_PROP_SECTIONS` 增加 `{ id: 'binding', label: '绑定' }`；节点面板渲染该活动的四面包裹条。
   - `web/js/core/state.js`：`designer.binding` 字段。
   - 画布角标：在 `web/js/views/designer/canvas.js` 的 `mount` 与 `reload` 路径调用 `canvas.addMarker(nodeKey, 'pms-bind-red|pms-bind-yellow|pms-bind-green')`；样式加到 `web/css/views.css`。

### 沿用而非重写

- 不要新建"四路使能度"算法。`app/services/alignment.py:226` 的 `_enablers` 是目标级；P0 是活动级，**判定规则可以借鉴，代码不复用**。若发现规则重复，抽到 `app/services/binding_readiness.py` 供 alignment 调用，不允许两套阈值。
- 活动映射的权威判定沿用 `app/services/asset_graph.py:550`–`:558`（`REALIZES` / `PARTIAL` 关系优先，`process_arch_id` 为兼容指针）。

### 验收

```bash
pytest tests/test_binding_readiness.py -q        # 新增
pytest -q
alembic check                                    # 本阶段无迁移，应输出无漂移
uvicorn app.main:app --reload --port 8123
python scripts/verify_frontend.py http://127.0.0.1:8123
python scripts/check.py
```

浏览器人工验收（必须贴截图或控制台输出）：

- 选一条已发布 L3，打开设计器，`绑定` 页签显示四个面与缺口；
- 至少一个节点角标为红色，点击进对应页签；
- 只读账号看不到编辑入口，页签仍可看。

### 不做

- 不做任何写入；不改 `ProcessDocument` / `RaciAssignment`；
- 不做流程级四面包裹条以外的仪表盘；
- 不把绑定状态写进数据库（P1 才有快照）。

### 风险

| 风险 | 处理 |
| --- | --- |
| 就绪判定过严，几乎所有节点飘红 | 判定规则先以 `PARTIAL` 为主，红只给"四个面全空" |
| 角标与 bpmnlint 标记冲突 | 角标用独立 class 前缀 `pms-bind-`，不加进 lint 结果 |
| 大流程节点多，角标计算卡顿 | 就绪度由一次请求返回，前端只做一次批量 `addMarker` |

---

## 3. P1 · 绑定数据模型

**目标**：修断点 1/3/4——把 RACI 与资源绑到活动，并让绑定进入版本冻结。

### 2026-11-10 实施与验收记录

- 基线 `df508db`；独立分支 `worktree-binding-p1`，详见 [P1 细化计划](superpowers/plans/2026-11-10-binding-p1.md)。实施阶段保持隔离，未迁移正在使用的业务库；收尾按用户授权提交并本地合入 main，不推送远端，身份以 Git 记录为准。
- 原RACI增加活动/节点作用域；历史事项仍为 `MATTER:`，不按名称猜活动。原事项API兼容，按scope分组返回；MANAGER+写权限不放宽，流程锁与数据库部分唯一索引共同保护同scope唯一A。
- 活动原资源引用支持原表单/规则/标准文件/集成/技术/RPA及设备量具引用key，不复制源主数据；停用引用不删除原资源。跨流程、错误节点、失效或受限来源明确拒绝/待核，不把SOP当记录表单。
- 原发布/固定模型捕获绑定内容hash；后续原来源改变显示待确认，删除/失效显示STALE。已固定快照不被重复固定或发布覆盖；冻结依据变化须先建新工作版。此为保护原不可变依据，不是执行版/绩效版的完整性硬门禁。
- 设计器绑定页与节点属性增加原责任/资源维护，顶层权责同步scope；只读账号不获编辑；原冻结状态与来源一致性分开，不代表有权组织裁决或运行效果。
- 首轮完整 `check.py`：`774 passed, 1 skipped, 4 warnings in 227.82s`、格式/lint/测试通过、退出0；独立PostgreSQL全量同为 `774 passed, 1 skipped, 4 warnings in 298.88s`。首轮全站脚本退出0，P1及既有专项通过。独立SQLite、专用PostgreSQL迁移均 `No new upgrade operations detected.`；专用PG空库回退再升级通过；全量测试后的PG库重复scope/多A查询均0行，scope空值0。最终当前代码全站已退出0、P1及全部场景通过；日志保留Playwright路由取消回调 `CancelledError`（非页面JS异常）、条件调色板跳过及外部draw.io403限制，不称零错误。一次独立复核已完成：发现的发布快照被freeze覆盖、L4查询、NODE作用域责任串用、证据原来源漏指纹、受限备注泄露、意外失效硬门禁均补RED→GREEN；维护后背景未刷新经真实浏览器复现升级为重要项并修复。当前定向/结构97项及新增浏览器通过，修复后完整工程检查 `779 passed, 1 skipped, 4 warnings in 241.29s`、格式/lint/测试均通过；PG全量 `779 passed, 1 skipped, 4 warnings in 300.19s`，重复scope/多A均0行、空scope0；最终全站 `全部检查通过。`、退出0，P1及所有既有场景通过；最终服务无500、无页面JS异常，仍保留预期负例请求、受保护实例清理409和调色板条件跳过；draw.io只测协议，不证明外站成功。不冒称独立二次复核。
- **P1 软件切片与本轮自动化验收完成。** 用户授权提交后本地合入 main，不推送远端；提交前重新执行 `check.py`：`779 passed, 1 skipped, 4 warnings in 224.94s`，格式/lint/测试通过、退出0。单迁移 `g9b0c1d2e3f4` 尚未应用实际业务库；存在P1数据时降级明确拒绝，不能用删记录回退。专用测试服务/PG容器已停止，证据在隔离工作树 `.superpowers/sdd/2026-11-10-binding-p1/`（`check-reviewed.log`、`postgres-reviewed.log`、`frontend-reviewed.log`）。生产并发压力、组织授权充分性、资源真实到位和业务收益均未验收。

### 迁移（一条 Alembic）

```bash
alembic revision -m "bindings to activity and resource reference"
```

1. `raci_assignment` 加 `activity_id`、`node_key`、`scope_key`（见主模型 §6.1）；
   - 数据迁移：`UPDATE raci_assignment SET scope_key = 'MATTER:' || matter`；
   - `scope_key` 先可空 → 回填 → 加 `NOT NULL`；
   - 唯一约束 `uq_raci_process_matter_role` → `uq_raci_process_scope_role`；
   - 保留 `matter` 列（历史与流程级事项）。
2. 新表 `activity_resource_link`（见主模型 §6.2）；
3. `process_model_version` 加 `binding_snapshot` JSON（可空）。

**注意**：`alembic.ini` 保持纯 ASCII（CLAUDE.md 硬性约定 6）；迁移文件注释用英文或纯 ASCII 中文以外的写法——**迁移文件本身可以用中文，禁的是 `alembic.ini`**。

### 服务与 API

| 变更 | 文件 |
| --- | --- |
| RACI 支持作用域（`scope_key` 生成、唯一 A 校验按作用域） | `app/services/raci.py:235` 的 `upsert_raci`、`:200` 的 `process_raci` |
| 活动资源链接 CRUD + 引用校验 | `app/services/resource_link.py`（新） |
| 发布/冻结写 `binding_snapshot` | `app/services/process_model.py:461` 的 `publish`、`:169` 的 `freeze` 路径 |
| 绑定一致性（`CONFIRMED` / `PENDING_CONFIRM` / `STALE`） | `app/services/binding_readiness.py` 扩展 |
| 就绪度页签加"编辑"按钮 | `web/js/views/designer/binding.js` |
| 节点抽屉"班子"面可加 A/R/C/I | `web/js/views/designer/panels.js`、`designer/raci.js` |
| 节点抽屉"资源"面可挂表单/规则/文档/接口 | `web/js/views/designer/binding.js` |

### 验收

```bash
alembic upgrade head
alembic check
pytest tests/test_raci_scope.py tests/test_resource_link.py tests/test_binding_snapshot.py -q
pytest -q
python scripts/verify_frontend.py http://127.0.0.1:8123
python scripts/check.py
```

数据库层证据（必须贴输出）：

```sql
-- 同一活动同一角色不重复
SELECT process_id, scope_key, role_id, count(*) FROM raci_assignment
GROUP BY 1,2,3 HAVING count(*) > 1;   -- 应为空

-- 每个作用域最多一个 A
SELECT process_id, scope_key, count(*) FROM raci_assignment
WHERE raci = 'A' GROUP BY 1,2 HAVING count(*) > 1;   -- 应为空

-- 历史 matter 全部有 scope_key
SELECT count(*) FROM raci_assignment WHERE scope_key IS NULL;   -- 应为 0
```

人工验收：

- 在节点抽屉给一个活动加 `A`，权责页签同步出现该活动作用域行；
- 同一活动再加一个 `A` → 报错并指明冲突角色；
- 给活动挂一张表单 → 资产就绪度的载体检查变为通过；
- 发布模型 → `process_model_version.binding_snapshot` 非空；改一条绑定后，就绪度显示 `PENDING_CONFIRM`。

### 不做

- 不自动把历史 `matter` 猜成活动（决策点 5）；
- 不新建资源主数据表；`EQUIPMENT` / `MEASURE` 只存 `ref_key`；
- 不改 `ProcessDocument.process_id`（P3 才动）。

### 风险

| 风险 | 处理 |
| --- | --- |
| `scope_key` 回填期间并发写入 | 迁移内单事务完成三步；部署窗内停写 |
| 现有 `process_raci` 调用方按 `matter` 分组 | 保持 `matter` 输出字段不变，新增 `scope` 分组字段，前端渐进切换 |
| 资源引用悬空 | `ref_id` 非空时服务层强校验；删除源对象时靠 `ON DELETE` 或停用，不静默保留 |

---

## 4. P2 · 岗位责任书 + 岗位覆盖度

**目标**：第一个真正的经营产物；它会反过来压出所有没绑到活动的断点。

### 2026-11-10 岗位粒度与实施边界（用户确认）

- P2先把“这个岗位负责什么”做准：流程责任、岗位覆盖度与岗位责任书到岗位，不停在部门职能，不按个人或高级/基础能力等级复制岗位。
- 职级/能力等级在后续工作量表环节划分并实施，回答“需要什么能力、配置多少人”；不预设能力效率系数。主管/专员等实际职责授权不同的岗位仍明确区分。
- 细化实施见 [P2计划](superpowers/plans/2026-11-10-binding-p2.md)。本工作树已实现岗位覆盖度、责任书预览/生成/原版本评审与岗位页；尚未提交、合并、推送或迁移实际业务库。

### 2026-11-10 P2 实施与验收记录

- 隔离分支 `worktree-binding-p2`，基线 `307520a`；基线工程检查 `779 passed, 1 skipped, 4 warnings`。复核前双库803项通过是历史时点；修复后最终完整工程检查 `809 passed, 1 skipped, 4 warnings in 276.24s`，格式/lint/tests通过、退出0；专用新PostgreSQL库最终全量 `809 passed, 1 skipped, 4 warnings in 343.41s`，退出0。
- SQLite与专用PostgreSQL Alembic upgrade/check均输出 `No new upgrade operations detected.`；PG空库降一版再升级通过；新增回归验证历史PROCESS回填及已有岗位产物拒绝降级。实际PG另测输出 `PASS PG missing position rejected by CHECK`、`PASS PG downgrade refused with position document retained`，未依靠SQLite替代PG约束验证。
- 三合成岗位已沿真实页面走发布模型→岗位活动→责任书草稿→原评审/批准/生效→刷新，节点深链专项RED→GREEN。全站首轮执行到底退出1：P0原定位一项失败，其余含P2通过、无500；根因为加载时清空原内部待定位，已修复，独立P0专项退出0；修复后当前全站完整重跑 `全部检查通过。`、退出0、`SERVER_500: []`，P0/P1/P2及既有场景通过。1024宽度、换岗位清旧内容/刷新、真实迟到响应及viewer只读禁写补验退出0。复核修复后的最终全站同样完整退出0、无500；条件调色板跳过、预期负例及外部draw.io限制保留，不称零错误。
- 已完成一次独立整片复核：1项Critical（固定历史来源权限）与4项Important（发布职责被工作版删除后遗漏、任务内容未入hash、仅角色歧义遗漏、正文深链无效）均新增回归先RED后修GREEN；定向29项通过。正文链接改为应用绝对地址+原路由+basis，真实三岗位逐条点击回原节点通过，未作独立二次复核。条件调色板跳过、预期负例及外部draw.io限制保留，不称零错误。
- 曾遇测试断言把版本号1.0误匹配时间戳、结构清单未加新视图/设计器模块超限，均保留失败记录并改为精确版本标题/同步结构/定位逻辑归binding子模块。PG复用库因原drop_all循环依赖失败exit4，尚未进入断言；不删旧库，另用专用新库重跑通过。
- 用户随后授权提交、推送、合并；P2提交及远端集成身份以Git/PR实际记录为准。远端main尚缺P0/P1，按每阶段独立PR先承接依赖；发布这两个此前仅本地合入的阶段须明确公开目标授权。业务库仍不迁移。
- **P2软件切片与本轮自动化验收完成。** 证据保留 `.superpowers/sdd/2026-11-10-binding-p2/`（`check-final.log`、`postgres-final.log`、`frontend-reviewed.log`、`review-resolution.md`、截图）；测试服务已停止，自有专用PG容器已停止但保留数据。单迁移 `h0c1d2e3f4a5` 未应用实际业务库。生产并发、组织授权充分性、历史任职快照与真实业务效果未验收；职级/能力及人数配置仍留工作量表后续。

### 岗位覆盖度（只读，先做）

`app/services/position_coverage.py`（新）：

- 输入：`position_id`（可选时间窗）；
- 输出：参与流程、参与活动（直接绑定 + 角色反推）、RACI 分布、标准工时与频次、实际工时、负荷率、未归位角色；
- 角色无法归位到岗位时输出 `UNMAPPED_ROLE`，**不静默分摊**。

API：`GET /workload/position-coverage`（挂 `app/api/v1/workload.py`，与工作量同域）。

### 岗位责任书（编译 + 预览 + 落库）

1. **编译服务**：`app/services/job_description.py`（新）
   - `preview(db, position_id) -> JobDescriptionPreviewOut`：只读，返回结构化章节 + HTML + `content_hash` + 输入快照；
   - `compile(db, position_id, user)`：落库，复用文档版本状态机。
2. **产物容器**：按主模型 §6.6 的**方案 A**，扩 `ProcessDocument`：
   - `process_id` 改可空；加 `scope`（`PROCESS` / `POSITION` / `ROLE`）、`position_id`、`governance_role_id`；
   - 检查约束：`scope='PROCESS'` 时 `process_id` 非空；`scope='POSITION'` 时 `position_id` 非空；`scope='ROLE'` 时 `governance_role_id` 非空；
   - 逐处加作用域守卫：`app/api/v1/process_documents.py:120`–`:140`、`app/services/process_document.py:352`、`app/services/maturity.py:324`、`app/services/asset_package.py:594` 等。
3. **组件复用**：`CompiledAssetComponent` 加 `POSITION_REF` 之外的 `RACI_ACTIVITY`、`WORK_STANDARD`（主模型 §4.1 的输入项），仍只存引用与 hash。
4. **前端**：新视图 `web/js/views/responsibility.js` → `register('responsibility', renderResponsibility)`（`web/js/main.js`）→ 加进 `app/main.py:36` 的 `SPA_VIEWS` → 登记 `tests/test_frontend_structure.py:216` 的 `MIGRATED_PAGE_SHELL` → 侧栏 `web/index.html`。必须用 `pageShell`，首屏只放结论/阻断/下一步。

### 验收

```bash
alembic upgrade head
alembic check
pytest tests/test_position_coverage.py tests/test_job_description.py -q
pytest -q
python scripts/verify_frontend.py http://127.0.0.1:8123
python scripts/check.py
```

人工验收（**主模型 §9 决策点 1 的硬要求**）：

- 选 3 个岗位，各生成一份责任书草稿；
- 草稿中每一条活动都能点回设计器对应节点；
- 草稿里的 RACI 与工时与设计器、工作量页数字一致（同源）；
- 走完 `草稿 → 提交评审 → 生效`，生效后模板与哈希可查；
- 岗位覆盖度页对"角色未归位"给出显式提示。

### 不做

- 不做员工手册（P3）；
- 不做个人考核、不做薪酬；
- 不做批量导出全部岗位（先证明单岗位正确）。

### 风险

| 风险 | 处理 |
| --- | --- |
| 改 `ProcessDocument.process_id` 影响面大 | 迁移前先用 `pytest -q` 全绿基线；改完后逐处补作用域测试 |
| 岗位责任书变成人工填表 | 若某条活动缺绑定，产物里**留空并标缺口**，不提供手填入口 |
| 岗位覆盖度与工作量页数字不一致 | 两者都从 `workload.summary` 取标准工时，不各自算 |

---

## 5. P3 · 员工手册 + 流程覆盖度矩阵

### P3a 员工手册

- 编译服务 `app/services/handbook.py`（新）：岗位/治理角色 → 流程 → 活动 → SOP / 表单 / 规则 / 工具 / 控制点；
- 复用 P2 的产物容器（`scope='POSITION' | 'ROLE'`，`category='HANDBOOK'`）；
- 与责任书的区别写进产物模板：责任书答"负什么责、多少量"，手册答"具体怎么做"。

### P3b 流程覆盖度矩阵

1. `ProcessArch` 加 `is_key_process`、`key_basis`（主模型 §6.4）；`is_key_process=true` 时服务层要求 `key_basis` 非空。
2. 服务 `app/services/key_process_coverage.py`（新）：
   - 关键活动清单；
   - 每个关键活动被哪些流程/节点实现（`NodeActivityLink`，注意 `model_version_id` 为空的历史行）；
   - 未建模（`UnmodeledActivity`）、未覆盖（无任何实现）；
   - 多条流程同时实现同一活动 → 重复/交叉；
   - 同级边界评审状态（`SiblingBoundaryReview` / `SiblingBoundaryLine`）；
   - 缺口责任岗位。
3. 前端：并入 `web/js/views/map.js`（已有 `pageShell`），不新建视图。

### 验收

```bash
alembic upgrade head && alembic check
pytest tests/test_handbook.py tests/test_key_process_coverage.py -q
pytest -q && python scripts/check.py
python scripts/verify_frontend.py http://127.0.0.1:8123
```

人工验收：

- 覆盖度矩阵对"未覆盖关键活动"给出数量与清单，且能点回流程/活动；
- 人工构造一条重复实现（两个节点挂同一活动），矩阵能识别并列出两边；
- 未做同级边界评审的 L2 在矩阵里显示为"未评审"，不显示为"无重叠"。

### 不做

- 不用名称相似度或 PCF 类别自动判定关键过程；
- 不自动判定"重叠/断点"结论，只做可核对的证据列表。

---

## 6. P2′ · 绑定性门禁

### 2026-11-10 P2′ 实施与验收记录

- 隔离分支 `worktree-binding-p2-gates`，基线 `57bdde8`。细化步骤见 [P2′ 实施计划](superpowers/plans/2026-11-10-binding-p2-gates.md)。本片不包含实际业务库迁移或应用升级；集成身份以仓库提交与 PR 记录为准。
- `binding_readiness.binding_gate` 只投影原四面结论：执行版检查班子与资源，绩效版检查四面。模型发布保留原评审／变更单／固定依据约束，仅增加缺项告警；不因绑定完整度禁止设计发布。
- 原上线准备增加执行版阻断及绑定指纹，原适用性“不适用”不能豁免绑定必需项；原指定本人和修订号控制保留。绑定来源内容变化后原确认失效，必须重新固定依据再确认。
- 资产包专用与通用文档流转共用同一守卫；评审、批准、生效都重算，旧清单缺指纹须重新生成。退回草稿与退役保留。诊断产物沿原诊断约束，不套绩效版完整度。
- 岗位责任书预览分别返回可生成草稿、可提交评审；正式流转检查该岗位相关活动。角色未归位仍显式显示，无关流程缺口不阻断本岗位；无来源授权不放行。
- 编译产物不隐式反向纳入自身绑定来源；显式资源引用继续核对。原证据裁决与绑定 METHOD 冲突判定对齐，不另造一套裁决。
- 已观察 RED→GREEN：缺 A 设计发布仍成功但使用入口阻断、原来源变化失效、通用接口不能绕过、补齐后重新固定／编译、1024／1440 宽度、刷新与只读入口。专项 `verify_binding_gates.py` 输出 `PASS P2′ 缺A发布、双使用入口阻断、补齐重新固定、旧草稿拒用、来源失效、1440/1024与只读`，退出 0。本次截图已人工查看。
- SQLite 与本片专用 PostgreSQL 空库 `alembic upgrade head` / `alembic check` 均退出 0，输出 `No new upgrade operations detected.`；无 ORM 或迁移变更。原循环外键 SAWarning 保留。
- 复核前完整工程检查 `829 passed, 1 skipped, 4 warnings in 303.28s`，格式／静态／测试通过，退出 0。原 P2 三岗位责任书与 M6 本人确认浏览器专项各自新服务复验退出 0。门禁加前端结构定向 `76 passed, 1 warning`。
- 首轮完整前端执行到底退出 1（6 项后续场景失败，P0/P1/P2/P2′/M6 通过）；专用 PostgreSQL 首轮 `828 passed, 1 failed, 1 skipped`，失败为预览／编译来源指纹顺序不稳定。两者保留原日志，不以专项通过冒称全站通过。已用真实 SQLite 查询顺序扰动观察 RED→GREEN，固定无序来源读取顺序；已修专项视口和合成根流程排序污染，最终全站重跑通过。
- 已完成一次独立整片复核，5 类 Important 经本会话新增 8 项回归复现 RED 后修复：显式资源引用的原模型身份贯穿、角色成员变化失效、生成容器人工上传绕过、岗位无关活动／受限来源的范围裁剪、默认表单经资源链接冒充载体。核心与原回归 `120 passed, 1 warning`。另补无关受限来源只读权限回归通过。未进行独立二次复核。
- 复核修复后工程检查曾输出 `838 passed, 1 skipped, 4 warnings in 311.05s`、退出 0；专用 PostgreSQL 输出 `837 passed, 2 skipped, 4 warnings in 452.40s`、退出 0（第二项跳过仅 SQLite 查询顺序扰动）。后续又补相关节点跨流程映射冲突与只读受限来源回归，最终版双库完整结果见后文。
- 修复后的全站执行到底仅 P1 旧合成角色缺成员一项失败，原 6 项后续失败已消除；为 P1 夹具补自有可归位角色成员，不删除冻结一致性断言，独立专项退出 0；最终全站重跑通过。
- 最终后端源码完整工程检查 `840 passed, 1 skipped, 4 warnings in 328.78s`，格式／静态／测试全部通过、退出 0。结构、来源权限与范围等定向 `111 passed, 1 warning`；P1 补可归位成员后的独立浏览器专项退出 0。
- 最终专用 PostgreSQL 全量 `839 passed, 2 skipped, 4 warnings in 440.45s`，退出 0；跳过为原真实引擎隔离前置与 SQLite 专属查询顺序扰动。责任重复 scope/role、多 A、空 scope 核对均 `0`。最终双库 Alembic check 均无漂移；专用 PG 空库降一版再升级退出 0。来源版本链定向 `67 passed, 1 warning`。
- 最终当前工作树新服务全站 `verify_frontend.py` 完整执行到底，输出 `全部检查通过。`、退出 0，P0/P1/P2/P2′/M6 与既有场景通过，`SERVER_500: []`；无页面 JS 异常。预期负例 400/403/404/409/422 请求与对应控制台资源 error、受保护实例清理 409、无评审中模型时只读调色板条件跳过保留；外部 draw.io 仅验消息协议，不声称外站成功。
- **P2′ 软件切片与本轮自动化验收完成。** 证据在 `.superpowers/sdd/2026-11-10-binding-p2-gates/`。日常业务库与应用均未升级；生产并发、组织授权充分性、资源真实到位和业务效果未验证。P3、职级／能力与人数配置不在本片范围。

放在 P1 之后、P3 之前或并行。按主模型 §3.2 的三个发布点分别落地：

| 发布点 | 改动 | 档位 |
| --- | --- | --- |
| 模型发布 `publish_model`（`app/api/v1/designer.py:555`） | 不改阻断，只写快照 + 返回告警 | 无 |
| 执行上线确认（`ProcessExecutionConfig.readiness`） | 加执行版硬阻断 | `EXECUTION` |
| 资产包/产物评审（`app/services/asset_graph.py:694` 的 `can_submit_review`） | 硬阻断改为四绑定完整度 | `PERFORMANCE` |

**注意**：`can_submit_review` 现在是 `not blockers`；改成档位制后，原有 `MODEL_NOT_VERSIONED` 等阻断码语义不变，新增码沿用 `ReadinessBlockerOut` 三段式（code / message / targets）。

验收：

```bash
pytest tests/test_publish_gate_bindings.py -q
pytest -q && python scripts/check.py
```

人工验收：缺 RACI-A 的流程能发布模型（有告警），但不能提交资产包评审；补齐后可提交。

---

## 7. P4 · 目标类型与经营视图

1. `StrategyObjective` 加 `goal_type`（`GROWTH` / `COST`），后端下发 `goal_type_label`；
2. `alignment` 四路使能度按目标类型分组展示；
3. 前端不维护中文映射（CLAUDE.md 硬性约定 3）。

验收：

```bash
alembic upgrade head && alembic check
pytest tests/test_strategy_goal_type.py -q
pytest -q && python scripts/check.py
python scripts/verify_frontend.py http://127.0.0.1:8123
```

---

## 8. 贯穿要求

### 每阶段必须过的门

```bash
python scripts/check.py          # 格式 + 静态检查 + 测试
pytest                            # 默认临时 SQLite
alembic check                    # 有模型的阶段
python scripts/verify_frontend.py http://127.0.0.1:8123   # 有前端的阶段
```

三者任一没过，不算完成（CLAUDE.md「AI 协作纪律」6）。

### 新增前端视图的固定动作

1. `web/js/views/x.js` 导出 `renderX`；
2. `web/js/main.js` `register('x', renderX)`；
3. `app/main.py:36` 的 `SPA_VIEWS` 同步（`tests/test_frontend_structure.py:184` 会查）；
4. `tests/test_frontend_structure.py:148` 的视图清单同步；
5. `tests/test_frontend_structure.py:216` 的 `MIGRATED_PAGE_SHELL` 登记；
6. `web/index.html` 侧栏入口；
7. `scripts/verify_frontend.py` 的 `VIEWS` 清单同步。

### 枚举中文

`goal_type`、`resource_type`、绑定状态、就绪档位的中文标签一律后端下发，前端只渲染。

### 时间

新增时间字段一律 UTC 存储、出参补 `+00:00`；纯日期字段不用 `new Date()` 解析（CLAUDE.md 硬性约定 2）。

### 不留废弃代码

`matter` 保留是**兼容语义**（流程级事项仍然合法），不是废弃字段——但 `RaciAssignment` 上的旧唯一约束必须在同一迁移里删掉，不允许两套约束并存。

## 9. 排期与工作量

| 阶段 | 内容 | 迁移 | 预计 |
| --- | --- | --- | --- |
| P0 | 只读就绪度 + 设计器绑定页签 + 角标 | 无 | 中 |
| P1 | RACI 作用域 + 资源引用 + 绑定快照 | 1 条 | 中大 |
| P2 | 岗位覆盖度 + 岗位责任书 | 1 条 | 大 |
| P2′ | 三档发布门禁 | 无 | 小中 |
| P3 | 员工手册 + 覆盖度矩阵 | 1 条 | 大 |
| P4 | 目标类型与经营视图 | 1 条 | 小 |

先做 P0 的理由：它零风险、零迁移，且能把"四绑定"从理念变成界面上可数的缺口。在 P0 落地前做 P2，责任书只能是人工填表。

## 10. 回滚

- P0：纯只读，`git revert` 即回滚。
- P1–P4：每个迁移写 `downgrade`，回滚顺序为 `alembic downgrade -1` → 回退代码。
- `scope_key` 回填不可逆（丢了原 `matter` 也能重建），但删除旧唯一约束**不可逆恢复数据一致性**；回滚前先导出 `raci_assignment` 全表。
- `binding_snapshot` 可空，回滚只需忽略该列。
