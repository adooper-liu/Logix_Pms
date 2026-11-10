"""迁移链的正确性验证。

核心断言只有一条：**迁移建出来的 schema 必须和 ORM 模型完全一致**。
只要这条成立，就不会出现「模型改了但忘了生成迁移」导致的线上事故。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, Table, create_engine, select

import app.models  # noqa: F401  确保所有模型已注册
from alembic import command
from app.core.config import PROJECT_ROOT
from app.core.database import Base


def _config(url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # 别让 alembic 重配 pytest 的日志
    return cfg


def _sqlite_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"


def _schema_diff(url: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": True}
            )
            return compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()


def test_upgrade_creates_schema_matching_models(tmp_path):
    url = _sqlite_url(tmp_path)
    command.upgrade(_config(url), "head")

    diff = _schema_diff(url)
    assert diff == [], f"迁移与模型不一致（说明模型改了但没生成迁移）：{diff}"


def test_governance_finding_type_preserves_review_code(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "q2b3c4d5e6f7")
    engine = create_engine(url)
    code = "AUTHORIZATION_EXCEPTION_DUE_REVIEW"
    try:
        table = Table("governance_finding", MetaData(), autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                table.insert().values(
                    type="REVIEW_OVERDUE",
                    severity="MEDIUM",
                    entity_type="tool_template",
                    entity_id=1,
                    title="原治理记录",
                    status="OPEN",
                    detected_at=datetime(2026, 11, 3),
                    last_seen_at=datetime(2026, 11, 3),
                )
            )
        command.upgrade(cfg, "head")
        table = Table("governance_finding", MetaData(), autoload_with=engine)
        assert table.c.type.type.length >= len(code)
        with engine.begin() as conn:
            assert conn.scalar(select(table.c.type)) == "REVIEW_OVERDUE"
            conn.execute(
                table.insert().values(
                    type=code,
                    severity="MEDIUM",
                    entity_type="authorization_exception",
                    entity_id=1,
                    title="到期例外待复盘",
                    status="OPEN",
                    detected_at=datetime(2026, 11, 3),
                    last_seen_at=datetime(2026, 11, 3),
                )
            )
            assert conn.scalar(select(table.c.type).where(table.c.type == code)) == code
        with pytest.raises(RuntimeError, match="保留 r3c4d5e6f7a8"):
            command.downgrade(cfg, "q2b3c4d5e6f7")
        with engine.connect() as conn:
            assert set(conn.scalars(select(table.c.type))) == {"REVIEW_OVERDUE", code}
            assert conn.scalar(
                select(Table("alembic_version", MetaData(), autoload_with=conn))
            ) == ("r3c4d5e6f7a8")
    finally:
        engine.dispose()


def test_upgrade_is_idempotent(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # 重复执行应为空操作
    assert _schema_diff(url) == []


def test_downgrade_to_base_removes_everything(tmp_path):
    """downgrade 必须能干净回退，否则出问题时没法 rollback。"""
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    # 回到 base 后，模型里的表应该一个都不剩（alembic_version 除外）
    engine = create_engine(url)
    try:
        from sqlalchemy import inspect

        tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert tables == set(), f"downgrade 后仍有残留表：{sorted(tables)}"

    # 再次升级应能恢复完整 schema
    command.upgrade(cfg, "head")
    assert _schema_diff(url) == []


def test_m3_upgrade_preserves_legacy_charter_and_sheet(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "s4d5e6f7a8b9")
    engine = create_engine(url)
    try:
        # 原行保持原内容，不能由迁移补客户/授权/交接确认。
        charter = Table("process_charter", MetaData(), autoload_with=engine)
        sheet = Table("tool_sheet", MetaData(), autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                charter.insert().values(
                    process_id=123,
                    purpose="原目的",
                    starts_at="起",
                    ends_at="止",
                    in_scope="含",
                    out_of_scope="不含",
                    stop_condition="停",
                    sponsor_user_id=456,
                    created_at=datetime(2026, 11, 4),
                    updated_at=datetime(2026, 11, 4),
                )
            )
            conn.execute(
                sheet.insert().values(
                    tool_code="SIPOC",
                    process_id=123,
                    title="原方法",
                    fields=[{"key": "input", "label": "输入", "value": "原输入"}],
                    created_at=datetime(2026, 11, 4),
                    updated_at=datetime(2026, 11, 4),
                )
            )
        command.upgrade(cfg, "head")
        charter = Table("process_charter", MetaData(), autoload_with=engine)
        sheet = Table("tool_sheet", MetaData(), autoload_with=engine)
        with engine.connect() as conn:
            old = conn.execute(select(charter)).mappings().one()
            assert old["purpose"] == "原目的" and old["details"] is None and old["revision"] == 0
            old_sheet = conn.execute(select(sheet)).mappings().one()
            assert old_sheet["fields"][0]["value"] == "原输入"
            assert (
                old_sheet["handoff"] is None
                and old_sheet["template_version_id"] is None
                and old_sheet["revision"] == 0
            )
    finally:
        engine.dispose()


def test_p1_backfills_matter_scope_without_guessing(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "f8a9b0c1d2e3")
    engine = create_engine(url)
    try:
        table = Table("raci_assignment", MetaData(), autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                table.insert().values(
                    process_id=123,
                    matter="同名活动",
                    role_id=456,
                    raci="A",
                    created_at=datetime(2026, 11, 10),
                    updated_at=datetime(2026, 11, 10),
                )
            )
        command.upgrade(cfg, "head")
        table = Table("raci_assignment", MetaData(), autoload_with=engine)
        with engine.connect() as conn:
            row = conn.execute(select(table)).mappings().one()
            assert row["scope_key"] == "MATTER:同名活动"
            assert row["activity_id"] is None and row["node_key"] is None
        command.downgrade(cfg, "f8a9b0c1d2e3")
        table = Table("raci_assignment", MetaData(), autoload_with=engine)
        with engine.connect() as conn:
            assert conn.execute(select(table.c.matter)).scalar_one() == "同名活动"
    finally:
        engine.dispose()


def test_p1_downgrade_refuses_data_before_ddl(tmp_path):
    url = _sqlite_url(tmp_path)
    cfg = _config(url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        table = Table("activity_resource_link", MetaData(), autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                table.insert().values(
                    activity_id=123,
                    resource_type="EQUIPMENT",
                    ref_key="EQUIP:TEST",
                    org_scope="GLOBAL",
                    is_active=True,
                    created_at=datetime(2026, 11, 10),
                )
            )
        with pytest.raises(RuntimeError, match="preserve g9b0c1d2e3f4"):
            command.downgrade(cfg, "f8a9b0c1d2e3")
        with engine.connect() as conn:
            assert conn.scalar(select(table.c.ref_key)) == "EQUIP:TEST"
            version = Table("alembic_version", MetaData(), autoload_with=conn)
            assert conn.scalar(select(version.c.version_num)) == "g9b0c1d2e3f4"
    finally:
        engine.dispose()


def test_current_revision_helper(tmp_path):
    from app.core.migrations import current_revision

    url = _sqlite_url(tmp_path)
    assert current_revision(url) is None
    command.upgrade(_config(url), "head")
    assert current_revision(url) is not None
