# 方法论工具箱：问题驱动改造方案

> 依据：`方法论工具箱_问题驱动版原型.html`、当前 `toolbox` 视图与 `tool` 模型，
> 以及刚完成的知识库场景化改造。
>
> 本文只做方案，不改代码。目标是把「33 个工具的分类目录」升级为
> **按问题匹配、带决策依据和验证标准的工作台**，并与知识库、五阶段工作流形成双向连接。

---

## 1. 结论与边界

### 1.1 推荐方案：保留两个入口，明确分工（方案 B）

不建议把知识库和工具箱合并成一个「方法中心」。原因：

1. **工具已经是单一事实源。** `tool` 表承载工具的五步操作、模板、常见误用、
   适用阶段，并被设计器、模板库、工作流步骤契约引用。合并会让这套模型被重复或膨胀。
2. **知识库已经通过 `tool_code` 引用工具。** 知识条目类型 `TOOL` 就是「工具使用指南」，
   可以直接作为工具的案例/证据层。两页不是重复，而是「参考层」与「执行层」。
3. **合并会增加而不是降低认知负担。** 用户的问题不是「为什么有两个入口」，
   而是「工具箱把匹配入口埋得太深」。先修入口和卡片信息，比合并两个数据模型收益更大。

| 入口 | 回答的问题 | 主要内容 |
|---|---|---|
| 知识库 | 我要找参考 | 案例、模板、方法、最佳实践、使用证据 |
| 工具箱 | 我要解决一个问题 | 工具适配度、难度、周期、为什么用、验证标准、五步操作、模板 |

两页通过 `tool_code` 双向跳转：

```text
知识库条目（type=TOOL / tool_code=RACI）  ⇄  工具箱工具详情（code=RACI）
```

### 1.2 三个不做的事

1. **不复制工具。** 知识库里不再新建「工具定义」；所有工具步骤、模板、误用仍以 `tool` 为准。
2. **不把四象限删掉。** 诊断/设计/落地/监控是工具的天然属性，保留为辅助筛选，
   但不再占据主入口。
3. **不新增第二套证据模型。** P0 先从关联的 `TOOL` 知识条目读取使用证据；
   若后续需要工具级独立使用记录，再把 `knowledge_usage` 统一抽象为共享证据表。

---

## 2. 现状盘点（代码事实）

| 能力 | 当前实现 | 与目标差距 |
|---|---|---|
| 工具模型 | `app/models/tool.py::Tool`：code/name/alias/category/stage_no/purpose/when_to_use/steps/template_ref/pitfalls/sort_order | 缺适用场景、不适用条件、前置条件、验证标准、难度、周期、维护人、版本、验证日期 |
| 匹配 | `app/services/tool_finder.py`：同义词 3.0 + 文本 1.0 + 阶段 0.5，返回原始分 | 没有场景加权、没有证据加权、没有适配度归一化、没有「为什么推荐」 |
| 分类 | `category`：DIAGNOSE / DESIGN / DEPLOY / MONITOR；`stage_no` 1–5 | 分类是工具属性，当前却承担主筛选；需要降为辅助 |
| API | `GET /tools/grouped`、`GET /tools`、`GET /tools/{code}`、`POST /tools/match` | 缺场景字典、适配度、难度/周期/验证标准、关联知识 |
| 前端 | `web/js/views/toolbox.js`：页头 + 分类页签 + 底部「按问题找工具」+ 静态快捷问题 | 匹配入口在底部；卡片只有「阶段 N / 5 步」；无决策信息 |
| 工作流 | `GET /workflow/steps/{step_no}/recommendations` 已返回推荐工具与模板 | 只给工具名/使用要求，缺「为什么用/验证标准」 |
| 知识库 | 已场景化，`knowledge_item.tool_code` 可反向关联工具 | 工具箱详情尚未挂「相关案例/模板/知识」 |

### 2.1 现有匹配逻辑

`tool_finder.match()` 的打分：

```text
score =
    3.0 × 同义词命中
  + 1.0 × 工具自身文本被问题 token 命中
  + 0.5 × 工具阶段 == 用户指定阶段
```

优点是可解释、离线、无依赖；缺点是：

