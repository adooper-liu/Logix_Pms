"""常驻任务：超期升级和 Outbox 投递。

    python -m scripts.worker
    WORKER_INTERVAL_SECONDS=60 python -m scripts.worker

多副本时只应跑一个 worker，避免同一条升级被两个进程同时改派。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: F401,E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.escalation import scan_escalations  # noqa: E402
from app.services.integrations import deliver_pending  # noqa: E402

logger = logging.getLogger("logix.worker")


def run_once() -> dict:
    from app.core.config import settings

    if settings.flowable_sandbox_enabled:
        from app.models.engine import EngineCommand
        from app.services import engine_execution, engine_projection

        with SessionLocal() as db:
            rows = db.scalars(
                select(EngineCommand)
                .where(
                    (EngineCommand.status.in_(("PREPARED", "UNKNOWN")))
                    | ((EngineCommand.status == "SUCCEEDED") & EngineCommand.error.is_not(None))
                )
                .limit(20)
            ).all()
            for command in rows:
                user = db.get(User, command.user_id)
                if user and user.is_active and user.role != "VIEWER":
                    engine_execution.recover(db, user, command.id)
            engine_projection.consume(db)
    with SessionLocal() as db:
        actor = db.scalar(
            select(User).where(
                User.role.in_((Role.ADMIN.value, Role.MANAGER.value)),
                User.is_active.is_(True),
            )
        )
        escalated = 0
        if actor is not None:
            result = scan_escalations(db, actor)
            escalated = result.escalated
        delivery = deliver_pending(db)
        db.commit()
        return {
            "escalated": escalated,
            "delivered": delivery.delivered,
            "pending": delivery.pending,
        }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    interval = int(os.getenv("WORKER_INTERVAL_SECONDS", "60"))
    while True:
        try:
            summary = run_once()
            logger.info("worker cycle %s", summary)
        except Exception:
            logger.exception("worker cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
