# 三层、Q1–Q8 与页面依赖

本文回答三个问题：

1. 开始页说的“全局”是什么，9 个阶段依据什么判定；
2. 三层 / Q1–Q8 分别映射到哪些页面；
3. 页面之间谁是谁的前置、输入、输出，谁触发谁。

> 当前数据的具体数值见 [startup-evidence-example.md](startup-evidence-example.md)；
> 本文讲规则和结构，那份文档讲某一天库里的实际值。

---

## 1. “全局”是什么

### 1.1 定义

开始页的**全局证据进度**是：

> **全公司范围内所有流程、制度、授权、工时、KPI 的证据汇总，不限定某一条试点路径。**

它不是“某个项目的当前阶段”，也不是“某个部门的进度”，更不是人工打勾的百分比。

计算入口：

```text
web/js/views/start.js  →  GET /api/v1/start/status
app/api/v1/startup.py  →  app/services/startup.py::status
app/services/startup.py::_collect_evidence  →  读各业务表
```

### 1.2 9 个阶段的判定算法

每个阶段有一组**必需证据**（`EVIDENCE_ITEMS`）。单项是否满足：

```python
# 大多数指标：> 0 表示已有
met = value > 0

# 这些指标：0 才是好结果
ZERO_IS_GOOD = {"invalid_processes", "open_findings", "open_authorization_exceptions"}
met = value == 0
```

阶段状态：

```text
READY（已具备）     所有必需证据都满足
IN_PROGRESS（进行中） 至少一项满足，但未全部满足
NOT_STARTED（还没开始）一项都不满足
SKIPPED（这次先不做） 人工标记，不计入就绪
```

当前阶段 = **按顺序第一个不是 READY、也没有被 SKIPPED 的阶段**。
所以它可能停在第 4 阶段，而第 5–7 阶段已经 READY；时间轴会如实显示蓝勾，
不会为了“看起来像线性流程”而把后面的阶段涂灰。

### 1.3 九个阶段的证据规则

| 阶段 | 必需证据 | 主要来源表 |
|---|---|---|
| 1 立项定界 | 有 Owner 的 L3；治理角色 | `process_arch`、`governance_role` |
| 2 战略与现状基线 | 目标；目标已挂流程；目标有责任人和目标值；目标有现状基线 | `strategy_objective`、`objective_process_link` |
| 3 流程架构设计 | L1/L2/L3 节点；已对应 PCF 的 L3；岗位；RACI 事项；权责冲突=0 | `process_arch`、`process_benchmark_map`、`position`、`raci_assignment` |
| 4 制度与授权设计 | 已生效制度/SOP；已生效授权规则 | `process_document` + `process_document_version`、`authorization_rule` |
| 5 流程/表单/工具设计 | 表单；表单/规则/工具绑定 | `form_definition`、`process_rule`、`node_tool` |
| 6 工作量测量 | 已验证标准工时；当月产能记录 | `work_measurement_standard`、`capacity_calendar` |
| 7 试运行与绩效监测 | 完整 KPI 卡；KPI 数据点 | `kpi_definition`、`kpi_record` |
| 8 评审与固化 | 已发布模型；已生效制度/SOP | `process_arch.published_model_version`、`process_document` |
| 9 改善与复制 | 改善项目；已应用变更；未闭环治理待办=0 | `project`、`process_change_request`、`governance_finding` |

### 1.4 全局 vs 试点路径

| 口径 | 位置 | 持久化 | 回答 |
|---|---|---|---|
| 全局证据进度 | 开始使用 / Q7 / 时间轴 | 否，实时计算 | 全公司这套体系还缺什么 |
| 项目当前层 | 十层单页 `pilot_path.current_layer` | 是 | 这条试点路径做到哪一层 |

十层单页第 4 层的证据还会**按试点流程及其上级范围**再统计一次，
所以它和开始页的全公司数字可能不同。两个口径不能互相替代。

---

## 2. 三层 / Q1–Q8 与页面的映射