- 没有场景概念（用户点「审批太多」和「责任不清」时，同一工具的相对优先级无法体现）；
- 没有证据权重（用过 30 次有效的工具和从未用过的工具同分）；
- 原始分不是 0–100，前端只能显示「8.4」这种用户无法解释的数字。

---

## 3. 目标数据模型

### 3.1 `tool` 扩展字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `scenario_links` | 关联表（见 3.2） | 适用痛点，复用知识库的 `knowledge_scenario` 字典 |
| `not_applicable_when` | Text | 什么情况下不该用（反证） |
| `prerequisites` | Text | 前置条件：数据、人员、授权、系统 |
| `verification_standard` | Text | 怎么判断用对了（必须可验证） |
| `difficulty` | String(8) | `LOW` / `MEDIUM` / `HIGH` |
| `typical_duration` | String(32) | 如「3 天」「2–3 周」「持续」 |
| `owner_user_id` | FK app_user, SET NULL | 维护人 |
| `version` | Integer, default 1 | 内容版本 |
| `last_verified_at` | DateTime, nullable | 最后验证日期；为空即「待复核」 |
| `review_due_at` | Date, nullable | 下次复核日期 |
| `is_active` | Boolean, default true | 归档/停用 |

现有 `purpose` 保持「解决什么问题」，`when_to_use` 作为「适用条件」的完整说明，
新增字段只补决策缺口，不重复已有内容。

### 3.2 `tool_scenario_link`（场景关联）

| 字段 | 说明 |
|---|---|
| `tool_id` | FK tool, CASCADE |
| `scenario_id` | FK knowledge_scenario, CASCADE |
| `weight` | Float，默认 1.0；主场景可 1.5 |

唯一约束 `(tool_id, scenario_id)`。

复用 `knowledge_scenario` 的六个场景（流程混乱 / 周期太长 / 差错返工多 /
责任不清 / 成本过高 / 缺少标准），不再维护第二套痛点字典。

### 3.3 证据

P0 **不新增 `tool_usage` 表**。工具的使用证据优先从关联的
`knowledge_item(type=TOOL, tool_code=该工具)` 的 `knowledge_usage` 聚合。
这符合「同一个概念只保留一个实现」。

如果后续确认工具需要独立于知识的现场使用记录（例如没有对应知识条目的工具），
再评估把 `knowledge_usage` 抽象为共享的 `usage_evidence(entity_type, entity_id)` 表；
这是一次独立的重构，不混在本次改造里。

### 3.4 枚举

新增 `ToolDifficulty`：

```python
class ToolDifficulty(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
```

`ToolDifficulty` 中文标签由后端下发（`/tools/meta`），前端不维护映射。

---

## 4. 匹配与推荐

### 4.1 复用与扩展

- 保留 `app/services/text_match.py::tokens()` 和 `tool_finder.SYNONYMS`；
- 在 `tool_finder` 中增加场景与证据权重，或新建 `tool_match.py` 组合
  `tool_finder` 的文本分与场景/证据分，避免把两套逻辑混在一个函数里。

推荐新增 `app/services/tool_match.py`：

```text
raw =
    3.0 × 同义词命中
  + 1.0 × 文本 token 命中
  + 2.5 × 场景命中
  + 0.5 × 阶段命中
  + 2.0 × Wilson 下界(有效次数, 使用次数)
  + 0.3 × 已验证
  - 0.5 × 复核过期
```

归一化到 0–100：

```text
适配度 = min(99, round(raw / MAX_RAW * 100))
```

`MAX_RAW` 在服务层集中定义，避免前端/后端各算一套。

返回：

```json
{
  "tool": {...},
  "score": 92,
  "match_level": "high",
  "matched_on": ["场景：审批太多", "文本：审批", "步骤：1.2"],
  "why": "周期长的根因往往在交接与等待……",
  "verification_standard": "找到≥3个非增值等待环节",
  "difficulty": "MEDIUM",
  "difficulty_label": "中",
  "typical_duration": "2–3 周",
  "usage": {"used": 23, "effective": 19, "rate": 82.6}
}
```

### 4.2 排序与筛选

