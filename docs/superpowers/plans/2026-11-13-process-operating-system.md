# Logix PMS 流程经营系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可引导任意流程从 0 到 1 的流程经营系统能力，并用 `L3-032 采购需求提报` 作为验证样本，而不是把样本写成生产规则。

**Architecture:** 先建立通用的流程经营契约：流程对象、12 个 Gate、状态、证据、责任和下一步；再以 L3-032 演练一条垂直主线，逐步暴露事实/证据/决策能力缺口。页面不按历史模块名一次性改造，而按用户任务和 Gate 输出逐个保留、合并或后台化。生产代码继续支持多流程、多项目。

**Tech Stack:** FastAPI、SQLAlchemy 2.0、原生 ES modules、PostgreSQL/SQLite、pytest、现有页面壳和流程/项目/执行/KPI/组织/治理模型。

**Spec:** `docs/superpowers/specs/2026-11-13-process-operating-system-design.md`

## Global Constraints

- 工作台三个入口保持：流程框架、一条流程、一个项目。
- `L3-032` 只是测试和反推样本，不是生产唯一流程，也不是系统固定业务规则。
- 生产 ORM、API、服务和页面能力继续支持多流程、多项目。
- 12 个 Gate 是通用流程经营能力框架，不是 L3-032 专属验收台账。
- Gate 1–10 属于上线准备，Gate 11 属于试点/上线决策，Gate 12 属于上线后运营复核。
- Gate 7 和 Gate 9 必须支持“不适用 / 轻量 / 正式分析”分级。
- 经营周期按 `process_id` 关联任意 L3，可选关联 `project_id` 与 `model_version_id`；不能把 Gate 状态直接写进 `ProcessArch`。
- Gate 评估是对现有 readiness、项目门、证据、异常、RACI、KPI 和工作量结果的聚合，不得创建第二套事实口径。
- 证据引用必须保留来源类型、来源 ID、来源版本/哈希、等级和核验记录；Seed/开发数据不能自动成为 E3/E4。
- 流程层决策必须持久化责任人、授权依据、理由、证据快照、适用范围和复核日期。
- 工程能力、业务证据和最终决策必须分离，Seed 数据不能冒充真实业务证据。
- 最佳实践按适用性融入 Gate，不建立 PMO/IPD/精益/六西格玛/SCOR/APQC 的平行流程引擎。
- 同一事实只保留一个来源，其他页面只读投影；不复制第二套指标、责任或状态计算。
- 本阶段先做系统规格和最小垂直切片，不一次性修改全部页面。
- schema 演进只走 Alembic；任何新表/字段必须先通过独立设计和迁移评审。

## Review Focus

- `process_id`、project、L4、Gate、evidence 和 decision 的关系是否能支持任意流程，而非只支持 L3-032。
- 工程配置、业务确认、真实运行和效果复核是否被错误合并为一个“完成”状态。
- Gate 12 是否被错误作为首次上线硬阻断；它必须是上线后的运营复核。
- 不适用实践/不适用 Gate 是否能被明确记录，而不是被误报为缺口。
- 页面主线是否真正由“当前任务—阻断—下一步”驱动，而不是继续按历史模块平铺。

---

### Task 1: 固化系统级规格和样本边界

**Files:**

- Review: `docs/superpowers/specs/2026-11-13-process-operating-system-design.md`
- Review: `docs/superpowers/specs/2026-11-13-l3-032-process-acceptance-baseline.md`
- Review: `docs/process-operating-binding-model.md`
- Review: `docs/process-performance-decision-loop.md`
- Review: `docs/process-organization-governance-loop.md`
- Review: `docs/process-transformation-practice-system.md`

**Interfaces:**

- Produces the system-level contract: any L3 process can use the same 12-Gate operating model.
- Produces the sample boundary: L3-032 is test/reasoning data only.
- Produces the page decision rule: task output and evidence decide mount/merge/backend status later.

- [x] **Step 1: Write the system-level specification**

The specification must include: system purpose, core process object, facts/evidence/decisions separation, 0-to-1 journey, 12 Gate capability model, lifecycle positioning, status model, evidence grades, sample role, practice integration, page reverse-mapping rules, and first-phase scope.

- [x] **Step 2: Self-review against scope**

Verify the document does not:

