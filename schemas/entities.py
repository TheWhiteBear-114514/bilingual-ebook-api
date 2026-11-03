"""Pydantic 请求 / 响应模型（与前端 src/api 约定一致）。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- 认证 ----------------
class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=40)


class UserOut(ORMModel):
    id: int
    email: str
    nickname: str | None = None
    points: int = 0
    role: str = "user"
    is_active: bool = True
    ban_reason: str | None = None
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class TokenOut(BaseModel):
    token: str
    user: UserOut


# ---------------- 书籍 ----------------
class SegmentOut(ORMModel):
    id: int
    seq: int
    source_text: str
    translated_text: str | None = None
    is_failed: bool = False


class BookOut(ORMModel):
    id: int
    title: str
    source_ext: str
    source_lang: str
    target_lang: str
    engine: str
    status: str
    progress: int = 0
    char_count: int | None = None
    cached_segments: int = 0
    segment_count: int = 0
    failed_segments: int = 0
    error_msg: str | None = None
    epub_url: str | None = None
    pdf_url: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BookDetail(BookOut):
    segments: list[SegmentOut] = []


class PagedBooks(BaseModel):
    total: int
    page: int
    size: int
    items: list[BookOut]


# ---------------- 公告 ----------------
class NoticeOut(ORMModel):
    id: int
    type: str
    title: str
    body: str
    is_active: bool = True
    views: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------- 积分 ----------------
class PointsOut(BaseModel):
    points: int
    rate: int


class PointLogOut(ORMModel):
    id: int
    delta: int
    balance_after: int
    type: str
    ref_id: int | None = None
    description: str | None = None
    created_at: datetime | None = None


class PagedPointLogs(BaseModel):
    total: int
    page: int
    size: int
    items: list[PointLogOut]


class CheckinOut(BaseModel):
    points: int
    reward: int


# ---------------- 反馈 ----------------
class FeedbackCreate(BaseModel):
    type: Literal["bug", "suggest", "experience", "other"] = "other"
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=2000)
    contact: str | None = Field(default=None, max_length=120)


class FeedbackOut(ORMModel):
    id: int
    type: str
    title: str
    body: str
    contact: str | None = None
    status: str
    reward: int = 0
    created_at: datetime | None = None
    handled_at: datetime | None = None


class FeedbackAdminOut(FeedbackOut):
    user_id: int
    user_email: str | None = None


# ---------------- 管理端 ----------------
class ResetPasswordOut(BaseModel):
    temp_password: str


class TaskAdminOut(BookOut):
    user: str | None = None


class CacheOut(ORMModel):
    id: int
    source_hash: str
    src_lang: str
    tgt_lang: str
    engine: str
    translated_text: str
    hit_count: int
    created_at: datetime | None = None


class CacheStatsOut(BaseModel):
    total: int
    hits: int
    hit_rate: float
    items: list[CacheOut]


class EngineOut(BaseModel):
    id: str
    name: str
    official: bool = False
    key_fields: list[dict[str, Any]] = []
    enabled: bool = True
    calls: int = 0
    fail_rate: float = 0


class OfficialApiOut(BaseModel):
    official_api_enabled: str
    token_per_point: int
    api_key_masked: str


class OfficialApiIn(BaseModel):
    official_api_enabled: bool | None = None
    official_api_key: str | None = None
    token_per_point: int | None = None


class AdjustPointsIn(BaseModel):
    user_id: int
    delta: int
    reason: str = "管理员调整"


class ClearPointsIn(BaseModel):
    user_id: int


class BulkPointsIn(BaseModel):
    delta: int
    reason: str = "批量发放"


class PointConfigIn(BaseModel):
    checkin_reward: int | None = None
    register_reward: int | None = None
    token_per_point: int | None = None


class PointUserOut(UserOut):
    log_count: int = 0


class FeedbackHandleIn(BaseModel):
    action: Literal["reward", "penalty", "ban"]
    amount: int = 20


class RiskAlertOut(ORMModel):
    id: int
    user_id: int
    user_email: str | None = None
    user_active: bool | None = None
    rule: str
    detail: str
    status: str
    resolve: str | None = None
    created_at: datetime | None = None
    handled_at: datetime | None = None


class RiskConfigIn(BaseModel):
    risk_max_single: int | None = None
    risk_max_freq: int | None = None
    risk_max_daily: int | None = None


class RiskResolveIn(BaseModel):
    resolve: Literal["unban", "confirm"]
    penalty: int = 0


class NoticeIn(BaseModel):
    type: str = "system"
    title: str = Field(min_length=1, max_length=60)
    body: str = Field(min_length=1)


class LogOut(ORMModel):
    id: int
    level: str
    module: str
    message: str
    created_at: datetime | None = None


class LogPage(BaseModel):
    total: int
    items: list[LogOut]


class CheckinRecordOut(ORMModel):
    id: int
    checkin_date: date
    reward: int
    created_at: datetime | None = None