- 主排序：适配度；
- 可选排序：难度从低到高、验证周期从短到长、使用频率从高到低；
- 四象限（category）作为可多选辅助筛选；
- 阶段（stage_no）作为可选筛选；
- 支持 `stage_no` / `step_no` 上下文加权，供工作流步骤调用。

### 4.3 API 变更

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tools/meta` | 增加 `difficulty_labels`、场景字典、排序说明 |
| GET | `/tools/grouped` | 返回扩展字段（场景、难度、验证标准、证据摘要） |
| POST | `/tools/match` | 入参增加 `scenario_codes`、`category_filters`、`step_no`；返回适配度与决策字段 |
| GET | `/tools/{code}` | 返回固定字段、关联知识、关联工作流步骤 |
| GET | `/tools/{code}/knowledge` | 关联的案例/模板/工具指南（可选） |
| GET | `/workflow/steps/{step_no}/recommendations` | 推荐工具增加 `why`、`verification_standard`、`difficulty`、`typical_duration` |

现有 `ToolOut` 增加字段，`ToolBrief` 保持轻量；不要让列表接口返回完整 `steps`。

---

## 5. 前端改造

### 5.1 页面结构

```text
页头：方法论工具箱 / 问题驱动匹配
① 我遇到了什么问题？（首屏主入口）
   - 输入框 + 「匹配工具」按钮
   - 快捷痛点 chips（可配置，来自场景字典）
② 匹配结果
   - 结果头：当前问题、匹配数、排序下拉
   - 工具卡：适配度进度条、难度、周期、阶段、为什么用它、验证标准、
     效果证据、维护人、关联知识
   - 动作：查看详情、用这个工具（有步骤上下文时）/ 加入当前工作流
③ 全部工具（可折叠）
   - 四象限辅助筛选（多选）
   - 按适配度 / 难度 / 周期 / 使用频率排序
侧栏：
   - 与五阶段工作流打通（5 个阶段入口）
   - 求真校验说明
