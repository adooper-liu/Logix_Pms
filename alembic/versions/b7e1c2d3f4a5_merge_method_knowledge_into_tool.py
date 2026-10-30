"""merge method/tool knowledge into tool

Revision ID: b7e1c2d3f4a5
Revises: ffffc3c1106f
Create Date: 2026-10-28 10:00:00.000000

把知识库里的 METHOD / TOOL（含旧的 BEST_PRACTICE）条目并入工具表：
- tool 新增 content 列，承载原来知识条目的长正文；
- 有 tool_code 的条目只补工具的空字段，不覆盖人工维护值；
- 没有匹配工具的条目创建为一条新工具；
- 使用证据、场景关联同步到工具侧；源知识条目归档保留，便于追溯。

注意：数据归并是单向的。downgrade 只回退 schema（删除 tool.content），
不会把已归档的源条目恢复成公开状态。
"""

from typing import Any, Dict, List, Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c2d3f4a5"
down_revision: Union[str, Sequence[str], None] = "ffffc3c1106f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIGRATED_TYPES = ("METHOD", "TOOL", "BEST_PRACTICE")
_CATEGORY_BY_STAGE = {
    1: "DIAGNOSE",
    2: "DIAGNOSE",
    3: "DESIGN",
    4: "DEPLOY",
    5: "MONITOR",
}


