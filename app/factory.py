"""应用工厂：创建 FastAPI 实例并装配各层。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.exceptions import register_exception_handlers
from app.middleware import register_middlewares
from app.routes import register_routes
from config.config_unified import settings
from core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logging.getLogger("app").info("数据库就绪：%s", settings.database_url)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="双语电子书生成系统 · 用户端 + 管理控制台 API",
        lifespan=lifespan,
    )
    register_middlewares(app)
    register_exception_handlers(app)
    register_routes(app)
    return app


app = create_app()
