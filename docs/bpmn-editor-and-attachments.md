# BPMN 编辑器与流程附件版本管理方案

本文回答两个问题：

1. 如何把当前的泳道式设计器升级为正式的 BPMN 2.0 编辑器（并评估类 Visio 方案）；
2. 一个流程如何管理多种格式的附件（尤其是表单 Excel）与版本。

结论先行：

- **流程逻辑用 bpmn-js 编辑，不用 Visio 类自由画布。** BPMN 是带执行语义的模型；
  Visio、Excel、PDF、SOP 属于流程的**文档附件**，走版本管理，不进入执行引擎。
- **BPMN 2.0 XML 作为唯一权威模型**，现有 `ProcessNode` / `ProcessEdge` 退化为
  「可执行投影 / 分析缓存」，避免两套模型各算各的。
- **附件按「文档 → 版本」两层建模**，文件存对象存储或本地卷，数据库只存元数据。
- 先做附件与版本（独立、风险低、马上可用），再做 BPMN 编辑（涉及执行语义），
  最后接 Excel 表单模板。

---

## 一、现状

| 能力 | 当前实现 | 局限 |
|---|---|---|
| 流程建模 | [web/js/views/designer.js](../web/js/views/designer.js) 的泳道卡片，节点/连线存 `ProcessNode` / `ProcessEdge` | 不是标准 BPMN 画布；不能拖拽连线、画网关、调整布局 |
| BPMN 导入导出 | [app/services/bpmn.py](../app/services/bpmn.py) 的结构子集 | 会拒绝 `parallelGateway` / `subProcess` / `boundaryEvent` 等；导入即替换，不能保留完整 XML |
| 执行引擎 | 单令牌顺序执行，启动时快照节点/连线 | 不支持并行、子流程、事件；正式 BPMN 中的这些元素目前不可执行 |
| 附件 | 无 | 没有上传、存储、版本、权限与审计 |

因此不能直接把 bpmn-js 接上就宣布「支持 BPMN」：编辑器能画出的元素，
执行引擎必须能执行，或者明确拒绝启动并告诉用户原因。

---

## 二、BPMN 编辑器

### 2.1 选型：bpmn-js

| 方案 | 结论 |
|---|---|
| **bpmn-js** | **推荐。** BPMN 2.0 标准建模器，MIT 许可，提供 `Modeler` / `NavigatedViewer`，支持泳道、网关、事件、BPMN DI 布局；有预构建 UMD 包，可在零构建前端里直接用 |
| draw.io / diagrams.net | 通用图形编辑器，适合自由布局，但 BPMN 语义校验弱；如果确实需要「类 Visio」自由绘图，可作为**附件编辑器**单独嵌入，不作为流程权威模型 |
| 自研画布 | 成本高、标准兼容性差、无法复用 BPMN 生态，不建议 |
| Camunda Modeler 桌面版 | 可作为离线建模工具，产物 `.bpmn` 通过导入接口进入系统，不作为 Web 编辑器 |

**为什么不选 Visio 类画布做流程主模型**：流程要被执行、测算、审计，需要稳定的
节点类型、连线条件与 ID；自由画布无法保证这些语义。Visio 文件应作为附件保存和下载，
需要预览时转 PDF，而不是把它当作可执行流程。

### 2.2 零构建集成方式

bpmn-js 发布包含预构建文件，不需要 Vite/Webpack：

```
web/vendor/bpmn-js/
  bpmn-modeler.production.min.js
  bpmn-navigated-viewer.production.min.js
  assets/diagram-js.css
  assets/bpmn-font/{css,fonts}
  LICENSE
```

- 版本锁定并提交到仓库，保证内网/离线部署可用；不使用 CDN。
- 在 `index.html` 引入 CSS；JS 通过一个 `web/js/core/bpmn.js` 动态加载，
  只有进入「BPMN 建模」页签时才加载，避免拖慢其他页面。
- 自定义属性面板不引入 Camunda properties panel，直接监听
  `selection.changed`，用 `modeling.updateProperties()` 写回；
  这样面板字段可以由我们控制（工期、等待、是否增值、Owner、表单、规则）。
- 保留 MIT LICENSE 与版本号，升级时单独提交 vendor 变更。

### 2.3 权威模型：BPMN XML

新增两张表，保存流程定义的版本链：

```text
process_definition
  id, process_id (unique FK), current_version_id (nullable FK),
  created_at, updated_at

process_definition_version
  id, definition_id FK, version_no,
  bpmn_xml TEXT, checksum,
  created_by_id FK, note, created_at
  unique(definition_id, version_no)
```

> `process_definition.current_version_id` 与版本表形成循环外键，迁移里用
> `use_alter=True` 或先建表后补 FK；删除当前版本必须拒绝。

保存链路：

