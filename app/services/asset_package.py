"""资产包生成：已发布模型 + 架构关系 + 证据主张 → 流程级 SOP 资产。

复用 `ProcessDocument` / `ProcessDocumentVersion` 的流程级生命周期，不另造版本表。
生成器只读；写入只发生在提交时，且必须重新跑阻断规则，不信任前端预览。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import timezone
from html import escape
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.execution import FormDefinition, ProcessRule
from app.models.process import ProcessArch, ProcessNode
from app.models.process_document import (
    CompiledAssetComponent,
    ProcessDocument,
    ProcessDocumentVersion,
)
from app.models.raci import RaciAssignment
from app.models.user import User
from app.schemas.asset_graph import (
    ArchitectureMapOut,
    AssetComponentImpactItem,
    AssetImpactOut,
    AssetPackageOut,
    AssetPackagePreviewOut,
    AssetReadinessOut,
    EvidenceClaimListOut,
    NodeActivityLinkOut,
)
from app.services import asset_graph as asset_service
from app.services import audit, binding_readiness
from app.services import deliverable as deliverable_service
from app.services import preview as preview_service
from app.services import process_document as document_service
from app.services import storage as storage_service

RULE_VERSION = "asset-compile-v1"
DOC_PREFIX = "AP-"
HARD_BLOCKERS = {"MODEL_NOT_VERSIONED", "NODE_ACTIVITY_UNMAPPED"}
NODE_TYPE_LABELS = {
    "START": "开始",
    "END": "结束",
    "TASK": "作业",
    "APPROVAL": "审批",
    "WAIT": "等待",
    "DECISION": "判断",
    "PARALLEL": "并行网关",
    "HANDOFF": "移交",
}
COMPONENT_LABELS = {
    "SOP_SECTION": "SOP 章节",
    "RACI": "责任",
    "CONTROL": "控制点",
    "FORM_REF": "表单引用",
    "RULE_REF": "规则引用",
    "KPI_REF": "KPI 引用",
    "CLAIM_REF": "证据主张引用",
}


def _hash_json(value) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _e(value) -> str:
    return escape(str(value)) if value is not None else ""


def _node_type(node: ProcessNode) -> str:
    return NODE_TYPE_LABELS.get(node.node_type, node.node_type)


def _activity_label(links: List[NodeActivityLinkOut]) -> str:
    for link in links:
        if link.relation in {"REALIZES", "PART_OF"}:
            code = link.activity_code or ""
            name = link.activity_name or ""
            return f"{code} {name}".strip() or f"活动 #{link.activity_id}"
    return "未映射"


def _activity_id(node: ProcessNode, links: List[NodeActivityLinkOut]) -> Optional[int]:
    if node.process_arch_id:
        return node.process_arch_id
    for link in links:
        if link.relation in {"REALIZES", "PART_OF"}:
            return link.activity_id
    return None


def _form_for(
    node: ProcessNode,
    forms_by_node: Dict[str, FormDefinition],
    default_form: Optional[FormDefinition],
) -> Optional[FormDefinition]:
    return forms_by_node.get(node.node_key) or default_form


def _collect(db: Session, process: ProcessArch) -> dict:
    readiness = asset_service.readiness(db, process)
    mapping = asset_service.architecture_map(db, process)
    claims = asset_service.evidence_claims(db, process)
    nodes = list(
        db.scalars(
            select(ProcessNode)
            .where(ProcessNode.process_id == process.id)
            .order_by(ProcessNode.sequence_order, ProcessNode.id)
        ).all()
    )
    forms = list(
        db.scalars(
            select(FormDefinition).where(
                FormDefinition.process_id == process.id,
                FormDefinition.is_active.is_(True),
            )
        ).all()
    )
    rules = list(
        db.scalars(
            select(ProcessRule).where(
                ProcessRule.process_id == process.id,
                ProcessRule.is_active.is_(True),
            )
        ).all()
    )

    links_by_node: Dict[str, List[NodeActivityLinkOut]] = {}
    for link in mapping.links:
        links_by_node.setdefault(link.node_key, []).append(link)
    forms_by_node = {row.node_key: row for row in forms if row.node_key}
    default_form = next((row for row in forms if not row.node_key), None)
    rules_by_node: Dict[str, List[ProcessRule]] = {}
    for row in rules:
        rules_by_node.setdefault(row.node_key, []).append(row)
    raci = list(
        db.scalars(
            select(RaciAssignment)
            .where(RaciAssignment.process_id == process.id)
            .order_by(RaciAssignment.matter, RaciAssignment.id)
        ).all()
    )

    html = _render_html(
        process,
        readiness,
        mapping,
        nodes,
        links_by_node,
        forms_by_node,
        default_form,
        rules_by_node,
        claims,
        raci,
    )
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    manifest = {
        "rule_version": RULE_VERSION,
        "process_id": process.id,
        "process_code": process.code,
        "process_name": process.name,
        "model_version_id": readiness.model_version_id,
        "model_version": readiness.model_version,
        "model_status": readiness.model_status,
        "generated_at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "activity_count": readiness.metrics.get("activity_nodes", 0),
        "metrics": readiness.metrics,
        "inputs": {
            "links": [row.model_dump(mode="json") for row in mapping.links],
            "activity_relations": [
                row.model_dump(mode="json") for row in mapping.activity_relations
            ],
            "handoffs": [row.model_dump(mode="json") for row in mapping.handoffs],
            "unmodeled": [row.model_dump(mode="json") for row in mapping.unmodeled],
            "claims": [row.model_dump(mode="json") for row in claims.claims],
            "forms": [
                {"id": row.id, "node_key": row.node_key, "name": row.name, "version": row.version}
                for row in forms
            ],
            "rules": [
                {
                    "id": row.id,
                    "node_key": row.node_key,
                    "name": row.name,
                    "version": row.version,
                }
                for row in rules
            ],
            "raci": [
                {
                    "id": row.id,
                    "matter": row.matter,
                    "role_id": row.role_id,
                    "role_name": row.role.name if row.role else None,
                    "raci": row.raci,
                    "note": row.note,
                }
                for row in raci
            ],
        },
        "blockers": [row.model_dump() for row in readiness.blockers],
        "warnings": list(dict.fromkeys(readiness.warnings + mapping.warnings)),
        "content_hash": content_hash,
        "binding_fingerprint": binding_readiness.binding_gate(
            db, process.id, profile="PERFORMANCE", model_version_id=readiness.model_version_id
        ).fingerprint,
    }
    return {
        "html": html,
        "manifest": manifest,
        "content_hash": content_hash,
        "readiness": readiness,
        "mapping": mapping,
        "claims": claims,
        "nodes": nodes,
        "links_by_node": links_by_node,
        "forms_by_node": forms_by_node,
        "default_form": default_form,
        "rules_by_node": rules_by_node,
        "raci": raci,
        "can_generate": not any(row.code in HARD_BLOCKERS for row in readiness.blockers),
    }


def _render_html(
    process: ProcessArch,
    readiness: AssetReadinessOut,
    mapping: ArchitectureMapOut,
    nodes: List[ProcessNode],
    links_by_node: Dict[str, List[NodeActivityLinkOut]],
    forms_by_node: Dict[str, FormDefinition],
    default_form: Optional[FormDefinition],
    rules_by_node: Dict[str, List[ProcessRule]],
    claims: EvidenceClaimListOut,
    raci: List[RaciAssignment],
) -> str:
    activity_rows = []
    for index, node in enumerate(nodes, start=1):
        if node.node_type in {"START", "END"}:
            continue
        links = links_by_node.get(node.node_key, [])
        form = _form_for(node, forms_by_node, default_form)
        node_rules = rules_by_node.get(node.node_key, [])
        rule_text = "；".join(_e(f"{row.name}（v{row.version}）") for row in node_rules) or "—"
        activity_rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><b>{_e(node.name)}</b><div class='sub mono'>{_e(node.node_key)} · "
            f"{_e(_node_type(node))}</div></td>"
            f"<td>{_e(_activity_label(links))}</td>"
            f"<td>{_e(node.owner_role or '—')}<div class='sub'>{_e(node.lane)}</div></td>"
            f"<td class='num'>{_e(f'{node.duration_minutes:.0f}')}</td>"
            f"<td class='num'>{_e(f'{node.wait_minutes:.0f}')}</td>"
            f"<td>{_e(form.name if form else '待补')}</td>"
            f"<td>{rule_text}</td>"
            "</tr>"
        )

    raci_rows = [
        "<tr>"
        f"<td>{_e(row.matter)}</td>"
        f"<td>{_e(row.role.name if row.role else '')}</td>"
        f"<td>{_e(row.raci)}</td>"
        f"<td>{_e(row.note or '—')}</td>"
        "</tr>"
        for row in raci
    ]

    control_rows = []
    for node in nodes:
        for link in links_by_node.get(node.node_key, []):
            if link.relation != "CONTROLS":
                continue
            control_rows.append(
                "<tr>"
                f"<td>{_e(node.name)}</td>"
                f"<td>{_e(link.activity_code or '')} {_e(link.activity_name or '')}</td>"
                f"<td>{_e(f'{link.coverage:.0%}')}</td>"
                f"<td>{_e(link.confirmed_by_name or '未确认')}</td>"
                "</tr>"
            )

    form_rows = []
    for node in nodes:
        if node.node_type in {"START", "END"}:
            continue
        form = _form_for(node, forms_by_node, default_form)
        form_rows.append(
            "<tr>"
            f"<td>{_e(node.name)}</td>"
            f"<td>{_e(form.name if form else '待补')}</td>"
            f"<td>{_e(f'v{form.version}' if form else '—')}</td>"
            f"<td>{_e('流程默认表单' if form and not form.node_key else ('节点表单' if form else '缺失'))}</td>"
            "</tr>"
        )

    claim_rows = []
    for claim in claims.claims:
        claim_rows.append(
            "<tr>"
            f"<td>{_e(claim.claim)}</td>"
            f"<td>{_e(claim.method)}</td>"
            f"<td class='num'>{_e(claim.samples if claim.samples is not None else '—')}</td>"
            f"<td>{_e(claim.status)}</td>"
            f"<td>{_e(claim.source_version or '—')}</td>"
            "</tr>"
        )

    unresolved = [
        row
        for row in readiness.blockers
        if row.code not in {"MODEL_NOT_VERSIONED", "NODE_ACTIVITY_UNMAPPED"}
    ]
    hard = [row for row in readiness.blockers if row.code in HARD_BLOCKERS]
    blocker_items = "".join(
        f"<li><b>{_e(row.message)}</b>"
        + (f"<div class='sub'>{_e('、'.join(row.targets))}</div>" if row.targets else "")
        + "</li>"
        for row in readiness.blockers
    )
    warning_items = "".join(
        f"<li>{_e(item)}</li>"
        for item in list(dict.fromkeys(readiness.warnings + mapping.warnings))
    )
    conflict_items = "".join(f"<li>{_e(item)}</li>" for item in claims.conflicts)
    unknown_items = "".join(f"<li>{_e(item)}</li>" for item in claims.unknown_targets)
    unmodeled_items = "".join(
        f"<li>{_e(row.activity_code or '')} {_e(row.activity_name or '')}"
        f"<div class='sub'>{_e(row.reason)}</div></li>"
        for row in mapping.unmodeled
    )

    state = "可生成草稿" if not hard else "拒绝生成（存在硬阻断）"
    if hard:
        state = "拒绝生成（存在硬阻断）"
    elif unresolved:
        state = "可生成草稿，提交评审前必须清零待补项"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{_e(process.code)} 资产包</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 12px/1.55 "Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         color:#111; margin:0; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:14px; margin:18px 0 7px; border-bottom:1px solid #999;
        padding-bottom:4px; }}
  h3 {{ font-size:12.5px; margin:12px 0 5px; }}
  .meta {{ color:#444; font-size:11px; margin-bottom:10px; }}
  .state {{ display:inline-block; border:1px solid #999; border-radius:4px;
            padding:2px 7px; font-size:11px; margin:4px 0 8px; }}
  .state.bad {{ border-color:#b42332; color:#b42332; }}
  .sub {{ color:#666; font-size:10.5px; }}
  .mono {{ font-family:Consolas,monospace; }}
  .num {{ text-align:right; }}
  table {{ width:100%; border-collapse:collapse; margin:6px 0 8px; }}
  th,td {{ border:1px solid #aaa; padding:4px 6px; text-align:left;
           vertical-align:top; }}
  th {{ background:#eee; font-size:10.5px; }}
  ul {{ margin:4px 0 0 18px; padding:0; }}
  li {{ margin-bottom:3px; }}
  .prov {{ color:#666; font-size:10px; font-weight:normal; }}
  .note {{ border-left:3px solid #999; padding-left:8px; color:#444;
           font-size:11px; margin:6px 0; }}
  @media print {{ h2 {{ page-break-after:avoid; }} tr {{ page-break-inside:avoid; }} }}
</style></head>
<body>
  <h1>{_e(process.name)} · 作业标准</h1>
  <div class="meta">
    {_e(process.code)} · L{process.level} · Owner {_e(process.owner or "未指定")}
    · 模型 v{readiness.model_version}（{_e(readiness.model_status)}）
    · 生成于 {_e(utcnow().strftime("%Y-%m-%d %H:%M UTC"))}
    · 规则 {_e(RULE_VERSION)}
  </div>
  <div class="state {"bad" if hard else ""}">{_e(state)}</div>
  <div class="meta">生成清单记录输入快照与内容 hash；本页只显示可复核的模型与证据事实。</div>

  <h2>1. 范围与边界 <span class="prov">来源：流程架构 + 模型 v{readiness.model_version}</span></h2>
  <p>{_e(process.description or "流程边界待补：请补充起点、终点与客户结果。")}</p>
  <p class="note">本文件由已发布模型确定性生成；责任、载体、控制点引用原对象，不复制第二套口径。</p>

  <h2>2. 活动与责任 <span class="prov">来源：模型 v{readiness.model_version} · 架构关系</span></h2>
  <table>
    <thead><tr><th>#</th><th>节点</th><th>L4 活动</th><th>责任角色 / 泳道</th>
      <th>作业(分)</th><th>等待(分)</th><th>表单 / 记录</th><th>规则</th></tr></thead>
    <tbody>{"".join(activity_rows) or '<tr><td colspan="8">没有可输出的活动节点</td></tr>'}</tbody>
  </table>

  <h2>2.1 流程级 RACI <span class="prov">来源：RaciAssignment</span></h2>
  <table>
    <thead><tr><th>事项</th><th>治理角色</th><th>R/A/C/I</th><th>说明</th></tr></thead>
    <tbody>{"".join(raci_rows) or '<tr><td colspan="4">没有登记流程级 RACI</td></tr>'}</tbody>
  </table>

  <h2>3. 控制点 <span class="prov">来源：CONTROLS 关系</span></h2>
  <table>
    <thead><tr><th>节点</th><th>活动</th><th>覆盖</th><th>确认人</th></tr></thead>
    <tbody>{"".join(control_rows) or '<tr><td colspan="4">没有登记控制点</td></tr>'}</tbody>
  </table>

  <h2>4. 表单与记录 <span class="prov">来源：FormDefinition</span></h2>
  <table>
    <thead><tr><th>节点</th><th>表单</th><th>版本</th><th>类型</th></tr></thead>
    <tbody>{"".join(form_rows) or '<tr><td colspan="4">没有活动节点</td></tr>'}</tbody>
  </table>

  <h2>5. 证据与未决 <span class="prov">来源：证据账本</span></h2>
  <table>
    <thead><tr><th>主张</th><th>方法</th><th>样本</th><th>状态</th><th>来源版本</th></tr></thead>
    <tbody>{"".join(claim_rows) or '<tr><td colspan="5">还没有证据主张</td></tr>'}</tbody>
  </table>
  <h3>未裁决冲突</h3>
  <ul>{conflict_items or "<li>无</li>"}</ul>
  <h3>未被主张覆盖</h3>
  <ul>{unknown_items or "<li>无</li>"}</ul>
  <h3>未建模活动</h3>
  <ul>{unmodeled_items or "<li>无</li>"}</ul>

  <h2>6. 生成说明 <span class="prov">来源：就绪度检查</span></h2>
  <h3>阻断</h3>
  <ul>{blocker_items or "<li>无</li>"}</ul>
  <h3>提示</h3>
  <ul>{warning_items or "<li>无</li>"}</ul>
  <p class="note">草稿可生成，但阻断未清零前不可提交评审；模型升版后必须重新生成。</p>
</body></html>"""


