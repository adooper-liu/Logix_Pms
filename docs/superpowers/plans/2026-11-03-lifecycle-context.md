# M2 八阶段任务入口与流程上下文 Implementation Plan

> 用户已明确要求合并前一单元后执行M2；原生执行，不启动文档评审循环。前一单元已通过PR#15合并为432451c；M2代码位于feat/lifecycle-task-handoffs，未自动发布。

**Goal:** 同一后端目录定义八阶段任务/方法/原产物/核验/下一步，体系总览和CBOK共享，进入原模块仍看同一流程上下文。
**Architecture:** 新只读/lifecycle返回8阶段和贯穿治理、经验证的流程/可选项目身份；core/lifecycle仅依赖api/state/format，router负责导航与renderAsync前后承接。阶段不保存状态，不新增表。
**Tech Stack:** FastAPI/Pydantic/SQLAlchemy，原生ES模块、pytest、Playwright。
**Spec:** 总规格R0-01与第2节，主任务brief M2。原主去向strategy/pcf/designer/monitor analysis/designer/execution/dashboard/projects不变，治理authorization独列。

## Global Constraints

- 不新八阶段/四结论引擎，不改项目五阶段、原发布/权限。
- 建模/设计同一个designer，以lifecycle键区分任务说明，不冒称As-Is/To-Be版本已自动冻结。
- URL显式流程优先；非法/不存在项目/跨流程引用拒绝，失效上下文不执行目标加载器，不回落其他流程。
- 未选流程可看目录和一般范围，不要求项目；需要具体流程的阶段提示先选择，不自动开演示模型。
- 任务说明不等于新增专业算法；方法引用原工具/模板，输出归原对象。
- 原有普通无lifecycle链接兼容；返回来源保留阶段与身份，换流程清除项目。

## Review Focus

1. 八阶段+治理不变九阶段——Task1目录契约和Task3真实UI。
2. 无项目流程可进入——Task2验证process-only与所有八个原跳转。
3. 错ID/跨流程项目不加载其他对象——Task1 API及Task3非法深链。
4. 目标页规范化URL不丢lifecycle，返回/刷新可复现——Task2 router与Task3设计器刷新。
5. 同一view不同阶段/上下文旧请求不覆盖——Task2 renderAsync请求代号及UI切换。

## Task1 后端单一目录和只读验证

Create app/services/lifecycle.py、schemas/lifecycle.py、api/v1/lifecycle.py、tests/test_lifecycle.py；Modify api/v1/router.py。
- [ ] RED：GET /lifecycle应有strategy/architecture/modeling/analysis/design/execution/monitoring/improvement八项，每项task/method_codes/artifact/verification/next_key/target；治理单独。
- [x] 验证可选process_id及project_id：正整数；项目需已选流程、项目流程必须相同、组织可见；错对象404，跨流程422。无ID不默认创建/选择；GET前后业务记录数量不变。
- [x] GREEN：读原ProcessArch分类输出，不复制状态。每项写明原产物和能力限制。

## Task2 前端共享目录与目标任务契约

Create web/js/core/lifecycle.js；Modify router.js、views/start.js、cbok.js。
- [x] 共享loadLifecycle(params)只从/lifecycle读；渲染流程/可选项目摘要、阶段nav、选中阶段task/方法/原产物/核验/下一步、治理入口。下拉只列L3/L4；换流程清项目。
- [x] 体系总览和CBOK移除各自硬编码生命周期数组，使用同一目录；公司框架证据仍保留，但不说八阶段顺序推进或最低证据=全公司完成。
- [x] router注册导航动作，目标params只构建process/project/lifecycle+该阶段tab；不携带不适用旧筛选。执行明确tab=tasks，设计器明确tab=model。
- [x] renderAsync遇lifecycle参数先验证目录/身份，错误或所需流程缺失时仅显示上下文指引，不执行业务loader；paint后插入共享任务契约。请求序号防旧响应覆盖同view新上下文。
- [x] setUrlState在当前同view规范化时保留合法lifecycle身份，换流程清project；普通非lifecycle链接行为不变。

补验扩展：monitoring允许驾驶舱原monitor下钻；方法页保留lifecycle/process/project并清旧step；分析请求延迟到上下文校验后。新增浏览器红例已逐条见失败，再转绿；完整全站门禁仍待通过。

## Task3 实际交互与证据

Create scripts/verify_lifecycle.py（复用frontend_test_app中性隔离器），Modify verify_frontend登记专项。
- [ ] 浏览器RED开始页无共享目录/流程选择；API RED目录不存在。
- [x] 真实UI验证开始与CBOK同8项/治理独列，流程选择、每项任务契约、八个原去向/URL process、无项目、返回来源/刷新、建模设计同view、非法ID明确错误不拉演示模型。
- [x] pytest全量、check.py、专项、verify_frontend实际执行；全站旧路径按当前原入口与实际夹具校正，业务页面不改回旧UI；最终退出0。无schema变更不新增迁移。
- [x] 更新brief M2实际结果，保留失败/限制，不宣称专业能力全部实现。M2不自动提交/合并。

## 本轮实施记录

- 继承会话开始前已存在的M2首版，不删除重写；本会话未亲见首版目录的历史RED，Task1/3的该复选项保留未勾，不冒称补验替代历史。
- 本轮新增四项真实浏览器红例分别捕获：方法项目身份丢失、监控下钻任务丢失、非法分析提前请求、方法残留上次项目步骤；最小修复后专项全部转绿，已接入全站入口。
- `python scripts/check.py`复核修复后输出`542 passed, 4 warnings in 121.11s`，格式/lint通过；`pytest tests/test_lifecycle.py tests/test_frontend_structure.py -q`为41项通过；方法保存浏览器回归通过；JS/Python语法与diff空白检查通过。
- 全站门禁未通过，不能标整单元完成；M2和前一快照完整对照均退出1、同名28项失败，无新增失败名称；复核修复后的最终入口亦完整退出1、相同28项失败；三个M2专项及20视图渲染通过。无schema迁移，不据此宣称生产环境已验收。
- 代码复核5项Important已用真实浏览器补红例并修正：设计器旧loader写共享模型、原方法按钮漏身份/旧step、方法保存误取历史项目、方法页返回资源误拦、告警原下钻漏任务/项目。复核次要项“监控选择全部流程时补回旧身份”在2026-11-04补红例后修复：显式空process/project/lifecycle，返回公司范围；不以重定向代替上下文承接。
- 2026-11-04最终收尾：旧门禁选择器/文案/夹具按当前代码校正，含内部页入口、树祖先、原驾驶舱动作、在线模板现行版本、发布说明及原方法modal等待；没有跳过28项后称通过。`check.py`542 passed,4 warnings in 114.95s，格式/lint通过；完整`verify_frontend.py`输出全部检查通过、exit0。只读调色板因无评审中流程跳过，外部diagrams.net 403，真实外站加载未验收；主brief记录限制。不新增schema，M2未提交发布。
