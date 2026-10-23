"""资产基线与差异审计。

基线是「某个时点的标准文件/模板版本快照」，只记录版本指针，不复制文件；
差异用来回答「基准之后哪些标准变了、哪些新增/移除」。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.timeutil import utcnow
from app.models.baseline import AssetBaseline
from app.models.deliverable import DeliverableDefinition, DeliverableInstance, DeliverableVersion
from app.models.enums import BaselineScope, DeliverableStatus
from app.models.org import OrgUnit
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project
from app.models.tool_template import TemplateUsage, ToolTemplate
from app.models.user import User
from app.schemas.baseline import (
    BaselineDetail,
    BaselineDiff,
    BaselineDiffItem,
    BaselineItem,
    BaselineMeta,
    BaselineOut,
    GovernanceFrozenItem,
    GovernanceStaleVariant,
    GovernanceSummary,
)
from app.services import governance as governance_service
from app.services import org_scope, process_scope
from app.services import org_unit as org_service
from app.services import process_document as document_service
from app.services import tool_template as template_service

SCOPE_LABELS: Dict[str, str] = {
    BaselineScope.ALL.value: "全部资产",
    BaselineScope.PROCESS.value: "单条流程（含上级继承）",
    BaselineScope.ORG.value: "组织视角（含上级继承）",
}

DIFF_LABELS: Dict[str, str] = {
    "UNCHANGED": "未变",
    "CHANGED": "已变更",
    "ADDED": "新增",
    "REMOVED": "已移除",
}

_DIFF_ORDER = {"CHANGED": 0, "REMOVED": 1, "ADDED": 2, "UNCHANGED": 3}


class BaselineError(ValueError):
    """基线规则拒绝；API 层转成 400。"""


def require_baseline(db: Session, baseline_id: int) -> AssetBaseline:
    baseline = db.get(AssetBaseline, baseline_id)
    if baseline is None:
        raise BaselineError(f"基线 {baseline_id} 不存在")
    return baseline


def capture_assets(
    db: Session,
    scope: str,
    process_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
) -> List[dict]:
    items: List[dict] = []

    doc_stmt = (
        select(ProcessDocument)
        .options(
            joinedload(ProcessDocument.process),
            joinedload(ProcessDocument.org_unit),
            selectinload(ProcessDocument.versions),
        )
        .where(ProcessDocument.is_active.is_(True))
    )
    if scope == BaselineScope.PROCESS.value:
        if process_id is None:
            raise BaselineError("流程范围的基线必须指定 process_id")
        doc_stmt = doc_stmt.where(
            ProcessDocument.process_id.in_(process_scope.ancestor_ids(db, process_id))
        )
    elif scope == BaselineScope.ORG.value:
        if org_unit_id is None:
            raise BaselineError("组织范围的基线必须指定 org_unit_id")
        condition = document_service.visible_conditions(db, org_unit_id)
        if condition is not None:
            doc_stmt = doc_stmt.where(condition)
        if process_id is not None:
            doc_stmt = doc_stmt.where(ProcessDocument.process_id == process_id)

    for document in db.scalars(doc_stmt).all():
        version = document_service.effective_version_on(document)
        if version is None:
            continue
        scope_info = org_service.resolve_scope(document.org_unit)
        items.append(
            {
                "kind": "document",
                "id": document.id,
                "code": document.code,
                "title": document.title,
                "version_id": version.id,
                "version_display": f"v{version.version_label}",
                "status": version.status,
                "checksum": version.checksum,
                "scope_label": scope_info["scope_label"],
                "process_code": document.process.code if document.process else None,
                "process_name": document.process.name if document.process else None,
                "type_label": document_service.POLICY_LABELS.get(
                    document.variation_policy, document.variation_policy
                ),
                "definition_code": None,
            }
        )

    # 模板是跨流程的方法资产，不纳入单流程基线
    if scope != BaselineScope.PROCESS.value:
        tpl_stmt = (
            select(ToolTemplate)
            .options(
                joinedload(ToolTemplate.tool),
                joinedload(ToolTemplate.definition),
                joinedload(ToolTemplate.org_unit),
                selectinload(ToolTemplate.versions),
            )
            .where(ToolTemplate.is_active.is_(True))
        )
        if scope == BaselineScope.ORG.value:
            tpl_stmt = org_scope.scoped(db, tpl_stmt, ToolTemplate.org_unit_id, org_unit_id)
        for template in db.scalars(tpl_stmt).all():
            version = template_service.effective_version(template)
            if version is None:
                continue
            scope_info = org_service.resolve_scope(template.org_unit)
            items.append(
                {
                    "kind": "template",
                    "id": template.id,
                    "code": template.code,
                    "title": template.name,
                    "version_id": version.id,
                    "version_display": version.version_label,
                    "status": version.status,
                    "checksum": version.checksum,
                    "scope_label": scope_info["scope_label"],
                    "process_code": None,
                    "process_name": None,
                    "type_label": template_service.FORMAT_LABELS.get(
                        template.format, template.format
                    ),
                    "definition_code": template.definition.code if template.definition else None,
                }
            )

    items.sort(key=lambda item: (item["kind"], item["code"]))
    return items


def next_code(db: Session) -> str:
    prefix = f"BL-{date.today().strftime('%Y%m%d')}-"
    existing = db.scalars(
        select(AssetBaseline.code).where(AssetBaseline.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:03d}"


def create_baseline(db: Session, data: dict, user: User) -> AssetBaseline:
    scope = data["scope"]
    process_id = data.get("process_id")
    org_unit_id = data.get("org_unit_id")
    if scope == BaselineScope.PROCESS.value:
        process = db.get(ProcessArch, process_id) if process_id else None
        if process is None:
            raise BaselineError("流程范围的基线必须指向存在的流程")
    elif scope == BaselineScope.ORG.value:
        if org_unit_id is None:
            raise BaselineError("组织范围的基线必须指定 org_unit_id")
        try:
            org_service.require_org(db, org_unit_id)
        except org_service.OrgError as exc:
            raise BaselineError(str(exc)) from exc
    else:
        process_id = None
        org_unit_id = None

    items = capture_assets(db, scope, process_id, org_unit_id)
    baseline = AssetBaseline(
        code=next_code(db),
        name=data["name"],
        scope=scope,
        process_id=process_id,
        org_unit_id=org_unit_id,
        note=data.get("note"),
        item_count=len(items),
        snapshot=items,
        created_by=user.display_name,
        created_by_id=user.id,
    )
    db.add(baseline)
    db.flush()
    return baseline


def baseline_out(db: Session, baseline: AssetBaseline) -> BaselineOut:
    process = db.get(ProcessArch, baseline.process_id) if baseline.process_id else None
    org = db.get(OrgUnit, baseline.org_unit_id) if baseline.org_unit_id else None
    return BaselineOut(
        id=baseline.id,
        code=baseline.code,
        name=baseline.name,
        scope=baseline.scope,
        scope_label=SCOPE_LABELS.get(baseline.scope, baseline.scope),
        process_id=baseline.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        org_unit_id=baseline.org_unit_id,
        org_unit_name=org.name if org else None,
        note=baseline.note,
        item_count=baseline.item_count,
        created_by=baseline.created_by,
        created_at=baseline.created_at,
    )


def baseline_detail(db: Session, baseline: AssetBaseline) -> BaselineDetail:
    base = baseline_out(db, baseline)
    return BaselineDetail(
        **base.model_dump(),
        items=[BaselineItem(**item) for item in baseline.snapshot or []],
    )


def diff_baseline(db: Session, baseline: AssetBaseline) -> BaselineDiff:
    current = {
        (item["kind"], item["id"]): item
        for item in capture_assets(db, baseline.scope, baseline.process_id, baseline.org_unit_id)
    }
    old_items = {(item["kind"], item["id"]): item for item in baseline.snapshot or []}
    items: List[BaselineDiffItem] = []
    counts = {"UNCHANGED": 0, "CHANGED": 0, "ADDED": 0, "REMOVED": 0}

    for key, old in old_items.items():
        new = current.get(key)
        if new is None:
            status = "REMOVED"
        elif new["version_id"] != old["version_id"]:
            status = "CHANGED"
        else:
            status = "UNCHANGED"
        counts[status] += 1
        items.append(
            BaselineDiffItem(
                kind=old["kind"],
                id=old["id"],
                code=old["code"],
                title=old["title"],
                status=status,
                status_label=DIFF_LABELS[status],
                old_version_display=old.get("version_display"),
                new_version_display=new.get("version_display") if new else None,
                scope_label=(new or old).get("scope_label"),
            )
        )

    for key, new in current.items():
        if key in old_items:
            continue
        counts["ADDED"] += 1
        items.append(
            BaselineDiffItem(
                kind=new["kind"],
                id=new["id"],
                code=new["code"],
                title=new["title"],
                status="ADDED",
                status_label=DIFF_LABELS["ADDED"],
                old_version_display=None,
                new_version_display=new.get("version_display"),
                scope_label=new.get("scope_label"),
            )
        )

    items.sort(key=lambda item: (_DIFF_ORDER[item.status], item.kind, item.code))
    return BaselineDiff(
        baseline_id=baseline.id,
        baseline_code=baseline.code,
        baseline_name=baseline.name,
        counts=counts,
        items=items,
    )


def meta() -> BaselineMeta:
    return BaselineMeta(scope_labels=SCOPE_LABELS, diff_status_labels=DIFF_LABELS)


def list_baselines(db: Session, limit: int = 100) -> List[AssetBaseline]:
    return list(
        db.scalars(
            select(AssetBaseline)
            .order_by(AssetBaseline.created_at.desc(), AssetBaseline.id.desc())
            .limit(limit)
        ).all()
    )


def count_baselines(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AssetBaseline)) or 0


def governance_summary(db: Session) -> GovernanceSummary:
    """治理概览：资产有效性、落后变体、固定旧版交付物、基线覆盖率、模板使用。"""
    documents = list(
        db.scalars(
            select(ProcessDocument)
            .options(selectinload(ProcessDocument.versions))
            .where(ProcessDocument.is_active.is_(True))
        ).all()
    )
    documents_effective = 0
    variants = [doc for doc in documents if doc.variant_of_document_id]
    stale: List[GovernanceStaleVariant] = []
    for document in documents:
        if document_service.effective_version_on(document) is not None:
            documents_effective += 1

    for variant in variants:
        base = (
            db.get(ProcessDocument, variant.variant_of_document_id)
            if variant.variant_of_document_id
            else None
        )
        latest_base = document_service.effective_version_on(base) if base else None
        current = document_service.effective_version_on(variant)
        old_id = (
            current.source_base_version_id
            if current and current.source_base_version_id
            else variant.variant_base_version_id
        )
        old_base = db.get(ProcessDocumentVersion, old_id) if old_id else None
        if current is None:
            status_label = "无生效版本"
        elif latest_base is None:
            status_label = "上级无生效版本"
        elif old_id == latest_base.id:
            continue
        else:
            status_label = (
                (
                    "落后 major"
                    if int(latest_base.version_label.split(".")[0])
                    > int(old_base.version_label.split(".")[0])
                    else "落后 minor"
                )
                if old_base
                else "未登记基线"
            )
        scope = org_service.resolve_scope(variant.org_unit)
        stale.append(
            GovernanceStaleVariant(
                document_id=variant.id,
                code=variant.code,
                title=variant.title,
                scope_label=scope["scope_label"],
                base_code=base.code if base else None,
                base_now=f"v{old_base.version_label}" if old_base else None,
                base_latest=(f"v{latest_base.version_label}" if latest_base else None),
                status_label=status_label,
            )
        )

    templates = list(
        db.scalars(
            select(ToolTemplate)
            .options(selectinload(ToolTemplate.versions))
            .where(ToolTemplate.is_active.is_(True))
        ).all()
    )
    templates_effective = sum(
        1 for template in templates if template_service.effective_version(template)
    )
    usage_30d = (
        db.scalar(
            select(func.count())
            .select_from(TemplateUsage)
            .where(TemplateUsage.created_at >= utcnow() - timedelta(days=30))
        )
        or 0
    )

    baselines = list_baselines(db, 1)
    latest_baseline = baselines[0] if baselines else None
    latest_diff = diff_baseline(db, latest_baseline).counts if latest_baseline else {}

    processes_total = (
        db.scalar(
            select(func.count())
            .select_from(ProcessArch)
            .where(ProcessArch.level == 3, ProcessArch.is_draft.is_(False))
        )
        or 0
    )
    processes_covered = (
        db.scalar(
            select(func.count(func.distinct(AssetBaseline.process_id)))
            .select_from(AssetBaseline)
            .where(
                AssetBaseline.scope == BaselineScope.PROCESS.value,
                AssetBaseline.process_id.is_not(None),
            )
        )
        or 0
    )
    coverage = round(processes_covered / processes_total * 100, 1) if processes_total else 0.0

    frozen: List[GovernanceFrozenItem] = []
    frozen_count = 0
    rows = db.execute(
        select(DeliverableVersion, DeliverableInstance, Project, DeliverableDefinition)
        .join(DeliverableInstance, DeliverableInstance.id == DeliverableVersion.instance_id)
        .join(Project, Project.id == DeliverableInstance.project_id)
        .join(
            DeliverableDefinition,
            DeliverableDefinition.id == DeliverableInstance.definition_id,
        )
        .where(
            DeliverableVersion.source_document_version_id.is_not(None),
            DeliverableVersion.status.in_(
                [DeliverableStatus.APPROVED.value, DeliverableStatus.EFFECTIVE.value]
            ),
        )
    ).all()
    for version, _instance, project, definition in rows:
        source = db.get(ProcessDocumentVersion, version.source_document_version_id)
        if source is None:
            continue
        document = db.get(ProcessDocument, source.document_id)
        latest = document_service.effective_version_on(document) if document else None
        if latest is None or latest.id == source.id:
            continue
        frozen_count += 1
        frozen.append(
            GovernanceFrozenItem(
                deliverable_version_id=version.id,
                project_code=project.code,
                definition_code=definition.code,
                version_label=f"R{version.version_no}",
                source_display=f"v{source.version_label}",
                latest_display=f"v{latest.version_label}",
            )
        )

    stale.sort(key=lambda item: item.code)
    frozen.sort(key=lambda item: (item.project_code or "", item.definition_code or ""))
    return GovernanceSummary(
        documents_total=len(documents),
        documents_effective=documents_effective,
        documents_without_effective=len(documents) - documents_effective,
        variants_total=len(variants),
        variants_stale=len(stale),
        templates_total=len(templates),
        templates_effective=templates_effective,
        template_usage_30d=usage_30d,
        baselines_total=count_baselines(db),
        latest_baseline_code=latest_baseline.code if latest_baseline else None,
        latest_baseline_name=latest_baseline.name if latest_baseline else None,
        latest_baseline_at=latest_baseline.created_at if latest_baseline else None,
        latest_diff=latest_diff,
        processes_total=processes_total,
        processes_covered=processes_covered,
        process_coverage_pct=coverage,
        frozen_references=frozen_count,
        open_findings=governance_service.open_count(db),
        findings_by_type=governance_service.summary(db),
        stale_variants=stale[:10],
        frozen_items=frozen[:10],
    )
