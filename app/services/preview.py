"""附件预览：原生内联 + 可选的 Office → PDF 转换。

预览分两层：
- 原生层（零依赖）：PDF、图片、纯文本直接以 `inline` 返回；
- 转换层（P1，可选）：配置 `PREVIEW_CONVERTER=libreoffice` 且镜像内有 `soffice` 时，
  把 docx/xlsx/pptx 转成 PDF 后内联；Visio/CAD 仍走下载，后续接 ODA/APS。

转换结果按源文件 SHA-256 缓存在存储层，同一版本只转一次。
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Dict, Optional
from urllib.parse import quote

from app.core.config import settings

PREVIEW_PDF = "PDF"
PREVIEW_IMAGE = "IMAGE"
PREVIEW_TEXT = "TEXT"

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_TEXT_EXTENSIONS = {".txt", ".csv", ".xml", ".bpmn", ".md"}
_TEXT_MIME_TYPES = {
    "application/xml",
    "application/csv",
    "text/csv",
    "text/plain",
    "text/xml",
}
# LibreOffice 能稳定转换的 Office 格式；vsdx/dwg 交给外部适配器，避免给出不可信预览。
_LIBREOFFICE_EXTENSIONS = {".docx", ".xlsx", ".xlsm", ".pptx"}
_EXTERNAL_EXTENSIONS = {".docx", ".xlsx", ".xlsm", ".pptx", ".vsdx", ".dwg", ".dxf"}
_CACHE_PREFIX = "previews/v1"


class PreviewConversionError(RuntimeError):
    """转换服务不可用或转换失败；API 层转成 502。"""


@lru_cache(maxsize=1)
def _soffice_binary() -> Optional[str]:
    return shutil.which("soffice") or shutil.which("libreoffice")


def converter_available() -> bool:
    mode = settings.preview_converter
    if mode == "libreoffice":
        return _soffice_binary() is not None
    if mode == "http":
        return bool(settings.preview_converter_url)
    return False


def is_convertible(filename: Optional[str], mime_type: Optional[str] = None) -> bool:
    suffix = Path(filename or "").suffix.lower()
    if settings.preview_converter == "libreoffice":
        return suffix in _LIBREOFFICE_EXTENSIONS
    if settings.preview_converter == "http":
        return suffix in _EXTERNAL_EXTENSIONS
    return False


def preview_kind(filename: Optional[str], mime_type: Optional[str]) -> Optional[str]:
    """返回最终以什么形式预览：PDF / IMAGE / TEXT；不支持时返回 None。"""
    suffix = Path(filename or "").suffix.lower()
    mime = (mime_type or "").lower()
    if suffix == ".pdf" or mime == "application/pdf":
        return PREVIEW_PDF
    if suffix in _IMAGE_EXTENSIONS or mime.startswith("image/"):
        return PREVIEW_IMAGE
    if suffix in _TEXT_EXTENSIONS or mime in _TEXT_MIME_TYPES or mime.startswith("text/"):
        return PREVIEW_TEXT
    if is_convertible(filename, mime_type) and converter_available():
        return PREVIEW_PDF
    return None


def preview_media_type(kind: str, mime_type: Optional[str], filename: Optional[str]) -> str:
    if kind == PREVIEW_PDF:
        return "application/pdf"
    if kind == PREVIEW_IMAGE:
        if mime_type and mime_type.lower().startswith("image/"):
            return mime_type
        suffix = Path(filename or "").suffix.lower()
        return "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    return "text/plain; charset=utf-8"


def preview_filename(filename: Optional[str], kind: str) -> str:
    """转换后统一叫 .pdf；原生文件保留原名。"""
    name = filename or "preview"
    if kind == PREVIEW_PDF and Path(name).suffix.lower() != ".pdf":
        return Path(name).stem + ".pdf"
    return name


def inline_headers(filename: str) -> Dict[str, str]:
    """预览响应头：内联展示，但仍禁止 MIME 嗅探和跨站嵌入。"""
    return {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
    }


def cache_key(checksum: Optional[str], storage_key: str) -> str:
    fingerprint = checksum or hashlib.sha256(storage_key.encode()).hexdigest()
    return f"{_CACHE_PREFIX}/{fingerprint}.pdf"


def convert_to_pdf(source: BinaryIO, filename: str) -> bytes:
    """把源文件转成 PDF。测试会 monkeypatch 这个函数。"""
    if settings.preview_converter == "http":
        return _convert_via_http(source, filename)
    binary = _soffice_binary()
    if binary is None:
        raise PreviewConversionError("未安装 LibreOffice（soffice）")
    suffix = Path(filename).suffix.lower() or ".docx"
    with tempfile.TemporaryDirectory(prefix="pms-preview-") as tmp:
        workdir = Path(tmp)
        source_path = workdir / ("source" + suffix)
        with source_path.open("wb") as out:
            shutil.copyfileobj(source, out)
        outdir = workdir / "out"
        outdir.mkdir()
        env = {**os.environ, "HOME": tmp, "TMPDIR": tmp}
        try:
            result = subprocess.run(
                [
                    binary,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(outdir),
                    str(source_path),
                ],
                capture_output=True,
                timeout=settings.preview_convert_timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PreviewConversionError("转换超时") from exc
        output = outdir / "source.pdf"
        if not output.is_file():
            detail = (result.stderr or result.stdout or b"").decode("utf-8", "ignore")
            detail = detail.strip().splitlines()[-1] if detail.strip() else "未生成 PDF"
            raise PreviewConversionError(f"转换失败：{detail}")
        return output.read_bytes()


def _convert_via_http(source: BinaryIO, filename: str) -> bytes:
    """把文件 POST 给外部转换适配器（ODA/APS/自建服务），返回 PDF 字节。

    适配器契约：
    - 请求：原始文件字节；`Content-Type: application/octet-stream`；
      `X-Filename` 为 URL 编码后的文件名；可选 `Authorization: Bearer <token>`；
    - 响应：`Content-Type: application/pdf`，正文为 PDF。
    """
    url = settings.preview_converter_url
    if not url:
        raise PreviewConversionError("未配置 PREVIEW_CONVERTER_URL")
    request = urllib.request.Request(
        url,
        data=source.read(),
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "Accept": "application/pdf",
            "X-Filename": quote(filename or "upload", safe=""),
        },
    )
    if settings.preview_converter_token:
        request.add_header("Authorization", "Bearer " + settings.preview_converter_token)
    try:
        with urllib.request.urlopen(
            request, timeout=settings.preview_convert_timeout_seconds
        ) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            max_bytes = settings.preview_convert_max_mb * 1024 * 1024
            pdf = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise PreviewConversionError(f"转换服务返回 {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PreviewConversionError("转换服务不可达或超时") from exc
    if not content_type.startswith("application/pdf") or not pdf.startswith(b"%PDF"):
        raise PreviewConversionError("转换服务没有返回 PDF")
    return pdf


def ensure_pdf_preview(
    storage,
    storage_key: str,
    checksum: Optional[str],
    filename: Optional[str],
) -> BinaryIO:
    """返回转换后的 PDF 流；命中缓存时不重复转换。"""
    key = cache_key(checksum, storage_key)
    if storage.exists(key):
        return storage.open(key)
    with storage.open(storage_key) as source:
        pdf_bytes = convert_to_pdf(source, filename or "preview.docx")
    max_bytes = settings.preview_convert_max_mb * 1024 * 1024
    if len(pdf_bytes) > max_bytes:
        raise PreviewConversionError(
            f"转换结果超过大小上限（{settings.preview_convert_max_mb} MB）"
        )
    storage.save(key, io.BytesIO(pdf_bytes), max_bytes)
    return storage.open(key)
