"""kpi intake source and confirmed exception origin

Revision ID: m7a8b9c0d1e2
Revises: l6f7a8b9c0d1
Create Date: 2026-11-01 16:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "m7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "l6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 不能直接 ALTER 加外键，必须走 batch 重建表。
    with op.batch_alter_table("kpi_definition") as batch_op:
        batch_op.add_column(sa.Column("data_flow_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("inbound_webhook_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_kpi_definition_data_flow_id", ["data_flow_id"])
        batch_op.create_index("ix_kpi_definition_inbound_webhook_id", ["inbound_webhook_id"])
        batch_op.create_foreign_key(
            "fk_kpi_definition_data_flow",
            "data_flow",
            ["data_flow_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_kpi_definition_inbound_webhook",
            "inbound_webhook",
            ["inbound_webhook_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("exception_event") as batch_op:
        batch_op.add_column(sa.Column("source_kpi_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_instance_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_exception_event_source_kpi_id", ["source_kpi_id"])
        batch_op.create_index("ix_exception_event_source_instance_id", ["source_instance_id"])
        batch_op.create_foreign_key(
            "fk_exception_event_source_kpi",
            "kpi_definition",
            ["source_kpi_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_exception_event_source_instance",
            "process_instance",
            ["source_instance_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("exception_event") as batch_op:
        batch_op.drop_constraint("fk_exception_event_source_instance", type_="foreignkey")
        batch_op.drop_constraint("fk_exception_event_source_kpi", type_="foreignkey")
        batch_op.drop_index("ix_exception_event_source_instance_id")
        batch_op.drop_index("ix_exception_event_source_kpi_id")
        batch_op.drop_column("source_instance_id")
        batch_op.drop_column("source_kpi_id")
    with op.batch_alter_table("kpi_definition") as batch_op:
        batch_op.drop_constraint("fk_kpi_definition_inbound_webhook", type_="foreignkey")
        batch_op.drop_constraint("fk_kpi_definition_data_flow", type_="foreignkey")
        batch_op.drop_index("ix_kpi_definition_inbound_webhook_id")
        batch_op.drop_index("ix_kpi_definition_data_flow_id")
        batch_op.drop_column("inbound_webhook_id")
        batch_op.drop_column("data_flow_id")
