# 通用 Gate 5 责任闭合能力设计

**状态：待确认**

## 1. 意图

建设适用于任意正式 L3 流程的 Gate 5「组织、岗位与责任」能力：既能核验责任是否闭合，也能由有权限的治理人员写入责任配置，并保留版本、组织范围、有效期和责任接受证据。

L3-032 只作为验收样本，不作为系统常量、唯一业务范围或独立责任台账。

目标问题：

```text
任意正式 L3
→ 已发布模型与 L4 活动
→ 流程 Owner
→ 每个 L4 的唯一 A
→ 执行岗位与账号
→ 审批角色与账号
→ 替补与升级责任人
→ 组织/岗位/账号有效性
→ 责任接受 E2 证据
→ Gate 5 readiness
```

## 2. 目标

1. 对任意正式 L3 流程计算 Gate 5 readiness，而不是只识别 L3-032。
2. 默认依据已发布模型；运行中的实例和未发布草稿不被责任配置悄悄替换。
3. 允许 ADMIN/MANAGER 写入责任配置；OWNER 只能在现有流程授权范围内操作，VIEWER 只读。
4. 复用已有 `RaciAssignment` 表达 A/R/C/I，复用 `NodeAssignment` 表达节点执行配置。
5. 新增一类通用责任接受证据，明确谁接受、接受什么、针对哪个模型版本、何时失效。
6. 将“配置存在”与“责任已接受”分成 E1/E2，不能把岗位名称、系统角色或流程级 RACI 自动升级为 Gate 5 通过。
7. readiness 输出逐个 L4 的 blockers、warnings、evidence grade、责任来源和下一步，不自动写入 Gate assessment，也不自动通过 Gate 5。

## 3. 非目标

- 不为 L3-032 创建专用责任台账或专用 API。
- 不自动把现有 `owner` 文本、流程级 RACI 或岗位名称转成账号责任。
- 不自动创建用户、岗位、治理角色、组织或责任接受记录。
- 不在本切片推进 Gate 6、真实运行、试点或上线。
- 不发布当前未发布模型，不把 Gate 5 readiness 当作业务 Owner 签字。
- 不重做现有 RACI、岗位覆盖、执行分派页面；先提供通用后端契约和可验证写入能力。

## 4. 术语与证据等级

| 术语 | 解释 |
|---|---|
| 配置事实 | 系统中已有责任关系或分派配置；通常为 E1 |
| 接受事实 | 对指定责任和模型版本有责任人确认并留有时间/有效期；为 E2 |
| 运行事实 | 真实任务由指定人员办理并形成轨迹；属于 E3，不在本切片生成 |
| 当前模型 | 已发布 `ProcessModelVersion`；默认作为 Gate 5 的核验基准 |
| 活动 | 当前模型中的 L4 活动，优先通过版本化 `NodeActivityLink` 识别 |
| 责任范围 | `PROCESS_OWNER`、`ACCOUNTABLE`、`EXECUTOR`、`APPROVER`、`BACKUP`、`ESCALATION` |

## 5. 现有对象的职责边界

### 5.1 `ProcessArch`

- `level=3` 的正式流程是核验入口。
- `owner_user_id` 是流程 Owner 的账号来源；`owner` 仅为展示兼容字段。
- 若只有 `owner` 文本而没有 `owner_user_id`，输出阻断，不推断账号。

### 5.2 `ProcessModelVersion` / `NodeActivityLink`

- 默认核验 `status=PUBLISHED` 且与 `published_model_version` 一致的模型。
- `NodeActivityLink` 的 `REALIZES`/`PART_OF` 是活动映射权威来源。
- 仅有 `ProcessNode.process_arch_id` 的兼容映射输出 `LEGACY_MAPPING` 警告；不能作为严格 Gate 5 PASS 的版本化活动映射证据。
- 指定未发布 `model_version_id` 只能用于管理员预览，不得写成正式 Gate 5 证据，也不得用于创建运行责任快照。

