#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mf_audit.py — EMF 方法论机器审计器 v1.0.3

把 00_总纲/01_元规则库 的纪律变成可执行检查。
设计原则（依 R04/R06 精神）：
  - 每条规则自身须标 TRL 层级与可靠性，不得越级宣称
  - 启发式规则只报 WARN，不报 FAIL（防止审计器自身成为 F-2 型假阳性源）
  - 无判假条件的规则不得用于阻断

v1.0.3 修正（依据：姊妹仓库 public_theorem 自审计裁决 SELF_AUDIT.md；FAIL 16 → 真问题 2 / 规则误报 14）:
  - A-04 **规则前提被实测证伪**：`mp.mp.dps = N` 判「落在非工作 context、不生效」不成立 ——
    mpmath 1.3.0 实测 `mpmath.mp` 即工作 context，赋值后 `mp.mp.dps == 50` 为 True。该模式删除
    （`import mpmath as mp; mp.dps = N` 的模块属性赋值缺陷仍由文件级模式覆盖，N1 不受影响）。
  - A-07 改**结构判别**（原为形态判据「尖括号」）：豁免 HTML 标签与数学比较片段（如 th 小于 pi/2），
    仅对具备「可被粘贴覆盖」结构特征的 token 报 FAIL。
  - A-09 规则消息不再硬编码 `03_缺口登记/`（旧布局遗留），改为回填本项目实际登记表路径。
  - A-10 增加 corrective 语境识别：记载「逆否只得析取 / 已 FALSIFIED / 逻辑错误」的文本降为 INFO
    （可见、不阻断）；此前这类**记录错误已被纠正**的文本一律 FAIL。
  - 新增**裁决记录豁免**：文件头 5 行内以 `<!-- audit-record: ... -->` 声明后，该文件对应规则的
    发现降为 INFO 并单独计数打印；声明含未知规则编号则 fail-closed（豁免不生效）。
  - negative_test.py 新增**假阳性对照**（FP 组）：此前只测假阴性 ⟹ 被证伪的规则前提可存活两个版本。

v1.0.2 修正（用户授权：立项后未及时发现的缺口，及时补正；详见 CHANGELOG #12）:
  - A-04 pattern2 双重死亡修复（反斜杠-dollar 误转义 + 逐行循环喂单行 ⟹ 多行模式永不匹配）
  - A-05 格式脆性修复（| F-n | 表格行 / 【F-n】行内格式此前静默漏检）
  - A-11 设计假阴性修复（无 config.yaml 时静默 return ⟹ 「无预注册」不报）
  - 死代码 FORBIDDEN_EFFECTIVITY_OK 移除（CHANGELOG #8 同类）
  - FRAMEWORK_DIRS 定义前移（消除使用先于定义的顺序脆弱性）
  - 新增 脚本/negative_test.py（自动化负向测试，验收流程第 2 项可重复执行）

用法:
    python mf_audit.py <项目根目录> [--strict] [--json] [--rules A-01,A-03]

退出码:
    0 = 无 FAIL（可能有 WARN）
    1 = 有 FAIL
    2 = 参数/路径错误
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

VERSION = "1.0.3"

# ─────────────────────────────────────────────────────────────
# 框架自身目录（自举豁免；v1.0.2 前移定义 —— 此前定义在 a03/a06 之后，
# 运行期可行但任何模块级调用即崩，属顺序脆弱性）
# ─────────────────────────────────────────────────────────────
FRAMEWORK_DIRS = ("00_总纲", "模板", "规范", "案例", "archive", "01_元规则库")

# ─────────────────────────────────────────────────────────────
# TRL 标签集（权威定义见 00_总纲/TRL_真值分层与升格通道.md §2）
# ─────────────────────────────────────────────────────────────
TRL_TAGS = {
    "DEFINITION", "EMPIRICAL", "HYPOTHESIS", "THEOREM",
    "THEOREM-COND", "FALSIFIED", "GAP-OPEN", "P_Axiom",
}
TRL_PATTERN = re.compile(r"`(" + "|".join(sorted(TRL_TAGS)) + r")`")

# ─────────────────────────────────────────────────────────────
# R04 封闭性词汇触发器
#
# 分两档（v1.0 修正）：
#   HARD   —— 无歧义的普遍量化词，一律检查
#   AMBIG  —— 中文里高度歧义的词（"唯一"），仅在「非导航语境 + 非标题」时检查。
#             "唯一登记处/唯一权威文件" 是**簿记指定**（指向一个文件），
#             不是真值主张，不属 R04 的打击对象。
# ─────────────────────────────────────────────────────────────
CLOSURE_HARD = [
    "必为", "必不", "完全", "彻底", "终局", "封闭", "穷尽",
    "完备", "必然", "永远", "一律", "无一例外", "不可破", "全封闭",
]
CLOSURE_AMBIG = ["唯一"]
# 导航语境：词指向"文件/位置"而非"事实"
NAVIGATIONAL = re.compile(r"(文件|处|位置|入口|页|表|栏目|通道|落点|路径|目录|项)")
# 同段需出现的自审证据（提示性，非强制）
AUDIT_EVIDENCE = [
    "判据", "定义", "多源", "互斥", "穷尽", "完备", "自审",
    "GAP-01", "GAP-02", "完备性未证", "未证",
]

