"""process charter context

Revision ID: t5e6f7a8b9c0
Revises: s4d5e6f7a8b9
"""

import sqlalchemy as sa

from alembic import op

revision = "t5e6f7a8b9c0"
down_revision = "s4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_charter") as batch:
        batch.add_column(sa.Column("details", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("process_charter") as batch:
        batch.drop_column("revision")
        batch.drop_column("details")
