"""实训指导：只读已有记录，不假装接了外部模型。"""

from __future__ import annotations

from pathlib import Path

API = "/api/v1"
TRAIN_JS = Path(__file__).resolve().parent.parent / "web" / "js" / "views" / "train.js"


def test_coach_reads_records_for_each_area(client):
    for area in (
        "bpm",
        "model",
        "analysis",
        "design",
        "performance",
        "change",
        "tech",
        "org",
        "enterprise",
    ):
        data = client.get(f"{API}/train/coach", params={"area": area}).json()
        assert data["area"] == area
        assert "已有记录" in data["basis"]
        assert "外部语言" in data["basis"]
        assert data["hints"]
        assert data["hints"][0]["title"]
        assert data["hints"][0]["detail"]


def test_unknown_area_falls_back_to_bpm(client):
    data = client.get(f"{API}/train/coach", params={"area": "slides"}).json()
    assert data["area"] == "bpm"
    assert any(hint["view"] == "pilot" for hint in data["hints"])


def test_train_page_keeps_lecture_and_evidence():
    text = TRAIN_JS.read_text(encoding="utf-8")
    lecture = (TRAIN_JS.parent / "train" / "lecture.js").read_text(encoding="utf-8")
    for title in (
        "Business Process Management",
        "Process Modeling",
        "Process Analysis",
        "Process Design",
        "Process Performance Management",
        "Process Transformation",
        "BPM Technologies",
        "Process Management Organization",
        "Enterprise Process Management",
    ):
        assert title in lecture
    for heading in ("开场导入", "核心概念", "实操演练", "模块小结", "本系统实证"):
        assert heading in text
    assert "订单到回款" in lecture
    assert "ADKAR" in lecture
    assert "知道为什么要变" in lecture
    assert "不用于个人排名" in text
    assert "没有机器人运行时" in text
    assert "仿真" in text
