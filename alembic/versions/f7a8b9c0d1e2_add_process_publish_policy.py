"""add process publish_policy

Revision ID: f7a8b9c0d1e2
Revises: e1f2a3b4c5d6
Create Date: 2026-10-31 20:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "process_arch",
        sa.Column(
            "publish_policy",
            sa.String(length=32),
            nullable=False,
            server_default="review_required",
        ),
    )


def downgrade() -> None:
    op.drop_column("process_arch", "publish_policy")
