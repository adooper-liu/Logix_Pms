"""add improvement project card

Revision ID: 98e8e5c8d921
Revises: dd95d8cd60f7
Create Date: 2026-10-24 13:47:58.290757

新增改善项目卡字段：
- 来源与来源 KPI（KPI 越线自动立项）；
- 问题、根因、对策、验证、收益；
- 观察期、一次性投入、转移成本；
- 复制状态与说明。

所有修改都走 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98e8e5c8d921'
down_revision: Union[str, Sequence[str], None] = 'dd95d8cd60f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(length=24), server_default='MANUAL', nullable=False)
        )
        batch_op.add_column(sa.Column('source_kpi_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('problem_statement', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('root_cause', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('countermeasure', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('verification', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('benefit', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('observation_until', sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column('one_time_cost', sa.Float(), server_default='0', nullable=False)
        )
        batch_op.add_column(
            sa.Column('transfer_cost', sa.Float(), server_default='0', nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                'replication_status',
                sa.String(length=20),
                server_default='NOT_EVALUATED',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('replication_note', sa.String(length=200), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_project_replication_status'), ['replication_status'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_project_source'), ['source'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_project_source_kpi_id'), ['source_kpi_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_project_source_kpi',
            'kpi_definition',
            ['source_kpi_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_source_kpi', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_project_source_kpi_id'))
        batch_op.drop_index(batch_op.f('ix_project_source'))
        batch_op.drop_index(batch_op.f('ix_project_replication_status'))
        batch_op.drop_column('replication_note')
        batch_op.drop_column('replication_status')
        batch_op.drop_column('transfer_cost')
        batch_op.drop_column('one_time_cost')
        batch_op.drop_column('observation_until')
        batch_op.drop_column('benefit')
        batch_op.drop_column('verification')
        batch_op.drop_column('countermeasure')
        batch_op.drop_column('root_cause')
        batch_op.drop_column('problem_statement')
        batch_op.drop_column('source_kpi_id')
        batch_op.drop_column('source')
