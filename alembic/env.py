"""Alembic 环境配置。

数据库地址直接取应用的 settings（环境变量 > .env > 默认值），
避免 alembic.ini 与 .env 两处配置各自漂移。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# 让 alembic 在仓库根目录之外被调用时也能 import app 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: F401,E402  必须导入，否则 Base.metadata 是空的
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

config = context.config

# 允许调用方（测试、脚本）在调用 command.* 之前用 set_main_option 指定库；
# 没指定时回落到应用配置。这样迁移既能跑在应用库上，也能跑在临时库上。
_url = config.get_main_option("sqlalchemy.url") or settings.database_url
config.set_main_option("sqlalchemy.url", _url)

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """生成 SQL 脚本而不连库：alembic upgrade head --sql"""
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 迁移是短生命周期操作，用 NullPool 即可，也避免和应用的连接池互相干扰
    engine = create_engine(_url, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite 基本不支持 ALTER COLUMN，用批处理模式重建表
            render_as_batch=_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
