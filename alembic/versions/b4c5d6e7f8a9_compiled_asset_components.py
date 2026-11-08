"""compiled asset package provenance

Revision ID: b4c5d6e7f8a9
Revises: a2f3b4c5d6e7

把「生成来源 + 生成清单」挂在既有的 process_document_version 上，并新增组件引用表。
资产包复用流程级标准文件的生命周期，不另造一套版本表。
"""

import sqlalchemy as sa

from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a2f3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("process_document_version") as batch:
        batch.add_column(
            sa.Column(
                "source_kind",
                sa.String(length=16),
                nullable=False,
                server_default="UPLOAD",
            )
        )
        batch.add_column(sa.Column("compile_manifest", sa.JSON(), nullable=True))
        batch.create_index("ix_process_document_version_source_kind", ["source_kind"])

    op.create_table(
        "compiled_asset_component",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("component_type", sa.String(length=24), nullable=False),
        sa.Column("component_ref_id", sa.Integer(), nullable=True),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["process_document_version.id"],
            name="fk_compiled_component_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["process_arch.id"],
            name="fk_compiled_component_activity",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_compiled_asset_component_document_version_id",
        "compiled_asset_component",
        ["document_version_id"],
    )
    op.create_index(
        "ix_compiled_asset_component_component_type",
        "compiled_asset_component",
        ["component_type"],
    )
    op.create_index(
        "ix_compiled_asset_component_component_ref_id",
        "compiled_asset_component",
        ["component_ref_id"],
    )
    op.create_index(
        "ix_compiled_asset_component_activity_id",
        "compiled_asset_component",
        ["activity_id"],
    )
    op.create_index(
        "ix_compiled_component_version_type",
        "compiled_asset_component",
        ["document_version_id", "component_type"],
    )


def downgrade():
    op.drop_table("compiled_asset_component")
    with op.batch_alter_table("process_document_version") as batch:
        batch.drop_index("ix_process_document_version_source_kind")
        batch.drop_column("compile_manifest")
        batch.drop_column("source_kind")
