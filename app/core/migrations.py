"""数据库迁移的应用内入口。

生产环境的 schema 演进只走 Alembic，不再用 create_all ——
否则模型一改，库就悄悄跟模型漂移，而且没有版本可回滚。
"""

from __future__ import annotations

from alembic.config import Config

from alembic import command
from app.core.config import PROJECT_ROOT, settings


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url or settings.database_url)
    return cfg


def upgrade_head(url: str | None = None) -> None:
    """把数据库升到最新版本。已是最新时是空操作。"""
    command.upgrade(alembic_config(url), "head")


def current_revision(url: str | None = None) -> str | None:
    cfg = alembic_config(url)
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, pool

    engine = create_engine(cfg.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
