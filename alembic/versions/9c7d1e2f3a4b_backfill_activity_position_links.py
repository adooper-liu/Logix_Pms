"""backfill activity and position links

Revision ID: 9c7d1e2f3a4b
Revises: b2cc822277d2
Create Date: 2026-10-23 21:10:00.000000

说明：b2cc822277d2 已经包含同一套回填逻辑；这个迁移用于那些在 schema 迁移
生成后、回填逻辑写入前就被自动迁移过的数据库（例如本地 --reload 服务）。
逻辑保持幂等：只补缺失的岗位/链接，不覆盖已有值。
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c7d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "b2cc822277d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    now = _now()

    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT name FROM position")).fetchall()
    }
    codes = {
        row[0]
        for row in bind.execute(sa.text("SELECT code FROM position")).fetchall()
    }
    owners = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT DISTINCT owner_role FROM process_node "
                "WHERE owner_role IS NOT NULL AND TRIM(owner_role) <> '' ORDER BY owner_role"
            )
        ).fetchall()
    ]
    next_code = 1
    for name in owners:
        if name in existing:
            continue
        while f"POS-{next_code:03d}" in codes:
            next_code += 1
        code = f"POS-{next_code:03d}"
        codes.add(code)
        existing.add(name)
        next_code += 1
        bind.execute(
            sa.text(
                "INSERT INTO position (code, name, is_active, created_at, updated_at) "
                "VALUES (:code, :name, :active, :created_at, :updated_at)"
            ),
            {
                "code": code,
                "name": name,
                "active": True,
                "created_at": now,
                "updated_at": now,
            },
        )

    bind.execute(
        sa.text(
            "UPDATE process_node SET owner_position_id = ("
            "  SELECT p.id FROM position p WHERE p.name = process_node.owner_role LIMIT 1"
            ") WHERE owner_position_id IS NULL "
            "AND owner_role IS NOT NULL AND TRIM(owner_role) <> ''"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE process_arch SET org_unit_id = ("
            "  SELECT o.id FROM org_unit o WHERE o.name = process_arch.department LIMIT 1"
            ") WHERE org_unit_id IS NULL AND department IS NOT NULL "
            "AND 1 = (SELECT COUNT(*) FROM org_unit o WHERE o.name = process_arch.department)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE process_node SET process_arch_id = ("
            "  SELECT pa.id FROM process_arch pa "
            "  WHERE pa.parent_id = process_node.process_id "
            "    AND pa.level = 4 AND pa.name = process_node.name LIMIT 1"
            ") WHERE process_arch_id IS NULL "
            "AND 1 = (SELECT COUNT(*) FROM process_arch pa "
            "         WHERE pa.parent_id = process_node.process_id "
            "           AND pa.level = 4 AND pa.name = process_node.name)"
        )
    )


def downgrade() -> None:
    # 数据回填不做反向删除：岗位可能已被人工修改/引用。
    pass
