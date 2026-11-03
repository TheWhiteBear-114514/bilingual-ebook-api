"""数据库引擎与会话。

关键点：SQLite 的 PRAGMA foreign_keys 是「按连接」生效的，
必须用 connect 事件在每个连接上开启，否则 ON DELETE CASCADE 静默失效。
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.config_unified import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import sqlite3
from pathlib import Path

from sqlalchemy import inspect

from config.config_unified import ROOT


# ---------------- 建库与种子 ----------------
SCHEMA_FILE = ROOT / "database" / "database.sql"


def _sqlite_path() -> Path | None:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        return None
    raw = url.replace("sqlite:///", "", 1)
    p = Path(raw)
    return p if p.is_absolute() else (ROOT / raw).resolve()


def init_db() -> None:
    sqlite_path = _sqlite_path()

    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(sqlite_path)
        try:
            exists = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            if not exists:
                if SCHEMA_FILE.exists():
                    con.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
                    con.commit()
                else:  # 兜底：ORM 建表（无种子数据）
                    Base.metadata.create_all(bind=engine)
        finally:
            con.close()
        return

    Base.metadata.create_all(bind=engine)


def tables_ready() -> bool:
    return inspect(engine).has_table("users")
