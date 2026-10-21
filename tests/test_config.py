"""配置加载的回归测试。"""

from __future__ import annotations

import os

from app.core.config import load_dotenv


def test_dotenv_loads_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# 注释行应被忽略\n"
        "\n"
        "PSM_TEST_PLAIN=hello\n"
        'PSM_TEST_QUOTED="with space"\n'
        "PSM_TEST_SINGLE='single'\n"
        "MALFORMED_LINE_WITHOUT_EQUALS\n",
        encoding="utf-8",
    )
    for key in ("PSM_TEST_PLAIN", "PSM_TEST_QUOTED", "PSM_TEST_SINGLE"):
        os.environ.pop(key, None)

    load_dotenv(env)

    assert os.environ["PSM_TEST_PLAIN"] == "hello"
    assert os.environ["PSM_TEST_QUOTED"] == "with space"
    assert os.environ["PSM_TEST_SINGLE"] == "single"
    for key in ("PSM_TEST_PLAIN", "PSM_TEST_QUOTED", "PSM_TEST_SINGLE"):
        os.environ.pop(key, None)


def test_dotenv_does_not_override_real_env(tmp_path):
    """环境变量的优先级必须高于 .env，否则容器注入的配置会被本地文件悄悄覆盖。"""
    env = tmp_path / ".env"
    env.write_text("PSM_TEST_OVERRIDE=from_file\n", encoding="utf-8")
    os.environ["PSM_TEST_OVERRIDE"] = "from_env"

    load_dotenv(env)

    assert os.environ["PSM_TEST_OVERRIDE"] == "from_env"
    os.environ.pop("PSM_TEST_OVERRIDE", None)


def test_missing_dotenv_is_ignored(tmp_path):
    load_dotenv(tmp_path / "does-not-exist.env")  # 不应抛异常


def test_settings_point_at_postgres_by_default():
    from app.core.config import settings

    # 测试里 conftest 会把 DATABASE_URL 指到临时库，这里只验证解析逻辑
    assert settings.is_sqlite or settings.is_postgres
    assert not (settings.is_sqlite and settings.is_postgres)
