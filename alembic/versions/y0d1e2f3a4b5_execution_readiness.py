"""execution readiness and direct instance identity

Revision ID: y0d1e2f3a4b5
Revises: x9c0d1e2f3a4
"""

import sqlalchemy as sa

from alembic import op

revision = "y0d1e2f3a4b5"
down_revision = "x9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_execution_config") as batch:
        batch.add_column(sa.Column("readiness", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("readiness_revision", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("process_instance") as batch:
        batch.add_column(sa.Column("model_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("round_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_instance_model_identity",
            "process_model_version",
            ["model_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_instance_round",
            "process_improvement_round",
            ["round_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_process_instance_model_version_id", ["model_version_id"])
        batch.create_index("ix_process_instance_round_id", ["round_id"])
    with op.batch_alter_table("pilot_layer") as batch:
        batch.add_column(sa.Column("applicability", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("pilot_layer") as batch:
        batch.drop_column("revision")
        batch.drop_column("applicability")
    with op.batch_alter_table("process_instance") as batch:
        batch.drop_index("ix_process_instance_round_id")
        batch.drop_index("ix_process_instance_model_version_id")
        batch.drop_constraint("fk_instance_round", type_="foreignkey")
        batch.drop_constraint("fk_instance_model_identity", type_="foreignkey")
        batch.drop_column("round_id")
        batch.drop_column("model_version_id")
    with op.batch_alter_table("process_execution_config") as batch:
        batch.drop_column("readiness_revision")
        batch.drop_column("readiness")
