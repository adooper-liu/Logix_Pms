"""Apply the explicitly scoped Gate 4 configuration without business attestation.

No commit, publication, task execution, account assignment or Gate transition.
"""

from copy import deepcopy
from io import BytesIO

from sqlalchemy import event, select

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.asset_graph import NodeActivityLink
from app.models.execution import FormDefinition
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.resource_link import ActivityResourceLink
from app.schemas.process import ProcessModelIn
from app.services import audit, binding_snapshot, forms, process_model
from app.services.gate4_definitions import CONTROLS, FORMS, GAPS, document_text
from app.services.storage import build_key, get_storage, max_bytes

CODE = "L3-032"
DOCUMENT_CODE = "PD-L3-032-GATE4"
MARKER = "Gate 4 规范配置（待业务确认）"


def _process(db, code):
    if code != CODE:
        raise ValueError("本配置包仅适用于 L3-032")
    process = db.scalar(select(ProcessArch).where(ProcessArch.code == code))
    if process is None or process.level != 3 or process.is_draft:
        raise ValueError("请选择正式 L3-032 流程")
    return process


def _document(db, process):
    document = db.scalar(select(ProcessDocument).where(ProcessDocument.code == DOCUMENT_CODE))
    if document and document.process_id != process.id:
        raise ValueError("Gate 4 文件归属发生变化")
    return document


def _fingerprint(db, version, document):
    mappings = db.scalars(
        select(NodeActivityLink)
        .where(NodeActivityLink.model_version_id == version.id)
        .order_by(NodeActivityLink.id)
    ).all()
    carriers = db.scalars(
        select(FormDefinition)
        .where(FormDefinition.process_id == version.process_id)
        .order_by(FormDefinition.id)
    ).all()
    resources = db.scalars(
        select(ActivityResourceLink)
        .where(
            ActivityResourceLink.activity_id.in_([m.activity_id for m in mappings]),
            ActivityResourceLink.resource_type == "FORM",
        )
        .order_by(ActivityResourceLink.id)
    ).all()
    return binding_snapshot._hash(
        {
            "model": version.snapshot,
            "bpmn_xml": version.bpmn_xml,
            "document": binding_snapshot._row(document),
            "status": version.status,
            "frozen_at": str(version.frozen_at),
            "bindings": version.binding_snapshot,
            "mappings": [binding_snapshot._row(m) for m in mappings],
            "forms": [binding_snapshot._row(f) for f in carriers],
            "resources": [binding_snapshot._row(r) for r in resources],
        }
    )


def check(db, process_code=CODE):
    """Read only: verify the recorded configuration, not business readiness."""
    process = _process(db, process_code)
    document = _document(db, process)
    if document is None:
        return {"configuration_ready": False, "process_code": CODE, "gaps": GAPS}
    doc_version = db.get(ProcessDocumentVersion, document.current_version_id)
    manifest = doc_version.compile_manifest if doc_version else None
    if not manifest or manifest.get("kind") != "GATE4_CONFIGURATION":
        raise ValueError("Gate 4 文件已变化，拒绝覆盖")
    version = db.get(ProcessModelVersion, manifest["model_version_id"])
    if version is None or version.process_id != process.id:
        raise ValueError("Gate 4 模型版本已变化")
    if _fingerprint(db, version, document) != manifest["configuration_hash"]:
        raise ValueError("Gate 4 配置已变化，请核对人工修改，不自动覆盖")
    if doc_version.status != "DRAFT" or doc_version.approved_at is not None:
        raise ValueError("Gate 4 文件状态已变化")
    with get_storage().open(doc_version.storage_key) as stream:
        import hashlib

        if hashlib.sha256(stream.read()).hexdigest() != doc_version.checksum:
            raise ValueError("Gate 4 文件内容已变化")
    return {
        "configuration_ready": True,
        "process_code": CODE,
        "model_version_id": version.id,
        "model_version": version.version,
        "model_status": version.status,
        "published_version": process.published_model_version,
        "document_id": document.id,
        "document_version_id": doc_version.id,
        "document_status": doc_version.status,
        "evidence_grade": "E1",
        "business_approved": False,
        "instances_created": 0,
        "gaps": GAPS,
    }


def _rollback_attachments(db):
    for storage, key in db.info.pop("gate4_new_attachments", []):
        storage.delete(key)


