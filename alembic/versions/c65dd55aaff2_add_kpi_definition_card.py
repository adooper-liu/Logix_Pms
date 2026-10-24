"""add kpi definition card

Revision ID: c65dd55aaff2
Revises: f3b7c1d95a28
Create Date: 2026-10-24 12:24:19.430217

KPI 定义卡：
- 三类（结果/过程/健康度）与频率、粒度、数据来源、质量规则；
- 公式与分子分母、红/黄/绿阈值、责任人外键、L4 活动绑定；
- 定义版本与生效/失效日期。

所有对既有表的修改都走 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c65dd55aaff2'
down_revision: Union[str, Sequence[str], None] = 'f3b7c1d95a28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('kpi_definition', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('kind', sa.String(length=16), server_default='PROCESS', nullable=False)
        )
        batch_op.add_column(sa.Column('formula', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('numerator', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('denominator', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('granularity', sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column('frequency', sa.String(length=16), server_default='MONTHLY', nullable=False)
        )
        batch_op.add_column(sa.Column('source_system', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('quality_rule', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('red_threshold', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('yellow_threshold', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('green_threshold', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('activity_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('version', sa.Integer(), server_default='1', nullable=False)
        )
        batch_op.add_column(sa.Column('valid_from', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('valid_to', sa.Date(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_kpi_definition_kind'), ['kind'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_kpi_definition_frequency'), ['frequency'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_kpi_definition_activity_id'), ['activity_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_kpi_definition_owner_user_id'), ['owner_user_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_kpi_activity',
            'process_arch',
            ['activity_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_kpi_owner_user',
            'app_user',
            ['owner_user_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('kpi_definition', schema=None) as batch_op:
        batch_op.drop_constraint('fk_kpi_owner_user', type_='foreignkey')
        batch_op.drop_constraint('fk_kpi_activity', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_kpi_definition_owner_user_id'))
        batch_op.drop_index(batch_op.f('ix_kpi_definition_activity_id'))
        batch_op.drop_index(batch_op.f('ix_kpi_definition_frequency'))
        batch_op.drop_index(batch_op.f('ix_kpi_definition_kind'))
        batch_op.drop_column('valid_to')
        batch_op.drop_column('valid_from')
        batch_op.drop_column('version')
        batch_op.drop_column('owner_user_id')
        batch_op.drop_column('activity_id')
        batch_op.drop_column('green_threshold')
        batch_op.drop_column('yellow_threshold')
        batch_op.drop_column('red_threshold')
        batch_op.drop_column('quality_rule')
        batch_op.drop_column('source_system')
        batch_op.drop_column('frequency')
        batch_op.drop_column('granularity')
        batch_op.drop_column('denominator')
        batch_op.drop_column('numerator')
        batch_op.drop_column('formula')
        batch_op.drop_column('kind')
