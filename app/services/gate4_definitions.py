"""Proposed L3-032 control definitions, never actual business records."""


def field(key, label, kind="text", *, required=True, options=None, minimum=None):
    item = {"key": key, "label": label, "type": kind, "required": required}
    if options:
        item["options"] = options
    if minimum is not None:
        item["min"] = minimum
    return item


FORMS = {
    "n1": (
        "需求发起与归集记录（待业务确认）",
        [
            field("applicant", "申请人"),
            field("amount", "预计金额（元）", "number", minimum=0),
            field("description", "需求说明", "textarea"),
            field("request_ref", "需求单/来源引用"),
            field("required_date", "需求日期", "date"),
        ],
    ),
    "n2": (
        "需求汇总与归并记录（待业务确认）",
        [
            field("source_request_refs", "来源需求引用", "textarea"),
            field("merge_basis", "归并依据及重复/冲突处理", "textarea"),
            field("consolidated_ref", "汇总清单引用"),
        ],
    ),
    "n3": (
        "预算占用校验记录（待业务确认）",
        [
            field("budget_ref", "预算依据引用"),
            field("budget_amount", "可用预算金额（元）", "number", minimum=0),
            field("budget_ok", "预算校验是否通过", "select", options=["是", "否"]),
            field("budget_check_note", "校验依据、占用结果或未通过原因", "textarea"),
        ],
    ),
    "n4": (
        "需求审批记录（待业务确认）",
        [
            field("approved", "是否通过", "select", options=["是", "否"]),
            field("comment", "审批依据及通过/驳回原因", "textarea"),
        ],
    ),
    "n5": (
        "采购计划生成记录（待业务确认）",
        [
            field("plan_ref", "采购计划编号/引用"),
            field("output_ref", "采购计划输出文件/系统引用"),
            field("intended_receiver", "预定下游接收方（非实际签收）"),
            field("completion_check", "生成完整性检查结果", "textarea"),
        ],
    ),
    "n6": (
        "计划回退与修改记录（待业务确认）",
        [
            field("original_request_ref", "原需求/计划引用"),
            field("return_reason", "回退原因", "textarea"),
            field("changes", "修改内容及对应问题", "textarea"),
            field("resubmit_ready", "是否已具备重新提交条件", "select", options=["是", "否"]),
        ],
    ),
}

CONTROLS = {
    "n1": "输入：需求来源、申请人、金额、需求说明及需求日期。输出：可追溯需求记录；接收环节：需求汇总与归并。必填字段完整后提交；真实性由业务核验。",
    "n2": "输入：来源需求。输出：汇总清单引用及归并依据；接收环节：预算占用校验。保留重复/冲突处理说明；不得以归并记录替代原单。",
    "n3": "输入：汇总需求和预算依据。输出：预算校验记录；通过进入需求审批，不通过进入计划回退与修改。填写结果不代表系统已与预算系统集成核验。",
    "n4": "输入：需求及预算校验记录。输出：审批决定及原因；通过进入采购计划生成，驳回进入计划回退与修改。不得手选相反分支。审批权限及责任确认不在本次范围。",
    "n5": "输入：已批准需求。输出：采购计划编号及文件/系统引用；预定接收方仅为交接对象登记，不代表真实接收。节点完成不等于下游结果验收。",
    "n6": "输入：预算未通过/审批驳回问题。输出：原单引用、回退原因和修改内容。仅在重新提交条件为是时返回需求汇总与归并，否则保留当前任务。",
}

GAPS = [
    "模型及控制定义尚未取得业务批准；工作版为草稿，不发布、不宣称 Gate 4 正式通过。",
    "六活动关系为依据现有模型登记的 E1 配置，业务确认人及确认时间留空。",
    "处理时限、适用日历及超期升级触发值无正式依据，未配置；不得把测算工时当作 SLA。",
    "超期升级对象、替补和责任接受待业务确认；本次不进入 Gate 5，不代填账号或岗位。",
    "外部系统失败、撤销、数据修正等异常补偿尚未确认；预算失败和审批驳回仅补设计路径。",
    "预算依据真实性、预算实际占用、审批授权及计划实际生成未验证；表单只是记录载体。",
    "真实运行、处理轨迹、异常处置和下游签收未验证；既有开发实例不能自动升级为 E3。",
    "旧实例缺失模型版本的历史问题保留，不猜填、不改写；在途实例继续使用原快照。",
    "本工作版的表单为流程当前配置，LEGACY 新实例会快照当前配置；未发布前不得据此开展正式业务试运行。",
]


def document_text(version, baseline):
    lines = [
        "L3-032 Gate 4 过程控制配置与缺口说明",
        "",
        f"工作版：V{version.version}（id={version.id}），依据已发布 V{baseline.version}（id={baseline.id}）。",
        "证据等级：E1 规范配置；AI 辅助拟定、待业务确认，非审批、非真实运行。",
        "本次仅模型版本、活动映射、表单/记录载体、分支规则和过程控制缺口。",
        "",
    ]
    for key, control in CONTROLS.items():
        lines.extend(
            [
                f"{key} / L4-{200 + int(key[1:])}：{control}",
                "记录字段：" + "、".join(f["label"] for f in FORMS[key][1]),
                "",
            ]
        )
    lines.append("尚未关闭的过程控制缺口：")
    lines.extend(f"{i}. {gap}" for i, gap in enumerate(GAPS, 1))
    return "\n".join(lines) + "\n"
