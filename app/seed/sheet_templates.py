"""每个工具一份可填写模板。格子按这个工具自己的表来，不把操作步骤当成表。

写入工具模板库的在线版本。填写弹窗只读已生效的这一版。
"""

from __future__ import annotations

from typing import List


def _f(key: str, label: str, *, required: bool = False, multiline: bool = False) -> dict:
    return {"key": key, "label": label, "required": required, "multiline": multiline}


def _choice(key: str, label: str) -> dict:
    return {
        "key": key,
        "label": label,
        "required": True,
        "kind": "choice",
        "options": ["符合", "部分符合", "未体现"],
    }


def _bpr(index: int, principle: str) -> List[dict]:
    return [
        _choice(f"p{index}", f"{index}. {principle}"),
        _f(f"p{index}_evidence", f"{index} 的证据：To-Be 里哪一段", multiline=True),
    ]


# (模板编码, 模板名称, 工具编码, 格子)
SHEET_TEMPLATES: List[tuple] = [
    (
        "TPL-SIPOC",
        "SIPOC 一页纸",
        "SIPOC",
        [
            _f("supplier", "供应方：谁交给这条流程", required=True, multiline=True),
            _f("input", "输入：交进来的是什么", required=True, multiline=True),
            _f("process", "过程：从哪一步开始，到哪一步结束", required=True, multiline=True),
            _f("output", "输出：交出去的是什么", required=True, multiline=True),
            _f("customer", "接收方：谁接着用这个输出", required=True, multiline=True),
            _f("dispute", "还有争议的边界", multiline=True),
        ],
    ),
    (
        "TPL-SWIMLANE",
        "泳道分工表",
        "SWIMLANE",
        [
            _f("lanes", "泳道：一行一个角色或部门", required=True, multiline=True),
            _f("handoffs", "跨道移交：从谁交到谁，交的是什么", multiline=True),
            _f("dispute", "还争着放进同一道的活动", multiline=True),
        ],
    ),
    (
        "TPL-VSM",
        "价值流时间表",
        "VSM",
        [
            _f("steps", "步骤、作业分钟、等待分钟，一行一步", required=True, multiline=True),
            _f("value", "哪几步是增值", multiline=True),
            _f("longest_wait", "等待最长落在哪一步", required=True),
        ],
    ),
    (
        "TPL-FIVE-WHY",
        "5 Why 追问表",
        "FIVE-WHY",
        [
            _f("phenomenon", "现象：看到的事实", required=True, multiline=True),
            _f("why1", "为什么 1", required=True),
            _f("why2", "为什么 2"),
            _f("why3", "为什么 3"),
            _f("why4", "为什么 4"),
            _f("why5", "为什么 5"),
            _f("cause", "可干预的原因", required=True, multiline=True),
            _f("action", "对策"),
            _f("verify", "怎么确认对策生效"),
        ],
    ),
    (
        "TPL-FISHBONE",
        "鱼骨对照表",
        "FISHBONE",
        [
            _f("phenomenon", "现象", required=True),
            _f("man", "人：和现象有关的事实", multiline=True),
            _f("machine", "设备", multiline=True),
            _f("material", "物料", multiline=True),
            _f("method", "方法", multiline=True),
            _f("measure", "测量", multiline=True),
            _f("environment", "环境", multiline=True),
            _f("kept", "这次留下要查的一条", required=True),
        ],
    ),
    (
        "TPL-PARETO",
        "帕累托计数表",
        "PARETO",
        [
            _f("items", "事项和次数，一行一条", required=True, multiline=True),
            _f("vital", "次数集中的少数几条", required=True, multiline=True),
            _f("rest", "其余先不动的", multiline=True),
        ],
    ),
    (
        "TPL-PROCESS-MINING",
        "挖掘问题单",
        "PROCESS-MINING",
        [
            _f("question", "这次要看清的问题", required=True),
            _f("case_key", "一条事例用什么串起来", required=True),
            _f("activity", "活动名称从哪来"),
            _f("gap", "和模型走法对不上时，记下缺了或重了哪一步", multiline=True),
        ],
    ),
    (
        "TPL-CJM",
        "客户旅程表",
        "CJM",
        [
            _f("actor", "为谁走这条旅程", required=True),
            _f("stages", "阶段和触点，一行一个阶段", required=True, multiline=True),
            _f("low", "情绪最低的触点", required=True),
            _f("change", "这次要改的触点", multiline=True),
        ],
    ),
    (
        "TPL-QUEUE-MODEL",
        "排队观测表",
        "QUEUE-MODEL",
        [
            _f("arrival", "到达率，写明单位", required=True),
            _f("service", "服务率，写明单位", required=True),
            _f("servers", "同时服务的台数或人数"),
            _f("observed_wait", "现场看到的等待", required=True),
        ],
    ),
    (
        "TPL-OGSM",
        "OGSM 一页纸",
        "OGSM",
        [
            _f("direction", "方向：这一年要赢什么", required=True),
            _f("baseline", "基线", required=True),
            _f("target", "目标值", required=True),
            _f("unit", "单位", required=True),
            _f("approach", "打法：靠哪几条流程做到", multiline=True),
            _f("measure", "用什么衡量", multiline=True),
            _f("source", "来源文件"),
        ],
    ),
    (
        "TPL-SWOT",
        "SWOT 四格",
        "SWOT",
        [
            _f("strengths", "优势（每条要能指出事实）", required=True, multiline=True),
            _f("weaknesses", "劣势", multiline=True),
            _f("opportunities", "机会", multiline=True),
            _f("threats", "威胁", multiline=True),
            _f("keep", "今年留下的几条，一行一条", multiline=True),
        ],
    ),
    (
        "TPL-GOAL-TREE",
        "目标树",
        "GOAL-TREE",
        [
            _f("result", "顶端：公司要赢的结果", required=True),
            _f("breakdown", "拆成能独立负责的几条，一行一条", multiline=True),
        ],
    ),
    (
        "TPL-BPR6",
        "BPR 六原则检查表",
        "BPR6",
        [
            *_bpr(1, "围绕结果组织工作，而不是围绕任务"),
            *_bpr(2, "让使用流程结果的人执行流程"),
            *_bpr(3, "把信息处理并进产生该信息的实际工作"),
            *_bpr(4, "将决策点放在执行处，并让执行者负责"),
            *_bpr(5, "在源头一次获取信息"),
            *_bpr(6, "把串行活动改为并行，并打破职能壁垒"),
        ],
    ),
    (
        "TPL-TOBE",
        "To-Be 取舍表",
        "TOBE",
        [
            _f("outcome", "未来态要交出的结果", required=True),
            _f("removed", "从现状删掉的步骤", required=True, multiline=True),
            _f("kept", "留下的步骤，按顺序", multiline=True),
            _f("decision", "这次定下来的设计决定", multiline=True),
        ],
    ),
    (
        "TPL-RACI",
        "RACI 事项表",
        "RACI",
        [
            _f("matters", "事项，一行一条", required=True, multiline=True),
            _f("accountable", "每条事项的唯一负责者", required=True, multiline=True),
            _f("conflict", "两个负责者，或没有负责者的事项", multiline=True),
        ],
    ),
    (
        "TPL-FMEA",
        "FMEA 表",
        "FMEA",
        [
            _f(
                "rows",
                "环节、失效模式、严重度、发生率、检出度、措施，一行一条",
                required=True,
                multiline=True,
            ),
            _f("top", "优先处理的一条", required=True),
        ],
    ),
    (
        "TPL-DECISION-MATRIX",
        "加权决策矩阵",
        "DECISION-MATRIX",
        [
            _f("options", "备选方案，一行一条", required=True, multiline=True),
            _f("criteria", "比较用的维度和权重", multiline=True),
            _f("choice", "留下哪一个", required=True),
            _f("reason", "为什么留下它", multiline=True),
        ],
    ),
    (
        "TPL-LEAN7",
        "七种浪费对照表",
        "LEAN7",
        [
            _f("transport", "搬运：看到的事实，没有就写无", multiline=True),
            _f("inventory", "库存", multiline=True),
            _f("motion", "动作", multiline=True),
            _f("waiting", "等待", multiline=True),
            _f("overprocess", "过度加工", multiline=True),
            _f("overproduction", "过量生产", multiline=True),
            _f("defects", "缺陷", multiline=True),
            _f("first", "先消除哪一种", required=True),
        ],
    ),
    (
        "TPL-KANBAN",
        "看板与在制品上限",
        "KANBAN",
        [
            _f("signal", "拉动信号是什么", required=True),
            _f("wip", "在制品上限", required=True),
            _f("pull_from", "从哪一段拉动"),
            _f("overflow", "超过上限时停在哪", multiline=True),
        ],
    ),
    (
        "TPL-DESIGN-THINKING",
        "设计思维记录",
        "DESIGN-THINKING",
        [
            _f("user", "为谁", required=True),
            _f("insight", "访谈里的一句事实", required=True, multiline=True),
            _f("idea", "留下的做法"),
            _f("prototype", "原型要验证的一件事", required=True),
        ],
    ),
    (
        "TPL-BPMN",
        "建模核对表",
        "BPMN",
        [
            _f("start_end", "开始事件和结束事件", required=True, multiline=True),
            _f("decisions", "判断和每个出口", multiline=True),
            _f("handoffs", "移交到谁", multiline=True),
            _f("missing", "图上还缺的", multiline=True),
        ],
    ),
    (
        "TPL-ADKAR",
        "ADKAR 诊断",
        "ADKAR",
        [
            _f("awareness", "知道：为什么要变", required=True, multiline=True),
            _f("desire", "愿意：谁还不愿", multiline=True),
            _f("knowledge", "会：要学会什么", multiline=True),
            _f("ability", "能：现场做不做得成", multiline=True),
            _f("reinforcement", "稳住：靠什么不退回去", multiline=True),
            _f("first", "最先补哪一层", required=True),
        ],
    ),
    (
        "TPL-STAKEHOLDER",
        "权力-利益表",
        "STAKEHOLDER",
        [
            _f(
                "people",
                "谁、权力高或低、利益高或低、怎么沟通，一行一人",
                required=True,
                multiline=True,
            ),
            _f("blocker", "最可能挡住的人，以及先对他说什么", required=True, multiline=True),
        ],
    ),
    (
        "TPL-TRAINING-MATRIX",
        "培训矩阵",
        "TRAINING-MATRIX",
        [
            _f("rows", "角色、要会什么、怎么教、何时，一行一条", required=True, multiline=True),
            _f("assess", "怎么知道学会了", required=True),
        ],
    ),
    (
        "TPL-PILOT",
        "试点方案",
        "PILOT",
        [
            _f("scope", "试点范围：哪一段、哪些人", required=True, multiline=True),
            _f("success", "成功标准", required=True, multiline=True),
            _f("schedule", "开始和结束"),
            _f("rollback", "不成功时退回什么"),
        ],
    ),
    (
        "TPL-COMM-PLAN",
        "沟通计划表",
        "COMM-PLAN",
        [
            _f("rows", "对象、信息、渠道、频次、责任人，一行一条", required=True, multiline=True),
        ],
    ),
    (
        "TPL-GOLIVE",
        "上线核对表",
        "GOLIVE",
        [
            _f("items", "条件、责任人、已确认或未确认，一行一条", required=True, multiline=True),
            _f("open_item", "还没确认、会挡住上线的一条", required=True),
        ],
    ),
    (
        "TPL-ROLLBACK",
        "回滚预案",
        "ROLLBACK",
        [
            _f("trigger", "什么情况触发退回", required=True),
            _f("decider", "谁拍板", required=True),
            _f("steps", "退回步骤", required=True, multiline=True),
            _f("drilled", "是否演练过，演练看到了什么"),
        ],
    ),
    (
        "TPL-BALANCED-SCORE",
        "平衡计分卡选用表",
        "BALANCED-SCORE",
        [
            _f("financial", "财务：选用哪个已有 KPI"),
            _f("customer", "客户：选用哪个已有 KPI"),
            _f("process", "流程：选用哪个已有 KPI", required=True),
            _f("learning", "学习：选用哪个已有 KPI"),
            _f("gap", "四个方向里还没有指标的", multiline=True),
        ],
    ),
    (
        "TPL-BI-DASHBOARD",
        "仪表盘布局说明",
        "BI-DASHBOARD",
        [
            _f("audience", "谁看", required=True),
            _f("tiles", "要看的已有 KPI，一行一个", required=True, multiline=True),
            _f("alert", "什么数越过什么线要提醒"),
        ],
    ),
    (
        "TPL-MINING-CONT",
        "持续挖掘观察表",
        "MINING-CONT",
        [
            _f("watch", "持续看的偏差", required=True),
            _f("threshold", "偏差到多少要打开看", required=True),
            _f("owner", "谁负责看"),
        ],
    ),
    (
        "TPL-CONTROL-CHART",
        "控制图说明",
        "CONTROL-CHART",
        [
            _f("metric", "看哪个已有序列", required=True),
            _f("rule", "准备用的判异规则，手写", required=True, multiline=True),
            _f("action", "判异之后谁处理"),
        ],
    ),
    (
        "TPL-PDCA",
        "PDCA 记录",
        "PDCA",
        [
            _f("plan", "计划：这次改什么", required=True, multiline=True),
            _f("do", "执行：实际做了什么", multiline=True),
            _f("check", "检查：和计划差在哪", multiline=True),
            _f("act", "处置：留下或退回", required=True, multiline=True),
        ],
    ),
    (
        "TPL-DMAIC",
        "DMAIC 阶段结论",
        "DMAIC",
        [
            _f("define", "定义：问题和范围", required=True, multiline=True),
            _f("measure", "测量：用哪个已有数", multiline=True),
            _f("analyze", "分析：原因", multiline=True),
            _f("improve", "改进：留下的做法", multiline=True),
            _f("control", "控制：以后看什么才算稳住", required=True),
        ],
    ),
    (
        "TPL-KAIZEN",
        "改善周记录",
        "KAIZEN",
        [
            _f("topic", "议题", required=True),
            _f("team", "参加的人", required=True),
            _f("days", "哪几天"),
            _f("output", "结束时交出什么", required=True, multiline=True),
        ],
    ),
    (
        "TPL-KB",
        "案例复盘",
        "KB",
        [
            _f("background", "背景", required=True, multiline=True),
            _f("approach", "当时的做法", multiline=True),
            _f("result", "结果", required=True, multiline=True),
            _f("pitfall", "踩过的坑", multiline=True),
            _f("reuse", "下次可以直接用的一点", multiline=True),
        ],
    ),
]
