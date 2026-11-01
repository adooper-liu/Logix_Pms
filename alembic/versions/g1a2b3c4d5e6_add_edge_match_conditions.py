"""add process_edge.match_conditions for design-time routing

Revision ID: g1a2b3c4d5e6
Revises: f7a8b9c0d1e2
Create Date: 2026-11-01 07:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "process_edge",
        sa.Column("match_conditions", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("process_edge", "match_conditions")
