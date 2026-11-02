"""add sibling boundary review, rpa bot, and training attendance

Revision ID: i3c4d5e6f7a8
Revises: h2b3c4d5e6f7
Create Date: 2026-11-01 11:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "i3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "h2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sibling_boundary_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("overlap_found", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["process_arch.id"],
            name="fk_sibling_boundary_parent",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["app_user.id"],
            name="fk_sibling_boundary_reviewer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id"),
    )
    op.create_index(
        "ix_sibling_boundary_review_parent_id",
        "sibling_boundary_review",
        ["parent_id"],
    )
    op.create_index(
        "ix_sibling_boundary_review_reviewer_user_id",
        "sibling_boundary_review",
        ["reviewer_user_id"],
    )
    op.create_table(
        "rpa_bot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("activity_name", sa.String(length=200), nullable=False),
        sa.Column("bot_name", sa.String(length=200), nullable=False),
        sa.Column("manual_step", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.id"],
            name="fk_rpa_bot_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_rpa_bot_process",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rpa_bot_process_id", "rpa_bot", ["process_id"])
    op.create_index("ix_rpa_bot_owner_user_id", "rpa_bot", ["owner_user_id"])
    op.create_table(
        "process_training_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("trainee_user_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_process_training_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trainee_user_id"],
            ["app_user.id"],
            name="fk_process_training_trainee",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_process_training_record_process_id",
        "process_training_record",
        ["process_id"],
    )
    op.create_index(
        "ix_process_training_record_trainee_user_id",
        "process_training_record",
        ["trainee_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_process_training_record_trainee_user_id",
        table_name="process_training_record",
    )
    op.drop_index("ix_process_training_record_process_id", table_name="process_training_record")
    op.drop_table("process_training_record")
    op.drop_index("ix_rpa_bot_owner_user_id", table_name="rpa_bot")
    op.drop_index("ix_rpa_bot_process_id", table_name="rpa_bot")
    op.drop_table("rpa_bot")
    op.drop_index(
        "ix_sibling_boundary_review_reviewer_user_id",
        table_name="sibling_boundary_review",
    )
    op.drop_index("ix_sibling_boundary_review_parent_id", table_name="sibling_boundary_review")
    op.drop_table("sibling_boundary_review")
