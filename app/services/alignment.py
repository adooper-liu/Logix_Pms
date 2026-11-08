"""客户/市场要求，以及「目标 → 四路使能」的承接就绪度。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.authorization import AuthorizationRule
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.raci import RaciAssignment
from app.models.requirement import MarketRequirement, RequirementObjectiveLink
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.models.workload import CapacityCalendar, WorkMeasurementStandard
from app.schemas.requirement import (
    SOURCE_TYPE_LABELS,
    AlignmentEnablerOut,
    AlignmentKpiOut,
    AlignmentObjectiveOut,
    AlignmentOut,
    AlignmentProcessOut,
    RequirementObjectiveOut,
    RequirementOut,
)

ENABLER_LABELS = {
    "RESOURCE": "配资源",
    "TEAM": "搭班子",
    "PROCESS": "建流程",
    "SYSTEM": "制度与绩效",
}

METRIC_LABELS = {
    "projects": "项目",
    "budget": "预算",
    "sponsors": "Sponsor",
    "work_standards": "标准工时卡",
    "capacity_calendars": "产能日历",
    "objective_owner": "目标 Owner",
    "process_owners": "有 Owner 流程",
    "processes": "承接流程",
    "raci_a": "RACI-A",
    "published_models": "已发布模型",
    "activities": "L4 活动",
    "kpis": "承接 KPI",
    "kpi_ready": "KPI 口径与目标",
    "documents": "生效制度",
    "authorization_rules": "授权规则",
}


def _next_code(db: Session) -> str:
    year = date.today().year
    prefix = f"REQ-{year}-"
    rows = db.scalars(
        select(MarketRequirement.code).where(MarketRequirement.code.like(prefix + "%"))
    ).all()
    numbers = []
    for code in rows:
        try:
            numbers.append(int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{(max(numbers) + 1) if numbers else 1:03d}"


def _objective_rows(db: Session, objective_ids: List[int]) -> List[StrategyObjective]:
    if not objective_ids:
        return []
    return list(
        db.scalars(
            select(StrategyObjective)
            .where(StrategyObjective.id.in_(objective_ids))
            .order_by(StrategyObjective.id)
        ).all()
    )


def _link_objectives(db: Session, requirement: MarketRequirement, objective_ids: List[int]) -> None:
    unique = sorted(set(objective_ids))
    objectives = {row.id: row for row in _objective_rows(db, unique)}
    missing = sorted(set(unique) - set(objectives))
    if missing:
        raise HTTPException(400, f"目标不存在：{missing}")
    db.execute(
        RequirementObjectiveLink.__table__.delete().where(
            RequirementObjectiveLink.requirement_id == requirement.id
        )
    )
    for ident in unique:
        db.add(RequirementObjectiveLink(requirement_id=requirement.id, objective_id=ident))


def requirement_out(db: Session, row: MarketRequirement) -> RequirementOut:
    links = db.scalars(
        select(RequirementObjectiveLink)
        .where(RequirementObjectiveLink.requirement_id == row.id)
        .order_by(RequirementObjectiveLink.objective_id)
    ).all()
    objectives = {obj.id: obj for obj in _objective_rows(db, [link.objective_id for link in links])}
    return RequirementOut(
        id=row.id,
        code=row.code,
        source_type=row.source_type,
        source_label=SOURCE_TYPE_LABELS.get(row.source_type, row.source_type),
        title=row.title,
        requirement=row.requirement,
        evidence_url=row.evidence_url,
        status=row.status,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        objectives=[
            RequirementObjectiveOut(
                id=link.objective_id,
                code=objectives[link.objective_id].code,
                name=objectives[link.objective_id].name,
            )
            for link in links
            if link.objective_id in objectives
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_requirements(
    db: Session, *, year: Optional[int] = None, status: Optional[str] = None
) -> List[RequirementOut]:
    stmt = select(MarketRequirement).order_by(MarketRequirement.created_at.desc())
    if status:
        stmt = stmt.where(MarketRequirement.status == status)
    if year is not None:
        stmt = stmt.where(
            MarketRequirement.id.in_(
                select(RequirementObjectiveLink.requirement_id)
                .join(
                    StrategyObjective,
                    StrategyObjective.id == RequirementObjectiveLink.objective_id,
                )
                .where(StrategyObjective.year == year)
            )
        )
    return [requirement_out(db, row) for row in db.scalars(stmt).all()]


def create_requirement(db: Session, user: User, payload) -> RequirementOut:
    code = (payload.code or "").strip() or _next_code(db)
    if db.scalar(select(MarketRequirement).where(MarketRequirement.code == code)):
        raise HTTPException(409, f"要求编码 {code} 已存在")
    if payload.valid_from and payload.valid_to and payload.valid_from > payload.valid_to:
        raise HTTPException(400, "生效日期不能晚于失效日期")
    row = MarketRequirement(
        code=code,
        source_type=payload.source_type,
        title=payload.title.strip(),
        requirement=payload.requirement.strip(),
        evidence_url=(payload.evidence_url or "").strip() or None,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        created_by_id=user.id,
    )
    if not row.title or not row.requirement:
        raise HTTPException(400, "请填写要求标题与正文")
    db.add(row)
    db.flush()
    _link_objectives(db, row, payload.objective_ids)
    db.commit()
    db.refresh(row)
    return requirement_out(db, row)


def update_requirement(db: Session, row: MarketRequirement, payload) -> RequirementOut:
    data = payload.model_dump(exclude_unset=True)
    objective_ids = data.pop("objective_ids", None)
    if "title" in data and not (data["title"] or "").strip():
        raise HTTPException(400, "要求标题不能为空")
    if "requirement" in data and not (data["requirement"] or "").strip():
        raise HTTPException(400, "要求正文不能为空")
    valid_from = data.get("valid_from", row.valid_from)
    valid_to = data.get("valid_to", row.valid_to)
    if valid_from and valid_to and valid_from > valid_to:
        raise HTTPException(400, "生效日期不能晚于失效日期")
    for key, value in data.items():
        setattr(row, key, value)
    if objective_ids is not None:
        _link_objectives(db, row, objective_ids)
    db.commit()
    db.refresh(row)
    return requirement_out(db, row)


def delete_requirement(db: Session, row: MarketRequirement) -> None:
    db.execute(
        RequirementObjectiveLink.__table__.delete().where(
            RequirementObjectiveLink.requirement_id == row.id
        )
    )
    db.delete(row)
    db.commit()


def _open_projects(db: Session, process_ids: List[int]) -> List[Project]:
    if not process_ids:
        return []
    return list(
        db.scalars(
            select(Project).where(
                Project.process_id.in_(process_ids),
                Project.status != "CANCELLED",
            )
        ).all()
    )


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


def _enablers(
    db: Session,
    objective: StrategyObjective,
    processes: List[ProcessArch],
    projects: List[Project],
    kpis: List[AlignmentKpiOut],
) -> List[AlignmentEnablerOut]:
    process_ids = [row.id for row in processes]
    org_ids = [row.org_unit_id for row in processes if row.org_unit_id]
    activities = _count(
        db,
        select(func.count())
        .select_from(ProcessArch)
        .where(
            ProcessArch.parent_id.in_(process_ids or {-1}),
            ProcessArch.level == 4,
            ProcessArch.is_draft.is_(False),
        ),
    )
    published = sum(1 for row in processes if (row.published_model_version or 0) > 0)
    work_standards = _count(
        db,
        select(func.count())
        .select_from(WorkMeasurementStandard)
        .join(ProcessArch, ProcessArch.id == WorkMeasurementStandard.activity_id)
        .where(ProcessArch.parent_id.in_(process_ids or {-1})),
    )
    capacity = _count(
        db,
        select(func.count())
        .select_from(CapacityCalendar)
        .where(CapacityCalendar.org_unit_id.in_(org_ids or {-1})),
    )
    raci_a = _count(
        db,
        select(func.count())
        .select_from(RaciAssignment)
        .where(
            RaciAssignment.process_id.in_(process_ids or {-1}),
            RaciAssignment.raci == "A",
        ),
    )
    documents = _count(
        db,
        select(func.count())
        .select_from(ProcessDocument)
        .where(
            ProcessDocument.process_id.in_(process_ids or {-1}),
            ProcessDocument.is_active.is_(True),
        ),
    )
    auth_rules = _count(
        db,
        select(func.count())
        .select_from(AuthorizationRule)
        .where(
            or_(
                AuthorizationRule.process_id.in_(process_ids or {-1}),
                AuthorizationRule.process_id.is_(None),
            )
        ),
    )
    budget = sum(float(row.budget or 0) for row in projects)
    sponsor_count = sum(1 for row in projects if (row.sponsor or "").strip())
    objective_owner = bool(objective.owner_user_id is not None or (objective.owner or "").strip())
    process_owners = sum(
        1 for row in processes if row.owner_user_id is not None or (row.owner or "").strip()
    )
    kpi_ready = bool(kpis) and all(
        row.has_measurement and row.target_value is not None for row in kpis
    )

    result: List[AlignmentEnablerOut] = []

    resource_gaps = []
    if not projects:
        resource_gaps.append("未关联改善项目")
    elif budget <= 0:
        resource_gaps.append("项目未写预算")
    if work_standards == 0:
        resource_gaps.append("缺 L4 标准工时")
    if capacity == 0:
        resource_gaps.append("缺产能日历")
    if not projects:
        resource_view, resource_action = "projects", "先立项"
    elif budget <= 0:
        resource_view, resource_action = "projects", "去项目组合补预算"
    elif work_standards == 0 or capacity == 0:
        resource_view, resource_action = "monitor", "去度量补标准工时/产能"
    else:
        resource_view, resource_action = "projects", "查看项目资源"
    result.append(
        AlignmentEnablerOut(
            key="RESOURCE",
            label=ENABLER_LABELS["RESOURCE"],
            ready=bool(projects) and budget > 0 and (work_standards > 0 or capacity > 0),
            metrics={
                "projects": len(projects),
                "budget": round(budget, 2),
                "sponsors": sponsor_count,
                "work_standards": work_standards,
                "capacity_calendars": capacity,
            },
            gaps=resource_gaps,
            metric_labels=METRIC_LABELS,
            next_action=resource_action,
            next_view=resource_view,
            next_params=(
                {"process": process_ids[0]}
                if process_ids and resource_view == "projects"
                else ({"tab": "workload"} if resource_view == "monitor" else {})
            ),
        )
    )

    team_gaps = []
    if not objective_owner:
        team_gaps.append("目标缺 Owner")
    if not processes:
        team_gaps.append("未承接流程")
    elif process_owners < len(processes):
        team_gaps.append(f"{len(processes) - process_owners} 条流程缺 Owner")
    if raci_a == 0:
        team_gaps.append("缺 RACI 的 A")
    if sponsor_count == 0:
        team_gaps.append("项目缺 Sponsor")
    if not objective_owner or not processes or process_owners < len(processes):
        team_view, team_action = "orgs", "去组织与人员绑定 Owner"
    elif raci_a == 0:
        team_view, team_action = "authorization", "去授权补 RACI 的 A"
    elif sponsor_count == 0:
        team_view, team_action = "projects", "去项目组合补 Sponsor"
    else:
        team_view, team_action = "orgs", "查看组织与责任"
    result.append(
        AlignmentEnablerOut(
            key="TEAM",
            label=ENABLER_LABELS["TEAM"],
            ready=objective_owner
            and bool(processes)
            and process_owners == len(processes)
            and raci_a > 0
            and sponsor_count > 0,
            metrics={
                "objective_owner": objective_owner,
                "process_owners": process_owners,
                "processes": len(processes),
                "sponsors": sponsor_count,
                "raci_a": raci_a,
            },
            gaps=team_gaps,
            metric_labels=METRIC_LABELS,
            next_action=team_action,
            next_view=team_view,
            next_params=(
                {"process": process_ids[0]} if process_ids and team_view == "projects" else {}
            ),
        )
    )

    process_gaps = []
    if not processes:
        process_gaps.append("未承接 L3/L4 流程")
    if processes and published < len(processes):
        process_gaps.append(f"{len(processes) - published} 条流程未发布模型")
    if processes and activities == 0:
        process_gaps.append("没有 L4 活动")
    if not processes:
        process_view, process_action = "map", "去流程框架承接流程"
    elif published < len(processes):
        process_view, process_action = "asset", "去发布模型"
    elif activities == 0:
        process_view, process_action = "asset", "去补 L4 活动"
    else:
        process_view, process_action = "asset", "查看流程资产"
    result.append(
        AlignmentEnablerOut(
            key="PROCESS",
            label=ENABLER_LABELS["PROCESS"],
            ready=bool(processes) and published == len(processes) and activities > 0,
            metrics={
                "processes": len(processes),
                "published_models": published,
                "activities": activities,
            },
            gaps=process_gaps,
            metric_labels=METRIC_LABELS,
            next_action=process_action,
            next_view=process_view,
            next_params=(
                {"process": process_ids[0]} if process_ids and process_view == "asset" else {}
            ),
        )
    )

    system_gaps = []
    if not kpis:
        system_gaps.append("未承接 KPI")
    elif not kpi_ready:
        system_gaps.append("KPI 缺口径或目标")
    if documents == 0:
        system_gaps.append("无生效制度")
    if auth_rules == 0:
        system_gaps.append("无授权规则")
    if not kpis or not kpi_ready:
        system_view, system_action = "monitor", "去度量补 KPI 口径/目标"
    elif documents == 0:
        system_view, system_action = "deliverables", "去交付物补生效制度"
    elif auth_rules == 0:
        system_view, system_action = "authorization", "去授权补规则"
    else:
        system_view, system_action = "monitor", "查看制度与绩效"
    result.append(
        AlignmentEnablerOut(
            key="SYSTEM",
            label=ENABLER_LABELS["SYSTEM"],
            ready=bool(kpis) and kpi_ready and documents > 0 and auth_rules > 0,
            metrics={
                "kpis": len(kpis),
                "kpi_ready": kpi_ready,
                "documents": documents,
                "authorization_rules": auth_rules,
            },
            gaps=system_gaps,
            metric_labels=METRIC_LABELS,
            next_action=system_action,
            next_view=system_view,
            next_params={"tab": "kpi"} if system_view == "monitor" else {},
        )
    )
    return result


def alignment(db: Session, year: int) -> AlignmentOut:
    objectives = list(
        db.scalars(
            select(StrategyObjective)
            .where(StrategyObjective.year == year)
            .order_by(StrategyObjective.id)
        ).all()
    )
    rows: List[AlignmentObjectiveOut] = []
    enabler_ready = {key: 0 for key in ENABLER_LABELS}
    for objective in objectives:
        links = db.scalars(
            select(ObjectiveProcessLink).where(ObjectiveProcessLink.objective_id == objective.id)
        ).all()
        process_ids = sorted({link.process_id for link in links})
        processes = (
            list(
                db.scalars(
                    select(ProcessArch)
                    .where(ProcessArch.id.in_(process_ids))
                    .order_by(ProcessArch.code)
                ).all()
            )
            if process_ids
            else []
        )
        kpi_ids = sorted({link.kpi_id for link in links if link.kpi_id})
        kpis: List[AlignmentKpiOut] = []
        for kpi_id in kpi_ids:
            kpi = db.get(KpiDefinition, kpi_id)
            if kpi is None:
                continue
            has_record = db.scalar(select(KpiRecord.id).where(KpiRecord.kpi_id == kpi.id).limit(1))
            kpis.append(
                AlignmentKpiOut(
                    id=kpi.id,
                    code=kpi.code,
                    name=kpi.name,
                    unit=kpi.unit,
                    baseline_value=kpi.baseline_value,
                    target_value=kpi.target_value,
                    has_measurement=bool((kpi.measurement or {}).get("source_kind")),
                    has_latest_record=has_record is not None,
                )
            )
        req_links = db.scalars(
            select(RequirementObjectiveLink)
            .join(
                MarketRequirement,
                MarketRequirement.id == RequirementObjectiveLink.requirement_id,
            )
            .where(
                RequirementObjectiveLink.objective_id == objective.id,
                MarketRequirement.status == "ACTIVE",
            )
        ).all()
        requirements = []
        for link in req_links:
            req = db.get(MarketRequirement, link.requirement_id)
            if req:
                requirements.append(
                    RequirementObjectiveOut(id=req.id, code=req.code, name=req.title)
                )
        projects = _open_projects(db, process_ids)
        enablers = _enablers(db, objective, processes, projects, kpis)
        for item in enablers:
            if item.ready:
                enabler_ready[item.key] += 1
        gaps = []
        if not requirements:
            gaps.append("未关联客户/市场要求")
        if objective.baseline_value is None:
            gaps.append("目标缺基线")
        if objective.target_value is None:
            gaps.append("目标缺目标值")
        gaps.extend(f"{item.label}：{gap}" for item in enablers for gap in item.gaps)
        rows.append(
            AlignmentObjectiveOut(
                id=objective.id,
                code=objective.code,
                name=objective.name,
                year=objective.year,
                owner=objective.owner,
                baseline_value=objective.baseline_value,
                target_value=objective.target_value,
                unit=objective.unit,
                status=objective.status,
                requirements=requirements,
                processes=[
                    AlignmentProcessOut(id=row.id, code=row.code, name=row.name, level=row.level)
                    for row in processes
                ],
                kpis=kpis,
                enablers=enablers,
                gaps=gaps,
            )
        )
    requirements_all = list_requirements(db, year=year)
    ready_objectives = sum(
        1 for row in rows if all(item.ready for item in row.enablers) and row.requirements
    )
    return AlignmentOut(
        year=year,
        source_labels=SOURCE_TYPE_LABELS,
        enabler_labels=ENABLER_LABELS,
        requirements=requirements_all,
        objectives=rows,
        summary={
            "requirements": len(requirements_all),
            "objectives": len(rows),
            "ready_objectives": ready_objectives,
            "gap_objectives": len(rows) - ready_objectives,
            "enabler_ready": enabler_ready,
        },
    )
