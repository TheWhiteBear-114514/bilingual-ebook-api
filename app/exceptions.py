"""统一异常处理：业务错误码 / 参数校验 / HTTP 异常。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.permissions import ApiError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "参数"
        message = f"{field} 不合法：{first.get('msg', '')}"
        return JSONResponse(status_code=422, content={"code": 400, "message": message, "data": None})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            content = {"code": detail["code"], "message": detail.get("message", ""), "data": None}
        else:
            content = {"code": exc.status_code, "message": str(detail), "data": None}
        return JSONResponse(status_code=exc.status_code, content=content)
