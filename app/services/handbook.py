"""员工手册：原发布作业与固定来源的确定性编译。"""

import hashlib

from sqlalchemy import select

from app.models.process import ProcessArch, ProcessModelVersion
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.schemas.handbook import HandbookPreviewOut
from app.services import (
    binding_readiness,
    binding_snapshot,
    handbook_render,
    handbook_scope,
    handbook_sources,
    storage,
)

RULE_VERSION = "handbook/v1"
LIMITATIONS = [
    "只呈现原作业依据，不自动补写指令；排序不代表执行路径。",
    "A/C/I 是协作身份，不自动等于执行；工时不推导职责。",
    "绑定齐全不等于作业说明齐全，不代表组织授权、操作能力或业务效果。",
]


def preview(db, scope, subject_id, user, *, application_url=None):
    data = handbook_scope.collect(db, scope, subject_id, user)
    gaps, entries, guards, gates, models = list(data["gaps"]), [], [], [], []
    guards.append(
        {
            "kind": scope,
            "id": subject_id,
            "org_unit_id": data["subject"]["org_unit_id"],
            "variation_policy": None,
        }
    )
    for step in data["steps"]:
        row, refs, hidden, invalid = handbook_sources.resolve(
            db, step, user, application_url=application_url
        )
        entries.append(row)
        guards.extend(refs)
        for code, message, condition in [
            ("SOURCE_RESTRICTED", "部分原作业来源受限，不能确认手册完整性", hidden),
            ("SOURCE_INVALID", "原作业来源已失效，须回原来源核对", invalid),
            ("INSTRUCTION_MISSING", "作业说明原依据未明确", not row["instruction_ready"]),
            (
                "EXCEPTION_UNDEFINED",
                "例外处理原依据未明确；不推定异常接收人",
                not row["exception_ready"],
            ),
            (
                "NODE_ACTIVITY_UNMAPPED",
                "作业节点没有正确映射本流程活动",
                bool(row["mapping_blockers"]),
            ),
        ]:
            if condition:
                gaps.append(
                    {
                        "code": code,
                        "message": message,
                        "process_id": row["process_id"],
                        "node_key": row["node_key"],
                        "task_id": row["task_id"],
                    }
                )
    for info in data["processes"]:
        if not info["activity_ids"]:
            continue
        process = db.get(ProcessArch, info["id"])
        version = db.get(ProcessModelVersion, info["model_version_id"])
        gate = binding_readiness.binding_gate(
            db,
            process.id,
            user,
            profile="PERFORMANCE",
            model_version_id=version.id,
            activity_ids=set(info["activity_ids"]),
        )
        gates.append(gate)
        for blocker in gate.blockers:
            gaps.append(
                {
                    "code": blocker.code,
                    "message": blocker.message,
                    "process_id": process.id,
                    "targets": blocker.targets,
                }
            )
        current = binding_snapshot.activity_scope(
            binding_snapshot.capture(db, process, version), set(info["activity_ids"])
        )
        # 全来源内容用不含正文的原hash固定，输出仅已授权解析后的作业内容。
        models.append(
            {
                "process_id": process.id,
                "model_version_id": version.id,
                "org_unit_id": process.org_unit_id,
                "binding_hash": binding_snapshot._hash(current["activities"]),
                "consistency": gate.consistency,
            }
        )
    unique_guards = {(g["kind"], g["id"]): g for g in guards}
    source_scopes = [unique_guards[k] for k in sorted(unique_guards)]
    identity_codes = {
        "SUBJECT_INACTIVE",
        "SOURCE_RESTRICTED",
        "SOURCE_INVALID",
        "BINDINGS_NOT_CONFIRMED",
        "NODE_ACTIVITY_UNMAPPED",
        "NO_EXECUTION_STEPS",
    }
    can_compile = bool(entries) and not any(g["code"] in identity_codes for g in gaps)
    can_submit_review = (
        can_compile
        and bool(gates)
        and all(g.ready for g in gates)
        and not any(g["code"] in {"INSTRUCTION_MISSING", "EXCEPTION_UNDEFINED"} for g in gaps)
    )
    html = handbook_render.render(data["subject"], entries, data["collaboration"], gaps)
    payload = {
        "kind": "HANDBOOK",
        "rule_version": RULE_VERSION,
        "subject": data["subject"],
        "entries": entries,
        "collaboration": data["collaboration"],
        "models": models,
        "source_scopes": source_scopes,
        "application_url": application_url,
        "binding_fingerprints": [g.fingerprint for g in gates],
        "gaps": gaps,
    }
    digest = binding_snapshot._hash(payload)
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return HandbookPreviewOut(
        subject=data["subject"],
        entries=entries,
        collaboration=data["collaboration"],
        gaps=gaps,
        binding_gates=gates,
        can_compile=can_compile,
        can_submit_review=can_submit_review,
        input_hash=digest,
        content_hash=content_hash,
        preview_html=html,
        manifest={**payload, "input_hash": digest, "content_hash": content_hash},
        limitations=LIMITATIONS,
    )


