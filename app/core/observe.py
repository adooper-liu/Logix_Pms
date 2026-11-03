"""请求号、访问日志和进程内计数。

计数按方法和状态码聚合，避免把路径放进标签把基数打爆。多副本各自计数，
由采集端加总。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("logix.access")

_counts: Dict[Tuple[str, str], int] = {}


def record(method: str, status_code: int) -> None:
    key = (method.upper(), str(status_code))
    _counts[key] = _counts.get(key, 0) + 1


def render_metrics() -> str:
    lines = [
        "# HELP logix_http_requests_total HTTP responses since process start",
        "# TYPE logix_http_requests_total counter",
    ]
    for (method, status_code), count in sorted(_counts.items()):
        lines.append(
            f'logix_http_requests_total{{method="{method}",status="{status_code}"}} {count}'
        )
    if len(lines) == 2:
        lines.append('logix_http_requests_total{method="GET",status="0"} 0')
    return "\n".join(lines) + "\n"


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            record(request.method, 500)
            logger.exception(
                "request_id=%s %s %s failed", request_id, request.method, request.url.path
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        record(request.method, response.status_code)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
