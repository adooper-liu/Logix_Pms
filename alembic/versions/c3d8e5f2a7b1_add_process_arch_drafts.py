"""add process architecture draft provenance

Revision ID: c3d8e5f2a7b1
Revises: a9c4e2f17b30
Create Date: 2026-10-23 23:10:00.000000

从 APQC PCF 分类树生成的企业流程架构需要两个能力：
- 标记「草稿」，确认后才转成正式流程；
- 记录来源 PCF ID，重复生成时按来源匹配、不重复创建。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d8e5f2a7b1'
down_revision: Union[str, Sequence[str], None] = 'a9c4e2f17b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('process_arch', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_draft', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('source_framework_code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('source_external_id', sa.String(length=32), nullable=True))
        batch_op.create_index(
            'ix_process_arch_source',
            ['source_framework_code', 'source_external_id'],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('process_arch', schema=None) as batch_op:
        batch_op.drop_index('ix_process_arch_source')
        batch_op.drop_column('source_external_id')
        batch_op.drop_column('source_framework_code')
        batch_op.drop_column('is_draft')
