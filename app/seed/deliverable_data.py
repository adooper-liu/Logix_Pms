"""步骤契约与交付物定义的底稿。

只放「标准」数据：工具引用、责任人角色、验收口径、每步应产出的交付物。
项目实例与版本由运行期产生，不在这里预置。
"""

from __future__ import annotations

from typing import Dict, List

# 每步允许/推荐的工具，引用 tool.code。语料里有些工具名（如「价值-痛点矩阵」）
# 不在 33 个工具库内，就只保留在 WorkflowTemplate.tools 的文字说明里，不硬凑引用。
STEP_TOOL_CODES: Dict[str, List[str]] = {
    "1.1": [],
    "1.2": [],
    "1.3": [],
    "1.4": [],
    "2.1": ["SIPOC", "SWIMLANE"],
    "2.2": ["VSM"],
    "2.3": ["FIVE-WHY", "FISHBONE", "PARETO", "PROCESS-MINING"],
    "2.4": ["QUEUE-MODEL"],
    "3.1": ["BPR6", "LEAN7"],
    "3.2": ["TOBE", "VSM"],
    "3.3": ["RACI", "BALANCED-SCORE"],
    "3.4": ["DECISION-MATRIX", "FMEA"],
    "3.5": ["BPMN"],
    "4.1": ["STAKEHOLDER"],
    "4.2": ["PILOT"],
    "4.3": ["PDCA"],
    "4.4": ["TRAINING-MATRIX"],
    "4.5": ["GOLIVE"],
    "4.6": ["ADKAR", "COMM-PLAN"],
    "5.1": ["RACI"],
    "5.2": ["BI-DASHBOARD", "BALANCED-SCORE"],
    "5.3": ["CONTROL-CHART"],
    "5.4": ["VSM", "KB"],
    "5.5": ["PDCA", "DMAIC", "KAIZEN"],
}

# 每个工具在本步骤里的使用要求；没写的工具按「推荐」处理。
STEP_TOOL_LEVELS: Dict[str, Dict[str, str]] = {
    "2.1": {"SIPOC": "REQUIRED", "SWIMLANE": "RECOMMENDED"},
    "2.2": {"VSM": "REQUIRED"},
    "2.3": {
        "FIVE-WHY": "REQUIRED",
        "FISHBONE": "RECOMMENDED",
        "PARETO": "RECOMMENDED",
        "PROCESS-MINING": "OPTIONAL",
    },
    "2.4": {"QUEUE-MODEL": "RECOMMENDED"},
    "3.1": {"BPR6": "RECOMMENDED", "LEAN7": "RECOMMENDED"},
    "3.2": {"TOBE": "REQUIRED", "VSM": "RECOMMENDED"},
    "3.3": {"RACI": "REQUIRED", "BALANCED-SCORE": "OPTIONAL"},
    "3.4": {"DECISION-MATRIX": "REQUIRED", "FMEA": "RECOMMENDED"},
    "3.5": {"BPMN": "RECOMMENDED"},
    "4.1": {"STAKEHOLDER": "REQUIRED"},
    "4.2": {"PILOT": "REQUIRED"},
    "4.3": {"PDCA": "REQUIRED"},
    "4.4": {"TRAINING-MATRIX": "RECOMMENDED"},
    "4.5": {"GOLIVE": "REQUIRED"},
    "4.6": {"ADKAR": "REQUIRED", "COMM-PLAN": "RECOMMENDED"},
    "5.1": {"RACI": "RECOMMENDED"},
    "5.2": {"BI-DASHBOARD": "REQUIRED", "BALANCED-SCORE": "OPTIONAL"},
    "5.3": {"CONTROL-CHART": "RECOMMENDED"},
    "5.4": {"VSM": "OPTIONAL", "KB": "RECOMMENDED"},
    "5.5": {"PDCA": "RECOMMENDED", "DMAIC": "RECOMMENDED", "KAIZEN": "OPTIONAL"},
}

# 责任人写角色，不写具体人；与项目 Owner 机制一致。
STEP_OWNER_ROLES: Dict[str, str] = {
    "1.1": "流程管理科",
    "1.2": "流程管理科",
    "1.3": "流程管理科",
    "1.4": "流程管理科",
    "2.1": "流程 Owner",
    "2.2": "流程管理科",
    "2.3": "流程 Owner",
    "2.4": "流程管理科",
    "3.1": "流程管理科",
    "3.2": "流程 Owner",
    "3.3": "流程 Owner",
    "3.4": "流程管理科",
    "3.5": "流程 Owner",
    "4.1": "变革经理",
    "4.2": "项目组长",
    "4.3": "项目组长",
    "4.4": "项目组长",
    "4.5": "项目组长",
    "4.6": "变革经理",
    "5.1": "流程 Owner",
    "5.2": "流程 Owner",
    "5.3": "流程 Owner",
    "5.4": "流程管理科",
    "5.5": "流程管理科",
}

