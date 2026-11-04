"""thin process improvement round

Revision ID: x9c0d1e2f3a4
Revises: w8b9c0d1e2f3
"""

import sqlalchemy as sa

from alembic import op

revision = "x9c0d1e2f3a4"
down_revision = "w8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "process_improvement_round",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "process_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "supersedes_id",
            sa.Integer(),
            sa.ForeignKey("process_improvement_round.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("scope_note", sa.Text(), nullable=False),
        sa.Column(
            "asis_model_version_id",
            sa.Integer(),
            sa.ForeignKey("process_model_version.id", ondelete="RESTRICT", name="fk_round_asis"),
            nullable=True,
        ),
        sa.Column(
            "tobe_model_version_id",
            sa.Integer(),
            sa.ForeignKey("process_model_version.id", ondelete="RESTRICT", name="fk_round_tobe"),
            nullable=True,
        ),
        sa.Column(
            "released_model_version_id",
            sa.Integer(),
            sa.ForeignKey(
                "process_model_version.id", ondelete="RESTRICT", name="fk_round_released"
            ),
            nullable=True,
        ),
        *[
            sa.Column(
                key,
                sa.JSON(),
                nullable=key in ("acceptance_snapshot", "after_window", "after_samples"),
            )
            for key in (
                "metric_contracts",
                "baseline_window",
                "baseline_samples",
                "acceptance_snapshot",
                "after_window",
                "after_samples",
                "model_hashes",
            )
        ],
        *[
            sa.Column(key, sa.DateTime(), nullable=True)
            for key in ("baseline_confirmed_at", "acceptance_locked_at")
        ],
        *[
            sa.Column(
                key, sa.Integer(), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
            )
            for key in ("baseline_confirmed_by_id", "acceptance_locked_by_id", "created_by_id")
        ],
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_process_improvement_round_process_id", "process_improvement_round", ["process_id"]
    )
    op.create_index(
        "ix_process_improvement_round_project_id", "process_improvement_round", ["project_id"]
    )


def downgrade():
    op.drop_table("process_improvement_round")
