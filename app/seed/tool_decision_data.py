"""高频工具的决策字段（适用痛点、难度、验证标准等）。

其余工具在迁移/种子时保留空值，UI 显示「待补充」，不编造验证标准。
"""

from __future__ import annotations

TOOL_DECISION_DATA = {
    "SIPOC": {
        "scenarios": ["FLOW"],
        "difficulty": "LOW",
        "typical_duration": "3–5 天",
        "prerequisites": "能召集跨部门负责人；对流程起点和终点有初步共识。",
        "not_applicable_when": "只需要优化单个岗位内部动作时，SIPOC 会过重。",
        "verification_standard": "产出一页纸 SIPOC，且跨部门对边界与客户无异议。",
        "owner": "流程管理科",
    },
    "VSM": {
        "scenarios": ["CYCLE", "COST"],
        "difficulty": "MEDIUM",
        "typical_duration": "2–3 周",
        "prerequisites": "选定代表性产品/服务；能到现场实测作业与等待时间。",
        "not_applicable_when": "没有现场数据、只能依赖系统台账时，VSM 会失真。",
        "verification_standard": "识别出 ≥3 个非增值等待环节，或定位周期波动集中的交接点。",
        "owner": "精益推进组",
    },
    "FIVE-WHY": {
        "scenarios": ["ERROR", "RACI"],
        "difficulty": "LOW",
        "typical_duration": "2–5 天",
        "prerequisites": "有可复现的问题现象；能找到直接当事人和现场记录。",
        "not_applicable_when": "问题由多因素叠加导致时，单链追问会过度简化。",
        "verification_standard": "第 5 层原因落在制度、培训或设计等可干预层面，而非归咎个人。",
        "owner": "改善中心",
    },
    "FISHBONE": {
        "scenarios": ["ERROR"],
        "difficulty": "LOW",
        "typical_duration": "1–3 天",
        "prerequisites": "有跨职能小组；能围绕人机料法环展开讨论。",
        "not_applicable_when": "问题原因高度确定且单一，鱼骨图会变成形式化会议。",
        "verification_standard": "列出 ≥3 类可能原因，并用数据或现场证据排除至少一半。",
        "owner": "改善中心",
    },
    "PARETO": {
        "scenarios": ["ERROR", "COST", "CYCLE"],
        "difficulty": "LOW",
        "typical_duration": "3 天",
        "prerequisites": "有可分类的问题数据；样本覆盖至少 30 单。",
        "not_applicable_when": "数据分类口径不稳定，或样本量过小。",
        "verification_standard": "80% 的问题/周期集中在 ≤20% 的类别或环节。",
        "owner": "运营分析组",
    },
    "RACI": {
        "scenarios": ["RACI", "FLOW"],
        "difficulty": "MEDIUM",
        "typical_duration": "1 周",
        "prerequisites": "已有流程活动清单；能找到每个活动的实际责任人。",
        "not_applicable_when": "组织权责尚未确定时，填出来的 RACI 只会是纸面共识。",
        "verification_standard": "每个活动有且仅有一个 A，且 A 本人书面确认能履行。",
        "owner": "流程管理科",
    },
    "DECISION-MATRIX": {
        "scenarios": ["STANDARD", "COST"],
        "difficulty": "LOW",
        "typical_duration": "2–5 天",
        "prerequisites": "有 ≥2 个可比较方案；权重由决策人提前确认。",
        "not_applicable_when": "只有一个可行方案，或评价维度无法量化。",
        "verification_standard": "权重与评分过程可复核，最终选择能解释每个维度的取舍。",
        "owner": "流程管理科",
    },
    "PILOT": {
        "scenarios": ["STANDARD", "FLOW"],
        "difficulty": "MEDIUM",
        "typical_duration": "2–4 周",
        "prerequisites": "方案已确定；试点单元、成功标准和回滚条件提前写死。",
        "not_applicable_when": "方案尚未稳定，或没有可比对的基线数据。",
        "verification_standard": "试点指标达到预设阈值，且一线愿意继续使用。",
        "owner": "流程管理科",
    },
    "CONTROL-CHART": {
        "scenarios": ["ERROR", "CYCLE"],
        "difficulty": "MEDIUM",
        "typical_duration": "持续",
        "prerequisites": "有稳定的采样频率和历史基线；控制限按数据计算而非拍脑袋。",
        "not_applicable_when": "过程尚未稳定，或数据口径频繁变化。",
        "verification_standard": "连续 25 点无超控制限，且改善效果未出现衰减。",
        "owner": "运营分析组",
    },
    "ADKAR": {
        "scenarios": ["FLOW", "RACI"],
        "difficulty": "MEDIUM",
        "typical_duration": "4–8 周",
        "prerequisites": "能识别关键利益相关者；有渠道观察采纳行为而非只听表态。",
        "not_applicable_when": "只是局部工具调整、没有行为改变要求时，ADKAR 会过重。",
        "verification_standard": "新流程单据占比持续上升，例外率下降，执行时长收敛。",
        "owner": "流程管理科",
    },
}
