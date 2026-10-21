"""表单定义与分支规则：校验、快照与条件求值。

表单字段是 JSON 数组，支持 text / textarea / number / date / select / checkbox。
规则条件是「全部满足」语义，命中后流转到 target_node_key；显式 next_node_key 优先。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import FormDefinition, ProcessRule
from app.models.process import ProcessEdge, ProcessNode

SUPPORTED_FIELD_TYPES = {"text", "textarea", "number", "date", "select", "checkbox"}
SUPPORTED_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "truthy", "falsy"}
NUMERIC_OPS = {"gt", "gte", "lt", "lte"}


# ------------------------------------------------------------------ 表单


def normalize_fields(fields: List[Dict]) -> List[Dict]:
    if not isinstance(fields, list):
        raise HTTPException(status_code=400, detail="fields 必须是数组")
    out: List[Dict] = []
    keys: set[str] = set()
    for raw in fields:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="每个字段必须是对象")
        key = str(raw.get("key") or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="字段缺少 key")
        if key in keys:
            raise HTTPException(status_code=400, detail=f"字段 key 重复：{key}")
        keys.add(key)
        label = str(raw.get("label") or key).strip()
        field_type = str(raw.get("type") or "text").strip()
        if field_type not in SUPPORTED_FIELD_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"字段 {key} 的类型不支持：{field_type}（支持 {', '.join(sorted(SUPPORTED_FIELD_TYPES))}）",
            )
        item: Dict[str, Any] = {
            "key": key,
            "label": label,
            "type": field_type,
            "required": bool(raw.get("required", False)),
        }
        if raw.get("placeholder"):
            item["placeholder"] = str(raw["placeholder"])
        if field_type == "select":
            options = raw.get("options") or []
            if not isinstance(options, list) or not options:
                raise HTTPException(status_code=400, detail=f"下拉字段 {key} 必须提供 options")
            item["options"] = [str(o) for o in options]
        if field_type == "number":
            for bound in ("min", "max"):
                if raw.get(bound) is not None:
                    try:
                        item[bound] = float(raw[bound])
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            status_code=400, detail=f"字段 {key} 的 {bound} 必须是数字"
                        ) from exc
        out.append(item)
    return out


def validate_form_data(fields: List[Dict], data: Optional[Dict]) -> Dict:
    result = dict(data or {})
    errors: List[str] = []
    for field in fields or []:
        key = field.get("key")
        label = field.get("label") or key
        value = result.get(key)
        empty = value is None or value == "" or value == []
        if empty:
            if field.get("required"):
                errors.append(f"{label}为必填")
            continue
        field_type = field.get("type")
        if field_type == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors.append(f"{label}必须是数字")
                continue
            if field.get("min") is not None and number < field["min"]:
                errors.append(f"{label}不能小于 {field['min']}")
            if field.get("max") is not None and number > field["max"]:
                errors.append(f"{label}不能大于 {field['max']}")
            result[key] = number
        elif field_type == "checkbox":
            result[key] = bool(value)
        elif field_type == "select":
            options = [str(o) for o in field.get("options", [])]
            if str(value) not in options:
                errors.append(f"{label}的取值不在可选范围内")
            else:
                result[key] = str(value)
        else:
            result[key] = str(value)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    return result


def form_for_snapshot(snapshot: Dict, node_key: str) -> Optional[Dict]:
    forms = snapshot.get("forms") or {}
    return forms.get(node_key) or forms.get("")


def form_snapshot(db: Session, process_id: int) -> Dict[str, Dict]:
    rows = db.scalars(
        select(FormDefinition).where(
            FormDefinition.process_id == process_id,
            FormDefinition.is_active.is_(True),
        )
    ).all()
    return {form.node_key: {"name": form.name, "fields": form.fields or []} for form in rows}


# ------------------------------------------------------------------ 规则


def normalize_conditions(conditions: List[Dict]) -> List[Dict]:
    if not isinstance(conditions, list):
        raise HTTPException(status_code=400, detail="conditions 必须是数组")
    out: List[Dict] = []
    for raw in conditions:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="每个条件必须是对象")
        field = str(raw.get("field") or "").strip()
        if not field:
            raise HTTPException(status_code=400, detail="条件缺少 field")
        op = str(raw.get("op") or "eq").strip()
        if op not in SUPPORTED_OPS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的规则运算符：{op}（支持 {', '.join(sorted(SUPPORTED_OPS))}）",
            )
        out.append({"field": field, "op": op, "value": raw.get("value")})
    return out


def rule_snapshot(db: Session, process_id: int) -> Dict[str, List[Dict]]:
    rows = db.scalars(
        select(ProcessRule)
        .where(ProcessRule.process_id == process_id, ProcessRule.is_active.is_(True))
        .order_by(ProcessRule.priority, ProcessRule.id)
    ).all()
    out: Dict[str, List[Dict]] = {}
    for rule in rows:
        out.setdefault(rule.node_key, []).append(
            {
                "name": rule.name,
                "conditions": rule.conditions or [],
                "target": rule.target_node_key,
                "priority": rule.priority,
            }
        )
    return out


def validate_rule_target(db: Session, process_id: int, node_key: str, target_node_key: str) -> None:
    nodes = {
        n.node_key
        for n in db.scalars(select(ProcessNode).where(ProcessNode.process_id == process_id)).all()
    }
    if node_key not in nodes:
        raise HTTPException(status_code=400, detail=f"节点 {node_key} 不存在于该流程")
    if target_node_key not in nodes:
        raise HTTPException(status_code=400, detail=f"目标节点 {target_node_key} 不存在于该流程")
    targets = {
        e.target_key
        for e in db.scalars(
            select(ProcessEdge).where(
                ProcessEdge.process_id == process_id,
                ProcessEdge.source_key == node_key,
            )
        ).all()
    }
    if target_node_key not in targets:
        raise HTTPException(
            status_code=400,
            detail=f"目标节点 {target_node_key} 不是节点 {node_key} 的出边目标",
        )


def _equals(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)
    if isinstance(actual, (int, float)) or isinstance(expected, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return str(actual) == str(expected)
    return actual == expected


def _match(condition: Dict, context: Dict) -> bool:
    actual = context.get(condition.get("field"))
    expected = condition.get("value")
    op = condition.get("op") or "eq"

    if op in NUMERIC_OPS:
        try:
            a, b = float(actual), float(expected)
        except (TypeError, ValueError):
            return False
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    if op == "eq":
        return _equals(actual, expected)
    if op == "ne":
        return not _equals(actual, expected)
    if op == "in":
        if isinstance(expected, list):
            return any(_equals(actual, item) for item in expected)
        return _equals(actual, expected)
    if op == "contains":
        if isinstance(actual, list):
            return any(_equals(item, expected) for item in actual)
        return actual is not None and str(expected) in str(actual)
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    return False


def evaluate_rules(rules: List[Dict], context: Dict) -> Optional[str]:
    """按优先级取第一个全部条件都命中的规则，返回目标节点 key。"""
    for rule in rules or []:
        conditions = rule.get("conditions") or []
        if all(_match(condition, context) for condition in conditions):
            return rule.get("target")
    return None
