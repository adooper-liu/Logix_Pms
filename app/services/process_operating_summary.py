"""Sample-facing aggregation for the generic process operating contract."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.process import ProcessArch
from app.models.process_operating import ProcessGateAssessment, ProcessOperatingCycle
from app.services.process_operating import can_enter_pilot

GATE_KEYS = tuple(f"GATE_{number}" for number in range(1, 13))


def sample_operating_summary(db: Session, process_id: int) -> dict:
    """Return a generic, evidence-aware summary for any L3 process.

    This is intentionally a read-side sample integration. It does not create a
    cycle or mark a gate complete; callers must create explicit cycle/evidence
    records for business decisions.
    """
    process = db.get(ProcessArch, process_id)
    if process is None or process.level != 3:
        raise ValueError("经营对象必须是 L3 流程")
    cycle = db.scalar(
        select(ProcessOperatingCycle)
        .where(
            ProcessOperatingCycle.process_id == process_id,
            ProcessOperatingCycle.status == "ACTIVE",
        )
        .order_by(ProcessOperatingCycle.id.desc())
    )
    if cycle is None:
        return {
            "process_id": process_id,
            "cycle_id": None,
            "gates": [],
            "blocking_gates": ["GATE_1"],
            "next_action": "创建流程经营周期并确认目标与结果",
            "can_enter_pilot": False,
            "sample_only": True,
        }
    assessments = {
        row.gate_key: row
        for row in db.scalars(
            select(ProcessGateAssessment).where(
                ProcessGateAssessment.cycle_id == cycle.id,
                ProcessGateAssessment.is_current.is_(True),
            )
        ).all()
    }
    gates = [
        {
            "key": key,
            "status": assessments[key].status if key in assessments else "NOT_STARTED",
            "applicability": assessments[key].applicability if key in assessments else "APPLICABLE",
            "rigor": assessments[key].rigor if key in assessments else "STANDARD",
        }
        for key in GATE_KEYS
    ]
    status_map = {row["key"]: row["status"] for row in gates}
    blocking = [
        row["key"]
        for row in gates[:10]
        if row["applicability"] != "NOT_APPLICABLE"
        and row["status"] not in {"PASS", "CONDITIONAL"}
    ]
    return {
        "process_id": process_id,
        "cycle_id": cycle.id,
        "gates": gates,
        "blocking_gates": blocking,
        "next_action": (
            f"补齐 {blocking[0]} 的事实与证据" if blocking else "可以准备受控试点"
        ),
        "can_enter_pilot": can_enter_pilot(status_map),
        "sample_only": True,
    }