- make L3-032 a production rule;
- treat existing configuration as business acceptance;
- require Gate 12 before first launch;
- make all practices mandatory;
- decide page keep/merge/backend status before the operating contract exists.

- [ ] **Step 3: Builder review**

Dispatch an implementation-oriented reviewer and record only questions that change the implementation plan. Resolve document-level gaps before writing code.

- [ ] **Step 4: Commit the specification**

```bash
git add docs/superpowers/specs/2026-11-13-process-operating-system-design.md
git commit -m "docs: define process operating system" 
```

---

### Task 2: Define the generic Process Operating Contract

**Files:**

- Inspect: `app/models/process.py`, `app/models/project.py`, `app/models/monitor.py`, `app/models/execution.py`, `app/models/raci.py`, `app/models/workload.py`, `app/models/asset_graph.py`
- Create: generic operating-cycle, gate-assessment, gate-evidence and operating-decision models/schemas/services after schema review
- Create: Alembic migration only if persistence is confirmed necessary
- Test: `tests/test_process_operating_contract.py`

**Interfaces:**

- `ProcessOperatingCycle` is keyed by any L3 `process_id`, with optional `project_id` and `model_version_id`; it supports `BASELINE`, `IMPROVEMENT`, `PILOT`, and `OPERATING` cycles and preserves closed history.
- `ProcessGateAssessment` is keyed by `cycle_id + gate_key`; it contains `status`, `applicability`, `rigor`, owner/verifier, risk, conclusion, next-action reference and due date.
- `ProcessGateEvidence` references source objects by type/ID plus source version/hash and stores `E0`–`E4`, verification state, verifier and note; it does not copy KPI/RACI/readiness facts.
- `ProcessOperatingDecision` records the cycle, decision type, decision, decision maker, authority basis, reason, evidence snapshot, scope and follow-up date; the decision maker is selected per process/cycle, not inferred from ADMIN/MANAGER/Owner alone.
- The readiness service returns `current_gate`, `completed_gates`, `blocking_gates`, `conditional_gates`, `unverified_evidence`, `next_actions` and `available_decisions` while consuming existing source services.
- Gate 12 is post-launch review only; `can_enter_pilot` and `can_enter_launch` must not require Gate 12.

- [ ] **Step 1: Write failing contract tests**

Test generic behavior using a temporary process created inside the test:

```python
def test_contract_is_keyed_by_any_l3_not_sample_code():
    contract = create_contract(process_id=temporary_process.id)
    assert contract.process_id == temporary_process.id
    assert contract.process_id != sample_l3_032_id


def test_gate_12_is_not_required_for_first_launch():
    assert readiness.can_enter_pilot(gates_with_gate_1_to_10_ready) is True
    assert readiness.can_enter_launch(gates_with_gate_11_passed_and_gate_12_unreviewed) is True


def test_gate_7_and_gate_9_can_be_not_applicable():
    assert gate.status == "NOT_APPLICABLE"
    assert gate.does_not_block_launch is True


def test_seed_configuration_is_not_business_evidence():
    assert evidence.grade_for_seed_configuration == "E1"
    assert evidence.grade_for_real_run == "E3"
```

Run the focused tests and confirm they fail because the generic contract does not exist.

- [ ] **Step 2: Implement the smallest generic contract**

Reuse existing process/project/evidence/exception/project-step objects wherever possible. Do not create a second process directory, KPI master, project engine or method repository. If a new persistence structure is required, write an Alembic migration and keep source references rather than copying full business records.

- [ ] **Step 3: Add readiness calculation**

Implement one backend service that returns:

```text
current_gate
completed_gates
blocking_gates
conditional_gates
unverified_evidence
next_actions
available_decisions
```

The service must not calculate a second version of KPI status, RACI validity or asset readiness; it consumes existing services and cites their source results.

- [ ] **Step 4: Verify focused tests**

Run the contract tests and the relevant existing tests for process, project, KPI, execution, RACI, workload and asset readiness.

- [ ] **Step 5: Commit**

```bash
git add app tests alembic
 git commit -m "feat: add generic process operating contract"
```

---

### Task 3: Build the L3-032 vertical sample path

**Files:**

- Modify only the selected mainline view(s) after Task 2 contract exists
- Create: sample/contract integration tests
- Test: `tests/test_process_operating_contract.py`

**Interfaces:**

