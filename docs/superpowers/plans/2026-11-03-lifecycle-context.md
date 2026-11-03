# M2 八阶段任务入口与流程上下文 Implementation Plan

> 用户已明确要求合并M1a后执行M2；原生执行，不启动文档评审循环。M2代码另分支，不自动发布M2。

**Goal:** 同一后端目录定义八阶段任务/方法/原产物/核验/下一步，开始使用和CBOK共享，进入原模块仍看同一流程上下文。
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
- [ ] 验证可选process_id及project_id：正整数；项目需已选流程、项目流程必须相同、组织可见；错对象404，跨流程422。无ID不默认创建/选择；GET前后业务记录数量不变。
- [ ] GREEN：读原ProcessArch分类输出，不复制状态。每项写明原产物和能力限制。

## Task2 前端共享目录与目标任务契约

Create web/js/core/lifecycle.js；Modify router.js、views/start.js、cbok.js。
- [ ] 共享loadLifecycle(params)只从/lifecycle读；渲染流程/可选项目摘要、阶段nav、选中阶段task/方法/原产物/核验/下一步、治理入口。下拉只列L3/L4；换流程清项目。
- [ ] 开始使用和CBOK移除各自硬编码生命周期数组，使用同一目录；公司框架证据仍保留，但不说八阶段顺序推进或最低证据=全公司完成。
- [ ] router注册导航动作，目标params只构建process/project/lifecycle+该阶段tab；不携带不适用旧筛选。执行明确tab=tasks，设计器明确tab=model。
- [ ] renderAsync遇lifecycle参数先验证目录/身份，错误或所需流程缺失时仅显示上下文指引，不执行业务loader；paint后插入共享任务契约。请求序号防旧响应覆盖同view新上下文。
- [ ] setUrlState在当前同view规范化时保留合法lifecycle身份，换流程清project；普通非lifecycle链接行为不变。

## Task3 实际交互与证据

Create scripts/verify_lifecycle.py（复用frontend_test_app中性隔离器），Modify verify_frontend登记专项。
- [ ] 浏览器RED开始页无共享目录/流程选择；API RED目录不存在。
- [ ] 真实UI验证开始与CBOK同8项/治理独列，流程选择、每项任务契约、八个原去向/URL process、无项目、返回来源/刷新、建模设计同view、非法ID明确错误不拉演示模型。
- [ ] pytest全量、check.py、专项、verify_frontend实际执行；全站其他旧路径失败明确记录，不改无关页面。无schema变更不新增迁移。
- [ ] 更新brief M2实际结果，保留失败/限制，不宣称专业能力全部实现。M2不自动提交/合并。
