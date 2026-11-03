"""依赖注入出口：数据库会话与当前用户。"""
from core.database import get_db  # noqa: F401
from core.permissions import get_current_user, require_admin  # noqa: F401

__all__ = ["get_db", "get_current_user", "require_admin"]
