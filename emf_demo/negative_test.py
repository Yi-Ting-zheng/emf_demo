#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
negative_test.py — EMF 审计器自动化负向测试 v1.0

> **自审永远查不出"漏检"，只能靠故意植入违规来暴露。**
> （README 验收流程第 2 项；本脚本把该项固化为可重复执行的工具。）

对 mf_audit.py 植入已知违规，断言审计器**逐一检出**；
任何一项漏检 ⟹ exit 1（审计器假阴性，比假阳性更危险）。

用法:
    python negative_test.py                 # 用内置违规集
    python negative_test.py --keep          # 保留临时项目（调试用）

退出码:
    0 = 全部违规被检出（审计器无假阴性）
    1 = 存在假阴性（须修复审计器）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "mf_audit.py")

# ─────────────────────────────────────────────────────────────
# 违规集：每项 = (名称, {文件名: 内容}, 期望检出的规则)
# ─────────────────────────────────────────────────────────────
CASES = [
    ("N1 模块属性赋值（CASE-02 缺陷1 类）",
     {"n1_precision.py": "import mpmath as mp\nmp.dps = 60\nprint(mp.mpf(2) ** 0.5)\n"},
     "A-04"),
    ("N2 F台账表格格式缺三要素（A-05 格式脆性）",
     {"n2_ledger.md":
      "# N2 测试台账\n\n"
      "| F-1 | 某断言被证伪 |\n|---|---|\n"
      "| 内容 | 无原断言/证伪/取代者三要素标记 |\n\n"
      "### F-2 对照（标题格式，同样缺三要素）\n\n"
      "| 项目 | 内容 |\n|---|---|\n"
      "| 记录 | 表格内无三要素字样 |\n"},
     "A-05"),
    ("N3 实验项目无 config.yaml（A-11 设计假阴性）",
     {"n3_experiment.md":
      "# N3 实验报告\n\n本文档为实验报告，含实验结果。\n"
      "主指标已测得，判假条件已定。综上，结论成立。\n"},
     "A-11"),
    ("N4 强断言句未见 TRL 标签（A-01 基线）",
     {"n4_claim.md": "# N4 测试\n\n该结论已经证实，事实上完全正确。\n"},
     "A-01"),
    ("N5 占位符未替换（A-07 基线）",
     {"n5_ph.md": "# N5 测试\n\n参数为 <待填参数> 未替换。\n"},
     "A-07"),
    ("N6 析取滑向合取（A-10 基线）",
     {"n6_disj.md": "# N6 测试\n\n综上，三项皆假。\n"},
     "A-10"),
]

# ─────────────────────────────────────────────────────────────
# 假阳性对照（FP 组）—— v1.0.3 新增
#
# 为什么必须补：原套件只测**假阴性**（植入违规 ⟹ 断言检出）。
# 一个"永不触发的规则"能通过全部 6 项负向测试 ⟹ A-04 的被证伪前提
# （mp.mp.dps 不生效）得以存活 v1.0.0 → v1.0.2 两个版本，无人察觉。
#
# **没有假阳性对照的测试套件，无法证明规则还活着。**
# 判据：以下内容**不得**被判为 FAIL（INFO 视为通过 —— 可见即可，不阻断）。
# ─────────────────────────────────────────────────────────────
FP_CASES = [
    ("FP1 mp.mp.dps 是 mpmath 官方工作 context 写法（A-04 前提已实测证伪）",
     {"fp1_mp.py": "import mpmath\nmpmath.mp.dps = 60\nprint(mpmath.mpf(2) ** 0.5)\n"},
     "A-04"),
    ("FP2 HTML 标签与数学比较片段非占位符（A-07 结构判别）",
     {"fp2_ph.md": "# FP2\n\n第一行<br>第二行；判定条件为 th 小于 pi/2 时取 a，pi/2 与 theta 另议。\n"},
     "A-07"),
    ("FP3 corrective 语境（记录该错误已被纠正）不是合取断言（A-10）",
     {"fp3_disj.md": "# FP3\n\n| F-5 | TC-4c「三项皆假」| `FALSIFIED` | 逆否命题只得析取：至多「至少一项为假」|\n"},
     "A-10"),
]