def preview(db: Session, process: ProcessArch) -> AssetPackagePreviewOut:
    data = _collect(db, process)
    readiness = data["readiness"]
    return AssetPackagePreviewOut(
        process_id=process.id,
        process_code=process.code,
        process_name=process.name,
        model_version_id=readiness.model_version_id,
        model_version=readiness.model_version,
        model_status=readiness.model_status,
        can_generate=data["can_generate"],
        blockers=readiness.blockers,
        warnings=data["manifest"]["warnings"],
        manifest=data["manifest"],
        preview_html=data["html"],
        content_hash=data["content_hash"],
    )


def _next_version_label(document: ProcessDocument) -> str:
    labels = [row.version_label for row in document.versions]
    minors = []
    for label in labels:
        parts = label.split(".")
        if len(parts) == 2 and parts[0] == "1" and parts[1].isdigit():
            minors.append(int(parts[1]))
    return f"1.{max(minors, default=-1) + 1}"


def _add_components(db: Session, version: ProcessDocumentVersion, data: dict) -> None:
    for node in data["nodes"]:
        if node.node_type in {"START", "END"}:
            continue
        links = data["links_by_node"].get(node.node_key, [])
        activity_id = _activity_id(node, links)
        form = _form_for(node, data["forms_by_node"], data["default_form"])
        node_rules = data["rules_by_node"].get(node.node_key, [])
        db.add(
            CompiledAssetComponent(
                document_version_id=version.id,
                component_type="SOP_SECTION",
                component_ref_id=node.id,
                activity_id=activity_id,
                source_hash=_hash_json(
                    {
                        "node_key": node.node_key,
                        "activity_id": activity_id,
                        "name": node.name,
                        "owner_role": node.owner_role,
                        "duration": node.duration_minutes,
                        "wait": node.wait_minutes,
                    }
                ),
            )
        )
        if form is not None:
            db.add(
                CompiledAssetComponent(
                    document_version_id=version.id,
                    component_type="FORM_REF",
                    component_ref_id=form.id,
                    activity_id=activity_id,
                    source_hash=_hash_json(
                        {"form_id": form.id, "node_key": form.node_key, "version": form.version}
                    ),
                )
            )
        for rule in node_rules:
            db.add(
                CompiledAssetComponent(
                    document_version_id=version.id,
                    component_type="RULE_REF",
                    component_ref_id=rule.id,
                    activity_id=activity_id,
                    source_hash=_hash_json(
                        {"rule_id": rule.id, "node_key": rule.node_key, "version": rule.version}
                    ),
                )
            )
        for link in links:
            if link.relation == "CONTROLS":
                db.add(
                    CompiledAssetComponent(
                        document_version_id=version.id,
                        component_type="CONTROL",
                        component_ref_id=link.id,
                        activity_id=link.activity_id,
                        source_hash=_hash_json(
                            {
                                "link_id": link.id,
                                "node_key": link.node_key,
                                "activity_id": link.activity_id,
                            }
                        ),
                    )
                )
    for row in data["raci"]:
        db.add(
            CompiledAssetComponent(
                document_version_id=version.id,
                component_type="RACI",
                component_ref_id=row.id,
                activity_id=None,
                source_hash=_hash_json(
                    {
                        "raci_id": row.id,
                        "matter": row.matter,
                        "role_id": row.role_id,
                        "raci": row.raci,
                    }
                ),
            )
        )
    for claim in data["claims"].claims:
        for target in claim.targets:
            if target.target_type == "KPI":
                db.add(
                    CompiledAssetComponent(
                        document_version_id=version.id,
                        component_type="KPI_REF",
                        component_ref_id=target.target_id,
                        source_hash=_hash_json({"claim_id": claim.id, "kpi_id": target.target_id}),
                    )
                )


