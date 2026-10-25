"""replication packs

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "replication_pack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("benefit_evidence", sa.Text(), nullable=True),
        sa.Column("failure_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("knowledge_ids", sa.JSON(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("template_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_replication_pack_source_project_id", "replication_pack", ["source_project_id"]
    )
    op.create_index("ix_replication_pack_status", "replication_pack", ["status"])
    op.create_index("ix_replication_pack_owner_user_id", "replication_pack", ["owner_user_id"])
    op.create_index(
        "ix_replication_pack_project_status", "replication_pack", ["source_project_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_replication_pack_project_status", table_name="replication_pack")
    op.drop_index("ix_replication_pack_owner_user_id", table_name="replication_pack")
    op.drop_index("ix_replication_pack_status", table_name="replication_pack")
    op.drop_index("ix_replication_pack_source_project_id", table_name="replication_pack")
    op.drop_table("replication_pack")
