# BPM 第一批开发计划（草案）

> **状态：待另一模型/人工审定。** 审定入口：[Brief](bpm-first-batch-brief.md) · 交接说明：[bpm-review-handoff.md](bpm-review-handoff.md)。**审定通过前不得按本文编码。**
> 统一契约见 [产品基本原则](bpm-product-principles.md)、[落地规格](bpm-lifecycle-implementation-spec.md)。
> 代码基线：`4607792`。本文不替代 Alembic 最终字段名，开工前须锁定 §2 未决项。
> 范围：六个可验收切片（其中 2a、5 可独立先发），对应 R2-01 核心 + R2-02 + R1-04a + R0-02/R5-01 + spec §2.2 + R4-01 部分。

## 1. 目标与非目标

**目标：** 在不动 Flowable、不新建方案库/发布包库的前提下，交付一条可演示的最小证据链：

> 选定流程 → 建立轮次对照 → 冻结 As-Is 与指标口径 → 立项绑定 → 发布绑定 → 四种结论只读投影 → 流程卡查看 → 异常/培训/门禁引用同一 `round_id`。

**非目标（本批不做）：**

- R1-01/02 全量、R2-03、R3 全系、R1-05 二十项 resolver 全量。
- 八种结论的「推进状态机」或 `advance` API。
- ProcessRelease、PilotCondition、ProjectSolutionOption 等新主库。
- 宣称改善达标：本批只投影结论与缺项，独立收益裁决 UI 可占位。

## 2. 开工前必须锁定的决定（来自综合评审 §4）

| # | 决定 | 本计划建议默认值 | 若未定则阻塞 |
|---|---|---|---|
| 1 | 非运行模型如何冻结 | 新增 `ProcessModelVersion.role`（`AS_IS`/`TO_BE`/`RELEASE_CANDIDATE`）+ `frozen_at`；草稿仍可变，**冻结**后禁止原地改 snapshot | Slice 1 bind As-Is |
| 2 | round revision / 幂等 | `expected_revision` 乐观锁；写操作支持 `Idempotency-Key`（复用 `idempotency_service`，scope 前缀 `round.*`） | Slice 1 全部写 API |
| 3 | GateAttestation 扩展 | 增 `round_id`、`purpose`（`STAGE_GATE`/`IMPROVEMENT_ACCEPTANCE`）、`evidence_snapshot` JSON；**禁止** `PASS` 自动映射「改善达标」 | Slice 4 |
| 4 | KpiRecord 与验收样本 | 正式 round 样本行带 `round_id` + `metric_contract_hash`；带 `EXECUTION_NOTE` 的自动回写**不得覆盖**带 `round_id` 的行 | Slice 2 |
| 5 | 删除/归档 | round 与 project **RESTRICT** 或软删；项目 CLOSED 不删 round | Slice 1 FK |
| 6 | 权限 | 复用 `org_access` + 流程 Owner；round 写操作需流程编辑或项目经理角色（与现有 project 写权限对齐） | 全部 API |
| 7 | 试点业务窗口 | 文档/种子数据约定，不硬编码 KPI 目标 | 验收演示 |

## 3. 切片依赖

```text
Slice 2a (KPI 回写收窄) ──可独立先发──┐
Slice 5 (去掉 auto-EFFECTIVE) ──可独立──┤
Slice 1 (Round 表 + API) ◄──────────────┘
    ├── Slice 2b (round 样本 + contract)
    ├── Slice 3 (十层适用性 + 四结论投影)
    ├── Slice 4 (流程卡 + Gate 扩展)
    └── Slice 6 (异常 round_id，可略晚)
```

## 4. 切片 1 — 薄轮次对照（R2-01）

### 4.1 数据模型（Alembic）

**新表 `process_improvement_round`（名称以实现为准）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| process_id | FK → process_arch | 必填 |
| project_id | FK → project, nullable | 立项后 bind |
| revision | int, default 1 | 乐观锁 |
| supersedes_id | FK self, nullable | 修订链 |
| status | str | `DRAFT` / `BASELINE_LOCKED` / `PROJECT_BOUND` / `RELEASED` / `CLOSED` |
| asis_model_version_id | FK → process_model_version, nullable | |
| tobe_model_version_id | FK, nullable | |
| released_model_version_id | FK, nullable | 与 publish 事件同步写入 |
| metric_contracts | JSON | 数组：`{kpi_id, contract_key, hash, formula, unit, granularity, source_kind, ...}` |
| baseline_window | JSON | 规则 + 实际锚点 |
| after_window | JSON | 可空，上线后填 |
| acceptance_snapshot | JSON | 目标/红线/观察规则（后侧锁定前可部分空） |
| acceptance_ref | JSON | 只读投影外部验收记录 |
| org_scope_note | text, nullable | 业务范围说明 |
| created_by_id, created_at, updated_at | | |

**校验（service 层）：**

