"""备份脚本的 SQLite 往返。"""

from __future__ import annotations

from scripts.backup_restore_drill import run_sqlite_drill


def test_sqlite_backup_restore_roundtrip():
    run_sqlite_drill()
