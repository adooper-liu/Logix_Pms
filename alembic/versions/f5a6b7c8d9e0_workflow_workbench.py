"""five-stage workflow workbench

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GATE_CONDITIONS = {
    1: [
        "项目范围与流程对象已确认",
        "目标值与基线已定义",
        "立项决策与责任人已记录",
        "关键依赖与资源约束已识别",
    ],
    2: [
        "根因结论有至少两类相互印证的证据",
        "受影响范围已界定到流程环节、对象和责任团队",
        "诊断结论已由执行方和接收方共同确认",
        "关键遗留问题已有责任人和关闭日期",
    ],
    3: [
        "方案比较有明确依据（收益/成本/风险）",
        "风险与回退方案已确认",
        "试点范围、接收方和评估口径已确认",
    ],
    4: [
        "试点结果达到预设目标或已记录偏差",
        "推广计划、培训与责任已确认",
        "试点遗留问题已关闭或移交",
    ],
    5: [
        "运行基线与控制限已定义",
        "监控责任人、采样频率已确认",
        "复盘周期与偏差触发条件已记录",
    ],
}


def upgrade() -> None:
    with op.batch_alter_table("project_step") as batch_op:
        batch_op.add_column(sa.Column("goal", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("inputs", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("process_steps", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("output", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("evidence", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("next_action", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("receiver", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("verified_by", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("blocked_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("blocked_owner", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("blocked_due", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("decision_options", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("decision_maker", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("decision_due", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("updated_by", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.create_table(
        "project_gate_condition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=240), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(length=64), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_met", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("met_at", sa.DateTime(), nullable=True),
        sa.Column("met_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_project_gate_condition_project_id", "project_gate_condition", ["project_id"])
    op.create_index("ix_project_gate_condition_stage_no", "project_gate_condition", ["stage_no"])
    op.create_index("ix_project_gate_condition_is_met", "project_gate_condition", ["is_met"])
    op.create_index(
        "ix_project_gate_project_stage",
        "project_gate_condition",
        ["project_id", "stage_no", "sort_order"],
    )

    bind = op.get_bind()
    project_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM project")).all()]
    for project_id in project_ids:
        for stage_no, texts in GATE_CONDITIONS.items():
            for order, text in enumerate(texts, start=1):
                bind.execute(
                    sa.text(
                        "INSERT INTO project_gate_condition "
                        "(project_id, stage_no, text, is_met, is_critical, sort_order) "
                        "VALUES (:project_id, :stage_no, :text, false, true, :sort_order)"
                    ),
                    {
                        "project_id": project_id,
                        "stage_no": stage_no,
                        "text": text,
                        "sort_order": order,
                    },
                )


def downgrade() -> None:
    op.drop_index("ix_project_gate_project_stage", table_name="project_gate_condition")
    op.drop_index("ix_project_gate_condition_is_met", table_name="project_gate_condition")
    op.drop_index("ix_project_gate_condition_stage_no", table_name="project_gate_condition")
    op.drop_index("ix_project_gate_condition_project_id", table_name="project_gate_condition")
    op.drop_table("project_gate_condition")

    with op.batch_alter_table("project_step") as batch_op:
        for column in (
            "updated_at",
            "updated_by",
            "decision_due",
            "decision_maker",
            "decision_options",
            "blocked_due",
            "blocked_owner",
            "blocked_reason",
            "verified_at",
            "verified_by",
            "receiver",
            "next_action",
            "evidence",
            "output",
            "process_steps",
            "inputs",
            "goal",
        ):
            batch_op.drop_column(column)