- `project.process_id` 必须与 `round.process_id` 一致（含祖先链规则与现有 strategy 一致）。
- `released_model_version_id` 必须属于同一 `process_id` 且该版本 `status=PUBLISHED`（或历史 SUPERSEDED 但有 `published_at`）。
- 绑定 As-Is 时允许 `project_id` 为空；绑定 project 后不可改 `process_id`。

**可选同批 FK（可为 NULL，后续切片填）：**

- `project_evidence_claim.round_id`
- `exception_event.round_id`
- `gate_attestation.round_id`

### 4.2 API（`/api/v1/processes/{process_id}/improvement-rounds`）

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `.../improvement-rounds` | 列表（含 status、四身份摘要、revision） |
| POST | `.../improvement-rounds` | 创建 DRAFT；可选初始 `asis_model_version_id` |
| GET | `.../improvement-rounds/{round_id}` | 详情 + 缺项列表（不计算四结论，可委托 Slice 3） |
| PATCH | `.../improvement-rounds/{round_id}` | 带 `expected_revision`；仅 DRAFT 可改 metric_contracts/baseline |
| POST | `.../improvement-rounds/{round_id}/lock-baseline` | → `BASELINE_LOCKED`；冻结 metric_contracts + asis |
| POST | `.../improvement-rounds/{round_id}/bind-project` | body: `{project_id}` |
| POST | `.../improvement-rounds/{round_id}/bind-published-version` | 在 publish 成功后由 API 或 publish hook 调用；写 `released_model_version_id` |

GET 不得创建 round、不得默认选最新 round 写库。

### 4.3 与现有 publish 集成

在 `process_model.publish()` 成功 `flush` 后：

- 若请求带 `round_id`（可选 query/header），校验版本属于该 round 的 tobe 或发布意图，更新 `released_model_version_id`。
- **不改变** 现有 publish 语义（仍 `_apply_snapshot`）。

### 4.4 测试（pytest）

新增 `tests/test_improvement_round.py`：

- 创建 round → lock baseline → bind project（错误 process 拒绝）。
- revision 冲突 409。
- bind published 版本非 PUBLISHED 拒绝。
- 项目删除/归档 round 仍可 GET（若采用 RESTRICT，则测删除项目失败或先解绑）。

## 5. 切片 2 — KPI 语义与 round 样本（R2-02）

### 5.1 Slice 2a（可先于 Slice 1 合并 PR）

**`KpiDefinition` 增量（或仅用 JSON `intake_spec`，优先显式字段）：**

- `intake_source_kind`：`EXECUTION_CYCLE` / `EXECUTION_NODE` / `INBOUND` / `MANUAL` / `WORKLOG` 等（枚举后端下发中文）。
- `intake_spec` JSON：如 `{ "event": "instance_completed", "aggregation": "avg", "field": "elapsed_seconds" }`。

**行为变更：**

- `intake_kind()`：仅当 `intake_source_kind==EXECUTION_CYCLE`（或等价）才走实例端到端回写。
- 保留现有 inbound webhook 路径。

**测试：** `tests/test_kpi.py` — 两个同为「小时」的 KPI，仅 cycle 指标被回写。

### 5.2 Slice 2b（依赖 Slice 1）

**`KpiRecord` 增量：** `round_id` nullable、`metric_contract_hash` nullable、`sample_role`（`BASELINE`/`AFTER`/`DIAGNOSTIC`）。

**规则：**

- `record_completed_instance` 跳过已有同 `(kpi_id, period, round_id)` 且 `sample_role=AFTER/BASELINE` 的行。
- 手工写入 round 样本须带 hash，与 round.metric_contracts 一致。

**测试：** 自动回写不覆盖 round 样本；hash 不匹配拒绝写入。

## 6. 切片 3 — 十层适用性 + 四种结论投影（R1-04a）

### 6.1 配置化适用性（可先不依赖 round）

**`PilotPath` 或新 JSON 列 `layer_overrides`：**

- 每层 evidence key → `REQUIRED` | `OPTIONAL` | `NOT_APPLICABLE` + `reason` + `approved_by`（可选）。

**默认：** 第 6 层 `rpa_bots`/`rpa_runs`/`technology_uses`/`process_cases` 为 OPTIONAL 或 N/A 模板（按流程类型后续 R1-01 再接）。

**`process_evidence._complete_runs`：** 可选仅计 `SUCCEEDED`（与规格一致；需产品确认是否 breaking change）。

### 6.2 四结论只读服务

新模块 `app/services/round_verification.py`（名待定），输入 `round_id`，输出：

```json
{
  "round_id": 1,
  "items": [
    {
      "conclusion_key": "DATA_READY",
      "status": "CONFIRMED|IN_PROGRESS|NOT_STARTED|BLOCKED",
      "verified_count": 4,
      "pending_count": 2,
      "missing": ["..."],
      "decision_ref": null,
      "next_actions": [{"view": "strategy", "label": "..."}]
    }
  ],
  "summary": "2/4 项结论已确认"
}
```

**判定要点（实现时必须编码，不能仅靠计数）：**