### 5.3 `RaciAssignment`

- 活动级唯一 A 使用 `activity_id`，不可用流程级 `activity_id=NULL` 代替。
- `role_id` 必须指向有效治理角色；角色全部成员必须有效且可归属于同一有效岗位，复用 `position_coverage.role_position` 的完整成员校验语义。
- R、C、I 作为协作信息输出；不把 RACI-R 自动当成执行账号。
- 写入沿用现有 RACI 唯一 A 约束和服务校验，不建立第二套 A 关系。

### 5.4 `NodeAssignment`

继续作为当前执行配置的唯一来源，保存：

- `role`：候选系统角色；
- `org_unit_id`：执行组织范围；
- `default_assignee_user_id`：默认执行账号；
- `due_hours` / `escalation_hours`：已有执行配置，Gate 5 只核验，不代填业务时限；
- `escalation_user_id`：升级账号。

为满足 Gate 5 责任闭合，增加：

- `backup_assignee_user_id`：备用责任人；
- `effective_from` / `effective_to`：该节点责任配置的有效期。

不把 `due_hours` 误当作责任接受或 SLA 业务事实。

### 5.5 新增责任接受证据

新增通用 `ProcessResponsibilityAcceptance`（名称可在实现阶段按仓库命名规则调整），用于记录：

- `process_id`；
- `model_version_id`，必须指向正式发布模型才能作为 Gate 5 E2；
- `node_key`，流程 Owner 接受时为空，L4 责任接受时必填；
- `scope`：`PROCESS_OWNER` / `ACCOUNTABLE` / `EXECUTOR` / `APPROVER` / `BACKUP` / `ESCALATION`；
- `subject_user_id`：被接受的责任人；
- `accepted_by_user_id`：实际确认账号；
- `accepted_at`；
- `valid_until`；
- `evidence_note`；
- `status`：`ACCEPTED` / `WITHDRAWN` / `EXPIRED`。

同一模型版本、节点、责任范围和责任账号只保留一个当前有效接受记录；历史记录不覆盖。

该表是“接受证据”对象，不复制 RACI 或 NodeAssignment 的配置正文。

## 6. Gate 5 readiness 规则

### 6.1 流程级规则

阻断条件：

- 对象不是正式 L3，或流程为草稿；
- 没有已发布模型；
- 流程 Owner 没有 `owner_user_id`；
- Owner 账号不存在、停用、无有效组织/岗位范围；
- Owner 没有当前模型版本的 `PROCESS_OWNER` 接受记录。

警告条件：

- 只有展示用 Owner 文本；
- 已发布模型存在但版本绑定来源是兼容旧映射。

### 6.2 每个 L4 规则

每个当前发布模型中的 L4 必须单独输出结果。

阻断条件：

- 没有版本化活动映射；
- 没有唯一活动级 A；
- A 对应治理角色停用、无成员、成员不在同一有效岗位，或成员账号停用；
- 没有节点级 `NodeAssignment`；
- 没有有效执行岗位或组织范围；
- 没有默认执行账号，或默认账号停用/不在指定组织范围；
- 审批活动没有可核验的审批角色/账号；
- 默认执行账号与审批账号冲突，导致申请人可直接审批自己的申请；
- 没有有效备用责任人；
- 没有有效升级责任人；
- 当前责任配置已过有效期；
- 关键责任范围缺少 E2 接受记录。

条件通过 / 警告：

- 只有兼容主活动指针，没有版本化映射；
- 有配置但责任接受即将到期；
- 有 RACI-A 但没有对应执行账号；
- 有执行账号但没有独立审批账号；
- 使用组织范围配置而不是明确账号，需限定在候选队列而不能宣称个人已接受。

### 6.3 汇总状态

- `PASS`：流程 Owner 和所有 L4 的必要责任配置闭合，关键范围均有当前 E2 接受证据。
- `CONDITIONAL`：配置闭合但存在可由有权人接受的明确风险，例如兼容映射或接受记录临近失效。
- `BLOCKED`：任一硬阻断未关闭。

