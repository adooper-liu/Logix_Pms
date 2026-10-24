"""十层单页服务：路径、层状态、待办与异常改善卡。

层的退出条件直接复用启动页的证据口径，不新增第二套判定。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.authorization import AuthorizationException, AuthorizationRule
from app.models.enums import (
    PilotIssueStatus,
    PilotLayerStatus,
    PilotPathStatus,
    PilotPriority,
    PilotSeverity,
    PilotTaskStatus,
)
from app.models.pilot import PilotIssue, PilotLayer, PilotPath, PilotTask
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument
from app.models.raci import GovernanceRole
from app.models.user import User
from app.schemas.pilot import (
    PilotActionOut,
    PilotDocumentOut,
    PilotExceptionOut,
    PilotIssueOut,
    PilotLayerEvidenceOut,
    PilotLayerOut,
    PilotLayerResourcesOut,
    PilotPathOut,
    PilotPathSummaryOut,
    PilotRuleOut,
    PilotTaskOut,
)
from app.services import authorization as authorization_service
from app.services import deliverable as deliverable_service
from app.services import process_document as document_service
from app.services import startup as startup_service


class PilotError(ValueError):
    pass


class PilotGateError(PilotError):
    def __init__(self, missing: List[str]):
        self.missing = missing
        super().__init__("当前层退出门未满足：" + "、".join(missing))


PATH_STATUS_LABELS: Dict[str, str] = {
    PilotPathStatus.ACTIVE.value: "进行中",
    PilotPathStatus.COMPLETED.value: "已完成",
    PilotPathStatus.ARCHIVED.value: "已归档",
}

LAYER_STATUS_LABELS: Dict[str, str] = {
    PilotLayerStatus.NOT_STARTED.value: "还没开始",
    PilotLayerStatus.IN_PROGRESS.value: "进行中",
    PilotLayerStatus.BLOCKED.value: "被阻断",
    PilotLayerStatus.DONE.value: "可退出",
}

TASK_STATUS_LABELS: Dict[str, str] = {
    PilotTaskStatus.TODO.value: "待办",
    PilotTaskStatus.DOING.value: "进行中",
    PilotTaskStatus.DONE.value: "已完成",
}

ISSUE_STATUS_LABELS: Dict[str, str] = {
    PilotIssueStatus.OPEN.value: "待处理",
    PilotIssueStatus.INVESTIGATING.value: "分析中",
    PilotIssueStatus.VERIFYING.value: "验证中",
    PilotIssueStatus.CLOSED.value: "已关闭",
}

PRIORITY_LABELS: Dict[str, str] = {
    PilotPriority.HIGH.value: "高",
    PilotPriority.MEDIUM.value: "中",
    PilotPriority.LOW.value: "低",
}

SEVERITY_LABELS: Dict[str, str] = {
    PilotSeverity.BLOCKER.value: "阻断",
    PilotSeverity.MAJOR.value: "重要",
    PilotSeverity.MINOR.value: "一般",
}

# 十层定义：标题、目标、输入/处理/输出、退出门证据、系统入口。
LAYER_DEFINITIONS: List[Dict] = [
    {
        "layer_no": 1,
        "title": "战略与目标",
        "goal": "说清楚为什么做、为谁创造什么价值、不做什么。",
        "inputs": ["年度经营计划", "客户/质量/成本目标", "现状数据"],
        "process": ["选 1 条试点流程", "建 1 条年度目标", "把目标挂到流程"],
        "outputs": ["目标卡", "现状基线", "目标—流程—指标映射"],
        "exit_criteria": "目标可测、边界明确、有责任人；目标已挂到试点流程。",
        "evidence": [
            "objectives",
            "linked_objectives",
            "objectives_with_owner",
            "objectives_with_baseline",
        ],
        "actions": [{"label": "去定目标", "view": "strategy"}],
    },
    {
        "layer_no": 2,
        "title": "架构与端到端链路",
        "goal": "用 PCF 统一名称和边界，画出起点、终点和关键接口。",
        "inputs": ["PCF 分类", "现有流程清单", "组织和系统边界"],
        "process": ["选 1 个 L1 + 3 个 L2 + 10 个 L3", "补齐 L1–L3", "映射 PCF"],
        "outputs": ["L1–L3 架构", "PCF 映射", "端到端链路"],
        "exit_criteria": "主链路完整、关键接口有责任方。",
        "evidence": ["l1", "l2", "l3", "pcf_mapped_l3"],
        "actions": [
            {"label": "看流程地图", "view": "map"},
            {"label": "看 PCF", "view": "pcf"},
            {
                "label": "1+3+10 建架构",
                "view": "map",
                "hint": "引导式选择",
                "action": "start.guidedPcf",
            },
        ],
    },
    {
        "layer_no": 3,
        "title": "组织与职责",
        "goal": "谁发起、谁执行、谁复核、谁知情。",
        "inputs": ["组织树", "岗位", "关键决策事项"],
        "process": ["任命流程 Owner/治理角色", "为关键事项配 RACI", "检查唯一 A"],
        "outputs": ["RACI 矩阵", "岗位边界", "角色成员"],
        "exit_criteria": "每个节点至少一个负责者，无冲突。",
        "evidence": ["positions", "raci_matters", "invalid_processes"],
        "actions": [
            {"label": "组织与人员", "view": "orgs"},
            {"label": "配权责", "view": "designer"},
        ],
    },
    {
        "layer_no": 4,
        "title": "制度与授权设计",
        "goal": "依据什么规则、谁在什么条件下可做什么。",
        "inputs": ["风险/合规要求", "现有制度", "金额/风险阈值", "例外场景"],
        "process": ["上传生效 SOP", "按 A/B/C/D 建授权规则", "定义例外路径和证据"],
        "outputs": ["生效制度/SOP", "授权矩阵", "例外路径", "审批证据"],
        "exit_criteria": "授权覆盖主链路、退出条件与证据齐备。",
        "evidence": [
            "effective_documents",
            "effective_authorization_rules",
            "open_authorization_exceptions",
        ],
        "actions": [
            {"label": "上传制度", "view": "deliverables"},
            {"label": "授权矩阵", "view": "authorization"},
        ],
    },
    {
        "layer_no": 5,
        "title": "流程",
        "goal": "每一步做什么、按什么顺序、何时升级。",
        "inputs": ["SIPOC", "泳道图", "控制点"],
        "process": ["拆 L4 步骤", "标角色、时限、控制点", "校验并发布模型"],
        "outputs": ["标准流程", "控制点", "已发布模型"],
        "exit_criteria": "关键决策点有输入、输出和责任人；模型已发布。",
        "evidence": ["l3_published"],
        "actions": [
            {"label": "流程设计器", "view": "designer"},
            {"label": "方法手册", "view": "workflow"},
        ],
    },
    {
        "layer_no": 6,
        "title": "表单/工具",
        "goal": "用哪些字段、模板、工具和确认动作。",
        "inputs": ["表单字段", "系统配置", "工具模板"],
        "process": ["建最小字段集", "绑定表单/规则/工具", "验证可填写、可留存"],
        "outputs": ["表单", "规则", "工具绑定"],
        "exit_criteria": "字段可填写、可验证、可留存。",
        "evidence": ["forms", "bindings"],
        "actions": [
            {"label": "流程设计器", "view": "designer"},
            {"label": "方法工具箱", "view": "toolbox"},
        ],
    },
    {
        "layer_no": 7,
        "title": "工作量",
        "goal": "频次、批量、工时区间和容量是否匹配。",
        "inputs": ["作业分解", "现场观测/抽样", "岗位与可用工时"],
        "process": ["定方法 → 观测 → 评定 → 宽放", "验证标准工时", "登记产能"],
        "outputs": ["标准工时卡", "能力负荷表"],
        "exit_criteria": "与试点样本量、周期和可用人力匹配。",
        "evidence": ["verified_standards", "capacity_rows"],
        "actions": [{"label": "工作量", "view": "monitor", "hint": "运营监控 → 工作量"}],
    },
    {
        "layer_no": 8,
        "title": "绩效",
        "goal": "用哪些指标判断成功和异常。",
        "inputs": ["目标与基线", "数据来源", "异常台账"],
        "process": ["建 2–5 个结果/过程/健康度指标", "设红黄绿阈值", "录入数据点"],
        "outputs": ["KPI 卡", "红黄灯", "异常闭环"],
        "exit_criteria": "指标可采集、不与安全/质量冲突。",
        "evidence": ["kpi_cards", "kpi_records"],
        "actions": [{"label": "运营监控", "view": "monitor"}],
    },
    {
        "layer_no": 9,
        "title": "改善",
        "goal": "发现什么、改什么、如何验证。",
        "inputs": ["红黄指标", "异常", "根因"],
        "process": ["从红黄 KPI 转改善项目", "试办法 → 验结果", "改标准"],
        "outputs": ["改善卡", "行动", "验证证据"],
        "exit_criteria": "每条阻断异常有责任人、期限和结果。",
        "evidence": ["improvement_projects", "open_findings"],
        "actions": [
            {"label": "运营监控", "view": "monitor"},
            {"label": "改善项目", "view": "projects"},
        ],
    },
    {
        "layer_no": 10,
        "title": "新版本",
        "goal": "何时发布、谁批准、如何回退。",
        "inputs": ["模型/制度/培训/权限", "回退方案", "变更单"],
        "process": ["门禁评审", "发布 V1.0", "更新基线、沉淀知识"],
        "outputs": ["基线/草稿/发布版本", "回退预案", "知识条目"],
        "exit_criteria": "验收通过、变更可追溯、回退可执行。",
        "evidence": ["applied_changes", "l3_published", "effective_documents"],
        "actions": [
            {"label": "流程设计器", "view": "designer"},
            {"label": "交付物", "view": "deliverables"},
            {"label": "知识库", "view": "knowledge"},
        ],
    },
]

LAYER_BY_NO = {layer["layer_no"]: layer for layer in LAYER_DEFINITIONS}


def require_path(db: Session, path_id: int) -> PilotPath:
    row = db.get(PilotPath, path_id)
    if row is None:
        raise PilotError(f"试点路径 {path_id} 不存在")
    return row


def require_task(db: Session, task_id: int) -> PilotTask:
    row = db.get(PilotTask, task_id)
    if row is None:
        raise PilotError(f"待办 {task_id} 不存在")
    return row


def require_issue(db: Session, issue_id: int) -> PilotIssue:
    row = db.get(PilotIssue, issue_id)
    if row is None:
        raise PilotError(f"异常 {issue_id} 不存在")
    return row


def _task_out(row: PilotTask) -> PilotTaskOut:
    return PilotTaskOut(
        id=row.id,
        layer_no=row.layer_no,
        title=row.title,
        priority=row.priority,
        priority_label=PRIORITY_LABELS.get(row.priority, row.priority),
        owner=row.owner,
        owner_user_id=row.owner_user_id,
        due_date=row.due_date,
        acceptance=row.acceptance,
        status=row.status,
        status_label=TASK_STATUS_LABELS.get(row.status, row.status),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _issue_out(row: PilotIssue) -> PilotIssueOut:
    return PilotIssueOut(
        id=row.id,
        layer_no=row.layer_no,
        title=row.title,
        severity=row.severity,
        severity_label=SEVERITY_LABELS.get(row.severity, row.severity),
        workaround=row.workaround,
        verification=row.verification,
        owner=row.owner,
        owner_user_id=row.owner_user_id,
        due_date=row.due_date,
        status=row.status,
        status_label=ISSUE_STATUS_LABELS.get(row.status, row.status),
        created_at=row.created_at,
        closed_at=row.closed_at,
    )


def _layer_status(items: List[PilotLayerEvidenceOut], blocked: bool) -> str:
    if blocked:
        return PilotLayerStatus.BLOCKED.value
    required = [item for item in items if item.required]
    met = sum(1 for item in required if item.met)
    if required and met == len(required):
        return PilotLayerStatus.DONE.value
    if met > 0:
        return PilotLayerStatus.IN_PROGRESS.value
    return PilotLayerStatus.NOT_STARTED.value


def _ensure_layers(db: Session, path: PilotPath) -> Dict[int, PilotLayer]:
    rows = {
        row.layer_no: row
        for row in db.scalars(select(PilotLayer).where(PilotLayer.path_id == path.id)).all()
    }
    for layer_no in range(1, 11):
        if layer_no not in rows:
            row = PilotLayer(path_id=path.id, layer_no=layer_no)
            db.add(row)
            rows[layer_no] = row
    db.flush()
    return rows


def _ancestor_ids(db: Session, process_id: Optional[int]) -> List[int]:
    ids: List[int] = []
    current = db.get(ProcessArch, process_id) if process_id else None
    guard = 0
    while current is not None and guard < 16:
        ids.append(current.id)
        current = db.get(ProcessArch, current.parent_id) if current.parent_id else None
        guard += 1
    return ids


def _layer4_resources(db: Session, path: PilotPath):
    """第 4 层的制度、授权规则与例外，按试点流程及其上级范围统计。"""
    scope = _ancestor_ids(db, path.process_id)
    doc_stmt = (
        select(ProcessDocument)
        .options(selectinload(ProcessDocument.versions))
        .where(ProcessDocument.is_active.is_(True))
        .order_by(ProcessDocument.code)
    )
    if scope:
        doc_stmt = doc_stmt.where(ProcessDocument.process_id.in_(scope))
    else:
        doc_stmt = doc_stmt.where(ProcessDocument.id.is_(None))
    documents: List[PilotDocumentOut] = []
    for document in db.scalars(doc_stmt).all():
        version = document_service.effective_version_on(document)
        if version is None:
            continue
        documents.append(
            PilotDocumentOut(
                id=document.id,
                code=document.code,
                title=document.title,
                category=document.category,
                category_label=document_service.CATEGORY_LABELS.get(
                    document.category, document.category
                ),
                version_label=f"v{version.version_label}",
                status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
            )
        )

    rule_stmt = select(AuthorizationRule).order_by(AuthorizationRule.id.desc())
    if scope:
        rule_stmt = rule_stmt.where(
            or_(
                AuthorizationRule.process_id.is_(None),
                AuthorizationRule.process_id.in_(scope),
            )
        )
    else:
        rule_stmt = rule_stmt.where(AuthorizationRule.process_id.is_(None))
    rules = db.scalars(rule_stmt).all()
    effective_rules = [
        rule
        for rule in rules
        if rule.status == authorization_service.AuthorizationStatus.EFFECTIVE.value
    ]
    rule_items: List[PilotRuleOut] = []
    for rule in rules:
        role = db.get(GovernanceRole, rule.approver_role_id) if rule.approver_role_id else None
        rule_items.append(
            PilotRuleOut(
                id=rule.id,
                code=rule.code,
                title=rule.title,
                matter=rule.matter,
                category=rule.category,
                category_label=authorization_service.CATEGORY_LABELS.get(
                    rule.category, rule.category
                ),
                status=rule.status,
                status_label=authorization_service.STATUS_LABELS.get(rule.status, rule.status),
                approver=role.name if role else rule.approver_label,
                amount_limit=float(rule.amount_limit) if rule.amount_limit is not None else None,
                exception_path=rule.exception_path,
                evidence_required=rule.evidence_required,
            )
        )
    rule_codes = {rule.id: rule.code for rule in rules}

    exc_stmt = select(AuthorizationException).order_by(AuthorizationException.id.desc())
    if scope:
        exc_stmt = exc_stmt.where(
            or_(
                AuthorizationException.process_id.is_(None),
                AuthorizationException.process_id.in_(scope),
            )
        )
    else:
        exc_stmt = exc_stmt.where(AuthorizationException.process_id.is_(None))
    exceptions = db.scalars(exc_stmt).all()
    open_exceptions = [
        row
        for row in exceptions
        if row.status
        in (
            authorization_service.AuthorizationExceptionStatus.REQUESTED.value,
            authorization_service.AuthorizationExceptionStatus.APPROVED.value,
        )
    ]
    exception_items = [
        PilotExceptionOut(
            id=row.id,
            code=row.code,
            title=row.title,
            rule_code=rule_codes.get(row.rule_id),
            status=row.status,
            status_label=authorization_service.EXCEPTION_STATUS_LABELS.get(row.status, row.status),
            expires_at=row.expires_at,
        )
        for row in exceptions[:30]
    ]
    counts = {
        "effective_documents": len(documents),
        "effective_authorization_rules": len(effective_rules),
        "open_authorization_exceptions": len(open_exceptions),
    }
    resources = PilotLayerResourcesOut(
        documents=documents[:30],
        rules=rule_items[:50],
        exceptions=exception_items,
    )
    return counts, resources


def path_detail(db: Session, path: PilotPath) -> PilotPathOut:
    base_evidence = startup_service.evidence_snapshot(db)
    layer4_evidence, layer4_resources = _layer4_resources(db, path)
    layer_rows = _ensure_layers(db, path)
    tasks = db.scalars(select(PilotTask).where(PilotTask.path_id == path.id)).all()
    issues = db.scalars(select(PilotIssue).where(PilotIssue.path_id == path.id)).all()
    tasks_by_layer: Dict[int, List[PilotTask]] = {}
    issues_by_layer: Dict[int, List[PilotIssue]] = {}
    for task in tasks:
        tasks_by_layer.setdefault(task.layer_no, []).append(task)
    for issue in issues:
        issues_by_layer.setdefault(issue.layer_no, []).append(issue)

    layers: List[PilotLayerOut] = []
    done_count = 0
    for definition in LAYER_DEFINITIONS:
        layer_no = definition["layer_no"]
        layer_evidence = {**base_evidence, **layer4_evidence} if layer_no == 4 else base_evidence
        items = [
            PilotLayerEvidenceOut(
                key=key,
                label=startup_service.EVIDENCE_LABELS[key],
                value=layer_evidence.get(key, 0),
                required=key != "open_authorization_exceptions",
                met=startup_service.evidence_met(key, layer_evidence.get(key, 0)),
            )
            for key in definition["evidence"]
        ]
        layer_issues = issues_by_layer.get(layer_no, [])
        blocked = any(
            issue.severity == PilotSeverity.BLOCKER.value
            and issue.status != PilotIssueStatus.CLOSED.value
            for issue in layer_issues
        )
        status = _layer_status(items, blocked)
        gate_open = status == PilotLayerStatus.DONE.value
        if gate_open:
            done_count += 1
        row = layer_rows[layer_no]
        layers.append(
            PilotLayerOut(
                layer_no=layer_no,
                title=definition["title"],
                goal=definition["goal"],
                inputs=definition["inputs"],
                process=definition["process"],
                outputs=definition["outputs"],
                exit_criteria=definition["exit_criteria"],
                status=status,
                status_label=LAYER_STATUS_LABELS.get(status, status),
                gate_open=gate_open,
                current=layer_no == path.current_layer,
                context_summary=row.context_summary,
                notes=row.notes,
                evidence_items=items,
                actions=[PilotActionOut(**action) for action in definition["actions"]],
                resources=layer4_resources if layer_no == 4 else None,
                tasks=[
                    _task_out(task)
                    for task in sorted(tasks_by_layer.get(layer_no, []), key=lambda t: t.id)
                ],
                issues=[
                    _issue_out(issue)
                    for issue in sorted(issues_by_layer.get(layer_no, []), key=lambda i: i.id)
                ],
            )
        )

    process = db.get(ProcessArch, path.process_id) if path.process_id else None
    current = LAYER_BY_NO.get(path.current_layer)
    return PilotPathOut(
        id=path.id,
        name=path.name,
        process_id=path.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        owner_user_id=path.owner_user_id,
        owner=path.owner,
        status=path.status,
        status_label=PATH_STATUS_LABELS.get(path.status, path.status),
        current_layer=path.current_layer,
        current_layer_title=current["title"] if current else None,
        progress=round(done_count * 100 / len(LAYER_DEFINITIONS), 1),
        baseline_version=path.baseline_version,
        draft_version=path.draft_version,
        created_at=path.created_at,
        updated_at=path.updated_at,
        layers=layers,
    )


def path_summary(db: Session, path: PilotPath) -> PilotPathSummaryOut:
    detail = path_detail(db, path)
    return PilotPathSummaryOut(
        id=detail.id,
        name=detail.name,
        process_id=detail.process_id,
        process_code=detail.process_code,
        process_name=detail.process_name,
        owner=detail.owner,
        status=detail.status,
        status_label=detail.status_label,
        current_layer=detail.current_layer,
        current_layer_title=detail.current_layer_title,
        progress=detail.progress,
        updated_at=detail.updated_at,
    )


def list_paths(db: Session) -> List[PilotPathSummaryOut]:
    rows = db.scalars(select(PilotPath).order_by(PilotPath.id.desc())).all()
    return [path_summary(db, row) for row in rows]


def create_path(
    db: Session,
    name: str,
    process_id: int,
    owner_user_id: Optional[int],
    owner: Optional[str],
) -> PilotPathOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise PilotError("关联流程不存在")
    if not (name or "").strip():
        raise PilotError("试点路径名称不能为空")
    path = PilotPath(
        name=name.strip(),
        process_id=process_id,
        owner_user_id=owner_user_id,
        owner=owner,
        status=PilotPathStatus.ACTIVE.value,
        current_layer=1,
    )
    db.add(path)
    db.flush()
    _ensure_layers(db, path)
    return path_detail(db, path)


def update_path(
    db: Session,
    path: PilotPath,
    name: Optional[str],
    status: Optional[str],
    owner_user_id: Optional[int],
    owner: Optional[str],
) -> PilotPathOut:
    if name is not None:
        if not name.strip():
            raise PilotError("试点路径名称不能为空")
        path.name = name.strip()
    if status is not None:
        path.status = status
    if owner_user_id is not None:
        path.owner_user_id = owner_user_id
        user = db.get(User, owner_user_id)
        path.owner = user.display_name if user else owner
    elif owner is not None:
        path.owner = owner
    db.flush()
    return path_detail(db, path)


def delete_path(db: Session, path: PilotPath) -> None:
    db.delete(path)
    db.flush()


def advance_path(db: Session, path: PilotPath) -> PilotPathOut:
    detail = path_detail(db, path)
    current = next((layer for layer in detail.layers if layer.current), None)
    if current is None:
        raise PilotError("当前层不存在")
    if not current.gate_open:
        missing = [item.label for item in current.evidence_items if not item.met]
        if current.status == PilotLayerStatus.BLOCKED.value:
            missing.append("未关闭的阻断异常")
        raise PilotGateError(missing)
    if path.current_layer >= len(LAYER_DEFINITIONS):
        path.status = PilotPathStatus.COMPLETED.value
    else:
        path.current_layer += 1
    db.flush()
    return path_detail(db, path)


def update_layer(
    db: Session,
    path: PilotPath,
    layer_no: int,
    context_summary: Optional[str],
    notes: Optional[str],
) -> PilotPathOut:
    if layer_no not in LAYER_BY_NO:
        raise PilotError("层号必须在 1–10 之间")
    rows = _ensure_layers(db, path)
    row = rows[layer_no]
    if context_summary is not None:
        row.context_summary = context_summary.strip() or None
    if notes is not None:
        row.notes = notes.strip() or None
    db.flush()
    return path_detail(db, path)


def create_task(
    db: Session,
    path: PilotPath,
    layer_no: int,
    title: str,
    priority: str,
    owner_user_id: Optional[int],
    owner: Optional[str],
    due_date,
    acceptance: Optional[str],
) -> PilotTaskOut:
    if layer_no not in LAYER_BY_NO:
        raise PilotError("层号必须在 1–10 之间")
    task = PilotTask(
        path_id=path.id,
        layer_no=layer_no,
        title=title.strip(),
        priority=priority,
        owner_user_id=owner_user_id,
        owner=owner,
        due_date=due_date,
        acceptance=(acceptance or "").strip() or None,
        status=PilotTaskStatus.TODO.value,
    )
    db.add(task)
    db.flush()
    return _task_out(task)


def update_task(db: Session, task: PilotTask, data: dict) -> PilotTaskOut:
    if "status" in data:
        data["completed_at"] = utcnow() if data["status"] == PilotTaskStatus.DONE.value else None
    for field, value in data.items():
        setattr(task, field, value)
    db.flush()
    return _task_out(task)


def delete_task(db: Session, task: PilotTask) -> None:
    db.delete(task)
    db.flush()


def create_issue(
    db: Session,
    path: PilotPath,
    layer_no: int,
    title: str,
    severity: str,
    workaround: Optional[str],
    verification: Optional[str],
    owner_user_id: Optional[int],
    owner: Optional[str],
    due_date,
) -> PilotIssueOut:
    if layer_no not in LAYER_BY_NO:
        raise PilotError("层号必须在 1–10 之间")
    issue = PilotIssue(
        path_id=path.id,
        layer_no=layer_no,
        title=title.strip(),
        severity=severity,
        workaround=(workaround or "").strip() or None,
        verification=(verification or "").strip() or None,
        owner_user_id=owner_user_id,
        owner=owner,
        due_date=due_date,
        status=PilotIssueStatus.OPEN.value,
    )
    db.add(issue)
    db.flush()
    return _issue_out(issue)


def update_issue(db: Session, issue: PilotIssue, data: dict) -> PilotIssueOut:
    if "status" in data:
        data["closed_at"] = utcnow() if data["status"] == PilotIssueStatus.CLOSED.value else None
    for field, value in data.items():
        setattr(issue, field, value)
    db.flush()
    return _issue_out(issue)


def delete_issue(db: Session, issue: PilotIssue) -> None:
    db.delete(issue)
    db.flush()
