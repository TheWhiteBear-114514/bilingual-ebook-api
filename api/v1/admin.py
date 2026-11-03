"""管理端接口（概览 / 用户 / 任务 / 缓存 / 引擎 / API / 积分 / 反馈 / 风控 / 公告 / 日志）。"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.database import get_db
from core.permissions import ApiError, require_admin
from models import (
    Book,
    Checkin,
    Feedback,
    Log,
    Notice,
    PointLog,
    RiskAlert,
    Segment,
    TranslationCache,
    User,
)
from api.v1.books import book_to_dict
from schemas import (
    AdjustPointsIn,
    BulkPointsIn,
    CacheOut,
    CacheStatsOut,
    ClearPointsIn,
    EngineOut,
    FeedbackAdminOut,
    FeedbackHandleIn,
    LogPage,
    LogOut,
    NoticeIn,
    NoticeOut,
    OfficialApiIn,
    OfficialApiOut,
    PointConfigIn,
    PointUserOut,
    ResetPasswordOut,
    RiskAlertOut,
    RiskConfigIn,
    RiskResolveIn,
    TaskAdminOut,
    UserOut,
)
from core.security import hash_password
from service.audit import audit
from service.pipeline import run_pipeline
from service.points import earn, get_config, set_config, spend
from service.translator import ENGINES
from utils.response import ok, page_params

router = APIRouter(prefix="/admin", tags=["管理端"], dependencies=[Depends(require_admin)])


# ----------------------------- 概览 -----------------------------
@router.get("/dashboard", summary="概览")
def dashboard(db: Session = Depends(get_db)):
    today = date.today()
    users_total = db.execute(select(func.count(User.id))).scalar_one()
    users_active = db.execute(select(func.count(User.id)).where(User.is_active == 1)).scalar_one()
    books_total = db.execute(select(func.count(Book.id))).scalar_one()
    tasks_running = db.execute(
        select(func.count(Book.id)).where(Book.status.in_(["pending", "processing"]))
    ).scalar_one()

    today_chars = db.execute(
        select(func.coalesce(func.sum(Book.char_count), 0)).where(func.date(Book.created_at) == today.isoformat())
    ).scalar_one()

    cache_hits = db.execute(select(func.coalesce(func.sum(TranslationCache.hit_count), 0))).scalar_one()
    seg_total = db.execute(select(func.count(Segment.id))).scalar_one()
    cached_total = db.execute(select(func.coalesce(func.sum(Book.cached_segments), 0))).scalar_one()
    hit_rate = round(cached_total / seg_total * 100, 1) if seg_total else 0.0

    risk_pending = db.execute(
        select(func.count(RiskAlert.id)).where(RiskAlert.status == "pending")
    ).scalar_one()

    last7 = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = db.execute(
            select(func.count(Book.id)).where(func.date(Book.created_at) == day.isoformat())
        ).scalar_one()
        last7.append({"date": day.strftime("%m-%d"), "count": count})

    engines = []
    for e in ENGINES:
        calls = db.execute(
            select(func.count(Book.id)).where(
                Book.engine == e.id, func.date(Book.created_at) == today.isoformat()
            )
        ).scalar_one()
        failed = db.execute(
            select(func.count(Book.id)).where(
                Book.engine == e.id,
                Book.status == "failed",
                func.date(Book.created_at) == today.isoformat(),
            )
        ).scalar_one()
        engines.append(
            {
                "id": e.id,
                "name": e.name,
                "official": e.official,
                "key_fields": e.key_fields,
                "enabled": get_config(db, "official_api_enabled", "1") == "1" if e.official else True,
                "calls": calls,
                "char_count": 0,
                "fail_rate": round(failed / calls * 100, 1) if calls else 0.0,
            }
        )

    latest_rows = db.execute(
        select(Book).order_by(Book.created_at.desc(), Book.id.desc()).limit(8)
    ).scalars().all()
    latest = []
    for b in latest_rows:
        owner = db.get(User, b.user_id)
        latest.append(
            {
                "id": b.id,
                "title": b.title,
                "user": owner.email if owner else "-",
                "pair": f"{b.source_lang}-{b.target_lang}".upper(),
                "status": b.status,
                "created_at": b.created_at,
            }
        )

    return ok(
        {
            "users": users_total,
            "users_active": users_active,
            "books": books_total,
            "tasks_running": tasks_running,
            "today_chars": int(today_chars or 0),
            "cache_hit_rate": hit_rate,
            "cache_hits": int(cache_hits or 0),
            "risk_pending": risk_pending,
            "last7": last7,
            "engines": engines,
            "latest": latest,
        }
    )


# ----------------------------- 用户 -----------------------------
@router.get("/users", summary="用户列表")
def list_users(
    search: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(User).order_by(User.created_at.desc())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.like(like), User.nickname.like(like)))
    rows = db.execute(stmt).scalars().all()
    items = [UserOut.model_validate(u).model_dump(mode="json") for u in rows]
    return ok({"total": len(items), "items": items})


@router.put("/users/{user_id}/status", summary="启用 / 禁用用户")
def toggle_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", 404)
    if user.role == "admin":
        raise ApiError(400, "不能禁用管理员账号")

    user.is_active = not user.is_active
    user.ban_reason = None if user.is_active else (user.ban_reason or "管理员手动禁用")
    audit(db, "INFO", "user", f"{user.email} 被{'启用' if user.is_active else '禁用'}（操作人 {admin.email}）")
    db.commit()
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.post("/users/{user_id}/reset-password", summary="重置密码")
def reset_password(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", 404)

    temp = f"Tmp{secrets.token_hex(4)}"
    user.password_hash = hash_password(temp)
    audit(db, "WARN", "user", f"重置 {user.email} 的密码（操作人 {admin.email}）")
    db.commit()
    return ok(ResetPasswordOut(temp_password=temp).model_dump())


@router.delete("/users/{user_id}", summary="删除用户")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "用户不存在", 404)
    if user.role == "admin":
        raise ApiError(400, "不能删除管理员账号")

    audit(db, "WARN", "user", f"删除用户 {user.email}（操作人 {admin.email}）")
    db.delete(user)
    db.commit()
    return ok(True)


# ----------------------------- 任务 -----------------------------
@router.get("/tasks", summary="任务列表")
def list_tasks(
    status: str = "all",
    search: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(Book).order_by(Book.created_at.desc(), Book.id.desc())
    if status and status != "all":
        stmt = stmt.where(Book.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Book.title.like(like))

    rows = db.execute(stmt).scalars().all()
    items = []
    for b in rows:
        data = book_to_dict(b)
        owner = db.get(User, b.user_id)
        data["user"] = owner.email if owner else "-"
        items.append(TaskAdminOut(**data).model_dump(mode="json"))
    return ok({"total": len(items), "items": items})


@router.post("/tasks/{book_id}/cancel", summary="取消任务")
def cancel_task(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError(404, "任务不存在", 404)
    if book.status not in ("pending", "processing"):
        raise ApiError(409, "只有进行中的任务可以取消", 409)

    book.status = "failed"
    book.error_msg = "已取消（管理员操作）"
    book.finished_at = datetime.now()
    audit(db, "WARN", "task", f"任务 {book.id} 被管理员取消")
    db.commit()
    return ok(book_to_dict(book))


@router.post("/tasks/{book_id}/retry", summary="重试任务")
def retry_task(book_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError(404, "任务不存在", 404)
    if book.status != "failed":
        raise ApiError(409, "只有失败任务可以重试", 409)
    if (book.error_msg or "").find("扫描") >= 0:
        raise ApiError(422, "解析类失败无法重试，请让用户重新上传文本型文件", 422)

    for seg in list(book.segments):
        db.delete(seg)
    book.status = "pending"
    book.progress = 0
    book.error_msg = None
    book.finished_at = None
    audit(db, "INFO", "task", f"任务 {book.id} 重新入队（管理员操作）")
    db.commit()

    background.add_task(run_pipeline, book.id, {})
    return ok(book_to_dict(book))


@router.delete("/tasks/{book_id}", summary="删除任务")
def delete_task(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError(404, "任务不存在", 404)
    audit(db, "WARN", "task", f"删除任务 {book.id}（{book.title}）")
    db.delete(book)
    db.commit()
    return ok(True)


# ----------------------------- 缓存 -----------------------------
@router.get("/cache", summary="缓存列表与统计")
def list_cache(
    search: str = "",
    db: Session = Depends(get_db),
):
    stmt = select(TranslationCache).order_by(TranslationCache.id.desc())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(TranslationCache.translated_text.like(like), TranslationCache.source_hash.like(like))
        )
    rows = db.execute(stmt).scalars().all()
    total = len(rows)
    hits = sum(r.hit_count for r in rows)
    seg_total = db.execute(select(func.count(Segment.id))).scalar_one()
    cached_total = db.execute(select(func.coalesce(func.sum(Book.cached_segments), 0))).scalar_one()
    rate = round(cached_total / seg_total * 100, 1) if seg_total else 0.0

    data = CacheStatsOut(
        total=total,
        hits=hits,
        hit_rate=rate,
        items=[CacheOut.model_validate(r) for r in rows],
    )
    return ok(data.model_dump(mode="json"))


@router.delete("/cache/{cache_id}", summary="删除单条缓存")
def delete_cache(cache_id: int, db: Session = Depends(get_db)):
    row = db.get(TranslationCache, cache_id)
    if row is None:
        raise ApiError(404, "缓存不存在", 404)
    db.delete(row)
    db.commit()
    return ok(True)


@router.delete("/cache", summary="清空缓存")
def clear_cache(db: Session = Depends(get_db)):
    count = db.execute(select(func.count(TranslationCache.id))).scalar_one()
    db.query(TranslationCache).delete()
    audit(db, "INFO", "cache", f"管理员清空翻译缓存（{count} 条）")
    db.commit()
    return ok(True)


# ----------------------------- 引擎 -----------------------------
@router.get("/engines", summary="引擎列表")
def list_engines(db: Session = Depends(get_db)):
    official_enabled = get_config(db, "official_api_enabled", "1") == "1"
    return ok(
        [
            EngineOut(
                id=e.id,
                name=e.name,
                official=e.official,
                key_fields=e.key_fields,
                enabled=official_enabled if e.official else True,
            ).model_dump()
            for e in ENGINES
        ]
    )


@router.put("/engines/{engine_id}/status", summary="启用 / 停用引擎")
def toggle_engine(engine_id: str, payload: dict, db: Session = Depends(get_db)):
    if engine_id not in {e.id for e in ENGINES}:
        raise ApiError(404, "引擎不存在", 404)
    if engine_id == "official":
        set_config(db, "official_api_enabled", "1" if payload.get("enabled") else "0")
    audit(db, "INFO", "engine", f"引擎 {engine_id} {'启用' if payload.get('enabled') else '停用'}")
    db.commit()
    return ok(True)


# ----------------------------- 官方 API -----------------------------
@router.get("/official-api", summary="官方 API 配置")
def get_official_api(db: Session = Depends(get_db)):
    key = get_config(db, "official_api_key", "")
    masked = ("sk-****" + key[-4:]) if key else "未配置"
    return ok(
        OfficialApiOut(
            official_api_enabled=get_config(db, "official_api_enabled", "1"),
            token_per_point=int(get_config(db, "token_per_point", "1000") or 1000),
            api_key_masked=masked,
        ).model_dump()
    )


@router.put("/official-api", summary="更新官方 API 配置")
def save_official_api(payload: OfficialApiIn, db: Session = Depends(get_db)):
    if payload.official_api_enabled is not None:
        set_config(db, "official_api_enabled", "1" if payload.official_api_enabled else "0")
    if payload.official_api_key:
        set_config(db, "official_api_key", payload.official_api_key)
    if payload.token_per_point is not None:
        set_config(db, "token_per_point", str(payload.token_per_point))
    audit(db, "INFO", "official", "更新官方 API 配置")
    db.commit()
    return ok(True)


# ----------------------------- 积分 -----------------------------
@router.get("/points", summary="用户积分列表")
def list_points(search: str = "", db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    if search:
        stmt = stmt.where(User.email.like(f"%{search.strip()}%"))
    rows = db.execute(stmt).scalars().all()
    items = []
    for u in rows:
        count = db.execute(
            select(func.count(PointLog.id)).where(PointLog.user_id == u.id)
        ).scalar_one()
        data = UserOut.model_validate(u).model_dump(mode="json")
        items.append(PointUserOut(**data, log_count=count).model_dump(mode="json"))
    return ok({"total": len(items), "items": items})


@router.post("/points/adjust", summary="调整单个用户积分")
def adjust_points(payload: AdjustPointsIn, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if user is None:
        raise ApiError(404, "用户不存在", 404)
    if payload.delta == 0:
        raise ApiError(400, "调整值不能为 0")

    if payload.delta > 0:
        earn(db, user, payload.delta, "admin_adjust", payload.reason)
    else:
        spend(db, user, abs(payload.delta), payload.reason, log_type="admin_adjust")

    audit(db, "INFO", "point", f"管理员调整 {user.email} 积分 {payload.delta:+d}")
    db.commit()
    return ok({"points": user.points})


@router.post("/points/clear", summary="清空用户积分")
def clear_points(payload: ClearPointsIn, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if user is None:
        raise ApiError(404, "用户不存在", 404)
    if user.points:
        spend(db, user, user.points, "管理员清空积分", log_type="admin_adjust")
    db.commit()
    return ok({"points": user.points})


@router.post("/points/bulk", summary="批量发放积分")
def bulk_points(payload: BulkPointsIn, db: Session = Depends(get_db)):
    users = db.execute(select(User).where(User.role == "user")).scalars().all()
    if payload.delta == 0:
        raise ApiError(400, "调整值不能为 0")
    for u in users:
        if payload.delta > 0:
            earn(db, u, payload.delta, "admin_bulk", payload.reason)
        else:
            spend(db, u, abs(payload.delta), payload.reason, log_type="admin_bulk")
    audit(db, "INFO", "point", f"管理员批量发放 {payload.delta:+d} 给 {len(users)} 名用户")
    db.commit()
    return ok({"affected": len(users)})


@router.put("/points/config", summary="积分规则配置")
def save_point_config(payload: PointConfigIn, db: Session = Depends(get_db)):
    if payload.checkin_reward is not None:
        set_config(db, "checkin_reward", str(payload.checkin_reward))
    if payload.register_reward is not None:
        set_config(db, "register_reward", str(payload.register_reward))
    if payload.token_per_point is not None:
        set_config(db, "token_per_point", str(payload.token_per_point))
    db.commit()
    return ok(True)


# ----------------------------- 反馈 -----------------------------
@router.get("/feedback", summary="反馈列表")
def list_feedback(status: str = "all", db: Session = Depends(get_db)):
    stmt = select(Feedback).order_by(Feedback.created_at.desc())
    if status and status != "all":
        stmt = stmt.where(Feedback.status == status)
    rows = db.execute(stmt).scalars().all()
    items = []
    for f in rows:
        owner = db.get(User, f.user_id)
        data = FeedbackAdminOut.model_validate(f).model_dump(mode="json")
        data["user_email"] = owner.email if owner else "-"
        items.append(data)
    return ok({"total": len(items), "items": items})


@router.post("/feedback/{feedback_id}/handle", summary="处理反馈")
def handle_feedback(feedback_id: int, payload: FeedbackHandleIn, db: Session = Depends(get_db)):
    fb = db.get(Feedback, feedback_id)
    if fb is None:
        raise ApiError(404, "反馈不存在", 404)
    user = db.get(User, fb.user_id)

    if user is not None:
        if payload.action == "reward":
            earn(db, user, payload.amount, "feedback_reward", f"反馈奖励：{fb.title}", fb.id)
            fb.reward = payload.amount
        elif payload.action == "penalty":
            spend(db, user, payload.amount, f"反馈扣分：{fb.title}", fb.id, "feedback_penalty")
        elif payload.action == "ban":
            user.is_active = False
            user.ban_reason = "反馈处理"

    fb.status = "done"
    fb.handled_at = datetime.now()
    audit(db, "INFO", "feedback", f"处理反馈 #{fb.id}：{payload.action}")
    db.commit()
    return ok(FeedbackOut.model_validate(fb).model_dump(mode="json"))


# ----------------------------- 风控 -----------------------------
@router.get("/risk/alerts", summary="风控告警列表")
def risk_alerts(status: str = "all", db: Session = Depends(get_db)):
    stmt = select(RiskAlert).order_by(RiskAlert.created_at.desc())
    if status and status != "all":
        stmt = stmt.where(RiskAlert.status == status)
    rows = db.execute(stmt).scalars().all()
    items = []
    for r in rows:
        owner = db.get(User, r.user_id)
        data = RiskAlertOut.model_validate(r).model_dump(mode="json")
        data["user_email"] = owner.email if owner else "-"
        data["user_active"] = bool(owner.is_active) if owner else None
        items.append(data)
    return ok({"total": len(items), "items": items})


@router.put("/risk/config", summary="风控阈值配置")
def save_risk_config(payload: RiskConfigIn, db: Session = Depends(get_db)):
    if payload.risk_max_single is not None:
        set_config(db, "risk_max_single", str(payload.risk_max_single))
    if payload.risk_max_freq is not None:
        set_config(db, "risk_max_freq", str(payload.risk_max_freq))
    if payload.risk_max_daily is not None:
        set_config(db, "risk_max_daily", str(payload.risk_max_daily))
    audit(db, "INFO", "risk", "更新风控阈值配置")
    db.commit()
    return ok(True)


@router.post("/risk/{alert_id}/resolve", summary="复核告警")
def resolve_risk(alert_id: int, payload: RiskResolveIn, db: Session = Depends(get_db)):
    alert = db.get(RiskAlert, alert_id)
    if alert is None:
        raise ApiError(404, "告警不存在", 404)
    if alert.status != "pending":
        raise ApiError(409, "该告警已处理", 409)

    user = db.get(User, alert.user_id)
    if user is not None:
        if payload.resolve == "unban":
            user.is_active = True
            user.ban_reason = None
        else:
            user.is_active = False
            user.ban_reason = "积分风控"
            if payload.penalty > 0:
                spend(db, user, payload.penalty, "风控确认扣分", alert.id, "risk_penalty")

    alert.status = "resolved"
    alert.resolve = payload.resolve
    alert.handled_at = datetime.now()
    audit(db, "WARN", "risk", f"告警 #{alert.id} 复核结果：{payload.resolve}")
    db.commit()
    return ok(RiskAlertOut.model_validate(alert).model_dump(mode="json"))


# ----------------------------- 公告 -----------------------------
@router.get("/notices", summary="公告列表（含停用）")
def admin_notices(db: Session = Depends(get_db)):
    rows = db.execute(select(Notice).order_by(Notice.created_at.desc())).scalars().all()
    return ok([NoticeOut.model_validate(n).model_dump(mode="json") for n in rows])


@router.post("/notices", summary="发布公告")
def create_notice(payload: NoticeIn, db: Session = Depends(get_db)):
    notice = Notice(
        type=payload.type,
        title=payload.title.strip(),
        body=payload.body.strip(),
        is_active=True,
        views=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(notice)
    audit(db, "INFO", "notice", f"发布公告「{notice.title}」")
    db.commit()
    return ok(NoticeOut.model_validate(notice).model_dump(mode="json"))


@router.put("/notices/{notice_id}", summary="编辑公告")
def update_notice(notice_id: int, payload: NoticeIn, db: Session = Depends(get_db)):
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise ApiError(404, "公告不存在", 404)
    notice.type = payload.type
    notice.title = payload.title.strip()
    notice.body = payload.body.strip()
    notice.updated_at = datetime.now()
    audit(db, "INFO", "notice", f"编辑公告「{notice.title}」")
    db.commit()
    return ok(NoticeOut.model_validate(notice).model_dump(mode="json"))


@router.put("/notices/{notice_id}/status", summary="启用 / 停用公告")
def toggle_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise ApiError(404, "公告不存在", 404)
    notice.is_active = not notice.is_active
    notice.updated_at = datetime.now()
    audit(db, "INFO", "notice", f"公告「{notice.title}」{'启用' if notice.is_active else '停用'}")
    db.commit()
    return ok(NoticeOut.model_validate(notice).model_dump(mode="json"))


@router.delete("/notices/{notice_id}", summary="删除公告")
def delete_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise ApiError(404, "公告不存在", 404)
    audit(db, "WARN", "notice", f"删除公告「{notice.title}」")
    db.delete(notice)
    db.commit()
    return ok(True)


# ----------------------------- 日志 -----------------------------
@router.get("/logs", summary="系统日志")
def list_logs(
    level: str = "all",
    q: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Log).order_by(Log.created_at.desc(), Log.id.desc())
    if level and level != "all":
        stmt = stmt.where(Log.level == level)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Log.message.like(like), Log.module.like(like)))

    p, s = page_params(page, size, 100)
    total = len(db.execute(stmt).scalars().all())
    rows = db.execute(stmt.offset((p - 1) * s).limit(s)).scalars().all()
    data = LogPage(total=total, items=[LogOut.model_validate(r) for r in rows])
    return ok(data.model_dump(mode="json"))
