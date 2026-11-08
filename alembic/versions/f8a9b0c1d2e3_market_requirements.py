"""market requirements and objective links

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_requirement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.String(length=500), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["app_user.id"],
            name="fk_requirement_creator",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_market_requirement_code", "market_requirement", ["code"], unique=True
    )
    op.create_index(
        "ix_market_requirement_source_type", "market_requirement", ["source_type"]
    )
    op.create_index("ix_market_requirement_status", "market_requirement", ["status"])
    op.create_index(
        "ix_market_requirement_created_by_id", "market_requirement", ["created_by_id"]
    )
    op.create_index(
        "ix_market_requirement_created_at", "market_requirement", ["created_at"]
    )
    op.create_index(
        "ix_requirement_status_type",
        "market_requirement",
        ["status", "source_type"],
    )

    op.create_table(
        "requirement_objective_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("objective_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["market_requirement.id"],
            name="fk_requirement_link_requirement",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["strategy_objective.id"],
            name="fk_requirement_link_objective",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "requirement_id", "objective_id", name="uq_requirement_objective"
        ),
    )
    op.create_index(
        "ix_requirement_objective_link_requirement_id",
        "requirement_objective_link",
        ["requirement_id"],
    )
    op.create_index(
        "ix_requirement_objective_link_objective_id",
        "requirement_objective_link",
        ["objective_id"],
    )
    op.create_index(
        "ix_requirement_link_objective",
        "requirement_objective_link",
        ["objective_id", "requirement_id"],
    )


def downgrade():
    op.drop_table("requirement_objective_link")
    op.drop_table("market_requirement")
