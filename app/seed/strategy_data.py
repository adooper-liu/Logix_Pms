"""演示用战略目标与承接关系。

这些目标是匿名化的演示数据，用来展示「目标 → L1/L2/L3 → KPI」的反查；
生产环境应由战略委员会批准后录入，不能直接照搬。
"""

STRATEGY_OBJECTIVES = [
    dict(
        code="OBJ-2026-01",
        name="采购需求端到端周期缩短 50%",
        description="从需求发起到采购计划生成的平均周期由 14 天降到 5 天，"
        "重点消除审批等待与需求返工。",
        year=2026,
        period="ANNUAL",
        baseline_value=14.0,
        target_value=5.0,
        unit="天",
        source_document="2026 年度经营计划 · 必赢之战 2",
        owner="陈经理",
        status="ACTIVE",
        links=[
            dict(process="L3-032", kpi="EFF-01", note="端到端周期主指标"),
            dict(process="L4-202", note="需求汇总环节"),
        ],
    ),
    dict(
        code="OBJ-2026-02",
        name="订单准时交付率达到 95%",
        description="按承诺日期交付的订单占比从 76% 提升到 95%，同时控制紧急插单对排程的冲击。",
        year=2026,
        period="ANNUAL",
        baseline_value=76.0,
        target_value=95.0,
        unit="%",
        source_document="2026 年度经营计划 · 客户价值",
        owner="周经理",
        status="ACTIVE",
        links=[
            dict(process="L2-005", kpi="QUA-01", note="交付结果指标"),
            dict(process="L3-045", note="换线能力支撑"),
        ],
    ),
    dict(
        code="OBJ-2026-03",
        name="客诉重复发生率降到 2%",
        description="同一根因重复发生的客诉占比从 12% 降到 2%，推动根因分析进入标准与培训。",
        year=2026,
        period="ANNUAL",
        baseline_value=12.0,
        target_value=2.0,
        unit="%",
        source_document="2026 年度质量目标",
        owner="吴主管",
        status="ACTIVE",
        links=[
            dict(process="L3-061", kpi="QUA-03", note="客诉重复率"),
        ],
    ),
]
