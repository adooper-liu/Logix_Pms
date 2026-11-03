"""真实前端专项共用的临时SQLite应用，仅创建本次隔离服务。"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SHEET_SOURCE = "web/js/views/map.js"


@contextmanager
def isolated_app():
    """只启动并清理本次子进程；调用者不能提供外部数据库或服务地址。"""
    with tempfile.TemporaryDirectory(
        prefix="logix-sheet-", ignore_cleanup_errors=True
    ) as directory:
        folder = Path(directory)
        database_url = "sqlite:///" + (folder / "app.db").as_posix()
        env = os.environ.copy()
        env.update(
            DATABASE_URL=database_url,
            TEST_DATABASE_URL="",
            ALLOW_DEV_SECRET="true",
            SEED_ON_STARTUP="true",
            AUTO_MIGRATE="true",
            ATTACHMENT_BACKEND="local",
            ATTACHMENT_DIR=str(folder / "attachments"),
            PREVIEW_CONVERTER="none",
            PYTHONUTF8="1",
        )
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.core.config import settings; import os; assert settings.is_sqlite and settings.database_url == os.environ['DATABASE_URL']; print('Isolated SQLite settings: OK')",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with (folder / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "隔离服务启动失败："
                            + (folder / "server.log").read_text(encoding="utf-8")[-4000:]
                        )
                    try:
                        with urlopen(base + "/health", timeout=1) as response:
                            health = json.load(response)
                        if health.get("database") == "sqlite" and health.get("database_ok"):
                            break
                    except (URLError, TimeoutError):
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("隔离服务未就绪")
                with urlopen(base + "/static/js/views/map.js", timeout=5) as response:
                    served = response.read()
                assert (
                    hashlib.sha256(served).digest()
                    == hashlib.sha256((ROOT / SHEET_SOURCE).read_bytes()).digest()
                ), "服务静态文件不是当前代码"
                yield base, folder
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
