"""反馈数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Feedback


def list_by_user(db: Session, user_id: int) -> list[Feedback]:
    return list(
        db.execute(select(Feedback).where(Feedback.user_id == user_id).order_by(Feedback.created_at.desc())).scalars()
    )


def list_by_status(db: Session, status: str | None = None) -> list[Feedback]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc())
    if status and status != "all":
        stmt = stmt.where(Feedback.status == status)
    return list(db.execute(stmt).scalars())
