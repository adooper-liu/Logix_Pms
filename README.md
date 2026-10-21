# Logix PMS · 流程管理系统

把 **BPR / BPI / 精益** 三大方法论整合成一套可落地的标准工作流，覆盖「识别问题 → 诊断 → 设计 → 落地 → 运营」的全生命周期。

这是后端服务（第一阶段交付物）：数据库模型 + REST API + 内容底稿。前端原型见 `index-sample.html`。

---

## 三层体系 × 五阶段标准工作流

```text
┌─────────────────────────────────────────────────────────────────┐
│  战略层：流程规划与治理（What & Why）                              │
│  ├── 流程架构设计（L1–L4 分层）                                   │
│  ├── 流程 Owner 机制                                              │
│  └── 流程 KPI 体系（效率/质量/成本/灵活性）                        │
├─────────────────────────────────────────────────────────────────┤
│  执行层：五阶段标准工作流（How）—— 共 24 个步骤                    │
│  ├── 阶段1 识别与优先级排序（4 步）                                │
│  ├── 阶段2 诊断与根因分析（4 步）                                  │
│  ├── 阶段3 方案设计与选择（5 步）                                  │
│  ├── 阶段4 试点与推广落地（6 步）                                  │
│  └── 阶段5 运营监控与持续改进（5 步）                              │
├─────────────────────────────────────────────────────────────────┤
│  支撑层：工具箱 & 能力底座（With What）—— 共 33 个工具             │
│  ├── 诊断 9 / 设计 9 / 落地 7 / 监控 8                            │
│  └── 流程设计器 · 知识库                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 平台定位与优势

- **三大方法论整合**：BPR / BPI / 精益不是三个孤立工具，而是同一套五阶段工作流里的可选路径；
  立项向导按现状、目标、范围、组织与数据条件自动推荐方法。
- **架构到项目一条主线**：L1–L4 流程架构、Owner、项目组合、24 步标准工作流、甘特图与
  里程碑在同一套数据模型里关联，不再维护多套台账。
- **可解释的量化测算**：按流转概率求期望周期，计入分支、回路和返工；成本与时间同口径；
  模型不可信时明确标记，不拿假数字冒充结论。
- **诊断直连工具**：9 类结构性建议 + 33 个方法论工具，从「发现问题」到「下一步做什么」。
- **一套架构、多套对标**：公司流程架构保持唯一，交叉映射 SCOR 与 APQC PCF，切换只换参照系。
- **运营闭环与治理**：KPI 雷达/趋势、异常闭环、知识沉淀、审计留痕、`owner_user_id` 归属校验。
- **工程可维护**：零构建前端、主题令牌、API 优先、Alembic 迁移、SQLite/PostgreSQL 双后端 CI。

行业标准、最佳实践与平台能力的逐条对照见
[docs/process-management-best-practices.md](docs/process-management-best-practices.md)。

---

## 快速开始

### 1. 启动 PostgreSQL（Docker）

```bash
docker compose up -d db
```

镜像 `postgres:16`，数据落在命名卷 `pgdata` 里，`docker compose down` 不会丢数据
（要清空加 `-v`）。

**宿主机端口是 5433，不是 5432**——本机 5432 常已被单独安装的 PostgreSQL 占用，
两者会同时监听、`localhost` 优先命中本地那个，导致「密码明明对却认证失败」。
需要换端口时：

```bash
POSTGRES_PORT=55432 docker compose up -d db
# 并同步修改 DATABASE_URL 里的端口
```

### 2. 启动应用

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8123
```

首次启动会自动建表并灌入种子数据。

> Windows 上如果 `--port 8000` 报 `WinError 10013`，是 8000 落在系统保留的 TCP 端口区间里
> （Hyper-V / WSL 常见），换端口即可。用 `netsh interface ipv4 show excludedportrange protocol=tcp`
> 查看被排除的区间。

### 或者：整栈容器化

```bash
docker compose --profile full up -d --build
```

应用与数据库都在容器里。`api` 会等 `db` 健康检查通过再启动，启动时自动执行
`alembic upgrade head`，宿主机访问 8123 即可。

首次构建要拉基础镜像 `python:3.12-slim`，网络不好时会等一会儿；之后有层缓存就很快。

> ⚠️ **端口优先级坑**：容器把 8123 发布到 `0.0.0.0`，而本地 `uvicorn` 默认绑 `127.0.0.1:8123`。
> 两者同时存在时，`localhost` 会命中本地的 uvicorn，容器的请求根本进不来（排查时看
> `docker logs logix-pms-api` 有没有你自己的请求就知道了）。用整栈模式时先停掉本地 uvicorn，
> 或者临时 `docker compose stop api` 只保留数据库容器。

只想要数据库时：

