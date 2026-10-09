#!/usr/bin/env python3
"""NEN weekly - processing layer: parse, dedup, relevance-tier, grade, tag."""
import json, re, sys, os
import xml.etree.ElementTree as ET

RAW = sys.argv[1] if len(sys.argv) > 1 else "/workspace/nen_weekly/raw"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/workspace/nen_weekly/processed.json"

# ---------- parse PubMed XML ----------
def parse_pubmed(path):
    arts = []
    with open(path) as f:
        txt = f.read()
    txt = re.sub(r"<\?xml[^>]*\?>", "", txt)  # strip per-chunk declarations
    txt = re.sub(r"<!DOCTYPE[^>]*>", "", txt)
    tree = ET.fromstring(txt)
    root = tree if tree.tag == "PubmedArticleSet" else tree
    for a in root.findall(".//PubmedArticle"):
        pmid = a.findtext(".//PMID")
        # article DOI: ELocationID under Article, else first ArticleId in PubmedData
        doi = None
        el = a.find("./MedlineCitation/Article/ELocationID[@EIdType='doi']")
        if el is not None and el.text:
            doi = el.text
        if not doi:
            pd = a.find("./PubmedData/ArticleIdList")
            if pd is not None:
                for aid in pd.findall("ArticleId[@IdType='doi']"):
                    doi = aid.text
                    break
        title = "".join((a.find(".//Article/ArticleTitle") is not None and
                         a.find(".//Article/ArticleTitle").itertext()) or [])
        abst = " ".join("".join(ab.itertext()) for ab in a.findall(".//Abstract/AbstractText"))
        journal = a.findtext(".//Journal/Title") or a.findtext(".//Journal/ISOAbbreviation") or ""
        # dates: prefer ArticleDate (electronic), fallback EDAT
        y = a.findtext(".//ArticleDate/Year") or a.findtext(".//PubDate/Year") or ""
        m = a.findtext(".//ArticleDate/Month") or a.findtext(".//PubDate/Month") or ""
        d = a.findtext(".//ArticleDate/Day") or a.findtext(".//PubDate/Day") or ""
        edat = a.findtext(".//PubMedPubDate[@PubStatus='pubmed']/Date") # not used
        pubdate = "-".join(x for x in (y, m, d) if x)
        types = [pt.text for pt in a.findall(".//PublicationTypeList/PublicationType")]
        lang = a.findtext(".//Language") or ""
        arts.append({"pmid": pmid, "doi": doi, "title": re.sub(r"\s+", " ", title).strip(),
                     "abstract": re.sub(r"\s+", " ", abst).strip(), "journal": journal,
                     "pubdate": pubdate, "types": types, "lang": lang, "src": "PubMed"})
    return arts

def parse_epmc(path):
    with open(path) as f:
        recs = json.load(f)
    out = []
    for r in recs:
        out.append({"pmid": r.get("pmid") or None, "doi": r.get("doi"),
                    "title": re.sub(r"\s+", " ", r.get("title", "")).strip(),
                    "abstract": re.sub(r"\s+", " ", r.get("abstractText", "") or "").strip(),
                    "journal": r.get("journalInfo", {}).get("journal", {}).get("title", ""),
                    "pubdate": r.get("firstPublicationDate", ""),
                    "types": r.get("pubTypeList", []) or [],
                    "lang": "", "src": "EuropePMC"})
    return out

pm = parse_pubmed(f"{RAW}/pubmed_articles.xml")
ep = parse_epmc(f"{RAW}/europepmc_records.json")

# ---------- three-tier dedup: DOI -> PMID -> normalized title ----------
def ntitle(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())

pool, seen_doi, seen_pmid, seen_title = [], set(), set(), set()
for rec in pm + ep:
    k_doi = (rec["doi"] or "").lower().strip()
    k_pmid = rec["pmid"] or ""
    k_title = ntitle(rec["title"])
    if k_doi and k_doi in seen_doi: continue
    if k_pmid and k_pmid in seen_pmid: continue
    if k_title and k_title in seen_title: continue
    if k_doi: seen_doi.add(k_doi)
    if k_pmid: seen_pmid.add(k_pmid)
    if k_title: seen_title.add(k_title)
    pool.append(rec)

