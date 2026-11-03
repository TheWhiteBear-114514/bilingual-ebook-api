"""公告数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Notice


def list_active(db: Session) -> list[Notice]:
    return list(
        db.execute(select(Notice).where(Notice.is_active == 1).order_by(Notice.created_at.desc())).scalars()
    )


def list_all(db: Session) -> list[Notice]:
    return list(db.execute(select(Notice).order_by(Notice.created_at.desc())).scalars())


def get(db: Session, notice_id: int) -> Notice | None:
    return db.get(Notice, notice_id)