### 2.1 总表

| 层 | 问题 | 页面 / 视图 | 主要 API | 输入 | 输出 | 下一步 |
|---|---|---|---|---|---|---|
| 地图层 | Q1 要什么 | 战略目标 `strategy` | `/strategy` | 年度经营计划、现状数据 | 目标卡、目标值、现状基线 | Q2 |
| 地图层 | Q2 有什么 | 企业流程地图 `map`、组织与人员 `orgs`、交付物 `deliverables`、工具箱 `toolbox`、监控 `monitor` | `/process-map`、`/org-units`、`/process-documents`、`/tools`、`/monitor` | 现有流程、岗位、制度、工具、KPI | 资产盘点 | Q3 |
| 地图层 | Q3 还缺什么 | 由证据派生，无独立页面 | `/start/status` | 全部必需证据 | 缺口清单 | Q4 / Q7 |
| 骨架层 | Q4 做什么 | 企业流程地图 `map`、PCF 分类框架 `pcf`、1+3+10 引导 | `/process-map`、`/benchmark` | PCF、流程清单、组织边界 | L1–L3 架构、PCF 映射 | Q5 / 项目组合 |
| 骨架层 | Q5 输入什么 | 组织与人员 `orgs`、流程设计器权责 | `/org-units`、`/governance` | 组织树、岗位、关键决策事项 | RACI、岗位边界 | Q6 |
| 执行层 | Q6 用什么 | 流程设计器 `designer`、方法工具箱 `toolbox`、交付物 `deliverables` | `/process-map/nodes`、`/tools`、`/tool-templates` | 控制点、表单字段、工具模板 | 表单/规则/工具绑定 | Q7 |
| 执行层 | Q7 输出什么 | 当前阶段工作区（证据面板） | `/start/status` | 当前阶段真实证据 | 证据清单、缺口 | Q8 |
| 执行层 | Q8 下一步 | 十层单页 `pilot`、项目详情、首次上线确认 | `/pilot`、`/projects/{id}`、`/start/pilot/confirm` | 退出门 | 下一阶段 / 上线确认 | 运营监控、改善 |

### 2.2 页面职责边界

- **开始使用**：只回答“现在缺什么、下一步去哪”，不替代项目详情；
- **企业流程地图**：架构与边界的唯一入口，L1–L3/L4 的归属地；
- **流程项目组合**：改善项目的立项、阶段、步骤和交付物；
- **流程设计器**：把流程、角色、表单、工具、控制点变成可执行模型；
- **运营监控**：KPI、异常、工作量与产能；
- **十层单页**：一条试点路径的十层状态与退出门；
- **驾驶舱 / 运营监控**：看板，不是流程阶段；
- **架构草图 / 设计器 / 工具箱**：工具，不是流程阶段；
- **知识库**：沉淀与复用，不是终点。

---

## 3. 页面之间的依赖逻辑

### 3.1 主因果链

```text
战略目标
  → 企业流程地图（选 L1–L3、定边界）
  → 流程项目组合（为某条 L3 立项）
  → 流程设计器（L4 步骤、表单、工具、控制点）
  → 流程执行（实例、任务、实际工时）
  → 运营监控（KPI、异常、负荷）
  → 改善项目（红黄指标、根因）
  → 变更单 / 新版本
  → 回写流程地图、制度、表单、KPI 基线
```

### 3.2 关键触发关系

| 触发 | 被触发 | 携带的上下文 |
|---|---|---|
| 新建年度目标 | 选择/确认试点 L3 | 目标 ID、目标值、基线 |
| 确认试点 L3 | 创建改善项目 / 十层路径 | 流程 ID、Owner |
| 项目进入设计阶段 | 打开流程设计器 | 项目 ID、流程 ID、当前步骤 |
| 模型发布 V1.0 | 配置流程执行 | 模型版本、流程 ID |
| 异常/红黄 KPI | 创建改善项目 | KPI ID、异常 ID、根因 |
| 变更单批准 | 发布新版本 | 变更 ID、影响分析、回退方案 |
| 新版本生效 | 更新地图/制度/表单/KPI 基线 | 版本号、生效日期 |

