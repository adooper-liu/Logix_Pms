# 通用 Gate 5 责任闭合能力实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为任意正式 L3 建设 Gate 5 责任配置写入与闭合核验能力；使用通用合成 L3/L4 规则验收，L3-032 仅作可选烟测，不把它作为机制通过条件。

**Architecture:** 在现有 `ProcessArch`、已发布 `ProcessModelVersion`、`NodeActivityLink`、`RaciAssignment` 和 `NodeAssignment` 之上增加版本绑定的责任配置字段与责任接受证据。Gate 5 服务默认读取已发布模型，写入时原子更新已有责任对象，接受记录单独存储并绑定模型版本；readiness 只计算，不自动改变 Gate 状态。

**Tech Stack:** FastAPI、SQLAlchemy 2.0、Alembic、Pydantic、pytest、SQLite/PostgreSQL。

**Spec:** docs/superpowers/specs/2026-11-15-gate5-responsibility-closure-design.md

## Global Constraints

- L3-032 仅作为可选烟测；生产服务不得写死 `L3-032`。
- 默认只核验已发布模型；未发布模型只允许预览，不产生正式接受证据。
- 配置事实是 E1；模型版本绑定且责任人确认的是 E2；不生成 E3 运行事实。
- 不把流程级 RACI、岗位名称、系统角色或 `owner` 文本推断成账号责任。
- 复用 RACI 和 NodeAssignment；不建立第二套 RACI/责任台账。
- 每个 L4 必须有活动级唯一 A；执行账号、审批账号、替补、升级分别核验。
- 写入前校验权限、组织范围、岗位/账号有效期和模型版本；失败整体回滚并写审计。
- 不发布模型、不创建实例、不改变 Gate assessment、不进入 Gate 6。
- schema 演进只走 Alembic；必须运行 `alembic check`。

## Review Focus

- 模型发布后，旧版本责任配置和接受记录不能冒充当前版本。
- 一个节点的执行人、审批人、替补和升级人不能被同一字段或默认角色混淆。
- 停用账号、停用岗位、跨组织账号、无成员治理角色必须阻断。
- 重复写入、并发版本变化和撤回接受必须保留历史且不产生两个当前有效接受记录。
- 任意 L3 都能使用服务；L3-032 测试不能成为生产代码分支。

## Task 1: 责任配置与接受证据 schema

**Files:**
- Modify: `app/models/execution.py` (`NodeAssignment`)
- Create: `app/models/responsibility.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<new>_gate5_responsibility_closure.py`
- Test: `tests/test_gate5_responsibility_schema.py`

**Interfaces:**
- `NodeAssignment`: add `model_version_id`, `approver_user_id`, `backup_assignee_user_id`, `effective_from`, `effective_to`; retain existing execution/escalation fields.
- `ProcessResponsibilityAcceptance`: `process_id`, `model_version_id`, nullable `node_key`, `scope`, `subject_user_id`, `accepted_by_user_id`, `accepted_at`, `valid_until`, `evidence_note`, `status`.
- Current acceptance uniqueness: one active `ACCEPTED` row per `(process_id, model_version_id, node_key, scope, subject_user_id)`; historical rows remain.

- [x] Write failing model/metadata tests for columns, FK ownership, uniqueness and model imports.
- [x] Run `pytest tests/test_gate5_responsibility_schema.py -q`; expected RED because the model/table/columns do not exist.
- [x] Implement model fields, indexes, status/scope constants, and Alembic upgrade/downgrade. Do not use `create_all` for production schema.
- [x] Run the schema test and `alembic check`; expected PASS.
- [x] Run the relevant migration tests on SQLite and PostgreSQL-compatible metadata.

## Task 2: Generic readiness calculation

**Files:**
- Create: `app/services/gate5_readiness.py`
- Create: `app/schemas/gate5.py`
- Test: `tests/test_gate5_readiness.py`

**Interfaces:**
- `readiness(db: Session, process_id: int, *, model_version_id: int | None = None, viewer: User | None = None) -> Gate5Readiness`
- `Gate5Readiness`: process/model identity, `status`, `evidence_grade`, process-owner result, activity results, blockers, warnings, next actions, `configuration_writable`, `business_accepted`.
- `activity_ids_for_model()` uses versioned `NodeActivityLink`; legacy pointers produce warnings and cannot yield strict PASS.

