# 三入口主线与单流程开发环境实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留工作台三个入口，保留全部生产代码能力，并让新部署的测试/开发环境自动使用 `L3-032 采购需求提报` 这一条干净流程。

**Architecture:** 不重写前端导航、不新增测试数据库、不删除页面。只在现有开发/测试 seed 路径中增加单流程数据集合，生产 bootstrap 保持不灌演示业务数据；当前开发数据库先备份，再用现有 seed reset 机制重建。后续页面优化另行逐页进行。

**Tech Stack:** FastAPI、SQLAlchemy 2.0、PostgreSQL/SQLite、pytest、现有 seed runner、Alembic。

**Spec:** `docs/superpowers/specs/2026-11-12-single-flow-navigation-design.md`

## Global Constraints

- 工作台三个入口必须保持不变：流程框架、一条流程、一个项目。
- 所有页面源码、API、ORM 和生产能力保留；本轮不做前端导航框架重写。
- 测试/开发环境只保留 `L3-032` 及其 `L1/L2/6 个 L4` 和必要关联数据。
- 生产代码不得写死唯一流程、`L3-032` 或测试数据数量。
- 不新增测试数据库；沿用现有数据库初始化和测试数据库机制。
- 生产 bootstrap 不灌演示业务流程；测试/开发 seed 才使用单流程集合。
- 数据删除前必须备份；本轮备份文件为 `logix_pms_before_single_flow_20261112.dump`。
- schema 演进只走 Alembic；本轮不新增表或字段。
- 不修改页面挂载列表；后续由用户指定页面后逐个优化、逐个挂载。
- 完成前运行 `pytest`；格式/静态检查使用项目实际可用的 Ruff 命令或 `python scripts/check.py`，失败必须如实报告。

## Review Focus

- 新库启动是否只生成 9 个保留流程节点和 1 个关联项目，而非只在当前库手工删除；由任务 1 的 seed 测试覆盖。
- 单流程 seed 是否漏掉某张业务关联表，导致旧数据残留或唯一键冲突；由任务 1 的重建测试和任务 2 的数据库复核覆盖。
- 生产 bootstrap 是否仍保持无演示业务数据；由任务 1 的既有 bootstrap 测试覆盖。
- 流程代码改动是否误把单流程限制写进生产模型/API；由任务 3 的差异检查和生产 bootstrap 测试覆盖。
- 当前数据库重建失败时是否可恢复；由任务 2 的备份、日志和恢复边界覆盖。

---

### Task 1: 让开发/测试 seed 只生成 L3-032

**Files:**

- Modify: `app/seed/runner.py`
- Modify: `app/main.py`
- Modify: `scripts/seed.py`
- Modify: `tests/test_bootstrap.py`
- Test: `tests/test_bootstrap.py`

**Interfaces:**

- `seed_single_flow(db: Session, reset: bool = False) -> Optional[Dict[str, int]]`：只用于开发/测试 seed；新库生成 `L1-03`、`L2-003`、`L3-032`、`L4-201..206` 和关联 `PR-2026-018`。
- `seed(db, reset=False)`：保持现有完整 seed 行为，支持真实多流程/多项目数据；不调用单流程过滤。
- `bootstrap_production(...)`：保持参考数据 + 管理员、无演示业务数据。

- [x] **Step 1: Write failing test**

在 `tests/test_bootstrap.py` 增加测试，使用临时 SQLite 数据库验证：

```python
def test_development_seed_contains_only_l3_032_and_its_project(tmp_path):
    with _session(tmp_path) as db:
        result = seed_single_flow(db, reset=True)
        assert {row.code for row in db.scalars(select(ProcessArch)).all()} == {
            "L1-03", "L2-003", "L3-032",
            "L4-201", "L4-202", "L4-203",
            "L4-204", "L4-205", "L4-206",
        }
        projects = db.scalars(select(Project)).all()
        assert len(projects) == 1
        assert projects[0].process_id == next(
            row.id for row in db.scalars(select(ProcessArch)).all()
            if row.code == "L3-032"
        )
        assert result["process_arch"] == 9
        assert result["projects"] == 1
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py::test_development_seed_contains_only_l3_032_and_its_project -q`
Expected before implementation: FAIL with `ImportError: cannot import name 'seed_single_flow'`.

- [x] **Step 2: Implement minimal seed filter**

在 `app/seed/runner.py` 增加开发/测试单流程过滤，只过滤 seed 输入集合，不改 ORM/API 业务规则：

- 流程树只保留 9 个确定代码；
- 项目只保留 `PR-2026-018`；
- KPI、异常、RACI、授权、数据流、变更、工作量、对标映射、设计模型等只保留指向该流程或其 L4 的记录；
- 执行 seed 不再无条件访问 `L3-033`；
- `_wipe()` 覆盖授权规则/例外、知识场景等实际 seed 会写入的业务表，避免 reset 后旧数据残留；
- 完整 `seed()` 在默认模式下继续遍历现有完整数据集。

- [x] **Step 3: Wire development startup and CLI**

开发启动 `SEED_ON_STARTUP=true` 且允许开发密钥时调用 `seed_single_flow(db, reset=False)`；生产 `SEED_ON_STARTUP=false` 路径不调用它。`scripts/seed.py` 增加 `--single-flow`，并正确处理已有数据时返回 `None` 的跳过情况；`--single-flow --reset` 才执行重建。

