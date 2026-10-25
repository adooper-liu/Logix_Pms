# 附件编辑、预览、分发与培训：现状与建设路线

> 本文回答两件事：
> 1. 为什么当前只能「上传/下载附件」，不能调用 Word/Excel/Visio/CAD 编辑；
> 2. 预览、打印、分享、分发、培训、考试应该怎样接，才不破坏现有版本与权限体系。
>
> 结论先说：**不要在 PMS 里重写 Office/CAD 编辑器**。用 WOPI/OnlyOffice 或
> Collabora 承接 Office，用桌面软件 + 检出/检入承接 Visio/CAD，PMS 只做
> 「权限、版本、锁、审计、分发」。预览和打印统一转 PDF；培训和考试是独立模块，
> 不塞进交付物版本表。

---

## 一、现状（以当前代码为准）

| 能力 | 现状 | 证据 |
|---|---|---|
| 文件上传 | 有，扩展名白名单 + 魔数校验 + 大小上限 | `app/services/storage.py` |
| 文件下载 | 有，强制 `Content-Disposition: attachment`、`nosniff` | `app/services/storage.py`、`app/api/v1/deliverables.py` |
| 在线预览 | 无；设计上刻意不在浏览器内联执行 | `app/services/storage.py` 顶部注释 |
| 在线编辑 | 无；只能下载到本地改完再上传新版本 | `app/services/deliverable.py` |
| 版本/审批 | 有；版本只追加不覆盖，状态机 `DRAFT → IN_REVIEW → APPROVED → EFFECTIVE` | `app/models/deliverable.py` |
| 分享链接 | 无 | — |
| 打印/打印包 | 无 | — |
| 分发/签收 | 无 | — |
| 培训/考试 | 无；只有启动路径第 8 步要求「培训记录」 | `app/services/setup_program.py` |

当前允许的扩展名（`app/core/config.py`）：

```text
.xlsx .xlsm .docx .pptx .pdf .bpmn .xml .csv .txt .png .jpg .jpeg .vsdx .zip
```

缺少用户提到的 `.md` 和 CAD 的 `.dwg`；即使加进白名单，也仍然只能上传/下载，
不能编辑和预览。

### 已落地（P0）

- **PDF / 图片 / 纯文本在线预览**：新增 `/preview` 接口，以 `inline` 返回；
  其他格式返回 415，前端提示下载后查看。
- 预览统一走鉴权：前端用 `fetch` 取回 blob 再嵌入 iframe/图片，
  不把受保护 URL 直接暴露给浏览器。
- 预览响应头：`X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、
  `Content-Security-Policy: frame-ancestors 'self'`。
- 覆盖三类受控文件：项目交付物、流程标准文件、工具模板。
- **项目交付物打印清单**：浏览器打印窗口，包含项目、步骤、交付物、类型、
  状态、当前版本、负责人；可按步骤筛选后打印。
- 尚未落地：Office/Visio/CAD 的服务端转换预览、服务端 PDF 打印包、
  标准文件/模板的打印包。

---

## 二、能力分层：先分清「预览、编辑、协同」不是一件事

| 层级 | 能力 | 用户动作 | 推荐实现 | 不做什么 |
|---|---|---|---|---|
| L0 | 附件 | 上传、下载、看版本 | 现有存储 + 版本表 | 不再用「文件名」判断类型 |
| L1 | 预览/打印 | 不下载就能看、能打印 | 统一转 PDF/图片 + 打印样式 | 不在浏览器里直接渲染用户上传的 HTML/SVG |
| L2 | 在线编辑 Office/MD | 在浏览器里改 docx/xlsx/pptx/md | WOPI + OnlyOffice/Collabora；MD 用内置编辑器 | 不自己实现 Office 排版引擎 |
| L3 | 桌面软件协同 | 用 Visio/CAD 改 vsdx/dwg | 检出/检入 + 桌面协议/插件；预览走转换 | 不承诺浏览器内直接编辑 dwg |
| L4 | 分发/培训/考试 | 定向发布、签收、学习、考试 | 独立的分发、课程、题库、考试表 | 不把考试结果塞进交付物版本 |

---

## 三、在线编辑：三种文件，三种策略

### 3.1 Word / Excel / PowerPoint：WOPI + OnlyOffice 或 Collabora

**推荐顺序**：OnlyOffice Docs（部署简单、中文支持好）→ Collabora Online（LibreOffice 内核）。

流程：

```text
用户点「在线编辑」
  → PMS 校验权限、创建/复用 edit_session 与锁
  → 后端签发短期 JWT（用户、文件、权限、回调地址）
  → 编辑器加载文件（通过 PMS 的 WOPI/file 接口，不暴露存储路径）
  → 用户保存
  → 编辑器回调 PMS「保存」接口
  → PMS 写入新版本（只追加）+ 校验 checksum + 释放锁
  → 审计记录：谁、何时、从哪个入口、产生了哪一版
