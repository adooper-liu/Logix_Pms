"""一键检查：格式、静态检查、测试。

这是本地和 CI 共用的唯一入口 —— `make` 在 Windows 上常常没有，所以用脚本兜底。

    python scripts/check.py          只检查
    python scripts/check.py --fix    先自动修复再检查
    python scripts/check.py --fast   跳过测试（只跑 lint）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Windows 控制台默认是 GBK，中文与符号会直接抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(name: str, cmd: list[str]) -> bool:
    print(f"\n>> {name}: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"[FAIL] {name}")
        return False
    print(f"[OK] {name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="项目检查")
    parser.add_argument("--fix", action="store_true", help="自动修复格式与可自动修复的 lint 问题")
    parser.add_argument("--fast", action="store_true", help="跳过测试")
    args = parser.parse_args()

    if shutil.which("ruff") is None:
        print("[FAIL] 找不到 ruff。先执行：pip install -r requirements-dev.txt")
        return 1

    if args.fix:
        steps = [
            ("格式化", ["ruff", "format", "."]),
            ("自动修复", ["ruff", "check", "--fix", "."]),
        ]
    else:
        steps = [
            ("格式检查", ["ruff", "format", "--check", "."]),
            ("静态检查", ["ruff", "check", "."]),
        ]

    if not args.fast:
        steps.append(("测试", [sys.executable, "-m", "pytest"]))

    failed = [name for name, cmd in steps if not run(name, cmd)]
    print()
    if failed:
        print(f"未通过：{'、'.join(failed)}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
