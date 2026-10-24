"""种子数据（业务数据部分）：项目组合、KPI 体系、异常事件、知识库、设计器模型。"""

from __future__ import annotations

# ======================================================================
# 四、流程项目组合
# process 字段填流程编码，灌库时解析为 process_id
# ======================================================================

PROJECTS = [
    dict(
        code="PR-2026-018",
        name="采购需求提报流程重组",
        methodology="BPR",
        status="ACTIVE",
        current_stage=3,
        priority=1,
        process="L3-032",
        owner="陈经理",
        sponsor="采购总监-刘总",
        department="采购部",
        objective="把采购需求从提报到计划生成的端到端周期从 14 天压到 5 天，取消 3 层冗余审批",
        scope="从需求部门发起需求 → 采购部汇总归并 → 财务预算校验 → 需求审批 → 采购计划生成，含驳回回路",
        metric_name="端到端周期",
        baseline_value=14.0,
        target_value=5.0,
        current_value=8.2,
        metric_unit="天",
        budget=42.0,
        actual_cost=28.0,
        roi_estimate=3.4,
        start_date="2026-07-01",
        end_date="2026-12-31",
    ),
    dict(
        code="PR-2026-021",
        name="订单交付周期优化",
        methodology="BPI",
        status="ACTIVE",
        current_stage=4,
        priority=1,
        process="L2-005",
        owner="周经理",
        sponsor="运营副总-钱总",
        department="销售运营部",
        objective="订单交付周期从 9.5 天缩短至 7 天，准时交付率提升 12 个百分点",
        scope="订单接收评审 → 交付计划协调 → 仓储拣货 → 发运结算",
        metric_name="平均交付周期",
        baseline_value=9.5,
        target_value=7.0,
        current_value=7.6,
        metric_unit="天",
        budget=28.0,
        actual_cost=24.0,
        roi_estimate=2.8,
        start_date="2026-06-10",
        end_date="2026-11-30",
    ),
    dict(
        code="PR-2026-024",
        name="生产现场换线改善",
        methodology="LEAN",
        status="ACTIVE",
        current_stage=2,
        priority=2,
        process="L3-045",
        owner="赵厂长",
        sponsor="制造总监-孙总",
        department="制造部",
        objective="换线调机时间从 45 分钟压缩到 20 分钟以内，提升设备稼动率",
        scope="轧制工段换线全过程：停机准备 → 模具更换 → 参数调校 → 首件确认",
        metric_name="平均换线时间",
        baseline_value=45.0,
        target_value=20.0,
        current_value=32.0,
        metric_unit="min",
        budget=18.0,
        actual_cost=9.0,
        roi_estimate=4.1,
        start_date="2026-08-01",
        end_date="2027-01-31",
    ),
    dict(
        code="PR-2026-026",
        name="客户投诉闭环优化",
        methodology="BPI",
        status="CLOSED",
        current_stage=5,
        priority=2,
        process="L3-061",
        owner="吴主管",
        sponsor="客服总监-周总",
        department="客服中心",
        objective="客诉平均闭环时间从 72 小时压缩到 24 小时，一次解决率提升到 94%",
        scope="客诉受理 → 责任判定 → 处理执行 → 客户回访 → 归档",
        metric_name="平均闭环时间",
        baseline_value=72.0,
        target_value=24.0,
        current_value=21.0,
        metric_unit="小时",
        budget=15.0,
        actual_cost=15.0,
        roi_estimate=2.2,
        start_date="2026-05-20",
        end_date="2026-09-30",
    ),
    dict(
        code="PR-2026-029",
        name="费用报销流程重组",
        methodology="BPR",
        status="PLANNING",
        current_stage=1,
        priority=1,
        process="L3-071",
        owner="孙经理",
        sponsor="财务总监-李总",
        department="财务部",
        objective="报销周期从 10 天压到 2 天，退单率从 18% 降到 5% 以内",
        scope="员工提单 → 票据审核 → 部门审批 → 财务复核 → 付款",
        metric_name="平均处理周期",
        baseline_value=10.0,
        target_value=2.0,
        current_value=10.0,
        metric_unit="天",
        budget=35.0,
        actual_cost=6.0,
        roi_estimate=2.9,
        start_date="2026-09-15",
        end_date="2027-03-31",
    ),
    dict(
        code="PR-2026-031",
        name="仓储拣货路径优化",
        methodology="LEAN",
        status="PLANNING",
        current_stage=1,
        priority=3,
        process="L3-054",
        owner="郑主管",
        sponsor="供应链总监-冯总",
        department="仓储部",
        objective="单票拣货时长从 35 分钟降到 22 分钟，拣货差错率降到 0.3% 以下",
        scope="拣货单分配 → 路径规划 → 拣货执行 → 复核打包",
        metric_name="单票拣货时长",
        baseline_value=35.0,
        target_value=22.0,
        current_value=35.0,
        metric_unit="min",
        budget=12.0,
        actual_cost=2.0,
        roi_estimate=3.7,
        start_date="2026-09-20",
        end_date="2027-02-28",
    ),
    dict(
        code="PR-2026-033",
        name="生产计划排程协同优化",
        methodology="HYBRID",
        status="ACTIVE",
        current_stage=3,
        priority=2,
        process="L3-041",
        owner="计划部-排程员",
        sponsor="制造总监-孙总",
        department="计划部",
        objective="排程计划冻结期从 3 天缩短到 1 天，紧急插单率从 11% 降到 8%",
        scope="销售预测 → 主计划 → 周排程 → 日派工，含插单处理规则",
        metric_name="计划冻结期",
        baseline_value=3.0,
        target_value=1.0,
        current_value=2.0,
        metric_unit="天",
        budget=22.0,
        actual_cost=11.0,
        roi_estimate=2.5,
        start_date="2026-07-15",
        end_date="2027-02-28",
    ),
    dict(
        code="PR-2026-035",
        name="订单接收与评审提速",
        methodology="BPI",
        status="ON_HOLD",
        current_stage=2,
        priority=3,
        process="L3-051",
        owner="销售运营-周经理",
        sponsor="运营副总-钱总",
        department="销售运营部",
        objective="订单评审从串行 4 个部门改为并行会签，评审时间从 2 天降到 4 小时",
        scope="订单接收 → 技术可行性 → 产能可行性 → 信用审核 → 评审结论",
        metric_name="订单评审时长",
        baseline_value=48.0,
        target_value=4.0,
        current_value=48.0,
        metric_unit="小时",
        budget=16.0,
        actual_cost=4.0,
        roi_estimate=2.1,
        start_date="2026-08-20",
        end_date="2027-01-31",
    ),
]


