"""依赖注入：数据库会话、当前用户、管理员校验、统一异常。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.database import get_db
from models import User
from core.security import decode_token

bearer = HTTPBearer(auto_error=False)


class ApiError(HTTPException):
    """业务错误：HTTP 状态与 code 一起返回，前端按 code 提示。"""

    def __init__(self, code: int, message: str, http_status: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=http_status, detail={"code": code, "message": message})
        self.code = code
        self.message = message


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise ApiError(401, "未登录或登录已过期", status.HTTP_401_UNAUTHORIZED)
    payload = decode_token(credentials.credentials)
    if not payload:
        raise ApiError(401, "登录已过期，请重新登录", status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None:
        raise ApiError(401, "用户不存在", status.HTTP_401_UNAUTHORIZED)
    if not user.is_active:
        raise ApiError(403, f"账号已被禁用{'（' + user.ban_reason + '）' if user.ban_reason else ''}")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ApiError(403, "需要管理员权限", status.HTTP_403_FORBIDDEN)
    return user
