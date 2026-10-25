"""BPMN element documentation and default branch

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("process_node") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
    with op.batch_alter_table("process_edge") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )


def downgrade() -> None:
    with op.batch_alter_table("process_edge") as batch_op:
        batch_op.drop_column("is_default")
        batch_op.drop_column("description")
    with op.batch_alter_table("process_node") as batch_op:
        batch_op.drop_column("description")
