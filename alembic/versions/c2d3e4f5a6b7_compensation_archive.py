"""取消补偿与实例归档

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compensation_action",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "process_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("process_id", "node_key", name="uq_compensation_action_process_node"),
    )
    op.create_index("ix_compensation_action_process_id", "compensation_action", ["process_id"])
    op.create_index("ix_compensation_action_node_key", "compensation_action", ["node_key"])
    op.create_index("ix_compensation_action_is_active", "compensation_action", ["is_active"])

    op.create_table(
        "compensation_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instance_id",
            sa.Integer(),
            sa.ForeignKey("process_instance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("process_task.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "completed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_compensation_record_instance_id", "compensation_record", ["instance_id"])
    op.create_index("ix_compensation_record_task_id", "compensation_record", ["task_id"])
    op.create_index("ix_compensation_record_status", "compensation_record", ["status"])
    op.create_index("ix_compensation_record_created_at", "compensation_record", ["created_at"])
    op.create_index(
        "ix_compensation_record_instance_status",
        "compensation_record",
        ["instance_id", "status"],
    )

    op.add_column("process_instance", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.create_index("ix_process_instance_archived_at", "process_instance", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_process_instance_archived_at", table_name="process_instance")
    op.drop_column("process_instance", "archived_at")

    op.drop_index("ix_compensation_record_instance_status", table_name="compensation_record")
    op.drop_index("ix_compensation_record_created_at", table_name="compensation_record")
    op.drop_index("ix_compensation_record_status", table_name="compensation_record")
    op.drop_index("ix_compensation_record_task_id", table_name="compensation_record")
    op.drop_index("ix_compensation_record_instance_id", table_name="compensation_record")
    op.drop_table("compensation_record")

    op.drop_index("ix_compensation_action_is_active", table_name="compensation_action")
    op.drop_index("ix_compensation_action_node_key", table_name="compensation_action")
    op.drop_index("ix_compensation_action_process_id", table_name="compensation_action")
    op.drop_table("compensation_action")
