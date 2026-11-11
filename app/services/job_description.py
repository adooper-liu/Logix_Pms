"""岗位责任书：只读编译原职责与固定来源，不生成平行责任台账。"""

import hashlib
import json
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import Position
from app.models.process import ProcessArch
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import User
from app.schemas.job_description import JobDescriptionPreviewOut
from app.schemas.position_coverage import CoverageGapOut
from app.services import (
    asset_graph,
    binding_readiness,
    binding_snapshot,
    org_access,
    position_coverage,
)
from app.services.job_description_render import render, row_html

RULE_VERSION = "job-description/v1"


def input_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def preview(
    db: Session,
    position_id: int,
    user: User,
    period: Optional[date] = None,
    *,
    application_url: Optional[str] = None,
) -> JobDescriptionPreviewOut:
    coverage = position_coverage.coverage(db, position_id, user, period)
    published = position_coverage.coverage(db, position_id, user, period, model_basis="PUBLISHED")
    current_ids = {p.id for p in coverage.processes}
    for source in published.processes:
        if source.id not in current_ids:
            coverage.processes.append(source)
            coverage.gaps.append(
                CoverageGapOut(
                    code="MODEL_DIFFERS",
                    message="已发布职责在工作版中被移除，需先核对模型版本",
                    process_id=source.id,
                )
            )
    row_keys = {(a.process_id, a.activity_id) for a in coverage.activities}
    coverage.activities += [
        a for a in published.activities if (a.process_id, a.activity_id) not in row_keys
    ]
    if application_url:
        base = application_url.rstrip("/") + "/"
        for activity in coverage.activities:
            activity.designer_url = base + activity.designer_url
    position = db.get(Position, position_id)
    position_data = {
        "id": position.id,
        "code": position.code,
        "name": position.name,
        "description": position.description,
        "org_unit_id": position.org_unit_id,
        "org_unit_name": position.org_unit_name,
        "is_active": position.is_active,
    }

    def relevant_gap(gap):
        if gap.process_id is None:
            return True
        related = [a for a in coverage.activities if a.process_id == gap.process_id]
        if gap.activity_id is not None:
            return any(a.activity_id == gap.activity_id for a in related)
        if gap.node_key:
            return any(gap.node_key in a.node_keys for a in related)
        # 流程事项不自动分配给任意岗位；来源身份等流程缺口仍保留。
        return gap.code != "UNMAPPED_ROLE" and bool(related)

    coverage.unmapped_roles = [g for g in coverage.unmapped_roles if relevant_gap(g)]
    coverage.gaps = [g for g in coverage.gaps if relevant_gap(g)]
    gaps = list(coverage.gaps) + list(coverage.unmapped_roles)
    if not position.is_active:
        gaps.append(CoverageGapOut(code="POSITION_INACTIVE", message="岗位已停用"))
    sources = []
    published_bindings = []
    facets = []
    binding_gates = []
    for process_info in coverage.processes:
        process = db.get(ProcessArch, process_info.id)
        version = asset_graph.published_model(db, process)
        relevant_ids = {
            row.activity_id for row in coverage.activities if row.process_id == process.id
        }
        if version is None:
            gaps.append(
                CoverageGapOut(
                    code="MODEL_NOT_PUBLISHED",
                    message="参与流程没有已发布模型",
                    process_id=process.id,
                )
            )
        elif process_info.model_version_id != version.id:
            gaps.append(
                CoverageGapOut(
                    code="MODEL_DIFFERS",
                    message="当前职责诊断基于工作版，与发布版本不同",
                    process_id=process.id,
                )
            )
        if version:
            current = binding_snapshot.activity_scope(
                binding_snapshot.capture(db, process, version), relevant_ids
            )
            consistency = binding_snapshot.compare(
                current, binding_snapshot.activity_scope(version.binding_snapshot, relevant_ids)
            )
            if consistency != "CONFIRMED":
                gaps.append(
                    CoverageGapOut(
                        code="BINDINGS_NOT_CONFIRMED",
                        message="发布绑定依据缺失或已变化，请在设计器核对",
                        process_id=process.id,
                    )
                )
            # 输出只用原来源可见解析，固定指纹不含原受限正文。
            source = {
                "process_id": process.id,
                "model_version_id": version.id,
                "binding_hash": input_hash(current["activities"]),
                "consistency": consistency,
            }
            sources.append(source)
        bindings = binding_readiness.activity_bindings(
            db,
            process.id,
            user,
            model_version_id=version.id if version else None,
            activity_ids=relevant_ids,
        )
        if version:
            published_bindings.append(bindings.model_dump(mode="json"))
        if not org_access.unrestricted(user):
            full = binding_readiness.activity_bindings(
                db,
                process.id,
                model_version_id=version.id if version else None,
                activity_ids=relevant_ids,
            )
            if [a.model_dump(mode="json") for a in full.activities] != [
                a.model_dump(mode="json") for a in bindings.activities
            ]:
                gaps.append(
                    CoverageGapOut(
                        code="SOURCE_RESTRICTED",
                        message="部分编译依据受限，不能确认责任书完整性",
                        process_id=process.id,
                    )
                )
        relevant_ids = {
            row.activity_id for row in coverage.activities if row.process_id == process.id
        }
        gate = binding_readiness.binding_gate(
            db,
            process.id,
            user,
            profile="PERFORMANCE",
            model_version_id=version.id if version else None,
            activity_ids=relevant_ids,
        )
        binding_gates.append(gate)
        for activity in coverage.activities:
            if activity.process_id == process.id:
                activity.binding_consistency = gate.consistency
        for blocker in gate.blockers:
            gaps.append(
                CoverageGapOut(code=blocker.code, message=blocker.message, process_id=process.id)
            )
        facets.extend(
            row.model_dump(mode="json")
            for row in bindings.activities
            if row.activity_id in relevant_ids
        )
    roles = []
    role_ids = {r.role_id for a in coverage.activities for r in a.raci}
    for data in published_bindings:
        for activity in data["activities"]:
            for facet in activity["facets"]:
                for ref in facet["refs"]:
                    if ref["kind"] == "RACI" and ref.get("id"):
                        assignment = db.get(RaciAssignment, ref["id"])
                        if assignment:
                            role_ids.add(assignment.role_id)
    for role in db.scalars(
        select(GovernanceRole)
        .where(GovernanceRole.id.in_(role_ids))
        .distinct()
        .order_by(GovernanceRole.id)
    ).all():
        members = list(
            db.scalars(
                select(GovernanceRoleMember)
                .where(GovernanceRoleMember.role_id == role.id)
                .order_by(GovernanceRoleMember.id)
            ).all()
        )
        # 指纹只记录非明文身份与任职有效性；受限角色不输出标识。
        roles.append(
            input_hash(
                {
                    "role": binding_snapshot._row(role),
                    "members": [
                        {
                            "id": m.id,
                            "user_id": m.user_id,
                            "position_id": m.user.position_id,
                            "active": m.user.is_active,
                        }
                        for m in members
                        if m.user
                    ],
                }
            )
        )
    from app.models.process_task import ProcessTaskDefinition

    task_ids = {s.id for a in coverage.activities for s in a.sources if s.kind == "TASK_DEFINITION"}
    task_fingerprints = [
        binding_snapshot._row(t)
        for t in db.scalars(
            select(ProcessTaskDefinition)
            .where(ProcessTaskDefinition.id.in_(task_ids))
            .order_by(ProcessTaskDefinition.id)
        ).all()
    ]
    from app.services import job_description_access

    source_scopes = job_description_access.capture(db, coverage, published_bindings)
    payload = {
        "application_url": application_url,
        "source_scopes": source_scopes,
        "task_definitions": task_fingerprints,
        "kind": "JOB_DESCRIPTION",
        "rule_version": RULE_VERSION,
        "position": position_data,
        "period": coverage.period.isoformat(),
        "coverage": coverage.model_dump(mode="json"),
        "facets": facets,
        "models": sources,
        "published_bindings": published_bindings,
        "role_fingerprints": roles,
    }
    sections = [
        {"title": "岗位与范围", "rows": [position_data]},
        {
            "title": "参与流程与活动",
            "rows": [r.model_dump(mode="json") for r in coverage.activities],
        },
        {
            "title": "职责与协作",
            "rows": [r.model_dump(mode="json") for a in coverage.activities for r in a.raci]
            or ["未绑定活动 RACI；节点责任岗位不自动等于 R 执行。"],
        },
        {"title": "工作量参考", "rows": [coverage.workload.model_dump(mode="json")]},
        {"title": "指标与控制", "rows": facets or ["未绑定"]},
        {"title": "来源与缺口", "rows": [g.message for g in gaps] + coverage.limitations},
    ]
    for section in sections:
        section["html"] = "".join(row_html(row) for row in section["rows"])
    html = render({"position": position_data, "sections": sections})
    content_hash = hashlib.sha256(html.encode()).hexdigest()
    digest = input_hash(payload)
    manifest = {**payload, "input_hash": digest, "content_hash": content_hash}
    identity_blockers = {
        "POSITION_INACTIVE",
        "MODEL_NOT_PUBLISHED",
        "MODEL_DIFFERS",
        "BINDINGS_NOT_CONFIRMED",
        "NO_ACTIVITY",
        "SOURCE_RESTRICTED",
    }
    return JobDescriptionPreviewOut(
        position=position_data,
        period=coverage.period,
        sections=sections,
        preview_html=html,
        input_hash=digest,
        content_hash=content_hash,
        manifest=manifest,
        gaps=gaps,
        can_compile=not any(g.code in identity_blockers for g in gaps),
        can_submit_review=bool(binding_gates)
        and all(g.ready for g in binding_gates)
        and not any(g.code in identity_blockers for g in gaps)
        and not any(g.code == "UNMAPPED_ROLE" for g in gaps),
        binding_gates=binding_gates,
        limitations=coverage.limitations,
    )


