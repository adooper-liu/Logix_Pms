"""演示用变更申请。

只放一条草稿，用于展示「变更单 → 提交 → 批准 → 发布」的门禁链路；
生产环境的变更单必须由流程所有者填写并由治理角色审批。
"""

CHANGE_REQUESTS = [
    dict(
        code="CR-2026-001",
        process="L3-033",
        title="询比价与招标：增加供应商准入校验节点",
        reason="审计发现未准入供应商可直接进入询比价，存在合规风险。",
        scope="L3-033 询比价与招标；涉及供应商主数据、询价单与审批流。",
        change_type="STRUCTURE",
        impact_level="MAJOR",
        version_label="V2.0",
        impact={
            "people": "采购员、采购经理、供应商管理员",
            "systems": "采购系统增加准入校验；OA 审批流增加节点",
            "data": "供应商主数据新增准入状态字段",
            "permissions": "未准入供应商不可创建询价单",
            "controls": "准入校验作为不可跳过的控制点",
            "training": "采购员与采购经理培训 1 小时",
            "kpis": "询比价周期预计增加 0.5 天，需观察 2 个月",
        },
        test_evidence="在测试环境用 3 家未准入供应商验证：询价单创建被拦截，"
        "准入后恢复正常；回归 12 条既有询价流程。",
        rollback_plan="关闭准入校验开关，恢复旧审批流；已拦截的询价单人工补录准入状态。",
        status="DRAFT",
        requested_by="流程管理科",
    ),
]
