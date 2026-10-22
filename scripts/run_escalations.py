"""按升级策略扫描超期任务，供 cron / 任务调度器调用。

用法：
    python scripts/run_escalations.py --username manager
    python scripts/run_escalations.py --username manager --process-id 12

示例 crontab（每 15 分钟）：
    */15 * * * * cd /srv/logix_pms && python scripts/run_escalations.py --username manager
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许直接从仓库根目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认是 GBK，中文输出会变乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: F401,E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.escalation import scan_escalations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Logix PMS 超期任务升级扫描")
    parser.add_argument("--username", default="manager", help="执行扫描的服务账号")
    parser.add_argument("--process-id", type=int, default=None, help="只扫描指定流程")
    parser.add_argument("--limit", type=int, default=500, help="单次最多扫描任务数")
    args = parser.parse_args()

    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == args.username))
        if actor is None or not actor.is_active:
            print(f"服务账号 {args.username} 不存在或已停用", file=sys.stderr)
            return 2
        if actor.role not in (Role.ADMIN.value, Role.MANAGER.value):
            print(f"服务账号 {args.username} 必须是流程管理科或系统管理员", file=sys.stderr)
            return 2

        result = scan_escalations(db, actor, process_id=args.process_id, limit=args.limit)
        db.commit()
        print(json.dumps(result.model_dump(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
