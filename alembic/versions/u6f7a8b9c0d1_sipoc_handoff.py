"""sipoc handoff on original sheet

Revision ID: u6f7a8b9c0d1
Revises: t5e6f7a8b9c0
"""

import sqlalchemy as sa

from alembic import op

revision = "u6f7a8b9c0d1"
down_revision = "t5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tool_sheet") as batch:
        batch.add_column(sa.Column("template_version_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("handoff", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key(
            "fk_sheet_template_version",
            "tool_template_version",
            ["template_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade():
    with op.batch_alter_table("tool_sheet") as batch:
        batch.drop_constraint("fk_sheet_template_version", type_="foreignkey")
        batch.drop_column("revision")
        batch.drop_column("handoff")
        batch.drop_column("template_version_id")
