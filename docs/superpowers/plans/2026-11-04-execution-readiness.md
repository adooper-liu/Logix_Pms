# M6 执行与上线准备 Implementation Plan

> 原生superpowers:executing-plans；用户先授权合并M5后继续M6，本轮进一步明确授权M6门禁通过后提交、推送、合并，再继续M7。

**Goal:** 原执行页核对发布/配置/表单/分派/时限及原上线依据；无RPA不强造登记，实例固定直接原模型身份及可选轮次。
**Architecture:** 原ProcessExecutionConfig加readiness JSON/revision（约定与本人确认在原配置，不建部署/条件主库）；原PilotLayer补可选证据适用性；原实例加model_version_id/round_id，启动事务固定。纯GET不建层/改层号。
**Spec:** implementation-next-brief.md M6；bpm-lifecycle-implementation-spec.md R1-04/R3；原执行专项现有支持子集。Flowable并行/事件接入明确后续，不虚称本片接入。

## 范围核对与防偏离
- 原目录三类型/八阶段导航/项目五阶段不变，治理贯穿。
- 本片是既有轻量执行器可办理上线准备，不把全套Flowable工程藏成已交付；并行/子流程/资源日历不支持仍显式提示。
- M5快照人工来源限制不被M6状态洗绿；上线准备确认不等于运行有效/改善达标，四结论最终授权规则仍M8承接。
- 方法/表单/分派/时限需按任务适用；必要配置遗漏显示待补，未知不默认为不适用。RPA/案例/新技术默认仅参考，选择必需可回查理由，技术登记不证明业务成功。

## Task1 原上线准备办理
Files: models/execution.py、schemas/execution.py、services/execution_readiness.py、api/v1/execution.py；migration；tests/test_execution_readiness.py。
- [x] RED GET /execution/readiness?process_id=返回发布版本原主键、配置事实、准备约定及限制，不写库。
- [x] PUT同路由 MANAGER+ {expected_revision,reviewer_user_id,requirements:{forms,assignments,deadlines},node_requirements:{node_key:{forms/assignments/deadlines}},evidence,rollback_note}；默认约定可按当前原任务覆盖，每项REQUIRED/NOT_APPLICABLE，N/A需理由；保存清本人决定，原审计保留。默认未配置不得报已确认。
- [x] POST /execution/readiness/confirm?process_id= 指定非编辑者本人 {expected_revision,decision ACCEPT/RETURN,evidence}；ACCEPT需真实当前发布、必要配置、证据/回退，固定模型/配置指纹。配置/发布后来变更只读显示待复核，不能靠旧确认放行。
- [x] 旧普通启动兼容；显式round启动需readiness当前已确认、round真实发布模型=当前，身份不可串；不把未确认配置变成全站强制生产准入政策。

## Task2 实例身份与十层适用性
Files: models/execution.py、services/execution.py、schemas/execution.py；pilot.py/service/schema；process_evidence.py；tests。
- [x] RED原实例启动新model_version_id取真实发布行，旧数据不猜回填；可选round_id必须同流程/项目，发布身份匹配。保存进原实例snapshot，旧在途不切换。
- [x] 第6层RPA/运行/案例/技术/挖掘为OPTIONAL，不强造登记；表单等参考项也与上线准备配置分开，原层详情展示required/applicability/reason。
- [x] 原PilotLayer applicability JSON/revision，PUT /pilot/paths/{id}/layers/{no}/applicability 管理权限；只允许该层原key，不能拿N/A豁免核心模型/改善目标。
- [ ] 已有层号advance显式落最终层仍有次要显示缺陷，已记README，不在本片暗称已修。
- [x] path_detail/list纯读，不_ensure_layers、不改path.current_layer；只派生出参；模型/round引用先验证，错误不回落别流程。

## Task3 原执行页UI/验证/偏差记录
Files: views/shared/execution_readiness.js、execution.js、pilot.js；scripts/verify_execution_readiness.py；verify_frontend登记。
- [x] 原执行页选流程可维护准备约定/本人确认，显示模型主键/指纹失效/缺项及原配置动作，不建新导航；pilot第6层不再宣称机器人/新技术必备。
- [x] 真实UI先红后绿：无RPA准备、约定保存刷新/错误保留、本人确认与配置变化待复核（API补负例）、原执行任务完成回归。
- [x] pytest/check、完整前端、独立Alembic check，schema与产品范围分别核对，文档明确实施/延期/缺口及漂移裁定。

## 核验重点
1. 本人决定/非作者与旧revision，管理员不代签；变更指纹失效。
2. round及project不可见404/错流程拒绝，幂等重放不能越权；无round启动兼容。
3. GET绝不写层/创建记录，适用性不抹掉核心要求。
4. 已有实例model主键不回填猜测，发布后旧实例原快照保留。
5. 原页面异步/切流程/modal守卫；技术登记/发布/真实成功分开。