- L3-032 is selected by its `process_id` from normal process selection; no production code checks `L3-032` specially.
- The sample test database contains one L3 but tests that need multiple processes create temporary processes and clean them up.
- The sample path must demonstrate at least: Gate 1, Gate 2, Gate 4, Gate 5, Gate 8, Gate 9, Gate 11 preparation.
- Gate 3 and Gate 11 real business evidence remain unfulfilled unless a real trial is explicitly supplied; the system must show the missing evidence, not fabricate it.

- [ ] **Step 1: Write failing sample-path tests**

Test that the same generic contract can:

- load L3-032;
- show current state and blockers;
- link existing objective/KPI/process/model/organization/project records;
- distinguish E1 configuration from E3 real run evidence;
- show Gate 11 as “trial evidence required” rather than “system error”;
- produce a next action for the user.

- [ ] **Step 2: Implement sample integration**

Use current L3-032 records only as references. Do not add sample-specific branches to production services. The sample path is successful when it exposes missing business evidence clearly.

- [ ] **Step 3: Verify sample path**

Run the focused sample tests, full pytest, Ruff and Alembic check.

- [ ] **Step 4: Commit**

```bash
git add web app tests
 git commit -m "feat: exercise process operating contract with sample flow"
```

---

### Task 4: Reverse-map existing pages from Gate tasks

**Files:**

- Review: all current `web/js/views/*.js`
- Create: `docs/superpowers/process-page-operating-map.md`
- Test: structure/contract assertions as appropriate

**Interfaces:**

- Each existing page is classified as one of: `mainline`, `projection`, `backend-support`, `learning/reference`, or `defer`.
- Classification is based on the Gate task it completes, its output evidence, its next action, and whether it owns or projects the source facts.
- No page is deleted as part of this task.
- No page is re-mounted merely because it exists.

- [ ] **Step 1: Build the page map**

For each page record:

```text
page
user task
Gate(s)
input sources
output evidence/decision
next destination
source-of-truth or projection
keep/merge/backend/defer recommendation
```

- [ ] **Step 2: Identify duplicate concepts**

Explicitly check for duplicated implementations of:

- process state;
- KPI labels/status;
- RACI/owner responsibility;
- workload/actual time;
- readiness/blockers;
- project progress and Gate status;
- benchmark mappings.

- [ ] **Step 3: Review the map before code changes**

The map is the decision artifact for the next page-by-page work. It must not silently authorize a broad navigation rewrite.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/process-page-operating-map.md
 git commit -m "docs: map process operating pages to gates"
```

---

### Task 5: Re-mount pages one focused topic at a time

**Files:**

- Modify one selected view at a time
- Modify `tests/test_frontend_structure.py` for each intentional mount
- Test: current-code frontend verification and focused sample path

**Interfaces:**

- A page is mounted only when it has one clear current topic, explicit process/project context, visible blockers, a next action, and a test against generic behavior plus L3-032 sample data.
- `pageShell` remains the layout boundary.
- Other expert content can remain as code but must not be eagerly fetched or rendered by an unrelated current topic.
- Backend support pages may remain reachable only through explicit, context-preserving actions.

- [ ] **Step 1: Choose the next topic from the page map**

Do not choose by historical menu order. Choose the next Gate task that blocks the sample 0-to-1 path and has enough backend evidence to test.

- [ ] **Step 2: Write a failing structure/behavior test**

Pin the intended mount, current topic, data loading boundary, next action, and process context.

- [ ] **Step 3: Implement the minimal page change**

Do not rewrite unrelated page modules or restore all historical tabs.

- [ ] **Step 4: Run focused and full verification**

Run page structure tests, current-code browser verification, full pytest, Ruff and Alembic check as applicable.

- [ ] **Step 5: Commit one topic**

```bash
git add web tests docs
 git commit -m "feat: mount one process operating topic"
```

Repeat Task 5 for each later topic.

## Final acceptance for this plan

The plan is complete when:

- any generic L3 can be represented by the operating contract;
- L3-032 can walk through a tested 0-to-1 sample path;
- the system distinguishes configuration from business evidence;
- Gate 11/12 are not falsely marked complete by Seed data;
- the page map explains which modules are mainline, projections or backend support;
- at least one page topic has been mounted from a Gate need rather than historical menu order;
- full pytest, Ruff, frontend structure verification and Alembic checks pass for the implemented slice.
