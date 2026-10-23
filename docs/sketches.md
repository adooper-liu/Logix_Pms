# 架构草图（独立 draw.io 白板）

> 定位：**自由画布**，用于流程架构草图、汇报示意、跨系统关系图。
> 它**不是**流程设计器，也不是可执行 BPMN 模型；不参与发布和流程执行。

## 1. 为什么单独做

流程设计器使用 bpmn-js，保存的是 BPMN 2.0 语义模型，能发布给执行引擎运行。
draw.io 是通用图表工具，保存 mxGraph/mxfile，适合自由布局和复杂示意图，
但没有 BPMN 执行语义。

两者混在一起会出现两套模型、互相覆盖和语义漂移，所以明确分层：

| 能力 | 流程设计器 | 架构草图 |
| --- | --- | --- |
| 编辑器 | bpmn-js | draw.io |
| 数据 | BPMN 2.0 XML + DI | mxfile XML |
| 是否可执行 | 是（发布后） | 否 |
| 版本治理 | 草稿/评审/发布/回滚 | 保存即更新 |
| 典型用途 | 可运行流程 | 架构草图/汇报图 |

## 2. 数据与接口

表 `sketch`：

- `title` / `description`
- `process_id` / `project_id`：可选关联，仅用于归类
- `mxfile_xml`：draw.io save 事件返回的原始 XML
- 创建人、创建时间、更新时间

接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/sketches/meta` | 返回 draw.io embed 地址 |
| GET/POST | `/api/v1/sketches` | 列表 / 新建 |
| GET | `/api/v1/sketches/{id}` | 详情（含 mxfile XML） |
| PATCH | `/api/v1/sketches/{id}` | 修改信息或保存 XML |
| DELETE | `/api/v1/sketches/{id}` | 删除（MANAGER+） |

## 3. draw.io 嵌入方式

前端通过 iframe 加载 `DRAWIO_EMBED_URL`，使用 draw.io embed 的 `postMessage` 协议：

1. iframe 发出 `{ event: 'init' }`
2. 页面回发 `{ action: 'load', xml: mxfile_xml, autosave: 1 }`
3. 用户保存时 iframe 发出 `{ event: 'save', xml }`（自动保存为 `event: 'autosave'`）
4. 页面 `PATCH /sketches/{id}` 保存 XML
5. `{ event: 'exit' }` 关闭弹窗

注意：`proto=json` 模式下，两个方向的消息体都是 **JSON 字符串**（`JSON.stringify` 后的
`postMessage`），不是对象。前端同时兼容对象形式，便于自托管实例或协议升级。

默认配置：

```text
DRAWIO_EMBED_URL=https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1&saveAndExit=1
```

## 4. 自托管建议

外部 embed 服务会把草图内容发送到 diagrams.net。生产环境建议自托管：

```bash
docker run -d --name drawio -p 8080:8080 jgraph/drawio
```

然后把 `DRAWIO_EMBED_URL` 指向：

```text
http://drawio.internal:8080/?embed=1&proto=json&spin=1&libraries=1&saveAndExit=1
```

自托管后需要按企业网络策略配置反向代理、HTTPS 和访问控制。

## 5. 边界

- 草图不参与 BPMN 校验、发布和流程执行。
- 目前保存即更新，没有草稿/评审/版本历史；需要时可沿用流程模型的版本表。
- 草图为整份 mxfile XML，列表接口不下发 XML，打开编辑器时才拉取详情。
- draw.io 是 Apache-2.0；如果使用官方 embed 服务，还需遵守其服务条款。