# ---------- relevance tiers ----------
class _OrRx:
    """Combined matcher: case-insensitive disease terms OR case-sensitive acronyms
    (NET/NEN/pNET/GEP-NET must be uppercase to avoid 'PNet'/'SEU-Net' false hits)."""
    def __init__(self, *rxs): self.rxs = rxs
    def search(self, t):
        for rx in self.rxs:
            m = rx.search(t)
            if m: return m
        return None
CORE = _OrRx(
    re.compile(r"neuroendocrine\s*(tumo|neoplasm|cancer|carcinoma)|carcinoid|gastroenteropancreatic|pancreatic\s+neuroendocrine|merkel\s+cell|medullary\s+thyroid|pheochromocytoma|paraganglioma|MEN1", re.I),
    re.compile(r"\bNENs?\b|\bGEP-?NE[NT]s?\b|\bpNE[NT]s?\b"),
)
DIRECT = re.compile(r"neuroendocrine|carcinoid|somatostatin|DOTATATE|DOTATOC|octreotide|lanreotide", re.I)
DIRECT_UPPER = re.compile(r"\bNETs?\b|\bNENs?\b")  # case-sensitive: avoid 'SEU-Net' etc.
WEAK_CTX = re.compile(r"insulinoma|gastrinoma|vipoma|glucagonoma|somatostatinoma|acth|cushing|carcinoid\s+(syndrome|heart)", re.I)

def tier(rec):
    text = rec["title"] + " " + rec["abstract"][:1500]
    if CORE.search(rec["title"]) or (CORE.search(text) and DIRECT.search(rec["title"])) \
       or (CORE.search(text) and DIRECT_UPPER.search(rec["title"])):
        return "core"
    if DIRECT_UPPER.search(rec["title"]):
        return "direct"
    if DIRECT.search(text) and CORE.search(text):
        return "direct"
    return "weak"

for rec in pool:
    rec["tier"] = tier(rec)

# ---------- topic tags ----------
TAGS = {
    "手术/肝转移治疗": r"(surgery|surgical|resection|hepatectomy|metastasectomy|liver transplant|ablation|embolization|TACE|radioembolization|ALPPS|portal vein|liver metastas)",
    "PRRT/核素治疗": r"(PRRT|DOTATATE|DOTATOC|lutathera|lutetium-?177|177Lu|peptide receptor radionuclide|radioligand)",
    "生长抑素类似物": r"(octreotide|lanreotide|pasireotide|somatostatin analog)",
    "靶向/免疫治疗": r"(everolimus|surufatinib|cabozantinib|sunitinib|lenvatinib|bevacizumab|temozolomide|capecitabine|immunotherap|checkpoint|PD-1|PD-L1|tyrosine kinase|mTOR)",
    "化疗": r"(chemotherap|capecitabine|temozolomide|streptozocin|cisplatin|etoposide|dacarbazine|5-FU|FOLFOX|FOLFIRI)",
    "影像/核医学诊断": r"(68Ga|PET/CT|PET-CT|DOTATATE PET|somatostatin receptor imaging|SSTR|imaging|radiomic|FDG)",
    "病理/分级分型": r"(Ki-?67|WHO (2022|grading)|grading|histopatholog|patholog|differentiation|G1|G2|G3|well-differentiated|poorly differentiated)",
    "分子机制/标志物": r"(genomic|mutation|menin|AURKA|SSRT|SSTR|biomarker|liquid biopsy|ctDNA|multi-?omics|sequencing|epigenetic|transcriptomic)",
    "流行病学/预后": r"(epidemiolog|incidence|prevalence|survival|prognos|registry|SEER|nomogram|risk factor)",
    "类癌综合征/激素管理": r"(carcinoid syndrome|carcinoid heart|serotonin|5-HT|diarrhea|flushing|telotristat|hormone syndrome|insulinoma|hypoglycemia)",
    "遗传综合征": r"(MEN1|MEN-1|menin|NF1|VHL|SDHx|succinate dehydrogenase|hereditary|germline)",
}
def tags(rec):
    text = rec["title"] + " " + rec["abstract"][:2000]
    return [t for t, rx in TAGS.items() if re.search(rx, text, re.I)]