# ─────────────────────────────────────────────────────────────
# E5 元层禁用表述（03_规范/立项准入清单_E1-E5.md §5.6）
# ─────────────────────────────────────────────────────────────
FORBIDDEN_EFFECTIVITY = [
    r"经验证有效", r"已验证有效", r"实验表明有效", r"已被验证(?:为)?(?:有效|正确)",
    r"证明了(?:本|本方法|该方法)方法论", r"科学范式(?!的|候选|级)",
    r"成为范式", r"全面优于", r"完全杜绝",
]
# v1.0.2: 死代码 FORBIDDEN_EFFECTIVITY_OK 已移除 —— 定义后从未使用
# （CHANGELOG #8 "死分支制造覆盖率幻觉"同类；❌ 案例由 NEG_CONTEXT 兜住）。
# 占位符未替换检测
PLACEHOLDER = re.compile(r"<[A-Za-z_一-鿿][^>\n]{0,80}>")

# ─────────────────────────────────────────────────────────────
# v1.0.3 结构判据（A-07）：形态 → 结构
#
# 根因（public_theorem/SELF_AUDIT.md §4，五次复发）：以**形态**（尖括号）而非
# **结构**（是否具备"可被粘贴覆盖"的特征）为判据的规则，一旦该形态成为被记录的对象，
# 规则即恒触发 —— 记录行为本身制造违规。
#
# 结构判据：token 是否像"一个待填槽位"。
#   - HTML 标签（<br>、</p> …）      → 结构上不是槽位
#   - 数学比较片段（th<pi/2）        → `<` 是运算符，`>` 是行尾，闭合成 token 属巧合
#   - 裸数学符号（<pi>、<theta>）    → 同上
#   - 其余（含下划线/空格/中文/斜杠结尾）→ 仍是槽位 ⟹ FAIL
# 已知残余局限：`<n>` 这类单字母小写 token 仍被判为占位符（保守方向，宁误报不漏报）。
# ─────────────────────────────────────────────────────────────
HTML_TAGS = {
    "br", "p", "hr", "b", "i", "em", "strong", "code", "pre", "a", "ul", "ol",
    "li", "table", "thead", "tbody", "tr", "td", "th", "div", "span", "sub",
    "sup", "img", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "kbd",
}
# 须含运算符才算数学片段：pi/2、th^2、x_1 —— 单字母不豁免（见残余局限）
MATH_FRAGMENT = re.compile(r"^[a-z0-9]+[/^_][a-z0-9]+$")
MATH_SYMBOLS = {
    "pi", "th", "theta", "delta", "eps", "epsilon", "lambda", "gamma",
    "alpha", "beta", "phi", "mu", "nu", "rho", "sigma", "tau", "omega",
}


def is_placeholder_token(inner: str) -> bool:
    """A-07 结构判据：True = 像待填槽位（FAIL）；False = HTML/数学/代码跨距形态。"""
    low = inner.lower()
    # 含反引号 ⟹ 该跨度跨越了代码 span（`<pi/2` 直到下一个 `>` 才是真正闭合），
    # 结构上是行文/代码，不是待填槽位。v1.0.3 前这条曾致勘误附录 3 处误报。
    if "`" in inner:
        return False
    if low in HTML_TAGS:
        return False
    if MATH_FRAGMENT.match(low):
        return False
    if low in MATH_SYMBOLS:
        return False
    return True


# ─────────────────────────────────────────────────────────────
# v1.0.3 裁决记录豁免（R00 精神：豁免必须可被 grep 统计、必须 fail-closed）
#
# 动机：裁决记录必须复述规则的触发形态才能被审查，于是记录本身必然触发规则
#       （SELF_AUDIT.md §4 的五次复发）。不给窄豁免，审计结果会随记录行为单调增长，
#       "零违规"将永不可达 —— 指标被记录行为污染即失去度量资格。
#
# 约束（刻意收窄，防止豁免沦为免检通道）：
#   1. 须在文件**头 5 行**内显式声明 `<!-- audit-record: A-07,A-10 -->`
#   2. 只豁免**声明中列出的规则**在该文件内的发现，不豁免该文件的其他内容
#   3. 豁免后的发现**降为 INFO 而非删除**，并在汇总中单独计数打印（豁免 12 条 ≠ 没有 12 条）
#   4. 声明含**未知规则编号** ⟹ 整个声明 fail-closed（豁免不生效）+ WARN
#   5. 无声明的文件（哪怕叫 SELF_AUDIT.md）**不豁免** —— 由负向测试 FP-N3 守住
#
# 已知局限（诚实登记）：一个刻意声明自身为裁决记录的文件仍可藏问题。
# 缓解手段 = 上述第 3 条（计数可见）与第 4 条（未知编号失效）。
# ─────────────────────────────────────────────────────────────
AUDIT_RECORD_DECL = re.compile(r"<!--\s*audit-record:\s*([^>]*?)-->")
AUDIT_RECORD_HEAD = 5
AUDIT_RECORD_COUNT: Counter = __import__("collections").Counter()
_DECL_CACHE: dict[str, tuple[set[str], set[str]]] = {}


