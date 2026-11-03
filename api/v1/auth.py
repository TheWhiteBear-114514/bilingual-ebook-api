"""认证：注册 / 登录 / 当前用户 / 管理员登录。"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from core.permissions import ApiError, get_current_user
from models import Log, User
from schemas import LoginRequest, RegisterRequest, TokenOut, UserOut
from core.security import create_access_token, hash_password, verify_password
from service.points import earn, get_config
from utils.response import ok

router = APIRouter(tags=["认证"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _log(db: Session, level: str, module: str, message: str) -> None:
    db.add(Log(level=level, module=module, message=message))


@router.post("/auth/register", summary="注册")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "邮箱格式不正确")

    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise ApiError(409, "该邮箱已注册", 409)

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        nickname=(payload.nickname or email.split("@")[0]).strip(),
        points=0,
        role="user",
        is_active=True,
        created_at=datetime.now(),
        last_login_at=datetime.now(),
    )
    db.add(user)
    db.flush()

    reward = int(get_config(db, "register_reward", "50") or 50)
    earn(db, user, reward, "register", "新用户注册奖励")
    _log(db, "INFO", "auth", f"{email} 注册成功")

    token = create_access_token(user.id, user.role)
    return ok(TokenOut(token=token, user=UserOut.model_validate(user)).model_dump(mode="json"))


@router.post("/auth/login", summary="登录")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "邮箱或密码错误", 401)
    if not user.is_active:
        reason = f"（{user.ban_reason}）" if user.ban_reason else ""
        raise ApiError(403, f"账号已被禁用{reason}", 403)

    user.last_login_at = datetime.now()
    _log(db, "INFO", "auth", f"{user.email} 登录成功")
    db.commit()

    token = create_access_token(user.id, user.role)
    return ok(TokenOut(token=token, user=UserOut.model_validate(user)).model_dump(mode="json"))


@router.get("/auth/me", summary="当前登录用户")
def me(user: User = Depends(get_current_user)):
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.post("/admin/login", summary="管理员登录")
def admin_login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "管理员账号或密码错误", 401)
    if user.role != "admin":
        raise ApiError(403, "该账号不是管理员", 403)
    if not user.is_active:
        raise ApiError(403, "管理员账号已被禁用", 403)

    user.last_login_at = datetime.now()
    _log(db, "INFO", "auth", f"管理员 {user.email} 登录成功")
    db.commit()

    token = create_access_token(user.id, user.role)
    return ok(TokenOut(token=token, user=UserOut.model_validate(user)).model_dump(mode="json"))
