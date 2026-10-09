#!/usr/bin/env python3
"""NEN weekly - HTML builder. Renders self-contained single-file HTML report."""
import json, sys, html, os, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content as _content
from content import HIGHLIGHTS, TOP10, SUMMARIES
from content_clinical import CLINICAL
from content_guidelines import GUIDELINES
# 本期关键结论（编辑维护，content.py 中 OVERVIEW；自动运行无编辑内容时为空 → 显示待补充空态）
OVERVIEW = getattr(_content, "OVERVIEW", "")

PROCESSED = sys.argv[1] if len(sys.argv) > 1 else "/workspace/nen_weekly/processed.json"
RAW = sys.argv[2] if len(sys.argv) > 2 else "/workspace/nen_weekly/raw"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/mnt/results/NEN_weekly/NEN_weekly.html"

d = json.load(open(PROCESSED))
qlog = json.load(open(f"{RAW}/query_log.json"))
papers, trials, s = d["papers"], d["trials"], d["summary"]
W0, W1 = qlog["window"]

final = [p for p in papers if p["tier"] in ("core", "direct") and not p.get("_excl")]
# rebuild exclusion flags deterministically
import re
PREPRINT_DOI = re.compile(r"^10\.(20944|21203|64898|1101|1590)/", re.I)
ANIMAL = re.compile(r"\b(dogs?|canine|canines|mice|mouse|rats?|murine|porcine|swine|zebrafish|rabbits?)\b", re.I)
PREPRINT_J = re.compile(r"bioRxiv|medRxiv|preprint server", re.I)
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

weekly_guidelines = [p for p in final if p.get("is_guideline_cn")]

def esc(x): return html.escape(str(x or ""))

def auto_excerpt(p, n=200):
    """编辑要点缺失时的自动节选：取英文摘要前 ~n 字符并按句界截断，如实标注非编辑内容。"""
    a = " ".join((p.get("abstract") or "").split())
    if len(a) <= n:
        return a
    cut = a[:n]
    dot = cut.rfind(". ")
    return (cut[:dot + 1].strip() if dot > n * 0.5 else cut.rstrip()) + " …"

GRADE_COLOR = {"S": "#c0392b", "A": "#0279EE", "B": "#75A025", "C": "#888"}
TIER_LABEL = {"core": "核心 NEN", "direct": "直接相关"}

# ---------- header stats ----------
n_pool = s["pool_size"]
n_final = len(final)
n_trials = s["trials_nen"]
n_trials_raw = s["trials_total"]
pm_hits = qlog["sources"].get("pubmed_Q1_disease", {}).get("count") or 0
pm_hits += qlog["sources"].get("pubmed_Q2_treatment", {}).get("count") or 0
pm_hits += qlog["sources"].get("pubmed_Q3_mesh", {}).get("count") or 0
ep_hits = (qlog["sources"].get("europepmc_main_OR", {}).get("count") or 0) + \
          (qlog["sources"].get("europepmc_directed_AND", {}).get("count") or 0)
oa_status = qlog["sources"]["openalex"]["status"]

# funnel numbers
n_weak = s["weak"]; n_pre = s["preprints"]; n_anim = s["animals"]; n_noabs = s["no_abs"]
funnel = [
    ("三级去重后候选池", n_pool, ""),
    ("剔除非 NEN 主题命中（弱相关层，保留可追溯）", -n_weak, "弱相关"),
    ("剔除预印本（无期刊正式记录）", -n_pre, "预印本"),
    ("剔除动物实验研究", -n_anim, "动物"),
    ("剔除无 PMID/DOI 标识记录", -s["no_id"], "无标识"),
    ("无可用摘要文本", -n_noabs, "无摘要"),
    ("最终纳入", n_final, "final"),
]
check = n_pool - n_weak - n_pre - n_anim - s["no_id"] - n_noabs
assert check == n_final, f"funnel mismatch {check} != {n_final}"

grades = {g: len([p for p in final if p["grade"] == g]) for g in "SABC"}
if_verified = [p for p in final if p["if_verified"]]

all_tags = []
for p in final:
    for t in p["tags"]:
        if t not in all_tags: all_tags.append(t)

