"""add work measurement observations

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-24 22:20:00.000000

新增：
- `work_measurement_observation`：现场观测记录，均值与样本量由记录回算；
- 标准工时卡增加评审人、评审时间与评审意见。

只新增表和字段，不改既有列；SQLite/PostgreSQL 均可用。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('work_measurement_standard', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reviewed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('review_note', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_wms_reviewed_by',
            'app_user',
            ['reviewed_by_id'],
            ['id'],
            ondelete='SET NULL',
        )

    op.create_table(
        'work_measurement_observation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('standard_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('observed_minutes', sa.Float(), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('observer_user_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['standard_id'],
            ['work_measurement_standard.id'],
            name='fk_wms_observation_standard',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['observer_user_id'],
            ['app_user.id'],
            name='fk_wms_observation_observer',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'standard_id', 'sequence', name='uq_wms_observation_sequence'
        ),
    )
    op.create_index(
        op.f('ix_work_measurement_observation_standard_id'),
        'work_measurement_observation',
        ['standard_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_work_measurement_observation_standard_id'),
        table_name='work_measurement_observation',
    )
    op.drop_table('work_measurement_observation')

    with op.batch_alter_table('work_measurement_standard', schema=None) as batch_op:
        batch_op.drop_constraint('fk_wms_reviewed_by', type_='foreignkey')
        batch_op.drop_column('review_note')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by_id')