def audit_record_decl(root: str, r: str) -> tuple[set[str], set[str]]:
    """返回 (已声明规则, 未知规则)。仅看文件头 AUDIT_RECORD_HEAD 行。"""
    if r in _DECL_CACHE:
        return _DECL_CACHE[r]
    t = read(os.path.join(root, r.replace("/", os.sep)))
    head = "\n".join(t.splitlines()[:AUDIT_RECORD_HEAD])
    m = AUDIT_RECORD_DECL.search(head)
    if not m:
        res = (set(), set())
    else:
        raw = {x.strip() for x in m.group(1).split(",") if x.strip()}
        res = (raw & set(RULES), raw - set(RULES))
    _DECL_CACHE[r] = res
    return res


def apply_audit_record_exemption(root: str, out: list[Finding]) -> None:
    """裁决记录豁免：在 run() 末尾统一施加，避免各规则各自实现而遗漏。"""
    warned: set[str] = set()
    for f in list(out):
        if f.severity not in ("FAIL", "WARN"):
            continue
        declared, unknown = audit_record_decl(root, f.file)
        if unknown and f.file not in warned:
            warned.add(f.file)
            out.append(Finding(
                "A-11", "WARN", "EMPIRICAL", f.file, 1,
                f"裁决记录声明含未知规则编号 {sorted(unknown)}；该声明 fail-closed，豁免未生效",
                f.snippet[:110],
                note="声明只接受 --list-rules 中已登记的规则编号，防止豁免沦为免检通道。",
            ))
            continue
        if f.rule in declared:
            f.severity = "INFO"
            f.note = ("[裁决记录豁免] " + f.note).strip()
            AUDIT_RECORD_COUNT[f.rule] += 1


SEVERITY = {"FAIL": 2, "WARN": 1, "INFO": 0}

# ─────────────────────────────────────────────────────────────
# 显式豁免标记（R00：豁免必须留痕，禁止暗箱容忍）
#   行内出现 [TRL-OK] / [R04-OK] 即视为"已人工确认并豁免"，
#   豁免本身可被 grep 统计 —— 豁免率过高时须人工复审。
# ─────────────────────────────────────────────────────────────
EXEMPT = {
    "A-01": re.compile(r"\[TRL-OK\]"),
    "A-02": re.compile(r"\[TRL-OK\]"),
    "A-03": re.compile(r"\[R04-OK\]"),
    "A-04": re.compile(r"\[R05-OK\]"),
    "A-06": re.compile(r"\[E5-OK\]"),
    # A-10 自 v1.0 起就调用 exempt()，但此前 EXEMPT 无此键 ⟹ 该调用恒返回 False
    # （死分支，制造覆盖率幻觉）。A-10 改扫引用块后需要显式逃生阀，故正式登记 [R11-OK]。
    "A-10": re.compile(r"\[R11-OK\]"),
}
EXEMPT_COUNT: Counter = __import__("collections").Counter()


def exempt(rid: str, line: str) -> bool:
    pat = EXEMPT.get(rid)
    if pat and pat.search(line):
        EXEMPT_COUNT[rid] += 1
        return True
    return False



@dataclass
class Finding:
    rule: str
    severity: str
    trl: str
    file: str
    line: int
    message: str
    snippet: str = ""
    note: str = ""


@dataclass
class RuleMeta:
    rid: str
    name: str
    trl: str            # 该规则实现的置信度
    reliability: str    # machine-heuristic / machine-strict / manual-only
    blocks: bool        # True => severity FAIL 时退出码 1


# ─────────────────────────────────────────────────────────────
# 规则注册表
# ─────────────────────────────────────────────────────────────
RULES: dict[str, RuleMeta] = {
    "A-01": RuleMeta("A-01", "标签强制分离(R01)", "EMPIRICAL", "machine-heuristic", False),
    "A-02": RuleMeta("A-02", "前提绑定/裸结论(R02)", "EMPIRICAL", "machine-heuristic", False),
    "A-03": RuleMeta("A-03", "封闭性词汇自审(R04)", "EMPIRICAL", "machine-heuristic", False),
    "A-04": RuleMeta("A-04", "数值守卫(R05)", "EMPIRICAL", "machine-heuristic", False),
    "A-05": RuleMeta("A-05", "台账三要素(R07)", "DEFINITION", "machine-strict", True),
    "A-06": RuleMeta("A-06", "元层有效性表述(E5§5.6)", "DEFINITION", "machine-strict", True),
    "A-07": RuleMeta("A-07", "占位符未替换", "DEFINITION", "machine-strict", True),
    "A-08": RuleMeta("A-08", "台账计数一致性", "DEFINITION", "machine-strict", True),
    "A-09": RuleMeta("A-09", "GAP-OPEN 唯一落点", "DEFINITION", "machine-strict", True),
    "A-10": RuleMeta("A-10", "析取不可滑向合取(R11)", "DEFINITION", "machine-strict", True),
    "A-11": RuleMeta("A-11", "预注册存在性(E1)", "DEFINITION", "machine-strict", False),
}

MD_EXT = (".md",)
CODE_EXT = (".py",)
SKIP_DIR = {".git", "node_modules", "__pycache__", ".venv", "archive", ".pytest_cache"}


def read(path: str) -> str:
    try:
        return io.open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def walk(root: str, exts: Iterable[str], skip_dirs=SKIP_DIR) -> Iterable[str]:
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in skip_dirs]
        for f in fn:
            if f.endswith(tuple(exts)):
                yield os.path.join(dp, f)


def rel(root: str, p: str) -> str:
    return os.path.relpath(p, root).replace("\\", "/")


