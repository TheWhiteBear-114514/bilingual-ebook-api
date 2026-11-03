"""积分账务：统一入口，保证 users.points 与 point_logs 在同一事务内一致。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import PointLog, SystemConfig, User


def get_config(db: Session, key: str, default: str = "") -> str:
    row = db.get(SystemConfig, key)
    return row.value if row else default


def set_config(db: Session, key: str, value: str) -> None:
    row = db.get(SystemConfig, key)
    if row:
        row.value = value
    else:
        db.add(SystemConfig(key=key, value=value))


def _write_log(
    db: Session,
    user: User,
    delta: int,
    log_type: str,
    description: str,
    ref_id: int | None = None,
) -> PointLog:
    user.points += delta
    log = PointLog(
        user_id=user.id,
        delta=delta,
        balance_after=user.points,
        type=log_type,
        ref_id=ref_id,
        description=description,
    )
    db.add(log)
    return log


def earn(
    db: Session,
    user: User,
    amount: int,
    log_type: str,
    description: str,
    ref_id: int | None = None,
) -> PointLog:
    return _write_log(db, user, abs(int(amount)), log_type, description, ref_id)


def spend(
    db: Session,
    user: User,
    amount: int,
    description: str,
    ref_id: int | None = None,
    log_type: str = "translate",
) -> PointLog:
    return _write_log(db, user, -abs(int(amount)), log_type, description, ref_id)


def official_cost(db: Session, char_count: int) -> int:
    """官方引擎计费：按字符估算 tokens，再按兑换比例折算积分。"""
    per = int(get_config(db, "token_per_point", "1000") or 1000)
    tokens = max(1, int(char_count * 0.35))
    return max(1, -(-tokens // per))


def points_used_today(db: Session, user_id: int) -> int:
    from datetime import date, datetime, time

    start = datetime.combine(date.today(), time.min)
    rows = db.execute(
        select(PointLog.delta).where(
            PointLog.user_id == user_id,
            PointLog.delta < 0,
            PointLog.created_at >= start,
        )
    ).scalars().all()
    return abs(sum(rows))


def recent_spends(db: Session, user_id: int, limit: int = 20) -> list[PointLog]:
    return list(
        db.execute(
            select(PointLog)
            .where(PointLog.user_id == user_id, PointLog.delta < 0)
            .order_by(PointLog.id.desc())
            .limit(limit)
        ).scalars()
    )
