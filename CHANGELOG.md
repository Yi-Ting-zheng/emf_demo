<!-- audit-record: A-01,A-03,A-07 -->

# CHANGELOG — public_demo（EMF 公开演示仓库）

> 本文件是 `MANIFEST_EMF.json` note 字段所指的登记处。哈希锁的处置条款要求
> 「若为有意修改：重生成清单并在本文件记一笔」——本文件此前缺失（死指针），
> 于首个发布版补建，缺陷已登记而非删除。
>
> 记录 Zenodo 缺陷必然复述缺陷的**字面症状**（未填占位符原文），
> 故按 SPEC §3.1.1 在文件头**声明式豁免** A-01/A-03/A-07（降为 INFO 并计数打印，豁免≠无问题）。

## 版本双轴约定（2026-09-30 补记，此前混淆已致标签漂移）

本仓库有**两条互相独立**的版本轴，段头一律按**发布轴**书写：

| 轴 | 取值 | 真值源 | 消费者 |
|---|---|---|---|
| **发布轴**（本文件段头） | `1.0.0` `1.0.1` `1.0.2` | git tag | GitHub Release / **Zenodo 版本 DOI** |
| **框架轴**（审计器） | `1.0.2` `1.0.3` | `mf_audit.py:VERSION`（`mk_manifest.py` 自动派生） | `MANIFEST_EMF.json` 的 `version` 字段 |

**二者不可互相推断**。1.0.1 装的是框架 v1.0.3；框架版本不变时发布轴仍可前进
（1.0.1 → 1.0.2 只改发布产物形态，框架仍为 v1.0.3）。

> 此前把两轴写混，导致「待发布 v1.0.1」与「待发布 v1.0.3」两段并存、而 1.0.1
> 其实已发布——自声明版本与实际 tag 脱节。此即 `mk_manifest.py` 版本漂移缺陷的
> 文档侧同型复发，故在此显式立约。

## [Unreleased] — 待发布 **1.0.2**（发布闸门 + 克隆可验证性；框架 v1.0.3）

### 修复：`.zenodo.json` 混用 schema 代际，Zenodo ingest 被拒（发布阻断级）

| 项 | 内容 |
|---|---|
| 症状 | Zenodo GitHub 集成 `Errors` 面板：`{'metadata': {'resource_type': ['Missing data for required field.']}}`；提交当时面板显示「无版本记录、无版本 DOI」 |
| 事后更正 | 该面板状态是**提交当时**的快照，不是终态。Zenodo 事后重试 ingest 成功，1.0.1 最终铸出 `10.5281/zenodo.23065720`。曾据该面板判定「1.0.1 无版本 DOI」，此判定错误 |
| 根因 | 写成 `"upload_type": {"type": "publication", "subtype": "workingpaper"}`。但 Zenodo legacy 反序列化器的契约是**两个平级标量**：`upload_type`（String → `resource_type.type`）与 `publication_type`（String → `resource_type.subtype`）。`subtype` 是**新版 `resource_type` 内部**的键名，放进 `upload_type` 里不认 ⟹ 产不出 `resource_type` ⟹ 校验失败。`upload_type` 写成对象（而非字符串）本身就足以致败 |
| 修正 | `"upload_type": "publication"` + 平级 `"publication_type": "workingpaper"` |
| 旁证 | 官方 Zenodo 文档示例为扁平 `"upload_type": "software"`；legacy 受控词表列 `publication_type` ∈ {softwaredocumentation, taxonomictreatment, technicalnote, thesis, workingpaper, other} |
| 为何闸门没拦住 | 闸门 3 只验「JSON 可解析 + title/description/creators/license 齐备」——**JSON 合法 ≠ Zenodo 接受**。缺陷恰好落在两者之间 |
| 防线 | 闸门 3 增 `validate_zenodo_meta()`：按受控词表逐条验 `upload_type`（须为字符串）/ `publication_type`（平级、词表内）/ `access_right`；并显式识别 `upload_type.subtype` 代际混用。新增 `--selftest`：**10 例正/反例，含本缺陷的实际 payload**，漏拦 0 / 误拦 0 |
| 实测 | `release_preflight.py --tag 1.0.2` 对**已存在的 tag 树**判 2 项阻断并直接指出根因；修正提交后判 0 项 |
| 同源 | 姊妹仓库 `public_theorem` 1.0.0 有**实证错误面板**，为同一缺陷；两仓库同日同型 |
| 元教训 | 上一轮我把「Zenodo 侧迟迟无记录」误判为服务端性能退化。**真实原因是本地 schema 非法**——服务端是秒回的确定性拒绝。先取错误面板原文，再谈服务端问题 |
| 元教训 2 | **集成面板 ≠ 终态**。Errors 面板是提交当时的快照；Zenodo 会事后重试 ingest 并可能成功。下一轮我又把「面板显示无版本 DOI」当成事实写进 CHANGELOG，事后证明 1.0.1 实际铸出了 DOI。**面板读数不可作为「无记录」的终局证据**——须以 `GET /api/records/{id}/versions` 的实际返回为准 |

