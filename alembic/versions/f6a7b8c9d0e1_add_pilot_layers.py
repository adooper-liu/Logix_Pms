"""add pilot layers

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-24 23:30:00.000000

新增十层单页所需的数据：
- `pilot_path`：一条流程试点路径；
- `pilot_layer`：10 层的备注与上下文摘要；
- `pilot_task`：层内待办；
- `pilot_issue`：层内异常/改善卡。

只新增表，不改既有表；SQLite/PostgreSQL 均可用。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pilot_path',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('owner', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
        sa.Column('current_layer', sa.Integer(), server_default='1', nullable=False),
        sa.Column('baseline_version', sa.String(length=16), server_default='V0.1', nullable=False),
        sa.Column('draft_version', sa.String(length=16), server_default='V0.1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['process_id'], ['process_arch.id'], name='fk_pilot_path_process', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['owner_user_id'], ['app_user.id'], name='fk_pilot_path_owner', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pilot_path_process_id'), 'pilot_path', ['process_id'], unique=False)
    op.create_index(
        op.f('ix_pilot_path_owner_user_id'), 'pilot_path', ['owner_user_id'], unique=False
    )
    op.create_index(op.f('ix_pilot_path_status'), 'pilot_path', ['status'], unique=False)

    op.create_table(
        'pilot_layer',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path_id', sa.Integer(), nullable=False),
        sa.Column('layer_no', sa.Integer(), nullable=False),
        sa.Column('context_summary', sa.String(length=400), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['path_id'], ['pilot_path.id'], name='fk_pilot_layer_path', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('path_id', 'layer_no', name='uq_pilot_layer_path_no'),
    )
    op.create_index(op.f('ix_pilot_layer_path_id'), 'pilot_layer', ['path_id'], unique=False)
    op.create_index(op.f('ix_pilot_layer_layer_no'), 'pilot_layer', ['layer_no'], unique=False)

    op.create_table(
        'pilot_task',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path_id', sa.Integer(), nullable=False),
        sa.Column('layer_no', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('priority', sa.String(length=16), server_default='MEDIUM', nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('owner', sa.String(length=64), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('acceptance', sa.String(length=400), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='TODO', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['path_id'], ['pilot_path.id'], name='fk_pilot_task_path', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['owner_user_id'], ['app_user.id'], name='fk_pilot_task_owner', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pilot_task_path_id'), 'pilot_task', ['path_id'], unique=False)
    op.create_index(op.f('ix_pilot_task_layer_no'), 'pilot_task', ['layer_no'], unique=False)
    op.create_index(op.f('ix_pilot_task_priority'), 'pilot_task', ['priority'], unique=False)
    op.create_index(op.f('ix_pilot_task_status'), 'pilot_task', ['status'], unique=False)

    op.create_table(
        'pilot_issue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path_id', sa.Integer(), nullable=False),
        sa.Column('layer_no', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('severity', sa.String(length=16), server_default='MAJOR', nullable=False),
        sa.Column('workaround', sa.Text(), nullable=True),
        sa.Column('verification', sa.Text(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('owner', sa.String(length=64), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='OPEN', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['path_id'], ['pilot_path.id'], name='fk_pilot_issue_path', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['owner_user_id'], ['app_user.id'], name='fk_pilot_issue_owner', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pilot_issue_path_id'), 'pilot_issue', ['path_id'], unique=False)
    op.create_index(op.f('ix_pilot_issue_layer_no'), 'pilot_issue', ['layer_no'], unique=False)
    op.create_index(op.f('ix_pilot_issue_severity'), 'pilot_issue', ['severity'], unique=False)
    op.create_index(op.f('ix_pilot_issue_status'), 'pilot_issue', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pilot_issue_status'), table_name='pilot_issue')
    op.drop_index(op.f('ix_pilot_issue_severity'), table_name='pilot_issue')
    op.drop_index(op.f('ix_pilot_issue_layer_no'), table_name='pilot_issue')
    op.drop_index(op.f('ix_pilot_issue_path_id'), table_name='pilot_issue')
    op.drop_table('pilot_issue')

    op.drop_index(op.f('ix_pilot_task_status'), table_name='pilot_task')
    op.drop_index(op.f('ix_pilot_task_priority'), table_name='pilot_task')
    op.drop_index(op.f('ix_pilot_task_layer_no'), table_name='pilot_task')
    op.drop_index(op.f('ix_pilot_task_path_id'), table_name='pilot_task')
    op.drop_table('pilot_task')

    op.drop_index(op.f('ix_pilot_layer_layer_no'), table_name='pilot_layer')
    op.drop_index(op.f('ix_pilot_layer_path_id'), table_name='pilot_layer')
    op.drop_table('pilot_layer')

    op.drop_index(op.f('ix_pilot_path_status'), table_name='pilot_path')
    op.drop_index(op.f('ix_pilot_path_owner_user_id'), table_name='pilot_path')
    op.drop_index(op.f('ix_pilot_path_process_id'), table_name='pilot_path')
    op.drop_table('pilot_path')
