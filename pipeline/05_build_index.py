#!/usr/bin/env python3
"""NEN weekly - landing page (index.html) builder.

Scans SITE_DIR for NEN_weekly_YYYY-MM-DD.html issue files, reads their
machine-readable meta tags (with regex fallback for older issues), and
renders a landing page: latest-issue card + full archive table.

Usage: python 05_build_index.py [SITE_DIR]   (default: ../site relative to this script)
"""
import os, re, sys, html, datetime

SITE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "site")

ISSUE_RE = re.compile(r"^NEN_weekly_(\d{4}-\d{2}-\d{2})\.html$")

def esc(x): return html.escape(str(x or ""))

def meta_or(m, default=""):
    return m.group(1) if m else default

def parse_issue(path):
    text = open(path, encoding="utf-8").read()
    # preferred: machine-readable meta tags written by 03_build_html.py
    w0 = meta_or(re.search(r'<meta name="nen-window-start" content="([^"]+)"', text))
    w1 = meta_or(re.search(r'<meta name="nen-window-end" content="([^"]+)"', text))
    papers = meta_or(re.search(r'<meta name="nen-papers" content="([^"]+)"', text))
    trials = meta_or(re.search(r'<meta name="nen-trials" content="([^"]+)"', text))
    # fallback: parse title + stat blocks (seed issues generated before meta tags existed)
    tm = re.search(r"<title>.*?·\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})</title>", text)
    if tm and not (w0 and w1):
        w0, w1 = tm.group(1), tm.group(2)
    if not papers:
        pm = re.search(r'<div class="stat"><b>(\d+)</b><span>纳入文献（篇）', text)
        papers = pm.group(1) if pm else ""
    if not trials:
        tm2 = re.search(r'<div class="stat"><b>(\d+)</b><span>临床试验动态（项）', text)
        trials = tm2.group(1) if tm2 else ""
    return {"file": os.path.basename(path), "w0": w0, "w1": w1,
            "papers": papers, "trials": trials}

issues = []
for fn in sorted(os.listdir(SITE)):
    m = ISSUE_RE.match(fn)
    if m:
        issues.append(parse_issue(os.path.join(SITE, fn)))
issues.sort(key=lambda x: x["w1"], reverse=True)  # newest first

if not issues:
    sys.exit("no NEN_weekly_*.html issue files found in " + SITE)

latest = issues[0]
today = datetime.date.today().isoformat()
rows = "".join(
    f'<tr{" style=font-weight:600" if i == 0 else ""}>'
    f'<td>{"最新" if i == 0 else ""}</td>'
    f'<td>{esc(x["w0"])} 至 {esc(x["w1"])}</td>'
    f'<td>{esc(x["papers"])}</td><td>{esc(x["trials"])}</td>'
    f'<td><a href="{esc(x["file"])}">阅读本期</a>'
    f' · <a href="{esc(x["file"].replace(".html", "_summary.md"))}">Markdown</a></td></tr>'
    for i, x in enumerate(issues))

HTML = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEN 研究周报 · 每周更新</title>
<style>
:root {{ --ink:#1a1a1a; --bg:#FAF9F3; --card:#fff; --accent:#0279EE; --line:#e4e0d6; }}
* {{ box-sizing:border-box; }}
body {{ font-family:"Liberation Sans","Arimo","DejaVu Sans","PingFang SC","Microsoft YaHei",sans-serif;
  margin:0; background:var(--bg); color:var(--ink); line-height:1.65; }}
.wrap {{ max-width:900px; margin:0 auto; padding:40px 20px 80px; }}
h1 {{ font-size:1.8rem; margin:0 0 6px; }}
.desc {{ color:#555; font-size:.95rem; }}
.latest {{ background:var(--card); border:2px solid var(--accent); border-radius:12px; padding:24px 26px; margin:26px 0; }}
.latest .kicker {{ color:var(--accent); font-weight:700; font-size:.85rem; letter-spacing:.05em; }}
.latest h2 {{ margin:6px 0 10px; font-size:1.3rem; }}
.latest .nums {{ display:flex; gap:26px; flex-wrap:wrap; margin:14px 0 18px; }}
.latest .nums b {{ display:block; font-size:1.7rem; color:var(--accent); }}
.latest .nums span {{ font-size:.8rem; color:#666; }}
.btn {{ display:inline-block; background:var(--accent); color:#fff; text-decoration:none;
  border-radius:8px; padding:10px 22px; font-weight:600; }}
.btn:hover {{ opacity:.9; }}
h3.sec {{ margin:40px 0 10px; font-size:1.15rem; border-bottom:2px solid var(--ink); padding-bottom:6px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); font-size:.9rem; }}
th, td {{ padding:9px 12px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ background:#ECE9E2; font-size:.82rem; }}
td a {{ color:var(--accent); text-decoration:none; }}
.note {{ color:#777; font-size:.82rem; margin-top:18px; }}
</style></head><body>
<div class="wrap">
<h1>神经内分泌肿瘤（NEN）研究周报</h1>
<div class="desc">泛 NEN 全谱每周文献监测：PubMed · Europe PMC · ClinicalTrials.gov 三源检索，去重 → 相关度分层 → 证据分级 → 中文精读。每周一自动更新。</div>

<div class="latest">
<div class="kicker">最新一期</div>
<h2>{esc(latest["w0"])} 至 {esc(latest["w1"])}</h2>
<div class="nums">
<div><b>{esc(latest["papers"])}</b><span>纳入文献（篇）</span></div>
<div><b>{esc(latest["trials"])}</b><span>临床试验动态（项）</span></div>
</div>
<a class="btn" href="{esc(latest["file"])}">阅读本期周报 →</a>
</div>

<h3 class="sec">往期归档（{len(issues)} 期）</h3>
<table><thead><tr><th></th><th>检索窗口</th><th>文献（篇）</th><th>试验（项）</th><th>链接</th></tr></thead>
<tbody>{rows}</tbody></table>

<div class="note">每周一 09:00（北京时间）由 GitHub Actions 自动检索上一周窗口并发布基础版；编辑精读内容随后在会话中补充更新。
所有文献条目均携带真实 PMID 或 DOI；检索式与原始命中数见各期「方法与检索式」板块。页面生成于 {today}。</div>
</div>
</body></html>"""

out = os.path.join(SITE, "index.html")
open(out, "w", encoding="utf-8").write(HTML)
print(f"written {out} ({len(HTML)} chars), issues={len(issues)}, latest={latest['w1']}")