# ======================================================================
# 五、流程 KPI 体系（四维度，含 6 个月时序）
# records: (期间, 实际值)
# ======================================================================

KPI_PERIODS = [
    "2026-04-01",
    "2026-05-01",
    "2026-06-01",
    "2026-07-01",
    "2026-08-01",
    "2026-09-01",
]

KPIS = [
    # ---- 效率
    dict(
        code="EFF-01",
        name="采购需求端到端周期",
        dimension="EFFICIENCY",
        direction="LOWER_BETTER",
        unit="天",
        baseline_value=14.0,
        target_value=5.0,
        process="L3-032",
        owner="陈经理",
        description="从需求发起至采购计划生成的平均自然日天数",
        values=[14.0, 13.5, 12.8, 11.6, 9.9, 8.2],
    ),
    dict(
        code="EFF-02",
        name="订单平均交付周期",
        dimension="EFFICIENCY",
        direction="LOWER_BETTER",
        unit="天",
        baseline_value=9.5,
        target_value=7.0,
        process="L2-005",
        owner="周经理",
        description="订单确认至客户签收的平均天数",
        values=[9.5, 9.3, 8.8, 8.4, 8.0, 7.6],
    ),
    dict(
        code="EFF-03",
        name="平均换线时间",
        dimension="EFFICIENCY",
        direction="LOWER_BETTER",
        unit="min",
        baseline_value=45.0,
        target_value=20.0,
        process="L3-045",
        owner="赵厂长",
        description="轧制工段单次换线调机的平均耗时",
        values=[45.0, 44.0, 41.5, 38.0, 34.5, 32.0],
    ),
    dict(
        code="EFF-04",
        name="采购需求审批节点数",
        dimension="EFFICIENCY",
        direction="LOWER_BETTER",
        unit="个",
        baseline_value=4.0,
        target_value=2.0,
        process="L3-032",
        owner="陈经理",
        description="需求提报流程中累计的审批层级数",
        values=[4.0, 4.0, 4.0, 3.0, 3.0, 3.0],
    ),
    dict(
        code="EFF-05",
        name="报销平均处理周期",
        dimension="EFFICIENCY",
        direction="LOWER_BETTER",
        unit="天",
        baseline_value=10.0,
        target_value=2.0,
        process="L3-071",
        owner="孙经理",
        description="员工提交报销单至款项到账的平均天数",
        values=[10.0, 10.0, 9.8, 10.0, 9.5, 10.0],
    ),
    # ---- 质量
    dict(
        code="QUA-01",
        name="准时交付率 OTD",
        dimension="QUALITY",
        direction="HIGHER_BETTER",
        unit="%",
        baseline_value=76.0,
        target_value=95.0,
        process="L2-005",
        owner="周经理",
        description="按承诺日期交付的订单占比",
        values=[76.0, 79.0, 82.0, 84.0, 86.0, 88.0],
    ),
    dict(
        code="QUA-02",
        name="一次合格率",
        dimension="QUALITY",
        direction="HIGHER_BETTER",
        unit="%",
        baseline_value=94.0,
        target_value=99.0,
        process="L3-044",
        owner="赵厂长",
        description="退火分切工序一次交检合格的产品占比",
        values=[94.0, 95.0, 95.6, 96.2, 96.8, 97.2],
    ),
    dict(
        code="QUA-03",
        name="客诉重复发生率",
        dimension="QUALITY",
        direction="LOWER_BETTER",
        unit="%",
        baseline_value=12.0,
        target_value=2.0,
        process="L3-061",
        owner="吴主管",
        description="同一根因重复发生客诉的比例",
        values=[12.0, 9.5, 7.0, 5.2, 3.8, 3.0],
    ),
    dict(
        code="QUA-04",
        name="报销退单率",
        dimension="QUALITY",
        direction="LOWER_BETTER",
        unit="%",
        baseline_value=18.0,
        target_value=5.0,
        process="L3-071",
        owner="孙经理",
        description="因票据或填写不合规被退回的比例",
        values=[18.0, 18.5, 19.0, 18.2, 17.6, 18.0],
    ),
    # ---- 成本
    dict(
        code="CST-01",
        name="单笔采购需求处理成本",
        dimension="COST",
        direction="LOWER_BETTER",
        unit="元",
        baseline_value=210.0,
        target_value=120.0,
        process="L3-032",
        owner="陈经理",
        description="需求提报全流程的人工与系统分摊成本",
        values=[210.0, 205.0, 196.0, 178.0, 152.0, 138.0],
    ),
    dict(
        code="CST-02",
        name="客诉处理单案成本",
        dimension="COST",
        direction="LOWER_BETTER",
        unit="元",
        baseline_value=860.0,
        target_value=600.0,
        process="L3-061",
        owner="吴主管",
        description="单起客诉的处理、赔付与差旅成本合计",
        values=[860.0, 820.0, 760.0, 700.0, 648.0, 620.0],
    ),
    dict(
        code="CST-03",
        name="换线损失成本",
        dimension="COST",
        direction="LOWER_BETTER",
        unit="万元/月",
        baseline_value=6.2,
        target_value=2.8,
        process="L3-045",
        owner="赵厂长",
        description="因换线停机导致的产能损失折算金额",
        values=[6.2, 6.0, 5.6, 5.0, 4.3, 3.9],
    ),
    # ---- 灵活性
    dict(
        code="FLX-01",
        name="紧急插单率",
        dimension="FLEXIBILITY",
        direction="LOWER_BETTER",
        unit="%",
        baseline_value=18.0,
        target_value=8.0,
        process="L2-005",
        owner="周经理",
        description="订单总量中需要紧急调整排程的占比",
        values=[18.0, 17.2, 15.8, 14.0, 12.4, 11.0],
    ),
    dict(
        code="FLX-02",
        name="工艺变更响应周期",
        dimension="FLEXIBILITY",
        direction="LOWER_BETTER",
        unit="天",
        baseline_value=7.0,
        target_value=3.0,
        process="L3-011",
        owner="工艺部-主管",
        description="客户提出工艺调整需求至方案确认的天数",
        values=[7.0, 7.0, 6.5, 6.0, 5.4, 5.0],
    ),
    dict(
        code="FLX-03",
        name="需求变更响应周期",
        dimension="FLEXIBILITY",
        direction="LOWER_BETTER",
        unit="小时",
        baseline_value=48.0,
        target_value=12.0,
        process="L3-051",
        owner="周经理",
        description="客户订单变更确认所需平均时长",
        values=[48.0, 46.0, 42.0, 36.0, 30.0, 26.0],
    ),
    # ---- 健康度
    dict(
        code="HLT-01",
        name="关键控制执行率",
        dimension="QUALITY",
        direction="HIGHER_BETTER",
        unit="%",
        baseline_value=70.0,
        target_value=98.0,
        process="L3-032",
        owner="流程管理科",
        description="按标准完成的关键控制点数占应完成控制点的比例",
        values=[70.0, 74.0, 80.0, 85.0, 90.0, 93.0],
    ),
]


