"""附件存储抽象：数据库只存元数据，文件落本地卷（生产可换 S3 实现）。

安全约束：
- `storage_key` 一律由服务端生成，原始文件名只用于展示，禁止拼进路径；
- 扩展名白名单 + 常见格式魔数校验，不信任客户端 `Content-Type`；
- 单文件大小上限；下载一律 `attachment` + `nosniff`，不在浏览器内联执行。
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO, Optional, Protocol, Tuple

from app.core.config import settings


class StorageError(ValueError):
    """文件不符合存储规则；API 层转成 400。"""


# 常见二进制格式的魔数；文本类（csv/txt/xml/bpmn）不做魔数校验。
_MAGIC: dict = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".xlsm": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".vsdx": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04",),
}

_MAX_FILENAME = 200


def validate_filename(filename: str, allowed_extensions: Tuple[str, ...]) -> str:
    """返回可安全展示的文件名（去掉任何路径成分）。"""
    # 浏览器可能带上 Windows 路径；统一按 / 切，只取最后一段
    base = os.path.basename((filename or "").replace("\\", "/")).strip()
    # 去掉控制字符，避免它们进入响应头或页面
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    if not base or base in {".", ".."}:
        raise StorageError("文件名不能为空")
    if len(base) > _MAX_FILENAME:
        raise StorageError(f"文件名过长（最多 {_MAX_FILENAME} 个字符）")
    suffix = Path(base).suffix.lower()
    if not suffix:
        raise StorageError("文件缺少扩展名")
    if suffix not in allowed_extensions:
        raise StorageError(f"不支持的文件类型：{suffix}")
    return base


def verify_magic(stream: BinaryIO, filename: str) -> None:
    """读取文件头校验魔数，然后复位指针。"""
    prefixes = _MAGIC.get(Path(filename).suffix.lower())
    if not prefixes:
        return
    head = stream.read(16)
    stream.seek(0)
    if not any(head.startswith(prefix) for prefix in prefixes):
        raise StorageError(f"文件内容与扩展名不符：{Path(filename).suffix}")


def build_key(prefix: str, filename: str) -> str:
    """服务端生成对象键：原始文件名不进路径，只用扩展名。"""
    suffix = Path(filename).suffix.lower()
    return f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"


class AttachmentStorage(Protocol):
    def save(self, key: str, stream: BinaryIO, max_bytes: int) -> Tuple[str, int]:
        """落盘并返回 (sha256, size)。"""

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """本地卷实现：先写临时文件并计算校验值，成功后原子 rename。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _resolve(self, key: str) -> Path:
        root = self.root.resolve()
        path = (root / key).resolve()
        if root != path and root not in path.parents:
            raise StorageError("非法的存储路径")
        return path

    def save(self, key: str, stream: BinaryIO, max_bytes: int) -> Tuple[str, int]:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        digest = hashlib.sha256()
        size = 0
        try:
            with tmp.open("wb") as out:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError(f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                    digest.update(chunk)
                    out.write(chunk)
            os.replace(tmp, path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return digest.hexdigest(), size

    def open(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()


_storage: Optional[LocalStorage] = None


def get_storage() -> LocalStorage:
    """按配置返回存储实现。测试会先改 ATTACHMENT_DIR 再导入 app。"""
    global _storage
    if _storage is None or str(_storage.root) != settings.attachment_dir:
        _storage = LocalStorage(Path(settings.attachment_dir))
    return _storage


def max_bytes() -> int:
    return settings.attachment_max_mb * 1024 * 1024
