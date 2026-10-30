"""add evidence claim gate condition

Revision ID: e1f2a3b4c5d6
Revises: c8d2e4f6a1b3
Create Date: 2026-10-30

根因门只认显式绑定到该门条件的证据；旧记录保持 NULL，不会自动满足根因门。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "c8d2e4f6a1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_project_evidence_claim_gate_condition"
INDEX_NAME = "ix_project_evidence_claim_gate_condition_id"


def upgrade() -> None:
    with op.batch_alter_table("project_evidence_claim") as batch_op:
        batch_op.add_column(sa.Column("gate_condition_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            FK_NAME,
            "project_gate_condition",
            ["gate_condition_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(INDEX_NAME, ["gate_condition_id"])


def downgrade() -> None:
    with op.batch_alter_table("project_evidence_claim") as batch_op:
        batch_op.drop_index(INDEX_NAME)
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.drop_column("gate_condition_id")
