"""add process charter for stage-1 scope

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-11-01 10:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_charter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.String(length=200), nullable=False),
        sa.Column("ends_at", sa.String(length=200), nullable=False),
        sa.Column("in_scope", sa.Text(), nullable=False),
        sa.Column("out_of_scope", sa.Text(), nullable=False),
        sa.Column("stop_condition", sa.Text(), nullable=False),
        sa.Column("sponsor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_process_charter_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sponsor_user_id"],
            ["app_user.id"],
            name="fk_process_charter_sponsor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("process_id"),
    )
    op.create_index("ix_process_charter_process_id", "process_charter", ["process_id"])
    op.create_index(
        "ix_process_charter_sponsor_user_id", "process_charter", ["sponsor_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_process_charter_sponsor_user_id", table_name="process_charter")
    op.drop_index("ix_process_charter_process_id", table_name="process_charter")
    op.drop_table("process_charter")
