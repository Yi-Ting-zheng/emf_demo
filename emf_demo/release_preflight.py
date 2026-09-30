#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release_preflight.py — 发布前置闸门（v1.0.4 新增）

为什么需要这个闸门
------------------
2026-09-30 连续发生两起**只有克隆才能发现**的发布缺陷：

  1. 哈希锁形同虚设：core.autocrlf=true 且无 .gitattributes ⟹ 新克隆 12/12 文件
     被 CRLF 化，清单锁的字节与检出字节全部不符。本机 --verify 却显示 [OK]。
  2. tag 指向陈旧 commit：GitHub Release 1.0.1 的 tag 落在 3e7a9d8，而修复
     (.gitattributes) 在其后的 5c0a74c ⟹ Zenodo 正在归档的正是那个坏版本。

两起的共同点：**本机自审全绿，产物是坏的**。任何只读工作区的检查都抓不到。

因此本闸门的核心不是"检查工作区"，而是
    把 tag 指向的树解包到临时目录，在**那个副本**上跑清单校验与审计，
    判定"Zenodo 实际会归档的东西"是否自洽。
这与人工"克隆一份再跑"是同一动作，只是可复现、可挂在发布流程上。

用法:
    python emf_demo/release_preflight.py                  # 校验 HEAD
    python emf_demo/release_preflight.py --tag 1.0.2       # 校验指定 tag
    python emf_demo/release_preflight.py --tag 1.0.2 --allow-tag-behind-head

退出码:
    0 = 可发布        1 = 阻断（产物不自洽）    2 = 用法/环境错误
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"

# 判定为"文本"的扩展名：这些文件受行尾转换影响，哈希锁对其敏感
TEXT_EXT = {".py", ".md", ".json", ".yml", ".yaml", ".txt", ".cfg", ".toml", ".ini"}


def git(*args: str, cwd: str | None = None) -> tuple[int, str, str]:
    p = subprocess.run(
        [GIT, *args], cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def hr(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 58 - len(title)))


def check_tag_matches_head(tag: str, allow_behind: bool) -> list[str]:
    """闸门 1：tag 必须指向 HEAD。

    2026-09-30 实证：Release 1.0.1 的 tag 落后 HEAD 一笔，Zenodo 因此归档了
    修复前的坏版本。tag 落后 ⟹ 归档内容 ≠ 已验证内容 ⟹ 等于没验证。
    """
    blockers: list[str] = []
    rc_t, out_t, _ = git("rev-parse", f"{tag}^{{commit}}")
    rc_h, out_h, _ = git("rev-parse", "HEAD")
    if rc_t or rc_h:
        return [f"无法解析 {tag} 或 HEAD（tag 未推送？）"]

    behind = git("log", f"{tag}..HEAD", "--oneline")[1]
    n = len(behind.splitlines()) if behind else 0
    if n == 0:
        print(f"[OK] tag {tag} == HEAD（{out_t[:7]}）")
    else:
        msg = (f"tag {tag} 落后 HEAD {n} 笔 ⟹ Zenodo 将归档未经验证的内容：\n"
               + "\n".join("         " + l for l in behind.splitlines()))
        print("[FAIL] " + msg)
        if allow_behind:
            print("       --allow-tag-behind-head 已给，仅告警")
        else:
            blockers.append(f"tag {tag} 落后 HEAD {n} 笔")
    return blockers


def check_gitattributes_in_tree(tag: str) -> list[str]:
    """闸门 2：被归档的树里必须有 eol=lf 固定，否则克隆即改字节。"""
    rc, out, _ = git("cat-file", "-e", f"{tag}:.gitattributes")
    if rc:
        print("[FAIL] 该树内无 .gitattributes ⟹ core.autocrlf=true 下克隆会改写字节，"
              "哈希锁在克隆后必然失效")
        return ["缺少 .gitattributes"]
    body = git("cat-file", "-p", f"{tag}:.gitattributes")[1]
    if "eol=lf" not in body:
        print("[FAIL] .gitattributes 存在但未固定 eol=lf")
        return [".gitattributes 未固定 eol=lf"]
    print("[OK] .gitattributes 已固定 eol=lf")
    return []


