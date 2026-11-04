"""work context and purpose receipt on original tool sheet

Revision ID: w8b9c0d1e2f3
Revises: v7a8b9c0d1e2
"""

import sqlalchemy as sa

from alembic import op

revision = "w8b9c0d1e2f3"
down_revision = "v7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tool_sheet") as batch:
        batch.add_column(sa.Column("work_context", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("review", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("tool_sheet") as batch:
        batch.drop_column("review")
        batch.drop_column("work_context")
