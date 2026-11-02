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
    op.add_column("kpi_definition", sa.Column("data_flow_id", sa.Integer(), nullable=True))
    op.add_column("kpi_definition", sa.Column("inbound_webhook_id", sa.Integer(), nullable=True))
    op.create_index("ix_kpi_definition_data_flow_id", "kpi_definition", ["data_flow_id"])
    op.create_index(
        "ix_kpi_definition_inbound_webhook_id", "kpi_definition", ["inbound_webhook_id"]
    )
    op.create_foreign_key(
        "fk_kpi_definition_data_flow",
        "kpi_definition",
        "data_flow",
        ["data_flow_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_kpi_definition_inbound_webhook",
        "kpi_definition",
        "inbound_webhook",
        ["inbound_webhook_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("exception_event", sa.Column("source_kpi_id", sa.Integer(), nullable=True))
    op.add_column("exception_event", sa.Column("source_instance_id", sa.Integer(), nullable=True))
    op.create_index("ix_exception_event_source_kpi_id", "exception_event", ["source_kpi_id"])
    op.create_index(
        "ix_exception_event_source_instance_id", "exception_event", ["source_instance_id"]
    )
    op.create_foreign_key(
        "fk_exception_event_source_kpi",
        "exception_event",
        "kpi_definition",
        ["source_kpi_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_exception_event_source_instance",
        "exception_event",
        "process_instance",
        ["source_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_exception_event_source_instance", "exception_event", type_="foreignkey"
    )
    op.drop_constraint("fk_exception_event_source_kpi", "exception_event", type_="foreignkey")
    op.drop_index("ix_exception_event_source_instance_id", table_name="exception_event")
    op.drop_index("ix_exception_event_source_kpi_id", table_name="exception_event")
    op.drop_column("exception_event", "source_instance_id")
    op.drop_column("exception_event", "source_kpi_id")
    op.drop_constraint("fk_kpi_definition_inbound_webhook", "kpi_definition", type_="foreignkey")
    op.drop_constraint("fk_kpi_definition_data_flow", "kpi_definition", type_="foreignkey")
    op.drop_index("ix_kpi_definition_inbound_webhook_id", table_name="kpi_definition")
    op.drop_index("ix_kpi_definition_data_flow_id", table_name="kpi_definition")
    op.drop_column("kpi_definition", "inbound_webhook_id")
    op.drop_column("kpi_definition", "data_flow_id")
