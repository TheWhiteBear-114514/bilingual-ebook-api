"""把后端依赖的 wheel 直接下载并解包到 vendor/（不依赖 pip 的临时目录）。"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
WHEELS = ROOT / "wheels"

PKGS = {
    "fastapi": "0.115.6",
    "starlette": "0.41.3",
    "pydantic": "2.10.4",
    "pydantic_core": "2.27.2",
    "annotated-types": "0.7.0",
    "typing_extensions": "4.12.2",
    "anyio": "4.7.0",
    "sniffio": "1.3.1",
    "idna": "3.10",
    "h11": "0.14.0",
    "click": "8.1.7",
    "colorama": "0.4.6",
    "uvicorn": "0.34.0",
    "SQLAlchemy": "2.0.36",
    "greenlet": "3.1.1",
    "PyJWT": "2.10.1",
    "bcrypt": "4.2.1",
    "python-multipart": "0.0.20",
    "httpx": "0.28.1",
    "httpcore": "1.0.7",
    "certifi": "2024.12.14",
}


def pick(files: list[dict]) -> dict | None:
    """优先纯 Python wheel，其次 cp312 win_amd64 / abi3。"""
    def score(f: dict) -> int:
        name = f["filename"]
        if not name.endswith(".whl"):
            return -1
        if "py3-none-any" in name:
            return 100
        if "cp312-cp312-win_amd64" in name:
            return 90
        if "abi3-win_amd64" in name:
            return 85
        if "cp312" in name and "win_amd64" in name:
            return 80
        return -1

    ranked = sorted(files, key=score, reverse=True)
    return ranked[0] if ranked and score(ranked[0]) > 0 else None


def main() -> int:
    VENDOR.mkdir(exist_ok=True)
    WHEELS.mkdir(exist_ok=True)
    failed = []
    for pkg, ver in PKGS.items():
        url_json = f"https://pypi.org/pypi/{pkg}/{ver}/json"
        try:
            data = json.load(urllib.request.urlopen(url_json, timeout=60))
        except Exception as exc:  # noqa: BLE001
            failed.append((pkg, f"meta: {exc}"))
            continue
        f = pick(data.get("urls", []))
        if f is None:
            failed.append((pkg, "no wheel"))
            continue
        target = WHEELS / f["filename"]
        if not target.exists():
            try:
                blob = urllib.request.urlopen(f["url"], timeout=120).read()
                target.write_bytes(blob)
            except Exception as exc:  # noqa: BLE001
                failed.append((pkg, f"download: {exc}"))
                continue
        try:
            with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as zf:
                zf.extractall(VENDOR)
        except Exception as exc:  # noqa: BLE001
            failed.append((pkg, f"unzip: {exc}"))
            continue
        print(f"ok  {pkg}=={ver}  <- {f['filename']}")

    if failed:
        print("\nFAILED:")
        for pkg, why in failed:
            print(f"  {pkg}: {why}")
        return 1
    print(f"\nvendor ready: {VENDOR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
