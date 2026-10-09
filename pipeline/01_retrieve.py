#!/usr/bin/env python3
"""NEN weekly report - retrieval layer.
Queries PubMed, Europe PMC, ClinicalTrials.gov for a date window.
Saves raw hits + query log to JSON for reproducibility.
"""
import json, sys, time, urllib.parse, urllib.request, os

WINDOW_START, WINDOW_END = sys.argv[1], sys.argv[2]  # e.g. 2026-09-17 2026-09-24
OUTDIR = sys.argv[3] if len(sys.argv) > 3 else "/workspace/nen_weekly/raw"
os.makedirs(OUTDIR, exist_ok=True)

UA = {"User-Agent": "NEN-weekly-report/1.0 (research use)"}

def get(url, params=None, retries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  retry {i+1} for {url[:100]}: {e}", flush=True)
            time.sleep(3 * (i + 1))
    return None

log = {"window": [WINDOW_START, WINDOW_END], "sources": {}}

# ---------------- PubMed ----------------
PM_QUERIES = {
    "Q1_disease": '("neuroendocrine tumor"[tiab] OR "neuroendocrine tumors"[tiab] OR "neuroendocrine neoplasm"[tiab] OR "neuroendocrine neoplasms"[tiab] OR "neuroendocrine cancer"[tiab] OR "neuroendocrine carcinomas"[tiab] OR NEN[tiab] OR GEP-NEN[tiab] OR GEP-NET[tiab] OR pNET[tiab] OR pNEN[tiab] OR "pancreatic neuroendocrine"[tiab] OR "gastroenteropancreatic neuroendocrine"[tiab] OR carcinoid[tiab] OR " Merkel cell"[tiab] OR "medullary thyroid"[tiab] OR "pheochromocytoma"[tiab] OR "paraganglioma"[tiab]) AND ("{s}"[EDAT] : "{e}"[EDAT])',
    "Q2_treatment": '(neuroendocrine[tiab] OR carcinoid[tiab] OR pheochromocytoma[tiab] OR paraganglioma[tiab]) AND (PRRT[tiab] OR DOTATATE[tiab] OR DOTATOC[tiab] OR lutathera[tiab] OR "peptide receptor"[tiab] OR octreotide[tiab] OR lanreotide[tiab] OR pasireotide[tiab] OR everolimus[tiab] OR surufatinib[tiab] OR cabozantinib[tiab] OR lutetium-177[tiab] OR "liver transplant"[tiab] OR metastasectomy[tiab] OR "telotristat"[tiab]) AND ("{s}"[EDAT] : "{e}"[EDAT])',
    "Q3_mesh": '("Neuroendocrine Tumors"[Mesh] OR "Carcinoid Tumors"[Mesh] OR "Pheochromocytoma"[Mesh] OR "Paraganglioma"[Mesh] OR "Medullary Thyroid Carcinoma"[Mesh] OR "Merkel Cell Carcinoma"[Mesh]) AND ("{s}"[EDAT] : "{e}"[EDAT])',
    "Q4_guideline_cn": '(neuroendocrine[tiab] OR carcinoid[tiab] OR pheochromocytoma[tiab] OR paraganglioma[tiab] OR "medullary thyroid"[tiab]) AND (consensus[tiab] OR guideline*[tiab] OR "expert agreement"[tiab] OR "expert recommendation"[tiab]) AND (China[tiab] OR Chinese[tiab]) AND ("{s}"[EDAT] : "{e}"[EDAT])',
}

def pubmed_search(query):
    q = query.format(s=WINDOW_START, e=WINDOW_END)
    txt = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
              {"db": "pubmed", "term": q, "retmax": 0, "retmode": "json", "datetype": "edat"})
    if not txt:
        return None, q
    return int(json.loads(txt)["esearchresult"]["count"]), q

pm_counts = {}
for name, q in PM_QUERIES.items():
    n, full_q = pubmed_search(q)
    pm_counts[name] = n
    log["sources"][f"pubmed_{name}"] = {"query": full_q, "count": n}
    print(f"PubMed {name}: {n}", flush=True)
    time.sleep(1)

# Fetch details for union of Q1+Q2+Q3 via combined OR search, retmax 800
combined = "(" + ") OR (".join([q.format(s=WINDOW_START, e=WINDOW_END) for q in PM_QUERIES.values()]) + ")"
txt = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
          {"db": "pubmed", "term": combined, "retmax": 800, "retmode": "json", "datetype": "edat"})
ids = json.loads(txt)["esearchresult"]["idlist"] if txt else []
print(f"PubMed combined ids: {len(ids)}", flush=True)

