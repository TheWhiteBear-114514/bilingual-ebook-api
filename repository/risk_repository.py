"""风控告警数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import RiskAlert


def list_by_status(db: Session, status: str | None = None) -> list[RiskAlert]:
    stmt = select(RiskAlert).order_by(RiskAlert.created_at.desc())
    if status and status != "all":
        stmt = stmt.where(RiskAlert.status == status)
    return list(db.execute(stmt).scalars())


def get(db: Session, alert_id: int) -> RiskAlert | None:
    return db.get(RiskAlert, alert_id)