def get_description(db: Session, position_id: int, version_id: int, user: User) -> dict:
    from fastapi import HTTPException

    from app.core.config import settings
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.services import process_document, storage
    from app.services.deliverable import STATUS_LABELS

    version = db.get(ProcessDocumentVersion, version_id)
    document = db.get(ProcessDocument, version.document_id) if version else None
    if (
        document is None
        or document.scope != "POSITION"
        or document.position_id != position_id
        or (version.compile_manifest or {}).get("kind") != "JOB_DESCRIPTION"
    ):
        raise HTTPException(404, "岗位责任书版本不存在")
    process_document.ensure_document_visible(db, user, document)
    html = None
    if version.storage_key:
        try:
            with storage.get_storage().open(version.storage_key) as handle:
                html = handle.read().decode("utf-8")
        except FileNotFoundError:
            pass
    return {
        "document_id": document.id,
        "version_id": version.id,
        "version_label": version.version_label,
        "status": version.status,
        "status_label": STATUS_LABELS.get(version.status, version.status),
        "content_hash": (version.compile_manifest or {}).get("content_hash"),
        "manifest": version.compile_manifest,
        "preview_html": html,
        "download_url": f"{settings.api_prefix}/process-documents/{document.id}/versions/{version.id}/download",
    }


def compile(
    db: Session,
    position_id: int,
    user: User,
    period: Optional[date],
    expected_input_hash: str,
    *,
    application_url: Optional[str] = None,
) -> dict:
    import io

    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.models.process_document import (
        CompiledAssetComponent,
        ProcessDocument,
    )
    from app.services import audit, process_document, storage

    position = db.scalar(select(Position).where(Position.id == position_id).with_for_update())
    if position is None:
        raise HTTPException(404, "岗位不存在")
    initial = position_coverage.coverage(db, position_id, user, period)
    for process_id in sorted(p.id for p in initial.processes):
        db.scalar(select(ProcessArch).where(ProcessArch.id == process_id).with_for_update())
    data = preview(db, position_id, user, period, application_url=application_url)
    if data.input_hash != expected_input_hash:
        raise HTTPException(409, "来源已变化，请刷新预览后重新生成")
    if not data.can_compile:
        raise HTTPException(
            409,
            detail={
                "message": "来源身份尚未确认，暂不能生成责任书草稿",
                "gaps": [g.model_dump() for g in data.gaps],
            },
        )
    code = f"JD-POS-{position_id}"
    document = db.scalar(select(ProcessDocument).where(ProcessDocument.code == code))
    if document and (
        document.scope != "POSITION"
        or document.position_id != position_id
        or document.category != "JOB_DESCRIPTION"
    ):
        raise HTTPException(409, "岗位责任书编码已被其他对象占用")
    if document:
        for version in document.versions:
            if (
                version.status not in {"RETIRED", "SUPERSEDED"}
                and (version.compile_manifest or {}).get("input_hash") == data.input_hash
            ):
                return get_description(db, position_id, version.id, user)
    backend = storage.get_storage()
    key = storage.build_key(f"job-descriptions/{position_id}", f"{code}.html")
    try:
        checksum, size = backend.save(
            key, io.BytesIO(data.preview_html.encode()), storage.max_bytes()
        )
        if document is None:
            document = ProcessDocument(
                scope="POSITION",
                position_id=position_id,
                code=code,
                title=f"{position.name} · 岗位责任书",
                category="JOB_DESCRIPTION",
                org_unit_id=position.org_unit_id,
                variation_policy="LOCKED",
            )
            db.add(document)
            db.flush()
        labels = [int(v.version_label.split(".")[0]) for v in document.versions]
        version = process_document.create_version(
            db,
            document,
            {"version_label": f"{max(labels, default=0) + 1}.0"},
            user,
            file_meta={
                "file_name": f"{code}.html",
                "mime_type": "text/html",
                "size_bytes": size,
                "checksum": checksum,
                "storage_backend": "local",
                "storage_key": key,
            },
        )
        version.source_kind = "COMPILED"
        version.compile_manifest = data.manifest
        refs = {("POSITION_REF", position_id, None)}
        for activity in data.manifest["coverage"]["activities"]:
            aid = activity["activity_id"]
            refs.update(("RACI_ACTIVITY", r["id"], aid) for r in activity["raci"])
            refs.update(("WORK_STANDARD", sid, aid) for sid in activity["standard_ids"])
        for facet_activity in data.manifest["facets"]:
            for facet in facet_activity["facets"]:
                for ref in facet["refs"]:
                    kind = {
                        "FORM": "FORM_REF",
                        "RULE": "RULE_REF",
                        "KPI": "KPI_REF",
                        "EVIDENCE": "CONTROL",
                    }.get(ref["kind"])
                    if kind and ref.get("id"):
                        refs.add((kind, ref["id"], facet_activity["activity_id"]))
        for kind, refid, aid in sorted(refs, key=lambda r: (r[0], r[1], r[2] or 0)):
            db.add(
                CompiledAssetComponent(
                    document_version_id=version.id,
                    component_type=kind,
                    component_ref_id=refid,
                    activity_id=aid,
                    source_hash=data.input_hash,
                )
            )
        audit.record(
            db,
            user,
            "CREATE",
            "process_document_version",
            version.id,
            f"生成岗位责任书 {code} v{version.version_label}",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        backend.delete(key)
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "岗位责任书版本已变化，请查询历史后重试") from exc
        raise
    return get_description(db, position_id, version.id, user)


def validate_for_transition(db: Session, document, version, target: str, user: User) -> None:
    from fastapi import HTTPException

    if target not in {"IN_REVIEW", "APPROVED", "EFFECTIVE"}:
        return
    manifest = version.compile_manifest or {}
    if document.scope != "POSITION" or manifest.get("kind") != "JOB_DESCRIPTION":
        raise HTTPException(409, "岗位产物缺少原编译依据")
    data = preview(
        db,
        document.position_id,
        user,
        date.fromisoformat(manifest["period"]),
        application_url=manifest.get("application_url"),
    )
    if not data.can_compile or data.input_hash != manifest.get("input_hash"):
        raise HTTPException(409, "原岗位或绑定依据已变化，请重新预览并生成责任书")

    if not data.can_submit_review:
        raise HTTPException(
            409,
            {
                "message": "岗位责任书绩效版绑定未齐，草稿可保留，不能正式流转。",
                "blockers": [b.model_dump() for gate in data.binding_gates for b in gate.blockers]
                + [
                    {
                        "code": g.code,
                        "message": g.message,
                        "targets": ["activity:" + str(g.activity_id)],
                    }
                    for g in data.gaps
                    if g.code == "UNMAPPED_ROLE"
                ],
            },
        )
