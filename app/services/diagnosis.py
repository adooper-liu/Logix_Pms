"""诊断证据包：已发布模型 + 证据主张 → 可复核的分析资产。

边界：

- 数字只从 `designer.analyze` 取，标为「模型估算」，不冒充实测。
- 来源画像从证据账本推导，不另建模型来源表。
- 没有观测/日志时允许生成草稿，但明确标注「只能做范围/设计，不能做定量结论」。
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import timezone
from html import escape
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessArch, ProcessEdge, ProcessNode
from app.models.process_document import (
    CompiledAssetComponent,
    ProcessDocument,
    ProcessDocumentVersion,
)
from app.models.tool_sheet import ToolSheet
from app.models.user import User
from app.schemas.asset_graph import AssetPackageOut, ReadinessBlockerOut
from app.schemas.diagnosis import (
    DiagnosisInputOut,
    DiagnosisPreviewOut,
    DiagnosisR1PreviewOut,
    DiagnosisR1ReadinessOut,
    DiagnosisReadinessOut,
    DiagnosisSourceProfileOut,
    DiagnosisUseOut,
)
from app.services import asset_graph as asset_service
from app.services import audit, designer
from app.services import process_document as document_service
from app.services import source_profile as source_profile_service
from app.services import storage as storage_service
from app.services.asset_package import package_out

RULE_VERSION = "diagnosis-compile-v1"
R1_RULE_VERSION = "diagnosis-r1-v1"
DOC_PREFIX = "DG-"
HARD_BLOCKERS = {"MODEL_NOT_VERSIONED", "NODE_ACTIVITY_UNMAPPED"}
METHOD_LABELS = {
    "OBSERVED": "现场观测",
    "LOGGED": "系统日志",
    "DOCUMENTED": "制度文本",
    "STATED": "访谈陈述",
    "ESTIMATED": "估算",
    "UNKNOWN": "来源待核",
}


def _e(value) -> str:
    return escape(str(value)) if value is not None else ""


def _hash_json(value) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _analysis(db: Session, process: ProcessArch):
    nodes = list(
        db.scalars(
            select(ProcessNode)
            .where(ProcessNode.process_id == process.id)
            .order_by(ProcessNode.sequence_order, ProcessNode.id)
        ).all()
    )
    edges = list(
        db.scalars(
            select(ProcessEdge).where(ProcessEdge.process_id == process.id).order_by(ProcessEdge.id)
        ).all()
    )
    return designer.analyze(process.id, nodes, edges)


def readiness(db: Session, process: ProcessArch) -> DiagnosisReadinessOut:
    base = asset_service.readiness(db, process)
    claims = asset_service.evidence_claims(db, process)
    analysis = _analysis(db, process)
    mapping = asset_service.architecture_map(db, process)
    profile = source_profile_service.build(
        db,
        model_version_id=base.model_version_id,
        claims=claims,
        mapping=mapping,
    )
    source_out = DiagnosisSourceProfileOut(
        claims_total=profile.claims_total,
        claims_active=profile.claims_active,
        methods=profile.methods,
        activity_count=profile.activity_count,
        covered_activities=profile.covered_activities,
        observed_time_claims=profile.observed_time_claims,
    )
    hard = [row for row in base.blockers if row.code in HARD_BLOCKERS]
    conflicts = list(claims.conflicts)
    expired = base.metrics.get("claims_expired", 0)
    quantitative_ready = profile.observed_time_claims > 0 and not conflicts and expired == 0
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
            else "需要观测或日志时间证据，模型估算不能当实测",
        ),
        DiagnosisUseOut(
            key="root_cause",
            label="根因与改善收益",
            ready=quantitative_ready,
            detail="定量证据 + 无未裁决冲突" if quantitative_ready else "先补定量证据并裁决冲突",
        ),
    ]

    blockers = list(hard)
    if not profile.observed_time_claims:
        blockers.append(
            ReadinessBlockerOut(
                code="OBSERVED_TIME_MISSING",
                message="还没有观测/日志时间主张；模型 PCE 只能当估算。",
            )
        )
    if conflicts:
        blockers.append(
            ReadinessBlockerOut(
                code="EVIDENCE_CONFLICT",
                message="存在未裁决证据冲突；定量结论需要先裁决。",
                targets=conflicts,
            )
        )
    if expired:
        blockers.append(
            ReadinessBlockerOut(
                code="EVIDENCE_EXPIRED",
                message=f"{expired} 条证据已过期；请续证或重新采集。",
            )
        )

    warnings = ["模型指标是估算，不是现场实测；不能直接用于作业绩收益承诺。"]
    if profile.covered_activities < profile.activity_count:
        warnings.append(
            f"证据只覆盖 {profile.covered_activities}/{profile.activity_count} 个活动。"
        )
    if analysis.metrics.has_branch_or_loop:
        warnings.append("模型存在分支/回路，期望值按概率计算；模型本身未确认时结论需复核。")

    if hard:
        next_action = "先发布模型版本并完成活动映射。"
    elif not profile.observed_time_claims:
        next_action = "补现场观测或系统日志时间，优先瓶颈候选节点。"
    elif conflicts:
        next_action = "裁决证据冲突后再做定量结论。"
    elif expired:
        next_action = "续证或重新采集过期证据。"
    else:
        next_action = "可以生成诊断证据包草稿。"

    return DiagnosisReadinessOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=base.model_version_id,
        model_version=base.model_version,
        model_status=base.model_status,
        versioned=base.versioned,
        metrics=analysis.metrics.model_dump(),
        source_profile=source_out,
        uses=uses,
        blockers=blockers,
        warnings=warnings,
        can_compile=not hard,
        next_action=next_action,
    )


def _r1_inputs(db: Session, process: ProcessArch, claims, base: DiagnosisReadinessOut):
    active = source_profile_service.active_claims(claims)
    sheet_ids = {
        claim.source_id for claim in active if claim.source_type == "TOOL_SHEET" and claim.source_id
    }
    sheets = (
        {
            row.id: row
            for row in db.scalars(select(ToolSheet).where(ToolSheet.id.in_(sheet_ids))).all()
        }
        if sheet_ids
        else {}
    )
    codes = {sheets[claim.source_id].tool_code for claim in active if claim.source_id in sheets}
    sipoc = "SIPOC" in codes
    vsm = "VSM" in codes or base.source_profile.observed_time_claims > 0
    root = bool(codes & {"FIVE-WHY", "FISHBONE", "PARETO"})
    queue = "QUEUE-MODEL" in codes
    inputs = [
        DiagnosisInputOut(
            key="2.1",
            label="SIPOC 范围与边界",
            required=True,
            ready=sipoc,
            detail="用于确定端到端范围与客户结果" if sipoc else "缺 SIPOC 方法记录",
        ),
        DiagnosisInputOut(
            key="2.2",
            label="VSM 与观测时间",
            required=True,
            ready=vsm,
            detail="模型估算 + 观测/日志时间" if vsm else "缺 VSM 或观测/日志时间",
        ),
        DiagnosisInputOut(
            key="2.3",
            label="5Why / 帕累托根因",
            required=True,
            ready=root,
            detail="根因假设与反证" if root else "缺 5Why / 鱼骨 / 帕累托记录",
        ),
        DiagnosisInputOut(
            key="2.4",
            label="瓶颈 / 队列",
            required=False,
            ready=queue,
            detail="可选；缺省用模型瓶颈候选",
        ),
    ]
    missing = [row.label for row in inputs if row.required and not row.ready]
    conflicting = any(
        row.code in {"EVIDENCE_CONFLICT", "EVIDENCE_EXPIRED"} for row in base.blockers
    )
    can_submit = base.can_compile and not missing and not conflicting
    return inputs, missing, can_submit


def r1_readiness(db: Session, process: ProcessArch) -> DiagnosisR1ReadinessOut:
    base = readiness(db, process)
    claims = asset_service.evidence_claims(db, process)
    inputs, missing, can_submit = _r1_inputs(db, process, claims, base)
    if not base.can_compile:
        next_action = base.next_action
    elif missing:
        next_action = "补 R1 必填输入：" + "、".join(missing)
    elif not can_submit:
        next_action = "裁决冲突或续证后再提交评审。"
    else:
        next_action = "R1 必填输入齐，可生成并提交评审。"
    data = base.model_dump()
    data["next_action"] = next_action
    return DiagnosisR1ReadinessOut(
        **data,
        inputs=inputs,
        missing_inputs=missing,
        can_compile_draft=base.can_compile,
        can_submit_review=can_submit,
    )


def _minutes(value: float) -> str:
    return f"{value:.0f}"


def _days(value: float) -> str:
    return f"{value / 480:.1f}"


def _render_html(
    process: ProcessArch,
    model_version: int,
    analysis,
    profile: DiagnosisSourceProfileOut,
    uses: List[DiagnosisUseOut],
    claims,
    blockers: List[ReadinessBlockerOut],
    warnings: List[str],
    inputs: Optional[List[DiagnosisInputOut]] = None,
    can_submit_review: bool = True,
) -> str:
    metrics = analysis.metrics
    active = source_profile_service.active_claims(claims)
    method_rows = (
        "".join(
            f"<tr><td>{_e(METHOD_LABELS.get(code, code))}</td><td>{count}</td></tr>"
            for code, count in sorted(profile.methods.items())
        )
        or "<tr><td colspan='2'>还没有证据主张</td></tr>"
    )
    use_rows = "".join(
        f"<tr><td>{_e(row.label)}</td>"
        f"<td>{'可用' if row.ready else '不可用'}</td>"
        f"<td>{_e(row.detail)}</td></tr>"
        for row in uses
    )
    node_rows = "".join(
        f"<tr><td>{_e(node.name)}</td><td>{_e(node.node_type)}</td>"
        f"<td class='num'>{_minutes(node.lead_minutes)}</td>"
        f"<td class='num'>{_minutes(node.value_minutes)}</td>"
        f"<td class='num'>{node.wait_share:.0%}</td>"
        f"<td class='num'>{node.visit_count:.2f}</td>"
        f"<td class='num'>{_minutes(node.weighted_minutes)}</td>"
        f"<td>{'候选' if node.is_bottleneck else '—'}</td></tr>"
        for node in analysis.nodes
    )
    claim_rows = (
        "".join(
            f"<tr><td>{_e(claim.claim)}</td>"
            f"<td>{_e(METHOD_LABELS.get(claim.method, claim.method))}</td>"
            f"<td class='num'>{_e(claim.samples if claim.samples is not None else '—')}</td>"
            f"<td>{_e(claim.status)}</td>"
            f"<td>{_e(claim.conflict_group or '—')}</td></tr>"
            for claim in active
        )
        or "<tr><td colspan='5'>还没有有效证据主张</td></tr>"
    )
    suggestion_rows = "".join(
        f"<li><b>{_e(row.title)}</b>（{_e(row.severity)}）"
        f"<div class='sub'>{_e(row.detail)}</div></li>"
        for row in analysis.suggestions
    )
    blocker_items = (
        "".join(
            f"<li><b>{_e(row.message)}</b>"
            + (f"<div class='sub'>{_e('、'.join(row.targets))}</div>" if row.targets else "")
            + "</li>"
            for row in blockers
        )
        or "<li>无</li>"
    )
    warning_items = "".join(f"<li>{_e(item)}</li>" for item in warnings)
    conflict_items = "".join(f"<li>{_e(item)}</li>" for item in claims.conflicts) or "<li>无</li>"
    unknown_items = (
        "".join(f"<li>{_e(item)}</li>" for item in claims.unknown_targets) or "<li>无</li>"
    )
    input_section = ""
    if inputs is not None:
        input_rows = "".join(
            f"<tr><td>{_e(row.key)}</td><td>{_e(row.label)}</td>"
            f"<td>{'必填' if row.required else '可选'}</td>"
            f"<td>{'齐' if row.ready else '缺'}</td>"
            f"<td>{_e(row.detail)}</td></tr>"
            for row in inputs
        )
        state = (
            "必填输入齐，可提交评审"
            if can_submit_review
            else "草稿可生成；必填输入未齐，不能提交评审"
        )
        input_section = f"""
  <h2>0. R1 输入清单</h2>
  <table>
    <thead><tr><th>步骤</th><th>输入</th><th>要求</th><th>状态</th><th>说明</th></tr></thead>
    <tbody>{input_rows}</tbody>
  </table>
  <p class="sub">{_e(state)}</p>"""

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{_e(process.code)} 诊断证据包</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font:12px/1.55 "Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         color:#111; margin:0; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:14px; margin:18px 0 7px; border-bottom:1px solid #999;
        padding-bottom:4px; }}
  .meta {{ color:#444; font-size:11px; margin-bottom:10px; }}
  .flag {{ border:1px solid #b47405; background:#fef5e3; color:#7a4b00;
           padding:6px 9px; border-radius:6px; font-size:11.5px; margin:8px 0; }}
  .sub {{ color:#666; font-size:10.5px; }}
  .num {{ text-align:right; }}
  table {{ width:100%; border-collapse:collapse; margin:6px 0 8px; }}
  th,td {{ border:1px solid #aaa; padding:4px 6px; text-align:left;
           vertical-align:top; }}
  th {{ background:#eee; font-size:10.5px; }}
  ul {{ margin:4px 0 0 18px; padding:0; }}
  li {{ margin-bottom:3px; }}
  .kpi {{ display:flex; gap:14px; flex-wrap:wrap; margin:8px 0 12px; }}
  .kpi div {{ border:1px solid #ccc; border-radius:6px; padding:6px 10px;
              min-width:110px; }}
  .kpi b {{ display:block; font-size:17px; }}
  @media print {{ h2 {{ page-break-after:avoid; }} tr {{ page-break-inside:avoid; }} }}
</style></head><body>
  <h1>{_e(process.name)} · 诊断证据包</h1>
  <div class="meta">
    {_e(process.code)} · Owner {_e(process.owner or "未指定")}
    · 模型 v{_e(model_version)}
    · 生成于 {_e(utcnow().strftime("%Y-%m-%d %H:%M UTC"))}
    · 规则 {_e(RULE_VERSION)}
  </div>
  <div class="flag">模型指标是估算，不是现场实测；定量结论必须同时看来源画像与证据主张。</div>
  {input_section}

  <h2>1. 来源画像与用途就绪度</h2>
  <table>
    <thead><tr><th>用途</th><th>是否可用</th><th>说明</th></tr></thead>
    <tbody>{use_rows}</tbody>
  </table>
  <table>
    <thead><tr><th>来源方法</th><th>有效主张数</th></tr></thead>
    <tbody>{method_rows}</tbody>
  </table>
  <p class="sub">覆盖活动 {profile.covered_activities}/{profile.activity_count}
    · 观测/日志时间主张 {profile.observed_time_claims} 条</p>

  <h2>2. 模型估算指标</h2>
  <div class="kpi">
    <div><span>PCE</span><b>{metrics.pce:.1%}</b></div>
    <div><span>期望周期</span><b>{_minutes(metrics.lead_time_minutes)} 分</b></div>
    <div><span>折合</span><b>{_days(metrics.lead_time_minutes)} 人天</b></div>
    <div><span>等待占比</span><b>{metrics.wait_ratio:.0%}</b></div>
    <div><span>返工损失</span><b>{_minutes(metrics.rework_loss_minutes)} 分</b></div>
    <div><span>单次成本</span><b>{metrics.unit_cost:.2f}</b></div>
  </div>
  <table>
    <thead><tr><th>节点</th><th>类型</th><th>单次时长(分)</th><th>增值(分)</th>
      <th>等待占比</th><th>期望次数</th><th>周期贡献(分)</th><th>瓶颈</th></tr></thead>
    <tbody>{node_rows or '<tr><td colspan="8">没有节点</td></tr>'}</tbody>
  </table>
  <p class="sub">瓶颈列是模型候选，不是已确认的运行瓶颈；需用到达负荷与实际队列证据复核。</p>

  <h2>3. 有效证据主张</h2>
  <table>
    <thead><tr><th>主张</th><th>方法</th><th>样本</th><th>状态</th><th>冲突组</th></tr></thead>
    <tbody>{claim_rows}</tbody>
  </table>
  <h3>未裁决冲突</h3><ul>{conflict_items}</ul>
  <h3>未被主张覆盖</h3><ul>{unknown_items}</ul>

  <h2>4. 模型提示的候选问题</h2>
  <ul>{suggestion_rows or "<li>没有提示</li>"}</ul>

  <h2>5. 阻断与提示</h2>
  <h3>阻断</h3><ul>{blocker_items}</ul>
  <h3>提示</h3><ul>{warning_items}</ul>

  <h2>6. 下一步</h2>
  <p>如果「定量诊断」不可用，先补现场观测/系统日志；如果存在冲突，先裁决。诊断证据包不是设计或上线批准。</p>
</body></html>"""


