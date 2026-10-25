"""document levels and authorization exception review

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("process_document") as batch_op:
        batch_op.add_column(
            sa.Column("level", sa.String(length=16), nullable=False, server_default="PROCESS")
        )
        batch_op.add_column(sa.Column("legal_entity", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("plant", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("product_family", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("language", sa.String(length=16), nullable=False, server_default="zh-CN")
        )
        batch_op.add_column(sa.Column("control_points", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("exception_terms", sa.Text(), nullable=True))
        batch_op.create_index("ix_process_document_level", ["level"])
        batch_op.create_index("ix_process_document_legal_entity", ["legal_entity"])
        batch_op.create_index("ix_process_document_plant", ["plant"])
        batch_op.create_index("ix_process_document_product_family", ["product_family"])

    with op.batch_alter_table("authorization_exception") as batch_op:
        batch_op.add_column(sa.Column("review_due_at", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_auth_exception_reviewed_by",
            "app_user",
            ["reviewed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_authorization_exception_review_due_at", ["review_due_at"])
        batch_op.create_index(
            "ix_authorization_exception_reviewed_by_user_id", ["reviewed_by_user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("authorization_exception") as batch_op:
        batch_op.drop_index("ix_authorization_exception_reviewed_by_user_id")
        batch_op.drop_index("ix_authorization_exception_review_due_at")
        batch_op.drop_constraint("fk_auth_exception_reviewed_by", type_="foreignkey")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_due_at")

    with op.batch_alter_table("process_document") as batch_op:
        batch_op.drop_index("ix_process_document_product_family")
        batch_op.drop_index("ix_process_document_plant")
        batch_op.drop_index("ix_process_document_legal_entity")
        batch_op.drop_index("ix_process_document_level")
        batch_op.drop_column("exception_terms")
        batch_op.drop_column("control_points")
        batch_op.drop_column("language")
        batch_op.drop_column("product_family")
        batch_op.drop_column("plant")
        batch_op.drop_column("legal_entity")
        batch_op.drop_column("level")
