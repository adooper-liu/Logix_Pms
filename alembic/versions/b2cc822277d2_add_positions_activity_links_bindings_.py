"""add positions activity links bindings and worklogs

Revision ID: b2cc822277d2
Revises: 26de8bfc2983
Create Date: 2026-10-23 20:34:20.789460

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2cc822277d2'
down_revision: Union[str, Sequence[str], None] = '26de8bfc2983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    """Upgrade schema.

    SQLite 不支持 ALTER 加外键，所有对既有表的修改都走 batch_alter_table；
    PostgreSQL 上会退化成普通 ALTER。
    """
    op.create_table(
        'position',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('org_unit_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['org_unit_id'], ['org_unit.id'], name='fk_position_org_unit', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_position_code'), 'position', ['code'], unique=True)
    op.create_index(op.f('ix_position_name'), 'position', ['name'], unique=False)
    op.create_index('ix_position_org_name', 'position', ['org_unit_id', 'name'], unique=False)
    op.create_index(op.f('ix_position_org_unit_id'), 'position', ['org_unit_id'], unique=False)

    op.create_table(
        'node_tool',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=False),
        sa.Column('node_key', sa.String(length=64), nullable=False),
        sa.Column('tool_code', sa.String(length=32), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['process_id'], ['process_arch.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tool_code'], ['tool.code'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_node_tool_process_id'), 'node_tool', ['process_id'], unique=False)
    op.create_index(
        'ix_node_tool_process_node', 'node_tool', ['process_id', 'node_key'], unique=False
    )
    op.create_index(op.f('ix_node_tool_tool_code'), 'node_tool', ['tool_code'], unique=False)
    op.create_index(
        'uq_node_tool_binding', 'node_tool', ['process_id', 'node_key', 'tool_code'], unique=True
    )

    op.create_table(
        'task_worklog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_name', sa.String(length=64), nullable=True),
        sa.Column('work_type', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('effort_minutes', sa.Float(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['process_task.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_worklog_created_at'), 'task_worklog', ['created_at'], unique=False)
    op.create_index(
        'ix_task_worklog_task_created', 'task_worklog', ['task_id', 'created_at'], unique=False
    )
    op.create_index(op.f('ix_task_worklog_task_id'), 'task_worklog', ['task_id'], unique=False)
    op.create_index(
        'ix_task_worklog_user_created', 'task_worklog', ['user_id', 'created_at'], unique=False
    )
    op.create_index(op.f('ix_task_worklog_user_id'), 'task_worklog', ['user_id'], unique=False)

    with op.batch_alter_table('app_user') as batch_op:
        batch_op.add_column(sa.Column('position_id', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_app_user_position_id'), ['position_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_app_user_position', 'position', ['position_id'], ['id'], ondelete='SET NULL'
        )

    with op.batch_alter_table('process_arch') as batch_op:
        batch_op.add_column(sa.Column('org_unit_id', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_process_arch_org_unit_id'), ['org_unit_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_process_arch_org_unit', 'org_unit', ['org_unit_id'], ['id'], ondelete='SET NULL'
        )

    with op.batch_alter_table('process_node') as batch_op:
        batch_op.add_column(sa.Column('process_arch_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('owner_position_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f('ix_process_node_process_arch_id'), ['process_arch_id'], unique=False
        )
        batch_op.create_index(
            op.f('ix_process_node_owner_position_id'), ['owner_position_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_process_node_activity',
            'process_arch',
            ['process_arch_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_process_node_position',
            'position',
            ['owner_position_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('process_document') as batch_op:
        batch_op.add_column(sa.Column('node_key', sa.String(length=64), nullable=True))
        batch_op.create_index(op.f('ix_process_document_node_key'), ['node_key'], unique=False)
        batch_op.create_index(
            'ix_process_document_process_node', ['process_id', 'node_key'], unique=False
        )

    with op.batch_alter_table('process_task') as batch_op:
        batch_op.add_column(
            sa.Column('actual_minutes', sa.Float(), server_default='0', nullable=False)
        )

    # ---- 数据回填：只做安全的唯一名称匹配，歧义保持 NULL ----
    bind = op.get_bind()
    now = _now()
    owners = bind.execute(
        sa.text(
            "SELECT DISTINCT owner_role FROM process_node "
            "WHERE owner_role IS NOT NULL AND TRIM(owner_role) <> '' ORDER BY owner_role"
        )
    ).fetchall()
    for index, (name,) in enumerate(owners, start=1):
        bind.execute(
            sa.text(
                "INSERT INTO position (code, name, is_active, created_at, updated_at) "
                "VALUES (:code, :name, :active, :created_at, :updated_at)"
            ),
            {
                "code": f"POS-{index:03d}",
                "name": name,
                "active": True,
                "created_at": now,
                "updated_at": now,
            },
        )

    bind.execute(
        sa.text(
            "UPDATE process_node SET owner_position_id = ("
            "  SELECT p.id FROM position p WHERE p.name = process_node.owner_role LIMIT 1"
            ") WHERE owner_position_id IS NULL "
            "AND owner_role IS NOT NULL AND TRIM(owner_role) <> ''"
        )
    )

    bind.execute(
        sa.text(
            "UPDATE process_arch SET org_unit_id = ("
            "  SELECT o.id FROM org_unit o WHERE o.name = process_arch.department LIMIT 1"
            ") WHERE org_unit_id IS NULL AND department IS NOT NULL "
            "AND 1 = (SELECT COUNT(*) FROM org_unit o WHERE o.name = process_arch.department)"
        )
    )

    bind.execute(
        sa.text(
            "UPDATE process_node SET process_arch_id = ("
            "  SELECT pa.id FROM process_arch pa "
            "  WHERE pa.parent_id = process_node.process_id "
            "    AND pa.level = 4 AND pa.name = process_node.name LIMIT 1"
            ") WHERE process_arch_id IS NULL "
            "AND 1 = (SELECT COUNT(*) FROM process_arch pa "
            "         WHERE pa.parent_id = process_node.process_id "
            "           AND pa.level = 4 AND pa.name = process_node.name)"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('process_task') as batch_op:
        batch_op.drop_column('actual_minutes')

    with op.batch_alter_table('process_document') as batch_op:
        batch_op.drop_index('ix_process_document_process_node')
        batch_op.drop_index(op.f('ix_process_document_node_key'))
        batch_op.drop_column('node_key')

    with op.batch_alter_table('process_node') as batch_op:
        batch_op.drop_constraint('fk_process_node_position', type_='foreignkey')
        batch_op.drop_constraint('fk_process_node_activity', type_='foreignkey')
        batch_op.drop_index(op.f('ix_process_node_owner_position_id'))
        batch_op.drop_index(op.f('ix_process_node_process_arch_id'))
        batch_op.drop_column('owner_position_id')
        batch_op.drop_column('process_arch_id')

    with op.batch_alter_table('process_arch') as batch_op:
        batch_op.drop_constraint('fk_process_arch_org_unit', type_='foreignkey')
        batch_op.drop_index(op.f('ix_process_arch_org_unit_id'))
        batch_op.drop_column('org_unit_id')

    with op.batch_alter_table('app_user') as batch_op:
        batch_op.drop_constraint('fk_app_user_position', type_='foreignkey')
        batch_op.drop_index(op.f('ix_app_user_position_id'))
        batch_op.drop_column('position_id')

    op.drop_index(op.f('ix_task_worklog_user_id'), table_name='task_worklog')
    op.drop_index('ix_task_worklog_user_created', table_name='task_worklog')
    op.drop_index(op.f('ix_task_worklog_task_id'), table_name='task_worklog')
    op.drop_index('ix_task_worklog_task_created', table_name='task_worklog')
    op.drop_index(op.f('ix_task_worklog_created_at'), table_name='task_worklog')
    op.drop_table('task_worklog')

    op.drop_index('uq_node_tool_binding', table_name='node_tool')
    op.drop_index(op.f('ix_node_tool_tool_code'), table_name='node_tool')
    op.drop_index('ix_node_tool_process_node', table_name='node_tool')
    op.drop_index(op.f('ix_node_tool_process_id'), table_name='node_tool')
    op.drop_table('node_tool')

    op.drop_index(op.f('ix_position_org_unit_id'), table_name='position')
    op.drop_index('ix_position_org_name', table_name='position')
    op.drop_index(op.f('ix_position_name'), table_name='position')
    op.drop_index(op.f('ix_position_code'), table_name='position')
    op.drop_table('position')