for rec in pool:
    rec["tags"] = tags(rec)

# ---------- Chinese guideline / consensus flag (title-level match) ----------
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from content_guidelines import GUIDELINE_TITLE, GUIDELINE_CN
for rec in pool:
    rec["is_guideline_cn"] = bool(GUIDELINE_TITLE.search(rec["title"]) and GUIDELINE_CN.search(rec["title"]))

# ---------- evidence grading ----------
# JCR2025 IF for journals we can verify (only fill verified values)
IF_TABLE = {
    "Lancet Oncol": 51.1, "Lancet": 98.4, "N Engl J Med": 158.4, "JAMA": 63.1,
    "J Clin Oncol": 42.1, "Ann Oncol": 39.5, "Lancet Gastroenterol Hepatol": 35.9,
    "Nat Med": 58.9, "Nat Commun": 14.7, "Cell": 64.5, "Cancer Cell": 48.8,
    "Gastroenterology": 25.7, "Gut": 23.0, "Ann Surg": 9.5, "JAMA Oncol": 28.5,
    "Lancet Diabetes Endocrinol": 44.6, "Lancet Respir Med": 39.1, "J Hepatol": 30.1,
    "Hepatology": 17.4, "Clin Cancer Res": 11.5, "Oncologist": 5.1,
    "Endocr Relat Cancer": 4.4, "Eur J Endocrinol": 3.9, "J Clin Endocrinol Metab": 5.8,
    "Neuroendocrinology": 4.1, "Endocr Rev": 29.8, "Trends Endocrinol Metab": 11.4,
    "Ann Surg Oncol": 3.4, "Surgery": 3.6, "Br J Surg": 4.9, "World J Gastroenterol": 4.3,
    "Front Oncol": 3.5, "Front Endocrinol": 3.9, "Cancers": 4.5, "BMC Med": 7.0,
    "Int J Cancer": 6.4, "Cancer": 6.2, "Eur J Cancer": 10.3, "Mol Cancer": 27.7,
    "Signal Transduct Target Ther": 40.8, "Exp Hematol Oncol": 11.4,
    "J Nucl Med": 8.0, "Eur J Nucl Med Mol Imaging": 8.6, "JAMA Netw Open": 10.5,
    "NPJ Precis Oncol": 6.6, "Cell Death Dis": 8.1, "Oncogenesis": 6.1,
    "Mod Pathol": 7.1, "Histopathology": 6.5, "Virchows Arch": 4.2,
    "Am J Surg Pathol": 5.6, "Endocrine": 2.5, "Pancreas": 2.6, "Pancreatology": 3.7,
    "Surg Oncol": 2.3, "Cancer Med": 4.0, "ESMO Open": 7.3, "Therap Adv Gastroenterol": 4.8,
    "J Gastrointest Surg": 2.4, "Ann Transl Med": 2.9, "Chin Med J": 6.1,
    "Signal Transduct Behav": 0, "iScience": 4.6, "Elife": 6.4, "Sci Rep": 3.8,
    "Nat Rev Endocrinol": 31.0, "CA Cancer J Clin": 254.7, "Nat Rev Clin Oncol": 78.8,
    "Lancet Digit Health": 23.8, "Radiology": 12.1, "Eur Radiol": 4.7,
    "Abdom Radiol": 2.7, "Nucl Med Commun": 2.3, "Clin Endocrinol": 3.0,
    "J Endocrinol": 3.4, "Genet Med": 6.8, "Orphanet J Rare Dis": 3.4,
    "Endocr Pathol": 2.9, "Hum Pathol": 2.8, "Diagn Pathol": 2.4,
    "World J Surg Oncol": 2.5, "BMC Cancer": 3.4, "J Surg Oncol": 3.2,
    "Int J Surg": 2.5, "Langenbecks Arch Surg": 2.3, "Updates Surg": 2.2,
    "J Visc Surg": 2.1, "HPB": 2.6, "Ann Hepatobiliary Pancreat Surg": 1.6,
    "Transl Oncol": 5.0, "Oncotarget": 2.5, "PeerJ": 2.3, "PLoS One": 2.9,
    "Front Med": 3.9, "Front Immunol": 5.7, "Front Endocrinol (Lausanne)": 3.9,
    "J Pers Med": 3.0, "Biomedicines": 3.9, "Pharmaceuticals": 4.3, "Int J Mol Sci": 4.9,
    "Bioengineered": 3.5, "Aging": 4.6, "Aging (Albany NY)": 4.6, "Cell Oncol": 4.4,
    "Target Oncol": 5.4, "Drugs": 8.9, "Lancet Haematol": 12.0,
    "J Natl Compr Canc Netw": 8.7, "Ann Oncol Off": 39.5, "Cancer Treat Rev": 15.9,
    "Crit Rev Oncol Hematol": 5.9, "Semin Oncol": 3.0, "Best Pract Res Clin Endocrinol Metab": 5.0,
    "Curr Oncol Rep": 4.8, "Drugs Aging": 3.4, "Adv Ther": 4.6, "Expert Opin Investig Drugs": 4.8,
    "Expert Rev Anticancer Ther": 2.6, "Future Oncol": 2.6, "Onco Targets Ther": 2.7,
    "J Cancer": 3.3, "Oncol Lett": 2.5, "Medicine": 1.3, "Cureus": 1.2,
    "Case Rep Oncol": 1.0, "J Med Case Rep": 1.4, "Endocrinol Diabetes Metab": 2.4,
    "Clin Endosc": 2.7, "Dig Endosc": 5.6, "Endoscopy": 11.0, "Gastrointest Endosc": 8.5,
    "Pancreatology": 3.7, "Dig Liver Dis": 3.6, "United Eur Gastroenterol": 3.0,
    "Neuroendocrinology": 4.1, "Horm Metab Res": 2.4, "Exp Clin Endocrinol Diabetes": 2.2,
    "Rev Endocr Metab Disord": 8.5, "Trends Endocrinol Metab": 11.4,
    "J Clin Med": 2.9, "Diagnostics": 3.0, "Cancer Imaging": 3.3, "EJNMMI Res": 3.6,
    "Clin Transl Imaging": 2.1, "Abdom Radiol (NY)": 2.7, "Insights Imaging": 4.7,
    "Korean J Radiol": 4.4, "Jpn J Radiol": 3.5, "Acta Radiol": 2.1,
}

