"""add exception owner user link

Revision ID: 2632bb97029f
Revises: 77035a97a97b
Create Date: 2026-10-21 18:20:41.426690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2632bb97029f'
down_revision: Union[str, Sequence[str], None] = '77035a97a97b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    异常事件与项目/流程模型使用同一套归属规则：owner_user_id 是权限依据，
    owner 只是展示标签。batch_alter_table 兼容 SQLite 加外键。
    """
    with op.batch_alter_table('exception_event') as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f('ix_exception_event_owner_user_id'), ['owner_user_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_exception_event_owner_user_id_app_user',
            'app_user',
            ['owner_user_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # 存量回填：姓名唯一（或「部门-姓名」后缀唯一）才绑定，其余保持 NULL
    op.execute(
        """
        UPDATE exception_event
        SET owner_user_id = (
            SELECT u.id FROM app_user u
            WHERE exception_event.owner = u.display_name
               OR exception_event.owner LIKE '%-' || u.display_name
            LIMIT 1
        )
        WHERE owner_user_id IS NULL
          AND 1 = (
            SELECT COUNT(*) FROM app_user u
            WHERE exception_event.owner = u.display_name
               OR exception_event.owner LIKE '%-' || u.display_name
          )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exception_event') as batch_op:
        batch_op.drop_constraint(
            'fk_exception_event_owner_user_id_app_user', type_='foreignkey'
        )
        batch_op.drop_index(op.f('ix_exception_event_owner_user_id'))
        batch_op.drop_column('owner_user_id')
