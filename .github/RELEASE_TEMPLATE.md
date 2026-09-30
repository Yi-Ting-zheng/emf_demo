# Release 模板（复制到 GitHub Release 的Describe框使用）

> **用法**：GitHub → Releases → Draft a new release → 选 tag → 把下表模板粘贴进描述框。
> 本模板与 `.github/release.yml`（label 分类）配套：PR 打上对应 label 后，
> 自动生成段会归入同类；手工段按本模板填写。

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
