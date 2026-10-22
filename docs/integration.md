# ERP / OA 集成说明

系统支持**出站 Outbox + Webhook** 和**入站 HMAC Webhook** 两个方向：
出站由业务写操作写入投递表，管理入口统一投递；入站由 ERP/OA 反向启动流程实例
或完成任务，使用独立密钥签名并保证幂等。

## 1. 配置端点

在「流程执行 → 集成」页签（MANAGER+）新增端点：

| 字段 | 说明 |
|---|---|
| 编码 | 全局唯一，如 `ERP-PROD` |
| 名称 / 类型 | 用于识别；类型可选 WEBHOOK / ERP / OA |
| URL | 必须 `http://` 或 `https://`；生产建议 HTTPS |
| 签名密钥 | 可选；配置后用 HMAC-SHA256 对请求体签名 |
| 订阅事件 | 逗号分隔；留空表示订阅全部；`*` 也表示全部 |
| 启用 | 停用后不再产生新的投递 |

## 2. 事件类型

| 事件 | 触发点 |
|---|---|
| `instance.started` | 流程实例启动 |
| `instance.suspended` | 流程实例挂起 |
| `instance.resumed` | 流程实例恢复 |
| `task.created` | 生成待办任务 |
| `task.claimed` | 任务被认领 |
| `task.assigned` | 任务被改派 |
| `task.escalated` | 任务超期自动升级并改派 |
| `task.completed` | 任务完成 |
| `instance.completed` | 实例完成 |
| `instance.cancelled` | 实例取消 |
| `exception.created` | 异常登记 |
| `exception.updated` | 异常更新（含状态/责任人变化） |

### 请求体

```json
{
  "event": "instance.started",
  "payload": { "...": "事件数据" },
  "delivery_id": 12,
  "timestamp": "2026-10-21T12:00:00.000000Z"
}
```

主要 payload 字段：

```text
instance.*   instance_id, code, process_id, process_name, project_id,
             status, current_node_key, started_by_id, started_by_name, started_at
task.*       task_id, instance_id, instance_code, process_name, node_key,
             name, task_type, status, assignee_user_id, assignee_name,
             created_at, due_at, escalated_at, escalated_to_user_id,
             escalated_to_name
exception.*  exception_id, code, title, severity, status, process_id,
             project_id, owner_user_id, owner, due_at
```

## 3. 请求头与签名

```text
Content-Type: application/json
User-Agent: Logix-PMS/1.0
X-Logix-Event: instance.completed
X-Logix-Delivery: 12
X-Logix-Signature: sha256=<hex>        # 仅配置了 secret 时出现
```

签名算法：

```python
import hashlib, hmac

expected = hmac.new(
    secret.encode("utf-8"),
    raw_body.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
assert hmac.compare_digest(expected, received_signature.split("=", 1)[1])
```

接收方必须使用**原始请求体**计算签名，不要先反序列化再序列化。

## 4. 投递与重试

- 「运行待发送」调用 `POST /api/v1/integrations/deliveries/run`。
- 成功（2xx）：状态 `SUCCESS`，记录响应码与送达时间。
- 失败：`attempts + 1`；未满 3 次保持 `PENDING`，按 1/2 分钟退避；
  满 3 次置 `FAILED`。
- 管理端可对任意未送达记录手动重试（`POST /integrations/deliveries/{id}/retry`），
  重试会清零尝试次数。
- 投递是**至少一次**语义，接收方应按 `X-Logix-Delivery` 做幂等。

当前没有内置定时器；生产环境可用 cron / 任务队列定时调用 run 接口。

## 5. 安全建议

1. 生产端点必须使用 HTTPS；密钥通过环境变量/密钥管理注入，不要写进代码。
2. 配置最小订阅集合，避免把无关事件发给外部系统。
3. 接收方校验签名 + 时间戳，拒绝重放过旧的请求。
4. URL 由 MANAGER+ 配置，系统不限制内网地址——这是为了对接企业内 ERP/OA；
   如果部署在不可信环境，应在网关层做出口白名单。
5. 集成投递记录包含业务数据，需按企业数据分级要求控制访问。

## 6. 入站 Webhook（ERP/OA → Logix PMS）

在「流程执行 → 集成 → 入站 Webhook」新建入口。每个入口有独立密钥，密钥只在
创建或轮换时显示一次；调用地址为：

```text
POST /api/v1/integrations/inbound/{code}
```

| 配置项 | 说明 |
|---|---|
| 编码 | 调用路径的一部分，全局唯一 |
| 限定流程 | 可留空（全部流程）；选择后只能操作该流程，且必须允许「启动流程」 |
| 服务账号 | 入站操作以该账号执行；必须是 MANAGER / ADMIN，且启用 |
| 允许动作 | `start_instance` / `complete_task`，至少一个 |
| 状态 | 停用后所有入站请求返回 403 |

### 请求头与签名

```text
Content-Type: application/json
X-Logix-Timestamp: 1790000000          # Unix 秒，允许 ±5 分钟
X-Logix-Signature: sha256=<hex>        # HMAC-SHA256(secret, timestamp + "." + raw_body)
```

```python
import hashlib, hmac, json, time
import requests

ts = str(int(time.time()))
raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
sig = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
requests.post(
    f"https://pms.example.com/api/v1/integrations/inbound/{code}",
    data=raw,
    headers={
        "Content-Type": "application/json",
        "X-Logix-Timestamp": ts,
        "X-Logix-Signature": "sha256=" + sig,
    },
)
```

必须使用**原始请求体**计算签名；时间戳超出窗口、签名不匹配或缺少请求头均返回 401。

### 启动流程实例

```json
{
  "event_id": "ERP-PO-20261022-001",
  "action": "start_instance",
  "process_id": 12,
  "project_id": 3,
  "variables": {"source": "ERP", "order_no": "PO-001"},
  "assignments": {"n1": 7}
}
```

- `event_id` 必填，在同一个入站入口内唯一；重复请求返回第一次的结果并带
  `"duplicate": true`，不会重复启动实例。
- 只有成功事件写入幂等表；失败请求不占用 `event_id`，修正后可直接重试。
- `process_id` 在入口未限定流程时必填。
- `assignments` 可选：按节点 key 指定处理人 user_id；不传则按节点分派/公共队列规则。

### 完成任务

```json
{
  "event_id": "ERP-PO-20261022-001-approve",
  "action": "complete_task",
  "task_id": 88,
  "form_data": {"approved": "是", "comment": "ERP 自动审批通过"},
  "variables": {"erp_status": "APPROVED"}
}
```

- 完成任务会走与页面相同的校验、通知和后续分支规则。
- `next_node_key` 可选；多分支且规则未命中时必填。
- 任务必须属于入口限定的流程（如果配置了限定流程）。

### 响应

```json
{
  "status": "ok",
  "action": "start_instance",
  "duplicate": false,
  "instance_id": 42,
  "instance_code": "PI-2026-002",
  "task_id": null,
  "task_status": null
}
```

入站事件可在 `GET /api/v1/integrations/inbound-events` 查看（MANAGER+）。

## 7. 已知边界

- 已支持出站事件与入站 HMAC Webhook；仍未提供 ERP 拉取接口；
- 没有事件 schema 版本号；
- 没有死信队列可视化之外的自动补偿（可在投递记录里手动重试）；
- 没有按事件类型配置不同的重试策略。
