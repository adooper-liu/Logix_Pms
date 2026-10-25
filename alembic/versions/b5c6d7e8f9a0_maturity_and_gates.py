"""maturity assessments and phase gate attestations

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column(
                "gate_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
            )
        )
        batch_op.create_index("ix_project_gate_required", ["gate_required"])

    op.create_table(
        "maturity_assessment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "process_id",
            sa.Integer(),
            sa.ForeignKey("process_arch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            sa.Integer(),
            sa.ForeignKey("org_unit.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("evidence_url", sa.String(length=500), nullable=False),
        sa.Column(
            "assessed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assessed_at", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_maturity_assessment_process_id", "maturity_assessment", ["process_id"])
    op.create_index("ix_maturity_assessment_org_unit_id", "maturity_assessment", ["org_unit_id"])
    op.create_index("ix_maturity_assessment_dimension", "maturity_assessment", ["dimension"])
    op.create_index(
        "ix_maturity_assessment_assessed_by_user_id", "maturity_assessment", ["assessed_by_user_id"]
    )
    op.create_index("ix_maturity_assessment_assessed_at", "maturity_assessment", ["assessed_at"])
    op.create_index(
        "ix_maturity_process_dimension", "maturity_assessment", ["process_id", "dimension"]
    )

    op.create_table(
        "gate_attestation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_no", sa.Integer(), nullable=False),
        sa.Column("gate_code", sa.String(length=32), nullable=False, server_default="STAGE_GATE"),
        sa.Column("exit_criteria", sa.Text(), nullable=True),
        sa.Column("evidence_url", sa.String(length=500), nullable=False),
        sa.Column("conclusion", sa.String(length=16), nullable=False),
        sa.Column(
            "signed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gate_attestation_project_id", "gate_attestation", ["project_id"])
    op.create_index("ix_gate_attestation_stage_no", "gate_attestation", ["stage_no"])
    op.create_index("ix_gate_attestation_conclusion", "gate_attestation", ["conclusion"])
    op.create_index(
        "ix_gate_attestation_signed_by_user_id", "gate_attestation", ["signed_by_user_id"]
    )
    op.create_index("ix_gate_attestation_signed_at", "gate_attestation", ["signed_at"])
    op.create_index("ix_gate_project_stage", "gate_attestation", ["project_id", "stage_no"])


def downgrade() -> None:
    op.drop_index("ix_gate_project_stage", table_name="gate_attestation")
    op.drop_index("ix_gate_attestation_signed_at", table_name="gate_attestation")
    op.drop_index("ix_gate_attestation_signed_by_user_id", table_name="gate_attestation")
    op.drop_index("ix_gate_attestation_conclusion", table_name="gate_attestation")
    op.drop_index("ix_gate_attestation_stage_no", table_name="gate_attestation")
    op.drop_index("ix_gate_attestation_project_id", table_name="gate_attestation")
    op.drop_table("gate_attestation")

    op.drop_index("ix_maturity_process_dimension", table_name="maturity_assessment")
    op.drop_index("ix_maturity_assessment_assessed_at", table_name="maturity_assessment")
    op.drop_index("ix_maturity_assessment_assessed_by_user_id", table_name="maturity_assessment")
    op.drop_index("ix_maturity_assessment_dimension", table_name="maturity_assessment")
    op.drop_index("ix_maturity_assessment_org_unit_id", table_name="maturity_assessment")
    op.drop_index("ix_maturity_assessment_process_id", table_name="maturity_assessment")
    op.drop_table("maturity_assessment")

    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_index("ix_project_gate_required")
        batch_op.drop_column("gate_required")