# ======================================================================
# 五（续）、KPI 定义卡
#
# `KPIS` 只保留展示与目标；定义卡单独维护，保证每个指标都能回答
# “公式是什么、数据从哪来、什么算红/黄/绿、由谁负责”。
# runner 会按 code 强制匹配：新增 KPI 没写定义卡会直接报错。
# ======================================================================

KPI_DEFINITION_CARDS = {
    "EFF-01": dict(
        kind="PROCESS",
        formula="Σ(需求发起时间 → 采购计划生成时间) ÷ 完成采购计划的需求单数",
        numerator="需求发起至采购计划生成的自然日合计",
        denominator="完成采购计划的需求单数",
        granularity="每张采购需求 / 月",
        frequency="MONTHLY",
        source_system="ERP 采购模块 + OA 审批",
        quality_rule="剔除撤销与重提需求；以首次提报时间计算",
        red_threshold=11.3,
        yellow_threshold=8.2,
        green_threshold=5.0,
        valid_from="2026-01-01",
    ),
    "EFF-02": dict(
        kind="PROCESS",
        formula="Σ(订单确认时间 → 客户签收时间) ÷ 签收订单数",
        numerator="订单确认至客户签收的天数合计",
        denominator="已签收订单数",
        granularity="每张订单 / 月",
        frequency="MONTHLY",
        source_system="ERP 销售 + WMS 出库",
        quality_rule="剔除内部订单与样品单；以客户签收时间为准",
        red_threshold=8.8,
        yellow_threshold=7.9,
        green_threshold=7.0,
        valid_from="2026-01-01",
    ),
    "EFF-03": dict(
        kind="PROCESS",
        formula="Σ换线调机耗时 ÷ 换线次数",
        numerator="换线调机耗时合计（分钟）",
        denominator="计划内换线次数",
        granularity="工段 / 月",
        frequency="MONTHLY",
        source_system="MES 设备事件",
        quality_rule="仅统计计划内换线；异常停机不计入",
        red_threshold=37.5,
        yellow_threshold=28.8,
        green_threshold=20.0,
        valid_from="2026-01-01",
    ),
    "EFF-04": dict(
        kind="PROCESS",
        formula="审批节点数（按已发布流程版本计数）",
        numerator="流程版本中的审批节点数",
        denominator="1（按版本计数）",
        granularity="流程版本",
        frequency="MONTHLY",
        source_system="BPM 流程模型",
        quality_rule="以已发布版本为准；草稿不计",
        red_threshold=3.4,
        yellow_threshold=2.7,
        green_threshold=2.0,
        valid_from="2026-01-01",
    ),
    "EFF-05": dict(
        kind="PROCESS",
        formula="Σ(报销提交 → 款项到账) ÷ 报销单数",
        numerator="报销提交至款项到账的天数合计",
        denominator="已到账报销单数",
        granularity="每张报销单 / 月",
        frequency="MONTHLY",
        source_system="OA + 财务系统",
        quality_rule="剔除退回重提；以首次提交时间计算",
        red_threshold=7.6,
        yellow_threshold=4.8,
        green_threshold=2.0,
        valid_from="2026-01-01",
    ),
    "QUA-01": dict(
        kind="RESULT",
        formula="按时、足额、无争议、无缺陷订单数 ÷ 总订单数 × 100%",
        numerator="按时、足额、无争议、无缺陷的订单数",
        denominator="总订单数",
        granularity="订单 / 周",
        frequency="WEEKLY",
        source_system="ERP 销售 + CRM",
        quality_rule="以承诺交付日为准；客户书面豁免不计逾期",
        red_threshold=82.7,
        yellow_threshold=89.3,
        green_threshold=95.0,
        valid_from="2026-01-01",
    ),
    "QUA-02": dict(
        kind="RESULT",
        formula="首次交检合格数量 ÷ 交检数量 × 100%",
        numerator="首次交检合格数量",
        denominator="交检数量",
        granularity="工序 / 日",
        frequency="DAILY",
        source_system="MES / QMS",
        quality_rule="按工序检验记录；返工后合格不计首次合格",
        red_threshold=95.0,
        yellow_threshold=96.5,
        green_threshold=97.0,
        valid_from="2026-01-01",
    ),
    "QUA-03": dict(
        kind="RESULT",
        formula="同一根因重复客诉数 ÷ 客诉总数 × 100%",
        numerator="同一根因重复发生的客诉数",
        denominator="客诉总数",
        granularity="客诉 / 月",
        frequency="MONTHLY",
        source_system="CRM 客诉系统",
        quality_rule="根因编码必须与历史客诉可关联",
        red_threshold=9.0,
        yellow_threshold=5.5,
        green_threshold=2.0,
        valid_from="2026-01-01",
    ),
    "QUA-04": dict(
        kind="PROCESS",
        formula="被退回报销单数 ÷ 提交报销单数 × 100%",
        numerator="因票据或填写不合规被退回的报销单数",
        denominator="提交报销单数",
        granularity="报销单 / 月",
        frequency="MONTHLY",
        source_system="OA + 财务系统",
        quality_rule="同一单多次退回只计一次",
        red_threshold=14.1,
        yellow_threshold=9.6,
        green_threshold=5.0,
        valid_from="2026-01-01",
    ),
    "CST-01": dict(
        kind="RESULT",
        formula="需求提报全流程人工与系统分摊成本 ÷ 需求单数",
        numerator="人工成本 + 系统分摊成本",
        denominator="完成提报的需求单数",
        granularity="需求单 / 月",
        frequency="MONTHLY",
        source_system="财务系统 + ERP",
        quality_rule="按作业成本法分摊；不含资本化投入",
        red_threshold=183.0,
        yellow_threshold=151.5,
        green_threshold=120.0,
        valid_from="2026-01-01",
    ),
    "CST-02": dict(
        kind="RESULT",
        formula="客诉处理、赔付与差旅成本合计 ÷ 客诉单数",
        numerator="处理成本 + 赔付 + 差旅",
        denominator="客诉单数",
        granularity="客诉 / 月",
        frequency="MONTHLY",
        source_system="财务系统 + CRM",
        quality_rule="赔付以实际支付为准；预计负债不计",
        red_threshold=782.0,
        yellow_threshold=691.0,
        green_threshold=600.0,
        valid_from="2026-01-01",
    ),
    "CST-03": dict(
        kind="RESULT",
        formula="换线停机时间 × 单位产能损失",
        numerator="换线停机时间",
        denominator="单位时间产能损失（万元/小时）",
        granularity="工段 / 月",
        frequency="MONTHLY",
        source_system="MES + 财务系统",
        quality_rule="仅计计划内换线；异常停机单列",
        red_threshold=5.2,
        yellow_threshold=4.0,
        green_threshold=2.8,
        valid_from="2026-01-01",
    ),
    "FLX-01": dict(
        kind="PROCESS",
        formula="紧急插单数 ÷ 订单总数 × 100%",
        numerator="需要紧急调整排程的订单数",
        denominator="订单总数",
        granularity="订单 / 月",
        frequency="MONTHLY",
        source_system="ERP 销售",
        quality_rule="紧急插单需有审批记录",
        red_threshold=15.0,
        yellow_threshold=11.5,
        green_threshold=8.0,
        valid_from="2026-01-01",
    ),
    "FLX-02": dict(
        kind="PROCESS",
        formula="Σ(工艺变更需求提出 → 方案确认) ÷ 变更单数",
        numerator="工艺变更需求提出至方案确认的天数合计",
        denominator="变更单数",
        granularity="变更单 / 月",
        frequency="MONTHLY",
        source_system="PLM / OA",
        quality_rule="以客户书面需求时间为起点",
        red_threshold=5.8,
        yellow_threshold=4.4,
        green_threshold=3.0,
        valid_from="2026-01-01",
    ),
    "FLX-03": dict(
        kind="PROCESS",
        formula="Σ(订单变更提出 → 确认) ÷ 变更单数",
        numerator="订单变更提出至确认的小时数合计",
        denominator="变更单数",
        granularity="变更单 / 月",
        frequency="MONTHLY",
        source_system="ERP + CRM",
        quality_rule="不含客户撤回的变更",
        red_threshold=37.2,
        yellow_threshold=24.6,
        green_threshold=12.0,
        valid_from="2026-01-01",
    ),
    "HLT-01": dict(
        kind="HEALTH",
        formula="按标准完成的关键控制点数 ÷ 应完成的关键控制点数 × 100%",
        numerator="按标准完成的关键控制点数",
        denominator="应完成的关键控制点数",
        granularity="流程 / 月",
        frequency="MONTHLY",
        source_system="BPM 审计 + 内控检查",
        quality_rule="控制点必须有执行证据；抽样复核 10%",
        red_threshold=80.0,
        yellow_threshold=88.0,
        green_threshold=92.0,
        valid_from="2026-01-01",
    ),
}


