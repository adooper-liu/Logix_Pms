# 场景驱动知识库：差距清单与实施方案

> 依据：`C:\Users\adoop\Downloads\result.md`、`五阶段工作流原型.html`、
> `流程知识库_场景驱动版原型.html`，以及当前仓库的 knowledge / workflow / deliverables 实现。
>
> 本文只做方案，不改代码。目标是把「资源网格」升级为
> **按场景匹配、带使用证据、能回流验证的能力网络**，并与五阶段工作流打通。

---

## 1. 结论与边界

### 1.1 目标形态

```text
用户带着问题来
  → 选场景/痛点（或自由描述）
  → 系统按「场景匹配 + 使用证据 + 工作流位置」推荐
  → 用户查看适用条件、使用证据、关联工具/制度
  → 用后回填效果
  → 高频有效 → 晋升最佳实践；长期未用/未复核 → 待复核/归档
```

### 1.2 三条不做的事

1. **不把「标准制度」继续混在知识库里。**
   仓库已经有 `process_document`（`app/models/process_document.py`）承载
   SOP / 表单 / 检查表，含版本、生效日期、适用范围、审批状态。
   知识库只保留可参考、可改编的案例 / 模板 / 方法 / 工具指南。
2. **不复制「工具」定义。**
   工具的唯一事实源是 `tool` 表（`app/models/tool.py`）和
   `app/services/tool_finder.py`。知识库里的「工具」只保存使用指南并引用
   `tool_code`，不重复维护工具的步骤、适用场景和模板。
3. **不用「浏览量」冒充「适用度」。**
   `download_count` 继续作为阅读量统计，但不参与推荐排序。
   推荐依据改为场景匹配度 + 使用证据（有效次数/使用次数）+ 工作流位置。

---

## 2. 现状盘点（代码事实）

| 能力 | 当前实现 | 与目标差距 |
|---|---|---|
| 知识条目模型 | `app/models/knowledge.py::KnowledgeItem`：title/type/methodology/summary/content/process_id/project_id/tool_code/author/download_count/created_at | 缺场景、适用/不适用条件、输入输出、维护人、验证日期、审核状态、版本 |
| 类型 | `KnowledgeType`：CASE / TEMPLATE / BEST_PRACTICE / STANDARD | 缺 METHOD / TOOL；BEST_PRACTICE 应是「晋升结果」而非并列类型；STANDARD 应移出 |
| 标签 | `KnowledgeTag` 关联表，SQL 层筛选 | 标签是文件属性，不是用户任务；不能直接充当场景 |
| 列表接口 | `GET /knowledge`：type/methodology/tool_code/tag/keyword/sort=recent\|hot | 缺 scenario/stage/step 筛选；缺 effect 排序；缺证据统计 |
| 推荐 | 只有底部的 `POST /tools/match`（`app/services/tool_finder.py`） | 只推工具，不推知识；没有场景匹配、没有证据权重、没有工作流位置 |
| 新建 | `POST /knowledge` 直接创建，ManagerUser | 没有草稿/审核/验证门禁，容易垃圾入库 |
| 详情 | 只统计阅读次数 | 没有「谁用过、效果如何」 |
| 工作流 | `GET /workflow/steps/{step_no}/recommendations` 已返回推荐工具与模板（`app/services/tool_template.py::step_recommendations`） | 不返回知识；步骤弹窗只能去工具箱/模板库 |
| 标准制度 | `ProcessDocument` + `deliverables` 的「流程标准文件」页签已完整 | 知识库仍有 `STANDARD` 条目，语义重复 |
| 前端 | `web/js/views/knowledge.js`：类型页签 + 卡片网格 + 底部分页 + 底部「按问题找工具」 | 模板/案例/最佳实践平铺；搜索权重低；没有推荐区、证据区、场景区 |

### 2.1 现有种子数据

`app/seed/corpus_data.py::KNOWLEDGE` 目前有 9 条：

- CASE：采购需求提报复盘、客诉闭环案例
- TEMPLATE：BPR 七步法、RACI、试点设计
- BEST_PRACTICE：VSM、ADKAR、Kaizen
- STANDARD：流程 KPI 平衡计分卡设计规范（1 条）

