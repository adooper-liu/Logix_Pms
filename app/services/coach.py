"""按实训模块读取已有记录，给出下一步。

不调用外部语言模型。没有记录时说明缺什么，不编造已经做过。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.adoption import ProcessEventLog
from app.models.monitor import ExceptionEvent, KpiDefinition, KpiRecord
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.project import Project
from app.models.raci import GovernanceRole
from app.models.startup import ProcessCharter
from app.schemas.coach import CoachHint, CoachOut

AREAS = (
    "bpm",
    "model",
    "analysis",
    "design",
    "performance",
    "change",
    "tech",
    "org",
    "enterprise",
)

BASIS = "根据库里已有记录给出下一步。没有接入外部语言模型。"


def _count(db: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for item in where:
        stmt = stmt.where(item)
    return int(db.scalar(stmt) or 0)


def _level(db: Session, level: int) -> int:
    return _count(db, ProcessArch, ProcessArch.level == level, ProcessArch.is_draft.is_(False))


def advise(db: Session, area: str) -> CoachOut:
    key = area if area in AREAS else "bpm"
    return CoachOut(area=key, basis=BASIS, hints=_HINTS[key](db))


def _bpm(db: Session) -> list[CoachHint]:
    l3 = _level(db, 3)
    charters = _count(db, ProcessCharter)
    hints = [
        CoachHint(
            title=f"地图上有 {l3} 条 L3，章程 {charters} 条",
            detail="章程只说明这一条从哪到哪。公司地图是否立起，在开始使用看。",
            view="pilot",
        )
    ]
    if l3 and charters < l3:
        hints.append(
            CoachHint(
                title="还有流程没写起止",
                detail="十层核对里补上起点、终点和范围内外。空着不算这条流程已经说清。",
                view="pilot",
            )
        )
    if l3 == 0:
        hints.append(
            CoachHint(
                title="还没有 L3",
                detail="先在企业流程地图挂上流程，再谈端到端。",
                view="map",
            )
        )
    return hints


def _model(db: Session) -> list[CoachHint]:
    published = _count(db, ProcessModelVersion, ProcessModelVersion.status == "PUBLISHED")
    hints = [
        CoachHint(
            title=f"已发布模型 {published} 个",
            detail="没发布的草稿不能启动实例。符号对照在 BPMN 学习页。",
            view="designer",
        )
    ]
    if published == 0:
        hints.append(
            CoachHint(
                title="还没有可执行的图",
                detail="在设计器画完并发布。分类名去流程架构，不要画进箭头。",
                view="bpmn",
            )
        )
    return hints


def _analysis(db: Session) -> list[CoachHint]:
    logs = _count(db, ProcessEventLog)
    hints = [
        CoachHint(
            title=f"事件日志 {logs} 条",
            detail="过程挖掘只读已记下的路径和已完成实例，不从外部业务系统拉日志。",
            view="monitor",
            params="tab=mining",
        )
    ]
    if logs == 0:
        hints.append(
            CoachHint(
                title="还没有可拆的路径",
                detail="在十层核对记一笔事件日志，或把一条已发布流程跑完。",
                view="pilot",
            )
        )
    return hints


def _design(db: Session) -> list[CoachHint]:
    published = _count(db, ProcessModelVersion, ProcessModelVersion.status == "PUBLISHED")
    drafts = _count(db, ProcessModelVersion, ProcessModelVersion.status == "DRAFT")
    return [
        CoachHint(
            title=f"草稿 {drafts} 个，已发布 {published} 个",
            detail="以后的走法改在设计器。发布后，新实例才用新版本。已经在跑的实例不跟着草稿变。",
            view="designer",
        )
    ]


def _performance(db: Session) -> list[CoachHint]:
    kpis = _count(db, KpiDefinition)
    points = _count(db, KpiRecord)
    return [
        CoachHint(
            title=f"KPI {kpis} 个，数据点 {points} 个",
            detail="周期类可以在实例完成时记月均。比率和金额要靠入站回传或补录，不会自己从业务系统进来。",
            view="monitor",
            params="tab=kpi",
        )
    ]


def _change(db: Session) -> list[CoachHint]:
    projects = _count(db, Project)
    open_exc = _count(
        db,
        ExceptionEvent,
        ExceptionEvent.status.in_(("OPEN", "IN_PROGRESS")),
    )
    return [
        CoachHint(
            title=f"改善项目 {projects} 个，未关闭异常 {open_exc} 件",
            detail="红黄 KPI 和未关闭异常可以生成项目草稿。异常本身仍要人登记，变红不会自动插一行。",
            view="projects",
        )
    ]


def _tech(db: Session) -> list[CoachHint]:
    published = _count(db, ProcessModelVersion, ProcessModelVersion.status == "PUBLISHED")
    return [
        CoachHint(
            title=f"可启动的已发布模型 {published} 个",
            detail="执行页编排待办、表单和入站回传。这里没有机器人运行时，也没有把外部日志自动挖成路径。",
            view="execution",
        )
    ]


def _org(db: Session) -> list[CoachHint]:
    roles = _count(db, GovernanceRole)
    return [
        CoachHint(
            title=f"治理角色 {roles} 个",
            detail="待办分派读运行配置。授权规则和设计器权责不拦截办理。标准工时不用于个人排名或奖金。",
            view="orgs",
        )
    ]


def _enterprise(db: Session) -> list[CoachHint]:
    return [
        CoachHint(
            title=f"L1 {_level(db, 1)} · L2 {_level(db, 2)} · L3 {_level(db, 3)} · L4 {_level(db, 4)}",
            detail="地图到活动为止。任务在流程任务里，不另占一层。总览优先级用节点上的三个分数，不读战略目标页的链接。",
            view="map",
        )
    ]


_HINTS = {
    "bpm": _bpm,
    "model": _model,
    "analysis": _analysis,
    "design": _design,
    "performance": _performance,
    "change": _change,
    "tech": _tech,
    "org": _org,
    "enterprise": _enterprise,
}
