"""decision tables

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_table",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "process_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("node_key", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hit_policy", sa.String(length=16), nullable=False, server_default="FIRST"),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_decision_table_code", "decision_table", ["code"], unique=True)
    op.create_index("ix_decision_table_process_id", "decision_table", ["process_id"])
    op.create_index("ix_decision_table_node_key", "decision_table", ["node_key"])
    op.create_index("ix_decision_table_hit_policy", "decision_table", ["hit_policy"])
    op.create_index("ix_decision_table_is_active", "decision_table", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_decision_table_is_active", table_name="decision_table")
    op.drop_index("ix_decision_table_hit_policy", table_name="decision_table")
    op.drop_index("ix_decision_table_node_key", table_name="decision_table")
    op.drop_index("ix_decision_table_process_id", table_name="decision_table")
    op.drop_index("ix_decision_table_code", table_name="decision_table")
    op.drop_table("decision_table")
