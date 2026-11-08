"""文档 → 候选活动：解析编号步骤，人工确认后才写 L4 活动。

边界：

- 只支持 txt/md/csv/docx 的文本读取；不调用外部 OCR/大模型。
- 候选不是 As-Is 实测，也不自动改 BPMN；确认只创建 L4 架构活动。
- 重复提取只清理未处理候选，已确认/已驳回的行保留。
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import List, Tuple
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.document_candidate import DocumentCandidateActivity
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.user import User
from app.schemas.document_candidate import DocumentCandidateConfirmIn, DocumentCandidateOut
from app.services import audit, process_scope
from app.services import storage as storage_service

_ARABIC = re.compile(r"^\s*[（(]?(\d{1,3})[）).、]\s*(.+?)\s*$")
_CHINESE = re.compile(r"^\s*([一二三四五六七八九十]{1,3})[、.]\s*(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*•·]\s*(.+?)\s*$")
_MAX_CANDIDATES = 200
_MAX_TEXT = 200


def _read_text(version: ProcessDocumentVersion) -> str:
    if not version.storage_key:
        raise HTTPException(400, "该文档版本没有文件，无法提取。")
    suffix = Path(version.file_name or "").suffix.lower()
    storage = storage_service.get_storage()
    try:
        with storage.open(version.storage_key) as handle:
            data = handle.read()
    except FileNotFoundError as exc:
        raise HTTPException(404, "文档文件不存在或已被清理。") from exc

    if suffix in {".txt", ".md", ".csv"}:
        return data.decode("utf-8", errors="replace")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise HTTPException(400, "docx 文件结构无法解析。") from exc
        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: List[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
            paragraphs.append("".join(texts))
        return "\n".join(paragraphs)
    raise HTTPException(400, "暂不支持从该文件类型提取；请上传 txt / md / csv / docx。")


def _parse_candidates(text: str) -> List[Tuple[int, str, str, str]]:
    seen: set[str] = set()
    result: List[Tuple[int, str, str, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or len(line) > _MAX_TEXT:
            continue
        match = _ARABIC.match(line)
        confidence = "NUMBERED"
        if match:
            candidate = match.group(2)
        else:
            match = _CHINESE.match(line)
            if match:
                candidate = match.group(2)
            else:
                match = _BULLET.match(line)
                confidence = "BULLET"
                if not match:
                    continue
                candidate = match.group(1)
        candidate = candidate.strip(" \t。；;，,")
        if len(candidate) < 2:
            continue
        key = re.sub(r"\s+", "", candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append((line_no, candidate, candidate[:128], confidence))
        if len(result) >= _MAX_CANDIDATES:
            break
    return result


def _require_version(
    db: Session,
    process: ProcessArch,
    document_version_id: int,
    *,
    require_effective: bool = True,
) -> Tuple[ProcessDocumentVersion, ProcessDocument]:
    version = db.get(ProcessDocumentVersion, document_version_id)
    if version is None:
        raise HTTPException(404, "文档版本不存在。")
    document = db.get(ProcessDocument, version.document_id)
    if document is None:
        raise HTTPException(404, "文档不存在。")
    if not process_scope.is_document_applicable(db, document.process_id, process.id):
        raise HTTPException(400, "文档不属于该流程的适用范围。")
    if require_effective and version.status != "EFFECTIVE":
        raise HTTPException(400, "只能从已生效的文档版本提取候选活动。")
    return version, document


def _out(db: Session, row: DocumentCandidateActivity) -> DocumentCandidateOut:
    activity = db.get(ProcessArch, row.activity_id) if row.activity_id else None
    return DocumentCandidateOut(
        id=row.id,
        document_version_id=row.document_version_id,
        process_id=row.process_id,
        line_no=row.line_no,
        text=row.text,
        name=row.name,
        confidence=row.confidence,
        status=row.status,
        activity_id=row.activity_id,
        activity_code=activity.code if activity else None,
        activity_name=activity.name if activity else None,
        created_by_name=row.created_by_name,
        confirmed_by_name=row.confirmed_by_name,
        confirmed_at=row.confirmed_at,
        created_at=row.created_at,
    )


def list_candidates(
    db: Session, process: ProcessArch, document_version_id: int
) -> List[DocumentCandidateOut]:
    _require_version(db, process, document_version_id, require_effective=False)
    rows = db.scalars(
        select(DocumentCandidateActivity)
        .where(
            DocumentCandidateActivity.process_id == process.id,
            DocumentCandidateActivity.document_version_id == document_version_id,
        )
        .order_by(DocumentCandidateActivity.line_no)
    ).all()
    return [_out(db, row) for row in rows]


def extract(
    db: Session,
    process: ProcessArch,
    user: User,
    document_version_id: int,
    *,
    force: bool = False,
) -> List[DocumentCandidateOut]:
    version, document = _require_version(db, process, document_version_id)
    existing = list(
        db.scalars(
            select(DocumentCandidateActivity)
            .where(
                DocumentCandidateActivity.process_id == process.id,
                DocumentCandidateActivity.document_version_id == version.id,
            )
            .order_by(DocumentCandidateActivity.line_no)
        ).all()
    )
    if existing and not force:
        return [_out(db, row) for row in existing]

    occupied: set[int] = set()
    if force:
        for row in existing:
            if row.status == "PROPOSED":
                db.delete(row)
            else:
                occupied.add(row.line_no)
        db.flush()

    parsed = _parse_candidates(_read_text(version))
    created = 0
    for line_no, text, name, confidence in parsed:
        if line_no in occupied:
            continue
        db.add(
            DocumentCandidateActivity(
                document_version_id=version.id,
                process_id=process.id,
                line_no=line_no,
                text=text,
                name=name,
                confidence=confidence,
                status="PROPOSED",
                created_by_id=user.id,
                created_by_name=user.display_name,
            )
        )
        created += 1
    db.flush()
    audit.record(
        db,
        user,
        "CREATE",
        "process_document_version",
        version.id,
        f"从 {document.code} v{version.version_label} 提取 {created} 条候选活动",
    )
    db.commit()
    return list_candidates(db, process, version.id)


def _next_activity_code(db: Session, process: ProcessArch) -> str:
    for index in range(1, 1000):
        code = f"L4C{process.id}-{index:03d}"
        if db.scalar(select(ProcessArch.id).where(ProcessArch.code == code)) is None:
            return code
    raise HTTPException(409, "该流程的候选活动编码已用尽。")


def confirm(
    db: Session,
    process: ProcessArch,
    candidate_id: int,
    payload: DocumentCandidateConfirmIn,
    user: User,
) -> DocumentCandidateOut:
    row = db.get(DocumentCandidateActivity, candidate_id)
    if row is None or row.process_id != process.id:
        raise HTTPException(404, "候选活动不存在。")
    if row.status == "CONFIRMED" and row.activity_id:
        return _out(db, row)
    if row.status != "PROPOSED":
        raise HTTPException(400, "只能确认待处理候选。")

    name = (payload.name or row.name).strip()
    if not name:
        raise HTTPException(400, "活动名称不能为空。")
    code = (payload.code or "").strip() or _next_activity_code(db, process)
    if len(code) > 32:
        raise HTTPException(400, "活动编码最多 32 个字符。")
    if db.scalar(select(ProcessArch.id).where(ProcessArch.code == code)) is not None:
        raise HTTPException(409, "活动编码已存在。")

    version, document = _require_version(
        db, process, row.document_version_id, require_effective=False
    )
    activity = ProcessArch(
        code=code,
        name=name[:128],
        level=4,
        parent_id=process.id,
        owner=payload.owner or process.owner,
        owner_user_id=process.owner_user_id,
        org_unit_id=process.org_unit_id,
        description=(
            f"从文档 {document.code} v{version.version_label} 第 {row.line_no} 行提取；人工确认。"
            "尚未映射到 BPMN 节点。"
        ),
    )
    db.add(activity)
    db.flush()
    row.status = "CONFIRMED"
    row.activity_id = activity.id
    row.confirmed_by_id = user.id
    row.confirmed_by_name = user.display_name
    row.confirmed_at = utcnow()
    audit.record(
        db,
        user,
        "UPDATE",
        "document_candidate_activity",
        row.id,
        f"确认候选 -> {activity.code} {activity.name}",
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)


def reject(
    db: Session, process: ProcessArch, candidate_id: int, user: User
) -> DocumentCandidateOut:
    row = db.get(DocumentCandidateActivity, candidate_id)
    if row is None or row.process_id != process.id:
        raise HTTPException(404, "候选活动不存在。")
    if row.status != "PROPOSED":
        raise HTTPException(400, "只能驳回待处理候选。")
    row.status = "REJECTED"
    row.confirmed_by_id = user.id
    row.confirmed_by_name = user.display_name
    row.confirmed_at = utcnow()
    audit.record(
        db,
        user,
        "UPDATE",
        "document_candidate_activity",
        row.id,
        "驳回候选",
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)
