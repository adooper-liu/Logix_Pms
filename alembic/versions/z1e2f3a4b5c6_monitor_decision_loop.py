"""explicit measurement on original KPI

Revision ID: z1e2f3a4b5c6
Revises: y0d1e2f3a4b5
"""

import sqlalchemy as sa
from alembic import op

revision = "z1e2f3a4b5c6"
down_revision = "y0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("kpi_definition") as batch:
        batch.add_column(sa.Column("measurement", sa.JSON(), nullable=True))
    with op.batch_alter_table("exception_event") as batch:
        batch.add_column(sa.Column("resolution", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("kpi_record") as batch:
        batch.add_column(sa.Column("provenance", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("exception_event") as batch:
        batch.drop_column("revision")
        batch.drop_column("resolution")
    with op.batch_alter_table("kpi_record") as batch:
        batch.drop_column("revision")
        batch.drop_column("provenance")
    with op.batch_alter_table("kpi_definition") as batch:
        batch.drop_column("measurement")
