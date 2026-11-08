"""document candidate activities

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9

从制度/操作文档抽取的候选活动暂存表。确认后才写 L4 活动，不自动改 BPMN。
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_candidate_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["process_document_version.id"],
            name="fk_document_candidate_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_document_candidate_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["process_arch.id"],
            name="fk_document_candidate_activity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["app_user.id"],
            name="fk_document_candidate_creator",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_document_candidate_confirmer",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "document_version_id", "line_no", name="uq_document_candidate_line"
        ),
    )
    op.create_index(
        "ix_document_candidate_activity_document_version_id",
        "document_candidate_activity",
        ["document_version_id"],
    )
    op.create_index(
        "ix_document_candidate_activity_process_id",
        "document_candidate_activity",
        ["process_id"],
    )
    op.create_index(
        "ix_document_candidate_activity_status",
        "document_candidate_activity",
        ["status"],
    )
    op.create_index(
        "ix_document_candidate_activity_activity_id",
        "document_candidate_activity",
        ["activity_id"],
    )
    op.create_index(
        "ix_document_candidate_process_status",
        "document_candidate_activity",
        ["process_id", "status"],
    )


def downgrade():
    op.drop_table("document_candidate_activity")
