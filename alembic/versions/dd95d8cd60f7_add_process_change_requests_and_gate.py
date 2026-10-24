"""add process change requests and gate

Revision ID: dd95d8cd60f7
Revises: d9a46136b3fe
Create Date: 2026-10-24 13:31:26.059721

新增：
- `process_change_request`：变更申请、影响分析、测试证据、回退方案与审批状态；
- `process_arch.requires_change_request`：流程级发布门禁开关；
- `process_model_version.change_request_id`：发布版本引用的变更单。

所有对既有表的修改都走 batch_alter_table，兼容 SQLite 测试库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd95d8cd60f7'
down_revision: Union[str, Sequence[str], None] = 'd9a46136b3fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'process_change_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column(
            'change_type', sa.String(length=16), server_default='STRUCTURE', nullable=False
        ),
        sa.Column(
            'impact_level', sa.String(length=16), server_default='MINOR', nullable=False
        ),
        sa.Column('version_label', sa.String(length=16), nullable=True),
        sa.Column('impact', sa.JSON(), nullable=False),
        sa.Column('test_evidence', sa.Text(), nullable=True),
        sa.Column('rollback_plan', sa.Text(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('emergency', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='DRAFT', nullable=False),
        sa.Column('decision_note', sa.String(length=200), nullable=True),
        sa.Column('requested_by_id', sa.Integer(), nullable=True),
        sa.Column('requested_by_name', sa.String(length=64), nullable=True),
        sa.Column('approved_by_id', sa.Integer(), nullable=True),
        sa.Column('approved_by_name', sa.String(length=64), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['approved_by_id'], ['app_user.id'], name='fk_change_approved_by', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['process_id'], ['process_arch.id'], name='fk_change_process', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['requested_by_id'],
            ['app_user.id'],
            name='fk_change_requested_by',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_change_process_status',
        'process_change_request',
        ['process_id', 'status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_process_change_request_change_type'),
        'process_change_request',
        ['change_type'],
        unique=False,
    )
    op.create_index(
        op.f('ix_process_change_request_code'),
        'process_change_request',
        ['code'],
        unique=True,
    )
    op.create_index(
        op.f('ix_process_change_request_created_at'),
        'process_change_request',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_process_change_request_impact_level'),
        'process_change_request',
        ['impact_level'],
        unique=False,
    )
    op.create_index(
        op.f('ix_process_change_request_process_id'),
        'process_change_request',
        ['process_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_process_change_request_status'),
        'process_change_request',
        ['status'],
        unique=False,
    )

    with op.batch_alter_table('process_arch', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'requires_change_request',
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    with op.batch_alter_table('process_model_version', schema=None) as batch_op:
        batch_op.add_column(sa.Column('change_request_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_process_model_version_change_request_id'),
            ['change_request_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_model_version_change_request',
            'process_change_request',
            ['change_request_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('process_model_version', schema=None) as batch_op:
        batch_op.drop_constraint('fk_model_version_change_request', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_process_model_version_change_request_id'))
        batch_op.drop_column('change_request_id')

    with op.batch_alter_table('process_arch', schema=None) as batch_op:
        batch_op.drop_column('requires_change_request')

    op.drop_index(
        op.f('ix_process_change_request_status'), table_name='process_change_request'
    )
    op.drop_index(
        op.f('ix_process_change_request_process_id'), table_name='process_change_request'
    )
    op.drop_index(
        op.f('ix_process_change_request_impact_level'), table_name='process_change_request'
    )
    op.drop_index(
        op.f('ix_process_change_request_created_at'), table_name='process_change_request'
    )
    op.drop_index(op.f('ix_process_change_request_code'), table_name='process_change_request')
    op.drop_index(
        op.f('ix_process_change_request_change_type'), table_name='process_change_request'
    )
    op.drop_index('ix_change_process_status', table_name='process_change_request')
    op.drop_table('process_change_request')
