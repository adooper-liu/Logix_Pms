"""original outcome, operation and replication evidence

Revision ID: a2f3a4b5c6d7
Revises: z1e2f3a4b5c6
"""

import sqlalchemy as sa
from alembic import op

revision = "a2f3a4b5c6d7"
down_revision = "z1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_training_record") as b:
        b.add_column(sa.Column("operation", sa.JSON(), nullable=True))
        b.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("replication_pack") as b:
        b.add_column(sa.Column("source_snapshot", sa.JSON(), nullable=True))
        b.add_column(sa.Column("receipt", sa.JSON(), nullable=True))
        b.add_column(sa.Column("receiver_user_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
        b.create_foreign_key(
            "fk_pack_receiver", "app_user", ["receiver_user_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("gate_attestation") as b:
        b.add_column(sa.Column("round_id", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column("purpose", sa.String(32), nullable=False, server_default="STAGE_GATE")
        )
        b.add_column(sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
        b.create_foreign_key(
            "fk_gate_round", "process_improvement_round", ["round_id"], ["id"], ondelete="RESTRICT"
        )
        b.create_index("ix_gate_attestation_round_id", ["round_id"])


def downgrade():
    with op.batch_alter_table("process_training_record") as b:
        b.drop_column("revision")
        b.drop_column("operation")
    with op.batch_alter_table("replication_pack") as b:
        b.drop_constraint("fk_pack_receiver", type_="foreignkey")
        b.drop_column("revision")
        b.drop_column("receiver_user_id")
        b.drop_column("receipt")
        b.drop_column("source_snapshot")
    with op.batch_alter_table("gate_attestation") as b:
        b.drop_index("ix_gate_attestation_round_id")
        b.drop_constraint("fk_gate_round", type_="foreignkey")
        b.drop_column("evidence_snapshot")
        b.drop_column("purpose")
        b.drop_column("round_id")