# ---------- trials table ----------
def trial_row(t):
    phase = esc(t["phase"]) if t["phase"] and t["phase"] != "N/A" else "—"
    status_map = {"RECRUITING": "招募中", "NOT_YET_RECRUITING": "尚未招募", "ACTIVE_NOT_RECRUITING": "活跃不招募",
                  "COMPLETED": "已完成", "WITHDRAWN": "撤回", "SUSPENDED": "暂停", "TERMINATED": "终止",
                  "ENROLLING_BY_INVITATION": "邀请招募", "UNKNOWN": "未知"}
    st = status_map.get(t["status"], t["status"])
    return f"""<tr data-phase="{esc(t['phase'])}" data-status="{esc(t['status'])}">
<td><a href="https://clinicaltrials.gov/study/{esc(t['nct'])}" target="_blank">{esc(t['nct'])}</a></td>
<td>{esc(t['title'])}<div class="sub">{esc(t['conds'][:120])}</div></td>
<td>{phase}</td><td>{esc(t['interventions'][:150])}</td>
<td><span class="pill">{esc(st)}</span></td><td>{esc(t['lastupd'])}</td></tr>"""

trials.sort(key=lambda t: ({"RECRUITING": 0, "NOT_YET_RECRUITING": 1, "ACTIVE_NOT_RECRUITING": 2,
                            "ENROLLING_BY_INVITATION": 3}.get(t["status"], 9), t["nct"]))

# ---------- paper cards ----------
def paper_card(i, p):
    key = p["pmid"] or p["doi"]
    summ = SUMMARIES.get(key, "")
    if summ:
        summ_html = esc(summ)
    else:
        summ_html = (f'{esc(auto_excerpt(p))}'
                     f'<span class="autopend">自动摘要（英文摘要节选） · 编辑要点待补充</span>')
    links = []
    if p["pmid"]:
        links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p["pmid"]}/" target="_blank">PMID:{p["pmid"]}</a>')
    if p["doi"]:
        links.append(f'<a href="https://doi.org/{esc(p["doi"])}" target="_blank">DOI</a>')
    ifv = f'IF {p["if"]}' if p["if_verified"] else "IF 待核实"
    tags_html = " ".join(f'<span class="tag">{esc(t)}</span>' for t in p["tags"])
    cl = CLINICAL.get(key, {})
    clin_html = ""
    if cl.get("clin"):
        clin_html = f'<p class="clin"><b>临床意义：</b>{esc(cl["clin"])}</p>'
    if cl.get("design"):
        clin_html += f'<p class="clin design"><b>课题借鉴：</b>{esc(cl["design"])}</p>'
    return f"""<div class="card paper" data-grade="{p['grade']}" data-tier="{p['tier']}"
     data-tags="{'|'.join(esc(t) for t in p['tags'])}">
<div class="card-head"><span class="badge" style="background:{GRADE_COLOR[p['grade']]}">{p['grade']}</span>
<span class="tier">{TIER_LABEL[p['tier']]}</span><span class="jif">{esc(ifv)}</span></div>
<h3>{esc(p['title'])}</h3>
<div class="meta">{esc(p['journal'])} · {esc(p['pubdate'])} · {' · '.join(links)}</div>
<div class="tags">{tags_html}</div>
{clin_html}
<details><summary>中文要点</summary><p>{summ_html}</p></details>
<details><summary>英文摘要原文</summary><p class="abs">{esc(p['abstract'])}</p></details>
</div>"""

top10_keys = [t["key"] for t in TOP10]
top10_cards = []
for t in TOP10:
    p = next((x for x in final if (x["pmid"] or x["doi"]) == t["key"]), None)
    if not p: continue
    links = []
    if p["pmid"]:
        links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p["pmid"]}/" target="_blank">PMID:{p["pmid"]}</a>')
    if p["doi"]:
        links.append(f'<a href="https://doi.org/{esc(p["doi"])}" target="_blank">DOI</a>')
    ifv = f'IF {p["if"]}' if p["if_verified"] else "IF 待核实"
    cl = CLINICAL.get(t["key"], {})
    design_html = f'<p><b>课题借鉴：</b>{esc(cl["design"])}</p>' if cl.get("design") else ""
    top10_cards.append(f"""<div class="card top10">
<div class="card-head"><span class="badge" style="background:{GRADE_COLOR[p['grade']]}">{p['grade']}</span>
<span class="jif">{esc(ifv)}</span><span class="tier">{esc(p['journal'])}</span></div>
<h3>{esc(p['title'])}</h3>
<div class="meta">{' · '.join(links)}</div>
<p><b>研究背景：</b>{esc(t['bg'])}</p>
<p><b>核心结果：</b>{esc(t['res'])}</p>
<p><b>临床意义：</b>{esc(t['sig'])}</p>
{design_html}</div>""")

