"""审计日志助手：所有管理操作都写一行 logs。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Log


def audit(db: Session, level: str, module: str, message: str) -> None:
    db.add(Log(level=level, module=module, message=message))
