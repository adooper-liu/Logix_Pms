"""add explicit key process coverage fields

Revision ID: a2b3c4d5e6f7
Revises: z1e2f3a4b5c6
"""

import sqlalchemy as sa

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "h0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_arch") as batch:
        batch.add_column(
            sa.Column("is_key_process", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("key_basis", sa.String(200), nullable=True))
        batch.create_index("ix_process_arch_is_key_process", ["is_key_process"] )


def downgrade():
    with op.batch_alter_table("process_arch") as batch:
        batch.drop_index("ix_process_arch_is_key_process")
        batch.drop_column("key_basis")
        batch.drop_column("is_key_process")