```bash
docker compose up -d db          # 只起 PostgreSQL
docker compose stop api          # 停掉应用容器，回到本地 uvicorn 开发
```

### 不想用 Docker？

```bash
DATABASE_URL=sqlite:///./logix_pms.db uvicorn app.main:app --port 8123
```

代码里没有 PostgreSQL 专有写法，退回单文件 SQLite 也能跑（测试默认就用 SQLite）。

| 地址 | 内容 |
|---|---|
| <http://127.0.0.1:8123/> | 前端应用（已接后端 API，需登录） |
| <http://127.0.0.1:8123/docs> | 交互式 API 文档 |
| <http://127.0.0.1:8123/sample> | 最初那份纯静态原型，保留作为设计对照 |
| <http://127.0.0.1:8123/health> | 健康检查（无需登录），会返回当前数据库类型 |

**演示账号**（首次登录后请立即改口令）：

| 账号 | 口令 | 角色 | 能做什么 |
|---|---|---|---|
| `admin` | `admin123` | ADMIN | 全部权限，含用户管理与审计日志 |
| `manager` | `manager123` | MANAGER | 全部业务写权限，可看审计日志，不能管用户 |
| `chen` | `chen123` | OWNER | 只能改自己名下（`陈经理`）的项目与流程模型 |
| `viewer` | `viewer123` | VIEWER | 只读 |

种子数据：8 个流程项目、148 个流程节点（L1–L4 全展开）、2 个流程实例、4 个运行时任务、2 个表单定义、1 条分支规则、33 个工具、24 个标准步骤、
15 个 KPI × 6 个月时序、8 条异常事件、9 篇知识条目、4 个演示用户、
2 套对标框架（71 个标准分类、249 条流程映射）。

手动重灌：

```bash
python -m scripts.seed            # 库为空时才灌，非空会提示并跳过
python -m scripts.seed --reset    # 清空重灌
python -m scripts.seed --benchmarks          # 只补灌 SCOR / APQC 对标数据
python -m scripts.seed --benchmarks --reset  # 只重建对标数据，不动业务数据
```

跑测试：

```bash
pytest -v                                              # 默认临时 SQLite，无需 Docker
TEST_DATABASE_URL="postgresql+psycopg://psm:psm_dev_password@localhost:5433/logix_pms_test" \
  pytest -v                                            # 对 PostgreSQL 跑（会先 drop 全部表）
```

前端联调自检（无头浏览器跑两段：9 个视图渲染 + 全量交互路径，收集 JS 报错与失败请求，并截图）：

```bash
uvicorn app.main:app --port 8123      # 另开一个终端
python scripts/verify_frontend.py http://127.0.0.1:8123 _screenshots
```

交互段覆盖：登录、地图下钻、对标框架切换、主题切换、工作流步骤详情、方法论匹配引擎、
项目详情四页签与步骤改状态、立项向导（真实入库后自动清理）、工具箱详情与按问题找工具、
设计器改节点并重算、异常处理弹窗、知识库详情、甘特图与里程碑、新建流程、登记异常、退出登录。

---

## 配置

优先级：环境变量 > 项目根目录 `.env` > 默认值。项目内置了一个极简的 `.env` 加载器
（不引入 python-dotenv）。见 `.env.example`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://psm:psm_dev_password@localhost:5433/logix_pms` | 指向 Docker 里的 PostgreSQL |
| `POSTGRES_PORT` | `5433` | docker compose 的宿主机端口，改的话要同步改 `DATABASE_URL` |
| `SECRET_KEY` | 开发用默认值 | **生产必须替换**，`/auth/security-check` 会提示 |
| `TOKEN_TTL_SECONDS` | `43200`（12 小时） | 令牌有效期 |
| `SEED_ON_STARTUP` | `true` | 启动时库为空则自动灌种子数据 |
| `CORS_ORIGINS` | `*` | 逗号分隔；生产请收紧 |
| `SQL_ECHO` | `false` | 打印 SQL |
| `AUTO_MIGRATE` | `true` | 启动时执行 `alembic upgrade head`；设为 `false` 则直接 `create_all`（测试用） |
| `TEST_DATABASE_URL` | 空 | 设了就让 pytest 针对该库跑 |

---

## 数据库迁移

schema 演进走 Alembic，**不再依赖 `create_all`**。应用启动时会自动 `upgrade head`，
已是最新版本时是空操作。

```bash
# 改了模型之后生成迁移
alembic revision --autogenerate -m "add xxx field"

# 检查模型与迁移是否一致（有未生成的改动会报错退出）
alembic check

# 手动升降级
alembic upgrade head
alembic downgrade -1
```

`alembic.ini` 里**不写数据库地址**，由 `alembic/env.py` 从 `app.core.config.settings` 读取，
避免 `.env` 和 `alembic.ini` 两处配置各自漂移。

