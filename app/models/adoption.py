"""同级边界核对、机器人登记、培训到场。

这三张表各自只记一件已经发生的事：
- 某个上级下的同级流程有没有做同一件事（人写的结论，不是自动判定）
- 某条流程上，哪一个机器人替掉了哪一段人工操作
- 谁在哪一天听完了这条流程的哪一课
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class SiblingBoundaryReview(Base):
    """一个 L1 或 L2 下，同级流程是否重叠的当前结论。每个上级只保留一份。"""

    __tablename__ = "sibling_boundary_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_sibling_boundary_parent"),
        unique=True,
        index=True,
    )
    reviewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_sibling_boundary_reviewer"),
        index=True,
    )
    overlap_found: Mapped[bool] = mapped_column(Boolean, default=False)
    # 有重叠时写下两边都在做的那一项工作。空字符串表示这份结论没有指出重复项。
    overlap_work: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SiblingBoundaryLine(Base):
    """一个直接下级在同级对照里的起止。过关要逐条写全，不能只选没有重叠。"""

    __tablename__ = "sibling_boundary_line"
    __table_args__ = (UniqueConstraint("parent_id", "child_id", name="uq_sibling_boundary_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_sibling_line_parent"),
        index=True,
    )
    child_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_sibling_line_child"),
        index=True,
    )
    starts_at: Mapped[str] = mapped_column(String(200))
    ends_at: Mapped[str] = mapped_column(String(200))
    in_scope: Mapped[str] = mapped_column(Text)
    out_of_scope: Mapped[str] = mapped_column(Text)
    distinct_work: Mapped[str] = mapped_column(Text)


class MapCoverageItem(Base):
    """公司工作清单的一条。要么挂到 L1/L2，要么写明本期不做。"""

    __tablename__ = "map_coverage_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    process_id: Mapped[int | None] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_coverage_item_process"),
        nullable=True,
        index=True,
    )
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_coverage_item_author"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RpaBot(Base):
    """挂在 L3 或 L4 上的一条机器人登记。"""

    __tablename__ = "rpa_bot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_rpa_bot_process"),
        index=True,
    )
    activity_name: Mapped[str] = mapped_column(String(200))
    bot_name: Mapped[str] = mapped_column(String(200))
    manual_step: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_rpa_bot_owner"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProcessTrainingRecord(Base):
    """某个人听完这条流程某一课的到场记录。"""

    __tablename__ = "process_training_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_process_training_process"),
        index=True,
    )
    trainee_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_process_training_trainee"),
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(200))
    completed_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MapCoverageReview(Base):
    """这张流程地图是否盖住公司要管的工作。全公司只留一份人写的说明。"""

    __tablename__ = "map_coverage_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reviewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_map_coverage_reviewer"),
        index=True,
    )
    covers_company: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProcessEventLog(Base):
    """记进本系统的一条外部日志。挖掘读这些行，不从 ERP 或 OA 自动拉取。"""

    __tablename__ = "process_event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_event_log_process"),
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(80))
    case_key: Mapped[str] = mapped_column(String(80), index=True)
    activity_name: Mapped[str] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RpaRun(Base):
    """一次已经记下的机器人运行，并指向一个已有的集成端点。"""

    __tablename__ = "rpa_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(
        ForeignKey("rpa_bot.id", ondelete="CASCADE", name="fk_rpa_run_bot"),
        index=True,
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("integration_endpoint.id", ondelete="RESTRICT", name="fk_rpa_run_endpoint"),
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessCase(Base):
    """一条没有固定步骤顺序的案例：事情、情形、责任人。"""

    __tablename__ = "process_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_process_case_process"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    situation: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_process_case_owner"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessTechnologyUse(Base):
    """这条流程上，区块链、人工智能或物联网具体用在哪一段。"""

    __tablename__ = "process_technology_use"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_technology_use_process"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(200))
    usage_note: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT", name="fk_technology_use_owner"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
