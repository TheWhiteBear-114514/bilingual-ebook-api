"""全局配置：全部来自环境变量，带可用默认值。

不引入 pydantic-settings，减少依赖；读取项目根目录的 .env（如果存在）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_name: str = "双语电子书生成系统 API"
    version: str = "1.6.0"
    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "dev"))

    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./storage/book.db")
    )

    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY", "dev-secret-change-me")
    )
    jwt_expire_days: int = field(default_factory=lambda: int(os.getenv("JWT_EXPIRE_DAYS", "7")))
    jwt_algorithm: str = "HS256"

    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", "./storage/uploads")))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./storage/output")))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "10")))

    translator_mode: str = field(default_factory=lambda: os.getenv("TRANSLATOR_MODE", "mock"))
    official_api_key: str = field(default_factory=lambda: os.getenv("OFFICIAL_API_KEY", ""))
    official_api_enabled: bool = field(default_factory=lambda: _bool("OFFICIAL_API_ENABLED", True))
    token_per_point: int = field(default_factory=lambda: int(os.getenv("TOKEN_PER_POINT", "1000")))

    demo_segment_delay: float = field(
        default_factory=lambda: float(os.getenv("DEMO_SEGMENT_DELAY", "0.15"))
    )

    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ]
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()

# 确保目录存在
for _p in (settings.upload_dir, settings.output_dir):
    _p.mkdir(parents=True, exist_ok=True)
