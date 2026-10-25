"""problem-driven toolbox

Revision ID: c9a1b2c3d4e5
Revises: b8f0c2d4e6a1
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c9a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "b8f0c2d4e6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 高频工具的决策字段；其余工具保留空值，UI 显示「待补充」
TOOL_DECISIONS = {
    "SIPOC": {
        "scenarios": ("FLOW",),
        "difficulty": "LOW",
        "duration": "3–5 天",
        "prerequisites": "能召集跨部门负责人；对流程起点和终点有初步共识。",
        "not_applicable": "只需要优化单个岗位内部动作时，SIPOC 会过重。",
        "verification": "产出一页纸 SIPOC，且跨部门对边界与客户无异议。",
        "owner": "流程管理科",
    },
    "VSM": {
        "scenarios": ("CYCLE", "COST"),
        "difficulty": "MEDIUM",
        "duration": "2–3 周",
        "prerequisites": "选定代表性产品/服务；能到现场实测作业与等待时间。",
        "not_applicable": "没有现场数据、只能依赖系统台账时，VSM 会失真。",
        "verification": "识别出 ≥3 个非增值等待环节，或定位周期波动集中的交接点。",
        "owner": "精益推进组",
    },
    "FIVE-WHY": {
        "scenarios": ("ERROR", "RACI"),
        "difficulty": "LOW",
        "duration": "2–5 天",
        "prerequisites": "有可复现的问题现象；能找到直接当事人和现场记录。",
        "not_applicable": "问题由多因素叠加导致时，单链追问会过度简化。",
        "verification": "第 5 层原因落在制度、培训或设计等可干预层面，而非归咎个人。",
        "owner": "改善中心",
    },
    "FISHBONE": {
        "scenarios": ("ERROR",),
        "difficulty": "LOW",
        "duration": "1–3 天",
        "prerequisites": "有跨职能小组；能围绕人机料法环展开讨论。",
        "not_applicable": "问题原因高度确定且单一，鱼骨图会变成形式化会议。",
        "verification": "列出 ≥3 类可能原因，并用数据或现场证据排除至少一半。",
        "owner": "改善中心",
    },
    "PARETO": {
        "scenarios": ("ERROR", "COST", "CYCLE"),
        "difficulty": "LOW",
        "duration": "3 天",
        "prerequisites": "有可分类的问题数据；样本覆盖至少 30 单。",
        "not_applicable": "数据分类口径不稳定，或样本量过小。",
        "verification": "80% 的问题/周期集中在 ≤20% 的类别或环节。",
        "owner": "运营分析组",
    },
    "RACI": {
        "scenarios": ("RACI", "FLOW"),
        "difficulty": "MEDIUM",
        "duration": "1 周",
        "prerequisites": "已有流程活动清单；能找到每个活动的实际责任人。",
        "not_applicable": "组织权责尚未确定时，填出来的 RACI 只会是纸面共识。",
        "verification": "每个活动有且仅有一个 A，且 A 本人书面确认能履行。",
        "owner": "流程管理科",
    },
    "DECISION-MATRIX": {
        "scenarios": ("STANDARD", "COST"),
        "difficulty": "LOW",
        "duration": "2–5 天",
        "prerequisites": "有 ≥2 个可比较方案；权重由决策人提前确认。",
        "not_applicable": "只有一个可行方案，或评价维度无法量化。",
        "verification": "权重与评分过程可复核，最终选择能解释每个维度的取舍。",
        "owner": "流程管理科",
    },
    "PILOT": {
        "scenarios": ("STANDARD", "FLOW"),
        "difficulty": "MEDIUM",
        "duration": "2–4 周",
        "prerequisites": "方案已确定；试点单元、成功标准和回滚条件提前写死。",
        "not_applicable": "方案尚未稳定，或没有可比对的基线数据。",
        "verification": "试点指标达到预设阈值，且一线愿意继续使用。",
        "owner": "流程管理科",
    },
    "CONTROL-CHART": {
        "scenarios": ("ERROR", "CYCLE"),
        "difficulty": "MEDIUM",
        "duration": "持续",
        "prerequisites": "有稳定的采样频率和历史基线；控制限按数据计算而非拍脑袋。",
        "not_applicable": "过程尚未稳定，或数据口径频繁变化。",
        "verification": "连续 25 点无超控制限，且改善效果未出现衰减。",
        "owner": "运营分析组",
    },
    "ADKAR": {
        "scenarios": ("FLOW", "RACI"),
        "difficulty": "MEDIUM",
        "duration": "4–8 周",
        "prerequisites": "能识别关键利益相关者；有渠道观察采纳行为而非只听表态。",
        "not_applicable": "只是局部工具调整、没有行为改变要求时，ADKAR 会过重。",
        "verification": "新流程单据占比持续上升，例外率下降，执行时长收敛。",
        "owner": "流程管理科",
    },
}


def upgrade() -> None:
    with op.batch_alter_table("tool") as batch_op:
        batch_op.add_column(sa.Column("not_applicable_when", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("prerequisites", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("verification_standard", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("difficulty", sa.String(length=8), nullable=False, server_default="MEDIUM")
        )
        batch_op.add_column(sa.Column("typical_duration", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_due_at", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))
        )
        batch_op.create_foreign_key(
            "fk_tool_owner_user",
            "app_user",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_tool_difficulty", ["difficulty"])
        batch_op.create_index("ix_tool_owner_user_id", ["owner_user_id"])
        batch_op.create_index("ix_tool_is_active", ["is_active"])

    op.create_table(
        "tool_scenario_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tool_id",
            sa.Integer(),
            sa.ForeignKey("tool.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_scenario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("tool_id", "scenario_id", name="uq_tool_scenario_link"),
    )
    op.create_index("ix_tool_scenario_link_tool_id", "tool_scenario_link", ["tool_id"])
    op.create_index("ix_tool_scenario_link_scenario_id", "tool_scenario_link", ["scenario_id"])

    bind = op.get_bind()
    for code, decision in TOOL_DECISIONS.items():
        bind.execute(
            sa.text(
                "UPDATE tool SET "
                "difficulty = :difficulty, typical_duration = :duration, "
                "prerequisites = :prerequisites, not_applicable_when = :not_applicable, "
                "verification_standard = :verification, "
                "last_verified_at = '2026-09-20 10:00:00', "
                "review_due_at = '2027-09-20', version = 1 "
                "WHERE code = :code"
            ),
            {
                "code": code,
                "difficulty": decision["difficulty"],
                "duration": decision["duration"],
                "prerequisites": decision["prerequisites"],
                "not_applicable": decision["not_applicable"],
                "verification": decision["verification"],
            },
        )
        bind.execute(
            sa.text(
                "UPDATE tool SET owner_user_id = "
                "(SELECT id FROM app_user WHERE display_name = :owner LIMIT 1) "
                "WHERE code = :code"
            ),
            {"code": code, "owner": decision["owner"]},
        )
        for scenario_code in decision["scenarios"]:
            bind.execute(
                sa.text(
                    "INSERT INTO tool_scenario_link (tool_id, scenario_id, weight) "
                    "SELECT t.id, s.id, 1.0 FROM tool t, knowledge_scenario s "
                    "WHERE t.code = :code AND s.code = :scenario "
                    "AND NOT EXISTS (SELECT 1 FROM tool_scenario_link l "
                    "WHERE l.tool_id = t.id AND l.scenario_id = s.id)"
                ),
                {"code": code, "scenario": scenario_code},
            )


def downgrade() -> None:
    op.drop_index("ix_tool_scenario_link_scenario_id", table_name="tool_scenario_link")
    op.drop_index("ix_tool_scenario_link_tool_id", table_name="tool_scenario_link")
    op.drop_table("tool_scenario_link")

    with op.batch_alter_table("tool") as batch_op:
        batch_op.drop_index("ix_tool_is_active")
        batch_op.drop_index("ix_tool_owner_user_id")
        batch_op.drop_index("ix_tool_difficulty")
        batch_op.drop_constraint("fk_tool_owner_user", type_="foreignkey")
        batch_op.drop_column("is_active")
        batch_op.drop_column("review_due_at")
        batch_op.drop_column("last_verified_at")
        batch_op.drop_column("version")
        batch_op.drop_column("owner_user_id")
        batch_op.drop_column("typical_duration")
        batch_op.drop_column("difficulty")
        batch_op.drop_column("verification_standard")
        batch_op.drop_column("prerequisites")
        batch_op.drop_column("not_applicable_when")
