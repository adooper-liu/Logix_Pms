"""原模型/方法记录的作业聚合与用途限定核验。"""

from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.timeutil import utcnow
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.project import Project
from app.models.tool import Tool
from app.models.tool_sheet import ToolSheet
from app.models.user import User
from app.services import audit, handoff, org_access

KIND_LABELS = {"MODELING": "现状建模", "ANALYSIS": "分析交付", "DESIGN": "方案设计"}
SOURCE_LABELS = {
    "OBSERVED": "现场/实测记录",
    "INTERVIEW": "访谈陈述",
    "ESTIMATE": "模型估算",
    "EXERCISE": "演练假设",
    "UNKNOWN": "来源待核",
}
DECISION_LABELS = {
    "ACCEPT": "本用途已接收",
    "RETURN": "退回补证",
    "OBSERVE": "继续观察",
    "STOP": "本次停止",
}
TOOLS = {"MODELING": "BPMN", "ANALYSIS": "FIVE-WHY", "DESIGN": "TOBE"}
LIMITATIONS = [
    "模型估算、路径枚举不是资源排队仿真；方法表不代表算法已实现。",
    "此处接收仅针对原产物用途，不发布模型，不证明上线或改善达标。",
    "正式轮次、指标口径/前后样本及项目根因门仍由原模块和后续M5承接。",
]


def require_process(db, pid, *, reading=False):
    process = db.get(ProcessArch, pid)
    if process is None:
        raise HTTPException(404, "流程不存在")
    if process.level < 3 or (process.is_draft and not reading):
        raise HTTPException(400, "请选择已纳入目录的L3/L4流程")
    return process


def valid_upstream(db, row, seen=None, *, check_basis=True):
    context = row.work_context or {}
    upstream = context.get("upstream_sheet_id")
    if not upstream:
        return context.get("kind") == "MODELING"
    seen = set(seen or ())
    if row.id in seen:
        return False
    seen.add(row.id)
    parent = db.get(ToolSheet, upstream)
    return bool(
        parent
        and parent.process_id == row.process_id
        and (parent.review or {}).get("decision") == "ACCEPT"
        and (not check_basis or (row.review or {}).get("upstream_revision") == parent.revision)
        and valid_upstream(db, parent, seen)
    )


def review_label(db, row):
    if not row.work_context:
        return "未记录作业核验"
    if (row.review or {}).get("decision") == "ACCEPT" and not valid_upstream(db, row):
        return "上游需复核"
    return DECISION_LABELS.get((row.review or {}).get("decision"), "待指定接收者核验")


def visible_chain(db, user, row, seen=None):
    # 所有原详情/流程卡与作业聚合共用同一递归可见性入口。
    handoff.require_sheet(db, user, row.tool_code, row.id)


def out(db, row):
    from app.services.tool_sheet import _out

    tool = db.scalar(select(Tool).where(Tool.code == row.tool_code))
    return _out(db, row, tool.name if tool else row.tool_code, [])


def board(db, user, pid):
    process = require_process(db, pid, reading=True)
    records = []
    for row in db.scalars(
        select(ToolSheet)
        .where(ToolSheet.process_id == pid, ToolSheet.work_context.is_not(None))
        .order_by(ToolSheet.id.desc())
    ).all():
        if not row.work_context:
            continue
        try:
            visible_chain(db, user, row)
            records.append(out(db, row))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    models = db.scalars(
        select(ProcessModelVersion)
        .where(ProcessModelVersion.process_id == pid)
        .order_by(ProcessModelVersion.version.desc())
    ).all()
    users = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role != "VIEWER")
        .order_by(User.display_name)
    ).all()
    return {
        "process_id": pid,
        "can_create": not process.is_draft,
        "records": records,
        "models": [
            {
                "id": r.id,
                "version": r.version,
                "status": r.status,
                "fixed": bool(r.frozen_at or r.status in ("PUBLISHED", "SUPERSEDED")),
            }
            for r in models
        ],
        "kind_labels": KIND_LABELS,
        "source_labels": SOURCE_LABELS,
        "decision_labels": DECISION_LABELS,
        "reviewers": [{"id": u.id, "name": u.display_name} for u in users],
        "limitations": LIMITATIONS,
    }


