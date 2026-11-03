# 全量文档综合评审 Brief

> **评审模型：** 独立只读综合评审（非原助手自审结论）。  
> **固定基线提交：** `6ba817f46f355c7e6ed0ca92d7ba88d4d8271f12`（`main` 与 `origin/main` 一致时的 HEAD）。  
> **任务书：** [document-review-handoff.md](../document-review-handoff.md)。  
> **日期：** 2026-11-03。  
> **说明：** 工作区存在**未提交** staged/未跟踪文档（含本地 `bpm-first-batch-*`、`bpm-requirements-traceability.md` 等），**未纳入**本评审的已合并基线；见附录「基线外修订」。

---

## 1. 基线、范围与核证方式

### 1.1 基线命令记录（只读）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `git rev-parse HEAD` | `6ba817f46f355c7e6ed0ca92d7ba88d4d8271f12` | 0 |
| `git status --short` | 6 个 `docs/*` + `README.md` 已 staged；7+ 未跟踪路径（含 `cbpp-prep-main/`） | 0 |
| `git log -5 --oneline` | `6ba817f` ← PR#13；`926d43b`；PR#12；`6291cee`；`4607792` | 0 |
| `docs/` 在基线树中文件数 | 46（含 `document-review-handoff.md`） | — |

**未执行：** `pytest`、`scripts/check.py`、`verify_frontend.py`、Docker 全栈启动、生产/共享库连接、外部标准原文检索。  
**已执行：** 16 份核心产物全文或等价深度阅读（C07–C14 为结论段+关键章节+与规格交叉）；30 份配套文档分类与首段/冲突关键词审读；定向源码核对（handoff §6 所列路径及 inventory 引用行）。

### 1.2 读取范围

- **C01–C16：** 按 handoff §3.1 顺序完成（C07–C14 八专项：各读 §1–§2、§8–§10/§12 及与闭环相关的中间章节要点）。  
- **S01–S30 + CLAUDE + 任务书：** 分类审读（见附录覆盖矩阵）。  
- **基线外：** 未读作「已批准设计」；仅在 brief 中标注分叉风险。

---

## 2. 一句话结论

**修订后可进入开发计划细化** —— 在固定提交 `6ba817f` 上，产品原则、落地规格、路线、文案规范及 PR#12/#13 的语言/页面清单构成**逻辑大体自洽、边界较清楚**的设计基线，且与「尚未实现薄轮次对照 / Flowable」的代码事实基本一致。

**尚不能**在无修订的情况下直接编码或对外宣称「闭环已实现」：代码层仍存在与规格 explicitly 冲突的 KPI 取数、工具 auto-EFFECTIVE、十层第 6 层技术强迫等；规格/footer 与综合评审的部分元陈述在 `6ba817f` 上**已过时**；S1–S5 页面/语言整治仅为**候选方案**，与「零构建、原对象扩展」一致但未验收。

---

## 3. 应保留的核心设计（最多 5 项）

1. **长期 `process_id` 为主对象，改善 `Project` 只交付一轮** —— 原则、规格、路线一致；`project_workflow` 对 `IMPROVEMENT` 与 `setup_program` 对治理体系项目的分轨与文档 P-10/L-20 叙述方向一致（实现上 workflow 仍待 S1 类型过滤）。  
2. **薄轮次四身份 + 按时点冻结/追加，非四阶段引擎** —— 规格 §3.2–§3.4 与文案 §2.5 一致；代码尚无 `ProcessImprovementRound`（符合规格自述）。  
3. **当前 `publish()` 更新运行模型与指针（SoD 已有）** —— `process_model.publish` 含 `_apply_snapshot`、`_apply_snapshot` 与 `published_model_version`（`app/services/process_model.py:457–477`）；文档禁止「仅审批未部署」的当前语义是正确的。  
4. **产品语言「一规范 + 清单证据 + 页面职责表」，非同义词批量替换** —— C05/C15/C16 与 handoff 审定候选一致；inventory 26 项有源码行号锚点。  
5. **R0–R5 为工作分组，第一批 = 薄表 + 必要 FK + 只读投影** —— 规格 §1.1 与路线 §8 段末一致，未在 `6ba817f` 树中引入已否决的主库（发布包/方案库等）。

---

## 4. 最关键问题（10 项，完整表见 findings）

