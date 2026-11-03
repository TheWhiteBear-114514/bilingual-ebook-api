"""访问审计中间件：记录方法、路径、状态码与耗时。"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from utils.logger import get_logger

logger = get_logger("access")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - started) * 1000
        if request.url.path.startswith("/api"):
            logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path, response.status_code, cost_ms)
        return response
