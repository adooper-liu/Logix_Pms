"""add project evidence claims and coded gate conditions

Revision ID: c8d2e4f6a1b3
Revises: b7e1c2d3f4a5
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d2e4f6a1b3"
down_revision: Union[str, Sequence[str], None] = "b7e1c2d3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project_gate_condition") as batch_op:
        batch_op.add_column(sa.Column("condition_code", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_project_gate_condition_condition_code", ["condition_code"])

    op.execute(
        sa.text(
            "UPDATE project_gate_condition SET condition_code = 'ROOT_CAUSE_EVIDENCE' "
            "WHERE stage_no = 2 AND text = '根因结论有至少两类相互印证的证据'"
        )
    )

    op.create_table(
        "project_evidence_claim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("counterevidence", sa.Text(), nullable=False),
        sa.Column("evidence_level", sa.String(length=2), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source_description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("sample_scope", sa.Text(), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_project_evidence_claim_project_id", "project_evidence_claim", ["project_id"]
    )
    op.create_index(
        "ix_project_evidence_claim_evidence_level", "project_evidence_claim", ["evidence_level"]
    )
    op.create_index(
        "ix_project_evidence_claim_evidence_type", "project_evidence_claim", ["evidence_type"]
    )
    op.create_index("ix_project_evidence_claim_verdict", "project_evidence_claim", ["verdict"])
    op.create_index(
        "ix_project_evidence_claim_created_by_user_id",
        "project_evidence_claim",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_project_evidence_claim_decided_by_user_id",
        "project_evidence_claim",
        ["decided_by_user_id"],
    )
    op.create_index(
        "ix_evidence_claim_project_verdict", "project_evidence_claim", ["project_id", "verdict"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_claim_project_verdict", table_name="project_evidence_claim")
    op.drop_index(
        "ix_project_evidence_claim_decided_by_user_id", table_name="project_evidence_claim"
    )
    op.drop_index(
        "ix_project_evidence_claim_created_by_user_id", table_name="project_evidence_claim"
    )
    op.drop_index("ix_project_evidence_claim_verdict", table_name="project_evidence_claim")
    op.drop_index("ix_project_evidence_claim_evidence_type", table_name="project_evidence_claim")
    op.drop_index("ix_project_evidence_claim_evidence_level", table_name="project_evidence_claim")
    op.drop_index("ix_project_evidence_claim_project_id", table_name="project_evidence_claim")
    op.drop_table("project_evidence_claim")

    with op.batch_alter_table("project_gate_condition") as batch_op:
        batch_op.drop_index("ix_project_gate_condition_condition_code")
        batch_op.drop_column("condition_code")
