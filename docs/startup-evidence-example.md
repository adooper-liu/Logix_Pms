# 九阶段启动证据：当前实例与判定口径

> 本文用**当前开发库的真实数据**解释“开始使用”页执行层 9 个阶段的判定依据。
> 数据是快照（2026-10-25），会随库里的流程、制度、授权、工时和 KPI 变化；
> 页面每次打开都会重新计算，不是写死的示例。
>
> 页面与页面的完整依赖关系见
> [information-architecture.md](information-architecture.md)。

---

## 1. 当前结果

```text
全局就绪：6/9
首次上线（前 8 阶段）：6/8
当前全局证据阶段：4. 制度与授权设计
下一步：policy
```

“全局”指**全公司范围内所有流程、制度、授权、工时、KPI 的证据汇总**，
不限定某一条试点路径。它与“十层单页”里某条试点路径的 `current_layer` 是两个口径。

---

## 2. 九个阶段的实际证据

| 阶段 | 状态 | 必需证据的实际值 | 判定 |
|---|---|---|---|
| 1 立项定界 | ✅ 已具备 | 有 Owner 的 L3 = 3；治理角色 = 7 | 两项都 >0 |
| 2 战略与现状基线 | ✅ 已具备 | 年度目标 = 3；已挂到流程 = 3；有责任人和目标值 = 1；有现状基线 = 3 | 四项都 >0 |
| 3 流程架构设计 | ✅ 已具备 | L1=7、L2=8、L3=28；已对应 PCF 的 L3=28；岗位=8；RACI 事项=5；权责冲突=0 | 必需项全满足，冲突为 0 |
| 4 制度与授权设计 | ❌ 进行中 | **已生效制度/SOP = 0**；**已生效授权规则 = 0** | 两项必需证据都是 0 |
| 5 流程/表单/工具设计 | ✅ 已具备 | 表单=2；表单/规则/工具绑定=3 | 两项都 >0 |
| 6 工作量测量 | ✅ 已具备 | 已验证标准工时=4；当月产能记录=3 | 两项都 >0 |
| 7 试运行与绩效监测 | ✅ 已具备 | 完整 KPI 卡=16；KPI 数据点=96 | 两项都 >0 |
| 8 评审与固化 | ❌ 进行中 | 已发布模型=1；**已生效制度/SOP = 0** | 模型有了，但制度证据缺失 |
| 9 改善与复制 | ❌ 进行中 | **改善项目=0**；**已应用变更=0**；未闭环治理待办=0 | 前两项必需证据为 0 |

非必需项（只提示、不挡退出门）示例：

- 第 1 阶段：有发起人的试点项目 = 8；
- 第 3 阶段：PCF 对标映射 = 251；
- 第 5 阶段：规则=1、工具绑定=0、已发布模型=1；
- 第 7 阶段：红/黄指标 = 14；
- 第 9 阶段：知识条目=9、近 30 天数据=0。

---

## 3. 为什么“当前”是第 4 阶段，而不是第 8 阶段

系统按顺序找**第一个非 READY、且未被标记“这次先不做”**的阶段：

```text
1 ✅ → 2 ✅ → 3 ✅ → 4 ❌ ← 当前
```

第 8 阶段也不满足，但它排在 4 后面，所以当前阶段是 4，下一步是 `policy`。

时间轴上 5–7 显示蓝勾，是因为它们的证据确实已经满足，不是“已经按顺序走过去了”。
这是真实的全局证据状态，不是强制的线性流程。

---

## 4. 一个完整的依赖例子：第 4 阶段卡住第 8 阶段

第 4 阶段的退出门：

```text
已生效的制度/SOP = 0        ❌
已生效的授权规则 = 0        ❌
```

第 8 阶段的退出门：

```text
已发布的流程模型 = 1        ✅
已生效的制度/SOP = 0        ❌
```

它们共用同一条证据：`effective_documents`。所以现在上传一份 SOP 并让它生效：

1. 第 4 阶段的 `effective_documents` 从 0 → 1；
2. 如果再建一条授权规则并生效，第 4 阶段的 `effective_authorization_rules` 从 0 → 1；
3. 第 4 阶段变成 READY；
4. 第 8 阶段的 `effective_documents` 也变成 1，于是第 8 阶段 READY；
5. 当前阶段直接跳到第 9 阶段（改善与复制），因为 `improvement_projects=0`、`applied_changes=0`。

这就是页面之间“谁是谁的前置、谁触发谁”的真实数据依赖。

---

## 5. 这些数字从哪来

| 证据 | 数据来源 |
|---|---|
| L3 已绑定负责人 | `process_arch`：`level=3 AND owner_user_id IS NOT NULL` |
| 治理角色 | `governance_role`：`is_active=true` |
| 目标 / 已挂流程 / 有责任人 / 有基线 | `strategy_objective`、`objective_process_link` |
| L1/L2/L3、已发布模型 | `process_arch` 按 `level` 计数、`published_model_version>0` |
| 已对应 PCF 的 L3 | `process_benchmark_map` 关联 `process_arch.level=3` |
| 岗位 / RACI / 权责冲突 | `position`、`raci_assignment`、`raci_service.invalid_processes` |
| 已生效制度/SOP | `process_document` + 有效版本状态 `EFFECTIVE` |
| 已生效授权规则 | `authorization_rule.status='EFFECTIVE'` |
| 表单/规则/工具绑定 | `form_definition`、`process_rule`、`node_tool` |
| 已验证工时 / 当月产能 | `work_measurement_standard.status='VERIFIED'`、`capacity_calendar` |
| 完整 KPI 卡 / 数据点 | `kpi_definition`（公式 + 四阈值）、`kpi_record` |
| 改善项目 / 已应用变更 / 治理待办 | `project.source='KPI_THRESHOLD'`、`process_change_request.status='APPLIED'`、`governance_finding.status='OPEN'` |

---

## 6. 全局口径 vs 试点路径口径

| 口径 | 位置 | 是否持久化 | 回答的问题 |
|---|---|---|---|
| 全局证据进度 | 开始使用 / Q7 / 时间轴 | 否，按数据库实时计算 | 全公司这套体系还缺什么 |
| 项目当前层 | 十层单页 `pilot_path.current_layer` | 是，退出门满足后推进 | 这条试点路径做到哪一层 |

开始页的 9 个数字是**全公司口径**，例如“有 Owner 的 L3 = 3”统计的是全库所有 L3，
不是某一条试点流程。十层单页第 4 层的证据是按**试点流程及其上级范围**统计的，
所以两边数字可能不同。

当前开发库显示 `effective_authorization_rules=0`，是因为还没有正式授权规则
（自检创建的规则跑完会被清理）；生产环境只要有一条生效规则，这个值就会变化。

---

## 7. 如何复现

启动应用后：

```bash
# 登录拿 token
curl -s -X POST http://127.0.0.1:8123/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'

# 查看九阶段状态
curl -s http://127.0.0.1:8123/api/v1/start/status \
  -H 'Authorization: Bearer <token>' | python -m json.tool
```

也可以直接调用服务：

```python
from app.core.database import SessionLocal
from app.services import startup

db = SessionLocal()
data = startup.status(db)
for step in data.steps:
    print(step.title, step.status_label)
    for item in step.evidence_items:
        print("  ", item.label, item.value, "必需" if item.required else "可选", item.met)
db.close()
```
