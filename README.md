# `bibcanon`

**`bibcanon`** 是一款专为计算机视觉（CV）、人工智能（AI）与机器学习（ML）论文写作打造的**单 `.bib` 参考文献真伪核验、预印本自动转正与出版方原汁原味官方 BibTeX 本地工作台**，全面兼容 **Overleaf** 与 **本地 LaTeX** 工作流。

---

## 核心特性

1. **多源交叉真伪核验与防幻觉熔断**
   - 并发检索 **DBLP、Crossref、OpenAlex、arXiv**（及可选 Semantic Scholar），精准识别大模型编造的虚假论文（`SUSPECTED_HALLUCINATION`）、标题与作者张冠李戴（`AUTHOR_MISMATCH`）、仅挂在 arXiv 却谎称顶会的条目（`FALSE_PUBLISHED_VENUE`）、死链 DOI（`INVALID_DOI`）以及文件内重复引用（`DUPLICATE_IN_BIB`）。
   - 严格区分**上游网络超时 (`ERROR`)** 与**查无此文 (`SUSPECTED_HALLUCINATION`)**，绝不因断网误报假论文。
2. **直连出版方获取「原汁原味」官方 BibTeX**
   - **CVPR / ICCV / WACV** ➔ 直连 **CVF Open Access**（内置会议目录本地 SQLite 缓存）
   - **ICML / AISTATS / CoRL / COLT** ➔ 直连 **PMLR** 官方 `#bibtex`
   - **ICLR / NeurIPS / TMLR** ➔ 直连 **OpenReview API (v2/v1)** 与 **NeurIPS Proceedings**
   - **ACL / EMNLP / NAACL / TACL** ➔ 直连 **ACL Anthology** `.bib`
   - **IEEE / ACM / Springer (ECCV) / AAAI 等** ➔ **DOI Content Negotiation** + 结构缺陷自动修复（如将 Springer LNCS 错误的 `@inbook` 自动修正为 `@inproceedings`、自动补全缺失页码与 `articleno`）
   - **未发表 arXiv 预印本** ➔ 采用 **arXiv 官网原生 `@misc`** 格式（含 `eprint`、`archivePrefix = {arXiv}`、`primaryClass`、`url`）
3. **尊重原意 + 预印本自动升级**
   - 若原 `.bib` 条目已明确指定某正式顶会（如 `CVPR`）且核验存在，**默认首推该顶会官方版**，并将后续同名期刊扩展版（如 `TPAMI`）列为候选标签供按需切换；
   - 仅当原条目为 `arXiv` / `CoRR` 预印本时，才自动推荐升级为最高规格的正式发表版本（正刊/正会 > Workshop > Preprint）。
4. **100% 锁死 Citation Key 与无损字符区间（Span）写回**
   - 严格保持原条目的 `cite_key` 不变，绝不破坏 `.tex` 正文中的 `\cite{...}`。
   - 基于精确字符偏移（Character Span）局部替换，文件内的 `%` 分组注释、`@string` 宏定义、`@preamble` 及未修改条目 **100% 字节级原样保留**。写回本地文件前自动生成时间戳 `.bak` 备份。
5. **LaTeX 编译绝对安全与双渲染模式**
   - 默认 **`canonical`（出版方原汁原味模式）**：保留出版方全部真实标准字段，仅剔除文献管理软件本地垃圾字段（`abstract`, `file`, `mendeley-tags`, `biburl`, `bibsource`, `timestamp` 等）。
   - 可选 **`compact`（顶会投稿省页码模式）**：一键切换为 35+ CV/AI/ML 权威会议/期刊标准缩写并精简冗余出版信息。
   - 内置幂等标题专有名词大小写保护（`{3D}`, `{RGB-D}`, `{ResNet}`, `{ViT}`, `{Gaussian}` 等）、裸 `&`/`%` 安全转义（跳过 URL/DOI 与 `$...$` 数学模式）以及页码双连字符 `--` 规范化。

---

## 安装方法

要求 **Python `>= 3.11`**。克隆或进入项目根目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\activate      # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

> 零配置开箱即用：无需申请任何 API Key 即可运行完整流程；可在 Web 工作台右上角「设置」中可选填写礼貌池邮箱（Crossref/OpenAlex Polite Pool）或本地代理（如 `http://127.0.0.1:7890`）。

---

## 使用指南

### 1. 本地 Web Diff 审核工作台（推荐）

在终端启动单端口本地 Web 服务（默认 `http://127.0.0.1:8765`）：

```powershell
# 直接打开空白工作台（适合粘贴 Overleaf .bib 或拖拽上传 .bib）
bibcanon serve

# 启动并自动加载指定的本地 .bib 文件
bibcanon serve path\to\references.bib

# 自定义端口且不自动弹出浏览器
bibcanon serve --port 8899 --no-browser
```

#### Overleaf 工作流
1. 运行 `bibcanon serve` 打开工作台。
2. 点击顶部 **「粘贴 .bib 全文」**（或直接将下载的 `.bib` 拖拽到顶部栏），开始实时流式核验。
3. 使用顶部胶囊快速定位 `❌ 疑似虚假`、`⚠️ 信息出入`、`🔄 可转正升级`、`🔁 重复条目`。
4. 点击 **「✨ 一键采纳高置信度更新」**，对个别疑难条目可使用底部 **Google Scholar / Bing 一键外跳检索 + 粘贴外部 BibTeX 自动锁 Key 合并**。
5. 点击 **「📋 复制完整 .bib」**，一键粘贴回 Overleaf 即可零报错编译。

#### 本地 LaTeX 工作流
1. 运行 `bibcanon serve D:\paper\references.bib`。
2. 审核确认后点击顶部 **「💾 备份并覆盖本地文件」**，系统自动将原文件备份为 `references.bib.bak.<YYYYMMDD_HHMMSS>` 并以 UTF-8 无损写回。

---

### 2. CLI 命令行体检与批量修复

```powershell
# 1. 终端彩色进度核验与体检汇总表（若发现疑似虚假条目返回退出码 1，可接入投稿前脚本检查）
bibcanon check references.bib --json audit_report.json

# 2. 自动替换所有高置信度（>=90）无警告条目，保留存疑条目不变并打印人工复核清单
bibcanon fix references.bib -o references.clean.bib

# 3. 自动生成 .bak 备份后就地更新原文件（可选切换省页码缩写模式 --mode compact）
bibcanon fix references.bib --in-place --mode canonical --min-confidence 90

# 4. 查看或清理本地 SQLite 缓存 (~/.bibcanon/cache.sqlite3)
bibcanon cache stats
bibcanon cache clear --scope queries
bibcanon cache clear --scope all
```

---

## 开发者构建与测试

```powershell
# 运行全量离线确定性单元测试与端到端集成测试
pytest -v

# 若修改了 frontend/ 前端源码，重新进行类型检查并构建静态资源至 src/bibcanon/static/
cd frontend
pnpm run build
```
