"""add sibling boundary lines and map coverage items

Revision ID: k5e6f7a8b9c0
Revises: j4d5e6f7a8b9
Create Date: 2026-11-01 12:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "k5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "j4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sibling_boundary_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.String(length=200), nullable=False),
        sa.Column("ends_at", sa.String(length=200), nullable=False),
        sa.Column("in_scope", sa.Text(), nullable=False),
        sa.Column("out_of_scope", sa.Text(), nullable=False),
        sa.Column("distinct_work", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["process_arch.id"],
            name="fk_sibling_line_parent",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["process_arch.id"],
            name="fk_sibling_line_child",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "child_id", name="uq_sibling_boundary_line"),
    )
    op.create_index(
        "ix_sibling_boundary_line_parent_id", "sibling_boundary_line", ["parent_id"]
    )
    op.create_index(
        "ix_sibling_boundary_line_child_id", "sibling_boundary_line", ["child_id"]
    )
    op.create_table(
        "map_coverage_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=True),
        sa.Column("excluded", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_coverage_item_process",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["app_user.id"],
            name="fk_coverage_item_author",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_map_coverage_item_process_id", "map_coverage_item", ["process_id"])
    op.create_index(
        "ix_map_coverage_item_author_user_id", "map_coverage_item", ["author_user_id"]
    )


def downgrade() -> None:
    op.drop_table("map_coverage_item")
    op.drop_table("sibling_boundary_line")
