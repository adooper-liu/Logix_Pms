"""login lockout, token version, and wider secret columns

Revision ID: p1a2b3c4d5e6
Revises: o9c0d1e2f3a4
Create Date: 2026-11-02 22:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "p1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "o9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))
    with op.batch_alter_table("integration_endpoint") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.String(length=128),
            type_=sa.Text(),
            existing_nullable=True,
        )
    with op.batch_alter_table("inbound_webhook") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.String(length=128),
            type_=sa.Text(),
            existing_nullable=False,
        )
    # 模型把这两列标成 unique=True, index=True。旧迁移建的是普通索引，
    # 对照时会报漂移。overlap_work 的库端默认值模型侧没有，一并去掉。
    with op.batch_alter_table("process_charter") as batch:
        batch.drop_index("ix_process_charter_process_id")
        batch.create_index("ix_process_charter_process_id", ["process_id"], unique=True)
    with op.batch_alter_table("sibling_boundary_review") as batch:
        batch.drop_index("ix_sibling_boundary_review_parent_id")
        batch.create_index("ix_sibling_boundary_review_parent_id", ["parent_id"], unique=True)
        batch.alter_column(
            "overlap_work",
            existing_type=sa.Text(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("sibling_boundary_review") as batch:
        batch.alter_column(
            "overlap_work",
            existing_type=sa.Text(),
            existing_nullable=False,
            server_default="",
        )
        batch.drop_index("ix_sibling_boundary_review_parent_id")
        batch.create_index("ix_sibling_boundary_review_parent_id", ["parent_id"], unique=False)
    with op.batch_alter_table("process_charter") as batch:
        batch.drop_index("ix_process_charter_process_id")
        batch.create_index("ix_process_charter_process_id", ["process_id"], unique=False)
    with op.batch_alter_table("inbound_webhook") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.Text(),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
    with op.batch_alter_table("integration_endpoint") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.Text(),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
    with op.batch_alter_table("app_user") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")
        batch.drop_column("token_version")