> 注意：`alembic.ini` 必须保持**纯 ASCII**。configparser 在 Windows 下按系统 locale
> （中文机器是 GBK）读取该文件，写中文注释会直接抛 `UnicodeDecodeError`。

迁移链的正确性由 [tests/test_migrations.py](tests/test_migrations.py) 守着，核心断言只有一条：
**迁移建出来的 schema 必须和 ORM 模型完全一致**。在此基础上还验证了幂等升级、`downgrade base`
能干净回退、以及 `current_revision` 助手。

多副本部署时建议把 `AUTO_MIGRATE` 设为 `false`，在发布流程里单独跑一次 `alembic upgrade head`，
避免多个实例同时执行迁移。

---

## 目录结构

```text
app/
  core/         配置与数据库引擎、会话
  models/       SQLAlchemy ORM（流程域 / 项目域 / 工具 / 监控 / 知识库）
  schemas/      Pydantic 出入参契约
  services/     业务逻辑
    execution.py    流程执行：实例、任务队列、分支推进
    methodology.py  立项向导：BPR / BPI / 精益 / 混合 自动匹配
    designer.py     流程设计器：周期效率测算 + 9 条改善建议规则
    workflow.py     标准工作流的项目实例化与进度回算
    tool_finder.py  「按问题找工具」语义匹配
    dashboard.py    驾驶舱聚合
    benchmark.py    对标框架：分类树、覆盖率、流程映射
  api/v1/       REST 路由
  seed/         内容底稿与灌库逻辑
web/            前端（原生 ES 模块，无构建步骤）
  index.html    页面骨架
  css/
    base.css        设计令牌（多主题）、页面骨架、登录页
    components.css  卡片/表格/标签/按钮/表单/模态框/反馈等通用组件
    views.css       仅单个视图使用的样式（流程画布、泳道、甘特图…）
  js/
    core/
      api.js        请求封装、鉴权头、错误类型
      auth.js       身份状态、登录界面、用户信息
      format.js     格式化与配色（纯函数）
      router.js     视图注册表、页面切换、搜索派发
      state.js      全局界面状态
      theme.js      主题注册、切换与 Canvas 取色
      ui.js         模态框、提示条、视图容器
    views/
      dashboard.js  map.js  workflow.js  projects.js
      toolbox.js    designer.js  monitor.js  knowledge.js  execution.js
    main.js       注册视图、接线 DOM、暴露模板所需函数、启动
scripts/
  seed.py             命令行灌库
  verify_frontend.py  无头浏览器联调自检（9 个视图 + 交互路径 + 主题切换 + 截图）
tests/          接口测试、迁移一致性测试、前端模块结构守卫
docs/           行业对标、信息架构、指标口径与可视化选型
alembic/        数据库迁移脚本（env.py + versions/）
alembic.ini     迁移配置（不含数据库地址，纯 ASCII）
docker-compose.yml  PostgreSQL（可选整栈）+ 应用容器
Dockerfile          应用镜像
index-sample.html  最初的纯静态原型，保留作为设计对照（挂在 /sample）
```

---

## 前端

原生 ES 模块，无构建步骤、无框架依赖。`web/index.html` 由 FastAPI 直接托管，
浏览器按 `<script type="module">` 原生加载。

**分层**（依赖单向，无循环）：

```text
main.js
  └─ views/*        九个视图，各自 import 需要的 core
       └─ core/router.js    注册表 + 页面切换（不 import 任何视图）
            └─ core/{api, auth, state, theme, ui, format}.js
```

`core/router.js` 刻意不 import 视图，视图由 `main.js` 注册 ——
否则 router → views → auth → router 会绕成环。`api.js` 的 401 处理也是通过
`setUnauthorizedHandler()` 回调注入，避免 api ↔ auth 互相依赖。

**为什么 `main.js` 往 `window` 上挂函数**：模板里的 `onclick="openProject(3)"`
在全局作用域求值，模块作用域隔离，不挂 window 就点不动。这段挂载是**唯一**的对外操作面，
集中在一个 `Object.assign(window, …)` 里；将来改成事件委托时，删掉它即可，不用动各视图模块。

**视觉壳与多主题**：所有颜色、圆角、阴影、间距都定义为 `base.css` 里 `:root` 的语义令牌，
组件和视图只允许用 `var(--token)`，不允许写死 hex。顶栏的「主题」下拉由 `core/theme.js`
的 `THEMES` 注册表生成，选择后写入 `data-theme` 并持久化到 localStorage。

新增一套主题只需要两步：

1. 在 `base.css` 里加一组 `[data-theme="xxx"]` 的变量覆盖（参考 `slate`）；
2. 在 `theme.js` 的 `THEMES` 里登记 `{ code, name }`。

