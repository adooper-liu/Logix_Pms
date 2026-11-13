"""add generic process operating contract tables

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_operating_cycle",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("supersedes_cycle_id", sa.Integer(), nullable=True),
        sa.Column("cycle_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["model_version_id"], ["process_model_version.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["process_id"], ["process_arch.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_cycle_id"], ["process_operating_cycle.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_operating_cycle_process_id", "process_operating_cycle", ["process_id"])
    op.create_index("ix_process_operating_cycle_project_id", "process_operating_cycle", ["project_id"])
    op.create_index("ix_process_operating_cycle_model_version_id", "process_operating_cycle", ["model_version_id"])
    op.create_index("ix_process_operating_cycle_supersedes_cycle_id", "process_operating_cycle", ["supersedes_cycle_id"])
    op.create_index("ix_process_operating_cycle_cycle_type", "process_operating_cycle", ["cycle_type"])
    op.create_index("ix_process_operating_cycle_status", "process_operating_cycle", ["status"])
    op.create_index("uq_operating_cycle_active", "process_operating_cycle", ["process_id"], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"), sqlite_where=sa.text("status = 'ACTIVE'"))

    op.create_table(
        "process_gate_assessment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("gate_key", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applicability", sa.String(length=20), nullable=False),
        sa.Column("rigor", sa.String(length=16), nullable=False),
        sa.Column("applicability_reason", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("verifier_user_id", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("next_action_ref", sa.String(length=160), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["process_operating_cycle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verifier_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id", "gate_key", "revision", name="uq_gate_revision"),
    )
    op.create_index("ix_process_gate_assessment_cycle_id", "process_gate_assessment", ["cycle_id"])
    op.create_index("ix_process_gate_assessment_gate_key", "process_gate_assessment", ["gate_key"])
    op.create_index("ix_process_gate_assessment_owner_user_id", "process_gate_assessment", ["owner_user_id"])
    op.create_index("ix_process_gate_assessment_verifier_user_id", "process_gate_assessment", ["verifier_user_id"])
    op.create_index("ix_process_gate_assessment_is_current", "process_gate_assessment", ["is_current"])

    op.create_table(
        "process_gate_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gate_assessment_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_version_or_hash", sa.String(length=128), nullable=True),
        sa.Column("evidence_grade", sa.String(length=4), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["gate_assessment_id"], ["process_gate_assessment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_gate_evidence_gate_assessment_id", "process_gate_evidence", ["gate_assessment_id"])
    op.create_index("ix_process_gate_evidence_source_type", "process_gate_evidence", ["source_type"])
    op.create_index("ix_process_gate_evidence_verified_by_user_id", "process_gate_evidence", ["verified_by_user_id"])

    op.create_table(
        "process_operating_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("decision_type", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("decision_by_user_id", sa.Integer(), nullable=False),
        sa.Column("authority_basis", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_snapshot", sa.Text(), nullable=True),
        sa.Column("valid_scope", sa.String(length=160), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.Column("follow_up_due", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["process_operating_cycle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_by_user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_operating_decision_cycle_id", "process_operating_decision", ["cycle_id"])
    op.create_index("ix_process_operating_decision_decision_type", "process_operating_decision", ["decision_type"])
    op.create_index("ix_process_operating_decision_decision_by_user_id", "process_operating_decision", ["decision_by_user_id"])


def downgrade() -> None:
    op.drop_table("process_operating_decision")
    op.drop_table("process_gate_evidence")
    op.drop_table("process_gate_assessment")
    op.drop_index("uq_operating_cycle_active", table_name="process_operating_cycle")
    op.drop_table("process_operating_cycle")
