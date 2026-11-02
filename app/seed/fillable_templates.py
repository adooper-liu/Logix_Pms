"""把每份工具的填写格子放进工具模板库。已有同编码模板则不覆盖。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DeliverableStatus, TemplateFormat
from app.models.tool_template import ToolTemplate, ToolTemplateVersion
from app.seed.sheet_templates import SHEET_TEMPLATES


def ensure_fillable_templates(db: Session) -> int:
    created = 0
    for code, name, tool_code, fields in SHEET_TEMPLATES:
        existing = db.scalar(select(ToolTemplate).where(ToolTemplate.code == code))
        if existing is not None:
            continue
        for other in db.scalars(
            select(ToolTemplate).where(
                ToolTemplate.tool_code == tool_code,
                ToolTemplate.is_default.is_(True),
            )
        ):
            other.is_default = False
        template = ToolTemplate(
            tool_code=tool_code,
            code=code,
            name=name,
            format=TemplateFormat.ONLINE.value,
            description="填写并挂上时使用的在线检查表。",
            is_default=True,
            is_active=True,
        )
        db.add(template)
        db.flush()
        version = ToolTemplateVersion(
            template_id=template.id,
            version_label="1.0.0",
            status=DeliverableStatus.EFFECTIVE.value,
            note="首版填写格子",
            placeholders=[],
            sheet_fields=fields,
            created_by="系统",
        )
        db.add(version)
        db.flush()
        template.current_version_id = version.id
        created += 1
    return created
