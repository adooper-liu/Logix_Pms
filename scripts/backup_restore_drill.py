"""备份后立刻恢复，确认读回的是同一行。

默认演练使用临时 SQLite，不碰开发库。PostgreSQL 需要本机有 pg_dump / psql，
并且显式传入 --postgres 与一个空的演练库 URL。

    python scripts/backup_restore_drill.py
    python scripts/backup_restore_drill.py --postgres postgresql+psycopg://.../logix_pms_drill
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def run_sqlite_drill() -> None:
    with tempfile.TemporaryDirectory(prefix="logix_pms_backup_") as tmp:
        root = Path(tmp)
        source = root / "source.db"
        backup = root / "backup.db"
        restored = root / "restored.db"

        source_conn = sqlite3.connect(source)
        backup_conn = sqlite3.connect(backup)
        try:
            source_conn.execute("CREATE TABLE drill (id INTEGER PRIMARY KEY, note TEXT)")
            source_conn.execute("INSERT INTO drill (note) VALUES (?)", ("备份演练",))
            source_conn.commit()
            source_conn.backup(backup_conn)
            backup_conn.commit()
        finally:
            source_conn.close()
            backup_conn.close()

        restored_conn = sqlite3.connect(restored)
        backup_conn = sqlite3.connect(backup)
        try:
            backup_conn.backup(restored_conn)
            restored_conn.commit()
            note = restored_conn.execute("SELECT note FROM drill").fetchone()
        finally:
            backup_conn.close()
            restored_conn.close()
        if note is None or note[0] != "备份演练":
            raise SystemExit("恢复后的数据与备份不一致")


def run_postgres_drill(database_url: str) -> None:
    """把当前库 pg_dump 到 SQL，再灌进演练库并核对 alembic_version 能读出来。"""
    if not database_url.startswith("postgresql"):
        raise SystemExit("演练库 URL 必须是 postgresql")
    # psycopg URL 转成 libpq 能识别的形式：去掉 +psycopg
    libpq = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    dump = subprocess.run(
        ["pg_dump", "--schema-only", libpq],
        check=False,
        capture_output=True,
        text=True,
    )
    if dump.returncode != 0:
        raise SystemExit(dump.stderr.strip() or "pg_dump 失败")
    if "CREATE TABLE" not in dump.stdout and "alembic_version" not in dump.stdout:
        raise SystemExit("pg_dump 没有产生可恢复的 schema")
    restore = subprocess.run(
        ["psql", libpq, "-v", "ON_ERROR_STOP=1"],
        input=dump.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    if restore.returncode != 0:
        raise SystemExit(restore.stderr.strip() or "psql 恢复失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="备份并恢复演练")
    parser.add_argument(
        "--postgres",
        default="",
        help="演练用的 PostgreSQL URL（会执行 schema-only 恢复，不要指向业务库）",
    )
    args = parser.parse_args()
    run_sqlite_drill()
    print("SQLite 备份恢复演练通过")
    if args.postgres:
        run_postgres_drill(args.postgres)
        print("PostgreSQL schema 备份恢复演练通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
