# CLAUDE.md

给在本仓库工作的 AI 助手（以及新加入的人）看的工程约定。
**这里写的是"必须遵守"，不是"建议"。**

## 项目是什么

Logix PMS —— 流程管理系统。面向制造业的流程管理科，把 BPR / BPI / 精益
三大方法论整合成「识别 → 诊断 → 设计 → 落地 → 运营」五阶段标准工作流。

技术栈：FastAPI + SQLAlchemy 2.0 + PostgreSQL；前端是原生 ES 模块，无构建步骤。

## 常用命令

```bash
python scripts/check.py          # 格式 + 静态检查 + 测试（与 CI 一致）
python scripts/check.py --fix    # 自动格式化并修复
python scripts/check.py --fast   # 只跑 lint

pytest                                              # 默认临时 SQLite
TEST_DATABASE_URL=postgresql+psycopg://psm:psm_dev_password@localhost:5433/logix_pms_test pytest

docker compose up -d db          # 只起 PostgreSQL（宿主机 5433）
uvicorn app.main:app --reload --port 8123
alembic revision --autogenerate -m "说明"   # 改模型后生成迁移
alembic check                    # 确认模型与迁移没有漂移
python scripts/verify_frontend.py http://127.0.0.1:8123   # 前端端到端自检
```

## 结构

```
app/core      配置、数据库、安全、时间、迁移入口
app/models    ORM
app/schemas   Pydantic 契约
app/services  业务逻辑（方法论匹配、测算、审计…）
app/api/v1    路由
web/js/core   前端基础设施（api/auth/format/router/state/ui）
web/js/views  八个视图模块
```

前端依赖是单向的：`main.js → views/* → core/router → core/{api,auth,state,ui,format}`。
`router.js` 刻意不 import 任何视图，视图由 `main.js` 注册——否则会绕成环。

## 硬性约定

1. **schema 演进只走 Alembic。** 不要用 `create_all` 建生产表（测试环境下
   `AUTO_MIGRATE=false` 是例外）。
2. **时间一律 UTC 存储**，出参补 `+00:00`，前端按浏览器本地时区渲染。
   纯日期字段（`2026-04-01`）不要用 `new Date()` 解析。
3. **枚举的中文标签由后端下发**（`methodology_label` / `status_label` / `heat_level`…），
   前端不许自己维护映射表。
4. **前端新增视图**：写 `web/js/views/x.js` 导出 `renderX` → 在 `main.js` 里
   `register('x', renderX)` → 更新 `tests/test_frontend_structure.py`。
5. **提交前跑 `python scripts/check.py`。** 它跑不过就不要提交。
6. **`alembic.ini` 必须保持纯 ASCII。** Windows 下 configparser 按系统 locale（中文机器是 GBK）
   读这个文件，写中文注释会直接抛 `UnicodeDecodeError`。

## AI 协作纪律

下面每一条都来自**已经发生过的真实事故**，不是泛泛而谈。

1. **不凭记忆改代码。** 动手前先 `Read` 当前文件。
   > 事故：我曾断言 Dockerfile「没有构建验证」，实际上后台构建早就成功了，
   > 而且容器里跑的是旧镜像。记忆和现实脱节时，只有读文件能救。

2. **结论必须附证据。** 说「通过 / 修复 / 改善」就要贴出命令输出；
   没有验证的部分必须明说「未验证」，不能含糊。
   > 事故：我声称改成完整图模型后 PCE 会从 8.0% 降到 5.9%，
   > 实测是 6.8%——因为我只放大了分母，忘了增值时间也会被放大。

3. **验证对象必须是当前代码。** 容器、后台服务、缓存都可能过期。
   先核对版本号、文件内容或启动日志，再下结论。
   > 事故：E2E「全绿」，但打到的其实是本地旧进程，容器里根本没有新代码。

4. **同一个概念只保留一个实现。** 发现重复建模立即合并，不要"两套各算各的"。
   > 事故：返工同时用「节点返工率」和「路径回路」表达，一套进了计算、一套没进。

5. **不留废弃代码。** 要么修，要么写进 README 的待办；不要注释掉留着。

6. **改完必须验证。** 后端改动跑 `pytest`；前端改动跑 `scripts/verify_frontend.py`；
   涉及 schema 跑 `alembic check`。三者任一没过，就不算完成。

## 不要做的事

- 不要在前端硬编码枚举中文，也不要引入构建工具（保持零构建）
- 不要在 `views/*` 之间互相 import 造成循环
- 不要把 `Depends()` 从默认参数里挪走（FastAPI 依赖注入就是这么用的，B008 已忽略）
- 不要为了让 lint 通过而把 `Optional[X]` 批量改成 `X | None` —— 这属于独立的一轮重构，
  会和业务改动混在一起，没法 review
- 不要在没有 git 提交的情况下做大范围重写
