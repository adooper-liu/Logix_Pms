"""project org scope

Revision ID: q2b3c4d5e6f7
Revises: p1a2b3c4d5e6
Create Date: 2026-11-02 23:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "p1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("org_unit_id", sa.Integer(), nullable=True))
        batch.create_index("ix_project_org_unit_id", ["org_unit_id"])
        batch.create_foreign_key(
            "fk_project_org_unit",
            "org_unit",
            ["org_unit_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.drop_constraint("fk_project_org_unit", type_="foreignkey")
        batch.drop_index("ix_project_org_unit_id")
        batch.drop_column("org_unit_id")