| 结论 | 最低条件 |
|---|---|
| 资料就绪 | round 有 BASELINE_LOCKED + 章程/目标/Owner 引用齐（复用 process_evidence 子集 + round 绑定） |
| 上线就绪 | `released_model_version_id` 非空 + 变更/制度引用（按适用性） |
| 运行有效 | 有 AFTER 样本或运行实例引用 + 数据质量未标红（可先简化：有样本且非 GRAY） |
| 改善达标 | **本批仅当** `acceptance_ref` 或扩展 Gate 存在且 purpose=IMPROVEMENT_ACCEPTANCE；否则 `NOT_STARTED` |

GET `/pilot/paths/{id}` 可选 query `round_id`：证据计数过滤到该 round 的模型版本。

### 6.3 测试

- 无 RPA 路径在第 6 层 N/A 时可 `gate_open`（若该层其余 required met）。
- 错 `released_model_version_id` 时「上线就绪」不为 CONFIRMED。
- `advance_path` 行为不变但文档标注：不等于八阶段推进。

## 7. 切片 4 — 流程卡与验收引用（R0-02 + R5-01 只读）

### 7.1 API

- `GET /process-card/{process_id}?round_id=` — 在现有 `ProcessCardOut` 增 `round_summary`、`verification`（Slice 3 输出）、`active_round_id`。
- `GateAttestation` 迁移字段见 §2；创建时可选 `round_id` + `purpose`。

### 7.2 前端（零构建）

- `process_card.js` / URL：`round` 参数；切换 round 刷新卡。
- 四种结论展示为规格文案（见 `bpm-interface-content-standard.md`），无「进入下一阶段」按钮。

### 7.3 测试

- 流程卡带 round 时返回 verification；无 round 时不伪造结论。
- Gate PASS + purpose=STAGE_GATE 不使「改善达标」为 CONFIRMED。

## 8. 切片 5 — 工具链（spec §2.2）

**规则：** 保存方法记录不自动写 EFFECTIVE；步骤上下文填 sheet 不等于方法已验证有效。

### 8.1 前端

- 删除 `web/js/views/shared/tool_sheet.js` 中在 `state.toolbox.step` 存在时自动 `POST /tools/.../usage` 且 `outcome: 'EFFECTIVE'` 的逻辑（`.catch(() => {})` 静默失败亦不允许作为补偿）。

### 8.2 测试

- 工具 sheet 提交后不得新增 `outcome=EFFECTIVE` 的 usage（除非用户显式走 usage API，且文案符合 [interface standard §2.2](bpm-interface-content-standard.md)）。
- `tests/test_tool_sheet.py` 或 API 级用例补充上述断言。

## 9. 切片 6 — 异常挂 round（R4-01 部分）

### 9.1 后端

- `ExceptionEvent.round_id` FK optional；创建/更新 API 接受 `round_id`；校验 round 与异常关联流程一致（若两者均有 process 上下文）。

### 9.2 测试

- API 测试 exception 带 `round_id` 持久化；越权/跨流程 round 拒绝。

## 10. 验收演示脚本（人工 / seed）

1. 选演示 L3，`POST` 创建 round，在设计器冻结 As-Is 版本并 `lock-baseline`。
2. 从 KPI 候选创建改善项目，`bind-project`。
3. 发布 To-Be，`bind-published-version`。
4. 流程卡查看 2/4 结论；十层路径带 `round_id` 查看第 6 层 N/A。
5. 登记异常挂 round；Gate 阶段门 PASS ≠ 改善达标。

## 11. 完成定义（DoD）

- `alembic check` 通过；新迁移纯 ASCII 注释。
- `pytest` 新增用例全绿；涉及前端改动的跑 `python scripts/verify_frontend.py`（若服务已起）。
- `python scripts/check.py` 通过（需 `pip install -r requirements-dev.txt`）。
- README **不**宣传未实现的四结论 UI 为「已上线」，可在「待办」链到本文。

## 12. 与文档产物链接

| 文档 | 关系 |
|---|---|
| [bpm-requirements-traceability.md](bpm-requirements-traceability.md) | 路线/规格/文案/IA 全量追溯 |
| [bpm-first-batch-brief.md](bpm-first-batch-brief.md) | 审定入口与通过标准（B1 子集） |
| [bpm-review-handoff.md](bpm-review-handoff.md) | 审定模型阅读顺序与输出模板 |
| [bpm-r1-implementability-review.md](bpm-r1-implementability-review.md) | R1-xx 相对基线代码 |
| [bpm-artifacts-review.md](bpm-artifacts-review.md) | §4 未决项必须在 §2 锁定 |
| [bpm-lifecycle-implementation-spec.md](bpm-lifecycle-implementation-spec.md) | R2-01/R1-04/R0-02/R5-01 的实现分解 |
| [bpm-interface-content-standard.md](bpm-interface-content-standard.md) | 四结论与「当前 publish / R3 部署」措辞 |

---

*本文档随第一批实施迭代；字段名或 API 路径变更时须同步更新测试与文案规范。*
