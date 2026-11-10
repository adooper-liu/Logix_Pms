"""活动原资源引用，不复制源对象。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ActivityResourceLink(Base):
    __tablename__ = "activity_resource_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_resource_link_activity"),
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(16), index=True)
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ref_key: Mapped[str] = mapped_column(String(128))
    org_scope: Mapped[str] = mapped_column(String(16), default="GLOBAL", server_default="GLOBAL")
    node_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_resource_link_creator"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("activity_id", "ref_key", "org_scope", name="uq_activity_resource_ref"),
    )
