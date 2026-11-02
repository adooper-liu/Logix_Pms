"""十层单页服务：一条流程的落地核对单。

退出门按「本流程会不会跑」计数（process_evidence），与开始使用的
「公司会不会做」全公司能力计数拆开。待办/异常是这条路径上的人工补充。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.adoption import (
    ProcessCase,
    ProcessEventLog,
    ProcessTechnologyUse,
    ProcessTrainingRecord,
    RpaBot,
    RpaRun,
)
from app.models.authorization import AuthorizationException, AuthorizationRule
from app.models.enums import (
    PilotIssueStatus,
    PilotLayerStatus,
    PilotPathStatus,
    PilotPriority,
    PilotSeverity,
    PilotTaskStatus,
)
from app.models.integration import IntegrationEndpoint
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
from app.services import audit as audit_service
from app.services import authorization as authorization_service
from app.services import deliverable as deliverable_service
from app.services import process_document as document_service
from app.services import process_evidence
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
        "goal": "同一张目标卡上要有责任人、目标值和现状基线，并且挂到这一条流程。",
        "inputs": ["年度目标", "责任人", "目标值", "现状基线"],
        "process": ["把目标挂到本流程", "在同一张卡上写责任人、目标值和基线"],
        "outputs": ["挂到本流程的完整目标卡"],
        "exit_criteria": "本流程至少有一条在用目标，同一张卡上同时有责任人、目标值和基线。",
        "evidence": ["objective_complete"],
        "actions": [{"label": "去定目标", "view": "strategy"}],
    },
    {
        "layer_no": 2,
        "title": "这条流程的起止",
        "goal": "写清这一条流程从哪里开始、到哪里结束、做什么、不做什么、什么情况停，"
        "并指定发起人。流程地图的上下级和 PCF 对应，在开始使用里数。",
        "inputs": ["这条 L3 的负责人", "发起人"],
        "process": ["写起点和终点", "写范围内和范围外", "写停止条件"],
        "outputs": ["挂在这条 L3 上的范围说明"],
        "exit_criteria": "这条 L3 有负责人；范围说明写全起止、范围内、范围外和停止条件；发起人已指定。",
        "evidence": ["process_charters"],
        "actions": [
            {"label": "写这条流程的起止", "view": "pilot", "action": "pilot.openCharter"},
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
        "goal": "表单能填写；路径来自执行实例或记入的日志；机器人有一次挂了端点的运行；"
        "并写下案例，以及区块链、人工智能或物联网用在哪一段。",
        "inputs": ["表单", "执行实例或日志行", "机器人运行", "案例", "技术用途"],
        "process": [
            "建最小字段集",
            "从执行实例或记入的日志挖路径",
            "登记机器人，并记下一次挂了集成端点的运行",
            "登记案例和技术用途",
        ],
        "outputs": ["表单", "路径变体", "机器人运行", "案例", "技术用途"],
        "exit_criteria": "表单、路径变体、机器人登记、挂了端点的运行、案例、技术用途都大于 0。"
        "日志行是记进本系统的，不会自动从 ERP 或 OA 拉下来。运行记录不代替机器人去执行。",
        "evidence": [
            "forms",
            "bindings",
            "mining_variants",
            "rpa_bots",
            "rpa_runs",
            "process_cases",
            "technology_uses",
        ],
        "actions": [
            {"label": "流程设计器", "view": "designer"},
            {"label": "方法工具箱", "view": "toolbox"},
            {"label": "看这条流程的挖掘", "view": "monitor", "action": "pilot.openMining"},
            {"label": "登记机器人", "view": "pilot", "action": "pilot.openRpa"},
            {"label": "记一条外部日志", "view": "pilot", "action": "pilot.openEvent"},
            {"label": "登记一次运行", "view": "pilot", "action": "pilot.openRun"},
            {"label": "登记案例", "view": "pilot", "action": "pilot.openCase"},
            {"label": "登记技术用途", "view": "pilot", "action": "pilot.openTech"},
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
        "goal": "同一张指标卡上要有公式、红黄绿阈值、责任人，并且至少有一个数据点。",
        "inputs": ["公式", "红黄绿阈值", "责任人", "数据点"],
        "process": ["在同一张 KPI 上写公式和三条阈值", "指定责任人", "录入至少一个数据点"],
        "outputs": ["可判断红黄绿的 KPI"],
        "exit_criteria": "本流程至少有一张 KPI 同时具备公式、目标值、红黄绿阈值、责任人和数据点。",
        "evidence": ["kpi_monitored"],
        "actions": [
            {"label": "运营监控", "view": "monitor", "view_params": {"tab": "kpi"}},
        ],
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
        "goal": "模型已发布，制度已生效，变更已应用。培训到场或已应用变更上的培训说明，有一处即可。",
        "inputs": ["已发布模型", "生效制度", "变更单", "培训到场或培训说明"],
        "process": [
            "发布模型",
            "让制度生效",
            "把变更标成已应用，并写上培训说明",
            "或记下谁在哪一天听完了哪一课",
        ],
        "outputs": ["已发布模型", "生效制度", "已应用变更", "培训到场或培训说明"],
        "exit_criteria": "已发布模型、生效制度、已应用变更都大于 0。"
        "培训到场，或已应用变更上写明的培训说明，至少有一处。回退方案写在变更单上。",
        "evidence": ["applied_changes", "l3_published", "effective_documents", "training_records"],
        "actions": [
            {"label": "流程设计器", "view": "designer"},
            {"label": "交付物", "view": "deliverables"},
            {"label": "知识库", "view": "knowledge"},
            {"label": "登记培训到场", "view": "pilot", "action": "pilot.openTraining"},
        ],
    },
]

LAYER_BY_NO = {layer["layer_no"]: layer for layer in LAYER_DEFINITIONS}

# 这些页面用流程 id 打开这一条；地图用流程编码定位节点。
_PROCESS_ID_VIEWS = frozenset({"designer", "monitor", "execution", "deliverables", "process_card"})


def _scope_view(
    view: str,
    params: Optional[dict],
    path: PilotPath,
    process: Optional[ProcessArch],
) -> Dict[str, str]:
    """从这条路径跳出去时，带上当前流程，避免落到上一次打开的另一条。"""
    scoped = {key: str(value) for key, value in (params or {}).items() if value is not None}
    if path.process_id and view in _PROCESS_ID_VIEWS:
        scoped["process"] = str(path.process_id)
    elif process is not None and view == "map":
        scoped["process"] = process.code
    return scoped


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
    if path.process_id:
        process_counts = process_evidence.collect(db, path.process_id)
    else:
        process_counts = {key: 0 for key in process_evidence.PROCESS_EVIDENCE_LABELS}
    _layer4_counts, layer4_resources = _layer4_resources(db, path)
    # 第 4 层制度/授权以本流程范围清单为准（与 collect 同源口径，展示用资源明细）
    layer_rows = _ensure_layers(db, path)
    tasks = db.scalars(select(PilotTask).where(PilotTask.path_id == path.id)).all()
    issues = db.scalars(select(PilotIssue).where(PilotIssue.path_id == path.id)).all()
    tasks_by_layer: Dict[int, List[PilotTask]] = {}
    issues_by_layer: Dict[int, List[PilotIssue]] = {}
    for task in tasks:
        tasks_by_layer.setdefault(task.layer_no, []).append(task)
    for issue in issues:
        issues_by_layer.setdefault(issue.layer_no, []).append(issue)

    process = db.get(ProcessArch, path.process_id) if path.process_id else None
    layers: List[PilotLayerOut] = []
    done_count = 0
    for definition in LAYER_DEFINITIONS:
        layer_no = definition["layer_no"]
        layer_evidence = process_counts
        items = []
        for key in definition["evidence"]:
            view, params = startup_service.EVIDENCE_DESTINATIONS[key]
            items.append(
                PilotLayerEvidenceOut(
                    key=key,
                    label=process_evidence.PROCESS_EVIDENCE_LABELS.get(
                        key, startup_service.EVIDENCE_LABELS.get(key, key)
                    ),
                    value=layer_evidence.get(key, 0),
                    required=key != "open_authorization_exceptions",
                    met=startup_service.evidence_met(key, layer_evidence.get(key, 0)),
                    view=view,
                    view_params=_scope_view(view, params, path, process),
                )
            )
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
                actions=[
                    PilotActionOut(
                        **{
                            **action,
                            "view_params": _scope_view(
                                action.get("view") or "",
                                action.get("view_params"),
                                path,
                                process,
                            ),
                        }
                    )
                    for action in definition["actions"]
                ],
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

    # 当前位置 = 第一个证据未齐的层。不再单独保存一个可以超前或落后的层号。
    derived = next(
        (layer.layer_no for layer in layers if not layer.gate_open), len(LAYER_DEFINITIONS)
    )
    if path.status != PilotPathStatus.COMPLETED.value:
        path.current_layer = derived
    layers = [
        layer.model_copy(update={"current": layer.layer_no == path.current_layer})
        for layer in layers
    ]

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
    name: Optional[str],
    process_id: int,
    owner_user_id: Optional[int],
    owner: Optional[str],
) -> PilotPathOut:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise PilotError("关联流程不存在")
    if process.level not in (3, 4):
        raise PilotError("十层路径只能挂在 L3 或 L4 流程上")
    existing = db.scalar(select(PilotPath.id).where(PilotPath.process_id == process_id).limit(1))
    if existing is not None:
        raise PilotError("该流程已有十层路径，请直接打开")
    # 路径名就是流程名；库里仍留 name 字段，方便列表展示，不再让人另起名字
    path_name = (name or "").strip() or (process.name or "").strip()
    if not path_name:
        raise PilotError("流程名称不能为空")
    path = PilotPath(
        name=path_name,
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
    """按证据重算当前层。证据未齐时拒绝；全部齐备才标记完成。"""
    detail = path_detail(db, path)
    current = next((layer for layer in detail.layers if layer.current), None)
    if current is None or not current.gate_open:
        missing = [item.label for item in current.evidence_items if not item.met] if current else []
        if current is not None and current.status == PilotLayerStatus.BLOCKED.value:
            missing.append("未关闭的阻断异常")
        raise PilotGateError(missing or ["当前层证据未齐"])
    path.status = PilotPathStatus.COMPLETED.value
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


def _require_activity_process(db: Session, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None or process.level not in (3, 4):
        raise PilotError("这条记录只能挂在 L3 或 L4 上")
    return process


def save_rpa(db: Session, user: User, payload) -> int:
    """新增一条机器人登记。活动名、机器人名、替掉的人工操作和责任人都要写上。"""
    process = _require_activity_process(db, payload.process_id)
    owner = db.get(User, payload.owner_user_id)
    if owner is None:
        raise PilotError("责任人不存在")
    activity_name = (payload.activity_name or "").strip()
    bot_name = (payload.bot_name or "").strip()
    manual_step = (payload.manual_step or "").strip()
    if not activity_name or not bot_name or not manual_step:
        raise PilotError("活动、机器人名称和替掉的人工操作都要写上")
    row = RpaBot(
        process_id=process.id,
        activity_name=activity_name,
        bot_name=bot_name,
        manual_step=manual_step,
        owner_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "rpa_bot", row.id, f"登记机器人 {bot_name}")
    db.commit()
    return row.id


def save_training(db: Session, user: User, payload) -> int:
    """新增一条培训到场。课题、听课人和完成日期都要有。"""
    process = _require_activity_process(db, payload.process_id)
    trainee = db.get(User, payload.trainee_user_id)
    if trainee is None:
        raise PilotError("听课人不存在")
    topic = (payload.topic or "").strip()
    if not topic or payload.completed_on is None:
        raise PilotError("课题和完成日期都要写上")
    row = ProcessTrainingRecord(
        process_id=process.id,
        trainee_user_id=trainee.id,
        topic=topic,
        completed_on=payload.completed_on,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "process_training_record", row.id, f"登记培训 {topic}")
    db.commit()
    return row.id


TECH_KINDS = {
    "BLOCKCHAIN": "区块链",
    "AI": "人工智能",
    "IOT": "物联网",
}
RUN_OUTCOMES = {
    "SUCCEEDED": "成功",
    "FAILED": "失败",
}


def technology_kinds() -> List[dict]:
    return [{"code": code, "label": label} for code, label in TECH_KINDS.items()]


def rpa_run_options(db: Session, process_id: int) -> dict:
    process = _require_activity_process(db, process_id)
    bots = db.scalars(select(RpaBot).where(RpaBot.process_id == process.id)).all()
    endpoints = db.scalars(select(IntegrationEndpoint).order_by(IntegrationEndpoint.id)).all()
    return {
        "bots": [
            {"id": row.id, "bot_name": row.bot_name, "activity_name": row.activity_name}
            for row in bots
        ],
        "endpoints": [
            {
                "id": row.id,
                "name": row.name,
                "kind": row.kind,
                "status_label": "启用" if row.is_active else "未启用",
            }
            for row in endpoints
        ],
        "outcomes": [{"code": code, "label": label} for code, label in RUN_OUTCOMES.items()],
    }


def save_event_log(db: Session, user: User, payload) -> int:
    """记入一条外部日志。来源、案例号、活动和发生时间都要写上。"""
    process = _require_activity_process(db, payload.process_id)
    source_name = (payload.source_name or "").strip()
    case_key = (payload.case_key or "").strip()
    activity_name = (payload.activity_name or "").strip()
    if not source_name or not case_key or not activity_name or payload.occurred_at is None:
        raise PilotError("来源、案例号、活动和发生时间都要写上")
    row = ProcessEventLog(
        process_id=process.id,
        source_name=source_name,
        case_key=case_key,
        activity_name=activity_name,
        occurred_at=payload.occurred_at,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db, user, "CREATE", "process_event_log", row.id, f"记入日志 {source_name} {case_key}"
    )
    db.commit()
    return row.id


def save_rpa_run(db: Session, user: User, payload) -> int:
    """记下一次运行，并挂到一个已启用的集成端点。这里不代替机器人去执行。"""
    bot = db.get(RpaBot, payload.bot_id)
    if bot is None:
        raise PilotError("先登记机器人，再记运行")
    _require_activity_process(db, bot.process_id)
    if payload.outcome not in RUN_OUTCOMES:
        raise PilotError("运行结果只能是成功或失败")
    endpoint = db.get(IntegrationEndpoint, payload.endpoint_id)
    if endpoint is None:
        raise PilotError("要挂一个已经登记的集成端点")
    if payload.ran_at is None:
        raise PilotError("写下这次运行的时间")
    row = RpaRun(
        bot_id=bot.id,
        ran_at=payload.ran_at,
        outcome=payload.outcome,
        endpoint_id=endpoint.id,
        note=(payload.note or "").strip() or None,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "rpa_run", row.id, f"记下运行 {bot.bot_name}")
    db.commit()
    return row.id


def save_case(db: Session, user: User, payload) -> int:
    """登记一条案例。标题、情形和责任人都要写上。"""
    process = _require_activity_process(db, payload.process_id)
    owner = db.get(User, payload.owner_user_id)
    if owner is None:
        raise PilotError("责任人不存在")
    title = (payload.title or "").strip()
    situation = (payload.situation or "").strip()
    if not title or not situation:
        raise PilotError("案例标题和情形都要写上")
    row = ProcessCase(
        process_id=process.id,
        title=title,
        situation=situation,
        owner_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "process_case", row.id, f"登记案例 {title}")
    db.commit()
    return row.id


def save_technology_use(db: Session, user: User, payload) -> int:
    """登记区块链、人工智能或物联网在这条流程上的用途。"""
    process = _require_activity_process(db, payload.process_id)
    if payload.kind not in TECH_KINDS:
        raise PilotError("技术用途只能是区块链、人工智能或物联网")
    owner = db.get(User, payload.owner_user_id)
    if owner is None:
        raise PilotError("责任人不存在")
    name = (payload.name or "").strip()
    usage_note = (payload.usage_note or "").strip()
    if not name or not usage_note:
        raise PilotError("名称和用在哪一段都要写上")
    row = ProcessTechnologyUse(
        process_id=process.id,
        kind=payload.kind,
        name=name,
        usage_note=usage_note,
        owner_user_id=owner.id,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_technology_use",
        row.id,
        f"登记{TECH_KINDS[payload.kind]} {name}",
    )
    db.commit()
    return row.id