def _collect(db: Session, process: ProcessArch) -> dict:
    base = readiness(db, process)
    claims = asset_service.evidence_claims(db, process)
    analysis = _analysis(db, process)
    html = _render_html(
        process,
        base.model_version,
        analysis,
        base.source_profile,
        base.uses,
        claims,
        base.blockers,
        base.warnings,
    )
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    manifest = {
        "kind": "DIAGNOSIS",
        "rule_version": RULE_VERSION,
        "process_id": process.id,
        "process_code": process.code,
        "process_name": process.name,
        "model_version_id": base.model_version_id,
        "model_version": base.model_version,
        "model_status": base.model_status,
        "generated_at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "metrics": base.metrics,
        "source_profile": base.source_profile.model_dump(),
        "uses": [row.model_dump() for row in base.uses],
        "inputs": {
            "model_version_id": base.model_version_id,
            "claims": [row.model_dump(mode="json") for row in claims.claims],
        },
        "blockers": [row.model_dump() for row in base.blockers],
        "warnings": base.warnings,
        "content_hash": content_hash,
    }
    return {
        "html": html,
        "manifest": manifest,
        "content_hash": content_hash,
        "readiness": base,
        "analysis": analysis,
        "claims": claims,
    }


def preview(db: Session, process: ProcessArch) -> DiagnosisPreviewOut:
    data = _collect(db, process)
    base = data["readiness"]
    return DiagnosisPreviewOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=base.model_version_id,
        model_version=base.model_version,
        model_status=base.model_status,
        can_compile=base.can_compile,
        metrics=base.metrics,
        source_profile=base.source_profile,
        uses=base.uses,
        blockers=base.blockers,
        warnings=base.warnings,
        manifest=data["manifest"],
        preview_html=data["html"],
        content_hash=data["content_hash"],
    )