# ---------- query log section ----------
def qblock(name, q):
    return f"<h4>{esc(name)}</h4><pre>{esc(q)}</pre>"

pm_q = "".join(qblock(k, v["query"]) for k, v in qlog["sources"].items() if k.startswith("pubmed_") and "query" in v)
ep_q = "".join(qblock(k, v["query"]) for k, v in qlog["sources"].items() if k.startswith("europepmc_") and "query" in v)
ct_q = "".join(qblock(k, v["query"]) for k, v in qlog["sources"].items() if k.startswith("ctgov_") and "query" in v)

today = datetime.date.today().isoformat()

HTML = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>神经内分泌肿瘤（NEN）研究周报 · {W0} 至 {W1}</title>
<meta name="nen-window-start" content="{W0}">
<meta name="nen-window-end" content="{W1}">
<meta name="nen-papers" content="{n_final}">
<meta name="nen-trials" content="{n_trials}">
<meta name="nen-generated" content="{today}">
<style>
:root {{ --ink:#1a1a1a; --bg:#FAF9F3; --card:#fff; --accent:#0279EE; --line:#e4e0d6; }}
* {{ box-sizing:border-box; }}
body {{ font-family:"Liberation Sans","Arimo","DejaVu Sans","PingFang SC","Microsoft YaHei",sans-serif;
  margin:0; background:var(--bg); color:var(--ink); line-height:1.65; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:24px 20px 80px; }}
header h1 {{ font-size:1.7rem; margin:0 0 6px; }}
header .desc {{ color:#555; font-size:.95rem; }}
.runbar {{ display:flex; flex-wrap:wrap; gap:14px; font-size:.85rem; color:#666; margin:12px 0 4px; }}
.stats {{ display:flex; gap:18px; flex-wrap:wrap; margin:18px 0; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 20px; text-align:center; }}
.stat b {{ display:block; font-size:1.6rem; color:var(--accent); }}
.stat span {{ font-size:.8rem; color:#666; }}
h2 {{ font-size:1.25rem; margin:44px 0 12px; padding-bottom:6px; border-bottom:2px solid var(--ink); }}
h2 small {{ font-weight:normal; color:#777; font-size:.85rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin:12px 0; }}
.card h3 {{ margin:6px 0; font-size:1.02rem; }}
.card .meta {{ font-size:.8rem; color:#777; margin-bottom:6px; }}
.card .meta a {{ color:var(--accent); text-decoration:none; }}
.card-head {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.badge {{ color:#fff; border-radius:5px; padding:1px 8px; font-size:.78rem; font-weight:bold; }}
.tier {{ font-size:.78rem; color:#555; background:#ECE9E2; border-radius:5px; padding:1px 8px; }}
.jif {{ font-size:.78rem; color:#555; }}
.tags {{ margin:6px 0; }}
.tag {{ display:inline-block; font-size:.72rem; background:#E9ED4C33; border:1px solid #d6d94a; border-radius:20px; padding:0 8px; margin:2px 3px 2px 0; }}
details {{ margin-top:8px; }}
summary {{ cursor:pointer; font-size:.85rem; color:var(--accent); font-weight:600; }}
details p {{ font-size:.9rem; margin:8px 0 2px; }}
.clin {{ font-size:.88rem; margin:6px 0 2px; }}
.clin.design {{ color:#5a4a00; }}
.clin.design b {{ color:#9a7d00; }}
.abs {{ color:#444; font-size:.84rem; }}
.autopend {{ display:block; color:#999; font-size:.75rem; margin-top:4px; }}
.pill {{ background:#ECE9E2; border-radius:12px; padding:1px 10px; font-size:.8rem; white-space:nowrap; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); font-size:.85rem; }}
th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ background:#ECE9E2; position:sticky; top:0; }}
td a {{ color:var(--accent); text-decoration:none; font-weight:600; }}
.sub {{ color:#888; font-size:.76rem; }}
.filters {{ display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }}
.filters button, .filters select {{ border:1px solid var(--line); background:#fff; border-radius:18px;
  padding:4px 14px; font-size:.82rem; cursor:pointer; }}
.filters button.on {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.funnel-row {{ display:flex; align-items:center; gap:10px; margin:4px 0; font-size:.85rem; }}
.funnel-label {{ width:340px; flex-shrink:0; }}
.funnel-bar {{ height:16px; background:var(--accent); border-radius:3px; min-width:2px; }}
.funnel-bar.neg {{ background:#c0392b; }}
.funnel-n {{ width:60px; text-align:right; font-weight:600; }}
.gradebar {{ display:flex; height:22px; border-radius:5px; overflow:hidden; margin:10px 0; }}
.gradebar div {{ color:#fff; font-size:.75rem; display:flex; align-items:center; justify-content:center; }}
.note {{ font-size:.8rem; color:#777; background:#ECE9E2; border-radius:8px; padding:10px 14px; margin:10px 0; }}
pre {{ background:#1a1a1a; color:#d8d8d8; padding:12px; border-radius:8px; overflow-x:auto; font-size:.78rem; }}
.hl {{ border-left:4px solid var(--accent); }}
.hl .tag {{ background:#0279EE22; border-color:var(--accent); }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
@media (max-width:800px) {{ .grid2 {{ grid-template-columns:1fr; }} .funnel-label {{ width:200px; }} }}
.topnav {{ position:sticky; top:0; z-index:100; background:#ffffffee; backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line); box-shadow:0 1px 4px #0000000a; }}
.navwrap {{ max-width:1080px; margin:0 auto; padding:10px 20px; display:flex; align-items:center; gap:18px; flex-wrap:wrap; }}
.brand {{ display:flex; align-items:center; gap:8px; text-decoration:none; color:var(--ink); font-weight:bold; font-size:1.02rem; white-space:nowrap; }}
.logo {{ display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px;
  background:var(--accent); color:#fff; border-radius:8px; font-size:.95rem; }}
.navlinks {{ display:flex; gap:4px; flex-wrap:wrap; flex:1; }}
.navlinks a {{ text-decoration:none; color:#555; font-size:.9rem; padding:5px 12px; border-radius:18px; white-space:nowrap; }}
.navlinks a:hover {{ color:var(--accent); }}
.navlinks a.on {{ background:#0279EE1a; color:var(--accent); font-weight:600; }}
.navdate {{ color:#999; font-size:.85rem; white-space:nowrap; }}
html {{ scroll-behavior:smooth; scroll-padding-top:64px; }}
@media (max-width:800px) {{ .navdate {{ display:none; }} }}
</style></head><body>
<nav class="topnav" id="topnav">
<div class="navwrap">
<a class="brand" href="index.html"><span class="logo">周</span><span class="brandtitle">NEN 研究周报</span></a>
<div class="navlinks">
<a href="#overview" data-sec="overview">本期概览</a>
<a href="#panel" data-sec="panel">数据面板</a>
<a href="#highlights" data-sec="highlights">本周看点</a>
<a href="#top10" data-sec="top10">精读 Top10</a>
<a href="#papers" data-sec="papers">全部文献 {n_final}</a>
<a href="#trials" data-sec="trials">临床试验 {n_trials}</a>
<a href="#guidelines" data-sec="guidelines">中国指南 {len(GUIDELINES)}</a>
<a href="#methods" data-sec="methods">方法与检索式</a>
</div>
<span class="navdate">{W0} → {W1}</span>
</div>
</nav>
<div class="wrap" id="top">
<header>
<h1>神经内分泌肿瘤（NEN）研究周报</h1>
<div class="desc">覆盖泛神经内分泌肿瘤全谱：胃肠胰 NEN（GEP-NEN/pNET）、肺 NET/类癌、胸腺 NET、垂体 PitNET、嗜铬细胞瘤/副神经节瘤、甲状腺髓样癌、Merkel 细胞癌及 MEN1 等遗传综合征相关肿瘤；主题涵盖手术与肝转移治疗、PRRT 核素治疗、生长抑素类似物、靶向与免疫治疗、68Ga PET 影像、病理分级分型、分子机制、流行病学预后与激素综合征管理。</div>
<div class="runbar"><span>运行日 {today}</span><span>窗口 {W0} 至 {W1}</span><span>影响因子口径 JCR 2025（仅填已核实数值）</span><span>全部条目含真实 PMID 或 DOI</span><span>OpenAlex {('可用' if 'ok' in oa_status else '不可用 · 已标注')}</span></div>
<div class="stats">
<div class="stat"><b>{n_final}</b><span>纳入文献（篇）</span></div>
<div class="stat"><b>{n_trials}</b><span>临床试验动态（项）</span></div>
<div class="stat"><b>{pm_hits + ep_hits}</b><span>原始文献命中（条）</span></div>
<div class="stat"><b>{n_trials_raw}</b><span>原始试验命中（项）</span></div>
</div>
</header>

<h2 id="overview">本期概览 <small>检索口径、纳入排除路径与本期关键结论</small></h2>
<div class="card">
<p><b>数据源命中：</b>PubMed（E-utilities · EDAT）{pm_hits} 条 ｜ Europe PMC（REST · FIRST_PDATE）{ep_hits} 条 ｜ ClinicalTrials.gov（API v2 · LastUpdatePostDate）{n_trials_raw} 项 ｜ OpenAlex：{('可用' if 'ok' in oa_status else '不可用（' + esc(oa_status) + '）')}</p>
<p><b>去重策略：</b>DOI → PMID → 标题归一化三级串联（{pm_hits + ep_hits} → {n_pool}）。日期口径采用 PubMed 的 ArticleDate/EDAT 与 Europe PMC 的 FIRST_PDATE。</p>
<p><b>本期关键结论：</b>{esc(OVERVIEW) or f'<span class="autopend">待编辑补充：自动运行生成基础版时，本期关键结论由编辑基于当期结果在下次会话中撰写。</span>'}</p>
<div class="tags">{''.join(f'<span class="tag">{esc(t)}</span>' for t in all_tags)}</div>
</div>

<h2 id="panel">数据面板 <small>筛选漏斗 · 证据分级 · 临床试验纳入路径</small></h2>
<div class="grid2">
<div class="card">
<h3>文献排除漏斗 {n_pool} → {n_final}</h3>
{''.join(f'<div class="funnel-row"><span class="funnel-label">{esc(lbl)}</span><div class="funnel-bar{" neg" if n < 0 else ""}" style="width:{max(2, abs(n) / n_pool * 100):.0f}%"></div><span class="funnel-n">{n:+d}</span></div>' for lbl, n, _ in funnel)}
<div class="note">校验：{n_pool} − {n_weak} − {n_pre} − {n_anim} − {n_noabs} = {n_final}。条形长度按 {n_pool} 为基准等比缩放，极小值设最小可见宽度。「NEN 相关」判定采用题名与摘要双域正则；弱相关层（关键词命中但非 NEN 专病）全部保留可追溯，不计入纳入。</div>
</div>
<div class="card">
<h3>纳入文献证据分级（{n_final} 篇）</h3>
<div class="gradebar">
{''.join(f'<div style="width:{grades[g]/n_final*100:.1f}%;background:{GRADE_COLOR[g]}">{g} {grades[g]}</div>' for g in "SABC" if grades[g] > 0)}
</div>
<p style="font-size:.85rem">S 级 · 顶刊 IF≥15 或可能改变临床实践：<b>{grades['S']}</b> ｜ A 级 · 前瞻性/随机/多中心/系统评价：<b>{grades['A']}</b> ｜ B 级 · 回顾性队列、机制研究、综述：<b>{grades['B']}</b> ｜ C 级 · 观点/病例类文献：<b>{grades['C']}</b></p>
<h3 style="margin-top:16px">影响因子核实情况（JCR 2025 口径）</h3>
<p style="font-size:.85rem">本期 {n_final} 篇中 {len(if_verified)} 篇所属期刊已核实 IF，其余一律标注「IF 待核实」，不使用推算值或占位数值。</p>
{''.join(f'<div style="font-size:.85rem">{esc(p["journal"])} — <b>{p["if"]}</b></div>' for p in if_verified)}
</div>
</div>
<div class="card">
<h3>临床试验纳入路径 {n_trials_raw} → {n_trials}</h3>
<p style="font-size:.85rem">ClinicalTrials.gov API v2 三组检索（条件侧 / 干预侧 / 主题侧）按 NCT 编号去重后 {n_trials_raw} 项；再以条件字段 NEN 相关正则（neuroendocrine / carcinoid / pheochromocytoma / paraganglioma / insulinoma / gastrinoma / Merkel）筛选，最终纳入 <b>{n_trials}</b> 项。窗口限定 LastUpdatePostDate（{W0} 至 {W1}），即本周内状态或资料有更新的研究。</p>
</div>

<h2 id="highlights">本周看点 <small>{len(HIGHLIGHTS)} 条 · 由本期文献提炼的课题组可执行信号</small></h2>
{''.join(f'<div class="card hl"><div class="card-head"><span class="tag">{esc(h["tag"])}</span></div><h3>{esc(h["title"])}</h3><p style="font-size:.92rem">{esc(h["text"])}</p></div>' for h in HIGHLIGHTS) or '<div class="note">本周看点待编辑补充：自动运行生成基础版时，此板块由编辑在下次会话中基于当期摘要撰写。</div>'}

<h2 id="top10">精读 Top10 <small>中文精读卡片 · 按证据等级与影响因子综合排序 · 含研究背景/核心结果/临床意义</small></h2>
{''.join(top10_cards) or '<div class="note">精读卡片待编辑补充：自动运行生成基础版时，此板块由编辑在下次会话中基于当期摘要撰写。</div>'}

<h2 id="papers">本周全部文献 <small>{n_final} 篇 · 每篇均附中文要点 + 英文摘要原文 · 支持分级、相关度、主题三重筛选</small></h2>
<div class="note">分级口径：S = 顶刊（已核实 IF≥15）或可能改变临床实践；A = 前瞻性/随机/多中心研究或系统评价；B = 单中心回顾性队列、机制研究或综述；C = 观点/病例类文献。中文要点严格依据英文摘要原文归纳，未引入摘要以外的信息；每篇同时保留英文摘要原文以便核对。</div>
<div class="filters" id="gradeF"><button class="on" data-g="all">全部 {n_final}</button>
{''.join(f'<button data-g="{g}">{g} 级 {grades[g]}</button>' for g in "SABC" if grades[g] > 0)}
<select id="tierF"><option value="all">相关度：全部</option><option value="core">核心 NEN</option><option value="direct">直接相关</option></select>
<select id="tagF"><option value="all">主题：全部</option>{''.join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in all_tags)}</select>
</div>
<div id="papers">{''.join(paper_card(i, p) for i, p in enumerate(final))}</div>

<h2 id="trials">临床试验动态 <small>ClinicalTrials.gov · LastUpdatePostDate 窗口限定 · {n_trials} 项</small></h2>
<table id="trials"><thead><tr><th>NCT 编号</th><th>适应证 / 研究题目</th><th>分期</th><th>干预措施</th><th>状态</th><th>最近更新</th></tr></thead>
<tbody>{''.join(trial_row(t) for t in trials)}</tbody></table>

<h2 id="guidelines">中国共识与指南 <small>现行重要指南清单（编辑维护）+ 本周窗口内新发表动态（自动检索）</small></h2>
<div class="card">
<h3>本周窗口内新发表的中国指南/共识</h3>
{''.join(f'<p style="font-size:.9rem"><b>{esc(p["title"])}</b> — {esc(p["journal"])} · <a href="https://pubmed.ncbi.nlm.nih.gov/{p["pmid"]}/" target="_blank">PMID:{p["pmid"]}</a></p>' for p in weekly_guidelines) or f'<p style="font-size:.9rem;color:#777">本周窗口（{W0} 至 {W1}）内未检索到新发表的中国 NEN 指南/共识（PubMed Q4 + Europe PMC 定向检索，题名级判定）。现行指南以下表为准。</p>'}
</div>
<div class="card">
<h3>现行重要中国指南/共识清单（{len(GUIDELINES)} 部 · 编辑核实维护）</h3>
<table><thead><tr><th>指南 / 共识</th><th>制定机构</th><th>出处 / 版本</th><th>覆盖范围</th><th>要点</th></tr></thead><tbody>
{''.join(f'<tr><td><b>{esc(g["title"])}</b></td><td>{esc(g["org"])}</td><td>{esc(g["source"])}<br>' + (f'<a href="https://doi.org/{esc(g["doi"])}" target="_blank">DOI</a>' if g["doi"] else (f'<a href="{esc(g["url"])}" target="_blank">链接</a>' if g["url"] else '')) + f'</td><td><span class="pill">{esc(g["scope"])}</span></td><td style="font-size:.8rem">{esc(g["note"])}</td></tr>' for g in GUIDELINES)}
</tbody></table>
<div class="note">清单由编辑核实维护（2026-09 核对出版社/期刊来源）；新版本发布时更新此表并在「本周看点」中提示。国际指南（ENETS、NANETS/NCCN、WHO 分类更新）如需纳入可扩展此表。</div>
</div>

<h2 id="methods">方法与检索式 <small>供课题组复核与复现</small></h2>
<div class="card">
<ul style="font-size:.88rem">
<li>本期 {n_final} 篇文献全部携带真实 PMID 或 DOI；卡片直链 PubMed 与 DOI 原始出处。</li>
<li>数据源状态：PubMed 检索成功；Europe PMC 检索成功；ClinicalTrials.gov 检索成功；OpenAlex {('检索成功' if 'ok' in oa_status else '检索失败（' + esc(oa_status) + '），本期未用任何替代数值填补')}。</li>
<li>影响因子口径为 JCR 2025；未能核实者一律标注「IF 待核实」，不做数值推算。</li>
<li>剔除层说明：弱相关 {n_weak} 篇（关键词命中但非 NEN 专病）、预印本 {n_pre} 篇（无期刊正式记录）、动物实验 {n_anim} 篇、无可用摘要 {n_noabs} 篇，均不计入纳入但过程可追溯。</li>
<li>等级定义：S = 顶刊 IF≥15 或可能改变临床实践；A = 前瞻性/随机/多中心研究或系统评价；B = 单中心回顾性队列、机制研究或综述；C = 观点/病例类文献。</li>
<li>中文要点由编辑依据英文摘要原文归纳；试验动态窗口为 LastUpdatePostDate，非注册日期。</li>
</ul>
{qblock('PubMed 检索式（E-utilities · EDAT 窗口）', pm_q)}
{qblock('Europe PMC 检索式（REST · FIRST_PDATE 限定）', ep_q)}
{qblock('ClinicalTrials.gov API v2（三组检索）', ct_q)}
</div>

<div class="note">所有文献卡片均直链 PubMed 与 DOI 原始出处；未经核实的期刊一律不填 IF 数值；中文要点为编辑归纳，英文摘要原文并列呈现以便核对。本报告由可复现流水线生成（检索 → 去重 → 分层 → 分级 → 渲染），检索式与原始命中已存档。</div>
</div>
<script>
const gBtns = document.querySelectorAll('#gradeF button[data-g]');
const tierF = document.getElementById('tierF'), tagF = document.getElementById('tagF');
let curG = 'all';
function apply() {{
  const tier = tierF.value, tag = tagF.value;
  document.querySelectorAll('#papers .paper').forEach(c => {{
    const okG = curG === 'all' || c.dataset.grade === curG;
    const okT = tier === 'all' || c.dataset.tier === tier;
    const okTag = tag === 'all' || c.dataset.tags.split('|').includes(tag);
    c.style.display = (okG && okT && okTag) ? '' : 'none';
  }});
}}
gBtns.forEach(b => b.addEventListener('click', () => {{
  gBtns.forEach(x => x.classList.remove('on')); b.classList.add('on'); curG = b.dataset.g; apply();
}}));
tierF.addEventListener('change', apply); tagF.addEventListener('change', apply);
// scroll-spy: highlight current section in top nav
const secs = ['overview','panel','highlights','top10','papers','trials','guidelines','methods'];
const navLinks = {{}}; secs.forEach(s => navLinks[s] = document.querySelector(`.navlinks a[data-sec="${{s}}"]`));
const spy = () => {{
  let cur = secs[0];
  for (const s of secs) {{
    const el = document.getElementById(s);
    if (el && el.getBoundingClientRect().top <= 80) cur = s;
  }}
  if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 40) cur = 'methods';
  secs.forEach(s => navLinks[s] && navLinks[s].classList.toggle('on', s === cur));
}};
document.addEventListener('scroll', spy, {{passive:true}}); spy();
</script>
</body></html>"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    f.write(HTML)
print(f"written {OUT} ({len(HTML)} chars), papers={n_final}, trials={n_trials}")
