"""作业原依据解析：固定文件版本，不读附件生成指令，不把方法工具当SOP。"""

import hashlib
from urllib.parse import urlencode

from sqlalchemy import or_, select

from app.core.timeutil import utcnow
from app.models.execution import FormDefinition, ProcessRule
from app.models.process import NodeTool, ProcessArch
from app.models.process_document import ProcessDocument
from app.models.resource_link import ActivityResourceLink
from app.services import binding_snapshot, org_access, resource_link
from app.services.job_description_access import ensure_manifest_visible
from app.services.process_document import effective_version_on, visible_conditions
from app.services.storage import StorageError, get_storage


def document_visible(db, user, doc, org_unit_id=None):
    if not org_access.unrestricted(user):
        # 原文档按祖先继承，而非业务记录的下级范围。
        condition = visible_conditions(db, user.org_unit_id)
        stmt = select(ProcessDocument.id).where(ProcessDocument.id == doc.id)
        stmt = (
            stmt.where(condition)
            if condition is not None
            else stmt.where(ProcessDocument.org_unit_id.is_(None))
        )
        if db.scalar(stmt) is None:
            return False
    if org_unit_id is not None:
        condition = visible_conditions(db, org_unit_id)
        if (
            condition is not None
            and db.scalar(select(ProcessDocument.id).where(ProcessDocument.id == doc.id, condition))
            is None
        ):
            return False
    return True


def source_guard(doc):
    return {
        "kind": "DOCUMENT",
        "id": doc.id,
        "org_unit_id": doc.org_unit_id,
        "variation_policy": doc.variation_policy,
    }


def file_available(version):
    if not version.storage_key:
        return False
    try:
        with get_storage().open(version.storage_key) as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return bool(version.checksum and digest.hexdigest() == version.checksum)
    except (FileNotFoundError, StorageError, OSError):
        return False


