"""filled tool templates mounted on a process

Revision ID: n8b9c0d1e2f3
Revises: m7a8b9c0d1e2
Create Date: 2026-11-01 17:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "n8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "m7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_sheet",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tool_code", sa.String(length=32), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("objective_id", sa.Integer(), nullable=True),
        sa.Column("step_no", sa.String(length=8), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tool_code"], ["tool.code"], ondelete="CASCADE", name="fk_tool_sheet_tool"),
        sa.ForeignKeyConstraint(
            ["process_id"], ["process_arch.id"], ondelete="CASCADE", name="fk_tool_sheet_process"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], ondelete="SET NULL", name="fk_tool_sheet_project"
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["strategy_objective.id"],
            ondelete="SET NULL",
            name="fk_tool_sheet_objective",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["app_user.id"], ondelete="SET NULL", name="fk_tool_sheet_user"
        ),
    )
    op.create_index("ix_tool_sheet_tool_code", "tool_sheet", ["tool_code"])
    op.create_index("ix_tool_sheet_process_id", "tool_sheet", ["process_id"])
    op.create_index("ix_tool_sheet_project_id", "tool_sheet", ["project_id"])
    op.create_index("ix_tool_sheet_objective_id", "tool_sheet", ["objective_id"])
    op.create_index("ix_tool_sheet_created_at", "tool_sheet", ["created_at"])
    op.create_index("ix_tool_sheet_process_tool", "tool_sheet", ["process_id", "tool_code"])


def downgrade() -> None:
    op.drop_index("ix_tool_sheet_process_tool", table_name="tool_sheet")
    op.drop_index("ix_tool_sheet_created_at", table_name="tool_sheet")
    op.drop_index("ix_tool_sheet_objective_id", table_name="tool_sheet")
    op.drop_index("ix_tool_sheet_project_id", table_name="tool_sheet")
    op.drop_index("ix_tool_sheet_process_id", table_name="tool_sheet")
    op.drop_index("ix_tool_sheet_tool_code", table_name="tool_sheet")
    op.drop_table("tool_sheet")
