"""迁移链的正确性验证。

核心断言只有一条：**迁移建出来的 schema 必须和 ORM 模型完全一致**。
只要这条成立，就不会出现「模型改了但忘了生成迁移」导致的线上事故。
"""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401  确保所有模型已注册
from alembic import command
from app.core.config import PROJECT_ROOT
from app.core.database import Base


def _config(url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # 别让 alembic 重配 pytest 的日志
    return cfg


def _sqlite_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"


def _schema_diff(url: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": True}
            )
            return compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()


def test_upgrade_creates_schema_matching_models(tmp_path):
    url = _sqlite_url(tmp_path)
    command.upgrade(_config(url), "head")

    diff = _schema_diff(url)
    assert diff == [], f"迁移与模型不一致（说明模型改了但没生成迁移）：{diff}"


def test_upgrade_is_idempotent(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # 重复执行应为空操作
    assert _schema_diff(url) == []


def test_downgrade_to_base_removes_everything(tmp_path):
    """downgrade 必须能干净回退，否则出问题时没法 rollback。"""
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    # 回到 base 后，模型里的表应该一个都不剩（alembic_version 除外）
    engine = create_engine(url)
    try:
        from sqlalchemy import inspect

        tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert tables == set(), f"downgrade 后仍有残留表：{sorted(tables)}"

    # 再次升级应能恢复完整 schema
    command.upgrade(cfg, "head")
    assert _schema_diff(url) == []


def test_current_revision_helper(tmp_path):
    from app.core.migrations import current_revision

    url = _sqlite_url(tmp_path)
    assert current_revision(url) is None
    command.upgrade(_config(url), "head")
    assert current_revision(url) is not None
