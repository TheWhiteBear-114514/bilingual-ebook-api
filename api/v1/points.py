"""积分：余额、明细、签到、兑换比例。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import get_db
from core.permissions import ApiError, get_current_user
from models import Checkin, PointLog, User
from schemas import CheckinOut, PagedPointLogs, PointLogOut, PointsOut
from service.points import earn, get_config
from utils.response import ok, page_params

router = APIRouter(tags=["积分"])


@router.get("/points", summary="积分余额")
def balance(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rate = int(get_config(db, "token_per_point", "1000") or 1000)
    return ok(PointsOut(points=user.points, rate=rate).model_dump())


@router.get("/points/rate", summary="积分兑换比例")
def rate(db: Session = Depends(get_db)):
    return ok({"token_per_point": int(get_config(db, "token_per_point", "1000") or 1000)})


@router.get("/points/logs", summary="积分明细")
def logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p, s = page_params(page, size, 20)
    total = db.execute(
        select(func.count(PointLog.id)).where(PointLog.user_id == user.id)
    ).scalar_one()
    rows = db.execute(
        select(PointLog)
        .where(PointLog.user_id == user.id)
        .order_by(PointLog.created_at.desc(), PointLog.id.desc())
        .offset((p - 1) * s)
        .limit(s)
    ).scalars().all()
    data = PagedPointLogs(
        total=total, page=p, size=s, items=[PointLogOut.model_validate(r) for r in rows]
    )
    return ok(data.model_dump(mode="json"))


@router.post("/points/checkin", summary="每日签到")
def checkin(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    exists = db.execute(
        select(Checkin).where(Checkin.user_id == user.id, Checkin.checkin_date == today)
    ).scalar_one_or_none()
    if exists:
        raise ApiError(409, "今天已经签到过了", 409)

    reward = int(get_config(db, "checkin_reward", "10") or 10)
    db.add(
        Checkin(
            user_id=user.id,
            checkin_date=today,
            reward=reward,
            created_at=datetime.now(),
        )
    )
    earn(db, user, reward, "checkin", "每日签到")
    db.commit()
    return ok(CheckinOut(points=user.points, reward=reward).model_dump())
