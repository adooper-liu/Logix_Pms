"""预览格式判定：原生内联与 Office 转换边界。"""

from __future__ import annotations

from app.services import preview


def test_preview_kind_native_formats():
    assert preview.preview_kind("a.pdf", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.png", None) == preview.PREVIEW_IMAGE
    assert preview.preview_kind("a.md", None) == preview.PREVIEW_TEXT


def test_office_only_converts_when_converter_available(monkeypatch):
    monkeypatch.setattr(preview, "converter_available", lambda: False)
    assert preview.preview_kind("a.docx", None) is None
    assert preview.preview_kind("a.vsdx", None) is None

    monkeypatch.setattr(preview, "converter_available", lambda: True)
    assert preview.preview_kind("a.docx", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.xlsx", None) == preview.PREVIEW_PDF
    # Visio/CAD 不在 LibreOffice 稳定转换范围内。
    assert preview.preview_kind("a.vsdx", None) is None
    assert preview.preview_kind("a.dwg", None) is None


def test_preview_filename_marks_converted_files_as_pdf():
    assert preview.preview_filename("方案.docx", preview.PREVIEW_PDF) == "方案.pdf"
    assert preview.preview_filename("方案.pdf", preview.PREVIEW_PDF) == "方案.pdf"
    assert preview.preview_filename("图.png", preview.PREVIEW_IMAGE) == "图.png"


def test_inline_headers_are_safe():
    headers = preview.inline_headers("方案 1.pdf")
    assert headers["Content-Disposition"].startswith("inline;")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in headers["Content-Security-Policy"]