```text
bpmn-js saveXML
  → POST /processes/{id}/definition（XML + expected_version）
  → XSD/结构校验 + 不支持元素扫描
  → 写 process_definition_version
  → 投影为 ProcessNode / ProcessEdge（同一事务）
  → 重算指标
  → 更新 current_version_id
```

投影规则：

- BPMN 元素 `id` → `node_key`，必须稳定；表单/规则引用 `node_key`，不能因排版变化而断。
- `laneSet/lane` → `lane` 字符串；`sequenceFlow` → `ProcessEdge`。
- 自定义属性放 `pms:` 扩展元素：`pms:nodeType`、`pms:durationMinutes`、
  `pms:waitMinutes`、`pms:isValueAdded`、`pms:ownerRole`、`pms:formKey`、`pms:ruleKey`。
- 不支持的 BPMN 元素**保留在 XML 中**，投影时标记 `unsupported`；
  该流程可以保存、查看，但 `POST /instances` 返回 422 并列出原因，不静默降级。
- 执行实例仍快照投影后的节点/连线，同时记录 `definition_version_id`，保证可追溯。

迁移步骤：

1. 为现有流程用 `export_bpmn()` 生成初始 XML，灌入 `process_definition_version` v1；
2. 保存入口切到 XML，节点/连线由投影生成；
3. 旧泳道视图保留为「快速查看/分析」，**编辑入口只留 BPMN**，避免两套编辑模型；
4. 执行引擎逐步补并行网关、子流程后，再放开对应元素的执行。

### 2.4 交互设计

设计器页签调整为：

```text
BPMN 建模 | 指标与建议 | 附件与版本
```

- 工具栏：保存、撤销/重做、缩放、适应画布、导入 `.bpmn`、导出 `.bpmn`。
- 右侧属性面板：名称、类型、泳道、Owner、工期、等待、是否增值、表单、规则。
- 底部状态条：当前版本号、保存状态、未保存变更、校验结果（错误/警告数量）。
- 只读用户使用 `NavigatedViewer`，不显示编辑工具。
- 保存冲突沿用现有 `expected_version` 乐观锁，冲突时提示「他人已保存，请刷新」。

---

## 三、附件与版本管理

### 3.1 数据模型

不要让一个流程直接挂一堆文件；按「文档（逻辑对象）→ 版本（物理文件）」两层建模：

```text
process_document
  id PK
  process_id FK -> process_arch.id (ondelete CASCADE)
  title             -- 业务名称，如「采购申请单模板」
  category          -- BPMN / FORM_EXCEL / SOP / VISIO / PDF / OTHER
  description
  current_version_id FK -> process_document_version.id (nullable)
  created_by_id FK -> app_user.id
  created_at, updated_at

process_document_version
  id PK
  document_id FK -> process_document.id (ondelete CASCADE)
  version_no        -- 从 1 递增，不覆盖
  filename          -- 原始文件名
  mime_type
  size_bytes
  sha256
  storage_backend   -- local / s3
  storage_key       -- 对象键，不含用户可控路径
  uploaded_by_id FK -> app_user.id
  note              -- 版本说明
  created_at
  unique(document_id, version_no)
```

规则：

- 上传新版本 = `max(version_no) + 1`，历史版本永不覆盖。
- 删除版本：仅管理员；当前版本不可删；删除写审计。
- 恢复历史版本 = 把 `current_version_id` 指回旧版本，不复制文件。
- 文档继承流程的权限：Owner / Manager 可写，Viewer 只读。
- 所有上传、下载、删除、恢复都写 `AuditLog`。

表单 Excel 额外建立可选关联：

```text
form_definition.template_document_id FK -> process_document.id
```

执行任务的表单区显示「下载表单模板（当前 v3）」，确保操作员拿到的永远是当前版本。

### 3.2 存储

数据库只存元数据，文件放对象存储：

```text
app/services/storage.py
  class AttachmentStorage(Protocol):
      save(key, stream) -> None
      open(key) -> BinaryIO
      delete(key) -> None
      exists(key) -> bool

  LocalStorage(root)      # 开发/单机：ATTACHMENT_DIR，挂 Docker volume
  S3Storage(bucket, ...)  # 生产：S3 / MinIO，下载用短时预签名 URL
```

- 开发默认 `./var/attachments`，生产用 S3/MinIO；不要把大文件塞进 PostgreSQL。
- `storage_key` 由服务端生成：`process/{process_id}/{document_id}/{version_no}/{uuid}`，
  原始文件名只用于展示，禁止拼进路径。
- 写入顺序：生成 key → 流式写临时文件并计算 SHA-256 → 原子 rename → 写 DB；
  失败清理临时文件。定期清理无 DB 记录的孤儿文件。
- 限制：单文件大小、允许的扩展名/MIME（服务端嗅探魔数，不只信 `Content-Type`）、
  每流程配额；`.xlsm` 标记为含宏，只下载不执行。

### 3.3 API