```

匹配区从底部移到首屏；底部的「按问题找工具」卡片删除，避免同一功能出现两次。

### 5.2 工具卡

卡片固定信息（不再以「阶段 + 5 步」为主）：

- 工具名 + 象限标签
- 适配度（0–100，进度条）
- 难度（低/中/高）、预计周期
- 为什么用它（来自 `purpose` + 场景匹配理由）
- 验证标准（`verification_standard`）
- 效果证据（已用/有效/有效率，来自关联知识）
- 维护人、最后验证日期
- 关联工作流阶段 / 关联知识数量

### 5.3 工具详情

固定字段：

```text
名称 | 象限 | 适用阶段 | 适用场景 | 不适用条件
前置条件 | 标准步骤 | 输出物 | 模板/工具指引
预计周期 | 难度 | 验证标准 | 使用证据
维护人 | 版本 | 最后验证日期 | 关联知识
```

动作：

- 查看关联知识/案例/模板；
- 在知识库中查看（`knowledge?tool=RACI` 或 `knowledge?q=...`）；
- 有步骤上下文时「应用到当前步骤」。

### 5.4 URL 状态

| 参数 | 作用 |
|---|---|
| `q` | 当前问题描述 |
| `scenario` | 场景 code |
| `category` | 工具象限，可逗号分隔 |
| `stage` | 阶段筛选 |
| `step` | 从工作流进入时的步骤上下文 |
| `sort` | fit / difficulty / duration / usage |
| `open` | 直接打开某个工具的详情 |

新增 `state.toolbox` 的 `q/scenario/categories/stage/step/sort/open`，并沿用
`urlParams()` / `setUrlState()`。

### 5.5 与知识库的双向跳转

- 工具箱详情底部：`相关案例/模板/知识` → `knowledge?tool=<code>`；
- 知识库详情：如果 `tool_code` 存在，保留「查看关联工具」；
- 知识库列表按 `tool_code` 筛选时，工具箱接收 `tool` 参数并直接打开详情。

### 5.6 与五阶段工作流

现有 `/workflow/steps/{step_no}/recommendations` 已经返回工具和模板。扩展：

- 每个推荐工具增加「为什么用」与「验证标准」两行；
- 提供「在工具箱查看」按钮，跳转 `toolbox?step=<step_no>&tool=<code>`；
- 工具详情可以反查它被哪些步骤契约引用（`StepContract.tool_codes`）。

---

## 6. 数据迁移与存量内容

### 6.1 Alembic 迁移

1. `extend_tool_for_problem_matching`
   - `tool` 增加 3.1 字段；
   - 新建 `tool_scenario_link`；
   - `difficulty` 默认 `MEDIUM`，`version` 默认 1，`is_active` 默认 true。
2. `backfill_tool_scenarios`
   - 从 `knowledge_scenario` 读取六个场景；
   - 按 `corpus.TOOLS` 中新增的 `scenarios` 字段建立关联；
   - 没有显式配置的工具，按 `knowledge_item(type=TOOL, tool_code)` 的已有场景反推。
3. `backfill_tool_decision_fields`
   - 用 `corpus.TOOLS` 的 `difficulty` / `typical_duration` / `verification_standard` /
     `prerequisites` / `not_applicable_when` 填充；
   - 未提供值的工具保留 NULL，UI 显示「待补充」，不伪造标准。

### 6.2 存量 33 个工具的内容

需要为 `app/seed/corpus.py::TOOLS` 增补字段。建议分批：

- P0 先补 10 个高频工具（SIPOC、VSM、PARETO、5Why、鱼骨图、RACI、
  决策矩阵、试点计划、A3、控制图）；
- 其余工具使用默认值，并在 UI 标「待补充」；
- 不一次性编造 33 个工具的验证标准，避免知识库变成「看起来很完整」的假数据。

---

## 7. 审核与证据

工具条目已经存在于 `tool` 表，且由流程管理科维护。P0 不新增「新建工具」入口；
沿用现有的管理入口（如需新增，走 Manager+ + 审核）。工具内容变更时：

- `version` +1；
- `last_verified_at` 清空或标「待复核」；
- 关联知识/模板不受影响。

如果后续开放工具提交，再引入与知识库一致的
「主张 → 反证 → 证据 → 裁决」审核状态。

---

## 8. 实施阶段与人日

| 阶段 | 范围 | 估算 | 验收 |
|---|---|---:|---|
| **P0 数据与匹配底座** | `tool` 扩展字段、`tool_scenario_link`、匹配服务与 API、10 个高频工具内容 | 5–7 人日 | 选定痛点后返回可解释的适配度；四象限可筛选；证据能影响排序 |
| **P1 页面重构** | 首屏匹配、工具卡决策信息、四象限侧栏、排序、URL 状态 | 4–6 人日 | 用户首屏能说出「该用什么、为什么、怎么验证」 |
| **P2 工作流与知识库打通** | 步骤推荐扩展、工具详情关联知识、双向跳转 | 3–4 人日 | 工作流步骤内直接看到工具和验证标准；知识库/工具箱互跳 |
| **P3 证据与审核增强** | 工具级使用证据、工具提交审核、复核提醒 | 4–6 人日 | 证据变化能改变推荐；过期工具标待复核 |

> **2026-10-25 落地记录**：P3 的复核提醒已落地——`Tool.review_overdue` 下发到工具箱卡片与详情，
> 治理扫描新增 `TOOL_REVIEW_OVERDUE`（含站内通知）。使用证据继续复用关联 `TOOL` 知识的
> `knowledge_usage`（第 3.3 节方案），未新增第二套证据表；工具提交审核仍沿用现有管理入口。
>
> **同日补全**：工具卡/详情显示关联知识数与适用场景；从工作流步骤进入工具箱时，
> 可通过关联知识记录「用到当前步骤」的使用证据；工具复核提醒与知识提醒共用
> `scripts/scan_reminders.py` 的 cron 入口。

P0 + P1 约 9–13 人日，即可交付可用的「问题驱动工具箱」；
P2 完成后才真正形成「知识库 ↔ 工具箱 ↔ 工作流」的闭环。

---

## 9. 验证方案

### 9.1 后端测试

新增 `tests/test_toolbox_matching.py`：

- `GET /tools/meta` 返回难度标签与六个场景；
- `POST /tools/match` 选「审批太多，周期太长」→ VSM、分级授权、帕累托进入前列；
- 适配度在 0–100，且带 `matched_on` 解释；
- 场景筛选、四象限筛选、阶段筛选生效；
- 证据（关联知识使用记录）增加后，工具排序或分数变化；
- `/workflow/steps/2.1/recommendations` 的工具包含 `why`、`verification_standard`。

更新：

- `tests/test_api.py` 现有 tools 路由测试；
- `tests/test_frontend_structure.py`：toolbox 仍导出 `renderToolbox`，新增静态守卫
  （匹配入口在首屏、四象限为辅助筛选）。

### 9.2 前端端到端

在 `scripts/verify_frontend.py` 扩展：

1. 进入工具箱，首屏出现「我遇到了什么问题？」与快捷痛点；
2. 点「审批太多，周期太长」→ 出现匹配结果，VSM 在结果中；
3. 卡片显示适配度、难度、周期、验证标准、证据；
4. 四象限筛选生效；
5. 点工具详情 → 显示前置条件、不适用条件、验证标准、关联知识；
6. 从工作流步骤弹窗点工具 → 带 `step` 上下文进入工具箱；
7. URL 带 `q=VSM` / `scenario=FLOW` 刷新后恢复匹配。

最终命令：

```bash
python scripts/check.py
python scripts/verify_frontend.py http://127.0.0.1:8123
alembic check
```

---

## 10. 风险与待决事项

| 风险/决策 | 建议 |
|---|---|
| 知识库与工具箱是否合并 | 推荐方案 B：明确分工 + 双向跳转；不合并数据模型 |
| 四象限是否保留 | 保留，但降为辅助筛选，可多选 |
| 工具证据从哪来 | P0 复用关联 `TOOL` 知识条目的 `knowledge_usage`；需要工具级独立记录时再做共享证据表 |
| 33 个工具的验证标准谁维护 | 流程管理科维护；P0 只补高频工具，其余标「待补充」，不编造 |
| 匹配算法是否引入向量检索 | 首版沿用同义词 + 2 字滑窗 + 场景/证据加权；工具量小，暂不需要 embedding |
| 是否需要“使用计划” | 可先做「应用到当前步骤」；真正的计划生成需要项目/步骤上下文，放到 P2 |

---

## 11. 代码落点清单

| 层 | 文件 | 改动 |
|---|---|---|
| 模型 | `app/models/tool.py` | 扩展决策字段、场景关联关系 |
| 枚举 | `app/models/enums.py` | `ToolDifficulty` |
| 迁移 | `alembic/versions/*_tool_problem_matching.py` | 字段、关联表、存量回填 |
| 服务 | `app/services/tool_match.py`（新增） | 场景/证据加权、适配度归一化、解释 |
| 服务 | `app/services/tool_finder.py` | 保留文本/同义词匹配，供 `tool_match` 复用 |
| 服务 | `app/services/tool_template.py` | 步骤推荐增加 why/verification |
| API | `app/api/v1/tools.py` | meta、grouped、match、detail 扩展 |
| Schema | `app/schemas/tool.py` | 新字段与推荐 DTO |
| 前端 | `web/js/views/toolbox.js` | 首屏匹配、卡片、四象限、URL 状态 |
| 前端 | `web/js/views/workflow.js` | 步骤弹窗展示 why/验证标准 |
| 前端 | `web/js/views/knowledge.js` | 工具跳转上下文（已有 openTool） |
| 种子 | `app/seed/corpus.py` | 10 个高频工具补决策字段 |
| 测试 | `tests/test_toolbox_matching.py` 等 | 见第 9 节 |

---

## 12. 一句话总结

> 工具箱不应是「33 个工具的漂亮目录」，而应是**「带着问题来、带着答案走」的匹配工作台**。
> 四象限保留为辅助筛选，主入口让位给问题匹配；每个工具必须回答
> **该不该用、为什么用、怎么验证用对了**。知识库负责参考层，工具箱负责执行层，
> 两者通过 `tool_code` 双向连接，而不是合并成一个更重的方法中心。
