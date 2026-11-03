"""积分流水数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import PointLog


def list_by_user(db: Session, user_id: int, offset: int = 0, limit: int = 20) -> list[PointLog]:
    return list(
        db.execute(
            select(PointLog).where(PointLog.user_id == user_id)
            .order_by(PointLog.created_at.desc(), PointLog.id.desc())
            .offset(offset).limit(limit)
        ).scalars()
    )


def count_by_user(db: Session, user_id: int) -> int:
    return db.execute(select(func.count(PointLog.id)).where(PointLog.user_id == user_id)).scalar_one()
