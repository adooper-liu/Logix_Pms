"""原证据来源解析，结构就绪度与绑定指纹共用；不复制秘密或源正文。"""

from fastapi import HTTPException
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models.log_import import ProcessLogImport
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.tool_sheet import ToolSheet
from app.services import handoff, org_access
from app.services.process_document import visible_conditions


def resolve(db, process, claim, user=None):
    """返回有效原对象；None表示失效/范围不适用/不可见，不猜来源。"""
    if claim.source_type == "TOOL_SHEET":
        row = db.get(ToolSheet, claim.source_id) if claim.source_id else None
        if row is None or row.process_id != process.id:
            return None
        if user:
            try:
                handoff.require_sheet(db, user, row.tool_code, row.id)
            except HTTPException:
                return None
        return row
    if claim.source_type == "DOCUMENT_VERSION":
        row = db.get(ProcessDocumentVersion, claim.source_id) if claim.source_id else None
        if row is None or row.status != "EFFECTIVE":
            return None
        document = db.get(ProcessDocument, row.document_id)
        if document is None or not document.is_active:
            return None
        from app.services import process_scope

        if not process_scope.is_document_applicable(db, document.process_id, process.id):
            return None
        today = utcnow().date()
        if row.valid_from and row.valid_from > today or row.valid_to and row.valid_to < today:
            return None
        stmt = select(ProcessDocument.id).where(ProcessDocument.id == document.id)
        condition = visible_conditions(db, process.org_unit_id)
        if condition is not None:
            stmt = stmt.where(condition)
        if user and not org_access.unrestricted(user):
            condition = visible_conditions(db, user.org_unit_id)
            stmt = (
                stmt.where(condition)
                if condition is not None
                else stmt.where(ProcessDocument.org_unit_id.is_(None))
            )
        return row if db.scalar(stmt) is not None else None
    if claim.source_type == "LOG_IMPORT":
        row = db.get(ProcessLogImport, claim.source_id) if claim.source_id else None
        if row is None or row.process_id != process.id or row.status != "COMMITTED":
            return None
        if user:
            try:
                org_access.ensure_visible(db, user, process.org_unit_id)
            except HTTPException:
                return None
        return row
    return None