def commit(db: Session, process: ProcessArch, user: User) -> AssetPackageOut:
    data = _collect(db, process)
    if not data["can_generate"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "存在硬阻断，拒绝生成资产包。",
                "blockers": [row.model_dump() for row in data["readiness"].blockers],
            },
        )
    readiness = data["readiness"]
    code = f"{DOC_PREFIX}{process.code}"
    document = db.scalar(select(ProcessDocument).where(ProcessDocument.code == code))
    if document is None:
        document = ProcessDocument(
            process_id=process.id,
            code=code,
            title=f"{process.name} · 资产包",
            category="SOP",
            description="由已发布模型、架构关系与证据主张生成；不是人工上传文件。",
            level="PROCESS",
            language="zh-CN",
            owner=process.owner,
            owner_user_id=process.owner_user_id,
            org_unit_id=process.org_unit_id,
        )
        db.add(document)
        db.flush()
    elif document.process_id != process.id or document.category != "SOP":
        raise HTTPException(409, "资产包编码已被其他对象占用。")

    label = _next_version_label(document)
    html = data["html"]
    storage = storage_service.get_storage()
    key = storage_service.build_key(
        f"asset-packages/{process.id}", f"{process.code}-asset-package.html"
    )
    try:
        digest, size = storage.save(
            key,
            io.BytesIO(html.encode("utf-8")),
            storage_service.max_bytes(),
        )
    except Exception as exc:  # noqa: BLE001 - 存储层错误统一转 500
        raise HTTPException(500, "资产包文件写入失败。") from exc

    try:
        version = document_service.create_version(
            db,
            document,
            {
                "version_label": label,
                "note": f"资产包生成 · 模型 v{readiness.model_version}",
            },
            user,
            file_meta={
                "file_name": f"{process.code}-asset-package.html",
                "mime_type": "text/html",
                "size_bytes": size,
                "checksum": digest,
                "storage_backend": "local",
                "storage_key": key,
            },
        )
        version.source_kind = "COMPILED"
        version.compile_manifest = data["manifest"]
        _add_components(db, version, data)
        db.flush()
        audit.record(
            db,
            user,
            "CREATE",
            "process_document_version",
            version.id,
            f"{code} v{label} 资产包生成（模型 v{readiness.model_version}）",
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


def get_package(db: Session, user: User, version_id: int) -> AssetPackageOut:
    version = db.get(ProcessDocumentVersion, version_id)
    if (
        version is None
        or version.source_kind != "COMPILED"
        or (version.compile_manifest or {}).get("kind") == "JOB_DESCRIPTION"
    ):
        raise HTTPException(404, "资产包版本不存在。")
    document = db.get(ProcessDocument, version.document_id)
    if document is None:
        raise HTTPException(404, "资产包文档不存在。")
    asset_service.require_process(db, user, document.process_id)
    html = None
    if version.storage_key:
        storage = storage_service.get_storage()
        try:
            with storage.open(version.storage_key) as handle:
                html = handle.read().decode("utf-8")
        except FileNotFoundError:
            html = None
    return package_out(document, version, preview_html=html)


def transition_by_id(
    db: Session,
    user: User,
    version_id: int,
    target: str,
    note: Optional[str],
) -> AssetPackageOut:
    version = db.get(ProcessDocumentVersion, version_id)
    if (
        version is None
        or version.source_kind != "COMPILED"
        or (version.compile_manifest or {}).get("kind") == "JOB_DESCRIPTION"
    ):
        raise HTTPException(404, "资产包版本不存在。")
    document = db.get(ProcessDocument, version.document_id)
    if document is None:
        raise HTTPException(404, "资产包文档不存在。")
    process = asset_service.require_process(db, user, document.process_id)
    return transition(db, process, version_id, target, note, user)


def transition(
    db: Session,
    process: ProcessArch,
    version_id: int,
    target: str,
    note: Optional[str],
    user: User,
) -> AssetPackageOut:
    version = db.get(ProcessDocumentVersion, version_id)
    if (
        version is None
        or version.source_kind != "COMPILED"
        or (version.compile_manifest or {}).get("kind") == "JOB_DESCRIPTION"
    ):
        raise HTTPException(404, "资产包版本不存在。")
    document = db.get(ProcessDocument, version.document_id)
    if document is None or document.process_id != process.id:
        raise HTTPException(404, "资产包不属于该流程。")

    try:
        version = document_service.transition_version(db, document, version, target, user)
    except document_service.ProcessDocumentError as exc:
        raise HTTPException(400, str(exc)) from exc
    audit.record(
        db,
        user,
        "UPDATE",
        "process_document_version",
        version.id,
        f"{document.code} v{version.version_label} → {target}" + (f"（{note}）" if note else ""),
    )
    db.commit()
    db.refresh(version)
    db.refresh(document)
    return get_package(db, user, version.id)


def package_out(
    document: ProcessDocument,
    version: ProcessDocumentVersion,
    *,
    preview_html: Optional[str] = None,
) -> AssetPackageOut:
    manifest = version.compile_manifest or {}
    pdf_available = preview_service.converter_available()
    return AssetPackageOut(
        kind=manifest.get("kind", "ASSET_PACKAGE"),
        document_id=document.id,
        document_code=document.code,
        document_title=document.title,
        version_id=version.id,
        version_label=version.version_label,
        status=version.status,
        status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
        manifest=manifest,
        preview_html=preview_html,
        content_hash=manifest.get("content_hash"),
        download_url=(
            f"{settings.api_prefix}/process-documents/{document.id}/versions/{version.id}/download"
            if version.storage_key
            else None
        ),
        pdf_available=pdf_available,
        pdf_url=(
            f"{settings.api_prefix}/asset-packages/{version.id}/pdf"
            if pdf_available and version.storage_key
            else None
        ),
    )


def component_impact(
    db: Session,
    user: User,
    *,
    component_type: Optional[str] = None,
    component_ref_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    limit: int = 100,
) -> AssetImpactOut:
    """反向查询：给定活动/组件，列出引用了它的资产包版本。"""
    if component_type is not None and component_type not in COMPONENT_LABELS:
        raise HTTPException(400, "不支持的组件类型。")
    if activity_id is None and (component_type is None or component_ref_id is None):
        raise HTTPException(400, "请给出 activity_id，或 component_type + component_ref_id。")

    stmt = select(CompiledAssetComponent)
    if component_type is not None:
        stmt = stmt.where(CompiledAssetComponent.component_type == component_type)
    if component_ref_id is not None:
        stmt = stmt.where(CompiledAssetComponent.component_ref_id == component_ref_id)
    if activity_id is not None:
        stmt = stmt.where(CompiledAssetComponent.activity_id == activity_id)
    rows = list(
        db.scalars(
            stmt.order_by(CompiledAssetComponent.id.desc()).limit(max(1, min(limit, 500)))
        ).all()
    )

    version_ids = {row.document_version_id for row in rows}
    versions = (
        {
            row.id: row
            for row in db.scalars(
                select(ProcessDocumentVersion).where(
                    ProcessDocumentVersion.id.in_(version_ids),
                    ProcessDocumentVersion.source_kind == "COMPILED",
                )
            ).all()
        }
        if version_ids
        else {}
    )
    document_ids = {row.document_id for row in versions.values()}
    documents = (
        {
            row.id: row
            for row in db.scalars(
                select(ProcessDocument).where(ProcessDocument.id.in_(document_ids))
            ).all()
        }
        if document_ids
        else {}
    )
    process_ids = {row.process_id for row in documents.values()}
    processes = (
        {
            row.id: row
            for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(process_ids))).all()
        }
        if process_ids
        else {}
    )
    visible: set[int] = set()
    for pid in process_ids:
        try:
            asset_service.require_process(db, user, pid)
            visible.add(pid)
        except HTTPException:
            continue

    activity_ids = {row.activity_id for row in rows if row.activity_id is not None}
    activities = (
        {
            row.id: row
            for row in db.scalars(select(ProcessArch).where(ProcessArch.id.in_(activity_ids))).all()
        }
        if activity_ids
        else {}
    )

    items: list[AssetComponentImpactItem] = []
    seen: set[tuple] = set()
    for row in rows:
        version = versions.get(row.document_version_id)
        if version is None:
            continue
        document = documents.get(version.document_id)
        if document is None or document.process_id not in visible:
            continue
        key = (
            version.id,
            row.component_type,
            row.component_ref_id,
            row.activity_id,
        )
        if key in seen:
            continue
        seen.add(key)
        process = processes.get(document.process_id)
        activity = activities.get(row.activity_id) if row.activity_id else None
        items.append(
            AssetComponentImpactItem(
                document_id=document.id,
                document_code=document.code,
                document_title=document.title,
                version_id=version.id,
                version_label=version.version_label,
                version_status=version.status,
                version_status_label=deliverable_service.STATUS_LABELS.get(
                    version.status, version.status
                ),
                process_id=document.process_id,
                process_code=process.code if process else None,
                process_name=process.name if process else None,
                component_type=row.component_type,
                component_type_label=COMPONENT_LABELS.get(row.component_type, row.component_type),
                component_ref_id=row.component_ref_id,
                activity_id=row.activity_id,
                activity_code=activity.code if activity else None,
                activity_name=activity.name if activity else None,
                source_hash=row.source_hash,
                created_at=row.created_at,
            )
        )

    return AssetImpactOut(
        query={
            "component_type": component_type,
            "component_ref_id": component_ref_id,
            "activity_id": activity_id,
        },
        total=len(items),
        items=items,
        labels=COMPONENT_LABELS,
    )