```

关键约束：

- 编辑器只拿到**一次会话**的短期令牌，不拿对象存储的长期密钥；
- 保存必须生成**新版本**，不能原地覆盖；
- 并发编辑用 WOPI lock 或 `edit_session` 唯一约束，冲突时提示「他人正在编辑」；
- 回调地址必须校验来源签名；文件大小、扩展名、魔数仍然走现有校验；
- 离线/保存失败要保留草稿，不能把旧版本覆盖掉。

### 3.2 Markdown：内置编辑器

Markdown 不需要外部软件，直接做：

- 左编辑右预览（CodeMirror 6 或 Milkdown，零构建可用 CDN 版，或用轻量 textarea + marked）；
- 保存生成新版本，记录 diff；
- 预览结果按 HTML 白名单清洗后渲染；
- 适合知识条目、SOP 草稿、培训讲义。

### 3.3 Visio / CAD：浏览器预览 + 桌面软件检出/检入

这两类不可能靠一个网页编辑器解决，正确做法是「PMS 管版本，桌面软件管编辑」：

| 文件 | 预览 | 编辑 | 说明 |
|---|---|---|---|
| `.vsdx` | LibreOffice 转 PDF/SVG，或 draw.io 导入 | 桌面 Visio + `ms-visio:` 协议；检出/检入 | 简单流程图可引导改用内嵌 draw.io |
| `.dwg` | Autodesk Platform Services Viewer，或 ODA/LibreDWG 转 PDF/SVG | 桌面 CAD（AutoCAD/中望/浩辰）+ 检出/检入 | 不在浏览器里承诺可编辑 |
| `.dxf` | 同上 | 同上 | 可作为轻量交换格式 |

检出/检入：

```text
检出 → 文件锁 + 本地副本下载 + 会话记录
编辑 → 桌面软件打开本地副本
检入 → 上传为新版本 + checksum 对比 + 释放锁 + 审计
超时 → 自动释放锁，但保留检出记录，避免「谁锁的」查不到
```

如果企业有 Autodesk Platform Services / 中望云 CAD，可把 L3 升级为云端编辑；
否则不要为了「在线」牺牲 CAD 的精度和插件能力。

---

## 四、预览与打印：统一转 PDF，而不是各页面各做一套

### 4.1 预览

- 上传后异步生成预览资产：PDF（Office/Visio/CAD）、PNG 缩略图（首屏）、
  文本抽取（检索用）；
- 预览接口按权限鉴权，短时签名 URL，禁止目录遍历；
- PDF/图片可 `inline`；其他类型仍 `attachment`；
- 生成失败要显示「仅可下载」，不能让用户看到空白预览。

建议新增表：

```text
preview_asset(id, version_id, kind, storage_key, status, error, created_at)
```

`kind`：`PDF | THUMBNAIL | TEXT`。转换服务可独立部署（LibreOffice headless /
OnlyOffice converter / ODA），不放进 API 进程。

### 4.2 打印

- 页面打印：为流程卡、SOP、检查表、KPI 卡提供 `@media print` 样式；
- 打印包：把「SOP + 表单 + RACI + 授权规则 + KPI」合成一个 PDF 包，
  带版本号、生效日期、页码和「受控文件」水印；
- 打印动作写审计（谁、哪一版、何时）。

---

## 五、分享与分发：链接不是公开 URL

### 5.1 受控分享链接

不要直接把存储对象 URL 发出去。新增：

```text
share_link(
  id, version_id, token_hash, scope_kind, scope_id,
  expires_at, max_downloads, download_count,
  watermark, created_by, created_at, revoked_at
)
```

- `scope_kind`：`ORG | ROLE | USER | PUBLIC_LINK`；
- 令牌只存哈希，链接短期有效，可撤销；
- 下载/预览写审计，支持下载次数上限；
- 受控文件默认带水印（用户、组织、时间）；
- `PUBLIC_LINK` 只允许非敏感文件，且必须显式二次确认。

### 5.2 分发与签收

```text
document_distribution(id, version_id, audience_kind, audience_id, due_at, created_by)
document_ack(distribution_id, user_id, acked_at, ip, user_agent)
```

- 按组织/角色/岗位分发，而不是发邮件附件；
- 需要签收的版本显示「已读/未读/逾期」；
- 新版本发布时，旧版本自动标记 `SUPERSEDED`，分发记录保留历史；
- 与授权矩阵联动：某些审批权限要求「已签收当前版本」。

---

## 六、培训与考试：独立模块，不塞进交付物

### 6.1 最小模型

```text
training_course(id, title, source_kind, source_id, version, owner, status)
training_lesson(id, course_id, title, content_md, order_no)
training_assignment(id, course_id, audience_kind, audience_id, due_at)
training_progress(assignment_id, user_id, lesson_id, completed_at)
exam_question(id, course_id, type, stem, options, answer, score)
exam_attempt(id, course_id, user_id, started_at, submitted_at, score, passed)
```

### 6.2 与现有模块的关系

- **课程来源**：知识库条目、流程标准文件（SOP）、十层单页的层目标；
- **培训对象**：按组织/角色/岗位分发，与授权矩阵的审批角色对齐；
- **考试结果**：作为「资格」记录，不直接改流程模型；
  授权规则可要求「当前版本已培训 + 考试通过」才允许审批；
- **版本升级**：SOP 升版后，自动生成「增量培训」任务；
  未完成培训的人在授权矩阵里显示「待复训」，但不自动收回已有权限（需管理员确认）。

### 6.3 验收指标

- 分发覆盖率 = 已签收 / 应签收；
- 培训完成率、考试通过率、平均完成时长；
- 版本更新后的复训完成率；
- 「未培训但已审批」的人数为 0。

---

## 七、路线图

| 阶段 | 范围 | 验收标准 | 估算 |
|---|---|---|---|
| P0 | 预览（PDF/图片/文本）+ 项目交付物打印清单 | 常见文件不下载可预览；打印清单版本正确（已完成） | 5–8 人日 |
| P1 | 服务端转换预览（Office/Visio/CAD）+ 服务端 PDF 打印包 | Office/Visio/CAD 可预览；标准文件/模板可打印 | 5–8 人日 |
| P1 | Office 在线编辑（WOPI + OnlyOffice/Collabora） | 编辑保存生成新版本；并发锁生效；审计完整 | 10–15 人日 |
| P1 | 受控分享 + 分发签收 | 链接可撤销/过期；签收率可查 | 6–10 人日 |
| P2 | Visio/CAD 检出/检入 + APS/ODA 预览 | 检出锁、检入新版本、超时释放 | 8–12 人日 |
| P2 | 培训课程 + 题库 + 考试 + 资格联动 | 按角色分发；通过率可查；审批前校验资格 | 12–18 人日 |

**不要做**：自研 Office/CAD 编辑器；把 `.docx` 当 HTML 内联渲染；用扩展名判断
文件类型；把公开对象存储 URL 当分享链接。

---

## 八、结论

- ④ 的问题不是「少一个上传按钮」，而是缺 **编辑器协议层**。Office 走 WOPI，
  Visio/CAD 走桌面检出/检入，MD 走内置编辑器；PMS 只做权限、版本、锁和审计。
- ⑤ 的预览/打印/分享/分发/培训/考试应分层建设：预览和打印先做（成本低、收益直接），
  分享和签收其次，培训考试最后；不要把它们混进交付物版本表。
