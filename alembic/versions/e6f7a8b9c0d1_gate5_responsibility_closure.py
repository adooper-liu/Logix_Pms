"""add version-bound Gate 5 responsibility closure fields and evidence"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("node_assignment") as batch:
        batch.add_column(sa.Column("model_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("approver_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("backup_assignee_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("effective_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("effective_to", sa.Date(), nullable=True))
        batch.create_foreign_key(
            "fk_node_assignment_model_version",
            "process_model_version",
            ["model_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_node_assignment_approver",
            "app_user",
            ["approver_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_node_assignment_backup",
            "app_user",
            ["backup_assignee_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_node_assignment_model_version_id", ["model_version_id"])
        batch.create_index("ix_node_assignment_approver_user_id", ["approver_user_id"])
        batch.create_index(
            "ix_node_assignment_backup_assignee_user_id", ["backup_assignee_user_id"]
        )

    op.create_table(
        "process_responsibility_acceptance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("node_key", sa.String(length=64), nullable=True),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("subject_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["process_id"], ["process_arch.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["model_version_id"], ["process_model_version.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["subject_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_process_responsibility_acceptance_process_id",
        "process_responsibility_acceptance",
        ["process_id"],
    )
    op.create_index(
        "ix_process_responsibility_acceptance_model_version_id",
        "process_responsibility_acceptance",
        ["model_version_id"],
    )
    op.create_index(
        "ix_process_responsibility_acceptance_node_key",
        "process_responsibility_acceptance",
        ["node_key"],
    )
    op.create_index(
        "ix_process_responsibility_acceptance_scope", "process_responsibility_acceptance", ["scope"]
    )
    op.create_index(
        "ix_process_responsibility_acceptance_subject_user_id",
        "process_responsibility_acceptance",
        ["subject_user_id"],
    )
    op.create_index(
        "ix_process_responsibility_acceptance_accepted_by_user_id",
        "process_responsibility_acceptance",
        ["accepted_by_user_id"],
    )
    op.create_index(
        "ix_process_responsibility_acceptance_status",
        "process_responsibility_acceptance",
        ["status"],
    )
    op.create_index(
        "uq_responsibility_acceptance_current",
        "process_responsibility_acceptance",
        ["process_id", "model_version_id", "node_key", "scope", "subject_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACCEPTED'"),
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_responsibility_acceptance_current", table_name="process_responsibility_acceptance"
    )
    for name in (
        "ix_process_responsibility_acceptance_status",
        "ix_process_responsibility_acceptance_accepted_by_user_id",
        "ix_process_responsibility_acceptance_subject_user_id",
        "ix_process_responsibility_acceptance_scope",
        "ix_process_responsibility_acceptance_node_key",
        "ix_process_responsibility_acceptance_model_version_id",
        "ix_process_responsibility_acceptance_process_id",
    ):
        op.drop_index(name, table_name="process_responsibility_acceptance")
    op.drop_table("process_responsibility_acceptance")
    with op.batch_alter_table("node_assignment") as batch:
        for name in (
            "fk_node_assignment_backup",
            "fk_node_assignment_approver",
            "fk_node_assignment_model_version",
        ):
            batch.drop_constraint(name, type_="foreignkey")
        for name in (
            "ix_node_assignment_backup_assignee_user_id",
            "ix_node_assignment_approver_user_id",
            "ix_node_assignment_model_version_id",
        ):
            batch.drop_index(name)
        for name in (
            "effective_to",
            "effective_from",
            "backup_assignee_user_id",
            "approver_user_id",
            "model_version_id",
        ):
            batch.drop_column(name)