`tests/test_frontend_structure.py` 会检查 `components.css` / `views.css` 里没有硬编码颜色，
防止主题壳被后续改动绕过。Canvas 图表通过 `cssVar()` 读取当前主题色。

**信息层级**：每个页面统一为「页头（标题/说明/主操作 + 分段控件）→ 关键指标 → 内容区」。
监控、工作流、设计器使用页内页签拆分高密度内容（概览 / KPI / 异常台账；阶段步骤 / 方法论匹配；
流程模型 / 指标与建议），仪表盘只保留 4 个主指标并把风险提醒放在首屏右侧。
驾驶舱的主指标卡、阶段行、方法论图例、风险提醒和项目行都是入口：点击后会跳到对应页面，
并自动带上状态、阶段或方法论筛选。逐页的元素关系与可视化选型见
[docs/ui-information-architecture.md](docs/ui-information-architecture.md)；
所有指标的公式、阈值与边界见 [docs/metrics.md](docs/metrics.md)，
页面上带 `?` 的指标可以直接悬停查看简版口径。

**为什么不引入 Vue**：当前是刻意维持的零构建前端，页面数量与交互复杂度仍在原生模块可维护的范围内。
这一轮的痛点（信息密度、主题不统一）不是框架能力问题，引入 Vue 会带来全量重写、构建链、
CI/Docker 改动，收益主要是开发体验。等出现复杂客户端状态、多人并行开发或移动端需求时，
再评估 Vue 3 + Vite；届时 `base.css` 的设计令牌与页面结构可以原样复用。

**数据来源**：全部走 `/api/v1/*`，前端不含任何演示数据。枚举的中文标签
（`methodology_label` / `status_label` / `stage_name` / `heat_level`）由后端下发，
前端不维护映射表，避免「后端加了新枚举、前端忘了同步」。

**测试守卫**：[tests/test_frontend_structure.py](tests/test_frontend_structure.py) 会在
pytest 里检查 import 路径是否存在、九个视图是否都注册且有 renderer、样式表是否被引用，
把「模块路径写错只会在浏览器里静默 404」这类问题提前到测试阶段。

**九个模块与对应接口**：

| 视图 | 主要接口 | 能做什么 |
|---|---|---|
| 管理驾驶舱 | `/dashboard/overview` | 指标卡、五阶段健康度、方法论分布、项目看板、健康度预警、异常概览 |
| 企业流程地图 | `/process-map/tree`、`/heatmap`、`/benchmark/frameworks/{code}/coverage` | L1→L4 逐级下钻、改善优先级热力图、SCOR / APQC 对标切换与覆盖率、点热力图行可跳转定位 |
| 五阶段标准工作流 | `/workflow/stages` | 24 个步骤卡片 + 点击查看方法/工具/交付物/关键要点 + 方法论匹配实时试算 |
| 流程项目组合 | `/projects`、`/projects/{id}` | 多维筛选、详情五页签（概览/KPI/工作流/甘特图/下一步）、步骤状态可变 |
| 流程执行 | `/execution/*` | 启动实例、任务队列、认领/完成/改派、分支选择、实例时间线 |
| 方法论工具箱 | `/tools/grouped`、`/tools/match` | 33 个工具卡片 + 「按问题找工具」自然语言匹配 |
| 流程设计器 | `/processes/{id}/design` | 泳道建模、节点增删改、改动即时保存并重算指标与建议 |
| 运营监控与KPI | `/monitor/kpi-radar`、`/exceptions` | 四维度雷达、KPI 明细 + 6 个月走势、异常闭环处理 |
| 流程知识库 | `/knowledge`、`/knowledge/meta/tags` | 类型/标签/关键词筛选、热度排序、阅读详情、按问题找工具 |

**两处值得说明的取舍**：

- 设计器的指标条只给「有明确目标或天然 0–100% 区间」的指标画进度条（PCE、等待占比、
  作业时间占比、返工占比）。端到端周期、成本、移交次数这些没有目标值，
  画条只能是编出来的百分比，所以只显示数字。
- 流程地图的热度分档由后端判定并下发（阈值见 `app/api/v1/process_map.py`）。
  综合得分区间是 0–125，阈值必须按这个量级标定——早期用 ≥50 判「紧急」，
  结果 28 条 L3 流程里 10 条全被标成紧急，热力图完全失去区分度。


---

## 数据模型

