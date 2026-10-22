"""一致性审计：扫描资产与项目交付物，生成可跟踪的治理待办。

去重键是 (type, entity_type, entity_id)：
- 新问题创建 OPEN；
- 老问题刷新 last_seen，已读后不重复造新记录；
- 条件消失自动 RESOLVED；
- 人工可 IGNORED，扫描时保留但不再提醒。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.timeutil import utcnow
from app.models.deliverable import DeliverableDefinition, DeliverableInstance, DeliverableVersion
from app.models.enums import DeliverableStatus
from app.models.governance import GovernanceFinding
from app.models.org import OrgUnit
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project
from app.models.tool_template import ToolTemplate
from app.models.user import User
from app.schemas.baseline import AuditScanResult, FindingOut
from app.services import notifications as notification_service
from app.services import process_document as document_service
from app.services import tool_template as template_service

TYPE_LABELS: Dict[str, str] = {
    "STALE_VARIANT": "变体落后",
    "FROZEN_REFERENCE": "交付物固定旧版",
    "NO_EFFECTIVE": "资产未生效",
    "REVIEW_OVERDUE": "模板复审逾期",
}

STATUS_LABELS: Dict[str, str] = {
    "OPEN": "待处理",
    "RESOLVED": "已解决",
    "IGNORED": "已忽略",
}

SEVERITY_LABELS: Dict[str, str] = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}
_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def finding_out(db: Session, row: GovernanceFinding) -> FindingOut:
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    org = db.get(OrgUnit, row.org_unit_id) if row.org_unit_id else None
    return FindingOut(
        id=row.id,
        type=row.type,
        type_label=TYPE_LABELS.get(row.type, row.type),
        severity=row.severity,
        severity_label=SEVERITY_LABELS.get(row.severity, row.severity),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        title=row.title,
        detail=row.detail,
        org_unit_id=row.org_unit_id,
        org_unit_name=org.name if org else None,
        owner_user_id=row.owner_user_id,
        owner_name=owner.display_name if owner else None,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        detected_at=row.detected_at,
        last_seen_at=row.last_seen_at,
        resolved_at=row.resolved_at,
    )


def _collect(db: Session) -> Dict[Tuple[str, str, int], dict]:
    findings: Dict[Tuple[str, str, int], dict] = {}

    def add(
        type_: str,
        severity: str,
        entity_type: str,
        entity_id: int,
        title: str,
        detail: str,
        *,
        org_unit_id: Optional[int] = None,
        owner_user_id: Optional[int] = None,
    ) -> None:
        key = (type_, entity_type, entity_id)
        existing = findings.get(key)
        if existing and _SEVERITY_RANK[existing["severity"]] >= _SEVERITY_RANK[severity]:
            return
        findings[key] = {
            "type": type_,
            "severity": severity,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "detail": detail,
            "org_unit_id": org_unit_id,
            "owner_user_id": owner_user_id,
        }

    documents = list(
        db.scalars(
            select(ProcessDocument)
            .options(
                joinedload(ProcessDocument.org_unit),
                selectinload(ProcessDocument.versions),
            )
            .where(ProcessDocument.is_active.is_(True))
        ).all()
    )
    for document in documents:
        current = document_service.effective_version_on(document)
        if document.variant_of_document_id:
            base = db.get(ProcessDocument, document.variant_of_document_id)
            latest_base = document_service.effective_version_on(base) if base else None
            old_id = (
                current.source_base_version_id
                if current and current.source_base_version_id
                else document.variant_base_version_id
            )
            old_base = db.get(ProcessDocumentVersion, old_id) if old_id else None
            owner = document.owner_user_id or (base.owner_user_id if base else None)
            if current is None:
                add(
                    "STALE_VARIANT",
                    "HIGH",
                    "process_document",
                    document.id,
                    f"变体没有生效版本：{document.title}",
                    "变体只有草稿或尚未上传版本",
                    org_unit_id=document.org_unit_id,
                    owner_user_id=owner,
                )
            elif latest_base is None:
                add(
                    "STALE_VARIANT",
                    "HIGH",
                    "process_document",
                    document.id,
                    f"上级标准没有生效版本：{document.title}",
                    f"上级 {base.code if base else '—'} 尚无生效版本",
                    org_unit_id=document.org_unit_id,
                    owner_user_id=owner,
                )
            elif old_id != latest_base.id:
                major = old_base is None or (
                    int(latest_base.version_label.split(".")[0])
                    > int(old_base.version_label.split(".")[0])
                )
                add(
                    "STALE_VARIANT",
                    "HIGH" if major else "MEDIUM",
                    "process_document",
                    document.id,
                    f"变体落后：{document.title}",
                    f"依据 {('v' + old_base.version_label) if old_base else '未登记'}，"
                    f"上级最新 v{latest_base.version_label}",
                    org_unit_id=document.org_unit_id,
                    owner_user_id=owner,
                )
        elif current is None:
            add(
                "NO_EFFECTIVE",
                "MEDIUM",
                "process_document",
                document.id,
                f"标准文件未生效：{document.title}",
                "只有草稿或尚未上传版本，项目无法复制",
                org_unit_id=document.org_unit_id,
                owner_user_id=document.owner_user_id,
            )

    templates = list(
        db.scalars(
            select(ToolTemplate)
            .options(
                joinedload(ToolTemplate.org_unit),
                selectinload(ToolTemplate.versions),
            )
            .where(ToolTemplate.is_active.is_(True))
        ).all()
    )
    today = date.today()
    for template in templates:
        if template_service.effective_version(template) is None:
            add(
                "NO_EFFECTIVE",
                "MEDIUM",
                "tool_template",
                template.id,
                f"模板未生效：{template.name}",
                "只有草稿或尚未上传版本",
                org_unit_id=template.org_unit_id,
                owner_user_id=template.owner_user_id,
            )
        if template.review_date and template.review_date < today:
            add(
                "REVIEW_OVERDUE",
                "LOW",
                "tool_template",
                template.id,
                f"模板复审逾期：{template.name}",
                f"复审日期 {template.review_date}",
                org_unit_id=template.org_unit_id,
                owner_user_id=template.owner_user_id,
            )

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
        add(
            "FROZEN_REFERENCE",
            "MEDIUM",
            "deliverable_version",
            version.id,
            f"交付物固定旧版：{project.code} · {definition.code}",
            f"来源 v{source.version_label}，标准现行 v{latest.version_label}",
            org_unit_id=document.org_unit_id if document else None,
            owner_user_id=project.owner_user_id,
        )

    return findings


def scan(db: Session) -> AuditScanResult:
    """执行一次一致性扫描；调用方负责 commit。"""
    current = _collect(db)
    now = utcnow()
    existing = {
        (row.type, row.entity_type, row.entity_id): row
        for row in db.scalars(select(GovernanceFinding)).all()
    }
    created = updated = ignored = resolved = notified = 0
    for key, draft in current.items():
        row = existing.get(key)
        if row is not None:
            row.last_seen_at = now
            if row.status == "IGNORED":
                ignored += 1
                continue
            row.title = draft["title"]
            row.detail = draft["detail"]
            row.severity = draft["severity"]
            row.org_unit_id = draft["org_unit_id"]
            row.owner_user_id = draft["owner_user_id"]
            if row.status == "RESOLVED":
                row.status = "OPEN"
                row.resolved_at = None
                _notify(db, row)
                notified += 1
            updated += 1
            continue
        row = GovernanceFinding(
            type=draft["type"],
            severity=draft["severity"],
            entity_type=draft["entity_type"],
            entity_id=draft["entity_id"],
            title=draft["title"],
            detail=draft["detail"],
            org_unit_id=draft["org_unit_id"],
            owner_user_id=draft["owner_user_id"],
            status="OPEN",
            detected_at=now,
            last_seen_at=now,
        )
        db.add(row)
        db.flush()
        _notify(db, row)
        created += 1
        notified += 1

    for key, row in existing.items():
        if key not in current and row.status != "RESOLVED":
            row.status = "RESOLVED"
            row.resolved_at = now
            resolved += 1

    db.flush()
    return AuditScanResult(
        scanned=len(current),
        created=created,
        updated=updated,
        ignored=ignored,
        resolved=resolved,
        notified=notified,
    )


def _notify(db: Session, row: GovernanceFinding) -> None:
    notification_service.notify(
        db,
        row.owner_user_id,
        "GOVERNANCE_FINDING",
        f"治理待办：{TYPE_LABELS.get(row.type, row.type)} · {row.title}",
        row.detail,
        link="deliverables",
        entity_type="governance_finding",
        entity_id=row.id,
    )


def list_findings(
    db: Session,
    status: Optional[str] = None,
    type_: Optional[str] = None,
    limit: int = 200,
) -> List[GovernanceFinding]:
    stmt = select(GovernanceFinding)
    if status:
        stmt = stmt.where(GovernanceFinding.status == status)
    if type_:
        stmt = stmt.where(GovernanceFinding.type == type_)
    rows = list(db.scalars(stmt).all())
    rows.sort(
        key=lambda row: (_SEVERITY_RANK.get(row.severity, 0), row.last_seen_at or utcnow()),
        reverse=True,
    )
    return rows[:limit]


def set_status(db: Session, row: GovernanceFinding, status: str) -> GovernanceFinding:
    row.status = status
    row.resolved_at = None
    db.flush()
    return row


def summary(db: Session) -> Dict[str, int]:
    rows = db.execute(
        select(GovernanceFinding.type, func.count(GovernanceFinding.id))
        .where(GovernanceFinding.status == "OPEN")
        .group_by(GovernanceFinding.type)
    ).all()
    return {type_: count for type_, count in rows}


def open_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(GovernanceFinding)
            .where(GovernanceFinding.status == "OPEN")
        )
        or 0
    )
