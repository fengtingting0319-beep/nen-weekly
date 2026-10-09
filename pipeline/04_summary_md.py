#!/usr/bin/env python3
"""NEN weekly - Markdown summary builder. Mirrors the HTML report sections."""
import json, sys, os, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content import HIGHLIGHTS, TOP10, SUMMARIES
from content_clinical import CLINICAL
from content_guidelines import GUIDELINES

PROCESSED = sys.argv[1] if len(sys.argv) > 1 else "/workspace/nen_weekly/processed.json"
RAW = sys.argv[2] if len(sys.argv) > 2 else "/workspace/nen_weekly/raw"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/mnt/results/NEN_weekly/NEN_weekly_summary.md"

d = json.load(open(PROCESSED))
qlog = json.load(open(f"{RAW}/query_log.json"))
papers, trials, s = d["papers"], d["trials"], d["summary"]
W0, W1 = qlog["window"]

PREPRINT_DOI = re.compile(r"^10\.(20944|21203|64898|1101|1590)/", re.I)
PREPRINT_J = re.compile(r"bioRxiv|medRxiv|preprint server", re.I)
ANIMAL = re.compile(r"\b(dogs?|canine|canines|mice|mouse|rats?|murine|porcine|swine|zebrafish|rabbits?)\b", re.I)

def is_preprint(r):
    if PREPRINT_J.search(r["journal"] or ""): return True
    return (not r["journal"] and r["doi"] and PREPRINT_DOI.match(r["doi"])) or (not r["journal"] and not r["pmid"])

def is_animal(r):
    if ANIMAL.search(r["title"]): return True
    first = r["abstract"].split(". ")[0] if r["abstract"] else ""
    return bool(ANIMAL.search(first)) and not re.search(r"patient|human|cohort|clinic", first, re.I)

final = [p for p in papers if p["tier"] in ("core", "direct")
         and not is_preprint(p) and not is_animal(p)
         and (p["pmid"] or p["doi"]) and p["abstract"]]
final.sort(key=lambda r: ({"S": 0, "A": 1, "B": 2, "C": 3}[r["grade"]], -(r["if"] or 0)))

def key(p): return p["pmid"] or p["doi"]
def link(p):
    if p["pmid"]: return f"https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/"
    return f"https://doi.org/{p['doi']}"
def ifs(p): return f"IF {p['if']}" if p["if"] else "IF 待核实"

L = []
L.append(f"# 神经内分泌肿瘤（NEN）研究周报 · {W0} 至 {W1}\n")
oa = qlog["sources"]["openalex"]["status"]
oa_note = "· OpenAlex 不可用（HTTP 429，已如实标注）" if "429" in str(oa) else ""
L.append(f"**纳入文献 {len(final)} 篇 · 临床试验动态 {s['trials_nen']} 项** · 影响因子口径 JCR 2025（仅填已核实数值）{oa_note}\n")

L.append("## 本周看点\n")
for h in HIGHLIGHTS:
    L.append(f"### [{h['tag']}] {h['title']}\n{h['text']}\n")

L.append("## 精读 Top10\n")
for t in TOP10:
    p = next((x for x in final if key(x) == t["key"]), None)
    if not p: continue
    c = CLINICAL.get(t["key"], {})
    L.append(f"### {p['title']}")
    L.append(f"{p['journal']} · [{link(p)}]({link(p)}) · {ifs(p)}")
    L.append(f"- **背景**：{t['bg']}")
    L.append(f"- **核心结果**：{t['res']}")
    if c.get("clin"): L.append(f"- **临床意义**：{c['clin']}")
    if c.get("design"): L.append(f"- **课题借鉴**：{c['design']}")
    L.append("")

L.append("## 全部纳入文献（按分级与 IF 排序，含临床意义与课题借鉴）\n")
for i, p in enumerate(final, 1):
    k = key(p)
    L.append(f"{i}. **[{p['grade']}]** {p['title']} — {p['journal']} · {ifs(p)} · [{link(p)}]({link(p)})")
    if k in SUMMARIES:
        L.append(f"   - 要点：{SUMMARIES[k]}")
    c = CLINICAL.get(k, {})
    if c.get("clin"): L.append(f"   - 临床意义：{c['clin']}")
    if c.get("design"): L.append(f"   - 课题借鉴：{c['design']}")

L.append("\n## 中国共识与指南\n")
L.append("### 现行重要中国指南/共识清单（编辑核实维护）\n")
for g in GUIDELINES:
    src = g["source"] + (f" · DOI: {g['doi']}" if g.get("doi") else "")
    L.append(f"- **{g['title']}**（{g['org']}）— {src} · 覆盖：{g['scope']}")
    L.append(f"  - {g['note']}")
L.append("\n### 本周窗口内新发表动态\n")
wk = [p for p in final if p.get("is_guideline_cn")]
if wk:
    for p in wk:
        L.append(f"- {p['title']} — {p['journal']} · [{link(p)}]({link(p)})")
else:
    L.append(f"本周窗口（{W0} 至 {W1}）内未检索到新发表的中国 NEN 指南/共识（PubMed Q4 + Europe PMC 定向检索，题名级判定）。")

L.append(f"\n## 临床试验动态（{s['trials_nen']} 项，LastUpdatePostDate 窗口）\n")
L.append("| NCT | 题目 | 分期 | 状态 | 最近更新 |")
L.append("|---|---|---|---|---|")
for t in trials:
    nct = t.get("nct_id", "")
    L.append(f"| [{nct}](https://clinicaltrials.gov/study/{nct}) | {t.get('brief_title','')[:80]} | {t.get('phase','—')} | {t.get('status','')} | {t.get('last_update','')} |")

L.append("\n## 检索与漏斗\n")
L.append("- PubMed（EDAT 窗口）四组检索式（含中国指南定向 Q4）；Europe PMC（FIRST_PDATE）三组；ClinicalTrials.gov 三组"
         + ("；OpenAlex HTTP 429 不可用。" if "429" in str(oa) else "。"))
L.append(f"- 三级去重后候选池 {s['pool_size']}；剔除非 NEN 主题（弱相关层，保留可追溯）{s['weak']}、预印本 {s['preprints']}、"
         f"动物实验 {s['animals']}、无标识 {s['no_id']}、无摘要 {s['no_abs']} → **最终纳入 {len(final)} 篇**"
         f"（A 级 {sum(1 for p in final if p['grade']=='A')}、B 级 {sum(1 for p in final if p['grade']=='B')}、"
         f"C 级 {sum(1 for p in final if p['grade']=='C')}；{s['if_verified']} 篇 IF 已核实）。")
L.append("- 中文要点、临床意义与课题借鉴均严格依据当期英文摘要原文归纳，未引入摘要以外信息。")
L.append("\n完整交互版（吸顶导航、筛选、折叠卡片、直链）见同目录 HTML 文件。")

text = "\n".join(L) + "\n"
open(OUT, "w").write(text)
print(f"written {OUT} ({len(text)} chars), papers={len(final)}, trials={len(trials)}")
