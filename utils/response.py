"""统一响应包裹与分页工具。"""
from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict:
    return {"code": 0, "message": "ok", "data": data}


def page_params(page: int | None, size: int | None, default_size: int = 12) -> tuple[int, int]:
    p = max(1, int(page or 1))
    s = min(100, max(1, int(size or default_size)))
    return p, s
