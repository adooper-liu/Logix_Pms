"""add authorization matrix

Revision ID: c3d4e5f6a7b8
Revises: b7c1a2d4e5f6
Create Date: 2026-10-24 21:30:00.000000

新增：
- `authorization_rule`：A/B/C/D 分级授权规则；
- `authorization_exception`：例外申请与审批记录。

只新增表，不改既有表；SQLite/PostgreSQL 均可用。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c1a2d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'authorization_rule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=48), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('matter', sa.String(length=160), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('org_unit_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=4), nullable=False),
        sa.Column('risk_level', sa.String(length=16), server_default='MEDIUM', nullable=False),
        sa.Column('amount_limit', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('impact_scope', sa.String(length=160), nullable=True),
        sa.Column('reversibility', sa.String(length=160), nullable=True),
        sa.Column('frequency', sa.String(length=160), nullable=True),
        sa.Column('approver_role_id', sa.Integer(), nullable=True),
        sa.Column('approver_label', sa.String(length=120), nullable=True),
        sa.Column('exception_path', sa.Text(), nullable=True),
        sa.Column('evidence_required', sa.Text(), nullable=True),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='DRAFT', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['process_id'], ['process_arch.id'], name='fk_auth_rule_process', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['org_unit_id'], ['org_unit.id'], name='fk_auth_rule_org', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['approver_role_id'],
            ['governance_role.id'],
            name='fk_auth_rule_role',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['document_id'],
            ['process_document.id'],
            name='fk_auth_rule_document',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['owner_user_id'], ['app_user.id'], name='fk_auth_rule_owner', ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_authorization_rule_code'), 'authorization_rule', ['code'], unique=True)
    op.create_index(
        op.f('ix_authorization_rule_matter'), 'authorization_rule', ['matter'], unique=False
    )
    op.create_index(
        op.f('ix_authorization_rule_process_id'),
        'authorization_rule',
        ['process_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_rule_org_unit_id'),
        'authorization_rule',
        ['org_unit_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_rule_category'),
        'authorization_rule',
        ['category'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_rule_approver_role_id'),
        'authorization_rule',
        ['approver_role_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_rule_document_id'),
        'authorization_rule',
        ['document_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_rule_status'), 'authorization_rule', ['status'], unique=False
    )
    op.create_index(
        op.f('ix_authorization_rule_owner_user_id'),
        'authorization_rule',
        ['owner_user_id'],
        unique=False,
    )
    op.create_index(
        'ix_authorization_rule_status_category',
        'authorization_rule',
        ['status', 'category'],
        unique=False,
    )

    op.create_table(
        'authorization_exception',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=48), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='REQUESTED', nullable=False),
        sa.Column('requested_by_id', sa.Integer(), nullable=True),
        sa.Column('requested_by_name', sa.String(length=64), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('decided_by_id', sa.Integer(), nullable=True),
        sa.Column('decided_by_name', sa.String(length=64), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_note', sa.String(length=400), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['rule_id'],
            ['authorization_rule.id'],
            name='fk_auth_exception_rule',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['process_id'],
            ['process_arch.id'],
            name='fk_auth_exception_process',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['requested_by_id'],
            ['app_user.id'],
            name='fk_auth_exception_requested_by',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['decided_by_id'],
            ['app_user.id'],
            name='fk_auth_exception_decided_by',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_authorization_exception_code'),
        'authorization_exception',
        ['code'],
        unique=True,
    )
    op.create_index(
        op.f('ix_authorization_exception_rule_id'),
        'authorization_exception',
        ['rule_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_exception_process_id'),
        'authorization_exception',
        ['process_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_authorization_exception_status'),
        'authorization_exception',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_authorization_exception_status'), table_name='authorization_exception'
    )
    op.drop_index(
        op.f('ix_authorization_exception_process_id'), table_name='authorization_exception'
    )
    op.drop_index(
        op.f('ix_authorization_exception_rule_id'), table_name='authorization_exception'
    )
    op.drop_index(op.f('ix_authorization_exception_code'), table_name='authorization_exception')
    op.drop_table('authorization_exception')

    op.drop_index(
        'ix_authorization_rule_status_category', table_name='authorization_rule'
    )
    op.drop_index(
        op.f('ix_authorization_rule_owner_user_id'), table_name='authorization_rule'
    )
    op.drop_index(op.f('ix_authorization_rule_status'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_document_id'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_approver_role_id'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_category'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_org_unit_id'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_process_id'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_matter'), table_name='authorization_rule')
    op.drop_index(op.f('ix_authorization_rule_code'), table_name='authorization_rule')
    op.drop_table('authorization_rule')
