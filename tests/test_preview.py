"""预览格式判定：原生内联与外部转换适配器边界。"""

from __future__ import annotations

import io
from types import SimpleNamespace
from urllib.parse import quote

from app.core.config import settings
from app.services import preview


def _preview_settings(monkeypatch, **overrides):
    monkeypatch.setattr(preview, "settings", SimpleNamespace(**{**settings.__dict__, **overrides}))


def test_preview_kind_native_formats():
    assert preview.preview_kind("a.pdf", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.png", None) == preview.PREVIEW_IMAGE
    assert preview.preview_kind("a.md", None) == preview.PREVIEW_TEXT


def test_office_only_converts_when_converter_available(monkeypatch):
    _preview_settings(monkeypatch, preview_converter="libreoffice")
    monkeypatch.setattr(preview, "converter_available", lambda: False)
    assert preview.preview_kind("a.docx", None) is None
    assert preview.preview_kind("a.vsdx", None) is None

    monkeypatch.setattr(preview, "converter_available", lambda: True)
    assert preview.preview_kind("a.docx", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.xlsx", None) == preview.PREVIEW_PDF
    # LibreOffice 不承诺 Visio/CAD。
    assert preview.preview_kind("a.vsdx", None) is None
    assert preview.preview_kind("a.dwg", None) is None


def test_http_converter_covers_visio_and_cad(monkeypatch):
    _preview_settings(
        monkeypatch,
        preview_converter="http",
        preview_converter_url="http://adapter.local/convert",
    )
    monkeypatch.setattr(preview, "converter_available", lambda: True)
    assert preview.preview_kind("a.vsdx", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.dwg", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.dxf", None) == preview.PREVIEW_PDF
    assert preview.preview_kind("a.zip", None) is None


def test_http_converter_posts_file_and_requires_pdf(monkeypatch):
    _preview_settings(
        monkeypatch,
        preview_converter="http",
        preview_converter_url="http://adapter.local/convert",
        preview_converter_token="secret",
    )
    seen = {}

    class FakeResponse:
        headers = {"Content-Type": "application/pdf"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return b"%PDF-1.4\nadapter\n%%EOF"

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = request.data
        seen["filename"] = request.headers.get("X-filename")
        seen["auth"] = request.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(preview.urllib.request, "urlopen", fake_urlopen)
    pdf = preview.convert_to_pdf(io.BytesIO(b"AC1015-dwg"), "图纸.dwg")
    assert pdf.startswith(b"%PDF")
    assert seen == {
        "url": "http://adapter.local/convert",
        "body": b"AC1015-dwg",
        "filename": quote("图纸.dwg", safe=""),
        "auth": "Bearer secret",
    }


def test_preview_filename_marks_converted_files_as_pdf():
    assert preview.preview_filename("方案.docx", preview.PREVIEW_PDF) == "方案.pdf"
    assert preview.preview_filename("图纸.dwg", preview.PREVIEW_PDF) == "图纸.pdf"
    assert preview.preview_filename("方案.pdf", preview.PREVIEW_PDF) == "方案.pdf"
    assert preview.preview_filename("图.png", preview.PREVIEW_IMAGE) == "图.png"


def test_inline_headers_are_safe():
    headers = preview.inline_headers("方案 1.pdf")
    assert headers["Content-Disposition"].startswith("inline;")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in headers["Content-Security-Policy"]