def _commit_attachments(db):
    db.info.pop("gate4_new_attachments", None)


def prepare(db, process_code=CODE, *, persist_file=True):
    """Add a clean frozen working version and original-source configuration.

    Caller owns the transaction. persist_file=False is for rollback-only preview.
    Existing packages are checked rather than silently re-applied.
    """
    process = _process(db, process_code)
    process_model.lock_process(db, process)
    if _document(db, process):
        return check(db, process_code)
    baseline = db.scalar(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.version == process.published_model_version,
            ProcessModelVersion.status == "PUBLISHED",
        )
    )
    if baseline is None:
        raise ValueError("缺少可追溯的已发布模型，不猜建业务基线")
    snapshot = deepcopy(baseline.snapshot)
    nodes = {node["node_key"]: node for node in snapshot.get("nodes", [])}
    if set(nodes) != set(FORMS) or len(snapshot["nodes"]) != 6:
        raise ValueError("已发布模型不再是预期六活动，请先核对范围")
    activities = {}
    for key, node in nodes.items():
        activity = db.get(ProcessArch, node.get("process_arch_id"))
        if (
            activity is None
            or activity.parent_id != process.id
            or activity.level != 4
            or activity.is_draft
            or activity.code != f"L4-{200 + int(key[1:])}"
        ):
            raise ValueError("六活动映射无效或已变化")
        activities[key] = activity
    expected_edges = {
        ("n1", "n2"),
        ("n2", "n3"),
        ("n3", "n4"),
        ("n4", "n5"),
        ("n4", "n6"),
        ("n6", "n2"),
    }
    if {(e["source_key"], e["target_key"]) for e in snapshot["edges"]} != expected_edges:
        raise ValueError("已发布路径已变化，拒绝覆盖业务设计")
    if db.scalar(
        select(ProcessModelVersion.id).where(
            ProcessModelVersion.process_id == process.id, ProcessModelVersion.status == "IN_REVIEW"
        )
    ):
        raise ValueError("存在待评审模型，请先完成当前评审")
    for key, activity in activities.items():
        inactive = db.scalar(
            select(ActivityResourceLink.id).where(
                ActivityResourceLink.activity_id == activity.id,
                ActivityResourceLink.resource_type == "FORM",
                ActivityResourceLink.node_key == key,
                ActivityResourceLink.is_active.is_(False),
            )
        )
        if inactive:
            raise ValueError("存在人工停用的表单链接，请先核对，不自动覆盖")
    for key, node in nodes.items():
        node["description"] = (node.get("description") or "") + "\n" + CONTROLS[key]
    for edge in snapshot["edges"]:
        route = (edge["source_key"], edge["target_key"])
        condition = {
            ("n3", "n4"): ("budget_ok", "是"),
            ("n4", "n5"): ("approved", "是"),
            ("n4", "n6"): ("approved", "否"),
            ("n6", "n2"): ("resubmit_ready", "是"),
        }.get(route)
        if condition:
            edge["match_conditions"] = [{"field": condition[0], "op": "eq", "value": condition[1]}]
            edge["is_default"] = False
    snapshot["edges"].append(
        {
            "source_key": "n3",
            "target_key": "n6",
            "label": "预算未通过（拟定）",
            "condition": "预算校验未通过，退回修改；待业务确认",
            "match_conditions": [{"field": "budget_ok", "op": "eq", "value": "否"}],
            "is_default": False,
            "probability": 0,
        }
    )
    payload = ProcessModelIn.model_validate(snapshot)
    process_model.validate_payload(payload)
    latest = process_model.latest_version(db, process.id)
    version = ProcessModelVersion(
        process_id=process.id,
        version=max(baseline.version, latest.version) + 1,
        status="DRAFT",
        execution_provider="LEGACY",
        snapshot=process_model.snapshot_from_payload(payload),
        change_note=MARKER,
        created_by_name="系统（AI 辅助规范配置，非业务确认）",
    )
    db.add(version)
    db.flush()
    version.bpmn_xml = process_model.render_bpmn(process, version.snapshot)
    for key, activity in activities.items():
        db.add(
            NodeActivityLink(
                process_id=process.id,
                model_version_id=version.id,
                node_key=key,
                activity_id=activity.id,
                relation="REALIZES",
                path_condition="ALL",
                note="依据已发布模型登记；E1 规范配置，待业务确认，不代表责任接受",
            )
        )
        carrier = db.scalar(
            select(FormDefinition).where(
                FormDefinition.process_id == process.id, FormDefinition.node_key == key
            )
        )
        name, required_fields = FORMS[key]
        if carrier is None:
            carrier = FormDefinition(
                process_id=process.id,
                node_key=key,
                name=name,
                fields=forms.normalize_fields(required_fields),
            )
            db.add(carrier)
        else:
            # Keep additional user fields; explicit Gate 4 fields acquire proposed validation.
            existing = {f["key"]: deepcopy(f) for f in carrier.fields}
            existing.update({f["key"]: deepcopy(f) for f in required_fields})
            carrier.fields = forms.normalize_fields(list(existing.values()))
            carrier.name = name
            carrier.is_active = True
            carrier.version += 1
        db.flush()
        resource = db.scalar(
            select(ActivityResourceLink).where(
                ActivityResourceLink.activity_id == activity.id,
                ActivityResourceLink.resource_type == "FORM",
                ActivityResourceLink.ref_id == carrier.id,
                ActivityResourceLink.node_key == key,
            )
        )
        if resource is None:
            db.add(
                ActivityResourceLink(
                    activity_id=activity.id,
                    resource_type="FORM",
                    ref_id=carrier.id,
                    ref_key=f"FORM:{carrier.id}",
                    node_key=key,
                    note="Gate 4 原表单引用；记录载体非业务事实",
                    is_active=True,
                )
            )
    db.flush()
    document = ProcessDocument(
        process_id=process.id,
        code=DOCUMENT_CODE,
        title="Gate 4 过程控制配置与缺口说明",
        category="CHECKLIST",
        org_unit_id=process.org_unit_id,
        description="E1 规范配置草稿，非业务批准、非真实运行；不推进 Gate 5",
        control_points="\n".join(CONTROLS.values()),
        exception_terms="\n".join(GAPS),
    )
    db.add(document)
    db.flush()
    process.model_version += 1
    process.model_updated_at = utcnow()
    content = document_text(version, baseline).encode("utf-8")
    key = build_key(f"process-documents/{document.id}", "gate4-controls.txt")
    checksum = size = None
    if persist_file:
        storage = get_storage()
        checksum, size = storage.save(key, BytesIO(content), max_bytes())
        # The session transaction owns this newly generated key, never an existing attachment.
        pending = db.info.setdefault("gate4_new_attachments", [])
        pending.append((storage, key))
        if not db.info.get("gate4_cleanup_registered"):
            event.listen(db, "after_rollback", _rollback_attachments)
            event.listen(db, "after_commit", _commit_attachments)
            db.info["gate4_cleanup_registered"] = True
    doc_version = ProcessDocumentVersion(
        document_id=document.id,
        version_label="1.0",
        status="DRAFT",
        source_kind="UPLOAD",
        created_by="系统（AI 辅助规范配置，非业务批准）",
        note=MARKER,
        file_name="gate4-controls.txt",
        mime_type="text/plain",
        storage_key=key if persist_file else None,
        storage_backend=settings.attachment_backend,
        checksum=checksum,
        size_bytes=size,
        compile_manifest={
            "kind": "GATE4_CONFIGURATION",
            "model_version_id": version.id,
            "baseline_version_id": baseline.id,
            "evidence_grade": "E1",
        },
    )
    db.add(doc_version)
    db.flush()
    document.current_version_id = doc_version.id
    db.flush()
    # Capture only after every referenced object has its final identity and pointer.
    db.expire(document, ["versions"])
    version.binding_snapshot = binding_snapshot.capture(db, process, version)
    version.frozen_at = utcnow()
    doc_version.compile_manifest = {
        **doc_version.compile_manifest,
        "configuration_hash": _fingerprint(db, version, document),
    }
    audit.record(
        db,
        None,
        "CREATE",
        "process_design",
        process.id,
        f"{CODE} {MARKER} V{version.version}；未发布，未审批，未创建运行，不进入 Gate 5",
    )
    db.flush()
    if persist_file:
        return check(db, process_code)
    return {
        "process_code": CODE,
        "model_version": version.version,
        "model_status": "DRAFT",
        "configuration_ready": True,
        "preview": True,
        "gaps": GAPS,
    }
