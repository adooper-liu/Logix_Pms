"""演示用数据域与数据流。

只展示最小登记口径：谁负责、从哪来、主键是什么、质量规则与保留期。
生产环境应由数据治理办公室与业务数据所有者共同维护。
"""

DATA_DOMAINS = [
    dict(
        code="DD-001",
        name="客户主数据",
        domain_type="CUSTOMER",
        owner="系统管理员",
        steward="流程管理科",
        description="客户编码、名称、等级、信用与联系人等跨系统共用口径",
    ),
    dict(
        code="DD-002",
        name="供应商主数据",
        domain_type="SUPPLIER",
        owner="陈经理",
        steward="流程管理科",
        description="供应商准入状态、资质、银行账户与联系人",
    ),
    dict(
        code="DD-003",
        name="物料主数据",
        domain_type="MATERIAL",
        owner="系统管理员",
        steward="流程管理科",
        description="物料编码、规格、计量单位与安全库存",
    ),
    dict(
        code="DD-004",
        name="项目主数据",
        domain_type="PROJECT",
        owner="流程管理科",
        steward="流程管理科",
        description="项目编码、类型、阶段与预算口径",
    ),
    dict(
        code="DD-005",
        name="指标口径",
        domain_type="KPI",
        owner="流程管理科",
        steward="系统管理员",
        description="KPI 编码、公式、分子分母、阈值与数据来源",
    ),
]


DATA_FLOWS = [
    dict(
        code="DF-001",
        name="CRM → ERP 客户主数据",
        domain="DD-001",
        process="L3-061",
        source_system="CRM",
        target_system="ERP",
        frequency="DAILY",
        primary_key="customer_code",
        field_definitions="customer_code, customer_name, level, credit_limit, owner_org",
        allowed_values="level ∈ {A,B,C}; credit_limit ≥ 0",
        quality_rule="customer_code 非空且唯一；名称与工商登记一致；每日比对增量",
        purpose="订单、开票、客诉按统一客户口径汇总",
        retention_period="合同终止后 10 年",
        cross_legal_visibility="集团内可见；联系方式按最小必要授权",
        data_subject_rights="按个人信息保护流程受理查询、更正与删除",
    ),
    dict(
        code="DF-002",
        name="ERP → SRM 供应商准入状态",
        domain="DD-002",
        process="L3-033",
        source_system="ERP",
        target_system="SRM",
        frequency="DAILY",
        primary_key="supplier_code",
        field_definitions="supplier_code, admission_status, qualification_expiry, bank_account",
        allowed_values="admission_status ∈ {PENDING, APPROVED, BLOCKED}",
        quality_rule="未准入供应商不得进入询比价；资质到期前 30 天预警",
        purpose="询比价与招标前的准入校验",
        retention_period="合作结束后 10 年",
        cross_legal_visibility="集团采购与法务可见；银行账户脱敏展示",
        data_subject_rights="供应商可申请更正资质与联系人信息",
    ),
    dict(
        code="DF-003",
        name="MES → ERP 生产工单",
        domain="DD-003",
        process="L3-045",
        source_system="MES",
        target_system="ERP",
        frequency="REAL_TIME",
        primary_key="work_order_no",
        field_definitions="work_order_no, material_code, quantity, start_time, end_time, scrap_qty",
        allowed_values="quantity > 0; scrap_qty ≥ 0",
        quality_rule="工单结束时必须回传数量与报废；缺失工单每日对账",
        purpose="产能、成本与交付周期测算",
        retention_period="10 年",
        cross_legal_visibility="集团制造与财务可见",
        data_subject_rights="不涉及个人信息",
    ),
]
