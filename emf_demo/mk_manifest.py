#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mk_manifest.py — EMF 框架哈希锁

用途：任何对 EMF 框架文件的改动都必须使 MANIFEST_EMF.json 失效，
从而"框架被静默修改"成为可检出事件，而非无声发生。

版本真值源：本文件不含版本常量。框架版本由 mf_audit.py 的 VERSION 自动派生
（见 framework_version()）。历史教训 v1.0.1→v1.0.3：硬编码副本导致清单自称
1.0.1 而代码已是 1.0.2 —— 重复常量必然漂移，故改为结构性消除。

用法:
    python mk_manifest.py            # 生成/覆盖
    python mk_manifest.py --verify   # 只校验，不写；不一致则 exit 1
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "MANIFEST_EMF.json")
SKIP_DIR = {".git", "__pycache__", ".venv", "archive"}
SKIP_FILE = {"MANIFEST_EMF.json"}


def sha(path: str) -> str:
    h = hashlib.sha256()
    with io.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIR]
        for f in sorted(fn):
            if f in SKIP_FILE:
                continue
            p = os.path.join(dp, f)
            r = os.path.relpath(p, ROOT).replace("\\", "/")
            out[r] = {"sha256": sha(p), "bytes": os.path.getsize(p)}
    return out


def framework_version() -> str:
    """从 mf_audit.py 的 VERSION 常量派生框架版本（单一真值源）。

    遍历而非硬编码相对路径，使内部布局（脚本/）与公开 demo 布局（emf_demo/）
    共用同一实现。找不到或解析失败时返回 "unknown" —— 不猜、不硬编码兜底值。
    """
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIR]
        if "mf_audit.py" not in fn:
            continue
        p = os.path.join(dp, "mf_audit.py")
        try:
            text = io.open(p, encoding="utf-8").read()
        except OSError:
            continue
        m = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if m:
            return m.group(1)
    return "unknown"


def build() -> dict:
    files = collect()
    return {
        "framework": "EMF",
        "version": framework_version(),
        "version_source": "derived from mf_audit.py:VERSION (single source of truth)",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "file_count": len(files),
        "note": (
            "EMF 框架文件哈希锁。E1 纪律：框架本身亦受预注册约束——"
            "修改任何条目必须重生成本清单并记入 CHANGELOG.md。"
            "框架有效性问题见 03_规范/GAP-01_元方法论自指缺口.md。"
        ),
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    new = build()

    if not args.verify:
        with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            json.dump(new, f, ensure_ascii=False, indent=2)
        print(f"[OK] MANIFEST_EMF.json 已生成：{new['file_count']} 个文件")
        print(f"     时间 {new['generated_at']}")
        return 0

    if not os.path.exists(MANIFEST):
        print("[FAIL] MANIFEST_EMF.json 不存在", file=sys.stderr)
        return 1
    old = json.load(io.open(MANIFEST, encoding="utf-8"))

    ver_old, ver_new = old.get("version"), new["version"]
    if ver_old != ver_new:
        print(f"[FAIL] 版本漂移：清单自称 v{ver_old}，而 mf_audit.py VERSION=v{ver_new}")
        print("       框架版本已变更但清单未重生 —— 须重生成并记入 CHANGELOG.md。")
        return 1

    of, nf = old.get("files", {}), new["files"]

    added = sorted(set(nf) - set(of))
    removed = sorted(set(of) - set(nf))
    changed = sorted(k for k in set(of) & set(nf) if of[k]["sha256"] != nf[k]["sha256"])

    if not (added or removed or changed):
        print(f"[OK] 哈希锁一致：{len(nf)} 个文件全部未变")
        return 0

    print("[FAIL] 哈希锁不一致 —— 框架已被修改：")
    for k in added:
        print(f"  + 新增   {k}")
    for k in removed:
        print(f"  - 删除   {k}")
    for k in changed:
        print(f"  ~ 修改   {k}")
    print("\n若为有意修改：重生成清单并在 CHANGELOG.md 记一笔。")
    print("若为无意修改：框架完整性已失守，全部结论的层级须下审查。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
