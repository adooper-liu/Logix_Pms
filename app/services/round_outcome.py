"""四结论引用原GateAttestation，绝不推进项目/流程阶段。"""

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select

from app.models.improvement_round import ProcessImprovementRound
from app.models.maturity import GateAttestation
from app.models.project import Project
from app.services import execution_readiness, improvement_round, org_access, process_model


def create(db, user, data):
    row = db.get(ProcessImprovementRound, data.get("round_id")) if data.get("round_id") else None
    if row is None:
        raise HTTPException(404, "本轮不存在")
    improvement_round.require(db, user, row.process_id, row.id)
    process = execution_readiness.require_process(db, row.process_id)
    process_model.lock_process(db, process)
    db.refresh(row)
    project = db.get(Project, data["project_id"])
    if project is None or row.project_id != project.id or project.process_id != row.process_id:
        raise HTTPException(400, "核验项目与本轮不一致")
    org_access.ensure_visible(db, user, project.org_unit_id)
    if data.get("expected_revision") != row.revision:
        raise HTTPException(409, "本轮依据已变化，请刷新")
    acceptance = row.acceptance_snapshot or {}
    if (
        acceptance.get("reviewer_user_id") != user.id
        or row.created_by_id == user.id
        or row.acceptance_locked_by_id == user.id
    ):
        raise HTTPException(403, "仅事先指定且非依据编制者本人可核验，不允许代签")
    purpose = data["purpose"]
    if not data["evidence_url"].strip():
        raise HTTPException(400, "请引用本次有权核验依据")
    if data["conclusion"] == "PASS":
        if (
            not row.baseline_confirmed_at
            or not row.asis_model_version_id
            or not row.metric_contracts
            or not row.baseline_samples
        ):
            raise HTTPException(400, "本轮资料/模型/口径/前侧样本尚未固定")
        if purpose != "DATA_READY":
            ready = execution_readiness.get(db, user, row.process_id)
            if (
                not row.released_model_version_id
                or ready["published_model_version_id"] != row.released_model_version_id
                or not ready["confirmed"]
            ):
                raise HTTPException(400, "本轮发布或当前上线准备尚未有效确认")
        if purpose in ("RUN_EFFECTIVE", "IMPROVEMENT_MET"):
            if not row.acceptance_locked_at or not row.after_samples:
                raise HTTPException(400, "缺事先验收约定或正式后侧样本")
            if any(s.get("provenance", {}).get("quality") != "VALID" for s in row.after_samples):
                raise HTTPException(400, "后侧样本仍待来源/质量核验")
        if purpose == "IMPROVEMENT_MET":
            if any(
                (s.get("provenance") or {}).get("quality") != "VALID" for s in row.baseline_samples
            ):
                raise HTTPException(400, "前侧样本仍未核正式来源，不能签改善达标")
            if any(
                s.get("contract_hash") not in {c["hash"] for c in row.metric_contracts}
                for s in row.baseline_samples + row.after_samples
            ):
                raise HTTPException(400, "前后口径不可比")
    snapshot = {
        "round_revision": row.revision,
        "process_id": row.process_id,
        "project_id": row.project_id,
        "asis_model_version_id": row.asis_model_version_id,
        "released_model_version_id": row.released_model_version_id,
        "metric_contracts": deepcopy(row.metric_contracts),
        "baseline_samples": deepcopy(row.baseline_samples),
        "after_samples": deepcopy(row.after_samples),
        "acceptance": deepcopy(row.acceptance_snapshot),
        "readiness_fingerprint": execution_readiness.get(db, user, row.process_id)["fingerprint"]
        if purpose != "DATA_READY"
        else None,
    }
    result = GateAttestation(
        project_id=project.id,
        stage_no=project.current_stage,
        purpose=purpose,
        round_id=row.id,
        evidence_snapshot=snapshot,
        gate_code=purpose,
        evidence_url=data["evidence_url"],
        conclusion=data["conclusion"],
        signed_by_user_id=user.id,
        note=data.get("note"),
        exit_criteria=data.get("exit_criteria"),
    )
    db.add(result)
    db.flush()
    return result


def projections(db, row):
    latest = {}
    for gate in db.scalars(
        select(GateAttestation)
        .where(GateAttestation.round_id == row.id)
        .order_by(GateAttestation.id)
    ).all():
        latest[gate.purpose] = gate
    result = []
    for key, label in improvement_round.CONCLUSIONS.items():
        gate = latest.get(key)
        current = bool(
            gate and (gate.evidence_snapshot or {}).get("round_revision") == row.revision
        )
        if current and key == "GO_LIVE_READY":
            process = execution_readiness.require_process(db, row.process_id)
            _, config, basis, *_ = execution_readiness.basis(db, process)
            decision = ((config.readiness or {}).get("confirmation") if config else None) or {}
            current = (
                (gate.evidence_snapshot or {}).get("readiness_fingerprint")
                == improvement_round.digest(basis)
                and decision.get("decision") == "ACCEPT"
                and decision.get("fingerprint") == improvement_round.digest(basis)
            )
        result.append(
            {
                "key": key,
                "label": label,
                "state": "CONFIRMED" if current and gate.conclusion == "PASS" else "PENDING",
                "state_label": "原有权核验已确认"
                if current and gate.conclusion == "PASS"
                else "原决定待复核"
                if gate
                else "待原业务核验",
                "decision_ref": gate.id if gate else None,
                "reason": "原核验仅针对当时固定依据，不等于项目阶段推进",
            }
        )
    return result