def check_zenodo_metadata_in_tree(tag: str) -> list[str]:
    """闸门 3：.zenodo.json 必须在**被归档的树**里且可解析。

    v1.0.0 的元数据缺陷根因：tag 早于 .zenodo.json 的提交，联动只读 tag 指向的
    commit ⟹ Zenodo 退回 GitHub 默认值。此闸门把它变成发布前可检事件。
    """
    rc, out, _ = git("cat-file", "-e", f"{tag}:.zenodo.json")
    if rc:
        print("[FAIL] 该树内无 .zenodo.json ⟹ Zenodo 元数据将退回 GitHub 默认值"
              "（v1.0.0 缺陷复现）")
        return ["缺少 .zenodo.json"]
    body = git("cat-file", "-p", f"{tag}:.zenodo.json")[1]
    try:
        meta = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"[FAIL] .zenodo.json 不可解析：{e}")
        return [".zenodo.json 不可解析"]
    bad = [k for k in ("title", "description", "creators", "license")
           if not meta.get(k) or "占位" in str(meta.get(k))]
    if bad:
        print(f"[FAIL] .zenodo.json 字段缺失或含占位：{bad}")
        return [f".zenodo.json 字段异常 {bad}"]
    print(f"[OK] .zenodo.json 可解析，关键字段齐备（title/description/creators/license）")
    return []


def check_archive_artifact(tag: str) -> list[str]:
    """闸门 4（决定性）：解包 tag 树，在副本上跑清单校验 + 审计。

    这是本闸门的核心：判定"Zenodo 实际会归档的东西"是否自洽。
    等价于人工"克隆一份再跑"，但可复现、可挂流程。
    """
    blockers: list[str] = []
    tmp = tempfile.mkdtemp(prefix="emf_preflight_")
    work = os.path.join(tmp, "x")
    try:
        blob = os.path.join(tmp, "tree.tar")
        rc, _, err = git("archive", "--format=tar", "-o", blob, tag)
        if rc:
            print(f"[FAIL] git archive 失败：{err}")
            return ["git archive 失败"]
        os.makedirs(work, exist_ok=True)
        with tarfile.open(blob) as tf:
            tf.extractall(work, filter="data")

        # 4a 行尾
        crlf = []
        for dp, dn, fn in os.walk(work):
            dn[:] = [d for d in dn if d not in {".git", "__pycache__"}]
            for f in fn:
                p = os.path.join(dp, f)
                if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                    continue
                with io.open(p, "rb") as fh:
                    if b"\r\n" in fh.read():
                        crlf.append(os.path.relpath(p, work).replace("\\", "/"))
        if crlf:
            print(f"[FAIL] 归档树内 {len(crlf)} 个文本文件含 CRLF ⟹ 哈希锁在该副本上必然失效：")
            for c in crlf:
                print(f"         {c}")
            blockers.append(f"归档树含 CRLF ×{len(crlf)}")
        else:
            print("[OK] 归档树内文本文件行尾统一")

        # 4b 清单校验
        py = sys.executable
        r = subprocess.run([py, os.path.join(work, "emf_demo", "mk_manifest.py"), "--verify"],
                           cwd=work, capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            print("[OK] 归档树内哈希锁自校验通过：" + r.stdout.strip().splitlines()[-1])
        else:
            print("[FAIL] 归档树内哈希锁不自洽：")
            for l in (r.stdout + r.stderr).strip().splitlines():
                print("         " + l)
            blockers.append("归档树哈希锁不自洽")

        # 4c 审计
        r = subprocess.run([py, os.path.join(work, "emf_demo", "mf_audit.py"), work],
                           cwd=work, capture_output=True, text=True, encoding="utf-8")
        line = next((l for l in r.stdout.splitlines() if "FAIL=" in l), "")
        if "FAIL=0" in line:
            print(f"[OK] 归档树内审计 {line.strip()}")
        else:
            print(f"[FAIL] 归档树内审计未过：{line.strip() or r.stdout.strip()[-200:]}")
            blockers.append("归档树审计未过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return blockers


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="HEAD")
    ap.add_argument("--allow-tag-behind-head", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(GIT):
        print(f"[FAIL] 找不到 git：{GIT}", file=sys.stderr)
        return 2

    tag = args.tag
    print(f"发布前置闸门 | EMF | 目标：{tag}")

    hr("闸门 1  tag 与 HEAD 一致性")
    b1 = check_tag_matches_head(tag, args.allow_tag_behind_head)
    hr("闸门 2  归档树含 .gitattributes（eol=lf）")
    b2 = check_gitattributes_in_tree(tag)
    hr("闸门 3  归档树含可解析的 .zenodo.json")
    b3 = check_zenodo_metadata_in_tree(tag)
    hr("闸门 4  归档产物自洽性（解包后实跑）")
    b4 = check_archive_artifact(tag)

    blockers = b1 + b2 + b3 + b4
    print()
    if blockers:
        print("=" * 64)
        print(f"裁定：❌ 不得发布 —— {len(blockers)} 项阻断")
        for b in blockers:
            print(f"  · {b}")
        print("=" * 64)
        return 1
    print("=" * 64)
    print("裁定：✅ 可发布（产物在 tag 指向的树上自洽）")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
