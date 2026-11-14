"""enforce one current gate assessment per cycle

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_gate_current",
        "process_gate_assessment",
        ["cycle_id", "gate_key"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_gate_current", table_name="process_gate_assessment")
