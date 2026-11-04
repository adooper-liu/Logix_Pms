"""原PDCA方法记录的控制复盘与五因素来源核验视图。"""

from copy import deepcopy
from datetime import date

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.timeutil import utcnow
from app.models.tool_sheet import ToolSheet
from app.models.user import User
from app.services import audit, improvement_round


class ControlIn(BaseModel):
    round_id: int | None = None
    reviewer_user_id: int = Field(ge=1)
    owner_user_id: int = Field(ge=1)
    review_due: date
    evidence: str = Field(min_length=1, max_length=3000)
    decision: str = Field(min_length=1, max_length=2000)
    next_action: str = Field(min_length=1, max_length=2000)
    guarantee_codes: list[str] = Field(default_factory=list, max_length=5)


def control_out(row):
    return {
        "id": row.id,
        "tool_code": row.tool_code,
        "process_id": row.process_id,
        "revision": row.revision,
        "work_context": row.work_context,
        "review": row.review,
        "fields": row.fields,
    }


def create(db, user, pid, payload):
    improvement_round.process(db, pid, user, True)
    if payload.round_id:
        improvement_round.require(db, user, pid, payload.round_id)
    reviewer = db.get(User, payload.reviewer_user_id)
    owner = db.get(User, payload.owner_user_id)
    if (
        reviewer is None
        or not reviewer.is_active
        or reviewer.role == "VIEWER"
        or reviewer.id == user.id
        or owner is None
        or not owner.is_active
    ):
        raise HTTPException(400, "请指定有效责任人及非编制者核验")
    if any(not v.strip() for v in (payload.evidence, payload.decision, payload.next_action)):
        raise HTTPException(400, "复盘依据/决定/下一步不可为空")
    if not set(payload.guarantee_codes) <= {x[0] for x in GUARANTEES if x[3] == "control"}:
        raise HTTPException(400, "复盘核验仅声明本次实际覆盖的原保障项")
    data = payload.model_dump(mode="json")
    data.update(kind="CONTROL_REVIEW", edited_by_id=user.id)
    row = ToolSheet(
        tool_code="PDCA",
        process_id=pid,
        title="原流程控制与周期复盘",
        fields=[
            {"key": "evidence", "label": "原依据", "value": payload.evidence},
            {"key": "decision", "label": "决定", "value": payload.decision},
            {"key": "next_action", "label": "下一责任动作", "value": payload.next_action},
        ],
        work_context=data,
        created_by_id=user.id,
        created_by=user.display_name,
    )
    db.add(row)
    db.flush()
    audit.record(db, user, "CREATE", "tool_sheet", row.id, "原PDCA控制复盘")
    db.commit()
    return control_out(row)


def require(db, user, pid, ident):
    row = db.get(ToolSheet, ident)
    if (
        row is None
        or row.process_id != pid
        or (row.work_context or {}).get("kind") != "CONTROL_REVIEW"
    ):
        raise HTTPException(404, "原控制复盘不存在")
    if row.work_context.get("round_id"):
        improvement_round.require(db, user, pid, row.work_context["round_id"])
    return row