# 裁决记录豁免的三条边界（同一机制，正反双向断言）
EXEMPT_DECL = "<!-- audit-record: A-07 -->\n"
EXEMPT_CASES = [
    ("E1 声明在文件头 ⟹ 对应规则降级为 INFO（非 FAIL）",
     {"e1_rec.md": EXEMPT_DECL + "# E1\n\n参数为 <待填参数> 未替换。\n"}, "A-07", True),
    ("E2 无声明 ⟹ 不豁免（文件名不构成豁免依据）",
     {"e2_plain.md": "# E2\n\n参数为 <待填参数> 未替换。\n"}, "A-07", False),
    ("E3 声明含未知规则编号 ⟹ fail-closed，豁免不生效",
     {"e3_unknown.md": "<!-- audit-record: A-99 -->\n# E3\n\n参数为 <待填参数> 未替换。\n"}, "A-07", False),
]


def run_case(work: str, files: dict, want_rule: str) -> tuple[bool, list]:
    # v1.0.3：每个用例独占子目录 —— 否则前序用例的违规文件会污染后续断言
    # （曾致 FP2/FP3 报"假阳性"，实为测试夹具污染，非规则缺陷）
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    for name, content in files.items():
        with open(os.path.join(work, name), "w", encoding="utf-8") as f:
            f.write(content)
    r = subprocess.run([sys.executable, AUDIT, work, "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    try:
        out = json.loads(r.stdout)
    except Exception:
        return False, []
    hits = [f for f in out.get("findings", []) if f.get("rule") == want_rule]
    return len(hits) > 0, hits


def main() -> int:
    ap = argparse.ArgumentParser(description="EMF 自动化负向测试")
    ap.add_argument("--keep", action="store_true", help="保留临时项目")
    args = ap.parse_args()

    work = os.path.join(tempfile.gettempdir(), "emf_negative_test")
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)

    print("=" * 60)
    print("EMF negative_test v1.0 —— 植入违规 → 断言逐一检出")
    print("=" * 60)

    missed = []
    for name, files, want in CASES:
        ok, hits = run_case(work, files, want)
        tag = "✅ 检出" if ok else "❌ 假阴性"
        print(f"\n[{tag}] {name}   期望规则={want}  检出={len(hits)}")
        for f in hits[:3]:
            print(f"      {f['file']}:{f['line']}  {f['message']}")
        if not ok:
            missed.append(name)

    # ── 假阳性对照 ────────────────────────────────────────────
    print(f"\n{'-'*60}")
    print("假阳性对照（FP）：以下内容不得被判 FAIL")
    print(f"{'-'*60}")
    fp_bad = []
    for name, files, rule in FP_CASES:
        _, hits = run_case(work, files, rule)
        fails = [f for f in hits if f.get("severity") == "FAIL"]
        ok = not fails
        print(f"\n[{'✅ 无假阳性' if ok else '❌ 假阳性'}] {name}   规则={rule}  FAIL={len(fails)}")
        for f in fails[:3]:
            print(f"      {f['file']}:{f['line']}  {f['message']}")
        if not ok:
            fp_bad.append(name)

    # ── 裁决记录豁免边界 ──────────────────────────────────────
    print(f"\n{'-'*60}")
    print("裁决记录豁免边界（E）：声明在头 ⟹ 非 FAIL；无声明/未知编号 ⟹ 仍 FAIL")
    print(f"{'-'*60}")
    ex_bad = []
    for name, files, rule, want_pass in EXEMPT_CASES:
        _, hits = run_case(work, files, rule)
        fails = [f for f in hits if f.get("severity") == "FAIL"]
        ok = (not fails) if want_pass else bool(fails)
        tag = "✅ 符合预期" if ok else "❌ 边界失效"
        print(f"\n[{tag}] {name}   规则={rule}  FAIL={len(fails)}（期望{'非 FAIL' if want_pass else 'FAIL'}）")
        if not ok:
            ex_bad.append(name)

    print(f"\n{'='*60}")
    bad = missed + fp_bad + ex_bad
    if bad:
        print(f"裁定：❌ 假阴性 {len(missed)} / 假阳性 {len(fp_bad)} / 豁免边界 {len(ex_bad)} —— 审计器不可信，须修复：")
        for b in bad:
            print(f"      - {b}")
        if missed:
            print("      （假阴性比假阳性更危险：'零违规'输出从此毫无价值）")
        if fp_bad:
            print("      （假阳性会训练复核者忽略审计输出 —— A-04 前提被证伪却存活两版即此因）")
    else:
        print(f"裁定：✅ 假阴性 0/{len(CASES)}、假阳性 0/{len(FP_CASES)}、"
              f"豁免边界 {len(EXEMPT_CASES)}/{len(EXEMPT_CASES)} 全部符合预期")

    if not args.keep:
        shutil.rmtree(work)
    else:
        print(f"\n(临时项目保留: {work})")
    return 1 if (missed or fp_bad or ex_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