def _r1_collect(db: Session, process: ProcessArch) -> dict:
    base = r1_readiness(db, process)
    claims = asset_service.evidence_claims(db, process)
    analysis = _analysis(db, process)
    html = _render_html(
        process,
        base.model_version,
        analysis,
        base.source_profile,
        base.uses,
        claims,
        base.blockers,
        base.warnings,
        inputs=base.inputs,
        can_submit_review=base.can_submit_review,
    )
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    manifest = {
        "kind": "DIAGNOSIS_R1",
        "rule_version": R1_RULE_VERSION,
        "process_id": process.id,
        "process_code": process.code,
        "process_name": process.name,
        "model_version_id": base.model_version_id,
        "model_version": base.model_version,
        "model_status": base.model_status,
        "generated_at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "metrics": base.metrics,
        "source_profile": base.source_profile.model_dump(),
        "uses": [row.model_dump() for row in base.uses],
        "inputs": {
            "model_version_id": base.model_version_id,
            "claims": [row.model_dump(mode="json") for row in claims.claims],
            "r1": [row.model_dump() for row in base.inputs],
        },
        "missing_inputs": base.missing_inputs,
        "can_submit_review": base.can_submit_review,
        "blockers": [row.model_dump() for row in base.blockers],
        "warnings": base.warnings,
        "content_hash": content_hash,
    }
    return {
        "html": html,
        "manifest": manifest,
        "content_hash": content_hash,
        "readiness": base,
        "analysis": analysis,
        "claims": claims,
    }


