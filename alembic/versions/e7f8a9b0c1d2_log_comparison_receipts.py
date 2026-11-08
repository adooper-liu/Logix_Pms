"""log comparison receipts

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1

记录前后对照的人工接收结论；claim_allowed 是“可宣称改善”的门禁结果。
"""

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "log_comparison_receipt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("before_import_id", sa.Integer(), nullable=False),
        sa.Column("after_import_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("comparable", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sample_ok", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("claim_allowed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("accepted_by_id", sa.Integer(), nullable=True),
        sa.Column("accepted_by_name", sa.String(length=64), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_log_receipt_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["before_import_id"],
            ["process_log_import.id"],
            name="fk_log_receipt_before",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["after_import_id"],
            ["process_log_import.id"],
            name="fk_log_receipt_after",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_id"],
            ["app_user.id"],
            name="fk_log_receipt_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_log_comparison_receipt_process_id",
        "log_comparison_receipt",
        ["process_id"],
    )
    op.create_index(
        "ix_log_comparison_receipt_before_import_id",
        "log_comparison_receipt",
        ["before_import_id"],
    )
    op.create_index(
        "ix_log_comparison_receipt_after_import_id",
        "log_comparison_receipt",
        ["after_import_id"],
    )
    op.create_index(
        "ix_log_comparison_receipt_decision",
        "log_comparison_receipt",
        ["decision"],
    )
    op.create_index(
        "ix_log_comparison_receipt_claim_allowed",
        "log_comparison_receipt",
        ["claim_allowed"],
    )
    op.create_index(
        "ix_log_receipt_pair",
        "log_comparison_receipt",
        ["process_id", "before_import_id", "after_import_id", "id"],
    )


def downgrade():
    op.drop_table("log_comparison_receipt")
