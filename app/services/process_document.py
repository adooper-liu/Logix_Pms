"""流程标准配套文件服务：版本审批、复制到项目、项目成果晋升。

版本状态机与交付物/模板共用同一套规则；文件复用 `storage.py`。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.deliverable import DeliverableDefinition, DeliverableInstance, DeliverableVersion
from app.models.enums import (
    AssetVariationPolicy,
    DeliverableStatus,
    DocumentLevel,
    ProcessDocumentCategory,
)
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project
from app.models.user import User
from app.schemas.process_document import (
    DeliverableReferenceOut,
    DocumentFieldDiff,
    DocumentImpactOut,
    EffectiveDocumentOut,
    ProcessDocumentDetail,
    ProcessDocumentMeta,
    ProcessDocumentOut,
    ProcessDocumentVersionOut,
    VariantImpactOut,
)
from app.services import deliverable as deliverable_service
from app.services import org_scope, process_scope
from app.services import org_unit as org_service
from app.services import preview as preview_service
from app.services import process_model as model_service
from app.services import storage as storage_service

CATEGORY_LABELS: Dict[str, str] = {
    ProcessDocumentCategory.SOP.value: "SOP",
    ProcessDocumentCategory.FORM.value: "表单",
    ProcessDocumentCategory.CHECKLIST.value: "检查表",
    ProcessDocumentCategory.TEMPLATE.value: "模板",
    ProcessDocumentCategory.POLICY.value: "制度",
    ProcessDocumentCategory.OTHER.value: "其他",
}

POLICY_LABELS: Dict[str, str] = {
    AssetVariationPolicy.LOCKED.value: "锁定",
    AssetVariationPolicy.PARAMETERIZED.value: "参数可调",
    AssetVariationPolicy.EXTENDABLE.value: "可扩展",
    AssetVariationPolicy.OPTIONAL.value: "可选",
    AssetVariationPolicy.LOCAL_ONLY.value: "仅本地",
}

LEVEL_LABELS: Dict[str, str] = {
    DocumentLevel.GROUP.value: "集团制度",
    DocumentLevel.COMPANY.value: "公司制度",
    DocumentLevel.PLANT.value: "工厂制度",
    DocumentLevel.LINE.value: "产线规定",
    DocumentLevel.PROCESS.value: "流程文件",
}

_VERSION_RE = re.compile(r"^\d+\.\d+$")


class ProcessDocumentError(ValueError):
    """业务规则拒绝；API 层转成 400/409。"""


# ------------------------------------------------------------------ 文档


def require_document(db: Session, document_id: int) -> ProcessDocument:
    document = db.get(ProcessDocument, document_id)
    if document is None:
        raise ProcessDocumentError(f"流程标准文件 {document_id} 不存在")
    return document


def require_process(db: Session, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ProcessDocumentError(f"流程节点 {process_id} 不存在")
    return process


def validate_node_key(db: Session, process_id: int, node_key: Optional[str]) -> None:
    """活动级标准文件必须指向当前设计模型里真实存在的节点。"""
    if not node_key:
        return
    nodes, _edges = model_service.rows_from_snapshot(
        process_id, model_service.current_snapshot(db, process_id)
    )
    if not any(node.node_key == node_key for node in nodes):
        raise ProcessDocumentError(f"活动 {node_key} 不存在于该流程")


def next_document_code(db: Session, process_code: str) -> str:
    prefix = f"PD-{process_code}-"
    existing = db.scalars(
        select(ProcessDocument.code).where(ProcessDocument.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:02d}"


def create_document(db: Session, data: dict) -> ProcessDocument:
    require_process(db, data["process_id"])
    document = ProcessDocument(**data)
    db.add(document)
    db.flush()
    return document


# ------------------------------------------------------------------ 版本


def create_version(
    db: Session,
    document: ProcessDocument,
    data: dict,
    user: User,
    file_meta: Optional[dict] = None,
    *,
    source_deliverable_version_id: Optional[int] = None,
) -> ProcessDocumentVersion:
    label = data["version_label"]
    if not _VERSION_RE.match(label):
        raise ProcessDocumentError("版本号必须形如 3.2（major.minor）")
    exists = db.scalar(
        select(func.count())
        .select_from(ProcessDocumentVersion)
        .where(
            ProcessDocumentVersion.document_id == document.id,
            ProcessDocumentVersion.version_label == label,
        )
    )
    if exists:
        raise ProcessDocumentError(f"版本 v{label} 已存在，版本只追加不覆盖")

    base_id = data.get("base_version_id") or document.current_version_id
    if base_id is not None:
        base = db.get(ProcessDocumentVersion, base_id)
        if base is None or base.document_id != document.id:
            raise ProcessDocumentError("base_version_id 不属于该标准文件")

    source_base_id = data.get("source_base_version_id")
    if source_base_id is None and document.variant_of_document_id:
        source_base_id = document.variant_base_version_id

    version = ProcessDocumentVersion(
        document_id=document.id,
        version_label=label,
        status=DeliverableStatus.DRAFT.value,
        note=data.get("note"),
        valid_from=data.get("valid_from"),
        base_version_id=base_id,
        source_deliverable_version_id=source_deliverable_version_id,
        source_base_version_id=source_base_id,
        created_by=user.display_name,
        created_by_id=user.id,
    )
    if file_meta:
        for field in (
            "file_name",
            "mime_type",
            "size_bytes",
            "checksum",
            "storage_backend",
            "storage_key",
        ):
            setattr(version, field, file_meta.get(field))
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    db.flush()
    return version


def transition_version(
    db: Session,
    document: ProcessDocument,
    version: ProcessDocumentVersion,
    target: str,
    user: User,
) -> ProcessDocumentVersion:
    allowed = deliverable_service.ALLOWED_TRANSITIONS.get(version.status, [])
    if target not in allowed:
        raise ProcessDocumentError(
            f"不允许从 {deliverable_service.STATUS_LABELS.get(version.status, version.status)} "
            f"变更为 {deliverable_service.STATUS_LABELS.get(target, target)}"
        )

    today = date.today()
    if target == DeliverableStatus.APPROVED.value:
        version.approved_by = user.display_name
        version.approved_by_id = user.id
        version.approved_at = utcnow()
        if version.valid_from is None:
            version.valid_from = today
    elif target == DeliverableStatus.EFFECTIVE.value:
        _supersede_others(db, document, version, today)
        version.valid_to = None
        if version.valid_from is None:
            version.valid_from = today
        document.current_version_id = version.id
        # 变基草稿生效后，才把文档声明的依据版本推进到新基线
        if document.variant_of_document_id and version.source_base_version_id:
            document.variant_base_version_id = version.source_base_version_id
    elif target in {DeliverableStatus.SUPERSEDED.value, DeliverableStatus.RETIRED.value}:
        version.valid_to = today
    elif target == DeliverableStatus.DRAFT.value:
        version.approved_by = None
        version.approved_by_id = None
        version.approved_at = None
        version.valid_from = None

    version.status = target
    if target == DeliverableStatus.RETIRED.value and document.current_version_id == version.id:
        _move_pointer_if_retired(db, document, version)
    db.flush()
    return version


def _supersede_others(
    db: Session, document: ProcessDocument, keep: ProcessDocumentVersion, today: date
) -> None:
    others = db.scalars(
        select(ProcessDocumentVersion).where(
            ProcessDocumentVersion.document_id == document.id,
            ProcessDocumentVersion.id != keep.id,
            ProcessDocumentVersion.status == DeliverableStatus.EFFECTIVE.value,
        )
    ).all()
    for other in others:
        other.status = DeliverableStatus.SUPERSEDED.value
        other.valid_to = today


def _move_pointer_if_retired(
    db: Session, document: ProcessDocument, retired: ProcessDocumentVersion
) -> None:
    replacement = db.scalar(
        select(ProcessDocumentVersion)
        .where(
            ProcessDocumentVersion.document_id == document.id,
            ProcessDocumentVersion.id != retired.id,
            ProcessDocumentVersion.status != DeliverableStatus.RETIRED.value,
        )
        .order_by(ProcessDocumentVersion.id.desc())
        .limit(1)
    )
    document.current_version_id = replacement.id if replacement else None


def effective_version(document: ProcessDocument) -> Optional[ProcessDocumentVersion]:
    for version in reversed(list(document.versions)):
        if version.status == DeliverableStatus.EFFECTIVE.value:
            return version
    return None


def effective_version_on(
    document: ProcessDocument, on_date: Optional[date] = None
) -> Optional[ProcessDocumentVersion]:
    """按日期解析生效版本：状态 EFFECTIVE 且在 valid_from/to 区间内。"""
    day = on_date or date.today()
    candidates = [
        version
        for version in document.versions
        if version.status == DeliverableStatus.EFFECTIVE.value
        and (version.valid_from is None or version.valid_from <= day)
        and (version.valid_to is None or version.valid_to >= day)
    ]
    return max(candidates, key=lambda version: version.id) if candidates else None


def validate_variant(
    db: Session, base: ProcessDocument, org_unit_id: Optional[int]
) -> ProcessDocumentVersion:
    """校验本地变体：只允许下级组织、上级必须已生效、锁定策略不允许变体。"""
    if not base.is_active:
        raise ProcessDocumentError("上级标准文件已停用，不能建立变体")
    if base.variation_policy == AssetVariationPolicy.LOCKED.value:
        raise ProcessDocumentError("该标准文件为锁定策略，不允许建立本地变体")
    if org_unit_id is None:
        raise ProcessDocumentError("本地变体必须指定所属组织")
    if base.org_unit_id == org_unit_id:
        raise ProcessDocumentError("变体必须建立在下级组织，不能与上级同组织")
    if base.org_unit_id is not None and base.org_unit_id not in org_scope.ancestor_ids(
        db, org_unit_id
    ):
        raise ProcessDocumentError("变体所属组织必须是上级标准文件所在组织的下级")
    base_version = effective_version_on(base)
    if base_version is None:
        raise ProcessDocumentError("上级标准还没有已生效版本，不能建立变体")
    return base_version


def visible_conditions(db: Session, org_unit_id: Optional[int]):
    """组织视角的可见范围：集团通用 + 本级 + 上级；LOCAL_ONLY 只对所属组织可见。"""
    if org_unit_id is None:
        return None
    ids = org_scope.ancestor_ids(db, org_unit_id)
    return and_(
        or_(ProcessDocument.org_unit_id.is_(None), ProcessDocument.org_unit_id.in_(ids)),
        or_(
            ProcessDocument.variation_policy != AssetVariationPolicy.LOCAL_ONLY.value,
            ProcessDocument.org_unit_id == org_unit_id,
        ),
    )


def effective_documents(
    db: Session,
    org_unit_id: int,
    process_id: Optional[int] = None,
    category: Optional[str] = None,
    on_date: Optional[date] = None,
) -> List[EffectiveDocumentOut]:
    """按「组织 + 流程 + 日期」解析有效版本；同一族取最具体的生效变体，否则向上继承。"""
    try:
        org_service.require_org(db, org_unit_id)
    except org_service.OrgError as exc:
        raise ProcessDocumentError(str(exc)) from exc
    stmt = (
        select(ProcessDocument)
        .options(
            joinedload(ProcessDocument.process),
            joinedload(ProcessDocument.org_unit),
            selectinload(ProcessDocument.versions),
        )
        .where(ProcessDocument.is_active.is_(True))
    )
    condition = visible_conditions(db, org_unit_id)
    if condition is not None:
        stmt = stmt.where(condition)
    if process_id is not None:
        stmt = stmt.where(ProcessDocument.process_id == process_id)
    if category is not None:
        stmt = stmt.where(ProcessDocument.category == category)
    documents = list(db.scalars(stmt).all())

    families: Dict[int, List[ProcessDocument]] = {}
    for document in documents:
        root = _family_root(db, document)
        families.setdefault(root.id, []).append(document)

    results: List[EffectiveDocumentOut] = []
    for candidates in families.values():
        # 组织越深越具体；同深度按 id 取最新
        candidates.sort(
            key=lambda doc: (
                doc.org_unit.path.count("/") if doc.org_unit else 0,
                doc.id,
            ),
            reverse=True,
        )
        chosen: Optional[ProcessDocument] = None
        version: Optional[ProcessDocumentVersion] = None
        for candidate in candidates:
            version = effective_version_on(candidate, on_date)
            if version is not None:
                chosen = candidate
                break
        if chosen is None or version is None:
            continue

        base = (
            db.get(ProcessDocument, chosen.variant_of_document_id)
            if chosen.variant_of_document_id
            else None
        )
        base_version = (
            db.get(ProcessDocumentVersion, chosen.variant_base_version_id)
            if chosen.variant_base_version_id
            else None
        )
        scope = org_service.resolve_scope(chosen.org_unit)
        policy = POLICY_LABELS.get(chosen.variation_policy, chosen.variation_policy)
        inherited = chosen.org_unit_id != org_unit_id
        if chosen.variant_of_document_id:
            explanation = f"使用{scope['scope_label']}变体 v{version.version_label}"
            if base is not None:
                explanation += f"，依据 {base.code}"
            if base_version is not None:
                explanation += f" v{base_version.version_label}"
        elif inherited:
            explanation = f"本级无生效版本，继承{scope['scope_label']} v{version.version_label}"
        else:
            explanation = f"{scope['scope_label']}本级生效 v{version.version_label}"
        explanation += f"（{policy}）"

        results.append(
            EffectiveDocumentOut(
                document_id=chosen.id,
                code=chosen.code,
                title=chosen.title,
                category=chosen.category,
                category_label=CATEGORY_LABELS.get(chosen.category, chosen.category),
                process_id=chosen.process_id,
                process_code=chosen.process.code if chosen.process else None,
                process_name=chosen.process.name if chosen.process else None,
                org_unit_id=chosen.org_unit_id,
                scope_label=scope["scope_label"],
                variation_policy=chosen.variation_policy,
                variation_policy_label=policy,
                is_variant=chosen.variant_of_document_id is not None,
                base_document_id=base.id if base else None,
                base_document_code=base.code if base else None,
                base_version_display=(f"v{base_version.version_label}" if base_version else None),
                inherited=inherited,
                source_org_code=chosen.org_unit.code if chosen.org_unit else None,
                source_org_name=chosen.org_unit.name if chosen.org_unit else None,
                version=version_out(db, version),
                explanation=explanation,
            )
        )
    results.sort(key=lambda row: (row.process_code or "", row.title))
    return results


def _family_root(db: Session, document: ProcessDocument) -> ProcessDocument:
    current = document
    seen: set = set()
    while current.variant_of_document_id and current.id not in seen:
        seen.add(current.id)
        parent = db.get(ProcessDocument, current.variant_of_document_id)
        if parent is None:
            break
        current = parent
    return current


# ------------------------------------------------------------------ 升级影响与变基

IMPACT_STATUS_LABELS: Dict[str, str] = {
    "UP_TO_DATE": "已对齐",
    "BEHIND_MINOR": "落后 minor",
    "BEHIND_MAJOR": "落后 major",
    "NO_BASE": "未登记基线",
    "NO_EFFECTIVE": "无生效版本",
}


def upgrade_impact(db: Session, document: ProcessDocument) -> DocumentImpactOut:
    """上级发布新版本后：哪些变体落后、哪些项目交付物仍固定旧版。"""
    new_base = effective_version_on(document)
    if new_base is None:
        raise ProcessDocumentError("该标准文件还没有已生效版本")

    variants = list(
        db.scalars(
            select(ProcessDocument)
            .options(
                joinedload(ProcessDocument.org_unit),
                selectinload(ProcessDocument.versions),
            )
            .where(
                ProcessDocument.variant_of_document_id == document.id,
                ProcessDocument.is_active.is_(True),
            )
            .order_by(ProcessDocument.org_unit_id, ProcessDocument.id)
        ).all()
    )

    items: List[VariantImpactOut] = []
    for variant in variants:
        current = effective_version_on(variant)
        old_id = (
            current.source_base_version_id
            if current and current.source_base_version_id
            else variant.variant_base_version_id
        )
        old_base = db.get(ProcessDocumentVersion, old_id) if old_id else None

        if current is None:
            status = "NO_EFFECTIVE"
        elif old_id == new_base.id:
            status = "UP_TO_DATE"
        elif old_base is None:
            status = "NO_BASE"
        else:
            old_major = int(old_base.version_label.split(".")[0])
            new_major = int(new_base.version_label.split(".")[0])
            status = "BEHIND_MAJOR" if new_major > old_major else "BEHIND_MINOR"

        scope = org_service.resolve_scope(variant.org_unit)
        fields = [
            DocumentFieldDiff(
                field="title",
                label="标题",
                base_old=document.title,
                base_new=document.title,
                variant=variant.title,
            ),
            DocumentFieldDiff(
                field="category",
                label="类型",
                base_old=CATEGORY_LABELS.get(document.category, document.category),
                base_new=CATEGORY_LABELS.get(document.category, document.category),
                variant=CATEGORY_LABELS.get(variant.category, variant.category),
            ),
            DocumentFieldDiff(
                field="variation_policy",
                label="变体策略",
                base_old=POLICY_LABELS.get(document.variation_policy, document.variation_policy),
                base_new=POLICY_LABELS.get(document.variation_policy, document.variation_policy),
                variant=POLICY_LABELS.get(variant.variation_policy, variant.variation_policy),
            ),
            DocumentFieldDiff(
                field="scope",
                label="适用范围",
                base_old=org_service.resolve_scope(document.org_unit)["scope_label"],
                base_new=org_service.resolve_scope(document.org_unit)["scope_label"],
                variant=scope["scope_label"],
            ),
            DocumentFieldDiff(
                field="version_note",
                label="上级版本说明",
                base_old=old_base.note if old_base else None,
                base_new=new_base.note,
                variant=current.note if current else None,
            ),
            DocumentFieldDiff(
                field="checksum",
                label="上级文件校验",
                base_old=old_base.checksum[:12] + "…" if old_base and old_base.checksum else None,
                base_new=new_base.checksum[:12] + "…" if new_base.checksum else None,
                variant=current.checksum[:12] + "…" if current and current.checksum else None,
            ),
        ]
        items.append(
            VariantImpactOut(
                document_id=variant.id,
                code=variant.code,
                title=variant.title,
                org_unit_id=variant.org_unit_id,
                scope_label=scope["scope_label"],
                variation_policy_label=POLICY_LABELS.get(
                    variant.variation_policy, variant.variation_policy
                ),
                current_version=version_out(db, current) if current else None,
                base_old_version_display=(f"v{old_base.version_label}" if old_base else None),
                base_new_version_display=f"v{new_base.version_label}",
                status=status,
                status_label=IMPACT_STATUS_LABELS[status],
                requires_reapproval=status != "UP_TO_DATE",
                changed_fields=fields,
            )
        )

    version_ids = [version.id for version in document.versions]
    references: List[DeliverableReferenceOut] = []
    if version_ids:
        rows = db.execute(
            select(DeliverableVersion, DeliverableInstance, Project, DeliverableDefinition)
            .join(DeliverableInstance, DeliverableInstance.id == DeliverableVersion.instance_id)
            .join(Project, Project.id == DeliverableInstance.project_id)
            .join(
                DeliverableDefinition,
                DeliverableDefinition.id == DeliverableInstance.definition_id,
            )
            .where(
                DeliverableVersion.source_document_version_id.in_(version_ids),
                DeliverableVersion.status.in_(
                    [DeliverableStatus.APPROVED.value, DeliverableStatus.EFFECTIVE.value]
                ),
            )
            .order_by(Project.code, DeliverableVersion.id)
        ).all()
        by_id = {version.id: version for version in document.versions}
        for version, _instance, project, definition in rows:
            referenced = by_id.get(version.source_document_version_id)
            references.append(
                DeliverableReferenceOut(
                    deliverable_version_id=version.id,
                    project_id=project.id,
                    project_code=project.code,
                    definition_code=definition.code,
                    version_label=f"R{version.version_no}",
                    status=version.status,
                    status_label=deliverable_service.STATUS_LABELS.get(
                        version.status, version.status
                    ),
                    source_version_display=(f"v{referenced.version_label}" if referenced else None),
                )
            )

    return DocumentImpactOut(
        document_id=document.id,
        code=document.code,
        title=document.title,
        base_effective_version=version_out(db, new_base),
        variants=items,
        project_references=references,
    )


def rebase_variant(
    db: Session,
    document: ProcessDocument,
    base_version: ProcessDocumentVersion,
    acknowledge_major: bool,
    user: User,
    note: Optional[str] = None,
) -> ProcessDocumentVersion:
    """变基：基于上级新版本生成变体草稿，审批生效后才推进依据版本。"""
    if document.variant_of_document_id is None:
        raise ProcessDocumentError("只有本地变体才能变基")
    base_document = db.get(ProcessDocument, document.variant_of_document_id)
    if base_document is None:
        raise ProcessDocumentError("上级标准文件不存在")
    if base_version.document_id != base_document.id:
        raise ProcessDocumentError("目标版本不属于上级标准文件")
    if base_version.status != DeliverableStatus.EFFECTIVE.value:
        raise ProcessDocumentError("只能变基到已生效的上级版本")

    current = effective_version_on(document)
    if current is None:
        raise ProcessDocumentError("变体还没有已生效版本，无法变基")
    if not current.storage_key:
        raise ProcessDocumentError("变体当前版本没有文件，无法变基")

    old_base_id = current.source_base_version_id or document.variant_base_version_id
    old_base = db.get(ProcessDocumentVersion, old_base_id) if old_base_id else None
    if old_base is not None and old_base.id == base_version.id:
        raise ProcessDocumentError("变体已基于该上级版本")
    pending = db.scalar(
        select(ProcessDocumentVersion).where(
            ProcessDocumentVersion.document_id == document.id,
            ProcessDocumentVersion.source_base_version_id == base_version.id,
            ProcessDocumentVersion.status.in_(
                [
                    DeliverableStatus.DRAFT.value,
                    DeliverableStatus.IN_REVIEW.value,
                    DeliverableStatus.APPROVED.value,
                ]
            ),
        )
    )
    if pending is not None:
        raise ProcessDocumentError("已有基于该版本的变基草稿，请先完成审批")

    major_changed = old_base is None or (
        int(base_version.version_label.split(".")[0]) > int(old_base.version_label.split(".")[0])
    )
    if major_changed and not acknowledge_major:
        raise ProcessDocumentError("上级 major 升级需要重新评估，请显式确认后再变基")

    label = _next_free_label(db, document, current.version_label)
    file_meta = _copy_storage(
        current.storage_key,
        f"process-documents/{document.id}",
        current.file_name or f"{document.code}-v{label}",
        current.mime_type,
    )
    note_text = f"基于上级 {base_document.code} v{base_version.version_label} 变基，待复核" + (
        f"：{note}" if note else ""
    )
    try:
        return create_version(
            db,
            document,
            {
                "version_label": label,
                "note": note_text,
                "base_version_id": current.id,
                "source_base_version_id": base_version.id,
            },
            user,
            file_meta,
        )
    except Exception:
        storage_service.get_storage().delete(file_meta["storage_key"])
        raise


def _next_free_label(db: Session, document: ProcessDocument, current_label: str) -> str:
    major, minor = current_label.split(".")
    candidate = int(minor) + 1
    used = {version.version_label for version in document.versions}
    while f"{major}.{candidate}" in used:
        candidate += 1
    return f"{major}.{candidate}"


# ------------------------------------------------------------------ 跨域动作


def copy_to_deliverable(
    db: Session,
    document: ProcessDocument,
    version: ProcessDocumentVersion,
    instance: DeliverableInstance,
    project: Project,
    user: User,
    *,
    title: Optional[str] = None,
    note: Optional[str] = None,
) -> DeliverableVersion:
    """把生效的标准文件复制成项目交付物版本，记录来源文档版本。"""
    if version.status != DeliverableStatus.EFFECTIVE.value:
        raise ProcessDocumentError("只能复制已生效的标准文件版本")
    if version.storage_key is None:
        raise ProcessDocumentError("该标准文件版本没有文件，无法复制")
    if not process_scope.is_document_applicable(db, document.process_id, project.process_id):
        raise ProcessDocumentError("该标准文件不属于本项目流程或其上级流程")

    file_meta = _copy_storage(
        version.storage_key,
        f"deliverables/{project.id}/{instance.id}",
        version.file_name or f"{document.code}.bin",
        version.mime_type,
    )
    payload = {
        "title": title or document.title,
        "note": note
        or f"基于流程标准文件 {document.code} v{version.version_label}"
        f"（{CATEGORY_LABELS.get(document.category, document.category)}）",
        "source_document_version_id": version.id,
        **file_meta,
    }
    try:
        return deliverable_service.create_version(db, instance, payload, user)
    except Exception:
        storage_service.get_storage().delete(file_meta["storage_key"])
        raise


def promote_deliverable(
    db: Session,
    document: ProcessDocument,
    deliverable_version: DeliverableVersion,
    version_label: str,
    user: User,
    note: Optional[str] = None,
) -> ProcessDocumentVersion:
    """把项目交付物版本晋升为标准文件草稿；审批仍走标准文件的版本状态机。"""
    if deliverable_version.status not in {
        DeliverableStatus.APPROVED.value,
        DeliverableStatus.EFFECTIVE.value,
    }:
        raise ProcessDocumentError("只有已批准或已生效的项目交付物版本才能晋升")
    if not deliverable_version.storage_key:
        raise ProcessDocumentError("该交付物版本没有文件，无法晋升")
    if not _VERSION_RE.match(version_label):
        raise ProcessDocumentError("目标版本号必须形如 3.3（major.minor）")

    instance = db.get(DeliverableInstance, deliverable_version.instance_id)
    project = db.get(Project, instance.project_id) if instance else None
    if project is None:
        raise ProcessDocumentError("交付物所属项目不存在")
    if project.process_id is None:
        raise ProcessDocumentError("项目未关联流程，不能晋升为标准文件")
    if not process_scope.is_document_applicable(db, document.process_id, project.process_id):
        raise ProcessDocumentError("该标准文件不属于本项目流程或其上级流程")

    file_meta = _copy_storage(
        deliverable_version.storage_key,
        f"process-documents/{document.id}",
        deliverable_version.file_name or f"{document.code}-v{version_label}",
        deliverable_version.mime_type,
    )
    try:
        return create_version(
            db,
            document,
            {"version_label": version_label, "note": note},
            user,
            file_meta,
            source_deliverable_version_id=deliverable_version.id,
        )
    except Exception:
        storage_service.get_storage().delete(file_meta["storage_key"])
        raise


def _copy_storage(
    source_key: str, prefix: str, filename: str, mime_type: Optional[str] = None
) -> dict:
    storage = storage_service.get_storage()
    try:
        source = storage.open(source_key)
    except FileNotFoundError as exc:
        raise ProcessDocumentError("源文件不存在或已被清理") from exc
    try:
        key = storage_service.build_key(prefix, filename)
        digest, size = storage.save(key, source, storage_service.max_bytes())
    finally:
        source.close()
    return {
        "file_name": filename,
        "mime_type": mime_type,
        "size_bytes": size,
        "checksum": digest,
        "storage_backend": "local",
        "storage_key": key,
    }


# ------------------------------------------------------------------ 出参


def _source_label(db: Session, version_id: Optional[int]) -> Optional[str]:
    if version_id is None:
        return None
    row = db.execute(
        select(DeliverableVersion, DeliverableInstance, Project, DeliverableDefinition)
        .join(DeliverableInstance, DeliverableInstance.id == DeliverableVersion.instance_id)
        .join(Project, Project.id == DeliverableInstance.project_id)
        .join(DeliverableDefinition, DeliverableDefinition.id == DeliverableInstance.definition_id)
        .where(DeliverableVersion.id == version_id)
    ).first()
    if row is None:
        return f"交付物版本 #{version_id}"
    version, _instance, project, definition = row
    return f"{project.code} · {definition.code} · R{version.version_no}"


def version_out(db: Session, version: ProcessDocumentVersion) -> ProcessDocumentVersionOut:
    has_file = bool(version.storage_key)
    preview_kind = (
        preview_service.preview_kind(version.file_name, version.mime_type) if has_file else None
    )
    source_base = (
        db.get(ProcessDocumentVersion, version.source_base_version_id)
        if version.source_base_version_id
        else None
    )
    return ProcessDocumentVersionOut(
        id=version.id,
        document_id=version.document_id,
        version_label=version.version_label,
        version_display=f"v{version.version_label}",
        status=version.status,
        status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
        note=version.note,
        file_name=version.file_name,
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        checksum=version.checksum,
        storage_backend=version.storage_backend,
        has_file=has_file,
        download_url=(
            f"{settings.api_prefix}/process-documents/{version.document_id}"
            f"/versions/{version.id}/download"
            if has_file
            else None
        ),
        preview_url=(
            f"{settings.api_prefix}/process-documents/{version.document_id}"
            f"/versions/{version.id}/preview"
            if preview_kind
            else None
        ),
        preview_kind=preview_kind,
        base_version_id=version.base_version_id,
        source_deliverable_version_id=version.source_deliverable_version_id,
        source_label=_source_label(db, version.source_deliverable_version_id),
        source_base_version_id=version.source_base_version_id,
        source_base_version_display=(f"v{source_base.version_label}" if source_base else None),
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        created_at=version.created_at,
    )


def document_out(db: Session, document: ProcessDocument) -> ProcessDocumentOut:
    versions = list(document.versions)
    current = next((v for v in versions if v.id == document.current_version_id), None)
    effective = next(
        (v for v in reversed(versions) if v.status == DeliverableStatus.EFFECTIVE.value), None
    )
    variant_of = (
        db.get(ProcessDocument, document.variant_of_document_id)
        if document.variant_of_document_id
        else None
    )
    base_version = (
        db.get(ProcessDocumentVersion, document.variant_base_version_id)
        if document.variant_base_version_id
        else None
    )
    return ProcessDocumentOut(
        id=document.id,
        process_id=document.process_id,
        process_code=document.process.code if document.process else None,
        process_name=document.process.name if document.process else None,
        node_key=document.node_key,
        code=document.code,
        title=document.title,
        category=document.category,
        category_label=CATEGORY_LABELS.get(document.category, document.category),
        description=document.description,
        level=document.level,
        level_label=LEVEL_LABELS.get(document.level, document.level),
        legal_entity=document.legal_entity,
        plant=document.plant,
        product_family=document.product_family,
        language=document.language,
        control_points=document.control_points,
        exception_terms=document.exception_terms,
        owner=document.owner,
        owner_user_id=document.owner_user_id,
        **org_service.resolve_scope(document.org_unit),
        variation_policy=document.variation_policy,
        variation_policy_label=POLICY_LABELS.get(
            document.variation_policy, document.variation_policy
        ),
        variant_of_document_id=document.variant_of_document_id,
        variant_of_code=variant_of.code if variant_of else None,
        variant_base_version_id=document.variant_base_version_id,
        variant_base_version_display=(f"v{base_version.version_label}" if base_version else None),
        is_active=document.is_active,
        current_version_id=document.current_version_id,
        current_version=version_out(db, current) if current else None,
        effective_version=version_out(db, effective) if effective else None,
        version_count=len(versions),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def document_detail(db: Session, document: ProcessDocument) -> ProcessDocumentDetail:
    base = document_out(db, document)
    return ProcessDocumentDetail(
        **base.model_dump(),
        versions=[version_out(db, v) for v in document.versions],
    )


def meta() -> ProcessDocumentMeta:
    return ProcessDocumentMeta(
        category_labels=CATEGORY_LABELS,
        status_labels=deliverable_service.STATUS_LABELS,
        transitions=deliverable_service.ALLOWED_TRANSITIONS,
        variation_policy_labels=POLICY_LABELS,
        level_labels=LEVEL_LABELS,
    )
