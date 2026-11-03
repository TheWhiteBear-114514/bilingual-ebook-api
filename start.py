"""启动入口：python start.py"""
from __future__ import annotations

import uvicorn

from config.config_unified import settings

if __name__ == "__main__":
    uvicorn.run("app.factory:app", host=settings.host, port=settings.port, reload=True)
