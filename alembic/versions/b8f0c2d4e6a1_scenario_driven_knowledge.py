"""scenario-driven knowledge base

Revision ID: b8f0c2d4e6a1
Revises: f6a7b8c9d0e1
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8f0c2d4e6a1"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCENARIOS = [
    {
        "code": "FLOW",
        "name": "流程混乱",
        "description": "环节不清、重复交接、部门墙",
        "sort_order": 1,
        "is_active": True,
    },
    {
        "code": "CYCLE",
        "name": "周期太长",
        "description": "等待多、节拍不稳、交付慢",
        "sort_order": 2,
        "is_active": True,
    },
    {
        "code": "ERROR",
        "name": "差错返工多",
        "description": "反复出错、客诉、质量波动",
        "sort_order": 3,
        "is_active": True,
    },
    {
        "code": "RACI",
        "name": "责任不清",
        "description": "多头负责、互相推诿、权责冲突",
        "sort_order": 4,
        "is_active": True,
    },
    {
        "code": "COST",
        "name": "成本过高",
        "description": "浪费多、投入产出低",
        "sort_order": 5,
        "is_active": True,
    },
    {
        "code": "STANDARD",
        "name": "缺少标准",
        "description": "靠经验、各做各的、无法复制",
        "sort_order": 6,
        "is_active": True,
    },
]

# 存量条目的默认场景映射：按 tool_code 推断，迁移后仍可由维护人调整
TOOL_SCENARIOS = {
    "BPR6": ("FLOW", "STANDARD"),
    "VSM": ("CYCLE", "COST"),
    "RACI": ("RACI", "FLOW"),
    "ADKAR": ("FLOW", "RACI"),
    "KAIZEN": ("COST", "CYCLE"),
    "PARETO": ("ERROR", "COST"),
    "PILOT": ("STANDARD", "FLOW"),
    "BALANCED-SCORE": ("STANDARD",),
    "FIVE-WHY": ("ERROR",),
    "FISHBONE": ("ERROR",),
    "DMAIC": ("ERROR", "CYCLE"),
}

TOOL_EXTRA_STAGES = {
    "BPR6": (1,),
    "RACI": (1,),
    "VSM": (3,),
    "PARETO": (3,),
    "PILOT": (1,),
    "KAIZEN": (4,),
    "BALANCED-SCORE": (5,),
}


def upgrade() -> None:
    op.create_table(
        "knowledge_scenario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_knowledge_scenario_code", "knowledge_scenario", ["code"], unique=True)

    op.create_table(
        "knowledge_scenario_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_scenario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("knowledge_id", "scenario_id", name="uq_knowledge_scenario_link"),
    )
    op.create_index(
        "ix_knowledge_scenario_link_knowledge_id",
        "knowledge_scenario_link",
        ["knowledge_id"],
    )
    op.create_index(
        "ix_knowledge_scenario_link_scenario_id",
        "knowledge_scenario_link",
        ["scenario_id"],
    )

    op.create_table(
        "knowledge_workflow_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_no", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.String(length=8), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint(
            "knowledge_id", "stage_no", "step_no", name="uq_knowledge_workflow_link"
        ),
    )
    op.create_index(
        "ix_knowledge_workflow_link_knowledge_id",
        "knowledge_workflow_link",
        ["knowledge_id"],
    )
    op.create_index("ix_knowledge_workflow_link_stage_no", "knowledge_workflow_link", ["stage_no"])
    op.create_index("ix_knowledge_workflow_link_step_no", "knowledge_workflow_link", ["step_no"])

    op.create_table(
        "knowledge_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_no", sa.String(length=8), nullable=True),
        sa.Column(
            "used_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("used_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="EFFECTIVE"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence_url", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_knowledge_usage_knowledge_id", "knowledge_usage", ["knowledge_id"])
    op.create_index("ix_knowledge_usage_project_id", "knowledge_usage", ["project_id"])
    op.create_index("ix_knowledge_usage_used_by_user_id", "knowledge_usage", ["used_by_user_id"])
    op.create_index("ix_knowledge_usage_used_at", "knowledge_usage", ["used_at"])
    op.create_index("ix_knowledge_usage_outcome", "knowledge_usage", ["outcome"])
    op.create_index("ix_knowledge_usage_item_time", "knowledge_usage", ["knowledge_id", "used_at"])

    with op.batch_alter_table("knowledge_item") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="PUBLISHED")
        )
        batch_op.add_column(sa.Column("claim", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("applicable_when", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("not_applicable_when", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("input_conditions", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("steps_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("outputs", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("evidence_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("verified_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_due_at", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_best_practice",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(sa.Column("promoted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_knowledge_owner_user",
            "app_user",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_knowledge_verified_by",
            "app_user",
            ["verified_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_knowledge_item_status", ["status"])
        batch_op.create_index("ix_knowledge_item_owner_user_id", ["owner_user_id"])
        batch_op.create_index("ix_knowledge_item_verified_by_user_id", ["verified_by_user_id"])

    bind = op.get_bind()
    scenario_table = sa.table(
        "knowledge_scenario",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(scenario_table, SCENARIOS)

    # 旧数据语义迁移：最佳实践改为标志位；标准制度退出知识库，等人工迁到制度中心
    bind.execute(sa.text("UPDATE knowledge_item SET updated_at = created_at"))
    bind.execute(
        sa.text(
            "UPDATE knowledge_item SET type = 'METHOD', is_best_practice = true "
            "WHERE type = 'BEST_PRACTICE'"
        )
    )
    bind.execute(sa.text("UPDATE knowledge_item SET status = 'ARCHIVED' WHERE type = 'STANDARD'"))

    for tool_code, codes in TOOL_SCENARIOS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO knowledge_scenario_link (knowledge_id, scenario_id, weight) "
                    "SELECT k.id, s.id, 1.0 FROM knowledge_item k, knowledge_scenario s "
                    "WHERE k.tool_code = :tool_code AND s.code = :code "
                    "AND NOT EXISTS (SELECT 1 FROM knowledge_scenario_link l "
                    "WHERE l.knowledge_id = k.id AND l.scenario_id = s.id)"
                ),
                {"tool_code": tool_code, "code": code},
            )

    # 工具的主适用阶段直接成为知识的工作流阶段；具体步骤由维护人后续补充
    bind.execute(
        sa.text(
            "INSERT INTO knowledge_workflow_link (knowledge_id, stage_no, step_no, is_primary) "
            "SELECT k.id, t.stage_no, '', false FROM knowledge_item k "
            "JOIN tool t ON t.code = k.tool_code "
            "WHERE NOT EXISTS (SELECT 1 FROM knowledge_workflow_link w "
            "WHERE w.knowledge_id = k.id AND w.stage_no = t.stage_no AND w.step_no = '')"
        )
    )

    # 除工具主阶段外，知识还会在相邻阶段被使用（如 BPR 模板也用于阶段 1 立项）
    for tool_code, stages in TOOL_EXTRA_STAGES.items():
        for stage_no in stages:
            bind.execute(
                sa.text(
                    "INSERT INTO knowledge_workflow_link "
                    "(knowledge_id, stage_no, step_no, is_primary) "
                    "SELECT k.id, :stage_no, '', false FROM knowledge_item k "
                    "WHERE k.tool_code = :tool_code "
                    "AND NOT EXISTS (SELECT 1 FROM knowledge_workflow_link w "
                    "WHERE w.knowledge_id = k.id AND w.stage_no = :stage_no AND w.step_no = '')"
                ),
                {"tool_code": tool_code, "stage_no": stage_no},
            )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_item") as batch_op:
        batch_op.drop_index("ix_knowledge_item_verified_by_user_id")
        batch_op.drop_index("ix_knowledge_item_owner_user_id")
        batch_op.drop_index("ix_knowledge_item_status")
        batch_op.drop_constraint("fk_knowledge_verified_by", type_="foreignkey")
        batch_op.drop_constraint("fk_knowledge_owner_user", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("promoted_at")
        batch_op.drop_column("is_best_practice")
        batch_op.drop_column("review_due_at")
        batch_op.drop_column("last_verified_at")
        batch_op.drop_column("verified_by_user_id")
        batch_op.drop_column("owner_user_id")
        batch_op.drop_column("version")
        batch_op.drop_column("evidence_summary")
        batch_op.drop_column("outputs")
        batch_op.drop_column("steps_summary")
        batch_op.drop_column("input_conditions")
        batch_op.drop_column("not_applicable_when")
        batch_op.drop_column("applicable_when")
        batch_op.drop_column("claim")
        batch_op.drop_column("status")

    op.drop_index("ix_knowledge_usage_item_time", table_name="knowledge_usage")
    op.drop_index("ix_knowledge_usage_outcome", table_name="knowledge_usage")
    op.drop_index("ix_knowledge_usage_used_at", table_name="knowledge_usage")
    op.drop_index("ix_knowledge_usage_used_by_user_id", table_name="knowledge_usage")
    op.drop_index("ix_knowledge_usage_project_id", table_name="knowledge_usage")
    op.drop_index("ix_knowledge_usage_knowledge_id", table_name="knowledge_usage")
    op.drop_table("knowledge_usage")

    op.drop_index("ix_knowledge_workflow_link_step_no", table_name="knowledge_workflow_link")
    op.drop_index("ix_knowledge_workflow_link_stage_no", table_name="knowledge_workflow_link")
    op.drop_index("ix_knowledge_workflow_link_knowledge_id", table_name="knowledge_workflow_link")
    op.drop_table("knowledge_workflow_link")

    op.drop_index("ix_knowledge_scenario_link_scenario_id", table_name="knowledge_scenario_link")
    op.drop_index("ix_knowledge_scenario_link_knowledge_id", table_name="knowledge_scenario_link")
    op.drop_table("knowledge_scenario_link")

    op.drop_index("ix_knowledge_scenario_code", table_name="knowledge_scenario")
    op.drop_table("knowledge_scenario")
