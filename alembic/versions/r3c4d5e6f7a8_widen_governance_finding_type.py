"""widen governance finding type and align postgres unique constraints

Revision ID: r3c4d5e6f7a8
Revises: q2b3c4d5e6f7
Create Date: 2026-11-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "r3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "q2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("governance_finding") as batch:
        batch.alter_column(
            "type", existing_type=sa.String(32), type_=sa.String(64), existing_nullable=False
        )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("process_charter_process_id_key", "process_charter", type_="unique")
        op.drop_constraint(
            "sibling_boundary_review_parent_id_key", "sibling_boundary_review", type_="unique"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(
            "process_charter_process_id_key", "process_charter", ["process_id"]
        )
        op.create_unique_constraint(
            "sibling_boundary_review_parent_id_key", "sibling_boundary_review", ["parent_id"]
        )
    with op.batch_alter_table("governance_finding") as batch:
        batch.alter_column(
            "type", existing_type=sa.String(64), type_=sa.String(32), existing_nullable=False
        )
