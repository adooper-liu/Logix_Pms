"""add workload standards and capacity

Revision ID: df082b8d9358
Revises: c65dd55aaff2
Create Date: 2026-10-24 12:46:16.232686

新增内容：
- `work_measurement_standard`：标准工时卡（活动 × 岗位 × 方法 × 样本 × 宽放）；
- `capacity_calendar`：组织 × 岗位 × 期间的可用产能；
- `process_task.activity_id`：任务创建时冻结 L4 活动，用于实际工时归集。

所有对既有表的修改都走 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df082b8d9358'
down_revision: Union[str, Sequence[str], None] = 'c65dd55aaff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'capacity_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_unit_id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('headcount', sa.Float(), nullable=False),
        sa.Column('available_hours_per_person', sa.Float(), nullable=False),
        sa.Column('attendance_rate', sa.Float(), nullable=False),
        sa.Column('equipment_availability', sa.Float(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['org_unit_id'], ['org_unit.id'], name='fk_capacity_org_unit', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['position_id'], ['position.id'], name='fk_capacity_position', ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'org_unit_id', 'position_id', 'period', name='uq_capacity_org_position_period'
        ),
    )
    op.create_index(
        op.f('ix_capacity_calendar_org_unit_id'), 'capacity_calendar', ['org_unit_id'], unique=False
    )
    op.create_index(
        op.f('ix_capacity_calendar_period'), 'capacity_calendar', ['period'], unique=False
    )
    op.create_index(
        op.f('ix_capacity_calendar_position_id'),
        'capacity_calendar',
        ['position_id'],
        unique=False,
    )

    op.create_table(
        'work_measurement_standard',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=48), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('org_unit_id', sa.Integer(), nullable=True),
        sa.Column('method_description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=20), server_default='TIME_STUDY', nullable=False),
        sa.Column('observed_minutes', sa.Float(), nullable=False),
        sa.Column('rating_factor', sa.Float(), nullable=False),
        sa.Column('allowance_rate', sa.Float(), nullable=False),
        sa.Column('standard_minutes', sa.Float(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('monthly_frequency', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='DRAFT', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('verified_by_id', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['activity_id'], ['process_arch.id'], name='fk_wms_activity', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['app_user.id'], name='fk_wms_created_by', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['org_unit_id'], ['org_unit.id'], name='fk_wms_org_unit', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['position_id'], ['position.id'], name='fk_wms_position', ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['verified_by_id'], ['app_user.id'], name='fk_wms_verified_by', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_wms_activity_position',
        'work_measurement_standard',
        ['activity_id', 'position_id'],
        unique=False,
    )
    op.create_index(
        'ix_wms_position_status',
        'work_measurement_standard',
        ['position_id', 'status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_activity_id'),
        'work_measurement_standard',
        ['activity_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_code'),
        'work_measurement_standard',
        ['code'],
        unique=True,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_created_at'),
        'work_measurement_standard',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_org_unit_id'),
        'work_measurement_standard',
        ['org_unit_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_position_id'),
        'work_measurement_standard',
        ['position_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_source'),
        'work_measurement_standard',
        ['source'],
        unique=False,
    )
    op.create_index(
        op.f('ix_work_measurement_standard_status'),
        'work_measurement_standard',
        ['status'],
        unique=False,
    )

    with op.batch_alter_table('process_task', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activity_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_process_task_activity_id'), ['activity_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_process_task_activity',
            'process_arch',
            ['activity_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('process_task', schema=None) as batch_op:
        batch_op.drop_constraint('fk_process_task_activity', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_process_task_activity_id'))
        batch_op.drop_column('activity_id')

    op.drop_index(
        op.f('ix_work_measurement_standard_status'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_source'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_position_id'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_org_unit_id'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_created_at'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_code'), table_name='work_measurement_standard'
    )
    op.drop_index(
        op.f('ix_work_measurement_standard_activity_id'), table_name='work_measurement_standard'
    )
    op.drop_index('ix_wms_position_status', table_name='work_measurement_standard')
    op.drop_index('ix_wms_activity_position', table_name='work_measurement_standard')
    op.drop_table('work_measurement_standard')

    op.drop_index(
        op.f('ix_capacity_calendar_position_id'), table_name='capacity_calendar'
    )
    op.drop_index(op.f('ix_capacity_calendar_period'), table_name='capacity_calendar')
    op.drop_index(
        op.f('ix_capacity_calendar_org_unit_id'), table_name='capacity_calendar'
    )
    op.drop_table('capacity_calendar')
