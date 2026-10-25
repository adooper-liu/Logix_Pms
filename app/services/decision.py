"""决策表求值。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.decision import DecisionTable
from app.schemas.decision import DecisionEvaluateOut, DecisionTableOut

HIT_POLICIES = {"FIRST", "COLLECT"}


class DecisionError(ValueError):
    pass


def table_out(row: DecisionTable) -> DecisionTableOut:
    return DecisionTableOut(
        id=row.id,
        code=row.code,
        name=row.name,
        process_id=row.process_id,
        node_key=row.node_key,
        description=row.description,
        hit_policy=row.hit_policy,
        inputs=row.inputs or [],
        outputs=row.outputs or [],
        rules=row.rules or [],
        version=row.version,
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


def list_tables(
    db: Session,
    process_id: Optional[int] = None,
    node_key: Optional[str] = None,
    include_inactive: bool = False,
) -> List[DecisionTable]:
    stmt = select(DecisionTable).order_by(DecisionTable.code)
    if process_id is not None:
        stmt = stmt.where(DecisionTable.process_id == process_id)
    if node_key is not None:
        stmt = stmt.where(DecisionTable.node_key == node_key)
    if not include_inactive:
        stmt = stmt.where(DecisionTable.is_active.is_(True))
    return list(db.scalars(stmt).all())


def require_table(db: Session, code: str) -> DecisionTable:
    row = db.scalar(select(DecisionTable).where(DecisionTable.code == code))
    if row is None:
        raise DecisionError(f"决策表 {code} 不存在")
    return row


def _coerce(value: Any, spec_type: Optional[str]) -> Any:
    if spec_type == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if spec_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "是")
    return value


def _matches(actual: Any, condition: Any) -> bool:
    if isinstance(condition, dict) and "op" in condition:
        op = str(condition.get("op") or "eq").lower()
        expected = condition.get("value")
    else:
        op = "eq"
        expected = condition
    if op == "always":
        return True
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual = float(actual)
        except (TypeError, ValueError):
            return False
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op in ("gt", "gte", "lt", "lte"):
        try:
            left = float(actual)
            right = float(expected)
        except (TypeError, ValueError):
            return False
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[
            op
        ]
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "contains":
        return str(expected) in str(actual or "")
    return False


def evaluate(row: DecisionTable, inputs: Dict[str, Any]) -> DecisionEvaluateOut:
    specs = {spec.get("name"): spec.get("type") for spec in (row.inputs or [])}
    matched_rules: List[Dict[str, Any]] = []
    merged: Dict[str, Any] = {}
    for rule in row.rules or []:
        conditions = rule.get("conditions") or {}
        if all(
            key in inputs and _matches(_coerce(inputs[key], specs.get(key)), condition)
            for key, condition in conditions.items()
        ):
            matched_rules.append(rule)
            for key, value in (rule.get("outputs") or {}).items():
                merged.setdefault(key, value)
            if row.hit_policy == "FIRST":
                break
    return DecisionEvaluateOut(
        code=row.code,
        hit_policy=row.hit_policy,
        matched=bool(matched_rules),
        matched_count=len(matched_rules),
        outputs=merged,
        matched_rules=matched_rules,
    )
