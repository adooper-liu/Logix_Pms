"""deliverable version model source

Revision ID: ffffc3c1106f
Revises: f5a6b7c8d9e0
Create Date: 2026-10-25 20:45:31.242751

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ffffc3c1106f"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("deliverable_version") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_kind",
                sa.String(length=16),
                server_default="FILE",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("source_model_version_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_deliverable_version_source_model",
            "process_model_version",
            ["source_model_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_deliverable_version_source_model_version_id",
        "deliverable_version",
        ["source_model_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deliverable_version_source_model_version_id",
        table_name="deliverable_version",
    )
    with op.batch_alter_table("deliverable_version") as batch_op:
        batch_op.drop_constraint("fk_deliverable_version_source_model", type_="foreignkey")
        batch_op.drop_column("source_model_version_id")
        batch_op.drop_column("source_kind")
