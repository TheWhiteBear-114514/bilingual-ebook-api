"""中间件注册：CORS / 安全头 / 访问审计。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.config_unified import settings
from middleware.audit_middleware import AuditMiddleware
from middleware.security_headers import SecurityHeadersMiddleware


def register_middlewares(app: FastAPI) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