| 表 | 说明 |
|---|---|
| `process_arch` | 流程架构 L1–L4，含价值-痛点三维打分（战略重要性 × 痛点 × 改善空间） |
| `process_node` / `process_edge` | 流程设计器的泳道节点与连线，节点带作业时间、等待时间、返工率、审批层级 |
| `process_instance` / `process_task` | 运行时实例与任务队列；实例启动时快照流程模型 |
| `form_definition` / `process_rule` | 节点表单定义与分支规则；随实例快照冻结 |
| `project` / `project_step` | 流程项目与它的 24 个步骤实例 |
| `workflow_template` | 五阶段标准工作流（全公司共用的操作手册） |
| `tool` | 方法论工具箱，每个工具含 5 步标准操作 |
| `kpi_definition` / `kpi_record` | KPI 定义与月度时序 |
| `exception_event` | 异常事件闭环台账 |
| `knowledge_item` | 案例 / 模板 / 最佳实践 / 标准 |
| `benchmark_framework` / `benchmark_category` | 对标框架（SCOR / APQC PCF）的 L1–L5 标准分类树 |
| `process_benchmark_map` | 公司流程 → 标准分类的多对多映射 |

---

## API 一览

所有接口前缀 `/api/v1`。

### 管理驾驶舱
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/dashboard/overview` | 首页一次拉齐：指标卡、五阶段健康度、方法论分布、项目看板、健康度预警、异常概览 |

### 企业流程地图
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/process-map/tree` | L1→L4 架构树，支持 `root_code` / `max_level` / `improvement_only` |
| GET | `/process-map/flat` | 扁平清单，支持 `level` / `keyword` |
| GET | `/process-map/heatmap` | 改善优先级热力图（CRITICAL / HIGH / MEDIUM / LOW） |
| GET/POST/PATCH/DELETE | `/process-map[/{id}]` | 流程节点 CRUD |

### 对标框架
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/benchmark/frameworks` | 框架清单（SCOR / APQC PCF），含分类数与已映射流程数 |
| GET | `/benchmark/frameworks/{code}/tree` | 标准分类树，`max_level=1–5` |
| GET | `/benchmark/frameworks/{code}/coverage` | 公司某层流程的覆盖率与缺口，`process_level=1–4` |
| GET | `/benchmark/processes/{id}/mappings` | 单个流程在所有框架下的映射 |
| POST | `/benchmark/mappings` | 新增流程 → 标准分类映射（MANAGER+） |
| DELETE | `/benchmark/mappings/{id}` | 删除映射（MANAGER+） |

### 标准工作流
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/workflow/stages` | 五阶段 × 24 步骤，含工具、交付物、关键要点 |
| GET | `/workflow/stages/{stage_no}` | 单阶段 |

### 流程项目组合
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects` | 多维筛选：methodology / status / stage / priority / owner / keyword，分页 |
| POST | `/projects` | 新建项目，自动生成绩效编码并按模板生成 24 个步骤 |
| GET | `/projects/{id}` | 项目详情：五阶段进度、当前待办、下一步建议、KPI 趋势 |
| PATCH | `/projects/{id}` | 更新项目 |
| GET | `/projects/{id}/steps` | 步骤清单 |
| PATCH | `/projects/steps/{id}` | 更新步骤状态；阶段完成自动推进，进度自动回算 |
| GET | `/projects/meta/summary` | 组合汇总 |
| **POST** | **`/projects/recommend-methodology`** | **立项向导：自动匹配方法论** |

### 流程执行
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/execution/processes` | 可启动流程（设计器里已有节点的流程） |
| GET | `/execution/instances` | 实例列表，支持 status / process_id |
| POST | `/execution/instances` | 启动实例；可传 variables 与按节点指派 assignments |
| GET | `/execution/instances/{id}` | 实例详情、任务时间线与变量 |
| POST | `/execution/instances/{id}/cancel` | 取消运行中实例（MANAGER+），未完成任务一并取消 |
| DELETE | `/execution/instances/{id}` | 删除实例及任务（MANAGER+，用于清理） |
| GET | `/execution/tasks` | 任务队列：status / assignee=me\|id / instance_id / process_id / only_open |
| GET | `/execution/tasks/{id}` | 任务详情（含可选下一步节点） |
| POST | `/execution/tasks/{id}/claim` | 认领任务 |
| POST | `/execution/tasks/{id}/complete` | 完成并推进；多出边时必须传 `next_node_key` |
| PATCH | `/execution/tasks/{id}/assignee` | 改派或退回公共队列（MANAGER+） |
| GET/POST | `/execution/forms` | 节点表单定义查询 / 新建（写入需 MANAGER+） |
| PATCH/DELETE | `/execution/forms/{id}` | 修改 / 删除表单定义（MANAGER+） |
| GET/POST | `/execution/rules` | 分支规则查询 / 新建（写入需 MANAGER+） |
| PATCH/DELETE | `/execution/rules/{id}` | 修改 / 删除分支规则（MANAGER+） |