### 研究发现：自审全绿（含 preflight）仍放行了坏的 `.zenodo.json`

> 三个缺陷同族：**只检查工作区能通过的属性，而失败发生在产物上**。
> 闸门 1/2/4 都在做「解包 tag 树后实跑」；唯独闸门 3 验的是**schema 语义**，
> 而它只验了「可解析」。补齐语义层校验，才使闸门覆盖与失败面一致。

### 判据修正（依据姊妹仓库 `public_theorem` 自审计裁决，FAIL 16 → 0）

| # | 修正 | 性质 |
|---|---|---|
| 1 | **A-04 前提被实测证伪并判死**：`mp.mp.dps = N` 判「落在非工作 context、不生效」不成立 —— mpmath 1.3.0 实测 `mpmath.mp` 就是工作 context，赋值后读回为 50。模式删除；模块属性赋值缺陷仍由文件级模式覆盖 | **前提证伪** |
| 2 | A-07 改**结构判别**（原为"存在尖括号"的形态判据）：豁免 HTML 标签、含运算符数学片段、裸数学符号、跨反引号跨度 | 假阳性修复 |
| 3 | A-09 规则消息不再硬编码 `03_缺口登记/`（旧布局遗留），改为从本项目实测回填登记表路径 | 消息与项目一致 |
| 4 | A-10 新增 corrective 语境识别：记载「逆否只得析取 / 已 FALSIFIED / 逻辑错误」的文本降 INFO（此前这类**记录错误已被纠正**的文本一律 FAIL） | 假阳性修复 |
| 5 | 新增**裁决记录豁免**（`<!-- audit-record: ... -->`）：头 5 行声明 + 逐条降 INFO + 计数打印 + 未知规则编号 fail-closed | 新机制 |
| 6 | `negative_test.py` 由 6 例扩到 **12 例**：补 3 例**假阳性对照** + 3 例豁免边界；测试夹具改为每例独占目录 | **元缺陷修复** |

### 元教训（与内部 CHANGELOG #8 同源，第二次复发）

> 规则修复后第一次跑，往往先抓到**自己刚写的修正记录**。本次实测复发 **5 次**
> （U+FFFD 证据内嵌 / 脱敏记法同形 / 记录占位符样例 / 裁决记录复述触发词 / 记录盘符字面量）。
> 处置不是改措辞，而是**职责分离 + 声明式窄豁免 + 计数可见**。
> 姊妹仓库 `public_theorem/SELF_AUDIT.md` §4 载有完整证据链。

### 修复：tag 指向陈旧 commit 导致 Zenodo 归档坏版本（发布阻断级）

| 项 | 内容 |
|---|---|
| 缺陷 | GitHub Release .0.1\ 的 tag 落在 e7a9d8\，而克隆可验证性修复在**其后的** c0a74c\ ⟹ Zenodo 正在归档的树里**没有** \.gitattributes\，11/11 文本文件为 CRLF，清单在归档内不自洽 |
| 闸门实测 | 新增 \emf_demo/release_preflight.py\ 对 tag .0.1\ 判定 **4 项阻断**（tag 落后 HEAD 1 笔 / 缺 .gitattributes / 归档树 CRLF×11 / 归档树哈希锁不自洽）；对 HEAD 判定 0 项 |
| 处置 | 1.0.1 按「降级不删除」保留为该缺陷的审计证据；修复走新版本 DOI |
| 根因 | 发布动作（打 tag）与验证动作（跑校验）之间**无强制闸门**，二者靠人工记忆对齐 |

### 修复：哈希锁的克隆可验证性（发布阻断级）