这些条目大多已有 `tool_code`，可直接映射到工具与工作流阶段；但没有使用证据和验证日期。
迁移时不能把它们标成「已验证」，应标为「待复核」。

---

## 3. 目标数据模型

### 3.1 `knowledge_item` 扩展字段

在现有表上增加（全部可空，便于平滑迁移）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | String(16) | 扩展为 `CASE` / `TEMPLATE` / `METHOD` / `TOOL`；保留旧值 `BEST_PRACTICE`、`STANDARD` 兼容 |
| `status` | String(16), index | `DRAFT` / `IN_REVIEW` / `PUBLISHED` / `VERIFIED` / `ARCHIVED` |
| `owner_user_id` | FK app_user, SET NULL | 维护人；与 `author` 展示名并存 |
| `claim` | Text | 主张：解决什么具体问题 |
| `applicable_when` | Text | 适用条件（补充场景标签的自由文本） |
| `not_applicable_when` | Text | 不适用/反证条件 |
| `input_conditions` | Text | 输入条件 |
| `steps_summary` | Text | 操作步骤要点（正文仍保留完整内容） |
| `outputs` | Text | 输出物 |
| `version` | Integer, default 1 | 内容版本 |
| `last_verified_at` | DateTime, nullable | 最后一次验证日期；为空即「待复核」 |
| `review_due_at` | Date, nullable | 下次复核日期；建议 `last_verified_at + 12 个月` |
| `verified_by_user_id` | FK app_user, SET NULL | 验证人 |
| `is_best_practice` | Boolean, default false | 晋升标志；不再作为独立类型 |
| `promoted_at` | DateTime, nullable | 晋升时间 |

保留 `download_count`（阅读统计）和 `created_at`，但推荐排序不读取它们。

### 3.2 新表

#### 3.2.1 `knowledge_scenario`（场景字典）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `code` | String(32) unique | `FLOW` / `CYCLE` / `ERROR` / `RACI` / `COST` / `STANDARD` |
| `name` | String(64) | 流程混乱 / 周期太长 / 差错返工多 / 责任不清 / 成本过高 / 缺少标准 |
| `description` | String(200) | 场景解释 |
| `sort_order` | Integer | 展示顺序 |
| `is_active` | Boolean | |

首版固定 6 个场景，后续由管理员扩展。场景是「用户任务」，标签仍是文件属性，
两者不复用。

#### 3.2.2 `knowledge_scenario_link`

| 字段 | 说明 |
|---|---|
| `knowledge_id` | FK knowledge_item, CASCADE |
| `scenario_id` | FK knowledge_scenario, CASCADE |
| `weight` | Float, default 1.0，主场景可设 1.5 |

唯一约束 `(knowledge_id, scenario_id)`。

#### 3.2.3 `knowledge_workflow_link`

| 字段 | 类型 | 说明 |
|---|---|---|
| `knowledge_id` | FK CASCADE | |
| `stage_no` | Integer | 1–5 |
| `step_no` | String(8), nullable | 为空表示阶段级推荐 |
| `is_primary` | Boolean | 是否该步骤的首选知识 |

唯一约束 `(knowledge_id, stage_no, step_no)`。
这样工作流步骤可以精准推送，而不需要在知识条目里硬编码 24 个步骤。

#### 3.2.4 `knowledge_usage`（使用证据）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `knowledge_id` | FK CASCADE, index | |
| `project_id` | FK project, SET NULL | 在哪个项目里使用 |
| `step_no` | String(8), nullable | 用在哪个工作流步骤 |
| `used_by_user_id` | FK app_user, SET NULL | 谁用过 |
| `used_at` | DateTime, index | 使用时间 |
| `outcome` | String(16) | `EFFECTIVE` / `PARTIAL` / `INEFFECTIVE` |
| `note` | Text | 效果说明 |
| `evidence_url` | String(500) | 证据链接（可选） |

索引：`(knowledge_id, used_at)`、`(project_id)`。

