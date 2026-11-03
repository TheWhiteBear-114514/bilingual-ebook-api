"""书籍：上传生成、书架、详情、重试、删除、下载。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.config_unified import settings
from core.database import get_db
from core.permissions import ApiError, get_current_user
from models import Book, Segment, User
from schemas import BookDetail, BookOut, PagedBooks, SegmentOut
from service.audit import audit
from service.pipeline import run_pipeline
from service.points import get_config, official_cost, spend
from service.risk import check_after_spend
from service.translator import ENGINE_IDS, TranslatorError, validate_keys
from utils.response import ok, page_params

router = APIRouter(tags=["书籍"])

ALLOWED_EXT = {"txt", "epub", "pdf"}


def book_to_dict(book: Book, with_segments: bool = False) -> dict:
    segs = book.segments or []
    data = {
        "id": book.id,
        "title": book.title,
        "source_ext": book.source_ext,
        "source_lang": book.source_lang,
        "target_lang": book.target_lang,
        "engine": book.engine,
        "status": book.status,
        "progress": book.progress,
        "char_count": book.char_count,
        "cached_segments": book.cached_segments,
        "segment_count": len(segs),
        "failed_segments": sum(1 for s in segs if s.is_failed),
        "error_msg": book.error_msg,
        "epub_url": f"/api/books/{book.id}/download?format=epub",
        "pdf_url": f"/api/books/{book.id}/download?format=pdf",
        "created_at": book.created_at,
        "started_at": book.started_at,
        "finished_at": book.finished_at,
    }
    if with_segments:
        data["segments"] = [SegmentOut.model_validate(s).model_dump() for s in segs]
    return data


@router.post("/books", summary="上传并生成双语书")
async def create_book(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = Form("zh"),
    title: str | None = Form(None),
    engine: str = Form("official"),
    engine_keys: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filename = file.filename or "book.txt"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise ApiError(400, "格式不支持，请上传 txt / epub / pdf")
    if engine not in ENGINE_IDS:
        raise ApiError(3001, f"未知翻译引擎：{engine}")
    if target_lang not in ("zh", "en", "ja", "ko", "fr", "de"):
        raise ApiError(422, "目标语言不受支持")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise ApiError(413, f"文件超过 {settings.max_upload_mb}MB 限制", 413)

    keys: dict = {}
    if engine_keys:
        try:
            keys = json.loads(engine_keys)
        except json.JSONDecodeError as exc:
            raise ApiError(3001, "engine_keys 不是合法 JSON") from exc
    try:
        validate_keys(engine, keys)
    except TranslatorError as exc:
        raise ApiError(exc.code, exc.message) from exc

    estimated_chars = max(6000, len(content))
    cost = 0
    if engine == "official":
        if get_config(db, "official_api_enabled", "1") != "1":
            raise ApiError(3001, "官方引擎已停用，请使用自带密钥的引擎")
        cost = official_cost(db, estimated_chars)
        if user.points < cost:
            raise ApiError(3002, f"积分不足（本次约需 {cost} 积分，当前 {user.points}）", 402)

    book = Book(
        user_id=user.id,
        title=(title or filename.rsplit(".", 1)[0]).strip()[:120] or "未命名",
        source_ext=ext,
        source_lang="en",
        target_lang=target_lang,
        engine=engine,
        status="pending",
        progress=1,
        char_count=estimated_chars,
        created_at=datetime.now(),
    )
    db.add(book)
    db.flush()

    upload_dir = settings.upload_dir / str(user.id) / str(book.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"source.{ext}"
    dest.write_bytes(content)
    book.source_path = str(dest)

    if engine == "official":
        spend(db, user, cost, f"官方引擎翻译《{book.title}》", book.id)
        check_after_spend(db, user, cost)

    audit(db, "INFO", "upload", f"{user.email} 上传 {filename}（{len(content) // 1024}KB）")
    audit(db, "INFO", "task", f"任务 {book.id} 入队（{book.title} · {user.email}）")
    db.commit()

    background.add_task(run_pipeline, book.id, keys)
    return ok(book_to_dict(book))


@router.get("/books", summary="我的书架")
def list_books(
    page: int = Query(1, ge=1),
    size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p, s = page_params(page, size)
    total = db.execute(
        select(func.count(Book.id)).where(Book.user_id == user.id)
    ).scalar_one()
    rows = db.execute(
        select(Book)
        .where(Book.user_id == user.id)
        .order_by(Book.created_at.desc(), Book.id.desc())
        .offset((p - 1) * s)
        .limit(s)
    ).scalars().all()
    data = PagedBooks(
        total=total, page=p, size=s, items=[BookOut(**book_to_dict(b)) for b in rows]
    )
    return ok(data.model_dump(mode="json"))


@router.get("/books/{book_id}", summary="书籍详情")
def get_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError(404, "任务不存在", 404)
    if book.user_id != user.id and user.role != "admin":
        raise ApiError(403, "无权访问", 403)
    return ok(BookDetail(**book_to_dict(book, with_segments=True)).model_dump(mode="json"))


@router.post("/books/{book_id}/retry", summary="重试失败任务")
def retry_book(
    book_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if book is None or (book.user_id != user.id and user.role != "admin"):
        raise ApiError(404, "任务不存在", 404)
    if book.status != "failed":
        raise ApiError(409, "只有失败的任务可以重试", 409)

    for seg in list(book.segments):
        db.delete(seg)
    book.status = "pending"
    book.progress = 0
    book.error_msg = None
    book.finished_at = None
    db.commit()

    background.add_task(run_pipeline, book.id, {})
    return ok(book_to_dict(book))


@router.delete("/books/{book_id}", summary="删除书籍")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if book is None or book.user_id != user.id:
        raise ApiError(404, "任务不存在", 404)

    for p in (book.epub_path, book.pdf_path, book.source_path):
        if p:
            Path(p).unlink(missing_ok=True)
    db.delete(book)
    db.commit()
    return ok(True)


@router.get("/books/{book_id}/download", summary="下载成品")
def download_book(
    book_id: int,
    format: str = Query("epub", pattern="^(epub|pdf)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError(404, "任务不存在", 404)
    if book.user_id != user.id and user.role != "admin":
        raise ApiError(403, "无权访问", 403)
    if book.status != "ready":
        raise ApiError(409, "尚未生成完成", 409)

    if format == "pdf":
        # 设计取舍：PDF 由前端「打印 → 另存为 PDF」生成，服务端不引入中文字体依赖
        raise ApiError(4001, "PDF 请在前端结果页使用「打印 / 另存为 PDF」导出")

    path = Path(book.epub_path or "")
    if not path.exists():
        raise ApiError(404, "文件已丢失，请重新生成", 404)

    return FileResponse(
        path,
        media_type="application/epub+zip",
        filename=f"{book.title}-{book.source_lang}{book.target_lang}对照.epub",
    )