# ======================================================================
# 六、异常事件（含已闭环与未闭环）
# ======================================================================

EXCEPTIONS = [
    dict(
        code="EXC-2026-001",
        title="采购需求审批连续 3 周超时",
        description="需求审批环节平均滞留 2.1 天，超过 1 天红线，主要卡在部门负责人出差期间无代理人",
        severity="HIGH",
        status="IN_PROGRESS",
        process="L4-204",
        project="PR-2026-018",
        owner="陈经理",
        detected_at="2026-09-08 09:20:00",
        due_at="2026-10-15 18:00:00",
        root_cause="审批人无授权代理人，且审批未设置超时提醒与自动流转",
        action_taken="已推动设置 24 小时超时自动提醒，代理人机制本周内落地",
    ),
    dict(
        code="EXC-2026-002",
        title="订单准时交付率连续两月低于 90%",
        description="9 月 OTD 为 88%，连续两月未达 90% 目标，集中在华东区小批量订单",
        severity="HIGH",
        status="IN_PROGRESS",
        process="L2-005",
        project="PR-2026-021",
        owner="周经理",
        detected_at="2026-10-06 08:30:00",
        due_at="2026-10-31 18:00:00",
        root_cause="小批量订单在排程中被大批量订单持续插队，缺少最小批量的交付保障规则",
        action_taken="正在制定小批量订单绿色通道规则，计划 10 月底试运行",
    ),
    dict(
        code="EXC-2026-003",
        title="报销流程单据退回率反弹",
        description="9 月退单率回升至 18%，主要因新票据规范发布后一线未同步知晓",
        severity="MEDIUM",
        status="OPEN",
        process="L3-071",
        project="PR-2026-029",
        owner="孙经理",
        detected_at="2026-10-08 14:10:00",
        due_at="2026-11-10 18:00:00",
        root_cause=None,
        action_taken=None,
    ),
    dict(
        code="EXC-2026-004",
        title="轧制工段换线时间波动异常",
        description="换线时间标准差由 4 分钟扩大到 9 分钟，存在特殊原因波动",
        severity="MEDIUM",
        status="IN_PROGRESS",
        process="L3-045",
        project="PR-2026-024",
        owner="赵厂长",
        detected_at="2026-09-25 16:40:00",
        due_at="2026-10-25 18:00:00",
        root_cause="夜班与白班的换线作业标准不一致，夜班依赖老师傅经验",
        action_taken="已完成白班标准作业视频录制，正在推进夜班同步培训",
    ),
    dict(
        code="EXC-2026-005",
        title="供应商来料检验积压",
        description="到货验收节点待检批次积压达 42 批，平均等待 1.8 天",
        severity="MEDIUM",
        status="OPEN",
        process="L3-035",
        project=None,
        owner="仓储部-QC",
        detected_at="2026-10-12 10:05:00",
        due_at="2026-11-05 18:00:00",
        root_cause=None,
        action_taken=None,
    ),
    dict(
        code="EXC-2026-006",
        title="客诉闭环流程超时归零",
        description="客诉平均闭环时间 21 小时，达标且稳定运行 3 个月，可解除重点监控",
        severity="LOW",
        status="CLOSED",
        process="L3-061",
        project="PR-2026-026",
        owner="吴主管",
        detected_at="2026-08-01 09:00:00",
        due_at=None,
        root_cause="原根因为责任判定环节缺少标准，已通过建立责任判定矩阵解决",
        action_taken="流程已移交流程 Owner 常态化运营，纳入季度评审",
    ),
    dict(
        code="EXC-2026-007",
        title="生产计划冻结期内插单超限",
        description="9 月冻结期内插单 7 次，超出每月 3 次的上限约定",
        severity="HIGH",
        status="RESOLVED",
        process="L3-041",
        project="PR-2026-033",
        owner="计划部-排程员",
        detected_at="2026-09-18 11:30:00",
        due_at="2026-10-10 18:00:00",
        root_cause="销售端缺少插单成本可视化，插单未纳入考核",
        action_taken="已上线插单成本看板，并将插单次数纳入销售区域负责人月度考核",
    ),
    dict(
        code="EXC-2026-008",
        title="采购计划回退率偏高",
        description="采购计划回退修改占比 35%，高于 15% 的控制线",
        severity="HIGH",
        status="IN_PROGRESS",
        process="L3-032",
        project="PR-2026-018",
        owner="采购部-计划员",
        detected_at="2026-09-30 15:00:00",
        due_at="2026-10-20 18:00:00",
        root_cause="需求汇总阶段未校核最小起订量与库存水位，到计划生成阶段才发现冲突",
        action_taken="正在把最小起订量校验前移到需求汇总环节",
    ),
]


