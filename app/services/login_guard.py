"""登录失败锁定。

账号锁定落在用户行上，多进程共用数据库也生效。同一 IP 的尝试次数记在
进程内存里，用来拖慢对不存在账号的喷洒；多副本时这层只覆盖本进程。
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Dict, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.user import User

_ip_hits: Dict[str, List[float]] = {}
_unknown_hits: Dict[str, List[float]] = {}


def _prune(hits: List[float], now: float, window: int) -> List[float]:
    cutoff = now - window
    return [item for item in hits if item >= cutoff]


def _too_many() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="尝试次数过多，请稍后再试",
    )


def assert_ip_allowed(ip: str) -> None:
    now = time.time()
    hits = _prune(_ip_hits.get(ip, []), now, settings.login_ip_window_seconds)
    _ip_hits[ip] = hits
    if len(hits) >= settings.login_ip_max_attempts:
        raise _too_many()


def note_ip(ip: str) -> None:
    now = time.time()
    hits = _prune(_ip_hits.get(ip, []), now, settings.login_ip_window_seconds)
    hits.append(now)
    _ip_hits[ip] = hits


def assert_account_unlocked(user: User) -> None:
    if user.locked_until is not None and user.locked_until > utcnow():
        raise _too_many()


def record_failure(db: Session, user: User) -> bool:
    """记一次失败。达到阈值时锁定并返回 True。"""
    user.failed_login_count = int(user.failed_login_count or 0) + 1
    locked = user.failed_login_count >= settings.login_max_failures
    if locked:
        user.locked_until = utcnow() + timedelta(seconds=settings.login_lockout_seconds)
    db.commit()
    return locked


def record_unknown(ip: str, username: str) -> bool:
    """不存在的账号也按同一阈值返回锁定，避免用状态码枚举用户名。"""
    now = time.time()
    key = f"{ip}|{username.strip().lower()}"
    hits = _prune(_unknown_hits.get(key, []), now, settings.login_lockout_seconds)
    hits.append(now)
    _unknown_hits[key] = hits
    return len(hits) >= settings.login_max_failures


def record_success(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.commit()
