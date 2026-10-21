"""灌种子数据。

用法：
    python -m scripts.seed                 # 只在库为空时灌
    python -m scripts.seed --reset         # 清空重灌（会丢掉已有业务数据）
    python -m scripts.seed --benchmarks    # 只补灌对标框架数据（已有则跳过）
    python -m scripts.seed --benchmarks --reset   # 只重建对标框架数据
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接从仓库根目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认是 GBK，中文输出会变乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import app.models  # noqa: F401,E402
from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.migrations import upgrade_head  # noqa: E402
from app.seed.runner import (  # noqa: E402
    reset_and_seed,
    reset_benchmarks,
    seed_benchmarks_if_empty,
    seed_if_empty,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Logix PMS 种子数据灌库")
    parser.add_argument("--reset", action="store_true", help="先清空对应数据再灌")
    parser.add_argument(
        "--benchmarks", action="store_true", help="只处理对标框架数据，不动业务数据"
    )
    args = parser.parse_args()

    # 与启动流程保持一致：默认走迁移，测试/临时环境才直接建表
    if settings.auto_migrate:
        upgrade_head()
    else:
        Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if args.benchmarks:
            counts = reset_benchmarks(db) if args.reset else seed_benchmarks_if_empty(db)
            if counts is None:
                print("对标框架数据已存在，跳过。要重建请加 --benchmarks --reset。")
                return 0
        elif args.reset:
            counts = reset_and_seed(db)
        else:
            counts = seed_if_empty(db)
            if counts is None:
                print("库里已有流程数据，跳过灌入。要清空重灌请加 --reset。")
                return 0

    print("灌库完成：")
    for key, value in counts.items():
        print(f"  {key:<16} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
