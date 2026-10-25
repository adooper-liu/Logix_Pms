"""定时提醒任务：治理扫描 + 逾期通知扫描。

仓库不内置进程内定时器（与 `services/escalation.py` 的约定一致），
由外部 cron / 任务调度器每天调用一次：

    python scripts/scan_reminders.py

crontab 示例（每天 08:07，避免整点集中）：

    7 8 * * * cd /app && python scripts/scan_reminders.py >> /var/log/logix-pms-scan.log 2>&1

它会：
1. 扫描资产、知识、工具的复核/归档问题，生成或关闭治理待办；
2. 扫描逾期异常、里程碑与流程任务，生成站内通知。
"""

from __future__ import annotations

import sys

from app.core.database import SessionLocal
from app.services import governance, notifications


def main() -> int:
    db = SessionLocal()
    try:
        findings = governance.scan(db)
        alerts = notifications.scan_overdue(db)
        db.commit()
        print(
            "治理扫描："
            f"扫描 {findings.scanned} 项，新增 {findings.created}，"
            f"更新 {findings.updated}，关闭 {findings.resolved}，通知 {findings.notified}"
        )
        print(f"逾期提醒：扫描 {alerts.scanned} 项，新建 {alerts.created} 条通知")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
