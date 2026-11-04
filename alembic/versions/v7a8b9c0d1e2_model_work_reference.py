"""freeze original model version for work reference

Revision ID: v7a8b9c0d1e2
Revises: u6f7a8b9c0d1
"""

import sqlalchemy as sa

from alembic import op

revision = "v7a8b9c0d1e2"
down_revision = "u6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_model_version") as batch:
        batch.add_column(sa.Column("frozen_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("process_model_version") as batch:
        batch.drop_column("frozen_at")
