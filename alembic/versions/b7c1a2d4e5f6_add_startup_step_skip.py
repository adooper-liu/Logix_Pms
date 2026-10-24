"""add startup step skip

Revision ID: b7c1a2d4e5f6
Revises: d910e6c8e0b2
Create Date: 2026-10-24 19:10:00.000000

新增 `startup_step_skip`：记录启动路径中“本轮不验证”的步骤。
只新增一张表，不改既有表；SQLite/PostgreSQL 均可用。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1a2d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd910e6c8e0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'startup_step_skip',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('step_key', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('skipped_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['skipped_by_user_id'],
            ['app_user.id'],
            name='fk_startup_step_skip_user',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_startup_step_skip_step_key'), 'startup_step_skip', ['step_key'], unique=True
    )
    op.create_index(
        op.f('ix_startup_step_skip_skipped_by_user_id'),
        'startup_step_skip',
        ['skipped_by_user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_startup_step_skip_skipped_by_user_id'), table_name='startup_step_skip'
    )
    op.drop_index(op.f('ix_startup_step_skip_step_key'), table_name='startup_step_skip')
    op.drop_table('startup_step_skip')
