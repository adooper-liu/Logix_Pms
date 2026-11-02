"""online template fill fields

Revision ID: o9c0d1e2f3a4
Revises: n8b9c0d1e2f3
Create Date: 2026-11-01 21:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "o9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "n8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tool_template_version", sa.Column("sheet_fields", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tool_template_version", "sheet_fields")