| ID | 级 | 摘要 | 证据锚点 |
|---|---|---|---|
| DR-001 | P1 | KPI 仍按「流程+时长单位」推断实例来源并回写全部时长 KPI | `app/services/kpi.py:112–114`, `:367–382` vs 规格 R2-02、路线 §6.3 |
| DR-002 | P1 | 工具 sheet 在步骤上下文自动 `usage` 且 `EFFECTIVE` | `web/js/views/shared/tool_sheet.js:93–102` vs 规格 §2.2、文案 §8 |
| DR-003 | P1 | 十层第 6 层强制 RPA/案例/技术登记（count>0） | `app/services/pilot.py:180–199`, `startup.evidence_met` vs 路线 §6.1、规格 R1-04 |
| DR-004 | P1 | 产品语言多源：BPR 等项目/驾驶舱标签不一致 | `projects.py:79`, `dashboard.py:52`；C15 L-01 |
| DR-005 | P1 | `monitor`/`dashboard` 共用顶栏「运营驾驶舱」 | `state.js:76,83`；C15 L-04 |
| DR-006 | P1 | 前端业务枚举中文仍多处维护（severity 等） | `format.js:92`, `process_card.js:80` vs 文案 §9、C15 L-05 |
| DR-007 | P1 | API 层将网络失败与 uvicorn 绑定；401 与会话过期混在 api 层 | `api.js:43–50` vs 文案 §6、handoff §5.1 场景 6 |
| DR-008 | P2 | 规格 §9 /footer 元陈述过时（「开发计划未生成」「文档均未提交」） | `6ba817f:implementation-spec` 末段 vs 已合并 handoff/inventory/page 表 |
| DR-009 | P2 | 综合评审 C17 与现状：无 `bpm-first-batch-dev-plan` **在基线树中**仍正确，但 principles §9 未列 C15/C16/handoff | `6ba817f:product-principles` §9 |
| DR-010 | P2 | 工作区 staged README 链向**未跟踪** brief/追溯表，若误提交会 404 | 当前 `git status` vs `6ba817f:README` |

---

## 5. 跨文档统一决定候选

| 主题 | 既定约束（不宜单方推翻） | 评审者新建议（需用户/终审） |
|---|---|---|
| 四结论 / round | 同轮核验进度，非阶段机；PASS≠改善达标 | 无 |
| publish vs R3 | 当前发布=运行更新；R3 部署 ID 分开 | 无 |
| 语言 | 后端 meta 为业务枚举中文唯一源；禁止全局 CLOSED→「已完成」 | 采纳 C15 标准名/短名契约；S2 批实施 |
| 页面 | 单主题子页，非侧栏菜单膨胀；流程卡/设计器保留 | 采纳 C16 S1–S5 顺序；deliverables/execution 先拆 |
| 第一批 BPM | 仅 `ProcessImprovementRound` + FK；无 Flowable | 本地未跟踪 dev-plan **不得**视为已合并基线，除非用户并入 `6ba817f` 之后提交 |
| 治理项目类型 | 框架边界 1 阶段（`setup_program.py:19–27`）≠ 改善五阶段 | workflow 须按 `project_type` 过滤（C16 P-10、L-20）——**部分已在文档，代码未验** |

---

## 6. 推荐修订顺序（对 S1–S5 / BPM 分批的影响）

1. **文档元数据同步（无代码）：** 规格 §9 footer、principles §9 产物表、artifacts-review 与 `6ba817f` 已合并的 C15/C16/handoff 对齐；消除 DR-008/009。  
2. **处理工作区分叉：** 要么 commit 追溯表/brief/dev-plan 全套，要么 revert staged README 中的死链（DR-010）。  
3. **BPM 第一批（若用户授权开发）：** 规格 R2-02 + §2.2 行为修正（DR-001/002）可独立于 round 表先发；round 表依赖 artifacts §4 七项决定定值。  
4. **S1（语言/标题）：** L-01、L-04 与 monitor 子标题（C16 S1）——纯前端+meta，不改业务对象。  
5. **S3/S4/S5：** deliverables 主题化、execution 配置/集成分轨、orgs 按需加载——按 C16，每片需独立验收与 `test_frontend_structure` 登记。

---

## 7. 须由用户决定的问题

1. **是否将本地未跟踪的 `bpm-first-batch-dev-plan.md` 等并入仓库**，作为「第一批开发计划」权威版本，还是重写以仅引用 `6ba817f` 已有产物。  
2. **十层第 6 层改为 OPTIONAL/N/A 时**，种子/demo 路径是否允许 breaking（DR-003）。  
3. **治理体系项目**在 UI 上是否强制与改善五阶段工作台彻底分离（C16 已建议，影响 workflow 深链）。  
4. **试点流程与 KPI 目标窗口**（规格/路线均不写死数值）——业务批准前不得写入种子为「达标」。

---

## 8. 交回原助手终审的核证清单

- [ ] 确认评审基线为 `6ba817f`，且未将工作区未跟踪文件当作已合并事实。  
- [ ] 对 DR-001～DR-007 各读源码与规格原文，决定 P0/P1 是否维持。  
- [ ] 更新 `bpm-lifecycle-implementation-spec.md` footer 与 principles §9（若接受 DR-008/009）。  
- [ ] 决定 local staged 变更去留（DR-010）。  
- [ ] 场景走查 §5.1（7 条）在 findings 附录中是否需补 DR。  
- [ ] **未验证项：** 全量 pytest/E2E、浏览器 S1–S5、Flowable、生产数据——不得因本 brief 声称通过。

---

*附录全文见 [document-review-findings.md](./document-review-findings.md)。*
