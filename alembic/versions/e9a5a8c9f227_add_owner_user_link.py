"""add owner user link

Revision ID: e9a5a8c9f227
Revises: a0886771a26e
Create Date: 2026-10-21 17:44:03.077509

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9a5a8c9f227'
down_revision: Union[str, Sequence[str], None] = 'a0886771a26e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    batch_alter_table：SQLite 不支持 ALTER 加外键约束，需要整表重建；
    在 PostgreSQL 上会退化成普通 ALTER，两边共用同一份迁移。
    """
    with op.batch_alter_table('process_arch') as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f('ix_process_arch_owner_user_id'), ['owner_user_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_process_arch_owner_user_id_app_user',
            'app_user',
            ['owner_user_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('project') as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_project_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_project_owner_user_id_app_user',
            'app_user',
            ['owner_user_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # 数据回填：只把「姓名在账号表里唯一」的存量对象绑定到账号。
    # 有歧义或无对应账号的保持 NULL（fail closed，仅 MANAGER+ 可改）。
    op.execute(
        """
        UPDATE project
        SET owner_user_id = (
            SELECT u.id FROM app_user u WHERE u.display_name = project.owner LIMIT 1
        )
        WHERE owner_user_id IS NULL
          AND 1 = (
            SELECT COUNT(*) FROM app_user u WHERE u.display_name = project.owner
          )
        """
    )
    # 流程底稿里的 Owner 常见写法是「部门-姓名」，除了完全一致也匹配后缀
    op.execute(
        """
        UPDATE process_arch
        SET owner_user_id = (
            SELECT u.id FROM app_user u
            WHERE process_arch.owner = u.display_name
               OR process_arch.owner LIKE '%-' || u.display_name
            LIMIT 1
        )
        WHERE owner_user_id IS NULL
          AND 1 = (
            SELECT COUNT(*) FROM app_user u
            WHERE process_arch.owner = u.display_name
               OR process_arch.owner LIKE '%-' || u.display_name
          )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('project') as batch_op:
        batch_op.drop_constraint('fk_project_owner_user_id_app_user', type_='foreignkey')
        batch_op.drop_index(op.f('ix_project_owner_user_id'))
        batch_op.drop_column('owner_user_id')

    with op.batch_alter_table('process_arch') as batch_op:
        batch_op.drop_constraint('fk_process_arch_owner_user_id_app_user', type_='foreignkey')
        batch_op.drop_index(op.f('ix_process_arch_owner_user_id'))
        batch_op.drop_column('owner_user_id')