### 方法论工具箱
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tools/grouped` | 按诊断/设计/落地/监控分组 |
| GET | `/tools/{code}` | 工具详情（含 5 步标准操作、模板、常见误用） |
| **POST** | **`/tools/match`** | **按问题找工具：输入「审批太多周期太长」返回匹配工具** |

### 流程设计器
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/processes/{id}/design` | 读取泳道模型 |
| PUT | `/processes/{id}/design` | 覆盖式保存（校验 node_key 唯一、连线不悬空） |
| POST | `/processes/{id}/design/analyze` | 测算已保存模型 |
| POST | `/design/analyze` | 边改边算，不落库 |

### 运营监控
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/monitor/kpi-radar` | 四维度雷达 + 各指标时序 |
| GET/POST | `/monitor/kpis` | KPI 定义 |
| GET/POST | `/monitor/kpis/{id}/records` | 时序数据（同期同项目重复提交自动覆盖） |
| GET | `/monitor/exceptions/summary` | 异常概览（含超期数、按严重度分布） |
| GET/POST/PATCH/DELETE | `/monitor/exceptions[/{id}]` | 异常事件闭环 |

### 流程知识库
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge` | 检索：type / methodology / tag / keyword / sort=recent\|hot |
| GET | `/knowledge/meta/tags` | 标签云 |
| POST | `/knowledge/{id}/read` | 记录查阅/下载 |
| GET/POST/PATCH/DELETE | `/knowledge[/{id}]` | CRUD |

---

## 两个核心算法

### 1. 立项向导：方法论自动匹配

输入流程现状、目标改善幅度、范围与约束，输出推荐方法论 + 置信度 + 判断依据 + 工具链 + 风险提示。

基础映射（方法论选择矩阵）：

| 流程现状 | 目标 | 推荐 |
|---|---|---|
| 严重过时、断裂、与战略脱节 | 阶跃式突破（≥50%） | 🔴 BPR |
| 基本合理但效率不足、局部堵点 | 渐进改善（10–30%） | 🟡 BPI |
| 现场/操作层浪费明显、波动大 | 持续流动、消除浪费 | 🟢 精益 |
| 混合状态 | 先 BPR 定架构，再 BPI/精益细化 | 组合拳 |

再按目标幅度、范围、是否涉及组织调整、有无数据基础、周期约束做校正，并给出反直觉的预警。例如：

```bash
curl -X POST localhost:8000/api/v1/projects/recommend-methodology \
  -H 'Content-Type: application/json' \
  -d '{"process_state":"SEVERE_OUTDATED","target_improvement_pct":8,"scope":"LOCAL"}'
```

→ 目标只有 8% 却判定现状严重过时：返回 RISK 级别的风险提示「以现有流程框架做局部改善，大概率改善后仍然过时」，并下调置信度。

### 2. 流程设计器：周期效率测算

对泳道模型逐节点测算，核心指标：

- **端到端周期** = Σ(作业时间 + 等待时间)
- **PCE（流程周期效率）** = 增值作业时间 ÷ 端到端周期
- **期望执行成本** = Σ(单次成本 × 期望执行次数)，返工造成的重复执行同样计入成本，
  与时间口径保持一致

然后跑 9 条建议规则，每条都给出量化依据、相关节点和应调用的工具：

| 规则 | 触发条件 | 建议工具 |
|---|---|---|
| `LOW_PCE` | PCE < 15% | BPR 六原则 |
| `WAIT_DOMINANT` | 等待占比 ≥ 50% | 产能与排队模型 |
| `TOO_MANY_APPROVALS` | 累计审批层级 > 3 | RACI |
| `MANY_HANDOFFS` | 跨泳道移交 > 3 次 | 跨职能泳道图 |
| `REWORK_LOSS` | 存在返工率 ≥ 10% 的节点 | 5 Why |
| `SERIAL_TO_PARALLEL` | 发现可并行的串行环节 | To-Be 蓝图 |
| `NON_VALUE_ADDED_TASKS` | 非增值作业 ≥ 30% | 精益七大浪费 |
| `MISSING_OWNER` | 有节点未指定负责人 | RACI |
| `COST_CONCENTRATION` | 单节点占 > 40% 执行成本 | 加权决策矩阵 |

最后根据测算结果反推方法论。以种子数据里的「采购需求提报」为例：

```text
线性合计 6720 分钟（14.0 天）
期望端到端 9459 分钟（19.7 天，含 30% 驳回回路与节点返工）  +41%
PCE 6.8%   等待占比 87.6%
跨泳道移交 5 次   累计审批 4 层   返工让周期多出 3315 分钟
→ 触发 6 类建议，推荐 BPR
```

> 注意分母和分子的口径：**增值时间只算「一次通过」**，返工是同一个步骤的重复执行，
> 按精益定义属于浪费，不能计入增值——否则 PCE 会虚高。

**瓶颈怎么判定**（这是个容易做错的地方）：不能拿「等待占比高」当判据——在等待主导的流程里，
几乎每个节点的等待占比都高，那样会得出「全是瓶颈」的结论，等于没结论。
实际用的是**相对时长**加硬伤：端到端时长超过均值 1.5 倍、或审批层级 ≥3 层、或返工率 ≥10%。
同一个流程用这两套判据的差别是 6 个瓶颈 vs 3 个瓶颈。