# ======================================================================
# 七、流程知识库
# ======================================================================

KNOWLEDGE = [
    dict(
        created="2026-09-10 10:30:00",
        title="BPR 实施七步法标准模板",
        type="TEMPLATE",
        methodology="BPR",
        tags=["BPR", "标准流程", "立项"],
        tool_code="BPR6",
        author="流程管理科",
        summary="适用于流程根本性重组项目，含立项章程、目标设定、配套方案模板与决策门检查清单",
        content=(
            "本模板按 BPR 七步法组织：①确立愿景与变革目标 ②识别核心流程 ③现状流程诊断 ④重新设计流程 "
            "⑤配套设计（组织/IT/绩效/制度）⑥试点与推广 ⑦持续改进与固化。\n\n"
            "每一步都附有产出物模板与决策门（Gate）检查项。使用要点：\n"
            "1. 第②步用「价值贡献度 × 痛点严重度」矩阵筛选，不要对所有流程平均用力；\n"
            "2. 第④步必须同时产出「理想态」与「可落地态」两版方案；\n"
            "3. 每个决策门未通过时，宁可停下来补齐，也不要带病进入下一步。"
        ),
        download_count=128,
    ),
    dict(
        created="2026-08-22 14:15:00",
        title="价值流图 VSM 绘制与解读手册",
        type="BEST_PRACTICE",
        methodology="LEAN",
        tags=["VSM", "诊断", "周期效率"],
        tool_code="VSM",
        author="制造部-赵厂长",
        summary="手把手教你画现状／未来状态价值流图，附铜加工行业实例与时间观测表",
        content=(
            "核心公式：PCE（流程周期效率）= 增值时间 ÷ 端到端周期时间。\n\n"
            "绘制步骤：选代表产品 → 现场实测每个环节的作业时间与等待时间 → 标注信息流 → "
            "标出爆炸点（等待/返工/搬运）→ 绘制未来状态图。\n\n"
            "本厂轧制工段实测数据：端到端 6.4 天，其中增值时间 42 分钟，PCE 约 1.1%。"
            "最大的浪费不是加工慢，而是批次间的排队等待。\n\n"
            "常见错误：用系统里的标准工时替代现场实测。标准工时经过多次「优化」已经失真，"
            "会系统性地抹掉等待时间，导致 PCE 虚高、改善点被忽略。"
        ),
        download_count=96,
    ),
    dict(
        created="2026-09-18 16:40:00",
        title="采购需求提报重组项目复盘",
        type="CASE",
        methodology="BPR",
        tags=["案例", "BPR", "采购", "周期压缩"],
        tool_code="BPR6",
        author="陈经理",
        summary="端到端周期从 14 天压缩至 8.2 天，含方案选择过程与踩坑记录",
        content=(
            "背景：采购需求提报端到端 14 天，其中等待占 85.7%，PCE 仅 8%，审批累计 4 层，跨部门移交 5 次。\n\n"
            "方案选择：先用加权决策矩阵对比三套方案——\n"
            "A 局部优化（简化表单）：预计改善 12%，投入 5 万；\n"
            "B 端到端重设（决策下沉 + 并行审批）：预计改善 60%，投入 42 万；\n"
            "C 完全外包：预计改善 70%，但合规风险高。\n"
            "最终选 B，权重由采购总监与财务总监共同确定。\n\n"
            "已实现：周期 14 天 → 8.2 天（-41%），审批层级 4 → 3，仍在推进。\n\n"
            "踩坑记录：\n"
            "1. 最初想跳过变革准备度评估直接推广，结果财务部预算会计强烈抵触——"
            "因为预算校验前移后他的工作量增加了。后来通过把校验做成系统自动比对才化解；\n"
            "2. 试点期没有记录真实耗时，被质疑「以前也一直这么干」，"
            "补做了两周时间观测才拿到数据支撑。"
        ),
        download_count=74,
    ),
    dict(
        created="2026-07-30 09:05:00",
        title="RACI 权责矩阵模板（含示例）",
        type="TEMPLATE",
        methodology=None,
        tags=["RACI", "权责", "设计"],
        tool_code="RACI",
        author="流程管理科",
        summary="可直接套用的 RACI 模板，含跨部门权责冲突处理建议",
        content=(
            "填写规则：\n"
            "R（Responsible）执行者——可以有多个；\n"
            "A（Accountable）最终批准者——**每个活动有且仅有一个**；\n"
            "C（Consulted）事前咨询者——双向沟通；\n"
            "I（Informed）事后知会者——单向通知。\n\n"
            "自查清单：\n"
            "□ 是否存在没有任何 R 的活动？\n"
            "□ 是否存在多个 A？\n"
            "□ 是否有整列全是 C/I 的部门？（说明该部门被架空，后续必然消极抵制）\n"
            "□ 审批链是否超过 3 层？超过就要考虑决策下沉。\n\n"
            "冲突处理：当两个部门都认为自己应该是 A 时，"
            "回到「谁对这条流程的最终结果负责、谁承担后果」这一标准来判断，由上一级拍板。"
        ),
        download_count=211,
    ),
    dict(
        created="2026-08-05 11:20:00",
        title="ADKAR 变革管理推进指南",
        type="BEST_PRACTICE",
        methodology="BPR",
        tags=["变革管理", "ADKAR", "阻力"],
        tool_code="ADKAR",
        author="流程管理科",
        summary="中层抵触如何化解、沟通节奏如何设计、采纳率如何度量",
        content=(
            "核心判断：流程变革失败 80% 源于人的阻力，而非方案缺陷。\n\n"
            "最常见的错误是跳过 A（意识）和 D（欲望）直接做 K（知识）培训——"
            "结果是员工学会了新流程，但根本不想用。\n\n"
            "中层管理者是关键：他们往往在变革中失去审批权与信息优势，"
            "抵触通常不会明说，而是表现为「配合但不动」。识别方法是看执行数据，"
            "不看态度表态。\n\n"
            "采纳率度量建议：\n"
            "- 系统路径采纳率：走新流程的单据占比；\n"
            "- 例外率：仍走线下/特批的占比；\n"
            "- 执行时长分布：是否收敛到新标准附近。\n\n"
            "沟通节奏：启动期高频（每周），推广期稳定（每两周），"
            "稳定期转为常规定期。切忌只在启动时宣讲一次。"
        ),
        download_count=63,
    ),
    dict(
        created="2026-09-01 15:50:00",
        title="精益改善周 Kaizen 操作手册",
        type="BEST_PRACTICE",
        methodology="LEAN",
        tags=["精益", "Kaizen", "现场改善"],
        tool_code="KAIZEN",
        author="制造部-赵厂长",
        summary="5 天改善周的日程安排、人员配置、产出物清单",
        content=(
            "改善周的价值在于「快」：5 天出可验证成果，用事实建立变革信心。\n\n"
            "前期准备（2–4 周，决定成败）：锁定改善区域、收集基线数据、"
            "确定跨职能团队（含一线操作工，必须）、明确量化目标。\n\n"
            "日程：\n"
            "Day 1 现场观察与浪费识别；\n"
            "Day 2–3 设计并**现场动手实施**（不做长篇报告）；\n"
            "Day 4 试运行与测量；\n"
            "Day 5 成果发布、标准化、确定 30/60/90 天跟进责任人。\n\n"
            "人员配置：组长 1 名（有决策权）、核心成员 5–7 名（跨职能）、"
            "一线操作工 2–3 名、 facilitator 1 名。\n\n"
            "最大的坑：把改善周做成「写报告周」。核心是动手改，报告是副产品。"
        ),
        download_count=52,
    ),
    dict(
        created="2026-09-25 10:10:00",
        title="客户投诉闭环流程优化案例",
        type="CASE",
        methodology="BPI",
        tags=["案例", "BPI", "客诉", "跨部门"],
        tool_code="PARETO",
        author="吴主管",
        summary="闭环时间 72 小时 → 21 小时，一次解决率提升至 94%，已推广至全公司",
        content=(
            "诊断发现：72 小时的闭环时间中，真正处理问题只有 4 小时，"
            "其余 68 小时消耗在「责任判定扯皮」上。\n\n"
            "根因（帕累托分析）：78% 的扯皮集中在 3 类客诉的定责上，"
            "而这三类占全部客诉的 22%。\n\n"
            "对策：建立「责任判定矩阵」——按客诉现象直接映射到责任部门，"
            "取消逐案开会定责；争议案例才走升级流程。同时对重复发生的三类客诉做源头改善。\n\n"
            "成效：闭环 72h → 21h，一次解决率 82% → 94%，重复投诉率 12% → 3%。\n"
            "项目已于 2026-09 结项，移交客服中心常态化运营，纳入季度评审。"
        ),
        download_count=58,
    ),
    dict(
        created="2026-09-05 13:30:00",
        title="流程 KPI 平衡计分卡设计规范",
        type="STANDARD",
        methodology=None,
        tags=["KPI", "监控", "标准"],
        tool_code="BALANCED-SCORE",
        author="流程管理科",
        summary="效率／质量／成本／灵活性四维度指标的设计口径与不超过 5 个指标的取舍原则",
        content=(
            "设计原则：\n"
            "1. 每个流程的 KPI 总数不超过 5 个，每维度 1–2 个。指标多了注意力被稀释，"
            "最终没人对结果负责；\n"
            "2. 必须同时写清基线值、目标值与统计口径（口径不一致的指标等于没有指标）；\n"
            "3. 明确指标方向与数据来源系统，能自动采集的绝不用人工填报；\n"
            "4. 每个指标必须有责任人，且责任人在其考核中能看到它。\n\n"
            "四维度参考指标：\n"
            "效率——周期时间、通过率、自动化率；\n"
            "质量——差错率、返工率、合规率；\n"
            "成本——流程运营成本、单笔处理成本；\n"
            "灵活性——变更响应时间、定制化能力。\n\n"
            "反模式：设计 15 个指标、全部人工填报、没有责任人——"
            "这种看板上线三个月后就会变成无人查看的摆设。"
        ),
        download_count=87,
    ),
    dict(
        created="2026-08-15 17:00:00",
        title="试点设计模板与回滚预案",
        type="TEMPLATE",
        methodology=None,
        tags=["试点", "落地", "风险"],
        tool_code="PILOT",
        author="流程管理科",
        summary="试点单元怎么选、成功标准怎么定、什么条件下回滚",
        content=(
            "试点单元选择三原则（缺一不可）：业务典型、领导支持、风险可控。\n"
            "- 拿最难啃的单位试点，一旦失败整个项目被否定；\n"
            "- 拿最轻松的单位试点，验证不出任何真问题。\n\n"
            "成功标准必须在试点开始前写死：量化指标（周期、差错率）+ 定性反馈"
            "（一线愿不愿意用）。事后定标准的试点，等于没有试点。\n\n"
            "回滚预案必须包含：\n"
            "□ 量化触发条件（关键指标恶化超过 X%、系统故障超过 N 小时）\n"
            "□ 唯一的回滚决策人\n"
            "□ 可执行的回退步骤（含数据回滚与人工补偿）\n"
            "□ 上线前完成一次回滚演练\n\n"
            "提醒：写了没演练的回滚预案，在真正需要时是不可执行的。"
        ),
        download_count=41,
    ),
]


