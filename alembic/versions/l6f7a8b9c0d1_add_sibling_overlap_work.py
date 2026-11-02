"""add the repeated work named on a sibling overlap review

Revision ID: l6f7a8b9c0d1
Revises: k5e6f7a8b9c0
Create Date: 2026-11-01 13:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "l6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "k5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sibling_boundary_review",
        sa.Column("overlap_work", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("sibling_boundary_review", "overlap_work")
