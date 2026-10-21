# 便捷入口。Windows 上通常没有 make，直接用 python scripts/check.py
# 这里保留是为了 CI 与类 Unix 环境。

.PHONY: help install check fix fast test lint format run seed migrate e2e

help:
	@echo "install  安装开发依赖"
	@echo "check    格式 + 静态检查 + 测试（与 CI 一致）"
	@echo "fix      自动格式化并修复可自动修复的问题"
	@echo "fast     只跑格式与静态检查"
	@echo "test     只跑测试"
	@echo "run      本地启动服务（需先 docker compose up -d db）"
	@echo "seed     灌种子数据"
	@echo "migrate  执行数据库迁移"
	@echo "e2e      前端联调自检（需服务已启动）"

install:
	pip install -r requirements-dev.txt

check:
	python scripts/check.py

fix:
	python scripts/check.py --fix

fast:
	python scripts/check.py --fast

test:
	pytest

lint:
	ruff format --check .
	ruff check .

format:
	ruff format .
	ruff check --fix .

run:
	uvicorn app.main:app --reload --port 8123

seed:
	python -m scripts.seed --reset

migrate:
	alembic upgrade head

e2e:
	python scripts/verify_frontend.py http://127.0.0.1:8123 _screenshots