def review(db, user, pid, ident, payload):
    row = require(db, user, pid, ident)
    context = row.work_context
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "原复盘已变化")
    if context.get("reviewer_user_id") != user.id or row.created_by_id == user.id:
        raise HTTPException(403, "仅指定非编制者本人核验")
    evidence = {
        "decision": payload.decision,
        "evidence": payload.evidence,
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().isoformat() + "+00:00",
    }
    if row.review:
        context = deepcopy(context)
        context.setdefault("review_history", []).append(deepcopy(row.review))
    changed = db.execute(
        update(ToolSheet)
        .where(ToolSheet.id == ident, ToolSheet.revision == payload.expected_revision)
        .values(review=evidence, work_context=context, revision=payload.expected_revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "原复盘已变化")
    audit.record(db, user, "UPDATE", "tool_sheet", ident, "本人控制复盘核验：" + payload.decision)
    db.commit()
    db.refresh(row)
    return control_out(row)


GUARANTEES = [
    ("SP-01", "高层", "目标范围与停止条件", "charter"),
    ("SP-02", "高层", "资源承诺", "charter"),
    ("SP-03", "高层", "仲裁升级", "authorization"),
    ("SP-04", "高层", "评审行动", "control"),
    ("OW-01", "Owner", "任命责任", "charter"),
    ("OW-02", "Owner", "交接确认", "handoff"),
    ("OW-03", "Owner", "代理交接", "authorization"),
    ("OW-04", "Owner", "端到端复盘", "control"),
    ("ST-01", "统一方法", "有效规范", "documents"),
    ("ST-02", "统一方法", "方法适用依据", "sheets"),
    ("ST-03", "统一方法", "原模型指标审核", "rounds"),
    ("ST-04", "统一方法", "模板与操作", "training"),
    ("PF-01", "绩效", "目标指标承接", "kpis"),
    ("PF-02", "绩效", "团队评价约定", "documents"),
    ("PF-03", "绩效", "样本可靠", "rounds"),
    ("PF-04", "绩效", "周期核验", "control"),
    ("CU-01", "文化采用", "沟通反馈", "sheets"),
    ("CU-02", "文化采用", "分角色操作", "training"),
    ("CU-03", "文化采用", "采用与绕行", "control"),
    ("CU-04", "文化采用", "建议复盘", "control"),
]


def evidence(db, user, pid):
    from app.models.adoption import ProcessTrainingRecord
    from app.services.adoption_review import out as training_out
    from app.services.adoption_review import require as training_require
    from app.services.handoff import require_sheet
    from app.services.process_card import build
    from app.services.tool_sheet import sheets_for_process

    card = build(db, pid)
    sheets = []
    for item in sheets_for_process(db, pid):
        try:
            require_sheet(db, user, item["tool_code"], item["id"])
            sheets.append(item)
        except HTTPException as e:
            if e.status_code != 404:
                raise
    control = []
    for row in db.scalars(select(ToolSheet).where(ToolSheet.process_id == pid)).all():
        if (row.work_context or {}).get("kind") == "CONTROL_REVIEW":
            try:
                control.append(control_out(require(db, user, pid, row.id)))
            except HTTPException as e:
                if e.status_code != 404:
                    raise
    training = []
    for row in db.scalars(
        select(ProcessTrainingRecord).where(ProcessTrainingRecord.process_id == pid)
    ).all():
        try:
            training.append(training_out(training_require(db, user, row.id)))
        except HTTPException as e:
            if e.status_code != 404:
                raise
    from app.models.authorization import AuthorizationRule
    from app.services import charter, handoff

    charter_refs = []
    if card.process.level == 3:
        try:
            context = charter.context(db, pid, user)
            if context.charter:
                charter_refs = [
                    {
                        "id": pid,
                        "revision": context.revision,
                        "reference_label": context.reference_label,
                    }
                ]
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    handoffs = handoff.for_process(db, user, pid)
    authorization = [
        {"id": entry.id}
        for entry in db.scalars(
            select(AuthorizationRule).where(AuthorizationRule.process_id == pid)
        ).all()
    ]
    from app.models.process_document import ProcessDocument
    from app.services import org_access

    visible_documents = []
    for d in card.documents:
        original = db.get(ProcessDocument, d.id)
        if original:
            try:
                org_access.ensure_visible(db, user, original.org_unit_id)
                visible_documents.append(d.model_dump(mode="json"))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
    refs = {
        "control": control,
        "training": training,
        "sheets": sheets,
        "rounds": improvement_round.list_rounds(db, user, pid),
        "documents": visible_documents,
        "kpis": [k.model_dump(mode="json") for k in card.kpis],
        "charter": charter_refs,
        "handoff": handoffs,
        "authorization": authorization,
    }
    items = []
    for code, factor, label, key in GUARANTEES:
        sources = refs[key]
        state = "PENDING" if sources else "MISSING"
        owner_id = None
        due = None
        reviewer_id = None
        decision_ref = None
        if key == "control" and sources:
            latest = max(sources, key=lambda r: r["id"])
            owner_id = latest["work_context"].get("owner_user_id")
            due = latest["work_context"].get("review_due")
            reviewer_id = latest["work_context"].get("reviewer_user_id")
            decision_ref = latest["id"] if latest.get("review") else None
            if due and due < date.today().isoformat():
                state = "STALE"
            elif (latest.get("review") or {}).get("decision") == "ACCEPT" and code in latest[
                "work_context"
            ].get("guarantee_codes", []):
                state = "CONFIRMED"
        if key == "training" and sources:
            owner_id = sources[-1]["trainee_user_id"]
            due = (sources[-1].get("operation") or {}).get("review_due")
            reviewer_id = (sources[-1].get("operation") or {}).get("reviewer_user_id")
            if due and due < date.today().isoformat():
                state = "STALE"
            elif all(r["operation_verified"] for r in sources):
                state = "CONFIRMED"
        links = {
            "control": ("process_card", {"process": pid, "module": "governance"}),
            "training": ("process_card", {"process": pid, "module": "governance"}),
            "documents": ("deliverables", {"process": pid, "tab": "document"}),
            "rounds": ("process_card", {"process": pid, "module": "rounds"}),
            "sheets": ("toolbox", {"process": pid}),
            "kpis": ("monitor", {"process": pid, "tab": "kpi"}),
            "charter": ("process_card", {"process": pid, "module": "context"}),
            "handoff": ("process_card", {"process": pid, "module": "context"}),
            "authorization": ("authorization", {"process": pid}),
        }
        items.append(
            {
                "code": code,
                "factor": factor,
                "label": label,
                "state": state,
                "state_label": {
                    "PENDING": "原来源待专项核验",
                    "MISSING": "缺原核验来源",
                    "CONFIRMED": "本期原记录用途已核（不代替组织效果）",
                    "STALE": "到期待复核",
                }[state],
                "sources": [
                    {"id": r.get("id") if isinstance(r, dict) else r.id, "type": key}
                    for r in sources
                ],
                "next_action": "回原" + key + "核对责任、时点与本人证据",
                "responsibility": "原对象责任人；有权方核验",
                "review_due": due,
                "owner_user_id": owner_id,
                "reviewer_user_id": reviewer_id,
                "decision_ref": decision_ref,
                "view": links[key][0],
                "view_params": links[key][1],
            }
        )
    return {
        "process_id": pid,
        "items": items,
        "control_reviews": control,
        "training": training,
        "limitations": [
            "20项为原事实核验视图，不自动生成任务。",
            "记录存在不证明资源到位、文化改变或组织业务效果；无可信分母不计算采用率。",
        ],
    }
