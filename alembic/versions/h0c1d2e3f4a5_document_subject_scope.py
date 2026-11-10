"""document subject scopes for compiled position deliverables

Revision ID: h0c1d2e3f4a5
Revises: g9b0c1d2e3f4
"""

import sqlalchemy as sa

from alembic import op

revision = "h0c1d2e3f4a5"
down_revision = "g9b0c1d2e3f4"
branch_labels = None
depends_on = None

SUBJECT_CHECK = (
    "(scope='PROCESS' AND process_id IS NOT NULL AND position_id IS NULL AND governance_role_id IS NULL) OR "
    "(scope='POSITION' AND process_id IS NULL AND position_id IS NOT NULL AND governance_role_id IS NULL AND node_key IS NULL) OR "
    "(scope='ROLE' AND process_id IS NULL AND position_id IS NULL AND governance_role_id IS NOT NULL AND node_key IS NULL)"
)


def upgrade():
    with op.batch_alter_table("process_document") as batch:
        batch.add_column(
            sa.Column("scope", sa.String(16), nullable=False, server_default="PROCESS")
        )
        batch.add_column(sa.Column("position_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("governance_role_id", sa.Integer(), nullable=True))
        batch.alter_column("process_id", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key(
            "fk_document_position", "position", ["position_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_foreign_key(
            "fk_document_role",
            "governance_role",
            ["governance_role_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_process_document_position_id", ["position_id"])
        batch.create_index("ix_process_document_governance_role_id", ["governance_role_id"])
        batch.create_check_constraint("ck_document_subject", SUBJECT_CHECK)


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM process_document WHERE scope <> 'PROCESS' LIMIT 1"))
        .first()
    ):
        raise RuntimeError(
            "P2 subject documents exist; preserve data and migration before downgrade"
        )
    with op.batch_alter_table("process_document") as batch:
        batch.drop_constraint("ck_document_subject", type_="check")
        batch.drop_index("ix_process_document_position_id")
        batch.drop_index("ix_process_document_governance_role_id")
        batch.drop_constraint("fk_document_position", type_="foreignkey")
        batch.drop_constraint("fk_document_role", type_="foreignkey")
        batch.alter_column("process_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("position_id")
        batch.drop_column("governance_role_id")
        batch.drop_column("scope")