**并行候选怎么找**：以连线为准，而不是按声明顺序猜。这样能自动排除「驳回」这类分支边
（它们带条件或发生概率小于 1，本来就不该进并行化讨论）。

---

## 对标框架：SCOR 与 APQC PCF 可切换

**为什么不做两套流程树**：SCOR 是供应链专用模型（Plan / Source / Make / Deliver /
Return / Enable），APQC PCF 是跨行业企业流程框架（13 个 L1，含战略、研发、人事）。
如果把两套分类直接混进 `process_arch`，同一份公司流程会被复制成两棵互不相干的树，
项目、流程模型、KPI 的引用也会跟着框架漂移。

当前采用**交叉映射**：

```text
process_arch（公司唯一流程架构，L1–L4）
        │  多对多
        ▼
process_benchmark_map
        │
        ├── benchmark_category ── benchmark_framework(SCOR)
        └── benchmark_category ── benchmark_framework(APQC_PCF)
```

- 切换框架只改变**参照树与覆盖率**，不改变业务数据；同一个流程可以同时映射到两套框架。
- 覆盖率按**后代聚合**：流程自身或任一后代映射到该框架，即视为覆盖。所以同一份映射
  在 L1 / L2 / L3 任一层都能看到有意义的覆盖率，不会出现「下层映射了、上层 0%」。
- L1/L2 覆盖率接口的参数是 `process_level`；流程地图右上角的框架选择器做的就是这个切换，
  选中后展示各 L1 分类的覆盖数、未覆盖流程，点分类行可看明细。
- L4 活动默认继承所属 L3 的对标分类（例如「生产计划排程」下的 4 个活动自动映射到
  SCOR `P3` / APQC `4.3`），不需要逐个维护。

**种子数据的实际对比**（L3 共 28 条流程）：

| 框架 | 已覆盖 | 覆盖率 | 未覆盖 |
|---|---|---|---|
| SCOR | 24 / 28 | 85.7% | 新产品开发立项、工艺设计变更、试制与验证、费用报销 |
| APQC PCF | 28 / 28 | 100% | — |

SCOR 的缺口不是数据缺陷，而是框架边界：研发与费用报销本来就不属于供应链运作。
这也验证了「两套框架适配不同」——切换后看到的不是同一份结果的换皮。

> ⚠️ 内置的只是 L1/L2 **基线分类**，用于演示映射机制。正式对标前应替换为
> ASCM / APQC 的授权版本全文，并补齐到 L3–L5；不要把这份数据当作官方框架全文。

---

## 权限与审计

**认证**：除 `/auth/login` 和 `/health` 外，所有接口都要求 `Authorization: Bearer <token>`。
令牌是 HMAC-SHA256 签名的无状态票据（标准库实现，不引入 PyJWT / passlib），口令用
PBKDF2-HMAC-SHA256 加盐存储，默认 12 小时过期。

> 生产上线前**必须**设置环境变量 `SECRET_KEY`（默认值只用于本地开发，`/auth/security-check`
> 会提示当前是否仍在使用默认密钥）。

**角色与权限边界**：

| 能力 | ADMIN | MANAGER | OWNER | VIEWER |
|---|---|---|---|---|
| 读全部数据 | ✅ | ✅ | ✅ | ✅ |
| 项目 / 异常 / 流程模型 | ✅ | ✅ | 仅自己名下 | ❌ |
| 流程架构 / KPI 定义 / 知识库 | ✅ | ✅ | ❌ | ❌ |
| 用户管理 | ✅ | ❌ | ❌ | ❌ |
| 审计日志 | ✅ | ✅ | ❌ | ❌ |

OWNER 的归属按 **`owner_user_id` 外键**判断（项目、异常事件与流程模型都带这个字段），
不再比较姓名字符串——改个 `display_name` 不会凭空获得别人的项目权限。
历史数据或外部导入只给了 Owner 姓名时，写入阶段会按**唯一**的同名账号尝试绑定；
同名账号有歧义、或系统中没有对应账号，就保持未绑定（fail closed，只有 MANAGER+
能改）。`owner` 文本仅作展示标签，绑定账号时会同步成该账号的姓名。

**审计**：所有写操作都会落 `audit_log`（谁、什么时候、对哪个对象、做了什么），
`GET /audit` 可按实体类型 / 动作 / 操作人筛选。

---

## 写入口一览（前端）

早期版本前端只能改状态、不能建数据，现在补齐了：

