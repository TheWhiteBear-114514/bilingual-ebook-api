"""解析 → 分句 → 翻译（带缓存）→ 导出 EPUB 的后台管线。"""
from __future__ import annotations

import hashlib
import io
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from config.config_unified import settings
from core.database import SessionLocal
from models import Book, Log, Segment, TranslationCache
from service.epub import build_epub
from service.translator import TranslatorError, get_translator, validate_keys


class PipelineError(Exception):
    def __init__(self, message: str, code: int = 5001):
        super().__init__(message)
        self.message = message
        self.code = code


def _log(db, level: str, module: str, message: str) -> None:
    db.add(Log(level=level, module=module, message=message))


# ----------------------------- 解析 -----------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def _html_to_text(raw: str) -> str:
    raw = _SCRIPT_RE.sub(" ", raw)
    raw = re.sub(r"</(p|div|h\d|li|br)\s*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = _TAG_RE.sub("", raw)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text


def _split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [re.sub(r"\s+", " ", b).strip() for b in re.split(r"\n\s*\n", text)]
    blocks = [b for b in blocks if len(b) >= 12]
    if len(blocks) >= 3:
        return blocks

    # 段落太少时按句切分（中英文句末标点）
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 12]
    return sentences or blocks


def extract_paragraphs(path: Path, ext: str) -> tuple[list[str], str]:
    ext = ext.lower().lstrip(".")
    if ext == "txt":
        for enc in ("utf-8", "gb18030", "latin-1"):
            try:
                text = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise PipelineError("无法识别文本编码", 422)
        return _split_paragraphs(text), text

    if ext == "epub":
        try:
            with zipfile.ZipFile(path) as zf:
                chunks: list[str] = []
                for name in zf.namelist():
                    if name.lower().endswith((".xhtml", ".html", ".htm")):
                        chunks.append(_html_to_text(zf.read(name).decode("utf-8", "ignore")))
            text = "\n\n".join(chunks)
        except zipfile.BadZipFile as exc:
            raise PipelineError("EPUB 文件损坏或格式不正确", 422) from exc
        if len(text.strip()) < 50:
            raise PipelineError("EPUB 中未提取到有效文本", 422)
        return _split_paragraphs(text), text

    if ext == "pdf":
        try:
            from pypdf import PdfReader  # 可选依赖
        except ImportError as exc:
            raise PipelineError("服务端未安装 pypdf，暂时无法解析 PDF；请上传 txt / epub", 422) from exc
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("PDF 解析失败，可能是扫描版（不支持 OCR）", 422) from exc
        if len(text.strip()) < 100:
            raise PipelineError("检测到扫描型 PDF，无法提取文本（不支持 OCR）", 422)
        return _split_paragraphs(text), text

    raise PipelineError(f"不支持的文件格式：{ext}", 422)


# ----------------------------- 管线 -----------------------------
def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def run_pipeline(book_id: int, engine_keys: dict | None = None) -> None:
    """在后台线程里执行；不依赖请求级 Session。"""
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            return
        if book.status not in ("pending", "processing"):
            return

        try:
            try:
                validate_keys(book.engine, engine_keys)
            except TranslatorError as exc:
                raise PipelineError(exc.message, exc.code) from exc

            book.status = "processing"
            book.progress = 5
            book.started_at = datetime.now()
            db.commit()

            src_path = Path(book.source_path or "")
            if not src_path.exists():
                raise PipelineError("源文件已丢失，请重新上传", 422)

            paragraphs, raw_text = extract_paragraphs(src_path, book.source_ext)
            if not paragraphs:
                raise PipelineError("没有解析到可翻译的段落，可能不是文本型文件", 422)

            book.char_count = len(raw_text)
            book.progress = 18
            db.commit()

            translator = get_translator(book.engine, engine_keys)
            total = len(paragraphs)
            failed = 0
            cached = 0

            for index, para in enumerate(paragraphs, start=1):
                key = _cache_key(para)
                hit = db.execute(
                    select(TranslationCache).where(
                        TranslationCache.source_hash == key,
                        TranslationCache.src_lang == book.source_lang,
                        TranslationCache.tgt_lang == book.target_lang,
                        TranslationCache.engine == book.engine,
                    )
                ).scalar_one_or_none()

                if hit is not None:
                    hit.hit_count += 1
                    translated, is_failed = hit.translated_text, False
                    cached += 1
                else:
                    try:
                        translated = translator.translate(para, book.source_lang, book.target_lang)
                        is_failed = not translated.strip()
                    except TranslatorError:
                        translated, is_failed = None, True
                    except Exception:  # noqa: BLE001
                        translated, is_failed = None, True

                    if is_failed:
                        failed += 1
                    else:
                        db.add(
                            TranslationCache(
                                source_hash=key,
                                src_lang=book.source_lang,
                                tgt_lang=book.target_lang,
                                engine=book.engine,
                                translated_text=translated,
                            )
                        )

                db.add(
                    Segment(
                        book_id=book.id,
                        seq=index,
                        source_text=para,
                        translated_text=translated,
                        is_failed=is_failed,
                    )
                )
                book.progress = 20 + int(62 * index / total)
                db.commit()

                if settings.demo_segment_delay:
                    time.sleep(settings.demo_segment_delay)

            book.cached_segments = cached
            book.progress = 88
            db.commit()

            segments = list(
                db.execute(select(Segment).where(Segment.book_id == book.id).order_by(Segment.seq)).scalars()
            )
            epub_bytes = build_epub(book, segments)
            out_dir = settings.output_dir / str(book.user_id) / str(book.id)
            out_dir.mkdir(parents=True, exist_ok=True)
            epub_path = out_dir / f"{book.id}.epub"
            epub_path.write_bytes(epub_bytes)

            if failed == total and total > 0:
                raise PipelineError("全书翻译失败，请检查翻译引擎密钥或额度", 3001)

            book.epub_path = str(epub_path)
            book.status = "ready"
            book.progress = 100
            book.finished_at = datetime.now()
            db.commit()
            _log(db, "INFO", "translate", f"书籍 {book.id} 翻译完成：{total} 段，缓存命中 {cached} 段，失败 {failed} 段")
            db.commit()

        except PipelineError as exc:
            book.status = "failed"
            book.error_msg = exc.message
            book.finished_at = datetime.now()
            db.commit()
            _log(db, "ERROR", "translate", f"书籍 {book.id} 失败：{exc.message}")
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            book = db.get(Book, book_id)
            if book:
                book.status = "failed"
                book.error_msg = f"内部错误：{exc}"
                book.finished_at = datetime.now()
                db.commit()
            _log(db, "ERROR", "translate", f"书籍 {book_id} 异常：{exc}")
            db.commit()
    finally:
        db.close()
