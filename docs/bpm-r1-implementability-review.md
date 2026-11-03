# R1 工作项可实施性复审（相对代码基线）

> **状态：** 供审定模型核对；**非**实施任务列表。  
> **基线：** `4607792`（`origin/main`）。Pull 后静态对照，未运行全量 pytest。  
> **规格锚点：** [落地规格 §4 R1-xx](bpm-lifecycle-implementation-spec.md)；第一批范围见 [Brief](bpm-first-batch-brief.md)。

## 1. 复审方法

- 对照 `docs/bpm-lifecycle-implementation-spec.md` 中 R1-01～R1-05 的「位置 / 增量 / 验收 / 分期」。  
- 在基线代码中确认**已有**能力与**缺口**；标注「第一批 / 后续 / 不前置」。  
- 「玩具/计数门禁」指：用 `count > 0` 或隐式副作用代替规格要求的适用性、来源与独立验收。

## 2. 总表

| 工作项 | 规格分期 | 基线代码支撑 | 第一批建议 | 主要阻塞 |
|---|---|---|---|---|
| R1-01 三类流程与排序 | 后续 | `ProcessArch` 无正式三类字段；有优先级/score 类逻辑 | **不做** | 主数据与 map 编辑规则 |
| R1-02 横向交接 | 后续 | SIPOC/ToolSheet/RACI 有模板与挂载 | **不做** | 无 Handoff 主表（规格亦不要求先建） |
| R1-03 章程/任命/资源 | 可增量 | `ProcessCharter`、治理角色、授权规则 | **部分**（字段补全） | SP-02/PF-02 等「批准文件」载体弱 |
| R1-04 十层适用性 | 第一批（引用/缺项） | `pilot.py` 路径与 `process_evidence` | **Slice 3** | 第 6 层强制 RPA/tech 计数；`_complete_runs` 是否只计 SUCCEEDED |
| R1-05 二十项保障视图 | 后续（resolver） | 章程/RACI/培训/KPI 等分散在各模块 | **不做全量** | 需只读 resolver，禁止 PilotTask 预生成 |

## 3. R1-01 分类和排序依据

**规格要求：** 三类流程落在同一目录；排序有批准依据，不承诺「核心永远第一」。

**基线：**

- `app/models/process.py`：`ProcessArch` 无 `process_type`（核心/支持/管理）一类正式枚举字段。  
- 实训/CBOK 有讲义级说明；`app/services/` 存在组合优先级/score 用于改善候选等（非投资排序承诺）。

**结论：** 非第一批。若演示需要，可种子/文案层面临时标注，**不能**冒充主数据已落地。

## 4. R1-02 横向交接

**规格要求：** 先用 SIPOC/RACI/结构化模板固定引用，不先建 `ProcessHandoff` 主表。

**基线：**

- 工具模板（如 SIPOC）可挂流程；无跨流程 SLA/交接关系的可查询图。

**结论：** 非第一批。与 R2-01 round 无硬依赖。

## 5. R1-03 章程、任命与资源

**规格要求：** 补责任/期限/接受/授权；章程仍是流程范围，不变成每项目平行引擎。

**基线：**

- `ProcessCharter`、`GovernanceRole`、`AuthorizationRule` 等已有。  
- 项目资源/预算的**版本化批准文件**链路较薄，R1-05 中 SP-02 等核验缺稳定只读来源。

**结论：** 第一批可在 round/流程卡上**引用**现有章程与角色；深字段补全可跟 R1-05 视图分步做，不阻塞 Slice 1。

## 6. R1-04 十层适用性核对（第一批重点）

**规格要求：** 区分必需/可选/不适用；RPA/技术/案例非全员强制；`round_id`/模型版本过滤证据；GET 不推进层号。

**基线（玩具风险）：**

- `app/services/pilot.py`：`_layer_status` / `startup.evidence_met` 大量 **count > 0** 判定。  
- 第 6 层对 `rpa_bots`、`technology_uses`、`process_cases` 等组合偏「全有才算 met」，与「按流程类型适用性」冲突。  
- `process_evidence._complete_runs`：是否仅统计 `SUCCEEDED` 需产品确认（若改则可能影响现有 seed 演示路径）。

**第一批 Slice 3 最小交付：**

- 配置层 `REQUIRED | OPTIONAL | NOT_APPLICABLE`（JSON 或 `PilotPath` 扩展）。  
- 四结论只读服务读 round + 发布版本 + 样本引用，**不**改 `advance_path` 为八阶段引擎。  
- GET `/pilot/paths/{id}?round_id=` 过滤证据范围（可选）。

**结论：** **可实施**，但须 explicit breaking change 说明与测试。

## 7. R1-05 五因素保障核验视图

**规格要求：** 20 项只读核验；指向原模块；**不**预生成 `PilotTask`；缺源引导补录，不批量勾过。

**基线：**

- 无集中 `/guarantee-checklist` 类 API；数据分散在 charter、governance、training、kpi 等。  
- `web/js/views/shared/tool_sheet.js`：保存 sheet 时若带 `state.toolbox.step`，可能**自动** `POST /tools/.../usage` 且 `outcome=EFFECTIVE`（与 spec §2.2 冲突）→ 归入 **Slice 5**，非 R1-05 resolver。

**结论：** R1-05 **全量 resolver 非第一批**；Slice 5 必须先于或并行于任何「保障 100%」类 UI。

## 8. 与 R2/R0/R5 的交叉（避免重复造轮子）

| 规格项 | 与 R1 关系 | 第一批归属 |
|---|---|---|
| R2-01 round | R1-04/05 的引用锚 | Slice 1 |
| R2-02 KPI 来源/样本 | R1-04「运行有效」、PF-03 | Slice 2a/2b |
| R0-02 流程卡 | 展示 round + verification | Slice 4 |
| R5-01 验收 | Gate 扩展；PASS ≠ 改善达标 | Slice 4 |
| R4-01 异常 | `round_id` | Slice 6 |

## 9. 审定模型需确认的问题

1. 十层第 6 层改为 OPTIONAL/N/A 后，现有 seed 路径是否仍可用于 demo？  
2. KPI 2a 后，种子中「流程 + 天」类 KPI（如 EFF-05）是否一律标 `EXECUTION_CYCLE`（迁移 backfill 策略）？  
3. R1-03 字段补全是否强制进第一批，还是流程卡只读「缺项」即可？  
4. R1-05 是否接受「第一批零 UI，仅 API 占位 + 4 结论投影覆盖部分 SP/OW」？

---

*代码变更以审定通过后的开发计划为准；本文不授权实施。*
