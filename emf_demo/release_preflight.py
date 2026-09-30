#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release_preflight.py — 发布前置闸门（v1.0.4 新增）

为什么需要这个闸门
------------------
2026-09-30 连续发生三起**只有克隆才能发现**的发布缺陷：

  1. 哈希锁形同虚设：core.autocrlf=true 且无 .gitattributes ⟹ 新克隆 12/12 文件
     被 CRLF 化，清本锁的字节与检出字节全部不符。本机 --verify 却显示 [OK]。
  2. tag 指向陈旧 commit：GitHub Release 1.0.1 的 tag 落在 3e7a9d8，而修复
     (.gitattributes) 在其后的 5c0a74c ⟹ Zenodo 正在归档的正是那个坏版本。
  3. **.zenodo.json 用了混合代际的 schema 键**（缺陷 3，Zenodo 面板实证）：
     写成 "upload_type": {"type": "publication", "subtype": "workingpaper"}。
     但 legacy Zenodo 反序列化器要的是两个**平级**标量字段——upload_type 是
     String（映射 resource_type.type），publication_type 是它的兄弟键（映射
     resource_type.subtype）。"subtype" 是**新版 resource_type 内部**的键名，
     放进 upload_type 里不认。⟹ 反序列化产不出 resource_type，Zenodo 校验器
     报 metadata.resource_type: Missing data for required field，ingest 失败。
     emf_demo 1.0.1 与 public_theorem 1.0.0 同时挂在这上面（后者有实证面板）。

三起的共同点：**本机自审全绿，产物是坏的**。任何只读工作区的检查都抓不到。

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

# --- Zenodo 词表（依据 legacy deposition schema / developers.zenodo.org）---
# upload_type      : String  -> resource_type.type
# publication_type : String  -> resource_type.subtype （upload_type=publication 时必填）
ZENODO_UPLOAD_TYPES = {
    "publication", "poster", "presentation", "dataset", "image", "video",
    "software", "lesson", "physicalobject", "other",
}
ZENODO_PUBLICATION_TYPES = {
    "softwaredocumentation", "taxonomictreatment", "technicalnote",
    "thesis", "workingpaper", "other",
}
ZENODO_ACCESS_RIGHTS = {"open", "restricted", "embargoed", "closed"}