def _first_nonempty(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _split_steps(text: Optional[str]) -> List[str]:
    if not text:
        return []
    parts: List[str] = []
    for line in text.replace("；", "\n").replace(";", "\n").splitlines():
        item = line.strip(" -•\t")
        if item:
            parts.append(item)
    return parts


def _unique_code(base: str, existing: set) -> str:
    code = (base or "").strip().upper()[:32] or "KB"
    if code not in existing:
        return code
    suffix = 1
    while True:
        candidate = f"{code[:28]}-{suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1


def _tool_payload(row: Dict[str, Any], stage_no: int, sort_order: int) -> Dict[str, Any]:
    return {
        "name": (row.get("title") or "未命名工具")[:64],
        "alias": None,
        "category": _CATEGORY_BY_STAGE.get(stage_no, "DIAGNOSE"),
        "stage_no": stage_no,
        "purpose": _first_nonempty(row.get("claim"), row.get("summary"), row.get("title"))
        or "待补充",
        "when_to_use": _first_nonempty(
            row.get("applicable_when"), row.get("summary"), row.get("title")
        )
        or "待补充",
        "steps": _split_steps(row.get("steps_summary")),
        "content": row.get("content"),
        "template_ref": None,
        "pitfalls": None,
        "not_applicable_when": row.get("not_applicable_when"),
        "prerequisites": row.get("input_conditions"),
        "verification_standard": None,
        "difficulty": "MEDIUM",
        "typical_duration": None,
        "owner_user_id": row.get("owner_user_id"),
        "version": 1,
        "status": row.get("status") or "PUBLISHED",
        "submitted_at": None,
        "reviewed_by_user_id": row.get("verified_by_user_id"),
        "reviewed_at": row.get("last_verified_at"),
        "last_verified_at": row.get("last_verified_at"),
        "review_due_at": row.get("review_due_at"),
        "is_active": True,
        "sort_order": sort_order,
    }


def _primary_stage(bind, item_id: int) -> int:
    row = bind.execute(
        sa.text(
            "SELECT stage_no FROM knowledge_workflow_link "
            "WHERE knowledge_id = :kid ORDER BY is_primary DESC, stage_no ASC LIMIT 1"
        ),
        {"kid": item_id},
    ).first()
    return int(row[0]) if row and row[0] else 3


def _append_text(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if not incoming or not incoming.strip():
        return current
    if not current or not current.strip():
        return incoming.strip()
    if incoming.strip() in current:
        return current
    return current.rstrip() + "\n\n---\n\n" + incoming.strip()


def _copy_usage(bind, knowledge_usage, tool_usage, item: Dict[str, Any], tool_code: str) -> None:
    rows = bind.execute(
        knowledge_usage.select().where(knowledge_usage.c.knowledge_id == item["id"])
    ).mappings()
    for usage in rows:
        exists = bind.execute(
            sa.select(tool_usage.c.id)
            .where(
                tool_usage.c.tool_code == tool_code,
                tool_usage.c.used_at == usage["used_at"],
                tool_usage.c.outcome == usage["outcome"],
                sa.func.coalesce(tool_usage.c.note, "") == (usage["note"] or ""),
            )
            .limit(1)
        ).first()
        if exists:
            continue
        bind.execute(
            tool_usage.insert().values(
                tool_code=tool_code,
                project_id=usage["project_id"],
                step_no=usage["step_no"],
                used_by_user_id=usage["used_by_user_id"],
                used_at=usage["used_at"],
                outcome=usage["outcome"],
                note=usage["note"],
                evidence_url=usage["evidence_url"],
            )
        )


def _copy_scenarios(bind, knowledge_scenario, tool_scenario, item: Dict[str, Any], tool_id: int) -> None:
    rows = bind.execute(
        knowledge_scenario.select().where(knowledge_scenario.c.knowledge_id == item["id"])
    ).mappings()
    for link in rows:
        exists = bind.execute(
            sa.select(tool_scenario.c.id)
            .where(
                tool_scenario.c.tool_id == tool_id,
                tool_scenario.c.scenario_id == link["scenario_id"],
            )
            .limit(1)
        ).first()
        if exists:
            continue
        bind.execute(
            tool_scenario.insert().values(
                tool_id=tool_id,
                scenario_id=link["scenario_id"],
                weight=link["weight"] or 1.0,
            )
        )


def upgrade() -> None:
    op.add_column("tool", sa.Column("content", sa.Text(), nullable=True))

    bind = op.get_bind()
    meta = sa.MetaData()
    tool = sa.Table("tool", meta, autoload_with=bind)
    knowledge = sa.Table("knowledge_item", meta, autoload_with=bind)
    tool_usage = sa.Table("tool_usage", meta, autoload_with=bind)
    tool_scenario = sa.Table("tool_scenario_link", meta, autoload_with=bind)
    knowledge_usage = sa.Table("knowledge_usage", meta, autoload_with=bind)
    knowledge_scenario = sa.Table("knowledge_scenario_link", meta, autoload_with=bind)

    rows = [
        dict(row)
        for row in bind.execute(
            knowledge.select().where(knowledge.c.type.in_(MIGRATED_TYPES))
        ).mappings()
    ]
    if not rows:
        return

    tools_by_code = {
        row.code: dict(row)
        for row in bind.execute(tool.select()).mappings()
    }
    next_sort = (
        bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), 0) FROM tool")).scalar() or 0
    )

    for item in rows:
        tool_code = (item.get("tool_code") or "").strip().upper()
        target = tools_by_code.get(tool_code) if tool_code else None

        if target is None:
            code = _unique_code(tool_code or f"KB-{item['id']}", set(tools_by_code))
            next_sort += 1
            payload = _tool_payload(item, _primary_stage(bind, item["id"]), next_sort)
            payload["code"] = code
            result = bind.execute(tool.insert().values(**payload))
            tool_id = result.inserted_primary_key[0]
            tool_code = code
            tools_by_code[code] = {**payload, "id": tool_id}
        else:
            updates: Dict[str, Any] = {}
            merged_content = _append_text(target.get("content"), item.get("content"))
            if merged_content != target.get("content"):
                updates["content"] = merged_content
            if not (target.get("purpose") or "").strip():
                updates["purpose"] = _first_nonempty(
                    item.get("claim"), item.get("summary"), item.get("title")
                )
            if not (target.get("when_to_use") or "").strip():
                updates["when_to_use"] = _first_nonempty(
                    item.get("applicable_when"), item.get("summary")
                )
            if not (target.get("not_applicable_when") or "").strip():
                updates["not_applicable_when"] = item.get("not_applicable_when")
            if not (target.get("prerequisites") or "").strip():
                updates["prerequisites"] = item.get("input_conditions")
            if not target.get("steps"):
                steps = _split_steps(item.get("steps_summary"))
                if steps:
                    updates["steps"] = steps
            if updates:
                updates = {key: value for key, value in updates.items() if value is not None}
                if updates:
                    bind.execute(
                        tool.update().where(tool.c.id == target["id"]).values(**updates)
                    )
                    target.update(updates)
            tool_id = target["id"]

        _copy_usage(bind, knowledge_usage, tool_usage, item, tool_code)
        _copy_scenarios(bind, knowledge_scenario, tool_scenario, item, tool_id)
        bind.execute(
            knowledge.update()
            .where(knowledge.c.id == item["id"])
            .values(status="ARCHIVED")
        )


def downgrade() -> None:
    with op.batch_alter_table("tool") as batch_op:
        batch_op.drop_column("content")
