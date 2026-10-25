"""L5 task definitions and work measurement binding

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_task_definition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_task_activity"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "position_id",
            sa.Integer(),
            sa.ForeignKey("position.id", ondelete="SET NULL", name="fk_task_position"),
            nullable=True,
        ),
        sa.Column("standard_minutes", sa.Float(), nullable=True),
        sa.Column("frequency", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("activity_id", "code", name="uq_process_task_activity_code"),
    )
    op.create_index(
        "ix_process_task_definition_activity_id", "process_task_definition", ["activity_id"]
    )
    op.create_index(
        "ix_process_task_definition_position_id", "process_task_definition", ["position_id"]
    )
    op.create_index(
        "ix_process_task_definition_is_active", "process_task_definition", ["is_active"]
    )
    op.create_index(
        "ix_process_task_activity_sort", "process_task_definition", ["activity_id", "sort_order"]
    )

    with op.batch_alter_table("work_measurement_standard") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_wms_task",
            "process_task_definition",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_work_measurement_standard_task_id", ["task_id"])


def downgrade() -> None:
    with op.batch_alter_table("work_measurement_standard") as batch_op:
        batch_op.drop_index("ix_work_measurement_standard_task_id")
        batch_op.drop_constraint("fk_wms_task", type_="foreignkey")
        batch_op.drop_column("task_id")

    op.drop_index("ix_process_task_activity_sort", table_name="process_task_definition")
    op.drop_index("ix_process_task_definition_is_active", table_name="process_task_definition")
    op.drop_index("ix_process_task_definition_position_id", table_name="process_task_definition")
    op.drop_index("ix_process_task_definition_activity_id", table_name="process_task_definition")
    op.drop_table("process_task_definition")
