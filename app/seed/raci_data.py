"""演示用治理角色、成员与 RACI。

角色类型与 RACI 是建议设计，生产环境应由集团治理委员会批准后维护；
这里只用演示账号展示“单点负责 + 分层授权”的结构。
"""

GOVERNANCE_ROLES = [
    dict(
        code="GR-001",
        name="集团流程治理委员会",
        role_type="COMMITTEE",
        description="批准原则、重大流程、优先级、资源与例外",
        members=[dict(user="系统管理员", is_primary=True)],
    ),
    dict(
        code="GR-002",
        name="集团端到端流程所有者",
        role_type="ENTERPRISE_OWNER",
        description="对端到端目标、设计、控制、KPI 与重大变更负责",
        members=[dict(user="陈经理", is_primary=True)],
    ),
    dict(
        code="GR-003",
        name="业务单元/工厂流程所有者",
        role_type="UNIT_OWNER",
        description="负责本地实例、资源、异常与目标承接",
        members=[],
    ),
    dict(
        code="GR-004",
        name="流程管理员/管家",
        role_type="STEWARD",
        description="维护文档、版本、培训、指标与审计准备",
        members=[dict(user="流程管理科", is_primary=True)],
    ),
    dict(
        code="GR-005",
        name="BPM/卓越运营办公室",
        role_type="BPM_OFFICE",
        description="提供方法、模板、项目组合与能力培养支持",
        members=[dict(user="流程管理科", is_primary=False)],
    ),
    dict(
        code="GR-006",
        name="数据所有者/管家",
        role_type="DATA_OWNER",
        description="定义数据口径、质量、访问与跨域冲突解决",
        members=[dict(user="系统管理员", is_primary=True)],
    ),
    dict(
        code="GR-007",
        name="风险/法务/财务/内控",
        role_type="RISK_LEGAL",
        description="红线、独立审查、阈值与例外审批",
        members=[],
    ),
]


RACI_ASSIGNMENTS = [
    dict(process="L3-032", matter="流程变更审批", role="GR-002", raci="A"),
    dict(process="L3-032", matter="流程变更审批", role="GR-005", raci="R"),
    dict(process="L3-032", matter="流程变更审批", role="GR-007", raci="C"),
    dict(process="L3-032", matter="流程变更审批", role="GR-003", raci="I"),
    dict(process="L3-032", matter="KPI 口径确认", role="GR-006", raci="A"),
    dict(process="L3-032", matter="KPI 口径确认", role="GR-002", raci="R"),
    dict(process="L3-032", matter="KPI 口径确认", role="GR-005", raci="C"),
    dict(process="L3-032", matter="例外审批", role="GR-003", raci="A"),
    dict(process="L3-032", matter="例外审批", role="GR-007", raci="C"),
    dict(process="L3-032", matter="例外审批", role="GR-004", raci="I"),
    dict(process="L3-032", matter="日常文档维护", role="GR-004", raci="A"),
    dict(process="L3-032", matter="日常文档维护", role="GR-005", raci="R"),
    dict(process="L3-033", matter="供应商准入例外", role="GR-003", raci="A"),
    dict(process="L3-033", matter="供应商准入例外", role="GR-007", raci="C"),
]