# ======================================================================
# 八、流程设计器：已建模的流程
# 灌库时自动按泳道顺序分配 sequence_order 与画布坐标
# ======================================================================

DESIGN_MODELS = {
    # 采购需求提报 —— 项目的重点改善对象，指标很「难看」，正好演示诊断能力
    "L3-032": dict(
        nodes=[
            dict(
                key="n1",
                name="需求发起与归集",
                type="TASK",
                lane="需求部门",
                owner="申请人",
                dur=120,
                wait=180,
                cost=5,
                rework=0.0,
                levels=0,
                va=True,
            ),
            dict(
                key="n2",
                name="需求汇总与归并",
                type="TASK",
                lane="采购部",
                owner="采购计划员",
                dur=240,
                wait=1200,
                cost=12,
                rework=0.25,
                levels=0,
                va=True,
            ),
            dict(
                key="n3",
                name="预算占用校验",
                type="APPROVAL",
                lane="财务部",
                owner="预算会计",
                dur=120,
                wait=1500,
                cost=8,
                rework=0.0,
                levels=1,
                va=False,
            ),
            dict(
                key="n4",
                name="需求审批",
                type="APPROVAL",
                lane="部门负责人",
                owner="部门负责人",
                dur=60,
                wait=2100,
                cost=10,
                rework=0.0,
                levels=3,
                va=False,
            ),
            dict(
                key="n5",
                name="采购计划生成",
                type="TASK",
                lane="采购计划员",
                owner="采购计划员",
                dur=180,
                wait=480,
                cost=6,
                rework=0.0,
                levels=0,
                va=True,
            ),
            dict(
                key="n6",
                name="计划回退与修改",
                type="TASK",
                lane="采购部",
                owner="采购计划员",
                dur=240,
                wait=300,
                cost=9,
                rework=0.35,
                levels=0,
                va=False,
            ),
        ],
        edges=[
            dict(src="n1", dst="n2", label=None, condition=None, p=1.0),
            dict(src="n2", dst="n3", label=None, condition=None, p=1.0),
            dict(src="n3", dst="n4", label=None, condition=None, p=1.0),
            dict(src="n4", dst="n5", label="通过", condition="预算与需求均合规", p=0.7),
            dict(src="n4", dst="n6", label="驳回", condition="预算不足或需求描述不清", p=0.3),
            dict(src="n6", dst="n2", label="重新提交", condition=None, p=1.0),
        ],
    ),
    # 询比价与招标 —— 与原型 index-sample.html 的设计器视图一致
    "L3-033": dict(
        nodes=[
            dict(
                key="n1",
                name="确认技术规格",
                type="START",
                lane="需求部门",
                owner="申请人",
                dur=120,
                wait=240,
                cost=6,
                rework=0.1,
                levels=0,
                va=True,
            ),
            dict(
                key="n2",
                name="发布询价/招标公告",
                type="TASK",
                lane="采购部",
                owner="采购员",
                dur=480,
                wait=480,
                cost=15,
                rework=0.0,
                levels=0,
                va=True,
            ),
            dict(
                key="n3",
                name="供应商筛选",
                type="APPROVAL",
                lane="采购部",
                owner="采购员",
                dur=960,
                wait=960,
                cost=20,
                rework=0.05,
                levels=1,
                va=True,
            ),
            dict(
                key="n4",
                name="商务谈判",
                type="TASK",
                lane="采购部",
                owner="采购员",
                dur=960,
                wait=1440,
                cost=35,
                rework=0.1,
                levels=0,
                va=True,
            ),
            dict(
                key="n5",
                name="参与评标",
                type="TASK",
                lane="需求部门",
                owner="申请人",
                dur=240,
                wait=1440,
                cost=10,
                rework=0.0,
                levels=0,
                va=True,
            ),
            dict(
                key="n6",
                name="预算校验",
                type="APPROVAL",
                lane="财务部",
                owner="预算会计",
                dur=240,
                wait=1440,
                cost=8,
                rework=0.0,
                levels=1,
                va=False,
            ),
            dict(
                key="n7",
                name="价格合理性审核",
                type="TASK",
                lane="财务部",
                owner="成本会计",
                dur=240,
                wait=960,
                cost=10,
                rework=0.15,
                levels=0,
                va=False,
            ),
            dict(
                key="n8",
                name="定标审批",
                type="APPROVAL",
                lane="采购部",
                owner="采购总监",
                dur=480,
                wait=2880,
                cost=25,
                rework=0.0,
                levels=3,
                va=False,
            ),
            dict(
                key="n9",
                name="合同条款审核",
                type="TASK",
                lane="法务/合规",
                owner="法务专员",
                dur=480,
                wait=1440,
                cost=18,
                rework=0.2,
                levels=0,
                va=True,
            ),
            dict(
                key="n10",
                name="合规备案",
                type="END",
                lane="法务/合规",
                owner="法务专员",
                dur=120,
                wait=480,
                cost=4,
                rework=0.0,
                levels=0,
                va=False,
            ),
        ],
        edges=[
            dict(src="n1", dst="n2", label=None, condition=None, p=1.0),
            dict(src="n2", dst="n3", label=None, condition=None, p=1.0),
            dict(src="n3", dst="n4", label="入围", condition="资质与技术符合", p=0.6),
            dict(src="n3", dst="n2", label="流标重发", condition="入围不足 3 家", p=0.4),
            dict(src="n4", dst="n5", label=None, condition=None, p=1.0),
            dict(src="n5", dst="n6", label=None, condition=None, p=1.0),
            dict(src="n6", dst="n7", label=None, condition=None, p=1.0),
            dict(src="n7", dst="n8", label=None, condition=None, p=1.0),
            dict(src="n8", dst="n9", label="定标", condition=None, p=1.0),
            dict(src="n9", dst="n10", label=None, condition=None, p=1.0),
        ],
    ),
}


# ======================================================================
# 九、演示用户
# 口令是明文写在这里的，仅供本地演示；首次登录后请立即改口令，
# 生产环境的账号应通过管理接口创建。
# ======================================================================

USERS = [
    dict(
        username="admin",
        password="admin123",
        display_name="系统管理员",
        role="ADMIN",
        department="信息中心",
    ),
    dict(
        username="manager",
        password="manager123",
        display_name="流程管理科",
        role="MANAGER",
        department="流程管理科",
    ),
    dict(
        username="chen",
        password="chen123",
        display_name="陈经理",
        role="OWNER",
        department="采购部",
    ),
    dict(
        username="viewer",
        password="viewer123",
        display_name="只读访客",
        role="VIEWER",
        department="观察员",
    ),
]
