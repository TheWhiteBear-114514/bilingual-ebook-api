"""公开元数据：引擎目录、语言列表、启用中的公告。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import get_db
from models import Notice
from schemas import NoticeOut
from service.points import get_config
from service.translator import ENGINES
from utils.response import ok

router = APIRouter(tags=["元数据"])

LANG_CODES = ["zh", "en", "ja", "ko", "fr", "de"]


@router.get("/engines", summary="引擎目录")
def engines(db: Session = Depends(get_db)):
    official_enabled = get_config(db, "official_api_enabled", "1") == "1"
    items = []
    for e in ENGINES:
        items.append(
            {
                "id": e.id,
                "name": e.name,
                "official": e.official,
                "key_fields": e.key_fields,
                "src_langs": LANG_CODES,
                "tgt_langs": LANG_CODES,
                "enabled": official_enabled if e.official else True,
            }
        )
    return ok({"default": "official", "engines": items})


@router.get("/languages", summary="支持的语种")
def languages():
    return ok({"source_langs": LANG_CODES, "target_langs": LANG_CODES})


@router.get("/notices", summary="公告列表（仅启用）")
def notices(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Notice).where(Notice.is_active == 1).order_by(Notice.created_at.desc())
    ).scalars().all()
    return ok([NoticeOut.model_validate(n).model_dump(mode="json") for n in rows])


@router.post("/notices/{notice_id}/view", summary="公告浏览量 +1")
def notice_view(notice_id: int, db: Session = Depends(get_db)):
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail={"code": 404, "message": "公告不存在"})
    notice.views = (notice.views or 0) + 1
    db.commit()
    return ok({"id": notice.id, "views": notice.views})
