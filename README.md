# NEN 研究周报 · GitHub Pages 站点

泛神经内分泌肿瘤（NEN）全谱每周文献监测，GitHub Pages 在线发布，GitHub Actions 每周一自动更新。

## 每周一自动发生什么

北京时间周一 09:00（cron `0 1 * * 1` UTC，GitHub 有约 15 分钟级触发抖动），Actions 自动：

1. **检索**：PubMed（E-utilities · EDAT）+ Europe PMC（REST · FIRST_PDATE）+ ClinicalTrials.gov（API v2 · LastUpdatePostDate），窗口为上一周（截至周日）
2. **处理**：三级去重 → 相关度分层（核心/直接/弱相关）→ 剔除预印本/动物/无摘要 → 证据分级（S/A/B/C）
3. **渲染**：生成当期 HTML 周报 + Markdown 摘要 + 站点主页 `index.html`（最新一期卡片 + 归档表）
4. **发布**：新期文件提交回仓库 `site/`，并部署到 GitHub Pages

自动发布的是**基础版**：文献全列表、试验动态、指南板块、数据面板齐全；每篇文献的「中文要点」显示英文摘要自动节选并标注「编辑要点待补充」，本周看点/精读 Top10/本期关键结论显示待补充空态——数据诚实，不凑数。

## 一次性开通（约 3 分钟）

```bash
# 1. 在 GitHub 网页创建一个空的 Public 仓库（Pages 免费额度要求 Public；
#    私有仓库需 GitHub Pro），不要勾选任何初始化选项。
#    假设仓库名：yourname/nen-weekly

# 2. 本地推送（在本目录下执行）
git init
git add .
git commit -m "NEN weekly: pipeline + site seed + weekly workflow"
git branch -M main
git remote add origin https://github.com/yourname/nen-weekly.git
git push -u origin main

# 3. 网页开启 Pages：仓库 Settings → Pages → Build and deployment →
#    Source 选「GitHub Actions」。
# 4.（可选立即验证）Actions 页选「NEN weekly report」→ Run workflow 手动触发一次。
```

之后每周一自动运行；也可随时在 Actions 页手动触发（`workflow_dispatch`）。

## 每周编辑层补充（唯一的人工步骤）

基础版发布后，在 Biomni 会话说「跑本周 NEN 周报」或「补充本周编辑层」：

1. 代理基于当期 `archive/YYYY-MM-DD_processed.json` 的摘要撰写编辑层：
   - `pipeline/content.py`：`OVERVIEW`（本期关键结论）、`HIGHLIGHTS`（本周看点）、`TOP10`（精读卡片）、`SUMMARIES`（每篇中文要点）
   - `pipeline/content_clinical.py`：`CLINICAL`（每篇临床意义 + 课题借鉴）
2. 重新渲染并推送：

```bash
cd pipeline
NEN_WEEKLY_OUT=../site python 03_build_html.py processed.json raw ../site/NEN_weekly_<END>.html
python 05_build_index.py ../site
git add . && git commit -m "editorial layer <END>" && git push
```

推送后 Actions 自动重新部署，页面即为完整版。编辑要点严格依据当期英文摘要原文归纳，不引入摘要以外的信息。

## 目录结构

```
pipeline/          流水线（纯 Python 3 标准库，无第三方依赖）
  01_retrieve.py     三源检索（PubMed / Europe PMC / ClinicalTrials.gov；OpenAlex 失败时如实标注）
  02_process.py      去重、分层、分级
  03_build_html.py   HTML 周报渲染（含编辑层回退：自动摘要 + 待补充标注）
  04_summary_md.py   Markdown 摘要
  05_build_index.py  站点主页 index.html（最新一期 + 归档表）
  content*.py        编辑层（每周由代理基于当期摘要重写）
  run_weekly.sh      一键入口（本地 cron 与 CI 共用）
site/              已发布页面（Pages 从这里部署；index.html 为着陆页）
archive/           每期 processed.json + query_log.json 存档（可追溯）
.github/workflows/weekly.yml   每周一自动更新工作流
```

## 升级路径：全自动编辑层（可选）

若未来希望完全零人工，可在仓库 Secrets 放置 LLM API key，在 workflow 中增加一步：把当期 `processed.json` 喂给 LLM 生成 `content*.py` 草稿后渲染，并在页面标注「AI 生成、未经审校」。当前版本刻意不采用：编辑内容涉及证据解读，无审校的自动生成有幻觉风险。

## 数据口径

- 文献日期：PubMed ArticleDate/EDAT；Europe PMC FIRST_PDATE；试验 LastUpdatePostDate
- 影响因子：JCR 2025，仅填已核实数值，其余标注「IF 待核实」
- 所有文献条目携带真实 PMID 或 DOI；弱相关层保留可追溯，不计入纳入
