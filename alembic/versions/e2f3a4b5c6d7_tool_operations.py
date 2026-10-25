"""tool operations: submission review and direct usage evidence

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tool") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="PUBLISHED")
        )
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tool_reviewed_by_user",
            "app_user",
            ["reviewed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_tool_status", ["status"])
        batch_op.create_index("ix_tool_reviewed_by_user_id", ["reviewed_by_user_id"])

    op.create_table(
        "tool_usage",
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
    op.create_index("ix_tool_usage_tool_code", "tool_usage", ["tool_code"])
    op.create_index("ix_tool_usage_project_id", "tool_usage", ["project_id"])
    op.create_index("ix_tool_usage_used_by_user_id", "tool_usage", ["used_by_user_id"])
    op.create_index("ix_tool_usage_used_at", "tool_usage", ["used_at"])
    op.create_index("ix_tool_usage_outcome", "tool_usage", ["outcome"])
    op.create_index("ix_tool_usage_code_time", "tool_usage", ["tool_code", "used_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_usage_code_time", table_name="tool_usage")
    op.drop_index("ix_tool_usage_outcome", table_name="tool_usage")
    op.drop_index("ix_tool_usage_used_at", table_name="tool_usage")
    op.drop_index("ix_tool_usage_used_by_user_id", table_name="tool_usage")
    op.drop_index("ix_tool_usage_project_id", table_name="tool_usage")
    op.drop_index("ix_tool_usage_tool_code", table_name="tool_usage")
    op.drop_table("tool_usage")

    with op.batch_alter_table("tool") as batch_op:
        batch_op.drop_index("ix_tool_reviewed_by_user_id")
        batch_op.drop_index("ix_tool_status")
        batch_op.drop_constraint("fk_tool_reviewed_by_user", type_="foreignkey")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("status")