readiness 只返回计算结果，不自动调用 `assess_gate`、不修改 Gate 状态。

## 7. 写入 API 设计

### 7.1 核验

```text
GET /api/v1/processes/{process_id}/gate5/readiness
    ?model_version_id=<optional-preview-version>
```

默认使用已发布模型。响应包含：

- `process_id`、`process_code`、`model_version_id`、`model_version`；
- `status`、`status_label`；
- `evidence_grade`；
- `process_owner`；
- `activities[]`；
- `blockers[]`、`warnings[]`、`next_actions[]`；
- `configuration_writable`；
- `business_accepted`。

### 7.2 责任配置

```text
PUT /api/v1/processes/{process_id}/gate5/assignments/{node_key}
POST /api/v1/processes/{process_id}/gate5/acceptances
POST /api/v1/processes/{process_id}/gate5/owner
```

写入规则：

- ADMIN/MANAGER 可写；OWNER 只能写其有权维护的流程；VIEWER 拒绝。
- 写入前锁定流程，确认目标模型仍是当前已发布版本；版本变化返回 409。
- 配置写入只更新 `ProcessArch.owner_user_id`、已有 `RaciAssignment`、`NodeAssignment` 和新接受证据，不复制对象。
- 每次写入记录审计；不自动发布模型、不创建实例、不改变 Gate assessment。
- 写入接口支持撤回接受记录，但不能删除历史接受证据。
- 接受接口只允许责任人本人或有权治理人员确认；账号、组织、岗位和有效期必须重新核验。

### 7.3 原子性

一组“活动 A + 执行配置 + 备用/升级 + 接受记录”的提交必须在一个事务中完成；任一校验失败整体回滚，不能留下半套责任配置。

## 8. 权限与安全边界

- 组织可见性复用 `org_access`；不能通过 API 写入不可见组织的责任。
- 不能将 ADMIN/MANAGER 这类系统角色直接当作治理 A 或执行岗位。
- 不能接受停用账号、停用岗位、停用治理角色或跨组织账号。
- 责任接受必须绑定模型版本，发布模型变化后旧接受自动降为过期/需重确认，不删除历史。
- 预览未发布模型只返回差距，不产生正式责任接受证据。

## 9. 验收方式

### 通用能力测试

使用临时合成 L3/L4 数据覆盖：

- 任意 L3 可核验，不依赖 L3-032 编码；
- 发布模型缺失、未发布模型预览、版本变化；
- 流程 Owner 文本但无账号；
- 唯一 A 缺失、重复 A、流程级 RACI 冒充活动 A；
- 停用用户、停用岗位、失效组织、跨组织账号；
- 执行账号、备用账号、升级账号配置；
- 审批人与申请人冲突；
- 接受记录缺失、过期、撤回、版本不一致；
- 写入事务整体回滚和审计记录；
- 重复写入幂等/冲突保护。

### L3-032 验收样本

只读取 L3-032 当前状态，验证它能被通用服务识别为存在以下缺口：

- Owner 账号未绑定；
- 六个 L4 当前没有节点分派；
- RACI 尚未闭合到活动级唯一 A；
- 备用和升级责任未配置；
- 责任接受记录不存在。

本次样本验证不写入 L3-032 的责任事实，不把样本变成业务批准。

## 10. 实施边界

本设计涉及三个独立交付单元，应分别保持可测试：

1. **责任接受模型与迁移**：新增接受证据及 NodeAssignment 扩展字段。
2. **通用 Gate 5 readiness 与写入服务/API**：任意 L3 可用，复用现有 RACI/组织/执行服务。
3. **样本验证与后续界面**：本次只做 L3-032 验收样本和后端契约，不默认新增专用页面。

前两项完成后，Gate 5 能力才算建立；第三项只是证明通用能力没有被样本编码绑死。