def build_print_pack(
    db: Session,
    user: User,
    process: ProcessArch,
    version_ids: Optional[List[int]] = None,
) -> str:
    """把一条流程的已生成资产包版本合并为一份可打印 HTML。"""
    asset_service.require_process(db, user, process.id)
    document = db.scalar(
        select(ProcessDocument).where(ProcessDocument.code == f"{DOC_PREFIX}{process.code}")
    )
    if document is None:
        raise HTTPException(404, "该流程还没有生成资产包。")
    versions = list(
        db.scalars(
            select(ProcessDocumentVersion)
            .where(
                ProcessDocumentVersion.document_id == document.id,
                ProcessDocumentVersion.source_kind == "COMPILED",
            )
            .order_by(ProcessDocumentVersion.id.desc())
        ).all()
    )
    if version_ids:
        selected = set(version_ids)
        versions = [version for version in versions if version.id in selected]
    if not versions:
        raise HTTPException(404, "没有可打印的资产包版本。")

    storage = storage_service.get_storage()
    extracted_style = ""
    sections: List[str] = []
    for version in versions:
        body = "<p>资产包文件不存在或已被清理。</p>"
        if version.storage_key:
            try:
                with storage.open(version.storage_key) as handle:
                    html = handle.read().decode("utf-8")
                if not extracted_style:
                    style_match = re.search(r"<style>(.*?)</style>", html, re.S)
                    if style_match:
                        extracted_style = style_match.group(1)
                body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
                if body_match:
                    body = body_match.group(1)
            except FileNotFoundError:
                pass
        manifest = version.compile_manifest or {}
        status_label = deliverable_service.STATUS_LABELS.get(version.status, version.status)
        sections.append(
            f"""<section class="pkg">
  <div class="pkg-cover">
    <div class="tiny">流程资产包</div>
    <h1>{_e(document.code)} · v{_e(version.version_label)}</h1>
    <div class="meta">状态 {_e(status_label)}
      · 模型 v{_e(manifest.get("model_version", "—"))}
      · 生成于 {_e(manifest.get("generated_at", "—"))}
      · hash {_e(str(manifest.get("content_hash", ""))[:12])}</div>
  </div>
  {body}
</section>"""
        )

    generated = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    base_style = """
  @page { size: A4; margin: 14mm; }
  * { box-sizing: border-box; }
  body { font: 12px/1.55 "Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         color:#111; margin:0; }
  h1 { font-size:20px; margin:0 0 4px; }
  h2 { font-size:14px; margin:18px 0 7px; border-bottom:1px solid #999;
       padding-bottom:4px; }
  table { width:100%; border-collapse:collapse; margin:6px 0 8px; }
  th,td { border:1px solid #aaa; padding:4px 6px; text-align:left;
          vertical-align:top; }
  th { background:#eee; font-size:10.5px; }
  .tiny { font-size:10.5px; color:#666; }
  .meta { color:#444; font-size:11px; margin-bottom:8px; }
  .pp-cover { padding:36mm 0 10mm; }
  .pp-cover h1 { font-size:26px; }
  .pkg { page-break-before: always; }
  .pkg-cover { border-bottom:2px solid #999; margin-bottom:10px;
               padding-bottom:6px; }
  .pkg-cover h1 { font-size:18px; margin:2px 0; }
  @media print { h2 { page-break-after:avoid; } tr { page-break-inside:avoid; } }
"""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{_e(process.code)} 资产包打印包</title>
<style>{base_style}{extracted_style}</style>
</head><body>
  <section class="pp-cover">
    <div class="tiny">流程资产打印包</div>
    <h1>{_e(process.code)} {_e(process.name)}</h1>
    <div class="meta">Owner {_e(process.owner or "未指定")}
      · 资产包 {len(versions)} 个版本
      · 生成于 {_e(generated)}</div>
    <div class="tiny">内容以各版本生成清单为准；打印包只是合并视图，不改变原版本。</div>
  </section>
  {"".join(sections)}
