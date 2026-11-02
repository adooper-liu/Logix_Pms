"""add map coverage, event logs, rpa runs, cases, technology uses

Revision ID: j4d5e6f7a8b9
Revises: i3c4d5e6f7a8
Create Date: 2026-11-01 12:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "j4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "i3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "map_coverage_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("covers_company", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["app_user.id"],
            name="fk_map_coverage_reviewer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_map_coverage_review_reviewer_user_id",
        "map_coverage_review",
        ["reviewer_user_id"],
    )
    op.create_table(
        "process_event_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("case_key", sa.String(length=80), nullable=False),
        sa.Column("activity_name", sa.String(length=200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_event_log_process",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_event_log_process_id", "process_event_log", ["process_id"])
    op.create_index("ix_process_event_log_case_key", "process_event_log", ["case_key"])
    op.create_index("ix_process_event_log_occurred_at", "process_event_log", ["occurred_at"])
    op.create_table(
        "rpa_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("ran_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["rpa_bot.id"], name="fk_rpa_run_bot", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["integration_endpoint.id"],
            name="fk_rpa_run_endpoint",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rpa_run_bot_id", "rpa_run", ["bot_id"])
    op.create_index("ix_rpa_run_ran_at", "rpa_run", ["ran_at"])
    op.create_index("ix_rpa_run_endpoint_id", "rpa_run", ["endpoint_id"])
    op.create_table(
        "process_case",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_process_case_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.id"],
            name="fk_process_case_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_case_process_id", "process_case", ["process_id"])
    op.create_index("ix_process_case_owner_user_id", "process_case", ["owner_user_id"])
    op.create_table(
        "process_technology_use",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("usage_note", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_technology_use_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.id"],
            name="fk_technology_use_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_process_technology_use_process_id", "process_technology_use", ["process_id"]
    )
    op.create_index("ix_process_technology_use_kind", "process_technology_use", ["kind"])
    op.create_index(
        "ix_process_technology_use_owner_user_id",
        "process_technology_use",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_table("process_technology_use")
    op.drop_table("process_case")
    op.drop_table("rpa_run")
    op.drop_table("process_event_log")
    op.drop_table("map_coverage_review")
