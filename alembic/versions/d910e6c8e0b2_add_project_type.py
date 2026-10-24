"""add project type

Revision ID: d910e6c8e0b2
Revises: 4d2fcd650024
Create Date: 2026-10-24 16:44:43.997090

区分两类项目：
- IMPROVEMENT：24 步流程改善项目（默认）；
- GOVERNANCE_SETUP：9 阶段治理体系落地项目。

使用 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd910e6c8e0b2'
down_revision: Union[str, Sequence[str], None] = '4d2fcd650024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'project_type',
                sa.String(length=24),
                server_default='IMPROVEMENT',
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f('ix_project_project_type'), ['project_type'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_project_type'))
        batch_op.drop_column('project_type')
