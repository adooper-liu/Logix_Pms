"""knowledge operations: full-text search, review history, recommend log

Revision ID: d1e2f3a4b5c6
Revises: c9a1b2c3d4e5
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_item", sa.Column("search_text", sa.Text(), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE knowledge_item SET search_text = trim("
            "coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || "
            "coalesce(content, '') || ' ' || coalesce(claim, '') || ' ' || "
            "coalesce(applicable_when, '') || ' ' || coalesce(not_applicable_when, ''))"
        )
    )
    if bind.dialect.name == "postgresql":
        # pg_trgm 让 ILIKE '%关键词%' 能走 GIN 索引；中文不需要额外分词器
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            "ix_knowledge_item_search_text_trgm",
            "knowledge_item",
            ["search_text"],
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        )
    else:
        op.create_index("ix_knowledge_item_search_text_trgm", "knowledge_item", ["search_text"])

    op.create_table(
        "knowledge_review",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_review_knowledge_id", "knowledge_review", ["knowledge_id"])
    op.create_index(
        "ix_knowledge_review_reviewer_user_id", "knowledge_review", ["reviewer_user_id"]
    )
    op.create_index("ix_knowledge_review_created_at", "knowledge_review", ["created_at"])

    op.create_table(
        "knowledge_recommend_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("scenario_codes", sa.JSON(), nullable=False),
        sa.Column("stage_no", sa.Integer(), nullable=True),
        sa.Column("step_no", sa.String(length=8), nullable=True),
        sa.Column("result_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_recommend_log_user_id", "knowledge_recommend_log", ["user_id"])
    op.create_index(
        "ix_knowledge_recommend_log_created_at", "knowledge_recommend_log", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_recommend_log_created_at", table_name="knowledge_recommend_log")
    op.drop_index("ix_knowledge_recommend_log_user_id", table_name="knowledge_recommend_log")
    op.drop_table("knowledge_recommend_log")

    op.drop_index("ix_knowledge_review_created_at", table_name="knowledge_review")
    op.drop_index("ix_knowledge_review_reviewer_user_id", table_name="knowledge_review")
    op.drop_index("ix_knowledge_review_knowledge_id", table_name="knowledge_review")
    op.drop_table("knowledge_review")

    op.drop_index("ix_knowledge_item_search_text_trgm", table_name="knowledge_item")
    op.drop_column("knowledge_item", "search_text")
