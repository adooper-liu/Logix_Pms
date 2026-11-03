"""唯一流程目录的业务分类；继承是读取投影，不复制下级保存值。"""

from typing import Optional

from app.models.process import ProcessArch

TYPE_LABELS = {"CORE": "核心流程", "SUPPORT": "支持流程", "MANAGEMENT": "管理流程"}
FILTERS = set(TYPE_LABELS) | {"UNCLASSIFIED"}


def meta() -> dict:
    return {
        "process_types": TYPE_LABELS,
        "unknown_label": "未明确",
        "inherit_label": "按上级继承",
        "blocked_label": "暂不分类（不继承）",
        "context_label": "路径上下文",
        "inherited_label": "继承自",
        "override_label": "跨类型例外",
    }


def resolve_all(rows: list[ProcessArch]) -> dict[int, dict]:
    by_id = {row.id: row for row in rows}

    def source(start):
        seen = set()
        current = start
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.process_type in TYPE_LABELS:
                return current
            if not current.classification_inherit:
                return None
            current = by_id.get(current.parent_id)
        return None

    result = {}
    for row in rows:
        origin = source(row)
        ancestor = source(by_id.get(row.parent_id))
        kind = origin.process_type if origin else None
        result[row.id] = {
            "effective_process_type": kind,
            "process_type_label": TYPE_LABELS.get(kind, "未明确"),
            "classification_source_id": origin.id if origin else None,
            "classification_source_code": origin.code if origin else None,
            "classification_is_inherited": origin is not None and origin.id != row.id,
            "classification_is_override": row.process_type in TYPE_LABELS
            and ancestor is not None
            and row.process_type != ancestor.process_type,
            "classification_matches_filter": True,
        }
    return result


def matches(resolved: dict, process_type: Optional[str]) -> bool:
    if process_type is None:
        return True
    if process_type == "UNCLASSIFIED":
        return resolved["effective_process_type"] is None
    return resolved["effective_process_type"] == process_type
