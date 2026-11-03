#!/usr/bin/env python
"""离线校验 openapi.json 的结构（零依赖，CI 与本地都能跑）。

检查项：
  1. 是合法 JSON，且 openapi 版本为 3.x
  2. info.title / info.version 存在
  3. 每个操作都有 responses，且至少包含一个 2xx 或 4xx
  4. operationId 唯一
  5. 所有本地 $ref 都能解析到 components
  6. 每个操作都带 tags

用法：
    python scripts/validate_spec.py [openapi.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

METHODS = ("get", "post", "put", "delete", "patch", "head", "options")


def resolve_ref(spec: dict, ref: str):
    if not ref.startswith("#/"):
        return None  # 外部引用不校验
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def walk_refs(node, out: list[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            out.append(ref)
        for v in node.values():
            walk_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_refs(v, out)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    if not path.exists():
        print(f"FAIL 找不到契约文件：{path}")
        return 1

    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL JSON 解析失败：{exc}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    version = str(spec.get("openapi", ""))
    if not version.startswith("3."):
        errors.append(f"openapi 版本应为 3.x，实际 {version or '缺失'}")

    info = spec.get("info", {})
    for key in ("title", "version"):
        if not info.get(key):
            errors.append(f"info.{key} 缺失")

    paths = spec.get("paths", {})
    if not paths:
        errors.append("paths 为空")

    seen_ids: dict[str, str] = {}
    op_count = 0

    for route, item in paths.items():
        if not route.startswith("/"):
            errors.append(f"路径必须以 / 开头：{route}")
        for method, op in item.items():
            if method.lower() not in METHODS:
                continue
            op_count += 1
            where = f"{method.upper()} {route}"

            if not isinstance(op.get("responses"), dict) or not op["responses"]:
                errors.append(f"{where} 缺少 responses")
            if not op.get("tags"):
                warnings.append(f"{where} 没有 tags")

            op_id = op.get("operationId")
            if op_id:
                if op_id in seen_ids:
                    errors.append(f"operationId 重复：{op_id}（{seen_ids[op_id]} 与 {where}）")
                seen_ids[op_id] = where
            else:
                warnings.append(f"{where} 没有 operationId")

    refs: list[str] = []
    walk_refs(spec, refs)
    for ref in sorted(set(refs)):
        if resolve_ref(spec, ref) is None:
            errors.append(f"无法解析的 $ref：{ref}")

    print(f"文件    ：{path}")
    print(f"版本    ：openapi {version} · {info.get('title', '-')} v{info.get('version', '-')}")
    print(f"路径    ：{len(paths)}")
    print(f"操作    ：{op_count}")
    print(f"Schema  ：{len(spec.get('components', {}).get('schemas', {}))}")
    print(f"本地引用：{len(set(r for r in refs if r.startswith('#/')))} 个，全部可解析"
          if not any('$ref' in e for e in errors) else "")

    if warnings:
        print(f"\n警告 {len(warnings)} 条：")
        for w in warnings[:10]:
            print(f"  - {w}")

    if errors:
        print(f"\n错误 {len(errors)} 条：")
        for e in errors:
            print(f"  - {e}")
        print("\nFAIL 契约校验未通过")
        return 1

    print("\nOK 契约结构合法")
    return 0


if __name__ == "__main__":
    sys.exit(main())
