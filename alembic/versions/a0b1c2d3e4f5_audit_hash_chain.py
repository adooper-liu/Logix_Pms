"""audit log hash chain

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-10-25
"""

from __future__ import annotations

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _digest(prev_hash, row) -> str:
    payload = "|".join(
        [
            prev_hash or "",
            str(row["user_id"] or ""),
            row["username"] or "",
            row["action"] or "",
            row["entity_type"] or "",
            str(row["entity_id"] if row["entity_id"] is not None else ""),
            row["summary"] or "",
            (
                row["created_at"].isoformat()
                if hasattr(row["created_at"], "isoformat")
                else str(row["created_at"] or "")
            ),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_log", sa.Column("hash", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_log_hash", "audit_log", ["hash"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, user_id, username, action, entity_type, entity_id, summary, created_at "
            "FROM audit_log ORDER BY id"
        )
    ).mappings()
    prev = None
    for row in rows:
        digest = _digest(prev, row)
        bind.execute(
            sa.text("UPDATE audit_log SET prev_hash = :prev, hash = :hash WHERE id = :id"),
            {"prev": prev, "hash": digest, "id": row["id"]},
        )
        prev = digest


def downgrade() -> None:
    op.drop_index("ix_audit_log_hash", table_name="audit_log")
    op.drop_column("audit_log", "hash")
    op.drop_column("audit_log", "prev_hash")
