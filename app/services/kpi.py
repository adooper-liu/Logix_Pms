"""KPI 定义卡规则：口径完整性、阈值语义与活动绑定。

这些规则放在服务层，API 只管出入参与审计；这样定义卡的校验可以被
种子、导入脚本和后续的 KPI 治理扫描复用。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import KpiDirection
from app.models.monitor import KpiDefinition
from app.models.process import ProcessArch
from app.services import process_scope


class KpiDefinitionError(ValueError):
    """KPI 定义卡规则拒绝；API 层转成 400/409。"""


STATUS_LABELS = {
    "RED": "红",
    "YELLOW": "黄",
    "GREEN": "绿",
    "GRAY": "灰（未取数）",
}


def validate_definition(
    formula: Optional[str], numerator: Optional[str], denominator: Optional[str]
) -> None:
    """新建 KPI 必须写清口径：公式，或分子 + 分母。"""
    if (formula or "").strip():
        return
    if (numerator or "").strip() and (denominator or "").strip():
        return
    raise KpiDefinitionError("请填写计算公式，或同时填写分子与分母")


def validate_dates(valid_from: Optional[date], valid_to: Optional[date]) -> None:
    if valid_from and valid_to and valid_from > valid_to:
        raise KpiDefinitionError("生效日期不能晚于失效日期")


def validate_thresholds(
    direction: str,
    red: Optional[float],
    yellow: Optional[float],
    green: Optional[float],
) -> None:
    """红/黄/绿三条线必须同进同退，且顺序与指标方向一致。

    HIGHER_BETTER：red ≤ yellow ≤ green（越低越差）；
    LOWER_BETTER ：red ≥ yellow ≥ green（越高越差）。
    """
    values = [red, yellow, green]
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise KpiDefinitionError("红/黄/绿阈值必须同时填写或同时留空")
    if direction == KpiDirection.HIGHER_BETTER.value:
        if not (red <= yellow <= green):
            raise KpiDefinitionError("越大越好的指标必须满足：红线 ≤ 黄线 ≤ 绿线")
    elif not (red >= yellow >= green):
        raise KpiDefinitionError("越小越好的指标必须满足：红线 ≥ 黄线 ≥ 绿线")


def status_for(
    value: Optional[float],
    direction: str,
    red: Optional[float],
    yellow: Optional[float],
    green: Optional[float],
) -> str:
    """按定义卡阈值判定 RED / YELLOW / GREEN。

    没有数据点或阈值未填全时返回 GRAY（未取数），而不是空值：
    灰色本身就是“等待上游/缺数据”的可视信号。
    """
    if value is None or any(threshold is None for threshold in (red, yellow, green)):
        return "GRAY"
    if direction == KpiDirection.HIGHER_BETTER.value:
        if value < red:
            return "RED"
        if value >= green:
            return "GREEN"
        return "YELLOW"
    if value > red:
        return "RED"
    if value <= green:
        return "GREEN"
    return "YELLOW"


def validate_activity(
    db: Session,
    process_id: Optional[int],
    activity_id: Optional[int],
) -> None:
    """活动必须是 L4，且同时指定流程时必须在流程子树内。"""
    if activity_id is None:
        return
    activity = db.get(ProcessArch, activity_id)
    if activity is None:
        raise KpiDefinitionError(f"活动 {activity_id} 不存在")
    if activity.level != 4:
        raise KpiDefinitionError("activity_id 必须指向 L4 活动")
    if process_id is not None and process_id not in process_scope.ancestor_ids(db, activity_id):
        raise KpiDefinitionError("所选活动不属于该流程")


def ensure_formula_consistency(
    db: Session,
    *,
    name: str,
    process_id: Optional[int],
    formula: Optional[str],
    exclude_id: Optional[int] = None,
) -> None:
    """同一流程下，同名 KPI 不允许出现两种公式。

    这是“同名异义”的硬门禁：只要两条定义都写了公式且不同，就拒绝。
    没有写公式的旧数据不参与判断，避免历史数据阻塞维护。
    """
    normalized = (name or "").strip()
    incoming = (formula or "").strip()
    if not normalized or not incoming:
        return
    rows = db.scalars(
        select(KpiDefinition).where(
            KpiDefinition.process_id == process_id,
            KpiDefinition.name == normalized,
        )
    ).all()
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        existing = (row.formula or "").strip()
        if existing and existing != incoming:
            raise KpiDefinitionError(
                f"同名 KPI「{normalized}」已存在不同公式（{row.code}）；"
                "请改用不同的指标名，或统一口径后再保存"
            )
