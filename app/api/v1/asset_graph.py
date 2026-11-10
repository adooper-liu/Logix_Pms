"""流程资产生产关系：查询、受控写入与生成就绪度。

读写分离：查询/就绪度在 `asset_graph` 服务，写入在 `asset_graph_write` 服务。
写入统一要求「已有已发布模型版本」，并把每次变更接入审计哈希链。
"""

import io
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    ensure_can_edit_owned,
)
from app.schemas.asset_graph import (
    ActivityRelationIn,
    ActivityRelationOut,
    ArchitectureMapOut,
    AssetImpactOut,
    AssetPackageOut,
    AssetPackagePreviewOut,
    AssetPackageTransitionIn,
    AssetReadinessOut,
    EdgeHandoffIn,
    EdgeHandoffOut,
    EvidenceAdjudicationIn,
    EvidenceAdjudicationOut,
    EvidenceClaimIn,
    EvidenceClaimListOut,
    EvidenceClaimOut,
    NodeActivityLinkIn,
    NodeActivityLinkOut,
    UnmodeledActivityIn,
    UnmodeledActivityOut,
)
from app.schemas.binding_readiness import ActivityBindingsOut
from app.schemas.common import DeleteResult
from app.schemas.diagnosis import (
    DiagnosisPreviewOut,
    DiagnosisR1PreviewOut,
    DiagnosisR1ReadinessOut,
    DiagnosisReadinessOut,
)
from app.schemas.document_candidate import (
    DocumentCandidateConfirmIn,
    DocumentCandidateOut,
    DocumentExtractIn,
)
from app.schemas.log_import import (
    ComparisonClaimReadinessOut,
    ComparisonReceiptOptionOut,
    LogComparisonOut,
    LogComparisonReceiptIn,
    LogComparisonReceiptOut,
    LogComparisonWriteBackIn,
    LogComparisonWriteBackOptionsOut,
    LogComparisonWriteBackOut,
    LogImportMapIn,
    LogImportOut,
)
from app.schemas.model_source import ModelSourceProfileOut
from app.schemas.resource_link import ResourceLinkIn, ResourceLinkOut, ResourceOptionsOut
from app.schemas.traceability import TraceabilityOut
from app.services import asset_graph as asset_service
from app.services import asset_graph_write as write_service
from app.services import asset_package as package_service
from app.services import audit as audit_service
from app.services import binding_readiness as binding_service
from app.services import diagnosis as diagnosis_service
from app.services import document_extract as document_extract_service
from app.services import log_import as log_import_service
from app.services import model_source as model_source_service
from app.services import preview as preview_service
from app.services import resource_link as resource_service
from app.services import traceability as traceability_service

router = APIRouter(prefix="/processes", tags=["流程资产"])
package_router = APIRouter(prefix="/asset-packages", tags=["流程资产"])
trace_router = APIRouter(prefix="/traceability", tags=["追溯矩阵"])


@trace_router.get(
    "",
    response_model=TraceabilityOut,
    summary="追溯矩阵：目标/KPI → L3/L4 → 节点 → 资产版本 → 证据",
)
def get_traceability(
    db: DbSession,
    user: CurrentUser,
    objective_id: Optional[int] = Query(default=None, ge=1),
    kpi_id: Optional[int] = Query(default=None, ge=1),
    process_id: Optional[int] = Query(default=None, ge=1),
    activity_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
):
    return traceability_service.traceability(
        db,
        user,
        objective_id=objective_id,
        kpi_id=kpi_id,
        process_id=process_id,
        activity_id=activity_id,
        limit=limit,
    )


# ------------------------------------------------------------------ 查询


@router.get(
    "/{process_id}/binding-readiness",
    response_model=ActivityBindingsOut,
    summary="活动四绑定只读核对：来源、缺口与当前设计模型",
)
def get_binding_readiness(process_id: int, db: DbSession, user: CurrentUser):
    return binding_service.activity_bindings(db, process_id, user)


@router.get("/{process_id}/resource-links", response_model=list[ResourceLinkOut])
def get_resource_links(process_id: int, db: DbSession, user: CurrentUser):
    process = resource_service.require_process(db, process_id)
    return resource_service.list_links(db, process, user)


