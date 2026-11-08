"""来源画像：从证据主张推导方法、覆盖活动与观测时间。

资产包、诊断证据包、As-Is 来源画像共用这一份实现，避免三套统计口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessNode

DOCUMENTED_METHODS = {"DOCUMENTED", "STATED", "OBSERVED", "LOGGED"}


@dataclass
class ActivityCoverage:
    activity_id: int
    activity_code: Optional[str]
    activity_name: Optional[str]
    methods: List[str] = field(default_factory=list)
    claim_ids: List[int] = field(default_factory=list)
    covered: bool = False


@dataclass
class SourceProfile:
    claims_total: int
    claims_active: int
    methods: Dict[str, int]
    source_types: Dict[str, int]
    activity_count: int
    covered_activities: int
    observed_time_claims: int
    activities: List[ActivityCoverage]
    gaps: List[str]
    warnings: List[str]


def active_claims(claims):
    today = utcnow().date()
    return [
        claim
        for claim in claims.claims
        if claim.status != "EXPIRED" and not (claim.valid_to is not None and claim.valid_to < today)
    ]


def build(
    db: Session,
    *,
    model_version_id: Optional[int],
    claims,
    mapping,
) -> SourceProfile:
    """按当前模型版本聚合来源。未绑定版本的目标按 legacy 计入，并给出提示。"""
    activity_meta: Dict[int, tuple[Optional[str], Optional[str]]] = {}
    node_activity: Dict[str, int] = {}
    for node in mapping.nodes:
        for link in node.links:
            if link.relation in {"REALIZES", "PART_OF"}:
                activity_meta.setdefault(link.activity_id, (link.activity_code, link.activity_name))
                node_activity.setdefault(node.node_key, link.activity_id)
                break

    active = active_claims(claims)
    node_ids: Set[int] = set()
    for claim in active:
        for target in claim.targets:
            if target.target_type == "NODE":
                node_ids.add(target.target_id)
    node_by_id = (
        {
            row.id: row
            for row in db.scalars(select(ProcessNode).where(ProcessNode.id.in_(node_ids))).all()
        }
        if node_ids
        else {}
    )

    methods: Dict[str, int] = {}
    source_types: Dict[str, int] = {}
    activity_methods: Dict[int, Set[str]] = {aid: set() for aid in activity_meta}
    activity_claims: Dict[int, Set[int]] = {aid: set() for aid in activity_meta}
    observed_claim_ids: Set[int] = set()
    unbound = 0

    for claim in active:
        relevant = False
        for target in claim.targets:
            if (
                target.model_version_id is not None
                and model_version_id is not None
                and target.model_version_id != model_version_id
            ):
                continue
            if target.target_type == "PROCESS":
                if target.target_id != mapping.process_id:
                    continue
                if target.model_version_id is None:
                    unbound += 1
                relevant = True
                if (
                    claim.method in {"OBSERVED", "LOGGED"}
                    and target.field in {"lead_time", "cycle_time"}
                    and (claim.samples or 0) >= 1
                ):
                    observed_claim_ids.add(claim.id)
                continue
            if target.target_type in {"ACTIVITY", "TIME_FIELD"}:
                activity_id = target.target_id
            elif target.target_type == "NODE":
                node = node_by_id.get(target.target_id)
                activity_id = node_activity.get(node.node_key) if node else None
            else:
                continue
            if activity_id is None or activity_id not in activity_meta:
                continue
            if target.model_version_id is None:
                unbound += 1
            relevant = True
            activity_methods[activity_id].add(claim.method)
            activity_claims[activity_id].add(claim.id)
            if (
                claim.method in {"OBSERVED", "LOGGED"}
                and target.target_type == "TIME_FIELD"
                and (claim.samples or 0) >= 1
            ):
                observed_claim_ids.add(claim.id)
        if relevant:
            methods[claim.method] = methods.get(claim.method, 0) + 1
            source_types[claim.source_type] = source_types.get(claim.source_type, 0) + 1

    activities: List[ActivityCoverage] = []
    gaps: List[str] = []
    covered = 0
    for activity_id, (code, name) in sorted(
        activity_meta.items(), key=lambda item: item[1][0] or ""
    ):
        claim_methods = sorted(activity_methods.get(activity_id, set()))
        is_covered = any(method in DOCUMENTED_METHODS for method in claim_methods)
        if is_covered:
            covered += 1
        else:
            gaps.append(f"{code or ''} {name or ''}".strip())
        activities.append(
            ActivityCoverage(
                activity_id=activity_id,
                activity_code=code,
                activity_name=name,
                methods=claim_methods,
                claim_ids=sorted(activity_claims.get(activity_id, set())),
                covered=is_covered,
            )
        )

    warnings: List[str] = []
    if unbound:
        warnings.append(f"{unbound} 个证据目标未绑定模型版本；模型升版后需重新确认。")
    if activity_meta and covered < len(activity_meta):
        warnings.append(f"来源只覆盖 {covered}/{len(activity_meta)} 个活动。")

    return SourceProfile(
        claims_total=len(claims.claims),
        claims_active=len(active),
        methods=methods,
        source_types=source_types,
        activity_count=len(activity_meta),
        covered_activities=covered,
        observed_time_claims=len(observed_claim_ids),
        activities=activities,
        gaps=gaps,
        warnings=warnings,
    )
