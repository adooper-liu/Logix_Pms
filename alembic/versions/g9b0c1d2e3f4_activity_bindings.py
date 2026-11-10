"""activity binding scopes, original resource links and immutable binding snapshot

Revision ID: g9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

import sqlalchemy as sa
from alembic import op

revision = "g9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("raci_assignment") as batch:
        batch.add_column(sa.Column("activity_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("node_key", sa.String(64), nullable=True))
        batch.add_column(sa.Column("scope_key", sa.String(160), nullable=True))
        batch.create_foreign_key(
            "fk_raci_activity", "process_arch", ["activity_id"], ["id"], ondelete="CASCADE"
        )
    op.execute("UPDATE raci_assignment SET scope_key = 'MATTER:' || matter")
    # Old data may contain invalid double-A rows. Never silently pick one or delete evidence.
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT process_id, scope_key FROM raci_assignment WHERE raci='A' GROUP BY process_id,scope_key HAVING count(*)>1"
        )
    ).first()
    if duplicates:
        raise RuntimeError("RACI contains duplicate accountable rows; resolve before P1 migration")
    with op.batch_alter_table("raci_assignment") as batch:
        batch.alter_column("scope_key", existing_type=sa.String(160), nullable=False)
        batch.drop_constraint("uq_raci_process_matter_role", type_="unique")
        batch.create_unique_constraint(
            "uq_raci_process_scope_role", ["process_id", "scope_key", "role_id"]
        )
        batch.create_index("ix_raci_assignment_activity_id", ["activity_id"])
        batch.create_index("ix_raci_assignment_scope_key", ["scope_key"])
    op.create_index(
        "uq_raci_scope_accountable",
        "raci_assignment",
        ["process_id", "scope_key"],
        unique=True,
        sqlite_where=sa.text("raci = 'A'"),
        postgresql_where=sa.text("raci = 'A'"),
    )
    op.create_table(
        "activity_resource_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(16), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("ref_key", sa.String(128), nullable=False),
        sa.Column("org_scope", sa.String(16), nullable=False, server_default="GLOBAL"),
        sa.Column("node_key", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["process_arch.id"],
            name="fk_resource_link_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["app_user.id"], name="fk_resource_link_creator", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("activity_id", "ref_key", "org_scope", name="uq_activity_resource_ref"),
    )
    op.create_index(
        "ix_activity_resource_link_activity_id", "activity_resource_link", ["activity_id"]
    )
    op.create_index(
        "ix_activity_resource_link_resource_type", "activity_resource_link", ["resource_type"]
    )
    with op.batch_alter_table("process_model_version") as batch:
        batch.add_column(sa.Column("binding_snapshot", sa.JSON(), nullable=True))


def downgrade():
    bind = op.get_bind()
    scoped = bind.execute(
        sa.text(
            "SELECT 1 FROM raci_assignment WHERE activity_id IS NOT NULL OR node_key IS NOT NULL LIMIT 1"
        )
    ).first()
    links = bind.execute(sa.text("SELECT 1 FROM activity_resource_link LIMIT 1")).first()
    models = sa.table("process_model_version", sa.column("binding_snapshot", sa.JSON()))
    snapshots = bind.execute(sa.select(models.c.binding_snapshot)).scalars().all()
    if scoped or links or any(value is not None for value in snapshots):
        raise RuntimeError(
            "P1 binding data exists; preserve g9b0c1d2e3f4 and export/restore before downgrade"
        )
    with op.batch_alter_table("process_model_version") as batch:
        batch.drop_column("binding_snapshot")
    op.drop_table("activity_resource_link")
    op.drop_index("uq_raci_scope_accountable", table_name="raci_assignment")
    with op.batch_alter_table("raci_assignment") as batch:
        batch.drop_index("ix_raci_assignment_activity_id")
        batch.drop_index("ix_raci_assignment_scope_key")
        batch.drop_constraint("uq_raci_process_scope_role", type_="unique")
        batch.create_unique_constraint(
            "uq_raci_process_matter_role", ["process_id", "matter", "role_id"]
        )
        batch.drop_constraint("fk_raci_activity", type_="foreignkey")
        batch.drop_column("scope_key")
        batch.drop_column("node_key")
        batch.drop_column("activity_id")
