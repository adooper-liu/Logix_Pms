"""把工具步骤收成可填写的模板，保存后挂到流程，并按工具写成目标。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.process import ProcessArch
from app.models.project import Project
from app.models.tool import Tool
from app.models.tool_sheet import ToolSheet
from app.models.tool_template import ToolTemplate
from app.models.user import User
from app.schemas.tool_sheet import SheetFieldOut, SheetFieldSpec, SheetFormOut, ToolSheetOut
from app.services import strategy as strategy_service
from app.services.tool_template import effective_version

_MAX_VALUE = 2000


class ToolSheetError(ValueError):
    """填写内容不符合这张模板。"""


def _field(key: str, label: str, *, required: bool = False, multiline: bool = False) -> dict:
    return {"key": key, "label": label, "required": required, "multiline": multiline}


# 这四张表的格子对应库里已有的目标或承接，不只是一段说明。
_SPECS: Dict[str, dict] = {
    "OGSM": {
        "writes": "objective",
        "allow_keep": False,
        "fields": [
            _field("direction", "方向：这一年要赢什么", required=True),
            _field("baseline", "基线", required=True),
            _field("target", "目标值", required=True),
            _field("unit", "单位", required=True),
            _field("approach", "打法：靠哪几条流程做到", multiline=True),
            _field("measure", "用什么衡量", multiline=True),
            _field("source", "来源文件"),
        ],
    },
    "SWOT": {
        "writes": "mount",
        "allow_keep": True,
        "fields": [
            _field("strengths", "优势（每条要能指出事实）", required=True, multiline=True),
            _field("weaknesses", "劣势", multiline=True),
            _field("opportunities", "机会", multiline=True),
            _field("threats", "威胁", multiline=True),
            _field("keep", "今年留下的几条，一行一条", multiline=True),
        ],
    },
    "GOAL-TREE": {
        "writes": "objective",
        "allow_keep": False,
        "fields": [
            _field("result", "顶端：公司要赢的结果", required=True),
            _field("breakdown", "拆成能独立负责的几条，一行一条", multiline=True),
        ],
    },
    "DECISION-MATRIX": {
        "writes": "mount",
        "allow_keep": False,
        "fields": [
            _field("options", "备选方案，一行一条", required=True, multiline=True),
            _field("criteria", "比较用的维度和权重", multiline=True),
            _field("choice", "留下哪一个", required=True),
            _field("reason", "为什么留下它", multiline=True),
        ],
    },
}


def _library_form(db: Session, tool: Tool) -> Optional[SheetFormOut]:
    template = db.scalar(
        select(ToolTemplate)
        .where(ToolTemplate.code == f"TPL-{tool.code}", ToolTemplate.is_active.is_(True))
        .options(selectinload(ToolTemplate.versions))
    )
    if template is None:
        return None
    version = effective_version(template)
    rows = list(version.sheet_fields or []) if version is not None else []
    if not rows:
        return None
    spec = _SPECS.get(tool.code, {"writes": "mount", "allow_keep": False})
    fields = []
    for row in rows:
        options = list(row.get("options") or [])
        fields.append(
            SheetFieldSpec(
                key=row["key"],
                label=row["label"],
                required=bool(row.get("required")),
                multiline=bool(row.get("multiline")),
                kind=row.get("kind") or ("choice" if options else "text"),
                options=options,
            )
        )
    return SheetFormOut(
        tool_code=tool.code,
        tool_name=tool.name,
        writes=spec["writes"],
        allow_keep=spec["allow_keep"],
        fields=fields,
        template_code=template.code,
        template_name=template.name,
        template_version=version.version_label if version is not None else None,
        template_version_id=version.id if version is not None else None,
        source_note=f"来自工具模板库 {template.name}",
    )


def form_for(db: Session, tool: Tool) -> SheetFormOut:
    loaded = _library_form(db, tool)
    if loaded is not None:
        return loaded
    spec = _SPECS.get(tool.code)
    if spec is None:
        return SheetFormOut(
            tool_code=tool.code,
            tool_name=tool.name,
            writes="mount",
            allow_keep=False,
            fields=[],
            source_note="工具模板库还没有这份可填写的模板。",
        )
    return SheetFormOut(
        tool_code=tool.code,
        tool_name=tool.name,
        writes=spec["writes"],
        allow_keep=spec["allow_keep"],
        fields=[SheetFieldSpec(**row) for row in spec["fields"]],
        source_note="工具模板库还没有生效版本，暂时用内置格子。",
    )


def _clean(values: Dict[str, str], key: str) -> str:
    text = (values.get(key) or "").strip()
    if len(text) > _MAX_VALUE:
        raise ToolSheetError(f"「{key}」超过 {_MAX_VALUE} 字")
    return text


def _number(text: str, label: str) -> float:
    raw = text.replace(",", "").replace("%", "").strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ToolSheetError(f"{label}要填数字") from exc


def _require_process(db: Session, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ToolSheetError(f"流程 {process_id} 不存在")
    if process.is_draft:
        raise ToolSheetError("草稿流程还不能挂模板结果")
    return process


def _require_project(db: Session, project_id: Optional[int]) -> Optional[int]:
    if project_id is None:
        return None
    if db.get(Project, project_id) is None:
        raise ToolSheetError(f"项目 {project_id} 不存在")
    return project_id


def _new_objective(
    db: Session,
    user: User,
    *,
    name: str,
    description: str,
    source: str,
    baseline: Optional[float] = None,
    target: Optional[float] = None,
    unit: Optional[str] = None,
):
    return strategy_service.create_objective(
        db,
        {
            "name": name[:160],
            "description": description or None,
            "year": date.today().year,
            "period": "ANNUAL",
            "baseline_value": baseline,
            "target_value": target,
            "unit": (unit or None),
            "source_document": source[:200],
            "owner": user.display_name,
            "owner_user_id": user.id,
            "status": "ACTIVE",
        },
    )


def _link(db: Session, objective, process_id: int, note: str) -> None:
    strategy_service.add_link(db, objective, process_id=process_id, kpi_id=None, note=note[:200])


def _write_records(
    db: Session,
    tool: Tool,
    user: User,
    process: ProcessArch,
    values: Dict[str, str],
    make_objectives: bool,
    spec: SheetFormOut,
):
    """返回 (标题, 主目标 id, 写成的目标编码)。"""
    code = tool.code
    if code == "OGSM":
        direction = _clean(values, "direction")
        baseline = _number(_clean(values, "baseline"), "基线")
        target = _number(_clean(values, "target"), "目标值")
        unit = _clean(values, "unit")
        if not direction or not unit:
            raise ToolSheetError("方向和单位都要填")
        parts = [part for part in (_clean(values, "approach"), _clean(values, "measure")) if part]
        row = _new_objective(
            db,
            user,
            name=direction,
            description="\n".join(parts),
            source=_clean(values, "source") or "OGSM 一页纸",
            baseline=baseline,
            target=target,
            unit=unit[:24],
        )
        _link(db, row, process.id, "OGSM 一页纸")
        return direction[:160], row.id, [row.code]
    if code == "GOAL-TREE":
        result = _clean(values, "result")
        if not result:
            raise ToolSheetError("先写顶端要赢的结果")
        row = _new_objective(
            db,
            user,
            name=result,
            description=_clean(values, "breakdown"),
            source="目标树",
        )
        _link(db, row, process.id, "目标树")
        return result[:160], row.id, [row.code]
    if code == "SWOT":
        quadrants = [
            _clean(values, key) for key in ("strengths", "weaknesses", "opportunities", "threats")
        ]
        if not any(quadrants):
            raise ToolSheetError("四格里至少写一格")
        codes: List[str] = []
        first_id = None
        if make_objectives:
            lines = [line.strip()[:160] for line in _clean(values, "keep").splitlines()]
            lines = [line for line in lines if line][:5]
            if not lines:
                raise ToolSheetError("要写成目标时，「留下」里至少写一行")
            for line in lines:
                row = _new_objective(
                    db, user, name=line, description="从 SWOT 留下", source="SWOT 取舍"
                )
                _link(db, row, process.id, "SWOT 取舍")
                codes.append(row.code)
                if first_id is None:
                    first_id = row.id
        return "SWOT 取舍", first_id, codes
    if code == "DECISION-MATRIX":
        if not _clean(values, "options") or not _clean(values, "choice"):
            raise ToolSheetError("备选方案和留下的那一个都要填")
        return _clean(values, "choice")[:160], None, []
    filled = [_clean(values, field.key) for field in spec.fields]
    filled = [text for text in filled if text]
    if not filled:
        raise ToolSheetError("至少写一条结论")
    return filled[0][:160], None, []


def save_sheet(
    db: Session,
    tool: Tool,
    user: User,
    *,
    process_id: int,
    project_id: Optional[int],
    step_no: Optional[str],
    values: Dict[str, str],
    make_objectives: bool,
    handoff=None,
    template_version_id=None,
) -> ToolSheetOut:
    process = _require_process(db, process_id)
    from app.services import handoff as handoff_service
    from app.services import org_access

    project_id = _require_project(db, project_id)
    if project_id is not None:
        project = db.get(Project, project_id)
        org_access.ensure_visible(db, user, project.org_unit_id)
        if project.process_id != process_id:
            raise ToolSheetError("项目与所选流程不一致")
    handoff_data = handoff_service.prepare(db, user, tool, process, handoff)
    spec = form_for(db, tool)
    if template_version_id is not None and template_version_id != spec.template_version_id:
        from fastapi import HTTPException

        raise HTTPException(409, "模板版本已变化，请重新打开填写，原输入尚未保存")
    if not spec.fields:
        raise ToolSheetError(spec.source_note or "工具模板库还没有这份可填写的模板")
    for field in spec.fields:
        text = _clean(values, field.key)
        if field.required and not text:
            raise ToolSheetError(f"请填写{field.label}")
        if text and field.options and text not in field.options:
            raise ToolSheetError(f"{field.label}要在给出的选项里选")
    title, objective_id, codes = _write_records(
        db, tool, user, process, values, make_objectives, spec
    )
    stored = [
        {"key": field.key, "label": field.label, "value": _clean(values, field.key)}
        for field in spec.fields
        if _clean(values, field.key)
    ]
    row = ToolSheet(
        tool_code=tool.code,
        template_version_id=spec.template_version_id,
        handoff=handoff_data,
        process_id=process.id,
        project_id=project_id,
        objective_id=objective_id,
        step_no=(step_no or "").strip() or None,
        title=title or tool.name,
        fields=stored,
        created_by=user.display_name,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    return _out(db, row, tool.name, codes)


def _out(db: Session, row: ToolSheet, tool_name: str, codes: List[str]) -> ToolSheetOut:
    from app.services.handoff import label
    from app.services.workbench import review_label

    process = db.get(ProcessArch, row.process_id)
    fields = row.fields if isinstance(row.fields, list) else []
    return ToolSheetOut(
        id=row.id,
        tool_code=row.tool_code,
        tool_name=tool_name,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        project_id=row.project_id,
        objective_id=row.objective_id,
        objective_codes=codes,
        step_no=row.step_no,
        title=row.title,
        fields=[SheetFieldOut(**item) for item in fields if isinstance(item, dict)],
        created_by=row.created_by,
        created_at=row.created_at,
        template_version_id=row.template_version_id,
        handoff=row.handoff,
        revision=row.revision,
        confirmation_label=label(row.handoff),
        work_context=row.work_context,
        review=row.review,
        review_label=review_label(db, row),
    )


def sheets_for_process(db: Session, process_id: int, limit: int = 5) -> List[dict]:
    rows = db.scalars(
        select(ToolSheet)
        .where(ToolSheet.process_id == process_id)
        .order_by(ToolSheet.id.desc())
        .limit(limit)
    ).all()
    if not rows:
        return []
    names = {
        tool.code: tool.name
        for tool in db.scalars(
            select(Tool).where(Tool.code.in_({row.tool_code for row in rows}))
        ).all()
    }
    result = []
    for row in rows:
        fields = row.fields if isinstance(row.fields, list) else []
        summary = "；".join(
            item.get("value", "") for item in fields if isinstance(item, dict) and item.get("value")
        )
        result.append(
            {
                "id": row.id,
                "tool_code": row.tool_code,
                "tool_name": names.get(row.tool_code, row.tool_code),
                "title": row.title,
                "summary": summary[:180],
            }
        )
    return result