@router.get("/{process_id}/resource-link-options", response_model=ResourceOptionsOut)
def get_resource_options(
    process_id: int,
    activity_id: int,
    db: DbSession,
    user: CurrentUser,
    node_key: Optional[str] = None,
):
    process = resource_service.require_process(db, process_id)
    return resource_service.options(db, process, activity_id, node_key, user)


@router.post("/{process_id}/resource-links", response_model=ResourceLinkOut, status_code=201)
def save_resource_link(process_id: int, payload: ResourceLinkIn, db: DbSession, user: ManagerUser):
    process = resource_service.require_process(db, process_id)
    row = resource_service.upsert(db, process, payload, user)
    audit_service.record(db, user, "UPDATE", "process", process_id, f"活动原资源引用 {row.ref_key}")
    db.commit()
    return resource_service.out(db, process, row, user)


@router.delete("/{process_id}/resource-links/{link_id}", response_model=DeleteResult)
def remove_resource_link(process_id: int, link_id: int, db: DbSession, user: ManagerUser):
    process = resource_service.require_process(db, process_id)
    row = resource_service.deactivate(db, process, link_id)
    audit_service.record(
        db, user, "UPDATE", "process", process_id, f"停用活动原资源引用 {row.ref_key}"
    )
    db.commit()
    return DeleteResult(deleted=1)


