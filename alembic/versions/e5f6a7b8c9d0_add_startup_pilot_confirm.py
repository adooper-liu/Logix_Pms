"""add startup pilot confirm

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-24 23:10:00.000000

新增 `startup_pilot_confirm`：首次上线的确认里程碑，记录确认人、时间、
备注与当时的证据快照。只新增一张表。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'startup_pilot_confirm',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=32), nullable=False),
        sa.Column('confirmed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('evidence_snapshot', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ['confirmed_by_user_id'],
            ['app_user.id'],
            name='fk_startup_pilot_confirm_user',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_startup_pilot_confirm_key'),
        'startup_pilot_confirm',
        ['key'],
        unique=True,
    )
    op.create_index(
        op.f('ix_startup_pilot_confirm_confirmed_by_user_id'),
        'startup_pilot_confirm',
        ['confirmed_by_user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_startup_pilot_confirm_confirmed_by_user_id'),
        table_name='startup_pilot_confirm',
    )
    op.drop_index(
        op.f('ix_startup_pilot_confirm_key'), table_name='startup_pilot_confirm'
    )
    op.drop_table('startup_pilot_confirm')