> 不把 `used_count/effective_count` 冗余到 knowledge_item。
> 统计走聚合查询；当前数据量（<1000 条）足够快。若后续成为瓶颈，再加物化计数。

#### 3.2.5 审核记录

首版用 `status` + `audit_service.record()` 记录「提交/通过/驳回」即可。
如果后续需要完整审核历史，再增加 `knowledge_review` 表（P2）。

### 3.3 枚举调整

`app/models/enums.py::KnowledgeType`：

```python
class KnowledgeType(str, Enum):
    CASE = "CASE"
    TEMPLATE = "TEMPLATE"
    METHOD = "METHOD"
    TOOL = "TOOL"
    BEST_PRACTICE = "BEST_PRACTICE"  # 兼容旧数据；新数据不再使用
    STANDARD = "STANDARD"  # 兼容旧数据；知识库 UI 不再展示
```

新增 `KnowledgeStatus`：

```python
class KnowledgeStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"
    VERIFIED = "VERIFIED"
    ARCHIVED = "ARCHIVED"
```

`STANDARD` 的处理见第 6 节迁移方案。

---

## 4. 后端服务与 API

### 4.1 推荐服务 `app/services/knowledge_match.py`（新增）

复用而不是重写：

- 中文粗分词：把 `app/services/tool_finder.py::_tokens` 提取为
  `app/services/text_match.py::tokens()`，`tool_finder` 改为引用它。
- 工具匹配：继续使用 `tool_finder.match()`。
- 工作流步骤：读取 `WorkflowTemplate`。

推荐打分（可解释）：

```text
score =
    3.0 × 命中场景数
  + 1.0 × 文本命中 token 数（title/summary/claim/applicable_when/content）
  + 2.0 × 精确命中 step_no
  + 1.0 × 命中 stage_no
  + 0.8 × status == VERIFIED
  + 0.8 × is_best_practice
  + 2.0 × Wilson 下界(有效次数, 使用次数)
  - 1.0 × 已过复核日期
```

- 使用 **Wilson 下界**而不是 `有效/使用` 直接相除，避免「1 次使用、1 次有效 = 100%」
  排到最前。
- 只返回 `PUBLISHED` / `VERIFIED`；`IN_REVIEW` 仅对 MANAGER+ 可见；`ARCHIVED` 不返回。
- 返回 `matched_on`（命中了哪些场景/词/步骤）和证据统计，前端可以解释「为什么推荐」。
- 结果统一为 `kind = knowledge | tool`：
  - `knowledge`：知识条目；
  - `tool`：由 `tool_finder.match()` 命中的工具，并附上关联知识/模板。
  这样原型里的「工具卡」不是复制出来的假数据，而是真实工具箱记录。

