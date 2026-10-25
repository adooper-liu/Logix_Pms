"""附件预览：只对浏览器能安全内联展示的格式开放。

P0 不做服务端格式转换：
- PDF、图片、纯文本直接以 `inline` 返回；
- Office/Visio/CAD 暂不预览，前端提示下载，后续接 LibreOffice/ODA 转换服务。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote

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


def preview_kind(filename: Optional[str], mime_type: Optional[str]) -> Optional[str]:
    """返回 PDF / IMAGE / TEXT；不支持时返回 None。"""
    suffix = Path(filename or "").suffix.lower()
    mime = (mime_type or "").lower()
    if suffix == ".pdf" or mime == "application/pdf":
        return PREVIEW_PDF
    if suffix in _IMAGE_EXTENSIONS or mime.startswith("image/"):
        return PREVIEW_IMAGE
    if suffix in _TEXT_EXTENSIONS or mime in _TEXT_MIME_TYPES or mime.startswith("text/"):
        return PREVIEW_TEXT
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


def inline_headers(filename: str) -> Dict[str, str]:
    """预览响应头：内联展示，但仍禁止 MIME 嗅探和跨站嵌入。"""
    return {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
    }