- [x] **Step 4: Run targeted tests**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py tests/test_frontend_structure.py -q
```

Expected: PASS。实际结果：`61 passed`（含既有警告）。单流程临时 SQLite seed 输出为 9 个流程节点、1 个项目、6 个模型节点、6 条连线、1 个实例、3 个任务、4 个 KPI。

- [ ] **Step 5: Run static check**

Run:

```bash
.venv/Scripts/python.exe -m ruff check app/main.py app/seed/runner.py scripts/seed.py tests/test_bootstrap.py
```

Expected: PASS。已验证 PASS。

- [ ] **Step 6: Commit task**

```bash
git add app/main.py app/seed/runner.py scripts/seed.py tests/test_bootstrap.py
git commit -m "test: seed one development process"
```

提交前不提交数据库 dump，除非项目明确要求将备份纳入版本库；备份应作为本地/运维产物保留。

---

### Task 2: 重建当前开发数据库并核对数据边界

**Files:**

- No source files expected after Task 1.
- Runtime artifact: `logix_pms_before_single_flow_20261112.dump` (local backup, not source code)

**Interfaces:**

- Target database: 当前 `.env` 指向的 `postgresql+psycopg://...@localhost:5435/logix_pms`。
- Retained process codes: `L1-03`, `L2-003`, `L3-032`, `L4-201` through `L4-206`。
- Retained project: existing project sourced from `L3-032` (`PR-2026-018`)。

- [x] **Step 1: Back up current database**

已执行：

```bash
docker exec logix-pms-db pg_dump -U psm -d logix_pms -Fc > logix_pms_before_single_flow_20261112.dump
```

结果：备份文件约 1.9 MB，当前数据库重建前已留存。

- [x] **Step 2: Rebuild the confirmed database**

执行：

```bash
.venv/Scripts/python.exe -m scripts.seed --single-flow --reset
```

结果：成功输出 `process_arch 9`、`projects 1`、`process_nodes 6`、`process_edges 6`、`process_instances 1`、`process_tasks 3`、`kpis 4`，以及用户 4、组织 13、岗位 8、工作流 24、工具 36、基准框架 4 等基础数据。

- [x] **Step 3: Verify retained and protected data**

执行数据库核对：

```python
assert process_codes == {
    "L1-03", "L2-003", "L3-032",
    "L4-201", "L4-202", "L4-203",
    "L4-204", "L4-205", "L4-206",
}
assert project_count == 1
assert project.process_id == l3_032_id
```

实际结果：通过；`process_arch=9`，项目唯一关联当前 `L3-032`。基础数据保留：用户 4、组织 13、岗位 8、工作流模板 24、工具 36、基准框架 4、基准分类 6135、基准指标 3453。

- [ ] **Step 4: Verify no unintended process/project references**

检查所有带 `process_id` / `project_id` 的业务表：任何非空引用必须指向保留 L3/L4 或保留项目；不允许出现已删除流程 ID 的孤儿记录。

- [ ] **Step 5: Do not commit runtime backup**

备份文件保留在本地用于恢复，不加入代码提交。若后续用户要求归档，另行处理。

---

### Task 3: 验证生产行为和后续页面挂载边界

**Files:**

- No further production source changes expected.
- Review: `app/seed/runner.py`, `app/main.py`, `scripts/seed.py`, existing page modules.

**Interfaces:**

- `bootstrap_production()` remains reference data + administrator only.
- `seed()` remains the full multi-process/multi-project development/demo seed when explicitly selected by existing callers.
- `seed_single_flow()` is only the development/test startup path requested here.

- [ ] **Step 1: Run production bootstrap tests**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py::test_bootstrap_seeds_reference_and_admin_only tests/test_bootstrap.py::test_bootstrap_is_idempotent_and_blocks_demo_seed -q
```

Expected: PASS; production bootstrap creates no `ProcessArch`, `Project`, or `ProcessInstance` demo rows.

- [ ] **Step 2: Review production diff**

Confirm no production model, API, service, page renderer, or permission check contains a single-process restriction or `TST-*` assumption. The only single-flow constants belong to the development/test seed selection.

- [ ] **Step 3: Record page-by-page follow-up rule**

Do not change page registration in this task. For each later page, use the following gate before mounting it:

- upstream and downstream are explicit;
- one clear current topic;
- `process_id`/project context is explicit;
- default view shows conclusion, blockers, and next step first;
- the page is tested against the single `L3-032` development data;
- only then is the page mounted.

- [ ] **Step 4: Run final checks**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py tests/test_frontend_structure.py -q
.venv/Scripts/python.exe -m ruff check app/main.py app/seed/runner.py scripts/seed.py tests/test_bootstrap.py
alembic check
```

Expected: targeted tests PASS, Ruff PASS, Alembic reports no model/ migration drift. The full existing suite is expected to fail where old tests explicitly assert the former multi-process/multi-project demo seed; these failures must be reported rather than hidden or fixed by weakening assertions. Current full-suite result after single-flow data was applied: 45 failures, caused by assertions expecting rows such as `L3-033`, 8 projects, 16 KPIs, 8 exceptions and multi-process benchmark coverage.

- [ ] **Step 5: Run current-code browser verification**

Start the current service against the rebuilt database, verify startup log and served source, then run the existing frontend verification. Do not claim frontend verification passed until its output is captured; no frontend verification was run in this turn.

---

## Known verification status

- Single-flow seed in disposable SQLite: **PASS**.
- Targeted bootstrap/frontend structure tests: **PASS** (`61 passed`, warnings only).
- Ruff on changed Python files: **PASS**.
- Current PostgreSQL rebuild: **PASS** with the retained data counts above.
- Full pytest after applying one-flow data: **FAIL**, 45 failures because many existing tests explicitly require the old multi-process/multi-project fixture data. This is an expected compatibility gap that must be handled in a separate test-fixture update, not hidden by changing production logic.
- `python scripts/check.py --fast`: **NOT RUN successfully** because the script environment could not find `ruff`, although the project virtualenv Ruff command passed.
- Frontend browser verification: **NOT RUN**.
