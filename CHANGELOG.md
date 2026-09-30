# CHANGELOG — public_demo（EMF 公开演示仓库）

> 本文件是 `MANIFEST_EMF.json` note 字段所指的登记处。哈希锁的处置条款要求
> 「若为有意修改：重生成清单并在本文件记一笔」——本文件此前缺失（死指针），
> 于 v1.0.2-lineage 补建，缺陷已登记而非删除。

## [Unreleased] — 待发布 v1.0.1

### 新增
- `LICENSE.md`：双协议（代码 MIT / 数学内容与文档 CC-BY-4.0）+ 真值层级引用义务
- `.zenodo.json`：Zenodo 联动元数据（Zenodo 仅从 **tag 指向的 commit** 读取该文件）
- `.github/release.yml`：release 自动分类（theorem / fix-negative / tooling / docs / ignore）
- `.github/RELEASE_TEMPLATE.md`：release 正文模板（含**诚实边界必填段**）
- `README_PUBLIC.md → README.md`：GitHub 仅自动渲染 `README.md`
- `CHANGELOG.md`：本文件（补建，见上方死指针登记）

### 修复
- **清单版本漂移（结构性）**：`mk_manifest.py` 曾硬编码 `"version": "1.0.1"`，
  而 `mf_audit.py` 已是 `VERSION = "1.0.2"` —— 重复常量必然漂移，且哈希锁只锁
  文件内容、不校验自声明版本，故该漂移**未被检出**。修复：版本改为从
  `mf_audit.py:VERSION` 自动派生（单一真值源），并在 `--verify` 增加版本一致性断言。
  审计规则本身未变，故**不升版本号**（v1.0.2 仍为真）。
- **manifest 死指针**：note 字段指向 `CHANGELOG.md`，而 demo 中该文件不存在 → 补建。

### 登记：Zenodo v1.0.0 记录（DOI 10.5281/zenodo.23056475）元数据缺陷

| 项 | 值 |
|---|---|
| 记录 | https://zenodo.org/records/23056475 |
| concept DOI | 10.5281/zenodo.23056474 |
| 版本 DOI | 10.5281/zenodo.23056475（v1.0.0，tag `1.0.0`） |
| 状态 | published；archive md5 `18a96e4081f8425a85caa21c9c571f9a` |
| 缺陷 | title/description/resource_type/creators 全部退回 GitHub 默认值 |
| 症状 | description = release 正文中的**未填占位符**（`<版本号>`、`<THEOREM/GAP-OPEN>`…） |
| 根因 | tag `1.0.0` 早于 `.zenodo.json` 的提交（`1f8cf6d`）；联动只读 tag 指向的 commit |
| 后果 | DOI 落地页未呈现诚实边界段 —— 申基金时的第一入口缺关键限定 |
| 处置 | **降级不删除**：保留 v1.0.0 作为该缺陷的审计证据；修复走 v1.0.1 新版本 DOI |
| 未修复项 | v1.0.0 记录的元数据本身仍在 Zenodo 侧（需账户权限才能改，本仓库无权修改） |

## [v1.0.2-lineage] — 2026-09-30 首次公开归档

- 提交 `2c52519`：init（审计器 v1.0.2 + 负向测试 6/6 + 哈希锁）
- 提交 `66e36c5`：双协议
- 提交 `ed3f270`：release 模板 + README 改名
- 提交 `1f8cf6d`：`.zenodo.json`
- GitHub Release `1.0.0` → Zenodo 自动铸 DOI `10.5281/zenodo.23056475`
- 本次验证：自审 `0 FAIL / 0 WARN`；负向测试 `6/6`（exit 0）；样例 `FAIL=0 WARN=2`（故意违规）

---

`EMF | public_demo | v1.0.2-lineage | GAP-OPEN | GAP-01/02/03 开放 | 归档 DOI 10.5281/zenodo.23056474`