### 4.2 API 变更

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge/scenarios` | 场景字典 |
| POST | `/knowledge/recommend` | 入参 `problem` / `scenario_codes` / `stage_no` / `step_no` / `limit`；返回知识+工具统一推荐 |
| GET | `/knowledge` | 增加 `scenario`、`stage_no`、`step_no`、`status`、`sort=match\|effect\|recent`；保留 `recent/hot` 兼容 |
| GET | `/knowledge/meta` | 场景、类型、状态、统计（总数/已验证/待复核/待审核） |
| POST | `/knowledge/{id}/usage` | 记录一次使用证据（WriteUser） |
| GET | `/knowledge/{id}/usage` | 查看证据列表 |
| POST | `/knowledge/{id}/submit` | DRAFT → IN_REVIEW（维护人/Manager） |
| POST | `/knowledge/{id}/review` | IN_REVIEW → VERIFIED / PUBLISHED；写 `last_verified_at`、`review_due_at` |
| POST | `/knowledge/{id}/promote` | VERIFIED → `is_best_practice=true`（Manager） |
| POST | `/knowledge/{id}/archive` | → ARCHIVED（Manager） |
| GET | `/workflow/steps/{step_no}/recommendations` | 响应增加 `knowledge` 列表，复用现有端点 |

现有 `GET /knowledge/{id}`、`PATCH`、`DELETE`、`POST /read` 保持向后兼容。
`create_knowledge` 的权限建议从 `ManagerUser` 调整为 `WriteUser`（OWNER 也能提交草稿），
但只有 Manager 能审核发布；这需要同步更新 `tests/test_auth.py`。

### 4.3 响应字段（推荐结果）

```json
{
  "kind": "knowledge",
  "id": 4,
  "code": null,
  "title": "RACI 权责矩阵模板",
  "type": "TEMPLATE",
  "type_label": "模板",
  "summary": "定义每个节点的唯一 A 与 R/C/I...",
  "score": 92,
  "matched_on": ["场景：责任不清", "文本：权责", "步骤：S1-4"],
  "scenarios": [{"code": "RACI", "name": "责任不清"}],
  "used_count": 23,
  "effective_count": 19,
  "effectiveness_rate": 82.6,
  "is_best_practice": true,
  "last_verified_at": "2026-09-10T00:00:00+00:00",
  "review_overdue": false,
  "owner": "流程管理部",
  "tool_code": "RACI",
  "links": {"detail": "/knowledge/4", "tool": "/toolbox?tool=RACI"}
}
```

---

## 5. 前端改造

### 5.1 `web/js/views/knowledge.js` 布局

严格按原型的三段式，但复用现有设计令牌和组件：

```text
页面头：知识库 / 按场景找工具 + 统计（已收录 / 已验证 / 待复核 / 待审核）
① 场景匹配区（首屏主入口）
   - 6 个痛点按钮（单选）
   - 自由描述输入框 + 「按痛点匹配」主按钮
   - 推荐结果：3 条，显示匹配分、适用场景、已用/有效、维护人、验证日期
   - 动作：查看详情 / 应用到当前步骤
② 全部资源
   - 类型：全部 / 案例 / 模板 / 方法 / 工具
   - 排序：匹配度 / 使用效果 / 最近更新
   - 卡片：标题、摘要、适用场景、有效率、已用次数、维护人、验证/待复核/最佳实践徽标
   - 不再显示「浏览量」作为主要指标
③ 标准制度入口
   - 不展示 STANDARD 卡片；改为「制度中心 →」链接到
     `deliverables?tab=document`（需给 deliverables 增加 tab URL 状态）
侧栏：
   - 与五阶段工作流打通（5 个阶段入口，带该阶段知识数量）
   - 固定字段说明
   - 入库审核清单