def validate_zenodo_meta(meta: dict) -> list[str]:
    """闸门 3b：.zenodo.json 必须符合 Zenodo 实际接受的 schema。

    缺陷 3 的教训：闸门 3 原本只验"能解析 + 字段齐备"，于是
    upload_type 写成嵌套对象也照样放行，而 Zenodo 侧直接拒收。
    这里按 Zenodo legacy 反序列化器的真实契约逐条验。
    """
    blockers: list[str] = []

    ut = meta.get("upload_type")
    if ut is None:
        blockers.append("缺 upload_type ⟹ Zenodo 退回默认 resource_type")
    elif isinstance(ut, dict):
        blockers.append(
            "upload_type 是对象 %r ⟹ 应为扁平字符串" % sorted(ut)
            + "（Zenodo 要 upload_type + publication_type 两个平级标量）"
        )
    elif ut not in ZENODO_UPLOAD_TYPES:
        blockers.append("upload_type=%r 不在受控词表内" % ut)

    if isinstance(ut, str) and ut == "publication":
        pt = meta.get("publication_type")
        if pt is None:
            blockers.append("upload_type=publication 时缺 publication_type（平级键）")
        elif not isinstance(pt, str):
            blockers.append("publication_type 应为字符串，实为 %r" % type(pt).__name__)
        elif pt not in ZENODO_PUBLICATION_TYPES:
            blockers.append("publication_type=%r 不在受控词表内" % pt)

    # 常见代际混用：把 subtype 塞在 upload_type 里
    if isinstance(ut, dict) and "subtype" in ut:
        blockers.append(
            "upload_type.subtype 是**新版 resource_type 内部**的键名，"
            "legacy schema 不认；应改为平级 publication_type"
        )

    ar = meta.get("access_right")
    if ar is not None and ar not in ZENODO_ACCESS_RIGHTS:
        blockers.append("access_right=%r 不在受控词表内" % ar)

    if not blockers:
        print("[OK] .zenodo.json 符合 Zenodo schema"
              "（upload_type=%r%s）"
              % (meta.get("upload_type"),
                 ", publication_type=%r" % meta["publication_type"]
                 if meta.get("publication_type") else ""))
    return blockers


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
    """闸门 3：.zenodo.json 必须在**被归档的树**里、可解析、且符合 Zenodo schema。

    v1.0.0 的元数据缺陷根因：tag 早于 .zenodo.json 的提交，联动只读 tag 指向的
    commit ⟹ Zenodo 退回 GitHub 默认值。此闸门把它变成发布前可检事件。

    v1.0.2 追加 schema 校验：能解析 ≠ Zenodo 接受。缺陷 3 即"JSON 合法但
    upload_type 代际混用"，被 Zenodo 侧以 resource_type 缺失拒收。
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
    print("[OK] .zenodo.json 可解析，关键字段齐备（title/description/creators/license）")

    return validate_zenodo_meta(meta)


def selftest() -> int:
    """闸门自测：每条规则须有正例通过、反例被拦（沿用 mf_audit 的负向测试纪律）。

    反例中 #1 是**实际踩过的那个 payload**，确保缺陷 3 不可能复发。
    """
    base = {
        "title": "t", "description": "d", "creators": [{"name": "n"}],
        "license": "cc-by-4.0", "access_right": "open",
    }
    cases = [
        ("正例: publication/workingpaper 平级标量",
         dict(base, upload_type="publication", publication_type="workingpaper"), 0),
        ("正例: software 扁平串（官方文档写法）",
         dict(base, upload_type="software"), 0),
        ("正例: presentation 无需 publication_type",
         dict(base, upload_type="presentation"), 0),
        ("反例: upload_type 嵌套对象+subtype（缺陷 3 实况）",
         dict(base, upload_type={"type": "publication", "subtype": "workingpaper"}), 1),
        ("反例: 嵌套对象且用 publication_type 子键（仍错，须平级）",
         dict(base, upload_type={"type": "publication",
                                 "publication_type": "workingpaper"}), 1),
        ("反例: publication 缺 publication_type",
         dict(base, upload_type="publication"), 1),
        ("反例: upload_type 缺失", dict(base), 1),
        ("反例: upload_type 词表外",
         dict(base, upload_type="paper"), 1),
        ("反例: publication_type 词表外",
         dict(base, upload_type="publication", publication_type="preprint"), 1),
        ("反例: access_right 词表外",
         dict(base, upload_type="software", access_right="public"), 1),
    ]
    bad_pass = bad_miss = 0
    for name, meta, expect_block in cases:
        got = len(validate_zenodo_meta(dict(meta)))
        blocked = got > 0
        ok = blocked == bool(expect_block)
        tag = "通过" if ok else "不符"
        if not ok:
            if blocked:
                bad_pass += 1   # 该拦没拦
            else:
                bad_miss += 1   # 不该拦却拦了
        print("  [%s] %s（%s）" % (tag, name, "blockers=%d" % got))
    print()
    print("裁定：%s —— 漏拦 %d / 误拦 %d / 共 %d 例"
          % ("✅ 全部符合预期" if not (bad_pass or bad_miss) else "❌",
             bad_pass, bad_miss, len(cases)))
    return 0 if not (bad_pass or bad_miss) else 1


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
    ap.add_argument("--selftest", action="store_true",
                    help="只跑 Zenodo schema 校验器的正/反例自测")
    args = ap.parse_args()

    if args.selftest:
        print("发布前置闸门 | Zenodo schema 自测")
        return selftest()

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
