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


def run_case(work: str, files: dict, want_rule: str) -> tuple[bool, list]:
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

    print(f"\n{'=' * 60}")
    if missed:
        print(f"裁定：❌ {len(missed)}/{len(CASES)} 违规漏检 —— 审计器假阴性，须修复：")
        for m_ in missed:
            print(f"      - {m_}")
        print("      （假阴性比假阳性更危险：'零违规'输出从此毫无价值）")
    else:
        print(f"裁定：✅ 全部 {len(CASES)} 项违规被检出，无假阴性")

    if not args.keep:
        shutil.rmtree(work)
    else:
        print(f"\n(临时项目保留: {work})")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
