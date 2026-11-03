"""用户反馈：提交与查看自己的反馈。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from core.permissions import get_current_user
from models import Feedback, User
from schemas import FeedbackCreate, FeedbackOut
from service.audit import audit
from utils.response import ok

router = APIRouter(tags=["反馈"])


@router.post("/feedback", summary="提交反馈")
def submit(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fb = Feedback(
        user_id=user.id,
        type=payload.type,
        title=payload.title.strip(),
        body=payload.body.strip(),
        contact=(payload.contact or "").strip(),
        status="pending",
        reward=0,
        created_at=datetime.now(),
    )
    db.add(fb)
    audit(db, "INFO", "feedback", f"{user.email} 提交反馈「{fb.title}」")
    db.commit()
    return ok(FeedbackOut.model_validate(fb).model_dump(mode="json"))


@router.get("/feedback/my", summary="我的反馈")
def mine(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(
        select(Feedback)
        .where(Feedback.user_id == user.id)
        .order_by(Feedback.created_at.desc())
    ).scalars().all()
    return ok([FeedbackOut.model_validate(r).model_dump(mode="json") for r in rows])
