"""端到端冒烟测试：注册登录 → 上传生成 → 下载 EPUB → 积分 → 管理端。

既可用 pytest 跑，也可直接 `python tests/test_smoke.py`。
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db  # noqa: E402

# TestClient 只有在 with 语句里才触发 lifespan，这里显式建库
init_db()

from app.factory import app  # noqa: E402

client = TestClient(app)

SAMPLE = (
    "It is a truth universally acknowledged, that a single man in possession of a good fortune, "
    "must be in want of a wife.\n\n"
    "Mr. Bennet replied that he had not.\n\n"
    "What is his name? asked Mr. Bennet.\n\n"
    "Bingley.\n\n"
    "She was a woman of mean understanding, little information, and uncertain temper.\n\n"
    "The business of her life was to get her daughters married.\n"
)


def _login(email: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    return {"Authorization": f"Bearer {body['data']['token']}"}


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"


def test_seed_accounts_login():
    assert _login("demo@book.app", "demo123")
    # chen 在种子数据里是「风控封号」状态
    resp = client.post("/api/auth/login", json={"email": "chen@mail.cn", "password": "user123"})
    assert resp.status_code == 403, resp.text


def test_generate_and_download():
    headers = _login("demo@book.app", "demo123")

    resp = client.post(
        "/api/books",
        headers=headers,
        files={"file": ("demo-book.txt", SAMPLE.encode("utf-8"), "text/plain")},
        data={"target_lang": "zh", "title": "冒烟测试书", "engine": "official"},
    )
    assert resp.status_code == 200, resp.text
    book = resp.json()["data"]
    assert book["status"] in ("pending", "processing", "ready")

    # 轮询直到完成
    book_id = book["id"]
    detail = {}
    for _ in range(60):
        r = client.get(f"/api/books/{book_id}", headers=headers)
        detail = r.json()["data"]
        if detail["status"] in ("ready", "failed"):
            break
        time.sleep(0.3)

    assert detail["status"] == "ready", detail.get("error_msg")
    assert detail["segment_count"] > 0
    assert detail["progress"] == 100

    # 失败回退不影响整体
    assert isinstance(detail["failed_segments"], int)

    epub = client.get(f"/api/books/{book_id}/download?format=epub", headers=headers)
    assert epub.status_code == 200, epub.text
    assert epub.headers["content-type"].startswith("application/epub+zip")
    assert zipfile.is_zipfile(io.BytesIO(epub.content))

    with zipfile.ZipFile(io.BytesIO(epub.content)) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype", names
        assert zf.read("mimetype") == b"application/epub+zip"
        assert "OEBPS/ch1.xhtml" in names

    # PDF 走前端打印，服务端明确拒绝
    pdf = client.get(f"/api/books/{book_id}/download?format=pdf", headers=headers)
    assert pdf.status_code == 400
    assert pdf.json()["code"] == 4001


def test_points_and_checkin():
    headers = _login("demo@book.app", "demo123")
    before = client.get("/api/points", headers=headers).json()["data"]["points"]

    resp = client.post("/api/points/checkin", headers=headers)
    assert resp.status_code in (200, 409), resp.text

    after = client.get("/api/points", headers=headers).json()["data"]["points"]
    assert after >= before

    logs = client.get("/api/points/logs", headers=headers).json()["data"]
    assert logs["total"] > 0
    assert all("balance_after" in item for item in logs["items"])


def test_admin_flow():
    headers = _login("admin@book.app", "admin123")

    dash = client.get("/api/admin/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    data = dash.json()["data"]
    assert "risk_pending" in data and "engines" in data and len(data["last7"]) == 7

    users = client.get("/api/admin/users", headers=headers).json()["data"]
    assert users["total"] >= 3

    tasks = client.get("/api/admin/tasks", headers=headers).json()["data"]
    assert tasks["total"] >= 1

    notices = client.get("/api/admin/notices", headers=headers).json()["data"]
    assert len(notices) >= 3

    logs = client.get("/api/admin/logs", headers=headers).json()["data"]
    assert logs["total"] > 0

    risk = client.get("/api/admin/risk/alerts", headers=headers).json()["data"]
    assert risk["total"] >= 1


def test_engine_validation():
    headers = _login("demo@book.app", "demo123")
    resp = client.post(
        "/api/books",
        headers=headers,
        files={"file": ("x.txt", SAMPLE.encode("utf-8"), "text/plain")},
        data={"target_lang": "zh", "engine": "baidu"},  # 缺密钥
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 3001


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print("\n" + ("ALL PASSED" if failures == 0 else f"{failures} FAILED"))
    sys.exit(1 if failures else 0)
