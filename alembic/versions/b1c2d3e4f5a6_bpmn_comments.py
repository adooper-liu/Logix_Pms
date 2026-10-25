"""BPMN element comments

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_comment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "process_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("element_id", sa.String(length=64), nullable=False),
        sa.Column("element_name", sa.String(length=128), nullable=True),
        sa.Column("element_type", sa.String(length=32), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_name", sa.String(length=64), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_process_comment_process_id", "process_comment", ["process_id"])
    op.create_index("ix_process_comment_element_id", "process_comment", ["element_id"])
    op.create_index("ix_process_comment_status", "process_comment", ["status"])
    op.create_index("ix_process_comment_created_at", "process_comment", ["created_at"])
    op.create_index(
        "ix_process_comment_process_element", "process_comment", ["process_id", "element_id"]
    )
    op.create_index(
        "ix_process_comment_process_status", "process_comment", ["process_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_process_comment_process_status", table_name="process_comment")
    op.drop_index("ix_process_comment_process_element", table_name="process_comment")
    op.drop_index("ix_process_comment_created_at", table_name="process_comment")
    op.drop_index("ix_process_comment_status", table_name="process_comment")
    op.drop_index("ix_process_comment_element_id", table_name="process_comment")
    op.drop_index("ix_process_comment_process_id", table_name="process_comment")
    op.drop_table("process_comment")