def resolve(db, step, user, *, application_url=None):
    process = db.get(ProcessArch, step["process_id"])
    aids, key = set(step["activity_ids"]), step["node_key"]
    from app.models.process import ProcessModelVersion

    version = db.get(ProcessModelVersion, step["model_version_id"])
    links = list(
        db.scalars(
            select(ActivityResourceLink)
            .where(
                ActivityResourceLink.activity_id.in_(aids),
                ActivityResourceLink.is_active.is_(True),
                or_(
                    ActivityResourceLink.node_key == key if key else False,
                    ActivityResourceLink.node_key.is_(None),
                ),
            )
            .order_by(ActivityResourceLink.id)
        ).all()
    )
    linked_docs = {r.ref_id for r in links if r.resource_type == "DOCUMENT"}
    valid_linked_docs = set()
    for link in links:
        if link.resource_type != "DOCUMENT":
            continue
        activity = db.get(ProcessArch, link.activity_id)
        if activity is None:
            invalid = True
            continue
        valid, _, _ = resource_link.source(
            db,
            process,
            activity,
            "DOCUMENT",
            link.ref_id,
            link.node_key,
            user,
            model_version=version,
        )
        if valid:
            valid_linked_docs.add(link.ref_id)
        else:
            invalid = True
    linked_docs = valid_linked_docs
    docs = db.scalars(
        select(ProcessDocument)
        .where(
            ProcessDocument.scope == "PROCESS",
            ProcessDocument.is_active.is_(True),
            or_(
                ProcessDocument.process_id.in_(aids | {process.id}),
                ProcessDocument.id.in_(linked_docs),
            ),
        )
        .order_by(ProcessDocument.id)
    ).all()
    documents, guards, hidden, invalid = [], [], False, False
    for doc in docs:
        direct = (
            doc.process_id in aids
            and not doc.node_key
            or doc.process_id == process.id
            and key
            and doc.node_key == key
        )
        inherited = doc.process_id == process.id and not doc.node_key
        if not (direct or inherited or doc.id in linked_docs):
            continue
        if doc.category not in {"SOP", "POLICY", "FORM", "CHECKLIST"}:
            continue
        if not document_visible(db, user, doc, process.org_unit_id):
            hidden = True
            continue
        original = effective_version_on(doc, utcnow().date())
        if original is None or original.source_kind == "COMPILED":
            invalid = True
            continue
        # 原活动/节点文件保留直接语义；流程默认始终标继承。
        source = "DIRECT" if direct else "INHERITED"
        available = file_available(original)
        query = urlencode({"document_id": doc.id, "version_id": original.id})
        url = "api/v1/handbooks/source?" + query
        documents.append(
            {
                "document_id": doc.id,
                "version_id": original.id,
                "version_label": original.version_label,
                "checksum": original.checksum,
                "title": doc.title,
                "category": doc.category,
                "source": source,
                "source_label": "直接作业依据"
                if source == "DIRECT"
                else "继承标准（不代替节点专属作业）",
                "control_points": doc.control_points or "",
                "exception_terms": doc.exception_terms or "",
                "openable": available,
                "download_url": (application_url.rstrip("/") + "/" if application_url else "/")
                + url,
                "source_hash": binding_snapshot._hash(
                    {
                        "document": binding_snapshot._row(doc),
                        "version": binding_snapshot._row(original),
                    }
                ),
            }
        )
        guards.append(source_guard(doc))
    forms = db.scalars(
        select(FormDefinition)
        .where(
            FormDefinition.process_id == process.id,
            FormDefinition.is_active.is_(True),
            FormDefinition.node_key.in_([key, ""] if key else [""]),
        )
        .order_by(FormDefinition.id)
    ).all()
    rules = db.scalars(
        select(ProcessRule)
        .where(
            ProcessRule.process_id == process.id,
            ProcessRule.is_active.is_(True),
            ProcessRule.node_key == key if key else False,
        )
        .order_by(ProcessRule.priority, ProcessRule.id)
    ).all()
    tools = db.scalars(
        select(NodeTool)
        .where(NodeTool.process_id == process.id, NodeTool.node_key == key if key else False)
        .order_by(NodeTool.id)
    ).all()
    resources = resource_link.list_links(db, process, user, model_version=version)
    resources = [
        r.model_dump(mode="json")
        for r in resources
        if r.activity_id in aids and r.node_key in {None, key}
    ]
    # 不将受限资源label/note带入手册；缺口只给通用提示。
    for row in resources:
        if not row["source_valid"]:
            invalid = True
            if row["source_label"] == "受限来源":
                hidden = True
    resources = [r for r in resources if r["source_valid"]]
    instruction_ready = bool(step["instruction"].strip()) or any(
        d["category"] in {"SOP", "POLICY"} and d["source"] == "DIRECT" and d["openable"]
        for d in documents
    )
    exception_ready = any(d["exception_terms"].strip() for d in documents)
    result = {
        **step,
        "documents": documents,
        "forms": [
            {
                "id": f.id,
                "name": f.name,
                "version": f.version,
                "fields": f.fields,
                "source": "DIRECT" if f.node_key else "INHERITED",
                "source_label": "节点表单" if f.node_key else "流程默认表单（继承）",
            }
            for f in forms
        ],
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "version": r.version,
                "conditions": r.conditions,
                "target_node_key": r.target_node_key,
                "priority": r.priority,
            }
            for r in rules
        ],
        "tools": [
            {
                "id": t.id,
                "name": t.tool_name,
                "code": t.tool_code,
                "note": t.note,
                "label": "方法工具（不代替作业说明）",
            }
            for t in tools
        ],
        "resources": resources,
        "instruction_ready": instruction_ready,
        "exception_ready": exception_ready,
        "instruction_label": "有原作业说明／可打开的适用标准"
        if instruction_ready
        else "原依据未明确",
        "exception_label": "有原例外条款／规则" if exception_ready else "原依据未明确",
        "designer_url": (application_url.rstrip("/") + "/" if application_url else "")
        + "#designer?"
        + urlencode(
            {
                "process": process.id,
                "node": key or "",
                "activity": next(iter(sorted(aids)), ""),
                "basis": version.id,
            }
        ),
        "source_note": "排序仅用于查阅，不代表执行路径；分支和例外按原模型／规则。",
    }
    return result, guards, hidden, invalid


def ensure_visible(db, user, manifest):
    ensure_manifest_visible(db, user, manifest)
    for item in manifest.get("models", []):
        process = db.get(ProcessArch, item["process_id"])
        if process is None:
            from fastapi import HTTPException

            raise HTTPException(404, "原流程不可见")
        org_access.ensure_visible(db, user, item.get("org_unit_id"))
        org_access.ensure_visible(db, user, process.org_unit_id)
