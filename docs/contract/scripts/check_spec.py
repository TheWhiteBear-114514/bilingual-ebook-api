#!/usr/bin/env python
"""校验后端实现是否偏离契约。

用法：
    python scripts/check_spec.py --api ../bilingual-ebook-api

做法：导入后端 FastAPI 应用，重新导出 OpenAPI，
与仓库里的 openapi.json 比对「路径 / 方法 / 参数 / 请求体 / Schema 字段」。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

METHODS = ("get", "post", "put", "delete", "patch", "head", "options")


def load_committed(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_current(api_dir: Path) -> dict:
    sys.path.insert(0, str(api_dir))
    vendor = api_dir / "vendor"
    if vendor.exists():
        sys.path.insert(0, str(vendor))
    from app.main import app  # noqa: PLC0415

    return app.openapi()


def ops(spec: dict) -> dict[tuple[str, str], dict]:
    result = {}
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method.lower() in METHODS:
                result[(path, method.lower())] = op
    return result


def param_sig(op: dict) -> set[tuple[str, str, bool]]:
    return {
        (p.get("name", ""), p.get("in", ""), bool(p.get("required")))
        for p in op.get("parameters", [])
    }


def body_ref(op: dict) -> str:
    ref = (
        op.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref", "")
    )
    return ref


def schema_props(spec: dict) -> dict[str, set[str]]:
    out = {}
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        out[name] = set(schema.get("properties", {}).keys())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="后端仓库路径（含 app/ 目录）")
    ap.add_argument("--spec", default="openapi.json", help="契约文件")
    args = ap.parse_args()

    committed = load_committed(Path(args.spec))
    current = dump_current(Path(args.api).resolve())

    a, b = ops(committed), ops(current)
    only_committed = sorted(set(a) - set(b))
    only_current = sorted(set(b) - set(a))

    changed = []
    for key in sorted(set(a) & set(b)):
        diffs = []
        if param_sig(a[key]) != param_sig(b[key]):
            diffs.append(f"参数：{sorted(param_sig(a[key]))} → {sorted(param_sig(b[key]))}")
        if body_ref(a[key]) != body_ref(b[key]):
            diffs.append(f"请求体：{body_ref(a[key]) or '无'} → {body_ref(b[key]) or '无'}")
        if diffs:
            changed.append((key, diffs))

    sa, sb = schema_props(committed), schema_props(current)
    schema_diffs = []
    for name in sorted(set(sa) | set(sb)):
        before, after = sa.get(name, set()), sb.get(name, set())
        if before != after:
            schema_diffs.append(
                f"{name}: 缺少 {sorted(before - after) or '—'} / 新增 {sorted(after - before) or '—'}"
            )

    print(f"契约操作数：{len(a)}    当前实现：{len(b)}")
    if only_committed:
        print("\n[契约有、实现缺失]")
        for path, method in only_committed:
            print(f"  - {method.upper():6} {path}")
    if only_current:
        print("\n[实现有、契约缺失]")
        for path, method in only_current:
            print(f"  + {method.upper():6} {path}")
    if changed:
        print("\n[同一接口签名变化]")
        for (path, method), diffs in changed:
            print(f"  * {method.upper():6} {path}")
            for d in diffs:
                print(f"      {d}")
    if schema_diffs:
        print("\n[Schema 字段变化]")
        for line in schema_diffs:
            print(f"  * {line}")

    ok = not (only_committed or only_current or changed or schema_diffs)
    print("\n" + ("OK：实现与契约一致" if ok else "DRIFT：实现与契约不一致，请更新 openapi.json 或修正代码"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
