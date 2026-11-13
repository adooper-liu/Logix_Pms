"""add process operating cycle authorizer

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("process_operating_cycle", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("launch_authorizer_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("launch_authorizer_scope", sa.String(length=160), nullable=True))
        batch_op.create_foreign_key(
            "fk_operating_cycle_launch_authorizer",
            "app_user",
            ["launch_authorizer_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_process_operating_cycle_launch_authorizer_user_id",
        "process_operating_cycle",
        ["launch_authorizer_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_process_operating_cycle_launch_authorizer_user_id",
        table_name="process_operating_cycle",
    )
    with op.batch_alter_table("process_operating_cycle", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_operating_cycle_launch_authorizer", type_="foreignkey")
        batch_op.drop_column("launch_authorizer_scope")
        batch_op.drop_column("launch_authorizer_user_id")
