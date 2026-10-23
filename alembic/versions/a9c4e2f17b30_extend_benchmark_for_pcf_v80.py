"""extend benchmark schema for APQC PCF v8.0

Revision ID: a9c4e2f17b30
Revises: 9c7d1e2f3a4b
Create Date: 2026-10-23 22:05:00.000000

新增内容：
- `benchmark_framework`：行业、主框架标记、基础框架、来源文件、生成日期、署名；
- `benchmark_category`：跨变体稳定键 external_id（PCF ID）、中文名 name_zh、
  指标可用标记、变更指数与变更说明；
- `benchmark_metric`：APQC 指标目录，按 (PCF ID, Metric ID) 唯一。

所有对既有表的修改都走 batch_alter_table，兼容 SQLite 测试库。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9c4e2f17b30'
down_revision: Union[str, Sequence[str], None] = '9c7d1e2f3a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'benchmark_metric',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=32), nullable=False),
        sa.Column('metric_id', sa.String(length=32), nullable=False),
        sa.Column('metric_category', sa.String(length=64), nullable=True),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.Column('unit', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'external_id', 'metric_id', name='uq_benchmark_metric_element_metric'
        ),
    )
    op.create_index(
        op.f('ix_benchmark_metric_external_id'), 'benchmark_metric', ['external_id'], unique=False
    )
    op.create_index(
        op.f('ix_benchmark_metric_metric_id'), 'benchmark_metric', ['metric_id'], unique=False
    )
    op.create_index(
        'ix_benchmark_metric_external_metric',
        'benchmark_metric',
        ['external_id', 'metric_id'],
        unique=False,
    )

    with op.batch_alter_table('benchmark_framework', schema=None) as batch_op:
        batch_op.add_column(sa.Column('industry', sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('base_framework_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source_file', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('generated_on', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('attribution', sa.Text(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_benchmark_framework_industry'), ['industry'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_benchmark_framework_base_framework_id'),
            ['base_framework_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_benchmark_framework_base',
            'benchmark_framework',
            ['base_framework_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('benchmark_category', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_id', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('name_zh', sa.String(length=160), nullable=True))
        batch_op.add_column(
            sa.Column('metrics_available', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('difference_index', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('change_details', sa.String(length=255), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_benchmark_category_external_id'), ['external_id'], unique=False
        )
        batch_op.create_unique_constraint(
            'uq_benchmark_category_framework_external', ['framework_id', 'external_id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('benchmark_category', schema=None) as batch_op:
        batch_op.drop_constraint('uq_benchmark_category_framework_external', type_='unique')
        batch_op.drop_index(batch_op.f('ix_benchmark_category_external_id'))
        batch_op.drop_column('change_details')
        batch_op.drop_column('difference_index')
        batch_op.drop_column('metrics_available')
        batch_op.drop_column('name_zh')
        batch_op.drop_column('external_id')

    with op.batch_alter_table('benchmark_framework', schema=None) as batch_op:
        batch_op.drop_constraint('fk_benchmark_framework_base', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_benchmark_framework_base_framework_id'))
        batch_op.drop_index(batch_op.f('ix_benchmark_framework_industry'))
        batch_op.drop_column('attribution')
        batch_op.drop_column('generated_on')
        batch_op.drop_column('source_file')
        batch_op.drop_column('base_framework_id')
        batch_op.drop_column('is_primary')
        batch_op.drop_column('industry')

    op.drop_index('ix_benchmark_metric_external_metric', table_name='benchmark_metric')
    op.drop_index(op.f('ix_benchmark_metric_metric_id'), table_name='benchmark_metric')
    op.drop_index(op.f('ix_benchmark_metric_external_id'), table_name='benchmark_metric')
    op.drop_table('benchmark_metric')
