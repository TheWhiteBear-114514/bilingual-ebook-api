"""积分风控：单次超限 / 短时高频 / 单日累计。

命中后：自动临时封号 + 生成 risk_alerts（pending）+ 写 WARN 日志，等管理员复核。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import Log, RiskAlert, User
from service.points import get_config, points_used_today, recent_spends


def _log(db: Session, level: str, module: str, message: str) -> None:
    db.add(Log(level=level, module=module, message=message))


def check_after_spend(db: Session, user: User, amount: int) -> RiskAlert | None:
    """在扣费事务内调用；命中则封号并返回告警。"""
    single_limit = int(get_config(db, "risk_max_single", "500") or 500)
    freq_limit = int(get_config(db, "risk_max_freq", "10") or 10)
    daily_limit = int(get_config(db, "risk_max_daily", "2000") or 2000)

    rule: str | None = None
    detail = ""

    if amount > single_limit:
        rule = "single"
        detail = f"单次翻译消耗 {amount} 积分，超过单次上限 {single_limit}，已自动封号。"
    else:
        window_start = datetime.now() - timedelta(minutes=5)
        recent = [p for p in recent_spends(db, user.id, limit=50) if (p.created_at or datetime.now()) >= window_start]
        if len(recent) >= freq_limit:
            rule = "freq"
            detail = f"5 分钟内发起 {len(recent)} 次翻译请求（阈值 {freq_limit}），疑似脚本刷量，已自动封号。"
        elif points_used_today(db, user.id) > daily_limit:
            used = points_used_today(db, user.id)
            rule = "daily"
            detail = f"单日累计消耗 {used} 积分，超过上限 {daily_limit}，已自动封号。"

    if rule is None:
        return None

    user.is_active = False
    user.ban_reason = "积分风控"
    alert = RiskAlert(user_id=user.id, rule=rule, detail=detail, status="pending")
    db.add(alert)
    _log(db, "WARN", "risk", f"风控命中：{user.email} {detail}")
    return alert
