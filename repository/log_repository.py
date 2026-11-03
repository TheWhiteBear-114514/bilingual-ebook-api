"""系统日志数据访问。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import Log


def list_filtered(db: Session, level: str = "all", q: str = "", limit: int = 100) -> list[Log]:
    stmt = select(Log).order_by(Log.created_at.desc(), Log.id.desc())
    if level and level != "all":
        stmt = stmt.where(Log.level == level)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Log.message.like(like), Log.module.like(like)))
    return list(db.execute(stmt.limit(limit)).scalars())
