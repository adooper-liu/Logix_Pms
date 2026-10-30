"""数据库引擎与会话。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Dict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

if settings.is_sqlite:
    # SQLite 在多线程下需要关闭 check_same_thread
    _engine_kwargs: Dict[str, Any] = {"connect_args": {"check_same_thread": False}}
else:
    # PostgreSQL：给足连接池，避免并发请求时排队
    _engine_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,  # 半小时回收，避开中间件/防火墙的空闲断连
        "pool_timeout": 30,
    }

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.sql_echo,
    future=True,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


def ensure_postgres_extensions(bind=engine) -> None:
    """create_all 路径不执行 Alembic 的 CREATE EXTENSION，这里补上。

    `knowledge_item.search_text` 的 GIN 索引依赖 pg_trgm；测试/临时环境
    用 create_all 建表时如果不先装扩展，PostgreSQL 会直接报
    `operator class "gin_trgm_ops" does not exist`。
    """
    if bind.dialect.name != "postgresql":
        return
    with bind.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