def r1_preview(db: Session, process: ProcessArch) -> DiagnosisR1PreviewOut:
    data = _r1_collect(db, process)
    base = data["readiness"]
    return DiagnosisR1PreviewOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=base.model_version_id,
        model_version=base.model_version,
        model_status=base.model_status,
        can_compile=base.can_compile,
        metrics=base.metrics,
        source_profile=base.source_profile,
        uses=base.uses,
        blockers=base.blockers,
        warnings=base.warnings,
        manifest=data["manifest"],
        preview_html=data["html"],
        content_hash=data["content_hash"],
        inputs=base.inputs,
        missing_inputs=base.missing_inputs,
        can_submit_review=base.can_submit_review,
    )


def _next_version_label(document: ProcessDocument) -> str:
    labels = [row.version_label for row in document.versions]
    minors = []
    for label in labels:
        parts = label.split(".")
        if len(parts) == 2 and parts[0] == "1" and parts[1].isdigit():
            minors.append(int(parts[1]))
    return f"1.{max(minors, default=-1) + 1}"


def commit(db: Session, process: ProcessArch, user: User) -> AssetPackageOut:
    return _commit_packet(db, process, user, _collect(db, process))


def r1_commit(db: Session, process: ProcessArch, user: User) -> AssetPackageOut:
    return _commit_packet(db, process, user, _r1_collect(db, process))