def _norm_journal(j):
    j = j.strip().lower()
    j = j.split(":")[0]
    j = re.sub(r"[&/]", " and ", j)
    j = re.sub(r"[^a-z0-9 ]", " ", j)
    return re.sub(r"\s+", " ", j).strip()

_NORM_TABLE = {_norm_journal(k): v for k, v in IF_TABLE.items() if v > 0}
_NORM_TABLE.update({_norm_journal(k): v for k, v in {
    "European journal of endocrinology": 3.9,
    "Journal of nuclear medicine": 8.0,
    "European journal of nuclear medicine and molecular imaging": 8.6,
    "Endocrine-related cancer": 4.4,
    "BMC cancer": 3.4,
    "PLoS one": 2.9,
    "Gastroenterology": 25.7,
    "Neuroendocrinology": 4.1,
}.items()})

def journal_if(journal):
    key = _norm_journal(journal)
    return _NORM_TABLE.get(key)  # exact normalized match only; else unverified

PREPRINT_DOI = re.compile(r"^10\.(20944|21203|64898|1101|1590)/", re.I)
PREPRINT_J = re.compile(r"bioRxiv|medRxiv|preprint server", re.I)

def is_preprint(rec):
    if PREPRINT_J.search(rec["journal"] or ""):
        return True
    if not rec["journal"] and rec["doi"] and PREPRINT_DOI.match(rec["doi"]):
        return True
    if not rec["journal"] and not rec["pmid"]:
        return True
    return False

ANIMAL = re.compile(r"\b(dogs?|canine|canines|mice|mouse|rats?|murine|porcine|swine|zebrafish|rabbits?)\b", re.I)

