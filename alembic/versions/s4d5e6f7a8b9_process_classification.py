"""process classification

Revision ID: s4d5e6f7a8b9
Revises: r3c4d5e6f7a8
"""

import sqlalchemy as sa

from alembic import op

revision = "s4d5e6f7a8b9"
down_revision = "r3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_arch") as batch:
        batch.add_column(sa.Column("process_type", sa.String(16), nullable=True))
        batch.add_column(sa.Column("classification_basis", sa.Text(), nullable=True))
        batch.add_column(sa.Column("classification_inherit", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("classification_revision", sa.Integer(), nullable=False, server_default="0"))
        batch.create_index("ix_process_arch_process_type", ["process_type"])


def downgrade():
    with op.batch_alter_table("process_arch") as batch:
        batch.drop_index("ix_process_arch_process_type")
        for column in ("classification_revision", "classification_inherit", "classification_basis", "process_type"):
            batch.drop_column(column)