def r1_transition_guard(db: Session, user: User, version_id: int) -> None:
    version = db.get(ProcessDocumentVersion, version_id)
    if version is None or (version.compile_manifest or {}).get("kind") != "DIAGNOSIS_R1":
        return
    document = db.get(ProcessDocument, version.document_id)
    if document is None:
        return
    process = asset_service.require_process(db, user, document.process_id)
    readiness = r1_readiness(db, process)
    if readiness.can_submit_review:
        return
    blockers = [
        {"message": row.label, "targets": [row.detail]}
        for row in readiness.inputs
        if row.required and not row.ready
    ]
    if not blockers:
        blockers = [{"message": "存在未裁决冲突或过期证据", "targets": []}]
    raise HTTPException(
        status_code=409,
        detail={"message": "R1 必填输入未齐，不能提交评审。", "blockers": blockers},
    )


def _commit_packet(db: Session, process: ProcessArch, user: User, data: dict) -> AssetPackageOut:
    base = data["readiness"]
    kind = data["manifest"].get("kind", "DIAGNOSIS")
    kind_label = "R1 诊断证据包" if kind == "DIAGNOSIS_R1" else "诊断证据包"
    if not base.can_compile:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "存在硬阻断，拒绝生成诊断证据包。",
                "blockers": [row.model_dump() for row in base.blockers],
            },
        )
    code = f"{DOC_PREFIX}{process.code}"
    document = db.scalar(select(ProcessDocument).where(ProcessDocument.code == code))
    if document is None:
        document = ProcessDocument(
            process_id=process.id,
            code=code,
            title=f"{process.name} · {kind_label}",
            category="OTHER",
            description="由已发布模型 + 证据主张生成；模型指标为估算，不等同于实测。",
            level="PROCESS",
            language="zh-CN",
            owner=process.owner,
            owner_user_id=process.owner_user_id,
            org_unit_id=process.org_unit_id,
        )
        db.add(document)
        db.flush()
    elif document.process_id != process.id:
        raise HTTPException(409, "诊断证据包编码已被其他对象占用。")

    label = _next_version_label(document)
    html = data["html"]
    storage = storage_service.get_storage()
    key = storage_service.build_key(
        f"diagnosis-packets/{process.id}", f"{process.code}-diagnosis-packet.html"
    )
    try:
        digest, size = storage.save(
            key, io.BytesIO(html.encode("utf-8")), storage_service.max_bytes()
        )
    except Exception as exc:  # noqa: BLE001 - 存储层错误统一转 500
        raise HTTPException(500, "诊断证据包文件写入失败。") from exc

    try:
        version = document_service.create_version(
            db,
            document,
            {
                "version_label": label,
                "note": f"{kind_label} · 模型 v{base.model_version}",
            },
            user,
            file_meta={
                "file_name": f"{process.code}-diagnosis-packet.html",
                "mime_type": "text/html",
                "size_bytes": size,
                "checksum": digest,
                "storage_backend": "local",
                "storage_key": key,
            },
        )
        version.source_kind = "COMPILED"
        version.compile_manifest = data["manifest"]
        if kind == "DIAGNOSIS_R1":
            seen: set[tuple] = set()
            for claim in data["claims"].claims:
                for target in claim.targets:
                    if target.target_type in {"ACTIVITY", "TIME_FIELD"}:
                        key = (claim.id, target.target_id)
                        activity_id = target.target_id
                    elif target.target_type == "PROCESS":
                        key = (claim.id, None)
                        activity_id = None
                    else:
                        continue
                    if key in seen:
                        continue
                    seen.add(key)
                    db.add(
                        CompiledAssetComponent(
                            document_version_id=version.id,
                            component_type="CLAIM_REF",
                            component_ref_id=claim.id,
                            activity_id=activity_id,
                            source_hash=claim.source_hash,
                        )
                    )
        db.flush()
        audit.record(
            db,
            user,
            "CREATE",
            "process_document_version",
            version.id,
            f"{code} v{label} {kind_label}生成（模型 v{base.model_version}）",
        )
        db.commit()
    except document_service.ProcessDocumentError as exc:
        db.rollback()
        storage.delete(key)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(version)
    db.refresh(document)
    return package_out(document, version, preview_html=html)