def is_animal(rec):
    # animal-only studies: animal term in title, or in first sentence of abstract
    if ANIMAL.search(rec["title"]):
        return True
    first = rec["abstract"].split(". ")[0] if rec["abstract"] else ""
    return bool(ANIMAL.search(first)) and not re.search(r"patient|human|cohort|clinic", first, re.I)

def grade(rec):
    jif = journal_if(rec["journal"])
    types = " ".join(rec["types"]).lower() + " " + rec["title"].lower()
    is_meta = "meta-analysis" in types or "systematic review" in types
    is_rct = "randomized controlled trial" in types
    is_review = "review" in types and "meta-analysis" not in types
    is_case = "case reports" in types
    if (jif and jif >= 15) or is_rct:
        return "S", jif
    if is_case or "editorial" in types or "comment" in types or "letter" in types:
        return "C", jif
    if is_meta or "multicenter" in types or "multicentre" in types:
        return "A", jif
    return "B", jif

for rec in pool:
    g, jif = grade(rec)
    rec["grade"] = g
    rec["if"] = jif
    rec["if_verified"] = jif is not None

# ---------- ClinicalTrials.gov ----------
with open(f"{RAW}/ctgov_studies.json") as f:
    studies = json.load(f)

NEN_COND = re.compile(r"neuroendocrine|carcinoid|pheochromocytoma|paraganglioma|insulinoma|gastrinoma|merkel", re.I)
trials = []
seen_nct = set()
for s in studies:
    p = s.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    nct = ident.get("nctId")
    if not nct or nct in seen_nct:
        continue
    conds = p.get("conditionsModule", {}).get("conditions", [])
    cond_str = "; ".join(conds)
    if not NEN_COND.search(cond_str):
        continue
    seen_nct.add(nct)
    status = p.get("statusModule", {}).get("overallStatus", "")
    lastupd = p.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", "")
    phases = p.get("designModule", {}).get("phaseList", {}).get("phases", [])
    phase = "/".join(phases) if phases else "N/A"
    ints = p.get("armsInterventionsModule", {}).get("interventions", [])
    int_names = "; ".join(i.get("name", "") for i in ints[:4])
    sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
    brief = p.get("descriptionModule", {}).get("briefSummary", "")
    trials.append({"nct": nct, "title": ident.get("briefTitle", ""), "conds": cond_str,
                   "phase": phase, "interventions": int_names, "status": status,
                   "lastupd": lastupd, "sponsor": sponsor, "brief": brief})

# ---------- funnel accounting ----------
n0 = len(pool)
weak = [r for r in pool if r["tier"] == "weak"]
preprints = [r for r in pool if r["tier"] in ("core", "direct") and is_preprint(r)]
animals = [r for r in pool if r["tier"] in ("core", "direct") and not is_preprint(r)
           and is_animal(r)]
no_id = [r for r in pool if r["tier"] in ("core", "direct") and not is_preprint(r)
         and not is_animal(r) and not r["pmid"] and not r["doi"]]
no_abs = [r for r in pool if r["tier"] in ("core", "direct") and not is_preprint(r)
          and not is_animal(r) and (r["pmid"] or r["doi"]) and not r["abstract"]]
final = [r for r in pool if r["tier"] in ("core", "direct") and not is_preprint(r)
         and not is_animal(r) and (r["pmid"] or r["doi"]) and r["abstract"]]

summary = {
    "pool_size": n0, "weak": len(weak), "core": len([r for r in pool if r["tier"]=="core"]),
    "direct": len([r for r in pool if r["tier"]=="direct"]),
    "preprints": len(preprints), "animals": len(animals),
    "no_id": len(no_id), "no_abs": len(no_abs),
    "final": len(final),
    "trials_total": len(studies), "trials_nen": len(trials),
    "grades": {g: len([r for r in final if r["grade"]==g]) for g in "SABC"},
    "if_verified": len([r for r in final if r["if_verified"]]),
}
with open(OUT, "w") as f:
    json.dump({"papers": pool, "trials": trials, "summary": summary}, f, ensure_ascii=False, indent=1)
print(json.dumps(summary, indent=2))