</body></html>"""


def validate_for_transition(db, document, version, target, user):
    """两种文档入口共用；诊断只走原诊断守卫，不套正式资产完整度。"""
    if target not in {"IN_REVIEW", "APPROVED", "EFFECTIVE"}:
        return
    manifest = version.compile_manifest or {}
    if version.source_kind != "COMPILED":
        raise HTTPException(409, "生成产物的人工替代版本不能正式流转，请回原入口重新编译。")
    if manifest.get("kind") in {"DIAGNOSIS", "DIAGNOSIS_R1"}:
        from app.services import diagnosis

        diagnosis.r1_transition_guard(db, user, version.id)
        return
    process = asset_service.require_process(db, user, document.process_id)
    readiness = asset_service.readiness(db, process, user)
    if readiness.blockers:
        raise HTTPException(
            409,
            {
                "message": "阻断未清零，不能提交评审或生效。",
                "blockers": [b.model_dump() for b in readiness.blockers],
            },
        )
    from app.services.binding_readiness import binding_gate

    current = binding_gate(
        db, process.id, profile="PERFORMANCE", model_version_id=readiness.model_version_id
    )
    if (
        manifest.get("model_version_id") != readiness.model_version_id
        or manifest.get("binding_fingerprint") != current.fingerprint
    ):
        raise HTTPException(409, "模型或绑定依据已变化（或缺少固定指纹），请重新生成资产包。")
