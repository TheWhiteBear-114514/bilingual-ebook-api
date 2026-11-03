"""路由注册。"""
from __future__ import annotations

from fastapi import FastAPI

from api.v1 import admin, auth, books, feedback, meta, points
from config.config_unified import settings
from utils.response import ok


def register_routes(app: FastAPI) -> None:
    for router in (auth.router, meta.router, books.router, points.router, feedback.router, admin.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health", tags=["系统"], summary="健康检查")
    def health():
        return ok({"status": "ok", "version": settings.version, "env": settings.env})