| 位置 | 能做什么 | 角色要求 |
|---|---|---|
| 流程地图 | 新建 / 编辑 / 删除流程架构 | MANAGER+ |
| 项目组合 | 新建（含立项向导）、编辑属性、删除项目 | OWNER 仅自己名下；删除需 MANAGER+ |
| 项目详情 | 改步骤状态、甘特图与里程碑 | OWNER 仅自己名下 |
| 流程设计器 | 节点增删改、泳道建模 | OWNER 仅自己负责的流程 |
| 运营监控 | 登记异常、处理异常、新建 KPI、录入数据点 | 异常 OWNER+；KPI 需 MANAGER+ |
| 知识库 | 新建知识条目 | MANAGER+ |

无权限时按钮直接隐藏或禁用，后端仍会独立校验（前端隐藏不等于后端放行）。

---

## 两个工程性保障

**流程模型的并发控制**：`PUT /processes/{id}/design` 是整份覆盖保存。请求体可带
`expected_version`，与服务端版本不一致时返回 **409**，前端会自动载入最新版本而不是覆盖别人的改动。
`GET` 返回的 `version` 每保存一次 +1。

**甘特图与里程碑**：每个阶段的最后一步（决策门）标为里程碑，`GET /projects/{id}/schedule`
返回按阶段聚合的时间轴。种子数据会按项目计划窗口自动铺开每个步骤的 `due_date`，
所以甘特图开箱就有内容。逾期里程碑会标红。

---

## 开发纪律

详细约定见 [CLAUDE.md](CLAUDE.md)（那份文件同时是给 AI 助手的作业规范）。这里只列执行层面。

**一条命令跑全部检查**（与 CI 一致）：

```bash
python scripts/check.py          # 格式 + 静态检查 + 测试
python scripts/check.py --fix    # 自动修复后再检查
python scripts/check.py --fast   # 只跑 lint
```

Windows 上通常没有 `make`，所以入口是 Python 脚本而不是 Makefile；
`Makefile` 保留给 CI 和类 Unix 环境。

**提交前自动检查**：`pre-commit install` 之后，每次 `git commit` 会跑
ruff 格式化、ruff 静态检查、前端模块结构检查。钩子全部是 `language: system`
的本地钩子，不会去拉远端仓库——内网环境不会卡住。

**CI**：`.github/workflows/ci.yml` 在 SQLite 与 PostgreSQL 两个后端上分别跑一遍测试，
矩阵里的 `TEST_DATABASE_URL` 决定用哪个。

**提交信息**用 Conventional Commits：`feat:` / `fix:` / `refactor:` / `test:` / `docs:` / `chore:`。
分支用 `main` + 短生命周期分支，不合长时间存在的开发分支。

**静态检查的规则集是收敛过的**，只选 `E / F / I / B`（语法级错误、未使用导入、
导入排序、易错写法）。刻意**没开** `UP`（pyupgrade）——它会把 `Optional[X]` 批量改成
`X | None`、`Dict` 改成 `dict`，一次三百多处改动，收益全在好看，风险却不小。
那应该是一轮独立的、可单独 review 的重构，不能混在业务改动里。

---

## 第二阶段待办

已完成：前端接后端、用户与权限、甘特图与里程碑、流程模型并发控制、时间语义统一、
周期测算改为按图求期望值、切换 Docker PostgreSQL、引入 Alembic 迁移、前端模块化、
对标框架（SCOR / APQC PCF）的后端交叉映射、流程执行第一阶段（实例 + 任务队列 + 分支推进）。还剩：

1. **流程挖掘对接**：接入 ERP/OA 日志，自动发现真实路径（`PROCESS-MINING` 工具已就位，缺数据管道）。
2. **权限细化**：OWNER 归属已改为 `owner_user_id` 外键（项目 / 流程模型），
   姓名只在写入时用于尝试绑定唯一账号；还剩字段级可见性控制没有做。
3. **通知与提醒**：里程碑逾期、异常超期目前只能靠人看板子，没有推送。
4. **导入导出**：BPMN 导出、Excel 导入流程清单都还没有。
5. **生产部署**：镜像里用 uvicorn 单进程起服务，上生产需要加 gunicorn/多副本 + 反向代理 + HTTPS；
   数据库连接的 SSL 与备份策略也还没配。
6. **前端事件委托**：模板仍用 `onclick` 内联属性，`main.js` 因此要把几十个函数挂到 `window`。
   改成 `data-action` + 事件委托后可以彻底去掉这层全局暴露；这是模块化之后剩下的最后一块耦合。
7. **对标框架前端**：流程地图已支持页面级框架切换、覆盖率展示与分类明细；还剩
   映射关系的可视化维护入口（目前映射 CRUD 只通过 API 提供）。
8. **流程执行后续**：已完成单令牌顺序执行、表单定义与分支规则；下一步补 BPMN 导入导出、
   并行网关与子流程、通知与 ERP/OA 集成。