- [x] Add synthetic any-L3 tests for no published model, owner text without account, missing activity A, process-level RACI masquerading as A, inactive users/positions/roles, absent assignment, stale acceptance, and valid E1/E2 output; watch RED.
- [x] Implement published-model resolution, activity mapping, organization/position/account validation, unique activity-A validation, assignment validation, approval conflict validation, acceptance lookup, and status aggregation.
- [x] Run readiness tests; expected PASS.
- [x] Add L3-032 fixture assertion only in tests: current sample is blocked for missing owner account, activity assignments/A, backup/escalation and acceptance; no production code branch on its code.

## Task 3: Generic configuration write service

**Files:**
- Modify: `app/services/gate5_readiness.py` or Create: `app/services/gate5_configuration.py`
- Modify: `app/services/raci.py` only where existing validation is insufficient
- Test: `tests/test_gate5_configuration.py`

**Interfaces:**
- `set_process_owner(db, process, *, owner_user_id, actor, expected_model_version_id) -> ProcessArch`
- `upsert_activity_assignment(db, process, *, node_key, expected_model_version_id, values, actor) -> NodeAssignment`
- `upsert_activity_accountability(db, process, *, node_key, role_id, actor, expected_model_version_id) -> RaciAssignment`
- `accept_responsibility(db, process, *, model_version_id, node_key, scope, subject_user_id, actor, valid_until, evidence_note) -> ProcessResponsibilityAcceptance`
- `withdraw_acceptance(db, acceptance, actor) -> ProcessResponsibilityAcceptance`

- [x] Add failing tests for ADMIN/MANAGER permission, OWNER scope, VIEWER rejection, published-version conflict, inactive/cross-org subjects, atomic rollback, audit entries, historical acceptance preservation and idempotent upsert.
- [x] Implement locked, atomic writes. Use existing `org_access`, RACI uniqueness and audit service. Assignments and acceptances must bind to the expected published model; preview versions cannot create E2 evidence.
- [x] Run configuration tests; expected PASS.
- [x] Run targeted existing RACI, position coverage, execution assignment, authorization and audit tests.

## Task 4: API contracts and routes

**Files:**
- Create/Modify: `app/schemas/gate5.py`
- Create/Modify: `app/api/v1/gate5.py`
- Modify: `app/main.py` or API router registration
- Test: `tests/test_gate5_api.py`

**Interfaces:**
- `GET /api/v1/processes/{process_id}/gate5/readiness?model_version_id=<optional>`
- `PUT /api/v1/processes/{process_id}/gate5/owner`
- `PUT /api/v1/processes/{process_id}/gate5/assignments/{node_key}`
- `PUT /api/v1/processes/{process_id}/gate5/accountability/{node_key}`
- `POST /api/v1/processes/{process_id}/gate5/acceptances`
- `POST /api/v1/processes/{process_id}/gate5/acceptances/{acceptance_id}/withdraw`

- [x] Add route tests for any-L3 readiness, response labels, read-only viewer, write permissions, 409 version conflicts, and no Gate assessment mutation; watch RED.
- [x] Implement routes with existing auth dependencies and transaction boundaries; expose backend labels, not frontend enum mappings.
- [x] Run API tests and existing auth/route tests; expected PASS.

## Task 5: Generic mechanism acceptance and optional smoke test

**Files:**
- Modify: `tests/test_gate5_readiness.py` only for sample assertions
- No dedicated L3-032 production files or page required.

- [x] Run the generic readiness and configuration suites plus existing RACI/execution/authorization tests. Only generic synthetic rules determine mechanism acceptance; the L3-032 smoke test is optional.
- [x] Run `python scripts/check.py` and `alembic check`.
- [x] Verify current development database with read-only readiness call only as an optional smoke check; do not use its blocked/conditional business result as a mechanism verdict.
- [x] Verify no new execution instance, no model publication, no Gate assessment mutation and no Gate 6 transition.
- [x] Review changed files for L3-032 literals in production code and remove any sample coupling.
