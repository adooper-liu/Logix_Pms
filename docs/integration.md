# ERP / OA 集成说明

系统采用 **Outbox + Webhook** 的出站集成方式：业务写操作只把事件写入投递表，
不阻塞主请求；由管理入口统一投递，失败自动退避重试。

> 当前只实现**出站**事件。ERP/OA 反向调用（入站 Webhook / 拉取接口）尚未实现。

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
| `task.created` | 生成待办任务 |
| `task.claimed` | 任务被认领 |
| `task.assigned` | 任务被改派 |
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
             name, task_type, status, assignee_user_id, assignee_name, created_at
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

## 6. 已知边界

- 只有出站事件，没有入站 Webhook / ERP 拉取；
- 没有事件 schema 版本号；
- 没有死信队列可视化之外的自动补偿（可在投递记录里手动重试）；
- 没有按事件类型配置不同的重试策略。