def create(db, user, pid, payload):
    require_process(db, pid)
    version = db.get(ProcessModelVersion, payload.model_version_id)
    if version is None or version.process_id != pid:
        raise HTTPException(404, "原模型版本不存在")
    if not version.frozen_at and version.status not in ("PUBLISHED", "SUPERSEDED"):
        raise HTTPException(400, "请先固定原模型版本，不能引用可变草稿")
    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
        if project.process_id != pid:
            raise HTTPException(400, "项目与作业流程不一致")
    reviewer = db.get(User, payload.reviewer_user_id)
    if reviewer is None or not reviewer.is_active or reviewer.role == "VIEWER":
        raise HTTPException(400, "请选择可办理的核验账号")
    if reviewer.id == user.id:
        raise HTTPException(400, "原产物作者不能自验，请指定另一位接收者")
    if payload.upstream_sheet_id:
        parent = db.get(ToolSheet, payload.upstream_sheet_id)
        if parent is None or parent.process_id != pid or not parent.work_context:
            raise HTTPException(404, "上游作业不存在于本流程")
        visible_chain(db, user, parent)
        expected = {"ANALYSIS": "MODELING", "DESIGN": "ANALYSIS"}.get(payload.kind)
        if parent.work_context.get("kind") != expected:
            raise HTTPException(400, "请选择对应前序原作业产物")
    if not payload.customer_result.strip() or not payload.problem.strip():
        raise HTTPException(400, "请写明客户结果与本次问题")
    from app.services.tool_sheet import form_for

    tool = db.scalar(select(Tool).where(Tool.code == TOOLS[payload.kind]))
    if tool is None or not tool.is_active or tool.status not in ("PUBLISHED", "VERIFIED"):
        raise HTTPException(404, "原方法不可用于新作业")
    spec = form_for(db, tool)
    data = payload.model_dump(mode="json", exclude={"project_id"})
    fields = [
        {"key": key, "label": label, "value": getattr(payload, key)}
        for key, label in [
            ("customer_result", "客户结果"),
            ("problem", "本次问题"),
            ("findings", "发现/结论"),
            ("evidence", "原证据"),
            ("limitations", "限制/未知"),
            ("next_action", "下一步"),
            ("alternatives", "备选"),
            ("choice_reason", "选择依据"),
            ("controls", "控制"),
            ("validation", "验证"),
            ("rollback", "回退"),
        ]
        if getattr(payload, key)
    ]
    row = ToolSheet(
        tool_code=tool.code,
        process_id=pid,
        project_id=payload.project_id,
        template_version_id=spec.template_version_id,
        title=KIND_LABELS[payload.kind] + " · " + payload.problem[:100],
        fields=fields,
        work_context=data,
        created_by=user.display_name,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        user,
        "CREATE",
        "tool_sheet",
        row.id,
        f"记录{KIND_LABELS[payload.kind]}，原模型#{version.id}",
    )
    db.commit()
    return out(db, row)


def review(db, user, pid, sheet_id, payload):
    row = db.get(ToolSheet, sheet_id)
    if row is None or row.process_id != pid or not row.work_context:
        raise HTTPException(404, "原作业记录不存在")
    visible_chain(db, user, row)
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "作业核验已更新，请刷新")
    context = row.work_context
    if context.get("reviewer_user_id") != user.id or row.created_by_id == user.id:
        raise HTTPException(403, "仅指定的非作者接收者可本人核验，不允许代签")
    if not payload.evidence.strip():
        raise HTTPException(400, "请填写本次核验依据")
    if payload.decision == "ACCEPT":
        if context.get("source_kind") in ("UNKNOWN", "EXERCISE", "ESTIMATE"):
            raise HTTPException(400, "未知、演练或模型估算不能接收为真实业务依据")
        if not all(
            (context.get(key) or "").strip()
            for key in ("findings", "evidence", "limitations", "next_action")
        ):
            raise HTTPException(400, "发现、证据、限制和下一步尚未完整")
        if not valid_upstream(db, row, check_basis=False):
            raise HTTPException(400, "前序原产物未接收或需要复核")
        if context.get("kind") == "DESIGN" and not all(
            (context.get(key) or "").strip()
            for key in ("alternatives", "choice_reason", "controls", "validation", "rollback")
        ):
            raise HTTPException(400, "请补齐备选、选择依据、控制、验证与回退")
    upstream = (
        db.get(ToolSheet, context.get("upstream_sheet_id"))
        if context.get("upstream_sheet_id")
        else None
    )
    decision = {
        "upstream_revision": upstream.revision if upstream else None,
        "decision": payload.decision,
        "evidence": payload.evidence.strip(),
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }
    result = db.execute(
        update(ToolSheet)
        .where(ToolSheet.id == row.id, ToolSheet.revision == payload.expected_revision)
        .values(review=decision, revision=row.revision + 1, updated_at=utcnow())
    )
    if result.rowcount != 1:
        raise HTTPException(409, "作业核验已更新，请刷新")
    audit.record(
        db,
        user,
        "UPDATE",
        "tool_sheet",
        row.id,
        f"作业本人核验{payload.decision}：{payload.evidence.strip()}",
    )
    db.commit()
    db.expire(row)
    return out(db, row)
