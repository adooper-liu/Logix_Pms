"""asset relations and claim-level evidence

Revision ID: a2f3b4c5d6e7
Revises: b3f4a5b6c7d8

新增 ArchiMate-lite 架构关系与主张级证据表。历史 `process_node.process_arch_id`
回填为 REALIZES 关系；模型版本未知时 `model_version_id` 留空，由服务层显式提示。
"""

import sqlalchemy as sa

from alembic import op

revision = "a2f3b4c5d6e7"
down_revision = "b3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "node_activity_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("path_condition", sa.String(length=16), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_node_activity_link_model_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_node_activity_link_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["process_arch.id"],
            name="fk_node_activity_link_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_node_activity_link_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "model_version_id",
            "node_key",
            "activity_id",
            "relation",
            "path_condition",
            name="uq_node_activity_link",
        ),
    )
    op.create_index(
        "ix_node_activity_link_model_version_id", "node_activity_link", ["model_version_id"]
    )
    op.create_index("ix_node_activity_link_process_id", "node_activity_link", ["process_id"])
    op.create_index("ix_node_activity_link_activity_id", "node_activity_link", ["activity_id"])
    op.create_index("ix_node_activity_link_relation", "node_activity_link", ["relation"])
    op.create_index(
        "ix_node_activity_link_process_node", "node_activity_link", ["process_id", "node_key"]
    )

    op.create_table(
        "activity_relation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("source_activity_id", sa.Integer(), nullable=False),
        sa.Column("target_activity_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_activity_relation_model_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_activity_relation_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_activity_id"],
            ["process_arch.id"],
            name="fk_activity_relation_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_activity_id"],
            ["process_arch.id"],
            name="fk_activity_relation_target",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_activity_relation_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "model_version_id",
            "source_activity_id",
            "target_activity_id",
            "relation",
            name="uq_activity_relation",
        ),
    )
    op.create_index(
        "ix_activity_relation_model_version_id", "activity_relation", ["model_version_id"]
    )
    op.create_index("ix_activity_relation_process_id", "activity_relation", ["process_id"])
    op.create_index(
        "ix_activity_relation_source_activity_id", "activity_relation", ["source_activity_id"]
    )
    op.create_index(
        "ix_activity_relation_target_activity_id", "activity_relation", ["target_activity_id"]
    )
    op.create_index("ix_activity_relation_relation", "activity_relation", ["relation"])

    op.create_table(
        "edge_handoff_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("edge_key", sa.String(length=160), nullable=False),
        sa.Column("from_activity_id", sa.Integer(), nullable=True),
        sa.Column("to_activity_id", sa.Integer(), nullable=True),
        sa.Column("handoff_type", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_edge_handoff_link_model_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_edge_handoff_link_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_activity_id"],
            ["process_arch.id"],
            name="fk_edge_handoff_from",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["to_activity_id"],
            ["process_arch.id"],
            name="fk_edge_handoff_to",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_edge_handoff_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("model_version_id", "edge_key", name="uq_edge_handoff_link"),
    )
    op.create_index(
        "ix_edge_handoff_link_model_version_id", "edge_handoff_link", ["model_version_id"]
    )
    op.create_index("ix_edge_handoff_link_process_id", "edge_handoff_link", ["process_id"])
    op.create_index(
        "ix_edge_handoff_link_from_activity_id", "edge_handoff_link", ["from_activity_id"]
    )
    op.create_index("ix_edge_handoff_link_to_activity_id", "edge_handoff_link", ["to_activity_id"])

    op.create_table(
        "unmodeled_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_name", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_unmodeled_activity_model_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_unmodeled_activity_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["process_arch.id"],
            name="fk_unmodeled_activity_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_unmodeled_activity_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("model_version_id", "activity_id", name="uq_unmodeled_activity"),
    )
    op.create_index(
        "ix_unmodeled_activity_model_version_id", "unmodeled_activity", ["model_version_id"]
    )
    op.create_index("ix_unmodeled_activity_process_id", "unmodeled_activity", ["process_id"])
    op.create_index("ix_unmodeled_activity_activity_id", "unmodeled_activity", ["activity_id"])

    op.create_table(
        "evidence_claim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_version", sa.String(length=64), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("conflict_group", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("query_ref", sa.JSON(), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_name", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_arch.id"],
            name="fk_evidence_claim_process",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["app_user.id"],
            name="fk_evidence_claim_created_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_evidence_claim_process_id", "evidence_claim", ["process_id"])
    op.create_index("ix_evidence_claim_claim_type", "evidence_claim", ["claim_type"])
    op.create_index("ix_evidence_claim_source_type", "evidence_claim", ["source_type"])
    op.create_index("ix_evidence_claim_source_id", "evidence_claim", ["source_id"])
    op.create_index("ix_evidence_claim_method", "evidence_claim", ["method"])
    op.create_index("ix_evidence_claim_conflict_group", "evidence_claim", ["conflict_group"])
    op.create_index("ix_evidence_claim_status", "evidence_claim", ["status"])
    op.create_index("ix_evidence_claim_process_status", "evidence_claim", ["process_id", "status"])

    op.create_table(
        "evidence_claim_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=True),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["evidence_claim.id"], name="fk_evidence_target_claim", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["process_model_version.id"],
            name="fk_evidence_target_model_version",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "claim_id",
            "target_type",
            "target_id",
            "model_version_id",
            "field",
            "condition",
            name="uq_evidence_claim_target",
        ),
    )
    op.create_index("ix_evidence_claim_target_claim_id", "evidence_claim_target", ["claim_id"])
    op.create_index(
        "ix_evidence_claim_target_target_type", "evidence_claim_target", ["target_type"]
    )
    op.create_index("ix_evidence_claim_target_target_id", "evidence_claim_target", ["target_id"])
    op.create_index(
        "ix_evidence_claim_target_model_version_id", "evidence_claim_target", ["model_version_id"]
    )

    op.create_table(
        "evidence_adjudication",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conflict_group", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_by_name", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.Column("authority_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["app_user.id"],
            name="fk_evidence_adjudication_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_evidence_adjudication_conflict_group", "evidence_adjudication", ["conflict_group"]
    )

    # 历史 1:1 活动指针回填为 REALIZES；模型版本未知时留空，服务层会提示。
    op.execute(
        sa.text(
            """
            INSERT INTO node_activity_link (
                model_version_id, process_id, node_key, activity_id, relation,
                path_condition, coverage, confirmed_by_name, confirmed_at, created_at
            )
            SELECT
                (
                    SELECT pmv.id
                    FROM process_model_version pmv
                    WHERE pmv.process_id = pn.process_id
                      AND pmv.status = 'PUBLISHED'
                    ORDER BY pmv.version DESC
                    LIMIT 1
                ),
                pn.process_id, pn.node_key, pn.process_arch_id, 'REALIZES',
                'ALL', 1.0, '系统回填', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM process_node pn
            WHERE pn.process_arch_id IS NOT NULL
            """
        )
    )


def downgrade():
    op.drop_table("evidence_adjudication")
    op.drop_table("evidence_claim_target")
    op.drop_table("evidence_claim")
    op.drop_table("unmodeled_activity")
    op.drop_table("edge_handoff_link")
    op.drop_table("activity_relation")
    op.drop_table("node_activity_link")
