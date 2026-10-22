"""应用配置。

优先级：环境变量 > 项目根目录的 .env > 默认值。
刻意不引入 python-dotenv / pydantic-settings，保证内网离线部署零额外依赖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

# 默认连 Docker Compose 里的 PostgreSQL（见 docker-compose.yml）
# 端口用 5433：宿主机 5432 经常已被本地安装的 PostgreSQL 占用
DEFAULT_DATABASE_URL = "postgresql+psycopg://psm:psm_dev_password@localhost:5433/logix_pms"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """极简 .env 加载：不覆盖已经存在的环境变量。

    只支持 KEY=VALUE 和 # 注释，够用即可；复杂的配置直接走环境变量注入。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv()


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def _env_bool(key: str, default: bool) -> bool:
    return _env(key, "true" if default else "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


@dataclass(frozen=True)
class Settings:
    app_name: str = "Logix PMS · 流程管理系统"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", DEFAULT_DATABASE_URL))
    seed_on_startup: bool = field(default_factory=lambda: _env_bool("SEED_ON_STARTUP", True))
    # true：启动时执行 alembic 迁移（生产默认）
    # false：直接 create_all（测试/临时环境用，跳过迁移链）
    auto_migrate: bool = field(default_factory=lambda: _env_bool("AUTO_MIGRATE", True))
    sql_echo: bool = field(default_factory=lambda: _env_bool("SQL_ECHO", False))

    cors_origins: Tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip() for origin in _env("CORS_ORIGINS", "*").split(",") if origin.strip()
        )
    )

    # 附件存储：数据库只存元数据，文件落本地卷；生产可换 S3 实现而不改接口。
    attachment_dir: str = field(
        default_factory=lambda: _env("ATTACHMENT_DIR", str(PROJECT_ROOT / "var" / "attachments"))
    )
    attachment_max_mb: int = field(default_factory=lambda: int(_env("ATTACHMENT_MAX_MB", "50")))
    attachment_allowed_extensions: Tuple[str, ...] = field(
        default_factory=lambda: tuple(
            ext.strip().lower()
            for ext in _env(
                "ATTACHMENT_ALLOWED_EXTENSIONS",
                ".xlsx,.xlsm,.docx,.pptx,.pdf,.bpmn,.xml,.csv,.txt,.png,.jpg,.jpeg,.vsdx,.zip",
            ).split(",")
            if ext.strip()
        )
    )

    # draw.io 白板（独立于 BPMN 设计器）：默认用官方 embed，生产可指向自托管实例
    drawio_embed_url: str = field(
        default_factory=lambda: _env(
            "DRAWIO_EMBED_URL",
            "https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1&saveAndExit=1",
        )
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = Settings()
