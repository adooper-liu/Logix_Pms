"""CSV event log imports

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0

事件日志导入与活动映射；提交只生成 LOGGED 证据主张，不改 BPMN。
"""

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "process_log_import",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("claim_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_name", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_log_import_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_log_import_model_version",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["evidence_claim.id"],
            name="fk_log_import_claim",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["app_user.id"],
            name="fk_log_import_creator",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_process_log_import_process_id", "process_log_import", ["process_id"])
    op.create_index(
        "ix_process_log_import_model_version_id", "process_log_import", ["model_version_id"]
    )
    op.create_index("ix_process_log_import_status", "process_log_import", ["status"])
    op.create_index("ix_process_log_import_claim_id", "process_log_import", ["claim_id"])

    op.create_table(
        "process_log_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("activity_label", sa.String(length=200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=True),
        sa.Column("mapped_activity_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["process_log_import.id"],
            name="fk_log_event_import",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mapped_activity_id"],
            ["process_arch.id"],
            name="fk_log_event_activity",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_process_log_event_import_id", "process_log_event", ["import_id"])
    op.create_index("ix_process_log_event_case_id", "process_log_event", ["case_id"])
    op.create_index("ix_process_log_event_activity_label", "process_log_event", ["activity_label"])
    op.create_index("ix_process_log_event_occurred_at", "process_log_event", ["occurred_at"])
    op.create_index(
        "ix_process_log_event_mapped_activity_id",
        "process_log_event",
        ["mapped_activity_id"],
    )
    op.create_index(
        "ix_log_event_import_case_time",
        "process_log_event",
        ["import_id", "case_id", "occurred_at"],
    )


def downgrade():
    op.drop_table("process_log_event")
    op.drop_table("process_log_import")
