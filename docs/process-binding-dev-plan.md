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
2. **产物容器**：按主模型 §6.5 的**方案 A**，扩 `ProcessDocument`：
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