```

### 5.2 交互与 URL 状态

沿用 `urlParams()` / `setUrlState()`：

| 参数 | 作用 |
|---|---|
| `scenario` | 场景 code，可逗号分隔 |
| `q` | 自由描述问题 |
| `type` | 类型筛选 |
| `stage` / `step` | 工作流阶段/步骤筛选 |
| `sort` | `match` / `effect` / `recent` |
| `page` | 分页 |

- 顶栏搜索（`router.js::onSearch`）在 knowledge 视图下写入 `q` 并触发推荐。
- 场景按钮点击后立即请求 `/knowledge/recommend`，结果区展开；没有选择时展示全部资源。
- 推荐项「应用到当前步骤」：如果 URL 带 `step`，记录一次 `knowledge_usage`；
  否则提示先从工作流步骤进入。

### 5.3 新建与审核

新建弹窗至少要求：

- 名称、类型、主张（解决什么问题）
- 适用场景（多选）
- 适用条件 / 不适用条件
- 输入条件 / 步骤要点 / 输出物
- 使用证据（首次可填「谁用过、什么效果」，也可后续回填）
- 维护人、关联工作流步骤、关联工具编码

保存为 `DRAFT`，提交后进入 `IN_REVIEW`；Manager 在「待审核」筛选中通过/驳回。
未通过审核的条目不出现在普通列表和推荐中。

### 5.4 详情弹窗

- 顶部：类型、状态、最佳实践/待复核徽标、版本、最后验证日期。
- 固定字段区：主张、适用/不适用、输入、步骤要点、输出物、关联工具、关联步骤。
- 使用证据区：使用次数、有效次数、有效率、最近 5 条证据记录。
- 「记录一次使用」表单：结果（有效/部分有效/无效）、项目、步骤、说明、证据链接。
- Manager 额外看到：通过审核、驳回、晋升最佳实践、归档。

### 5.5 与工作流打通

- 扩展 `app/services/tool_template.py::step_recommendations`：
  - 在 `StepRecommendationOut` 增加 `knowledge: List[KnowledgeRecommendationOut]`。
  - 查询 `knowledge_workflow_link` 精确命中 `step_no`，再回退到 `stage_no`，
    按推荐分排序取前 3。
- `web/js/views/workflow.js::paintStepRecommendations`：
  - 在现有「推荐工具与预制模板」下方增加「本步骤推荐知识」；
  - 每条显示类型、适用条件、有效率、查看详情；
  - 「查看详情」在弹窗内打开知识详情，或跳转到
    `knowledge?scenario=...&step=...`，不要丢失当前步骤上下文。
- 工作流步骤清单卡片显示「推荐知识 N」，让用户不用点开就知道有内容。

---

## 6. 数据迁移与存量内容处理

### 6.1 Alembic 迁移顺序

1. `add_knowledge_scenario_and_workflow_links`
   - `knowledge_scenario`、`knowledge_scenario_link`、`knowledge_workflow_link`、
     `knowledge_usage`
2. `extend_knowledge_item_for_evidence`
   - 第 3.1 节字段；`status` 默认 `PUBLISHED`，`version` 默认 1
3. `backfill_knowledge_scenarios_and_links`
   - 插入 6 个场景；
   - 按标签/工具/标题把现有 9 条知识映射到场景；
   - 按 `tool_code -> Tool.stage_no` 生成阶段级工作流关联；
   - `last_verified_at = NULL`，`review_due_at = created_at + 12 个月`，
     `status = PUBLISHED`（因为存量没有可核验的使用证据）。
4. `deprecate_knowledge_standard_type`
   - 对 `type='STANDARD'` 的条目逐条人工判定：
     - 强制、绑定流程 → 迁到 `process_document`（标准文件中心），知识条目置 `ARCHIVED`；
     - 跨流程的设计指导 → 改为 `METHOD` 或 `PUBLISHED` 的知识条目；
   - 不在迁移里自动删除内容，先归档再人工确认。

> `knowledge_item.type` 和 `status` 都是 String 列，不需要数据库 ENUM 迁移；
> 但 Pydantic 枚举与种子数据要同步。

### 6.2 存量 9 条的初步映射

| 条目标题 | 现类型 | 建议类型 | 场景 | 关联阶段 |
|---|---|---|---|---|
| BPR 实施七步法标准模板 | TEMPLATE | TEMPLATE | FLOW / STANDARD | 1 |
| 价值流图 VSM 绘制与解读手册 | BEST_PRACTICE | METHOD | CYCLE / COST | 2 |
| 采购需求提报重组项目复盘 | CASE | CASE | CYCLE / ERROR | 1–3 |
| RACI 权责矩阵模板 | TEMPLATE | TEMPLATE | RACI / FLOW | 1 |
| ADKAR 变革管理推进指南 | BEST_PRACTICE | METHOD | FLOW / RACI | 4 |
| 精益改善周 Kaizen 操作手册 | BEST_PRACTICE | METHOD | COST / CYCLE | 4 |
| 客户投诉闭环流程优化案例 | CASE | CASE | ERROR / CYCLE | 2–4 |
| 流程 KPI 平衡计分卡设计规范 | STANDARD | METHOD（或迁制度） | STANDARD | 5 |
| 试点设计模板与回滚预案 | TEMPLATE | TEMPLATE | STANDARD / FLOW | 4 |

最终以人工复核为准；迁移脚本只做可解释的默认映射。

---

## 7. 推荐与审核规则

### 7.1 状态流转

```text
DRAFT --提交--> IN_REVIEW --通过--> VERIFIED
                    |                  |
                    |--驳回--> DRAFT   |--晋升--> is_best_practice=true
                                       |--过期/长期未用--> PUBLISHED / ARCHIVED
