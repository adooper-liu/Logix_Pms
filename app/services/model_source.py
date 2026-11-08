"""As-Is 来源画像：当前模型版本的方法覆盖、活动缺口与用途就绪度。

只读；来源登记仍走证据主张写入，不另建一套来源表。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.process import ProcessArch
from app.schemas.diagnosis import DiagnosisUseOut
from app.schemas.model_source import ActivitySourceCoverageOut, ModelSourceProfileOut
from app.services import asset_graph as asset_service
from app.services import source_profile as source_profile_service

HARD_BLOCKERS = {"MODEL_NOT_VERSIONED", "NODE_ACTIVITY_UNMAPPED"}


def profile(db: Session, process: ProcessArch) -> ModelSourceProfileOut:
    base = asset_service.readiness(db, process)
    claims = asset_service.evidence_claims(db, process)
    mapping = asset_service.architecture_map(db, process)
    data = source_profile_service.build(
        db,
        model_version_id=base.model_version_id,
        claims=claims,
        mapping=mapping,
    )
    hard = [row for row in base.blockers if row.code in HARD_BLOCKERS]
    conflicts = list(claims.conflicts)
    expired = base.metrics.get("claims_expired", 0)
    quantitative_ready = data.observed_time_claims > 0 and not conflicts and expired == 0
    uses = [
        DiagnosisUseOut(
            key="scope",
            label="范围 / 设计讨论",
            ready=not hard,
            detail="有已发布模型与活动映射" if not hard else "先补模型版本/活动映射",
        ),
        DiagnosisUseOut(
            key="quantitative",
            label="定量诊断（PCE / 瓶颈）",
            ready=quantitative_ready,
            detail="有观测/日志时间证据"
            if quantitative_ready
            else "需要观测/日志时间证据；制度/访谈只能说明应有流程",
        ),
        DiagnosisUseOut(
            key="root_cause",
            label="根因与改善收益",
            ready=quantitative_ready,
            detail="定量证据 + 无未裁决冲突" if quantitative_ready else "先补定量证据并裁决冲突",
        ),
    ]

    warnings = list(data.warnings)
    if not hard:
        warnings.append("模型指标是估算；来源画像只说明证据覆盖，不等于实测结论。")

    if hard:
        next_action = "先发布模型版本并完成活动映射。"
    elif not data.observed_time_claims:
        next_action = "给关键活动登记现场观测或系统日志时间；制度/访谈不能替代实测。"
    elif conflicts:
        next_action = "裁决证据冲突后再做定量结论。"
    elif expired:
        next_action = "续证或重新采集过期证据。"
    else:
        next_action = "来源画像已可支撑定量诊断。"

    return ModelSourceProfileOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=base.model_version_id,
        model_version=base.model_version,
        model_status=base.model_status,
        versioned=base.versioned,
        claims_total=data.claims_total,
        claims_active=data.claims_active,
        methods=data.methods,
        source_types=data.source_types,
        activity_count=data.activity_count,
        covered_activities=data.covered_activities,
        observed_time_claims=data.observed_time_claims,
        activities=[ActivitySourceCoverageOut(**row.__dict__) for row in data.activities],
        gaps=data.gaps,
        uses=uses,
        warnings=warnings,
        next_action=next_action,
    )
