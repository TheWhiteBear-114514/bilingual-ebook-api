"""翻译缓存数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import TranslationCache


def get_by_key(db: Session, source_hash: str, src: str, tgt: str, engine: str) -> TranslationCache | None:
    return db.execute(
        select(TranslationCache).where(
            TranslationCache.source_hash == source_hash,
            TranslationCache.src_lang == src,
            TranslationCache.tgt_lang == tgt,
            TranslationCache.engine == engine,
        )
    ).scalar_one_or_none()


def count(db: Session) -> int:
    return db.execute(select(func.count(TranslationCache.id))).scalar_one()


def total_hits(db: Session) -> int:
    return db.execute(select(func.coalesce(func.sum(TranslationCache.hit_count), 0))).scalar_one()