PUBLISHED --复核通过--> VERIFIED
```

- `VERIFIED` 必须有 `last_verified_at` 和验证人。
- `review_due_at` 过期 → UI 标「待复核」，推荐分扣分，但不必立刻下线。
- 超过 12 个月无人使用 → 进入「归档候选」列表，由 Manager 确认归档。
- `is_best_practice` 只在 VERIFIED 且使用证据达到阈值（建议使用 ≥5 次、
  有效率 ≥70%）时允许晋升。

### 7.2 证据与反证

新建/编辑必须填写「不适用条件」才能提交审核。这是原型里「主张→反证→证据→裁决」
的最小落地：没有反证条件，就无法判断知识边界，也就无法防止误用。

---

## 8. 分阶段实施与人日

| 阶段 | 范围 | 估算 | 验收 |
|---|---|---:|---|
| **P0 数据与推荐底座** | 迁移、场景表、使用证据表、推荐服务、`/knowledge/recommend`、列表筛选/排序、存量映射 | 8–10 人日 | 选定场景能返回可解释的推荐；证据变化能改变排序；`alembic check` 无漂移 |
| **P1 页面重构与审核闭环** | knowledge 页面三段式、详情固定字段、使用回填、草稿→审核→验证、待审核筛选、URL 状态 | 7–9 人日 | 新建条目未审核不可见；详情能看到证据；刷新/分享恢复场景与筛选 |
| **P2 工作流打通与制度中心** | 扩展步骤推荐响应、工作流弹窗推荐知识、制度中心链接、deliverables tab URL、归档候选 | 5–7 人日 | 工作流步骤内可直接看到并打开推荐知识；STANDARD 不再出现在知识库 |
| **P3 运营化增强** | 最佳实践晋升、自动待复核提醒、使用效果统计、全文检索（pg_trgm/tsvector） | 3–5 人日 | 12 个月未用自动进入归档候选；推荐解释可审计 |

> **2026-10-25 落地记录**：P3 已实现最佳实践晋升（VERIFIED + 使用 ≥5 次 + 有效率 ≥70%）、
> `/knowledge/effect-stats` 使用效果统计、治理扫描新增 `KNOWLEDGE_REVIEW_OVERDUE` /
> `KNOWLEDGE_ARCHIVE_CANDIDATE`（含站内通知）。全文检索按第 10 节阈值（5,000 条）暂缓，
> 当前仍用 2 字滑窗 + 场景/步骤结构化筛选。
>
> **同日补全**：推荐卡与详情支持「用到当前步骤」，使用证据写入 `knowledge_usage.step_no`；
> 详情展示关联阶段/步骤/工具；新建表单可精确关联到具体步骤；知识库侧栏阶段入口显示知识数；
> 使用证据增加 10 分钟短期去重；提醒任务由 `scripts/scan_reminders.py` 供外部 cron 调用。

总计约 23–31 人日。若只做最小可用版，P0 + P1 的核心（不做审核历史、不做自动归档）
约 12–15 人日。

---

## 9. 验证方案

### 9.1 后端测试

新增 `tests/test_knowledge_scenarios.py`：

- 场景字典返回 6 个场景；
- 选定 `RACI` 场景，RACI 模板排在第一，且 `matched_on` 包含场景；
- 使用证据从 0/0 变为 3/2 后，推荐分与排序发生变化；
- 归档/未审核条目不进入普通推荐；
- 新建条目默认 DRAFT，未审核不出现在列表；
- Manager 审核通过后可见，`last_verified_at` 写入；
- VIEWER 不能新建/审核，OWNER 可新建草稿但不能审核；
- 工作流步骤推荐响应包含 `knowledge` 字段。

同时更新：

- `tests/test_api.py::test_knowledge_*`：兼容现有 `recent/hot` 与标签筛选；
- `tests/test_auth.py`：create 权限调整后的断言；
- `tests/test_frontend_structure.py`：knowledge 仍导出 `renderKnowledge`，保留分页。

### 9.2 迁移测试

- `alembic upgrade head` 后：
  - 6 个场景存在；
  - 存量知识都有 `status`；
  - `STANDARD` 条目的处理结果可审计；
  - `knowledge_usage` 为空，不伪造证据；
- `alembic check` 无漂移。

### 9.3 前端端到端

在 `scripts/verify_frontend.py` 增加：

1. 进入知识库，首屏出现「我先想解决什么？」场景区；
2. 点击「责任不清」，出现推荐列表，且 RACI 模板在结果中；
3. 点击推荐项，详情弹窗显示适用条件、使用证据、维护人、验证日期；
4. 记录一次使用后，详情中的使用次数 +1；
5. 新建条目 → 提交审核 → Manager 审核通过 → 普通列表可见；
6. 从工作流步骤弹窗看到「本步骤推荐知识」，点击后仍保留 step 上下文；
7. 知识库不再出现 STANDARD 卡，制度入口跳到 `deliverables?tab=document`；
8. URL 带 `scenario=RACI&step=S1-4` 刷新后恢复场景与步骤。

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
| 中文全文检索没有搜索引擎 | 首版用现有 2 字滑窗 + 场景/步骤结构化筛选；条目超过 5000 条再上 pg_trgm/tsvector |
| 证据可能被刷 | Wilson 下界 + 同一用户/项目短期去重 + Manager 审核；不把单条证据当结论 |
| 存量 STANDARD 内容归属 | 先人工逐条判定，迁移脚本只做默认建议，不自动删内容 |
| BEST_PRACTICE 是否保留为类型 | 建议降为 `is_best_practice` 标志，类型只保留 CASE/TEMPLATE/METHOD/TOOL |
| 新建权限是否开放给 OWNER | 建议开放「创建草稿」，审核仍限 MANAGER+；否则知识库仍然只有流程管理科能贡献 |
| 是否新建独立「制度中心」页面 | 首版不新建，直接复用 `deliverables` 的「流程标准文件」页签，避免第二套标准模型 |
| 阅读量是否保留 | 保留为统计字段，但不再作为推荐依据，UI 文案改为「查阅」 |

---

## 11. 代码落点清单

| 层 | 文件 | 改动 |
|---|---|---|
| 模型 | `app/models/knowledge.py` | 扩展字段、新关联表/证据表 |
| 枚举 | `app/models/enums.py` | `KnowledgeType` 扩展、`KnowledgeStatus` |
| 迁移 | `alembic/versions/*_knowledge_scenario_*.py` | 表结构、场景字典、存量映射 |
| 服务 | `app/services/knowledge_match.py`（新增） | 场景匹配、Wilson 证据分、统一推荐 |
| 服务 | `app/services/text_match.py`（新增） | 从 `tool_finder._tokens` 提取共享分词 |
| 服务 | `app/services/tool_finder.py` | 改为引用共享分词 |
| 服务 | `app/services/tool_template.py` | `step_recommendations` 增加 knowledge |
| API | `app/api/v1/knowledge.py` | scenarios/recommend/usage/review/promote/archive |
| Schema | `app/schemas/knowledge.py` | 新字段、推荐 DTO、证据 DTO |
| Schema | `app/schemas/tool_template.py` | `StepRecommendationOut.knowledge` |
| 前端 | `web/js/views/knowledge.js` | 三段式重构、推荐、证据、审核、URL 状态 |
| 前端 | `web/js/views/workflow.js` | 步骤弹窗展示推荐知识 |
| 前端 | `web/js/views/deliverables.js` | 支持 `?tab=document` 深链 |
| 前端 | `web/js/core/router.js` | knowledge 搜索参数改为 `q`，保留 `keyword` 兼容 |
| 种子 | `app/seed/corpus_data.py` | 补充场景/工作流关联/证据示例 |
| 测试 | `tests/test_knowledge_scenarios.py` 等 | 见第 9 节 |

---

## 12. 一句话总结

> 知识库的价值不在「有多少条」，而在「用户当下能不能找到对的那个」。
> 落地关键不是再加一层卡片，而是把 **场景、证据、验证状态、工作流位置**
> 变成可查询、可排序、可回流的数据；标准制度回归 `process_document`，
> 工具回归 `tool`，知识库只做「场景匹配 + 使用证据 + 最佳实践晋升」。