pm_articles = []
for i in range(0, len(ids), 100):
    chunk = ids[i:i+100]
    txt = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
              {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
    if txt:
        pm_articles.append(txt)
    time.sleep(1)
with open(f"{OUTDIR}/pubmed_articles.xml", "w") as f:
    f.write("<PubmedArticleSet>" + "".join(pm_articles) + "</PubmedArticleSet>")
log["sources"]["pubmed_fetch"] = {"ids": len(ids)}

# ---------------- Europe PMC ----------------
EPM_QUERIES = {
    "main_OR": '("neuroendocrine tumor" OR "neuroendocrine tumors" OR "neuroendocrine neoplasm" OR "neuroendocrine neoplasms" OR "neuroendocrine cancer" OR NEN OR GEP-NEN OR GEP-NET OR pNET OR pNEN OR "pancreatic neuroendocrine" OR "gastroenteropancreatic neuroendocrine" OR carcinoid OR "carcinoid tumor" OR pheochromocytoma OR paraganglioma OR "medullary thyroid carcinoma" OR "Merkel cell carcinoma") AND (FIRST_PDATE:[{s} TO {e}])',
    "directed_AND": '(neuroendocrine OR carcinoid) AND (PRRT OR DOTATATE OR DOTATOC OR lutathera OR "peptide receptor radionuclide" OR octreotide OR lanreotide OR pasireotide OR everolimus OR surufatinib OR cabozantinib OR "liver metastas*") AND (FIRST_PDATE:[{s} TO {e}])',
    "guideline_cn": '(neuroendocrine AND (China OR Chinese) AND (consensus OR guideline OR "expert recommendation")) AND (FIRST_PDATE:[{s} TO {e}])',
}

def epmc_search(query, page=1):
    q = query.format(s=WINDOW_START, e=WINDOW_END)
    txt = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
              {"query": q, "format": "json", "pageSize": 200, "page": page,
               "resultType": "core"})
    if not txt:
        return None, q
    d = json.loads(txt)
    return d, q

epmc_records = {}
epmc_counts = {}
for name, q in EPM_QUERIES.items():
    d, full_q = epmc_search(q)
    if d is None:
        epmc_counts[name] = None
        log["sources"][f"europepmc_{name}"] = {"query": full_q, "count": None, "status": "failed"}
        continue
    hits = d.get("resultList", {}).get("result", [])
    nl = d.get("hitCount", len(hits))
    epmc_counts[name] = nl
    pages = 1
    all_hits = list(hits)
    while len(all_hits) < min(nl, 800) and pages < 5:
        d2, _ = epmc_search(q, pages + 1)
        if not d2:
            break
        all_hits += d2.get("resultList", {}).get("result", [])
        pages += 1
    for h in all_hits:
        k = h.get("id") or h.get("doi") or h.get("title")
        if k and k not in epmc_records:
            epmc_records[k] = h
    log["sources"][f"europepmc_{name}"] = {"query": full_q, "count": nl}
    print(f"EuropePMC {name}: {nl}", flush=True)
    time.sleep(1)

with open(f"{OUTDIR}/europepmc_records.json", "w") as f:
    json.dump(list(epmc_records.values()), f, ensure_ascii=False)

# ---------------- ClinicalTrials.gov ----------------
CT_QUERIES = {
    "cond": '("neuroendocrine tumors" OR "neuroendocrine tumor" OR "neuroendocrine neoplasm" OR carcinoid OR pheochromocytoma OR paraganglioma OR "pancreatic neuroendocrine" OR "gastroenteropancreatic neuroendocrine")',
    "intr": '("peptide receptor radionuclide" OR PRRT OR DOTATATE OR DOTATOC OR lutathera OR octreotide OR lanreotide OR pasireotide OR telotristat) AND (neuroendocrine OR carcinoid)',
    "term": '"neuroendocrine tumor" OR "neuroendocrine cancer" OR GEP-NET OR pNET',
}

def ct_search(param, query, page_token=None):
    params = {param: query,
              "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{WINDOW_START},{WINDOW_END}]",
              "countTotal": "true", "pageSize": 100,
              "fields": "NCTId|BriefTitle|Condition|OverallStatus|Phase|InterventionName|LeadSponsorName|LastUpdatePostDate|BriefSummary|EnrollmentCount|StudyType"}
    if page_token:
        params["pageToken"] = page_token
    txt = get("https://clinicaltrials.gov/api/v2/studies", params)
    if not txt:
        return None, params[param]
    return json.loads(txt), params[param]

ct_studies = {}
ct_counts = {}
for name, q in CT_QUERIES.items():
    param = {"cond": "query.cond", "intr": "query.intr", "term": "query.term"}[name]
    d, full_q = ct_search(param, q)
    if d is None:
        ct_counts[name] = None
        log["sources"][f"ctgov_{name}"] = {"query": full_q, "count": None, "status": "failed"}
        continue
    total = d.get("totalCount", 0)
    ct_counts[name] = total
    studies = d.get("studies", [])
    token = d.get("nextPageToken")
    while token and len(studies) < min(total, 600):
        d2, _ = ct_search(param, q, token)
        if not d2 or not d2.get("studies"):
            break
        studies += d2["studies"]
        token = d2.get("nextPageToken")
    for s in studies:
        nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if nct:
            ct_studies[nct] = s
    log["sources"][f"ctgov_{name}"] = {"query": full_q, "count": total}
    print(f"CTgov {name}: {total}", flush=True)
    time.sleep(1)

with open(f"{OUTDIR}/ctgov_studies.json", "w") as f:
    json.dump(list(ct_studies.values()), f, ensure_ascii=False)

# ---------------- OpenAlex (attempt, may 429) ----------------
oa_txt = get("https://api.openalex.org/works",
             {"filter": f"from_publication_date:{WINDOW_START},to_publication_date:{WINDOW_END}",
              "search": "neuroendocrine tumor", "per-page": 1})
log["sources"]["openalex"] = {"status": "ok" if oa_txt else "failed (HTTP 429 / quota)"}
print(f"OpenAlex: {'ok' if oa_txt else 'failed'}", flush=True)

with open(f"{OUTDIR}/query_log.json", "w") as f:
    json.dump(log, f, ensure_ascii=False, indent=2)
print("DONE", flush=True)