```text
GET    /api/v1/processes/{id}/documents
POST   /api/v1/processes/{id}/documents            multipart: file, title, category
GET    /api/v1/processes/{id}/documents/{doc_id}
PATCH  /api/v1/processes/{id}/documents/{doc_id}   title/description
DELETE /api/v1/processes/{id}/documents/{doc_id}   仅管理员

GET    /api/v1/processes/{id}/documents/{doc_id}/versions
POST   /api/v1/processes/{id}/documents/{doc_id}/versions   multipart: file, note
GET    /api/v1/processes/{id}/documents/{doc_id}/versions/{v}/download
POST   /api/v1/processes/{id}/documents/{doc_id}/versions/{v}/restore
DELETE /api/v1/processes/{id}/documents/{doc_id}/versions/{v}
```

- 上传需要 `python-multipart`（当前 requirements 里还没有，需要新增）。
- 下载走鉴权接口或短时预签名 URL，不把上传目录挂成公开静态目录。
- 响应头：`Content-Disposition: attachment; filename*=UTF-8''...`、
  `X-Content-Type-Options: nosniff`。

### 3.4 Excel 表单的特殊处理

| 能力 | 做法 |
|---|---|
| 原样保存/下载 | 存 `.xlsx` / `.xlsm` 原始文件，版本化；这是审计与打印的依据 |
| 在线预览 | 前端引入 SheetJS（vendored，零构建），只读渲染工作表；大文件限制行/列 |
| 结构识别 | 后端用 `openpyxl` 只读模式读取工作表名、表头、数据验证列表，生成字段预览 |
| 生成表单字段 | 后续能力：把 Excel 表头/校验规则映射为 `FormDefinition` 字段，需人工确认后保存 |
| 宏安全 | `.xlsm` 不做任何执行，不服务端打开宏；预览只读单元格值 |
| 版本关联 | `FormDefinition.template_document_id` 指向文档，任务页显示当前版本 |

Visio（`.vsdx`）浏览器无法原生预览：默认只提供下载；需要预览时在部署侧用
LibreOffice headless 转 PDF（异步任务），不把转换依赖塞进主请求链路。

### 3.5 UI

- 设计器新增「附件与版本」页签：按文档分组，显示当前版本、上传人、时间、大小、
  下载/预览、上传新版本、历史版本抽屉、恢复。
- 流程地图的流程详情弹窗增加「附件」入口；执行任务页显示关联表单模板。
- 分类用图标 + 标签（BPMN / 表单 Excel / SOP / Visio / 其他），不要用文件扩展名当分类。
- 上传支持拖拽；上传中显示进度；失败给出具体原因（大小、类型、重复）。

---

## 四、实施顺序

### 阶段 1：附件与版本（建议先做）

- 模型 + Alembic 迁移：`process_document` / `process_document_version`
- 存储抽象 + 本地实现 + 配置项；S3 实现留接口
- 上传/下载/新版本/恢复/删除 API + 权限 + 审计
- 设计器「附件与版本」页签 + 流程详情入口
- 测试：版本递增、当前版本唯一、权限、路径穿越、大小/类型限制、审计
- 验收：上传 Excel → 改一版 → 下载 v1/v2 → 恢复 v1，全程有审计记录

### 阶段 2：BPMN 查看与编辑

- 引入 bpmn-js vendor + 只读查看器（先不写库）
- 现有流程 export 成 XML 展示，验证 DI 布局
- 增加 `process_definition` / `process_definition_version`，回填 v1
- 保存链路：XML 校验 → 投影 → 重算；不支持元素标记并阻止启动实例
- 属性面板、版本冲突、只读角色
- 验收：bpmn-js 画出的流程可保存、刷新后布局不丢、可导出并在 Camunda Modeler 打开

### 阶段 3：执行语义补齐

- 并行网关、子流程、边界事件按优先级补执行引擎
- 每补一种，解除对应的「不可执行」标记
- 验收：含并行分支的 BPMN 能启动、任务队列出现多个可认领任务（或明确的分支策略）

### 阶段 4：Excel 表单模板联动

- `FormDefinition.template_document_id`
- 执行任务页展示/下载当前模板
- Excel 表头识别 → 表单字段草稿（人工确认）
- 验收：模板升版后，新任务拿到新版本，历史实例仍指向启动时版本

---

## 五、明确不做的事

- **不做 Visio 克隆。** 自由画布不是流程执行模型；Visio 文件作为附件保存/下载。
- **不在同一页面同时提供两套可编辑模型。** 泳道卡片只读展示，编辑统一走 BPMN。
- **不静默降级 BPMN 元素。** 不支持的网关/子流程保留 XML，但阻止启动实例并说明原因。
- **不把文件存进数据库大字段。** 元数据入库，文件进对象存储/卷。
- **不覆盖历史版本。** 新版本永远追加，恢复只移动当前版本指针。