### 3.3 已实现的上下文跳转

| 起点 | 动作 | 落点 | 携带的上下文 |
|---|---|---|---|
| 战略目标 | 「看流程」 | 企业流程地图 | 流程编码，地图自动定位并打开流程详情 |
| 企业流程地图 L3 | 「立项」 | 流程项目组合 | 流程 ID、流程名称，项目向导预填 |
| 项目详情 | 「查看流程模型」 | 流程设计器 | 流程 ID |
| 项目详情 | 「去流程执行」 | 流程执行 → 配置 | 流程 ID，直接打开该流程的配置页签 |
| 流程设计器 | 「去流程执行」 | 流程执行 → 配置 | 当前流程 ID |
| 运营监控 KPI | 「转改善」 | 改善项目详情 | KPI ID，服务端生成改善草稿 |
| 设计器变更（已批准） | 「发布新版本」 | 模型发布 | 变更单 ID，发布时引用 |

### 3.4 行业最佳实践对应的逻辑

| 实践 | 在系统里的落点 |
|---|---|
| APQC PCF 作为共同语言 | L1–L3 以 PCF 为骨架，L4/L5 本地建模；PCF ID 做稳定键 |
| 每个 L3 一个 Owner | `process_arch.owner_user_id`，启动阶段 1 验证 |
| RACI 唯一 A | `raci_assignment` + `raci_service.invalid_processes`，阶段 3 验证 |
| 分级授权 | A/B/C/D 规则、金额/风险阈值、例外路径，阶段 4 验证 |
| 证据门禁 | ISO 9001 的“输入/决策/记录/异常/变更”落成 `EVIDENCE_ITEMS` |
| 标准工时是能力基线 | 只允许 `VERIFIED` 进入产能；页面注明不用于个人考核 |
| PDCA / 轻量 DMAIC | 异常 → 改善项目 → 验证 → 标准更新 → 复制 |
| 受控变更与版本 | 变更单、影响分析、回退方案、V1.x 发布 |
| 单一事实源 | 项目进度=Project/ProjectStep；全局证据=startup；试点当前层=pilot_path |

### 3.5 反模式

- 把 7 个模块排成一条“推进线”：它不是同一对象的时间序列，且重复导航；
- 用“记录数”冒充“就绪度”：有表不等于有证据；
- 把“跳过”当“完成”：跳过只记未验证；
- 两套项目进度各算各的：24 步项目和 9 阶段落地项目必须明确口径；
- 在驾驶舱堆模块入口：驾驶舱只回答“现在关注什么、下一步做什么”。

---

## 4. 代码落点

| 能力 | 文件 |
|---|---|
| 全局证据与 9 阶段 | `app/services/startup.py` |
| 开始页三栏八问 / 时间轴 | `web/js/views/start.js`、`web/css/views.css` |
| 驾驶舱角色首页 / 当前推进 | `app/services/dashboard.py`、`web/js/views/dashboard.js` |
| 十层单页 / 第 4 层 | `app/services/pilot.py`、`web/js/views/pilot.js` |
| 授权矩阵 | `app/services/authorization.py`、`web/js/views/authorization.js` |
| 项目 5 阶段 24 步 | `app/services/workflow.py`、`app/api/v1/projects.py` |

---

## 5. 验证方式

```bash
# 九阶段状态
curl -s http://127.0.0.1:8123/api/v1/start/status \
  -H 'Authorization: Bearer <token>' | python -m json.tool

# 十层路径
curl -s http://127.0.0.1:8123/api/v1/pilot/paths \
  -H 'Authorization: Bearer <token>' | python -m json.tool
```

当前库的 6/9 实例、第 4 与第 8 阶段的依赖示例，见
[startup-evidence-example.md](startup-evidence-example.md)。