# ─────────────────────────────────────────────────────────────
# A-01 标签强制分离（启发式）
# 只对"强断言行"报警：含限定词且不含 TRL 标签的行
# ─────────────────────────────────────────────────────────────
STRONG_CLAIM = re.compile(
    r"(证明|定理|必然|一定|肯定会|可以确认|已经证实|事实上|综上)"
)
META_LINE = re.compile(r"^\s*(#|>|\||-\s|创建|修订|状态|日期|作者|真值层级|归档标签|\*本文档)")

# 规范性条文属「规则层」而非「断言层」——规则本身不需要 TRL 标签。
# 这是分层原则的直接推论，不是为降噪而设的例外。
NORMATIVE = re.compile(
    r"(必须|不得|禁止|严禁|应当|应该|须|不可|只能|仅限|一律禁止|条文|纪律|注意：|⚠)"
)
# 显式谦逊标记 = 已在陈述其未证状态，无需再补标签
HUMBLE = re.compile(r"(未证|无证明|无证据|未穷尽|未封闭|待验|存疑|不成立|非结论)")


def a01(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        t = read(p)
        for i, line in enumerate(t.splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("```"):
                continue
            if META_LINE.match(s):
                continue
            if NORMATIVE.search(s) or HUMBLE.search(s):
                continue
            if not STRONG_CLAIM.search(s):
                continue
            if TRL_PATTERN.search(s):
                continue
            if PLACEHOLDER.search(s):
                continue
            # 只对"独立句"报警：须以句号/分号收尾，碎片续写不报
            if not re.search(r"[。；;](\*\*)?\s*$", s):
                continue
            # 结构图/表格行不报
            if re.search(r"[─═│┌└├→▶←]", s):
                continue
            if exempt("A-01", line):
                continue
            out.append(Finding(
                "A-01", "WARN", "EMPIRICAL", rel(root, p), i,
                "强断言句未见 TRL 标签",
                s[:110],
                note="R01。确认非独立断言则加 [TRL-OK] 显式豁免。",
            ))


# ─────────────────────────────────────────────────────────────
# A-02 前提绑定（启发式）
# ─────────────────────────────────────────────────────────────
HEDGED = re.compile(
    r"(若|如果|假设|前提|设|令|suppose|假设下|在此前|前提是|conditional|given)"
)


def a02(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        t = read(p)
        for i, line in enumerate(t.splitlines(), 1):
            s = line.strip()
            if not s.startswith(">"):
                continue
            if not STRONG_CLAIM.search(s):
                continue
            if HEDGED.search(s) or TRL_PATTERN.search(s):
                continue
            if NORMATIVE.search(s) or HUMBLE.search(s):
                continue
            if PLACEHOLDER.search(s):
                continue
            if not re.search(r"[。；;](\*\*)?\s*$", s):
                continue
            if exempt("A-02", line):
                continue
            out.append(Finding(
                "A-02", "WARN", "EMPIRICAL", rel(root, p), i,
                "引用块中的强断言句未见前提标记(若/假设/设)",
                s[:110],
                note="R02：裸结论须补前提。确认非独立断言则加 [TRL-OK]。",
            ))


# ─────────────────────────────────────────────────────────────
# A-03 封闭性词汇自审（R04）
# ─────────────────────────────────────────────────────────────
def a03(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        r = rel(root, p)
        # 框架自身文档（规范/模板/案例/归档/元规则库）的散文不是「项目实例断言」，
        # 豁免；否则框架将被自己的规则淹没（自举悖论，见 GAP-01 §6 开放性）。
        if any(x in r for x in FRAMEWORK_DIRS):
            continue
        t = read(p)
        lines = t.splitlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("```"):
                continue
            hits = [w for w in CLOSURE_HARD if w in s]
            # AMBIG 档：仅在「非导航语境 + 非标题 + 含断言动词」时计入
            amb = [w for w in CLOSURE_AMBIG if w in s]
            if amb and not s.startswith("#") and not NAVIGATIONAL.search(s) \
                    and STRONG_CLAIM.search(s):
                hits += amb
            if not hits:
                continue
            # 自身规则条文中的举例不算违规：若同段命中 AUDIT_EVIDENCE 则视为已自审
            # 显式标记优先：豁免必须可被统计，否则退化为暗箱容忍（R00）
            if exempt("A-03", line):
                continue
            ctx = "\n".join(lines[max(0, i - 4): i + 4])
            if any(ev in ctx for ev in AUDIT_EVIDENCE):
                continue
            if PLACEHOLDER.search(s):
                continue
            out.append(Finding(
                "A-03", "WARN", "EMPIRICAL", rel(root, p), i,
                f"封闭性词汇 {hits[:3]} 未见同段自审证据",
                s[:110],
                note="R04：回查判据定义本身。确认已自审则加 [R04-OK]。",
            ))


# ─────────────────────────────────────────────────────────────
# A-04 数值守卫（R05）
# v1.0.2 修正：多行模式拆出为文件级检查 —— 此前混在逐行循环里，
# pattern.search(line) 只喂单行 ⟹ 含 \n 的模式永不匹配（双重死亡：
# 且原式中 \$ 被转义成字面美元符，本意是行尾锚）。
#
# v1.0.3 **删除** `mp.mp.dps = N` 判据 —— 其前提已被实测证伪（不得以"疑似"结案）：
#   mpmath 1.3.0：`mpmath.mp` **就是**工作 context；执行 `mp.mp.dps = 50` 后
#   读回 `mp.mp.dps` 为 50 ⟹ 设置**确实生效**。该写法是官方推荐写法。
#   仍存的真实缺陷是**模块属性赋值**（见下方文件级模式，N1 覆盖）。
# ─────────────────────────────────────────────────────────────
BAD_PRECISION = [
    (re.compile(r"float\(\s*iv"), "区间端点经 float()，宽度会归零（CASE-02 缺陷2）"),
]
# 文件级多行模式：对全文 finditer，逐行循环永远无法匹配多行结构
BAD_PRECISION_FILE = [
    (re.compile(r"^\s*import\s+mpmath\s+as\s+mp\s*$\n(?:.*\n)*?^\s*mp\.dps\s*=", re.M),
     "模块属性赋值（import mpmath as mp 后 mp.dps=），不影响计算（CASE-02 缺陷1）"),
]
EPS_AS_ERR = re.compile(r"(strict|>|>=|<|<=)\s*eps\b")


def a04(root: str, out: list[Finding]) -> None:
    for p in walk(root, CODE_EXT):
        t = read(p)
        # 文件级多行模式（v1.0.2 修正：对全文匹配，不再喂单行）
        for pat, msg in BAD_PRECISION_FILE:
            for m in pat.finditer(t):
                line_no = t[:m.start()].count("\n") + 1
                if exempt("A-04", t.splitlines()[line_no - 1]):
                    continue
                out.append(Finding(
                    "A-04", "WARN", "EMPIRICAL", rel(root, p), line_no, msg,
                    m.group(0)[:110].replace("\n", " ⏎ "),
                    note="R05：改用守卫 A（字面量比对）/ 守卫 B（双精度一致）。",
                ))
        for i, line in enumerate(t.splitlines(), 1):
            for pat, msg in BAD_PRECISION:
                if pat.search(line):
                    if exempt("A-04", line):
                        continue
                    out.append(Finding(
                        "A-04", "WARN", "EMPIRICAL", rel(root, p), i, msg,
                        line.strip()[:110],
                        note="R05：改用守卫 A（字面量比对）/ 守卫 B（双精度一致）。",
                    ))
            if EPS_AS_ERR.search(line) and "eps" in line:
                if exempt("A-04", line):
                    continue
                out.append(Finding(
                    "A-04", "WARN", "EMPIRICAL", rel(root, p), i,
                    "判据疑似用外扩余量 eps 代替真实误差界（区间宽度）",
                    line.strip()[:110],
                    note="R05：真实误差界应为区间实际宽度 W。",
                ))


# ─────────────────────────────────────────────────────────────
# A-05 台账三要素（R07）
# 严格要求：F-n 条目须含三要素标记
# v1.0.2 修正：F-n 条目格式扩展 —— 此前只认 `### F-n` 标题，
# `| F-n |` 表格行 / 【F-n】行内格式静默漏检（格式脆性，负向测试确认）。
# 并补围栏跳过：模板原文在 fence 内（与 a06/a07/a10 一致）。
# ─────────────────────────────────────────────────────────────
THREE_ELEMENTS = ["原断言", "证伪", "取代者"]
F_HEADINGS = [
    re.compile(r"^###\s*F-(\d+[a-z]?)\b.*$", re.M),        # ### F-n 标题
    re.compile(r"^\|\s*\**F-(\d+[a-z]?)\**\b.*$", re.M),   # | F-n | 表格行
    re.compile(r"【F-(\d+[a-z]?)】", re.M),                 # 【F-n】行内
]


def a05(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        t = read(p)
        lines = t.splitlines()
        hits = []                      # (fid, block_start, line_no)
        for pat in F_HEADINGS:
            for m in pat.finditer(t):
                fid = m.group(1)
                line_no = t[:m.start()].count("\n") + 1
                if _in_fence(lines, line_no - 1):
                    continue           # 围栏内为模板原文，豁免
                hits.append((fid, m.start(), line_no))
        for fid, start, line_no in hits:
            # 块终点 = 任意 F-n 格式的下一个命中（跨格式），上限 2000 字符
            nxt = [s for _, s, _ in hits if s > start]
            end = min(nxt) if nxt else start + 2000
            block = t[start:end]
            miss = [e for e in THREE_ELEMENTS if e not in block]
            if miss:
                out.append(Finding(
                    "A-05", "FAIL", "DEFINITION", rel(root, p), line_no,
                    f"F-{fid} 缺三要素: {miss}",
                    lines[line_no - 1][:110],
                    note="R07：撤回必须三要素写全（原文/原因/取代者）。",
                ))


# ─────────────────────────────────────────────────────────────
# A-06 元层有效性表述禁令（E5 §5.6）
# ─────────────────────────────────────────────────────────────
NEG_CONTEXT = re.compile(r"(禁止|不得|不可|严禁|不构成|不能|未被|从未|❌|非|≠|\\ne\b|最多|仅能)")


def a06(root: str, out: list[Finding]) -> None:
    # 规范/模板/案例类文档天然含禁用表述**原文**（反例清单、词表、判据描述），
    # 属 SPEC §4 的自举豁免；E5/GAP-01 亦为条文载体。
    EXEMPT_FILES = FRAMEWORK_DIRS + ("立项准入清单", "GAP-01_元方法论自指缺口")
    for p in walk(root, MD_EXT):
        r = rel(root, p)
        if any(x in r for x in EXEMPT_FILES):
            continue
        t = read(p)
        lines = t.splitlines()
        for i, line in enumerate(lines, 1):
            # 只跳过围栏代码块**内部**（模板原文）。
            # ⚠ 不可再按 startswith(('>','#','|','```')) 根式跳行——本框架的
            #   裁定/结论恰恰写在引用块与表格里，整块跳过会造成阻断级**假阴性**
            #   （见 CHANGELOG 判据修正记录 #11）。
            if _in_fence(lines, i - 1):
                continue
            s = line.strip()
            for pat in FORBIDDEN_EFFECTIVITY:
                for m in re.finditer(pat, line):
                    pre = line[max(0, m.start() - 25): m.start()]
                    if NEG_CONTEXT.search(pre):
                        continue
                    if exempt("A-06", line):
                        break
                    out.append(Finding(
                        "A-06", "FAIL", "DEFINITION", r, i,
                        "疑似对方法论自身作未经验证的有效性主张",
                        s[:110],
                        note="E5§5.6：未过 E5 对照 ⟹ 只能表述为结构可审计/案例级证据。"
                             "反例请写成显式否定句，或加 [E5-OK]。",
                    ))
                    break


# ─────────────────────────────────────────────────────────────
# A-07 占位符未替换
# 仅扫「项目实例文件」；规范/模板/案例/归档 天然含占位符，豁免。
# 围栏代码块内为模板原文，豁免。
# （FRAMEWORK_DIRS 已于 v1.0.2 前移至模块顶部常量区）
# ─────────────────────────────────────────────────────────────
def _in_fence(lines: list[str], idx: int) -> bool:
    depth = 0
    for j in range(idx - 1, -1, -1):
        if lines[j].strip().startswith("```"):
            depth += 1
    return depth % 2 == 1


def a07(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT + (".yaml", ".yml")):
        r = rel(root, p)
        if any(x in r for x in FRAMEWORK_DIRS):
            continue
        t = read(p)
        lines = t.splitlines()
        for i, line in enumerate(lines, 1):
            ms = list(PLACEHOLDER.finditer(line))
            if not ms:
                continue
            if _in_fence(lines, i - 1):
                continue
            if "[PH-OK]" in line:
                EXEMPT_COUNT["A-07"] += 1
                continue
            # v1.0.3 结构判别：逐 token 判"是否具备可被粘贴覆盖的结构特征"，
            # 而非只看是否存在尖括号（形态判据 → 记录即触发，五次复发）。
            real = [m.group(0) for m in ms if is_placeholder_token(m.group(0)[1:-1])]
            if not real:
                continue
            out.append(Finding(
                "A-07", "FAIL", "DEFINITION", r, i,
                f"占位符未替换: {', '.join(real[:3])}", line.strip()[:110],
                note="实例文件不得留占位符。确为示例请加 [PH-OK] 或移入 02_模板/。",
            ))


# ─────────────────────────────────────────────────────────────
# A-08 台账计数一致性
# ─────────────────────────────────────────────────────────────
def a08(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        t = read(p)
        if "计数合计" not in t:
            continue
        # 抓声明的计数
        nums = {}
        for st in ["FALSIFIED", "RESOLVED", "RETRACTED"]:
            m = re.search(st + r"[^\d]{0,12}\|\s*\**(\d+)\**\s*\|", t)
            if m:
                nums[st] = int(m.group(1))
        m = re.search(r"计数合计[^\d]{0,12}\|\s*\**(\d+)\**", t)
        if not m:
            continue
        total = int(m.group(1))
        s = sum(nums.values())
        if nums and s != total:
            out.append(Finding(
                "A-08", "FAIL", "DEFINITION", rel(root, p), t[:m.start()].count("\n") + 1,
                f"计数不一致：分项和={s}，声明合计={total}",
                m.group(0),
                note="重算台账或修正声明。",
            ))
        # 计数合计 vs 实际 F-n 条目数
        actual = len(set(re.findall(r"^###\s*F-(\d+[a-z]?)", t, re.M)))
        if actual and total and abs(actual - total) > 0:
            # 若两者差异大给 WARN（小差异可能是合并编号）
            if abs(actual - total) > 3:
                out.append(Finding(
                    "A-08", "WARN", "EMPIRICAL", rel(root, p), 1,
                    f"实际 F-n 条目数={actual}，与声明合计={total} 差异较大",
                    "", note="可能为口径差异（如脚本缺陷合并计入）。人工核对。",
                ))


# ─────────────────────────────────────────────────────────────
# A-09 缺口记录唯一落点
# 注意：GAP-OPEN 作为「标签名」出现在标签集定义/规则条文中是合法的。
# 本规则只禁止「缺口记录」散落——即 `### GAP-nn` 标题或 GAP-nn 台账行
# 出现在登记表以外的文件。
# ─────────────────────────────────────────────────────────────
GAP_DECL = [
    re.compile(r"^#{1,6}\s*GAP-\d+"),                 # ### GAP-01 …
    re.compile(r"^\|[\s|]*GAP-\d+[\s|]*\|"),          # | GAP-01 | … 台账行
]
# 注意：`| `GAP-OPEN` | 已知开放… |` 这类**标签集定义行**不是缺口记录，合法。


GAP_REGISTRY = re.compile(r"缺口登记|GAP[-_]?登记|gap_register")


def a09(root: str, out: list[Finding]) -> None:
    # v1.0.3：登记表路径**从本项目实测回填**，不再硬编码 `03_缺口登记/`
    # （该路径是旧布局遗留，在 PI^π 类项目中实际为 04_缺口/缺口登记.md，
    #  硬编码会让规则消息与项目实际不符 ⟹ 复核者被误导）。
    registry = None
    for q in walk(root, MD_EXT):
        rq = rel(root, q)
        if GAP_REGISTRY.search(rq):
            registry = rq
            break
    registry_hint = registry or "本项目未发现缺口登记表（文件名须含 缺口登记/gap_register）"
    for p in walk(root, MD_EXT):
        r = rel(root, p)
        if GAP_REGISTRY.search(r) or "GAP-01_元方法论自指缺口" in r:
            continue  # 登记表豁免
        if any(x in r for x in FRAMEWORK_DIRS):
            continue  # 模板/规范内为模板原样
        t = read(p)
        for i, line in enumerate(t.splitlines(), 1):
            for pat in GAP_DECL:
                if pat.search(line.strip()):
                    out.append(Finding(
                        "A-09", "FAIL", "DEFINITION", r, i,
                        "缺口记录声明出现在登记表之外",
                        line.strip()[:110],
                        note=f"R01：缺口记录只能落在登记表（实测：{registry_hint}）；"
                             "他处只能以文字引用 GAP-nn 编号。",
                    ))
                    break


# ─────────────────────────────────────────────────────────────
# A-10 析取不可滑向合取（R11）
# ─────────────────────────────────────────────────────────────
BAD_DISJ = re.compile(
    r"(三项皆假|皆假|三个(?:小)?实例同时证伪|同时证伪)"
)
# v1.0.3 corrective 语境：记录「该错误已被纠正」的文本不是断言，
# 此前一律 FAIL ⟹ 6 处 FALSIFIED 台账/裁定记录被判违规（审计器制造违规）。
# 判据为**语境词**（逆否/析取/纠错/逻辑错误…），非"是否为已知坏句"。
CORRECTIVE = re.compile(
    r"(逆否|析取|合取|纠错|自纠|误写|逻辑错误|已被证伪|已证伪|已纠正|纠正|"
    r"FALSIFIED|至多|至少一项|不得写为|只能写为|须写为)"
)


def _in_backticks(line: str, m: re.Match) -> bool:
    """反引号包裹的内容是**字面量**（模式名/代码/术语），不是主张。"""
    a, b = m.start(), m.end()
    return a > 0 and b < len(line) and line[a - 1] == "`" and line[b] == "`"


def a10(root: str, out: list[Finding]) -> None:
    for p in walk(root, MD_EXT):
        r = rel(root, p)
        # 规范/模板/案例内含规则自身的关键词原文，属自举豁免（见 SPEC §4）
        if any(x in r for x in FRAMEWORK_DIRS):
            continue
        t = read(p)
        lines = t.splitlines()
        for i, line in enumerate(lines, 1):
            # 只跳过围栏代码块内部；引用块/表格行**照扫**
            # （裁定与结论表正是本规则主战场，见 CHANGELOG 判据修正记录 #8/#11）。
            if _in_fence(lines, i - 1):
                continue
            s = line.strip()
            m = BAD_DISJ.search(s)
            if not m or _in_backticks(s, m):
                continue
            if NEG_CONTEXT.search(s) or "绝不能" in s or "不可" in s or "禁止" in s:
                continue
            if exempt("A-10", line):
                continue
            # v1.0.3：corrective 语境降 INFO（可见、不阻断）
            sev = "INFO" if CORRECTIVE.search(s) else "FAIL"
            out.append(Finding(
                "A-10", sev, "DEFINITION", r, i,
                "疑似将逆否的析取结论误写为合取" + ("（corrective 语境，仅提示）" if sev == "INFO" else ""),
                s[:110],
                note="R11：¬(P∧Q∧R)=¬P∨¬Q∨¬R，只能推出'至少一项为假'。",
            ))


# ─────────────────────────────────────────────────────────────
# A-11 预注册存在性（E1）
# v1.0.2 修正：无 config.yaml 时不再静默 return —— 先探测项目是否
# 含实验标记（实验报告/预注册/对照试验/主指标/判假条件），有则
# WARN「无预注册文件」（设计假阴性，负向测试确认）。
# ─────────────────────────────────────────────────────────────
EXPERIMENT_MARKERS = re.compile(
    r"(实验报告|预注册|对照试验|对照实验|主指标|判假条件|prereg|A/B ?测试|ablation)"
)


def a11(root: str, out: list[Finding]) -> None:
    # 若项目根下有 config.yaml 则校验 prereg 字段
    cfg = os.path.join(root, "config.yaml")
    if not os.path.exists(cfg):
        # v1.0.2: 无 config 时探测实验标记 —— 有则报「无预注册」
        # CHANGELOG/哈希锁为框架簿记文件，非实验报告，豁免（自举边界）。
        for p in walk(root, MD_EXT + (".yaml", ".yml")):
            r = rel(root, p)
            if any(x in r for x in FRAMEWORK_DIRS) or "CHANGELOG" in r:
                continue
            t = read(p)
            if EXPERIMENT_MARKERS.search(t):
                if "[PH-OK]" in t:
                    EXEMPT_COUNT["A-11"] += 1
                    continue
                out.append(Finding(
                    "A-11", "WARN", "EMPIRICAL", r, 1,
                    "项目含实验标记但根目录无 config.yaml（无预注册文件）",
                    "", note="E1：实验立项前须锁定 config.yaml（指标/分组/阈值/假设）。",
                ))
                break
        return
    t = read(cfg)
    for field in ["primary_metric", "falsification_condition", "prereg_hash"]:
        if field not in t:
            out.append(Finding(
                "A-11", "WARN", "EMPIRICAL", "config.yaml", 1,
                f"预注册缺字段 {field}",
                "", note="E1：目标/主指标/判假条件须执行前锁死。",
            ))
    if re.search(r"prereg_hash:\s*<", t):
        out.append(Finding(
            "A-11", "FAIL", "DEFINITION", "config.yaml", 1,
            "prereg_hash 未填（仍为占位符）",
            "", note="运行 scaffold.py 或手动填入哈希。",
        ))


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────
def run(root: str, only: set[str] | None) -> list[Finding]:
    out: list[Finding] = []
    disp = {
        "A-01": a01, "A-02": a02, "A-03": a03, "A-04": a04, "A-05": a05,
        "A-06": a06, "A-07": a07, "A-08": a08, "A-09": a09, "A-10": a10,
        "A-11": a11,
    }
    for rid, fn in disp.items():
        if only and rid not in only:
            continue
        fn(root, out)
    # v1.0.3：裁决记录豁免统一在此施加（各规则不自行实现，避免遗漏）
    apply_audit_record_exemption(root, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="EMF 方法论机器审计器")
    ap.add_argument("root", help="项目根目录")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--rules", default="", help="仅跑指定规则, 逗号分隔")
    ap.add_argument("--list-rules", action="store_true")
    args = ap.parse_args()

    if args.list_rules:
        print(f"EMF mf_audit v{VERSION}")
        for rid, m in RULES.items():
            print(f"  {rid}  [{m.trl}/{m.reliability}]  "
                  f"{'BLOCK' if m.blocks else 'warn'}  {m.name}")
        return 0

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"[ERROR] 目录不存在: {root}", file=sys.stderr)
        return 2

    only = set(x.strip() for x in args.rules.split(",") if x.strip()) or None
    findings = run(root, only)

    fails = [f for f in findings if f.severity == "FAIL"]
    warns = [f for f in findings if f.severity == "WARN"]
    infos = [f for f in findings if f.severity == "INFO"]

    if args.json:
        print(json.dumps({
            "version": VERSION,
            "root": root,
            "counts": {"FAIL": len(fails), "WARN": len(warns), "INFO": len(infos)},
            "verdict": "FAIL" if fails else ("WARN" if warns else "PASS"),
            "findings": [f.__dict__ for f in findings],
        }, ensure_ascii=False, indent=2))
        return 1 if (fails or (warns and args.strict)) else 0
    else:
        print(f"\n=== EMF mf_audit v{VERSION} ===")
        print(f"target: {root}")
        for sev, group in (("FAIL", fails), ("WARN", warns), ("INFO", infos)):
            if not group:
                continue
            print(f"\n--- {sev} ({len(group)}) ---")
            by_rule: dict[str, list[Finding]] = {}
            for f in group:
                by_rule.setdefault(f.rule, []).append(f)
            for rid, items in sorted(by_rule.items()):
                m = RULES.get(rid)
                name = m.name if m else "?"
                print(f"\n[{rid}] {name}  ×{len(items)}")
                for f in items[:12]:
                    print(f"  {f.file}:{f.line}  {f.message}")
                    if f.snippet:
                        print(f"      | {f.snippet}")
                    if f.note:
                        print(f"      → {f.note}")
                if len(items) > 12:
                    print(f"  ... 另 {len(items)-12} 条")

    print(f"\n{'='*50}")
    print(f"FAIL={len(fails)}  WARN={len(warns)}  INFO={len(infos)}")
    if EXEMPT_COUNT:
        tot = sum(EXEMPT_COUNT.values())
        print(f"显式豁免={tot}  " + "  ".join(f"{k}:{v}" for k, v in sorted(EXEMPT_COUNT.items())))
        if tot > 3:
            print("⚠️  豁免率偏高，须人工复审（R00：豁免必须可被 grep 统计）")
    if AUDIT_RECORD_COUNT:
        n = sum(AUDIT_RECORD_COUNT.values())
        print(f"裁决记录豁免={n}  " + "  ".join(f"{k}:{v}" for k, v in sorted(AUDIT_RECORD_COUNT.items())))
        print("   （豁免≠无问题：这些条目已降为 INFO 并在上方 INFO 段逐条可见）")
    if fails:
        print("裁定：❌ 有阻断级违规（FAIL）")
    elif warns and args.strict:
        print("裁定：❌ strict 模式下 WARN 视为失败")
    elif warns:
        print("裁定：⚠️  无 FAIL，但有启发式告警（须人工确认）")
    else:
        print("裁定：✅ 无违规")
    print(f"{'='*50}\n")
    if fails:
        return 1
    if warns and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