def compile(db, scope, subject_id, user, expected_input_hash, *, application_url=None):
    import io

    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.models.process_document import ProcessDocument
    from app.services import audit
    from app.services import process_document as doc_service

    data = preview(db, scope, subject_id, user, application_url=application_url)
    if data.input_hash != expected_input_hash:
        raise HTTPException(409, "来源已变化，请刷新手册预览")
    if not data.can_compile:
        raise HTTPException(
            409, {"message": "来源身份或发布依据未确认，暂不能生成手册草稿", "gaps": data.gaps}
        )
    subject = data.subject
    code = f"HB-{scope[:3]}-{subject_id}"
    document = db.scalar(select(ProcessDocument).where(ProcessDocument.code == code))
    if document and (
        document.scope != scope
        or document.position_id != (subject_id if scope == "POSITION" else None)
        or document.governance_role_id != (subject_id if scope == "ROLE" else None)
        or document.category != "HANDBOOK"
    ):
        raise HTTPException(409, "手册编码已被其他对象占用")
    if document:
        for version in document.versions:
            if (
                version.status not in {"RETIRED", "SUPERSEDED"}
                and (version.compile_manifest or {}).get("input_hash") == data.input_hash
            ):
                return get_handbook(db, version.id, user)
    if document is None:
        document = ProcessDocument(
            scope=scope,
            position_id=subject_id if scope == "POSITION" else None,
            governance_role_id=subject_id if scope == "ROLE" else None,
            code=code,
            title=f"{subject['name']} · 员工作业手册",
            category="HANDBOOK",
            org_unit_id=subject.get("org_unit_id"),
            variation_policy="LOCKED",
        )
        db.add(document)
        db.flush()
    backend = storage.get_storage()
    key = storage.build_key(f"handbooks/{scope.lower()}-{subject_id}", f"{code}.html")
    try:
        checksum, size = backend.save(
            key, io.BytesIO(data.preview_html.encode()), storage.max_bytes()
        )
        version = doc_service.create_version(
            db,
            document,
            {
                "version_label": f"{max([int(v.version_label.split('.')[0]) for v in document.versions], default=0) + 1}.0"
            },
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
        db.flush()
        audit.record(
            db,
            user,
            "CREATE",
            "process_document_version",
            version.id,
            f"生成员工手册 {code} v{version.version_label}",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        backend.delete(key)
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "员工手册版本已变化，请刷新历史") from exc
        raise
    return get_handbook(db, version.id, user)


def get_handbook(db, version_id, user):
    from fastapi import HTTPException

    from app.services import process_document as doc_service

    row = db.get(ProcessDocumentVersion, version_id)
    if row is None or (row.compile_manifest or {}).get("kind") != "HANDBOOK":
        raise HTTPException(404, "员工手册版本不存在")
    document = db.get(ProcessDocument, row.document_id)
    if document is None:
        raise HTTPException(404, "员工手册不存在")
    doc_service.ensure_document_visible(db, user, document)
    html = None
    if row.storage_key:
        try:
            with storage.get_storage().open(row.storage_key) as handle:
                raw = handle.read()
            if hashlib.sha256(raw).hexdigest() != row.checksum:
                raise HTTPException(404, "手册固定文件校验失败")
            html = raw.decode()
        except FileNotFoundError:
            pass
    from app.services.deliverable import STATUS_LABELS

    return {
        "document_id": document.id,
        "version_id": row.id,
        "version_label": row.version_label,
        "status": row.status,
        "status_label": STATUS_LABELS.get(row.status, row.status),
        "content_hash": (row.compile_manifest or {}).get("content_hash"),
        "manifest": row.compile_manifest,
        "preview_html": html,
        "download_url": f"/api/v1/process-documents/{document.id}/versions/{row.id}/download",
    }
