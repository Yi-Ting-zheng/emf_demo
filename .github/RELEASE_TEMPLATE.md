# Release 模板（复制到 GitHub Release 的Describe框使用）

> **用法**：GitHub → Releases → Draft a new release → 选 tag → 把下表模板粘贴进描述框。
> 本模板与 `.github/release.yml`（label 分类）配套：PR 打上对应 label 后，
> 自动生成段会归入同类；手工段按本模板填写。

---

## ⚠️ 发布前置校验（任一未过 → 不得发布）

**一条命令跑完全部机器可检项**（务必在**打好 tag 之后**执行，让闸门校验 tag 指向的树，
而不是本机工作区）：

```bash
python emf_demo/release_preflight.py --tag <版本号>
# 退出码 0 = 可发布；1 = 阻断（逐条列出）
```

闸门检四项：① tag 是否等于 HEAD（防归档未验证内容）② 归档树是否含 `.gitattributes`
且固定 `eol=lf` ③ `.zenodo.json` 是否在归档树内且可解析 ④ **把 tag 树解包到临时目录，
在副本上实跑清单校验 + 审计**。

第 ④ 项是决定性的：它检验"Zenodo 实际会归档的东西"是否自洽，等价于人工"克隆一份再跑"，
但可复现、可挂流程。

**历史教训（2026-09-30，两起）**：

| 记录 | 症状 | 根因 | 防线 |
|---|---|---|---|
| v1.0.0 | Zenodo 元数据退回 GitHub 默认值，DOI 落地页丢失诚实边界段 | tag 早于 `.zenodo.json` 的提交；联动只读 tag 指向的 commit | 闸门 ③ |
| 1.0.1 | 归档 11/11 文本文件 CRLF，清单在归档内不自洽 | ① tag 落后 HEAD 一笔 ② 归档树无 `.gitattributes` | 闸门 ①②④ |

> 共同点：**本机自审全绿，产物是坏的**。任何只读工作区的检查都抓不到这类缺陷。
> 故第 ④ 项必须在**解包副本**上跑，不能用本机 `--verify` 的通过结果代替。

**仍需人工复核的一项**（机器检不了）：

```bash
# release 正文无未填占位符（形如 <...>）——占位符一旦发布即成为公开记录
# 粘贴后肉眼复核：表格里不得残留 <版本号> <日期> <THEOREM...> 等尖括号内容
```

**tag 命名**：与 `.zenodo.json`/清单声明的版本一致（`1.0.1` 或 `v1.0.1`，全程统一，
不要混用）。Zenodo 自动为每个新 release 铸**版本 DOI**，concept DOI 恒定。
**已发布记录的 tag 不可移动**——修正只能走新版本（见「降级不删除」纪律）。

---

```markdown
## 版本与真值层级

| 项 | 值 |
|---|---|
| 版本 | v<版本号> |
| 日期 | <日期> |
| 主结果层级 | <THEOREM / THEOREM-COND / EMPIRICAL / GAP-OPEN> |
| 取代 | <前一版本号> |
| 文档哈希 | <MANIFEST sha256 前16位> |

## 本版本新增（按真值层级分组）

### 新增 THEOREM / 闭合式
- <每条带真值层级，不得剥离条件>

### 修复（含假阴性修复）
- <每条注明：缺陷 → 修法 → 负向测试确认>

### 审计轨迹
- 文档 append-only：+<字节数>，双前缀守卫 <OK/BROKEN>，U+FFFD=<数>
- 台账：<ledger 名单>，pointer <MATCH/STALE>
- 负向测试：<N/N 检出，exit 0/1>

## 诚实边界（必填，不得删）

- 主结果状态：<如"条件于 GAP-OPEN 引理 6.0，未证">
- 本版本**未解决**项：<如实登记，降级而非删除>
- ✅ 允许的表述 / ❌ 禁止的表述（E5 §5.6）

## 复现

\```bash
cd emf_demo
python mf_audit.py sample          # 样例应报 WARN
python negative_test.py            # 全部检出
python mk_manifest.py --verify     # 哈希锁一致
\```

## 许可

- 代码 MIT / 数学内容与文档 CC-BY-4.0（见 LICENSE.md）
- 引用数学结论不得剥离真值层级标签
```

---

## .github/release.yml 的 label 约定

| label | 归入类别 |
|---|---|
| `theorem` | 数学结论（THEOREM/闭合式） |
| `fix-negative` | 假阴性修复 |
| `tooling` | 审计器与工具 |
| `docs` | 文档与登记 |
| `ignore` | 排除（不出现在发布说明） |
