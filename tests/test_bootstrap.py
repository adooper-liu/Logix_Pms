"""生产初始化的边界：只灌参考数据，不灌演示业务数据。"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.database import Base
from app.core.security import verify_password
from app.models.benchmark import BenchmarkCategory, BenchmarkFramework, BenchmarkMetric
from app.models.execution import ProcessInstance
from app.models.process import ProcessArch
from app.models.project import Project, WorkflowTemplate
from app.models.tool import Tool
from app.models.user import User
from app.seed import benchmark_data, corpus, pcf_data
from app.seed.runner import bootstrap_production, seed_if_empty, seed_single_flow


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'bootstrap.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_bootstrap_seeds_reference_and_admin_only(tmp_path):
    with _session(tmp_path) as db:
        result = bootstrap_production(
            db,
            username="admin",
            password="S3cure-pass",
            display_name="系统管理员",
            department="信息中心",
        )

        assert result["admin"]["created"] is True
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(WorkflowTemplate)) == len(corpus.WORKFLOW)
        assert db.scalar(select(func.count()).select_from(Tool)) == len(corpus.TOOLS)
        pcf_dataset = pcf_data.load_pcf_v80()
        assert db.scalar(select(func.count()).select_from(BenchmarkFramework)) == len(
            benchmark_data.BENCHMARK_FRAMEWORKS
        ) + len(pcf_dataset["frameworks"])
        assert db.scalar(select(func.count()).select_from(BenchmarkCategory)) == len(
            benchmark_data.BENCHMARK_CATEGORIES
        ) + sum(len(framework["categories"]) for framework in pcf_dataset["frameworks"])
        assert db.scalar(select(func.count()).select_from(BenchmarkMetric)) == len(
            pcf_dataset["metrics"]
        )

        # 演示业务数据一行都不能进来
        assert db.scalar(select(func.count()).select_from(ProcessArch)) == 0
        assert db.scalar(select(func.count()).select_from(Project)) == 0
        assert db.scalar(select(func.count()).select_from(ProcessInstance)) == 0

        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin.role == "ADMIN"
        assert verify_password("S3cure-pass", admin.password_hash)


def test_bootstrap_is_idempotent_and_blocks_demo_seed(tmp_path):
    with _session(tmp_path) as db:
        params = dict(username="admin", password="S3cure-pass", display_name="系统管理员")
        bootstrap_production(db, **params)
        before = {
            "users": db.scalar(select(func.count()).select_from(User)),
            "steps": db.scalar(select(func.count()).select_from(WorkflowTemplate)),
            "tools": db.scalar(select(func.count()).select_from(Tool)),
        }

        second = bootstrap_production(db, **params)
        assert second["admin"]["created"] is False
        assert second["admin"]["password_reset"] is False
        assert db.scalar(select(func.count()).select_from(User)) == before["users"]
        assert db.scalar(select(func.count()).select_from(WorkflowTemplate)) == before["steps"]
        assert db.scalar(select(func.count()).select_from(Tool)) == before["tools"]

        # 已有账号时，即使 SEED_ON_STARTUP=true 也不会把演示流程灌进来
        assert seed_if_empty(db) is None
        assert db.scalar(select(func.count()).select_from(ProcessArch)) == 0


def test_development_seed_contains_only_l3_032_and_its_project(tmp_path):
    with _session(tmp_path) as db:
        result = seed_single_flow(db, reset=True)

        processes = db.scalars(select(ProcessArch)).all()
        assert {row.code for row in processes} == {
            "L1-03",
            "L2-003",
            "L3-032",
            "L4-201",
            "L4-202",
            "L4-203",
            "L4-204",
            "L4-205",
            "L4-206",
        }
        projects = db.scalars(select(Project)).all()
        assert len(projects) == 1
        assert projects[0].process_id == next(
            row.id for row in processes if row.code == "L3-032"
        )
        assert result["process_arch"] == 9
        assert result["projects"] == 1


def test_bootstrap_can_reset_existing_admin_password(tmp_path):
    with _session(tmp_path) as db:
        bootstrap_production(
            db, username="admin", password="S3cure-pass", display_name="系统管理员"
        )
        result = bootstrap_production(
            db,
            username="admin",
            password="N3w-pass-ok",
            display_name="系统管理员",
            reset_password=True,
        )
        assert result["admin"]["created"] is False
        assert result["admin"]["password_reset"] is True
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert verify_password("N3w-pass-ok", admin.password_hash)
