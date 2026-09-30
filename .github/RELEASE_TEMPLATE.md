# Release 模板（复制到 GitHub Release 的Describe框使用）

> **用法**：GitHub → Releases → Draft a new release → 选 tag → 把下表模板粘贴进描述框。
> 本模板与 `.github/release.yml`（label 分类）配套：PR 打上对应 label 后，
> 自动生成段会归入同类；手工段按本模板填写。

---

## ⚠️ 发布前置校验（任一未过 → 不得发布）

**历史教训（v1.0.0 记录）**：tag `1.0.0` 早于 `.zenodo.json` 的提交，而 Zenodo 联动
**只从 tag 指向的 commit 读取** `.zenodo.json` → 元数据退回 GitHub 默认（release 标题 +
未填占位符正文）→ DOI 落地页丢失诚实边界段。根因防线如下：

```bash
# 1) 元数据文件必须已在【待打 tag 的那个 commit】里（不是 main 的最新状态）
git cat-file -e HEAD:.zenodo.json && echo "[OK] .zenodo.json 在 HEAD"
#    若用已有 tag：git cat-file -e <tag>:.zenodo.json

# 2) 哈希锁一致（否则清单失效，归档内容与声明不符）
cd emf_demo && python mk_manifest.py --verify

# 3) 负向测试全检出（6/6，exit 0）
cd emf_demo && python negative_test.py

# 4) release 正文无未填占位符（形如 <...>）——占位符一旦发布即成为公开记录
#    粘贴后肉眼复核：表格里不得残留 <版本号> <日期> <THEOREM...> 等尖括号内容
```

**tag 命名**：与 `.zenodo.json`/清单声明的版本一致（`1.0.1` 或 `v1.0.1`，全程统一，
不要混用）。Zenodo 自动为每个新 release 铸**版本 DOI**，concept DOI 恒定。

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