@router.get(
    "/{process_id}/architecture-map",
    response_model=ArchitectureMapOut,
    summary="流程架构关系：节点↔活动、层级、交接、未建模",
)
def get_architecture_map(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return asset_service.architecture_map(db, process)


@router.get(
    "/{process_id}/evidence-claims",
    response_model=EvidenceClaimListOut,
    summary="证据主张：范围、方法、样本、冲突、未知覆盖",
)
def get_evidence_claims(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return asset_service.evidence_claims(db, process)


@router.get(
    "/{process_id}/asset-readiness",
    response_model=AssetReadinessOut,
    summary="资产生产就绪度：能产出什么、缺什么、下一步",
)
def get_asset_readiness(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return asset_service.readiness(db, process)


# ------------------------------------------------------------------ 架构关系写入


@router.post(
    "/{process_id}/architecture-map/links",
    response_model=NodeActivityLinkOut,
    summary="新增或合并节点↔活动关系",
)
def upsert_node_activity_link(
    process_id: int,
    payload: NodeActivityLinkIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return write_service.upsert_node_activity_link(db, process, payload, user)


@router.post(
    "/{process_id}/architecture-map/relations",
    response_model=ActivityRelationOut,
    summary="新增或合并活动↔活动关系",
)
def upsert_activity_relation(
    process_id: int,
    payload: ActivityRelationIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return write_service.upsert_activity_relation(db, process, payload, user)


@router.post(
    "/{process_id}/architecture-map/handoffs",
    response_model=EdgeHandoffOut,
    summary="新增或合并连线交接",
)
def upsert_edge_handoff(
    process_id: int,
    payload: EdgeHandoffIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return write_service.upsert_edge_handoff(db, process, payload, user)


@router.post(
    "/{process_id}/architecture-map/unmodeled",
    response_model=UnmodeledActivityOut,
    summary="登记未建模活动",
)
def upsert_unmodeled_activity(
    process_id: int,
    payload: UnmodeledActivityIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return write_service.upsert_unmodeled_activity(db, process, payload, user)


@router.delete(
    "/{process_id}/architecture-map/links/{link_id}",
    response_model=DeleteResult,
    summary="撤销节点↔活动关系；同步清理兼容主活动指针",
)
def delete_node_activity_link(
    process_id: int,
    link_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return DeleteResult(deleted=write_service.delete_node_activity_link(db, process, link_id, user))


@router.delete(
    "/{process_id}/architecture-map/relations/{relation_id}",
    response_model=DeleteResult,
    summary="撤销活动↔活动关系",
)
def delete_activity_relation(
    process_id: int,
    relation_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return DeleteResult(
        deleted=write_service.delete_activity_relation(db, process, relation_id, user)
    )


@router.delete(
    "/{process_id}/architecture-map/handoffs/{handoff_id}",
    response_model=DeleteResult,
    summary="撤销连线交接",
)
def delete_edge_handoff(
    process_id: int,
    handoff_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return DeleteResult(deleted=write_service.delete_edge_handoff(db, process, handoff_id, user))


@router.delete(
    "/{process_id}/architecture-map/unmodeled/{unmodeled_id}",
    response_model=DeleteResult,
    summary="撤销未建模活动登记",
)
def delete_unmodeled_activity(
    process_id: int,
    unmodeled_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return DeleteResult(
        deleted=write_service.delete_unmodeled_activity(db, process, unmodeled_id, user)
    )


# ------------------------------------------------------------------ 证据写入


@router.post(
    "/{process_id}/evidence-claims",
    response_model=EvidenceClaimOut,
    summary="登记一条证据主张及其覆盖范围",
)
def create_evidence_claim(
    process_id: int,
    payload: EvidenceClaimIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return write_service.create_evidence_claim(db, process, payload, user)


@router.post(
    "/{process_id}/evidence-claims/{claim_id}/adjudicate",
    response_model=EvidenceAdjudicationOut,
    summary="裁决证据冲突组；保留原主张不覆盖",
)
def adjudicate_evidence_claim(
    process_id: int,
    claim_id: int,
    payload: EvidenceAdjudicationIn,
    db: DbSession,
    user: ManagerUser,
):
    process = asset_service.require_process(db, user, process_id)
    return write_service.adjudicate_claim(db, process, claim_id, payload, user)


# ------------------------------------------------------------------ 日志导入


@router.get(
    "/{process_id}/log-imports",
    response_model=list[LogImportOut],
    summary="事件日志导入清单",
)
def list_log_imports(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.list_imports(db, process)


@router.get(
    "/{process_id}/log-imports/compare",
    response_model=LogComparisonOut,
    summary="双样本前后对照：只读比较两次已提交日志",
)
def compare_log_imports(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    before_id: int = Query(ge=1),
    after_id: int = Query(ge=1),
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.compare(db, process, before_id, after_id)


@router.post(
    "/{process_id}/log-imports/compare/receipt",
    response_model=LogComparisonReceiptOut,
    summary="接收/退回/观察前后对照结论（MANAGER+）",
)
def create_log_comparison_receipt(
    process_id: int,
    payload: LogComparisonReceiptIn,
    db: DbSession,
    user: ManagerUser,
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.create_receipt(db, process, user, payload)


@router.get(
    "/{process_id}/log-imports/compare/receipts",
    response_model=list[LogComparisonReceiptOut],
    summary="前后对照的接收记录",
)
def list_log_comparison_receipts(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    before_id: int = Query(ge=1),
    after_id: int = Query(ge=1),
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.list_receipts(db, process, before_id, after_id)


@router.get(
    "/{process_id}/log-imports/compare/claim-readiness",
    response_model=ComparisonClaimReadinessOut,
    summary="能否据此宣称改善：可比 + 样本达标 + 已接收",
)
def get_comparison_claim_readiness(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    before_id: int = Query(ge=1),
    after_id: int = Query(ge=1),
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.claim_readiness(db, process, before_id, after_id)


@router.get(
    "/{process_id}/log-imports/compare/accepted",
    response_model=list[ComparisonReceiptOptionOut],
    summary="当前可引用的已接收对照（每个对照对取最新结论）",
)
def list_accepted_comparisons(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.claimable_receipts(db, process)


@router.get(
    "/{process_id}/log-imports/compare/write-back-options",
    response_model=LogComparisonWriteBackOptionsOut,
    summary="可写回的流程级时长 KPI 与换算后的观测值",
)
def get_comparison_write_back_options(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    before_id: int = Query(ge=1),
    after_id: int = Query(ge=1),
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.write_back_options(db, process, before_id, after_id)


@router.post(
    "/{process_id}/log-imports/compare/write-back",
    response_model=LogComparisonWriteBackOut,
    summary="把已接收的对照写回 KPI 基线/目标（MANAGER+）",
)
def write_back_log_comparison(
    process_id: int,
    payload: LogComparisonWriteBackIn,
    db: DbSession,
    user: ManagerUser,
):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.write_back(db, process, user, payload)


@router.get(
    "/{process_id}/log-imports/{import_id}",
    response_model=LogImportOut,
    summary="事件日志导入详情",
)
def get_log_import(process_id: int, import_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return log_import_service.get_import(db, process, import_id)


@router.post(
    "/{process_id}/log-imports",
    response_model=LogImportOut,
    summary="上传 CSV 事件日志（先解析，后映射）",
)
def create_log_import(
    process_id: int,
    db: DbSession,
    user: WriteUser,
    file: UploadFile = File(...),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "请上传 CSV 文件。")
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    data = file.file.read()
    return log_import_service.create_import(db, process, user, file.filename or "events.csv", data)


@router.post(
    "/{process_id}/log-imports/{import_id}/map",
    response_model=LogImportOut,
    summary="映射日志活动标签到 L4 活动并计算指标",
)
def map_log_import(
    process_id: int,
    import_id: int,
    payload: LogImportMapIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return log_import_service.map_import(db, process, import_id, payload.mapping, user)


@router.post(
    "/{process_id}/log-imports/{import_id}/commit",
    response_model=LogImportOut,
    summary="把日志指标提交为 LOGGED 证据",
)
def commit_log_import(
    process_id: int,
    import_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return log_import_service.commit_import(db, process, import_id, user)


# ------------------------------------------------------------------ 文档候选活动


@router.get(
    "/{process_id}/document-candidates",
    response_model=list[DocumentCandidateOut],
    summary="文档候选活动清单",
)
def list_document_candidates(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    document_version_id: int = Query(ge=1),
):
    process = asset_service.require_process(db, user, process_id)
    return document_extract_service.list_candidates(db, process, document_version_id)


@router.post(
    "/{process_id}/document-candidates/extract",
    response_model=list[DocumentCandidateOut],
    summary="从已生效文档提取候选活动（不自动写模型）",
)
def extract_document_candidates(
    process_id: int,
    payload: DocumentExtractIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return document_extract_service.extract(
        db,
        process,
        user,
        payload.document_version_id,
        force=payload.force,
    )


@router.post(
    "/{process_id}/document-candidates/{candidate_id}/confirm",
    response_model=DocumentCandidateOut,
    summary="确认候选并创建 L4 活动（不自动映射 BPMN）",
)
def confirm_document_candidate(
    process_id: int,
    candidate_id: int,
    payload: DocumentCandidateConfirmIn,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return document_extract_service.confirm(db, process, candidate_id, payload, user)


@router.post(
    "/{process_id}/document-candidates/{candidate_id}/reject",
    response_model=DocumentCandidateOut,
    summary="驳回候选活动",
)
def reject_document_candidate(
    process_id: int,
    candidate_id: int,
    db: DbSession,
    user: WriteUser,
):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return document_extract_service.reject(db, process, candidate_id, user)


# ------------------------------------------------------------------ As-Is 来源画像


@router.get(
    "/{process_id}/model-source-profile",
    response_model=ModelSourceProfileOut,
    summary="As-Is 来源画像：方法覆盖、活动缺口与用途就绪度",
)
def get_model_source_profile(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return model_source_service.profile(db, process)


# ------------------------------------------------------------------ 诊断证据包


@router.get(
    "/{process_id}/diagnosis-readiness",
    response_model=DiagnosisReadinessOut,
    summary="诊断就绪度：来源画像、用途就绪度与下一步",
)
def get_diagnosis_readiness(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return diagnosis_service.readiness(db, process)


@router.post(
    "/{process_id}/diagnosis-packet/compile",
    response_model=DiagnosisPreviewOut,
    summary="诊断证据包预览（不写库）",
)
def preview_diagnosis_packet(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return diagnosis_service.preview(db, process)


@router.post(
    "/{process_id}/diagnosis-packet",
    response_model=AssetPackageOut,
    summary="生成诊断证据包草稿（流程级报告）",
)
def create_diagnosis_packet(process_id: int, db: DbSession, user: WriteUser):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return diagnosis_service.commit(db, process, user)


# ------------------------------------------------------------------ R1 诊断编译


@router.get(
    "/{process_id}/r1-readiness",
    response_model=DiagnosisR1ReadinessOut,
    summary="R1 就绪度：2.1–2.4 必填输入与提交门禁",
)
def get_r1_readiness(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return diagnosis_service.r1_readiness(db, process)


@router.post(
    "/{process_id}/r1/compile",
    response_model=DiagnosisR1PreviewOut,
    summary="R1 诊断证据包预览（不写库）",
)
def preview_r1(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return diagnosis_service.r1_preview(db, process)


@router.post(
    "/{process_id}/r1",
    response_model=AssetPackageOut,
    summary="生成 R1 诊断证据包草稿；必填输入未齐仍可出草稿",
)
def create_r1(process_id: int, db: DbSession, user: WriteUser):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return diagnosis_service.r1_commit(db, process, user)


# ------------------------------------------------------------------ 资产包生成


@router.post(
    "/{process_id}/asset-packages/compile",
    response_model=AssetPackagePreviewOut,
    summary="资产包预览：阻断清单 + HTML + 生成清单（不写库）",
)
def preview_asset_package(process_id: int, db: DbSession, user: CurrentUser):
    process = asset_service.require_process(db, user, process_id)
    return package_service.preview(db, process)


@router.get(
    "/{process_id}/asset-packages/print-pack",
    summary="流程资产打印包：合并多个已生成版本（HTML/PDF）",
)
def asset_print_pack(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    format: str = Query(default="html", pattern="^(html|pdf)$"),
    version_ids: Optional[str] = Query(default=None),
):
    process = asset_service.require_process(db, user, process_id)
    ids: Optional[list[int]] = None
    if version_ids:
        try:
            ids = [int(part) for part in version_ids.split(",") if part.strip()]
        except ValueError as exc:
            raise HTTPException(400, "version_ids 必须是逗号分隔的整数。") from exc
        if not ids:
            raise HTTPException(400, "version_ids 不能为空。")
    html = package_service.build_print_pack(db, user, process, ids)
    if format == "pdf":
        if not preview_service.converter_available():
            raise HTTPException(503, "未配置 LibreOffice 转换器，无法生成 PDF。")
        try:
            pdf = preview_service.convert_to_pdf(
                io.BytesIO(html.encode("utf-8")),
                f"{process.code}-asset-print-pack.html",
            )
        except preview_service.PreviewConversionError as exc:
            raise HTTPException(502, f"打印包 PDF 生成失败：{exc}") from exc
        filename = quote(f"{process.code}-asset-print-pack.pdf")
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "X-Content-Type-Options": "nosniff",
            },
        )
    filename = quote(f"{process.code}-asset-print-pack.html")
    return HTMLResponse(
        html,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{process_id}/asset-packages",
    response_model=AssetPackageOut,
    summary="生成资产包草稿（流程级 SOP 版本）",
)
def create_asset_package(process_id: int, db: DbSession, user: WriteUser):
    process = asset_service.require_process(db, user, process_id)
    ensure_can_edit_owned(user, process.owner_user_id, process.owner)
    return package_service.commit(db, process, user)


@package_router.get(
    "/impact",
    response_model=AssetImpactOut,
    summary="组件反向查询：哪些资产包引用了该活动/表单/规则",
)
def get_asset_impact(
    db: DbSession,
    user: CurrentUser,
    component_type: Optional[str] = Query(default=None),
    component_ref_id: Optional[int] = Query(default=None, ge=1),
    activity_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
):
    return package_service.component_impact(
        db,
        user,
        component_type=component_type,
        component_ref_id=component_ref_id,
        activity_id=activity_id,
        limit=limit,
    )


@package_router.get(
    "/{version_id}",
    response_model=AssetPackageOut,
    summary="资产包版本详情与生成清单",
)
def get_asset_package(version_id: int, db: DbSession, user: CurrentUser):
    return package_service.get_package(db, user, version_id)


@package_router.get(
    "/{version_id}/pdf",
    summary="资产包 PDF（需 LibreOffice 转换器）",
)
def download_asset_package_pdf(version_id: int, db: DbSession, user: CurrentUser):
    package = package_service.get_package(db, user, version_id)
    if not package.preview_html:
        raise HTTPException(404, "资产包文件不存在或已被清理。")
    if not preview_service.converter_available():
        raise HTTPException(503, "未配置 LibreOffice 转换器，无法生成 PDF。")
    try:
        pdf = preview_service.convert_to_pdf(
            io.BytesIO(package.preview_html.encode("utf-8")),
            f"{package.document_code}-{package.version_label}.html",
        )
    except preview_service.PreviewConversionError as exc:
        raise HTTPException(502, f"PDF 生成失败：{exc}") from exc
    filename = quote(f"{package.document_code}-{package.version_label}.pdf")
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@package_router.post(
    "/{version_id}/transition",
    response_model=AssetPackageOut,
    summary="资产包版本流转（MANAGER+）；阻断未清零拒绝提交",
)
def transition_asset_package(
    version_id: int,
    payload: AssetPackageTransitionIn,
    db: DbSession,
    user: ManagerUser,
):
    diagnosis_service.r1_transition_guard(db, user, version_id)
    return package_service.transition_by_id(db, user, version_id, payload.status, payload.note)
