"""DMAIC stage tracking for improvement projects

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(sa.Column("dmaic_stage", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("dmaic_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("dmaic_updated_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_project_dmaic_stage", ["dmaic_stage"])


def downgrade() -> None:
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_index("ix_project_dmaic_stage")
        batch_op.drop_column("dmaic_updated_at")
        batch_op.drop_column("dmaic_note")
        batch_op.drop_column("dmaic_stage")
