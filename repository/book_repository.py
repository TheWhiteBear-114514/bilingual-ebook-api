"""书籍数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Book


def get(db: Session, book_id: int) -> Book | None:
    return db.get(Book, book_id)


def list_by_user(db: Session, user_id: int, offset: int = 0, limit: int = 12) -> list[Book]:
    return list(
        db.execute(
            select(Book).where(Book.user_id == user_id)
            .order_by(Book.created_at.desc(), Book.id.desc())
            .offset(offset).limit(limit)
        ).scalars()
    )


def count_by_user(db: Session, user_id: int) -> int:
    return db.execute(select(func.count(Book.id)).where(Book.user_id == user_id)).scalar_one()


def list_all(db: Session) -> list[Book]:
    return list(db.execute(select(Book).order_by(Book.created_at.desc(), Book.id.desc())).scalars())
