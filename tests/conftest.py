"""测试入口。

必须在导入 app 之前设置环境变量——Settings 是模块级实例，导入即固化。

数据库选择：
- 默认用临时 SQLite 文件，`pytest` 开箱即跑，不需要 Docker；
- 设了 `TEST_DATABASE_URL` 就针对那个库跑（建议指向独立的 test 库，会先 drop 全部表）。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if _TEST_DB_URL:
    os.environ["DATABASE_URL"] = _TEST_DB_URL
else:
    _TMP_DIR = Path(tempfile.mkdtemp(prefix="logix_pms_test_"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["SEED_ON_STARTUP"] = "true"
# 测试直接建表，不跑迁移链：每个用例集都要快，且迁移本身有专门的用例验证
os.environ["AUTO_MIGRATE"] = "false"
# 附件落临时目录，禁止测试往仓库 var/ 里写文件
os.environ["ATTACHMENT_DIR"] = str(Path(tempfile.mkdtemp(prefix="logix_pms_attachments_")))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: F401,E402
from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine, ensure_postgres_extensions  # noqa: E402
from app.main import app  # noqa: E402

# 针对真实数据库跑测试时，先重建 schema，避免上一轮残留数据影响断言。
# 放在模块级而不是 fixture 里，保证在任何用例之前执行。
if not settings.is_sqlite:
    ensure_postgres_extensions()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

API = "/api/v1"


def _auth_headers(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败 {username}: {resp.text}"
    return {"Authorization": "Bearer " + resp.json()["token"]}


@pytest.fixture(scope="session")
def client():
    """默认以系统管理员身份访问，业务用例不必各自处理鉴权。"""
    with TestClient(app) as c:
        c.headers.update(_auth_headers(c, "admin", "admin123"))
        yield c


@pytest.fixture(scope="session")
def anon_client():
    """未登录的客户端，用于验证 401。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def viewer_client():
    with TestClient(app) as c:
        c.headers.update(_auth_headers(c, "viewer", "viewer123"))
        yield c


@pytest.fixture(scope="session")
def owner_client():
    """流程 Owner：chen 的 display_name 是「陈经理」，种子数据里已按 owner_user_id 绑定。"""
    with TestClient(app) as c:
        c.headers.update(_auth_headers(c, "chen", "chen123"))
        yield c


@pytest.fixture(scope="session")
def manager_client():
    with TestClient(app) as c:
        c.headers.update(_auth_headers(c, "manager", "manager123"))
        yield c
