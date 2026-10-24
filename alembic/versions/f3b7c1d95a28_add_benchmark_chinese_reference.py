"""add Chinese reference translations for APQC PCF

Revision ID: f3b7c1d95a28
Revises: c3d8e5f2a7b1
Create Date: 2026-10-24 08:20:00.000000

新增内容：
- `benchmark_category.description_zh`：官方定义的中文参考译文；
- `benchmark_metric.name_zh` / `formula_zh` / `unit_zh` / `category_label_zh`：
  指标名称、口径、单位、分类的中文参考译文。

设计约束：
- 官方英文原文一律保留在原字段，译文另存，不覆盖；
- 译文为自建参考译文，**非 APQC 官方**，界面必须标注来源；
- 所有对既有表的修改都走 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b7c1d95a28'
down_revision: Union[str, Sequence[str], None] = 'c3d8e5f2a7b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('benchmark_category', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description_zh', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('name_zh_source', sa.String(length=32), nullable=True))

    with op.batch_alter_table('benchmark_metric', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_zh', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('formula_zh', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('unit_zh', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('category_label_zh', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('translation_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('benchmark_metric', schema=None) as batch_op:
        batch_op.drop_column('translation_source')
        batch_op.drop_column('category_label_zh')
        batch_op.drop_column('unit_zh')
        batch_op.drop_column('formula_zh')
        batch_op.drop_column('name_zh')

    with op.batch_alter_table('benchmark_category', schema=None) as batch_op:
        batch_op.drop_column('name_zh_source')
        batch_op.drop_column('description_zh')
