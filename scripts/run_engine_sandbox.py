"""Run only the explicitly isolated synthetic PMS sandbox; never loads the root .env."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sandbox_environment():
    if (ROOT / ".env").exists():
        raise RuntimeError("Sandbox requires an isolated checkout without root .env")
    folder = ROOT / "var/r3-sandbox"
    path = folder / "runtime.env"
    values = dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    allowed = {
        "FLOWABLE_POC_TOKEN",
        "FLOWABLE_POC_DB_PASSWORD",
        "FLOWABLE_SANDBOX_TOKEN",
        "BUILD_REVISION",
    }
    if set(values) != allowed or any(not value for value in values.values()):
        raise RuntimeError("Dedicated sandbox runtime.env fields required")
    env = os.environ.copy()
    env.update(values)
    env.update(
        DATABASE_URL="sqlite:///" + (folder / "pms.db").as_posix(),
        SEED_ON_STARTUP="true",
        ALLOW_DEV_SECRET="true",
        AUTO_MIGRATE="true",
        FLOWABLE_SANDBOX_ENABLED="true",
        FLOWABLE_SANDBOX_URL="http://127.0.0.1:8136",
        FLOWABLE_SANDBOX_NAMESPACE="logix-r3-sandbox",
        PYTHONIOENCODING="utf-8",
    )
    return env


def main():
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8124"],
        cwd=ROOT,
        env=sandbox_environment(),
        check=True,
    )


if __name__ == "__main__":
    main()
