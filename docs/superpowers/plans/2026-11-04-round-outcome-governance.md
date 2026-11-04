# M8 变革优化与持续治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。承接用户“合并后继续下一步”，不是重开总路线或文案专项。

**Goal:** 在原GateAttestation/培训/标准方法/复制包上固定同轮有权核验、人员操作和持续复盘，投影四种结论而非另造阶段机。
**Architecture:** 原GateAttestation追加round_id、purpose、evidence_snapshot及revision/指定核验身份；四结论读取原决定。原ProcessTrainingRecord补对应版本/轮次的操作核验和责任期限；原ToolSheet/有效标准承载控制复盘；原ReplicationPack冻结源版本与接收决定。20保障只读原事实，不生成任务。
**Tech Stack:** FastAPI、SQLAlchemy2、Alembic、原生ES模块零构建。
**Spec:** docs/implementation-next-brief.md M8；docs/bpm-lifecycle-implementation-spec.md R1-05/R5；process-transformation-practice-system.md；process-organization-governance-loop.md。

## Global Constraints
- 唯一流程目录/八阶段导航/项目五阶段不变；治理贯穿，不编号第九阶段。
- 原项目普通阶段PASS不等于本轮改善达标；管理员不天然业务验收者。
- 事先验收约定、发布身份、冻结口径/前后正式样本不可被看到结果后改写。
- 有改善目标不能标改善达标不适用；停止/取消可结案但不标达标。
- 培训到场≠会操作，分母不明≠采用率；复制接受≠当地已上线。
- Flowable/真实外部业务/组织效果未验证不洗绿，不建OutcomeReview/ControlPlan/ReviewRecord平行主库。

## Review Focus
- 同流程错项目/轮次/模型/口径，验收不能引用；Task1。
- 修改/撤回原决定不漂移历史快照，原PATCH不能绕本人核验；Task1/2。
- 本人/代签/离岗与当前授权不同；Task1/2。
- 复制源新修订不改旧包，接收不覆盖当地模型；Task3。
- 保障缺证/到期/不适用清楚，GET不造20任务；Task4。

### Task 1: 原门禁上的本轮核验与四结论投影
**Files:** models/maturity.py、schemas/maturity.py、services/maturity.py、api/v1/maturity.py、services/improvement_round.py、原项目/轮次UI、migration、tests/test_round_outcome_governance.py。
**Interfaces:** GateAttestation.round_id nullable RESTRICT，purpose（STAGE_GATE/DATA_READY/GO_LIVE_READY/RUN_EFFECTIVE/IMPROVEMENT_MET），evidence_snapshot JSON；原gate接口追加purpose时要求同project/round及事先指定独立审核人当前本人。普通STAGE_GATE仍原语义。
- [x] RED普通PASS不投影改善；缺发布/缺质量/缺可比样本拒确认适用结论；错四身份400/404、自验403、旧revision409。
- [x] GREEN原结论append-only保留原依据快照；round.verification读取原签收，不设current_stage/advance；本轮改善验收未达标与合法项目结案分开。
- [x] 原项目Gate/流程卡办理与刷新，真实两账号，pytest + migration + frontend专项通过。

### Task 2: 原培训的操作核验与控制复盘
**Files:** models/adoption.py、schemas/pilot.py、services/pilot.py、原ToolSheet治理用途增量、原培训/流程卡UI；tests。
**Interfaces:** ProcessTrainingRecord operation JSON、model_version_id/round_id、责任/复核日期；原ToolSheet控制/复盘记录引用本轮原结论、标准、异常与下次动作。
- [x] RED签到不等操作通过；错模型/轮次拒绝；无采用分母标未核；旧决定不由新版本自动继承。
- [x] GREEN原记录保存演练/实际/失败/返训，指定本人操作核对；原控制复盘写责任/期限/例外/反馈和下次复核，不造任务主库。
- [x] pytest + 原UI专项，Expected上述业务断言全部通过。

### Task 3: 原复制包固定来源与接收
**Files:** models/replication.py、schemas/replication.py、services/replication.py、api/v1/replication.py、原复制UI、tests。
**Interfaces:** ReplicationPack.source_snapshot JSON/revision 与原接收决定JSON，源project/round/model/document/template原版本hash；接收指定范围和有权本人。
- [x] RED可变源更新不改旧包；未通过适用验收不得宣传收益；拒绝有依据；接受不改本地运行指针/项目结项。
- [x] GREEN原包办理/引用/范围可见性及审计；无平行接收台账。
- [x] pytest + 原UI专项，Expected固定源与零隐式发布通过。

### Task 4: 五因素20保障只读核验与收尾
**Files:** services/process_card.py原聚合服务、原流程卡/authorization、README/implementation brief、tests及全量前端入口。
- [x] RED缺原章程/RACI/绩效/培训/复盘时显示缺证而非生成20任务；GET数据库零新增/更新；权限过滤覆盖引用/计数。
- [x] GREEN每项只读显示来源/责任/时点/核验/下一步；总体不宣称组织效果已完成。
- [x] check.py、独立Alembic check、当前隔离服务完整verify_frontend；一次整分支复核Important红绿修正，未验证生产/外部/组织事项明确保留。

## 起步核对
原GateAttestation当前仅project/current_stage1–5和evidence_url/conclusion，尚无round_id/核验用途；create_gate只核项目当前阶段与非空链接，不能直接用来宣称独立效果验收。ProcessTrainingRecord当前仅签到，ReplicationPack资产ID仍动态解析。先TDD扩原对象，不为方便另建主库。