# 阶段级验收口径：具体某一步可以再覆盖。
STAGE_ACCEPTANCE: Dict[int, str] = {
    1: "交付物经流程管理科评审；打分与立项数据能追溯到来源，不只停留在结论。",
    2: "覆盖端到端流程；时间、频次、不良率有现场观测或系统数据支撑。",
    3: "方案包含目标状态、配套措施与评估结论；关键假设写明验证方式。",
    4: "试点结果可量化；推广范围、责任人与时间表已对齐。",
    5: "指标、异常与评审机制已移交，并有连续运行记录。",
}

# (step_no, code 后缀, 名称, 类型)
DELIVERABLES: List[dict] = [
    dict(step_no="1.1", code="DLV-1.1-01", name="企业流程地图（L1–L4）", type="DIAGRAM"),
    dict(step_no="1.2", code="DLV-1.2-01", name="流程改善优先级排序清单", type="DATA"),
    dict(step_no="1.3", code="DLV-1.3-01", name="流程项目组合看板", type="DATA"),
    dict(step_no="1.3", code="DLV-1.3-02", name="立项章程", type="DOCUMENT"),
    dict(step_no="1.4", code="DLV-1.4-01", name="方法论匹配决策", type="DECISION"),
    dict(step_no="2.1", code="DLV-2.1-01", name="As-Is 流程图", type="DIAGRAM"),
    dict(step_no="2.2", code="DLV-2.2-01", name="价值流现状图", type="DIAGRAM"),
    dict(step_no="2.2", code="DLV-2.2-02", name="周期效率（PCE）报告", type="REPORT"),
    dict(step_no="2.3", code="DLV-2.3-01", name="根因分析报告", type="REPORT"),
    dict(step_no="2.4", code="DLV-2.4-01", name="瓶颈清单", type="DATA"),
    dict(step_no="2.4", code="DLV-2.4-02", name="影响量化表", type="DATA"),
    dict(step_no="3.1", code="DLV-3.1-01", name="设计原则清单", type="DATA"),
    dict(step_no="3.2", code="DLV-3.2-01", name="To-Be 流程方案", type="DOCUMENT"),
    dict(step_no="3.3", code="DLV-3.3-01", name="配套方案包", type="DOCUMENT"),
    dict(step_no="3.4", code="DLV-3.4-01", name="选定方案", type="DECISION"),
    dict(step_no="3.4", code="DLV-3.4-02", name="评估报告", type="REPORT"),
    dict(step_no="3.5", code="DLV-3.5-01", name="SOP 文档", type="DOCUMENT"),
    dict(step_no="3.5", code="DLV-3.5-02", name="表单设计", type="FORM"),
    dict(step_no="3.5", code="DLV-3.5-03", name="系统需求规格", type="DOCUMENT"),
    dict(step_no="4.1", code="DLV-4.1-01", name="变革风险地图", type="DIAGRAM"),
    dict(step_no="4.2", code="DLV-4.2-01", name="试点方案", type="DOCUMENT"),
    dict(step_no="4.3", code="DLV-4.3-01", name="试点报告", type="REPORT"),
    dict(step_no="4.3", code="DLV-4.3-02", name="修正方案", type="DOCUMENT"),
    dict(step_no="4.4", code="DLV-4.4-01", name="推广计划", type="DOCUMENT"),
    dict(step_no="4.5", code="DLV-4.5-01", name="落地确认清单", type="DATA"),
    dict(step_no="4.6", code="DLV-4.6-01", name="变革采纳率指标", type="DATA"),
    dict(step_no="5.1", code="DLV-5.1-01", name="运营移交确认", type="DATA"),
    dict(step_no="5.2", code="DLV-5.2-01", name="流程健康报告", type="REPORT"),
    dict(step_no="5.3", code="DLV-5.3-01", name="异常事件记录与闭环台账", type="DATA"),
    dict(step_no="5.4", code="DLV-5.4-01", name="评审报告", type="REPORT"),
    dict(step_no="5.4", code="DLV-5.4-02", name="改进建议", type="DOCUMENT"),
    dict(step_no="5.5", code="DLV-5.5-01", name="新一轮改善项目立项申请", type="DOCUMENT"),
]