| 项 | 内容 |
|---|---|
| 缺陷 | 无 `.gitattributes` 且 `core.autocrlf=true`（Git for Windows 安装级默认）⇒ **新克隆 12/12 文件行尾被 CRLF 化**，`mk_manifest.py --verify` 判「框架完整性已失守」 |
| 处置 | 新增 `.gitattributes`（`* text=auto eol=lf`）；`.gitignore` 与 `emf_demo/sample/demo_case.md` 归一化为 LF；清单重生（12 文件） |
| 证据 | 修复前新克隆实测 FAIL；修复后新克隆实测 `[OK] 哈希锁一致：12 个文件全部未变` |
| 同源 | 姊妹仓库 `public_theorem` 同日同型缺陷（2 个 CRLF 文件 ⟹ 新克隆 `FAIL 2`），已同步处置 |
| 性质 | 哈希锁是本仓库唯一完整性凭据。**只在作者机器上成立的锁等于没有锁**——「我这份跑过了」不是「克隆下来还成立」的证据 |

> 与 A-04 同族的方法论教训：本次缺陷不是读代码看出来的，是**克隆一份再跑**跑出来的。
> 自审套件再多也只覆盖作者机器上的那一份字节。

## 登记：发布 1.0.1 归档不自洽（降级不删除）

| 项 | 值 |
|---|---|
| 记录 | https://github.com/Yi-Ting-zheng/emf_demo/releases/tag/1.0.1 |
| tag 指向 | 3e7a9d8（落后当时 HEAD 5c0a74c 一笔） |
| 版本 DOI | **10.5281/zenodo.23065720**（`publication` / `workingpaper`）。首次提交触发时 Zenodo GitHub 联动面板报 `{'metadata': {'resource_type': ['Missing data for required field.']}}`，面板当时显示「无版本记录」；Zenodo 事后重试 ingest 成功，铸出版本 DOI。同期另有一条同版本号重复记录 `10.5281/zenodo.23065691`（同日期、同 `publication`/`workingpaper`），源于两次 Release/tag 事件，已由维护者删除。概念 DOI 10.5281/zenodo.23056474 恒定 |
| 缺陷 | 该 tag 的树内**无** .gitattributes，11/11 文本文件为 CRLF，MANIFEST_EMF.json 在归档副本上自校验失败 |
| 症状 | 下载者执行 mk_manifest.py --verify 得「框架完整性已失守」 |
| 闸门实测 | 
elease_preflight.py --tag 1.0.1 判 **4 项阻断**（tag 落后 / 缺 .gitattributes / 归档树 CRLF×11 / 归档树哈希锁不自洽）；判 **5 项阻断**（追加 Zenodo schema，见下节） |
| 根因 | 发布动作（打 tag）与验证动作（跑校验）之间无强制闸门，二者靠人工记忆对齐 |
| 处置 | **降级不删除**：1.0.1 保留为该缺陷的审计证据（版本 DOI `10.5281/zenodo.23065720`）；修正走 1.0.2 新版本 DOI |
| 防线 | emf_demo/release_preflight.py（5 闸门，第 4 项解包 tag 树实跑，第 5 项校 Zenodo schema）已并入发布流程 |

## [1.0.1] — 已发布（2026-09-30）；框架 v1.0.3（审计器判据修正）

> **本版归档不自洽**，按「降级不删除」保留为审计证据。缺陷见下方登记；修正走 1.0.2。

### 收录
- 审计器判据修正（框架 v1.0.3）：A-04 前提证伪 / A-07 结构判别 / A-09 路径回填 / A-10 corrective 语境 / udit-record 豁免 / 负向测试 6 → 12 例

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

## [1.0.0] — 已发布（2026-09-30）；框架 v1.0.2（首次公开归档）

- 提交 `2c52519`：init（审计器 v1.0.2 + 负向测试 6/6 + 哈希锁）
- 提交 `66e36c5`：双协议
- 提交 `ed3f270`：release 模板 + README 改名
- 提交 `1f8cf6d`：`.zenodo.json`
- GitHub Release `1.0.0` → Zenodo 自动铸 DOI `10.5281/zenodo.23056475`
- 本次验证：自审 `0 FAIL / 0 WARN`；负向测试 `6/6`（exit 0）；样例 `FAIL=0 WARN=2`（故意违规）

---

`EMF | public_demo | v1.0.3 待发 | 前提证伪 | 结构判据 | 假阳性对照 | 裁决记录豁免 | 克隆可验证 | GAP-OPEN | 归档 DOI 10.5281/zenodo.23056474`
