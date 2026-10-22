"""生产环境初始化：参考数据 + 首个管理员，不灌演示业务数据。

用法：
    python -m scripts.bootstrap                     # 交互式输入管理员口令
    BOOTSTRAP_ADMIN_PASSWORD='...' python -m scripts.bootstrap
    python -m scripts.bootstrap --username admin --display-name 系统管理员
    python -m scripts.bootstrap --skip-reference    # 连工作流/工具/对标框架也不灌
    python -m scripts.bootstrap --reset-password    # 已存在同名管理员时重置口令

生产部署前必须设置：
    SEED_ON_STARTUP=false      # 否则空库首次启动会灌演示流程/项目
    SECRET_KEY=<随机串>
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# 允许直接从仓库根目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认是 GBK，中文输出会变乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.migrations import upgrade_head  # noqa: E402
from app.seed.runner import bootstrap_production  # noqa: E402


def _resolve_password(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    env_value = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if env_value:
        return env_value
    if not sys.stdin.isatty():
        print(
            "缺少管理员口令：请设置 BOOTSTRAP_ADMIN_PASSWORD 环境变量，或加 --password。",
            file=sys.stderr,
        )
        return None
    return getpass.getpass("管理员口令（至少 8 位，输入不回显）：")


def main() -> int:
    parser = argparse.ArgumentParser(description="Logix PMS 生产环境初始化")
    parser.add_argument(
        "--username",
        default=os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin"),
        help="首个管理员用户名（默认 admin）",
    )
    parser.add_argument(
        "--display-name",
        default=os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "系统管理员"),
        help="管理员显示名（默认 系统管理员）",
    )
    parser.add_argument("--department", default=os.getenv("BOOTSTRAP_ADMIN_DEPARTMENT"))
    parser.add_argument(
        "--password",
        default=None,
        help="管理员口令；不传则读 BOOTSTRAP_ADMIN_PASSWORD 或交互输入（不建议写在命令历史里）",
    )
    parser.add_argument(
        "--skip-reference",
        action="store_true",
        help="不灌工作流模板、工具箱与对标框架，只创建管理员",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="同名管理员已存在时重置其口令（默认不改）",
    )
    args = parser.parse_args()

    password = _resolve_password(args.password)
    if not password:
        return 2

    # 生产初始化必须建立 Alembic 版本链，不能退回 create_all
    upgrade_head()

    with SessionLocal() as db:
        try:
            result = bootstrap_production(
                db,
                username=args.username,
                password=password,
                display_name=args.display_name,
                department=args.department,
                include_reference=not args.skip_reference,
                reset_password=args.reset_password,
            )
        except ValueError as exc:
            print(f"初始化失败：{exc}", file=sys.stderr)
            return 1

    admin = result["admin"]
    reference = result["reference"]
    print("生产初始化完成：")
    if admin["created"]:
        state = "新建"
    elif admin["password_reset"]:
        state = "已存在，口令已重置"
    else:
        state = "已存在，口令未改"
    print(f"  管理员            {admin['username']}（{state}）")
    if args.skip_reference:
        print("  参考数据          已跳过")
    else:
        print(f"  标准工作流步骤     {reference['workflow_steps']}")
        print(f"  方法论工具         {reference['tools']}")
        print(f"  步骤契约           {reference['step_contracts']}")
        print(f"  交付物定义         {reference['deliverable_definitions']}")
        print(f"  对标框架           {reference['benchmark_frameworks']}")
        print(f"  对标分类           {reference['benchmark_categories']}")
    print(f"  数据库             {settings.database_url.split('://')[0]}")
    print("提示：演示业务数据未灌入；请用管理员账号登录后录入公司流程与项目。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
