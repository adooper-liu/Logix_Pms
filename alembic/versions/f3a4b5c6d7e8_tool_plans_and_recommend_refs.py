"""tool usage plans and unified recommendation refs

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_recommend_log", sa.Column("result_refs", sa.JSON(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("UPDATE knowledge_recommend_log SET result_refs = '[]'::json"))
    else:
        bind.execute(sa.text("UPDATE knowledge_recommend_log SET result_refs = '[]'"))
    with op.batch_alter_table("knowledge_recommend_log") as batch_op:
        batch_op.alter_column("result_refs", existing_type=sa.JSON(), nullable=False)

    op.create_table(
        "tool_usage_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tool_code",
            sa.String(length=32),
            sa.ForeignKey("tool.code", ondelete="CASCADE"),
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
            "planned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("planned_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PLANNED"),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tool_usage_plan_tool_code", "tool_usage_plan", ["tool_code"])
    op.create_index("ix_tool_usage_plan_project_id", "tool_usage_plan", ["project_id"])
    op.create_index(
        "ix_tool_usage_plan_planned_by_user_id", "tool_usage_plan", ["planned_by_user_id"]
    )
    op.create_index("ix_tool_usage_plan_planned_at", "tool_usage_plan", ["planned_at"])
    op.create_index("ix_tool_usage_plan_status", "tool_usage_plan", ["status"])
    op.create_index("ix_tool_usage_plan_tool_time", "tool_usage_plan", ["tool_code", "planned_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_usage_plan_tool_time", table_name="tool_usage_plan")
    op.drop_index("ix_tool_usage_plan_status", table_name="tool_usage_plan")
    op.drop_index("ix_tool_usage_plan_planned_at", table_name="tool_usage_plan")
    op.drop_index("ix_tool_usage_plan_planned_by_user_id", table_name="tool_usage_plan")
    op.drop_index("ix_tool_usage_plan_project_id", table_name="tool_usage_plan")
    op.drop_index("ix_tool_usage_plan_tool_code", table_name="tool_usage_plan")
    op.drop_table("tool_usage_plan")

    with op.batch_alter_table("knowledge_recommend_log") as batch_op:
        batch_op.drop_column("result_refs")
