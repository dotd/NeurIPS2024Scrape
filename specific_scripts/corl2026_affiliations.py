"""Extract author affiliations (companies / universities) from page 1 of each CoRL 2026 PDF.

Affiliation candidates come from the page-1 header (between title and abstract) and the
page-1 footnotes. Each candidate is resolved with ROR's affiliation matcher
(https://ror.readme.io/docs/match-organizations), which says whether an org is a company
or a university; well-known companies are also caught by name/email patterns because many
robotics startups aren't in ROR.

Writes htmls/corl2026/affiliations.json (ROR lookups are cached in it; reruns are cheap).

    uv run python specific_scripts/corl2026_affiliations.py
"""

import concurrent.futures as cf
import glob
import json
import os
import re
import sys
import time

import pymupdf
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_first_page import ANCHOR_SIZE, ANY_CAPTION_RE, SECTION_RE, blocks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "htmls", "corl2026", "pdfs")
OUT = os.path.join(ROOT, "htmls", "corl2026", "affiliations.json")
ROR = "https://api.ror.org/v2/organizations"

# canonical company name -> pattern over affiliation text and email domains
COMPANIES = {
    "Google DeepMind": r"\bGoogle\b|DeepMind|@google\.com|Everyday Robots",
    "NVIDIA": r"NVIDIA|@nvidia\.com",
    "Meta": r"\bMeta\b(?! ?-)|\bFAIR\b|Facebook|@meta\.com|@fb\.com",
    "Microsoft": r"Microsoft|@microsoft\.com",
    "Amazon": r"Amazon|\bAWS\b|@amazon\.com",
    "Toyota Research Institute": r"Toyota Research|\bTRI\b|@tri\.global",
    "Toyota": r"Toyota(?! Research)",
    "RAI Institute": r"RAI Institute|Robotics and AI Institute|Boston Dynamics AI Institute|\bThe AI Institute",
    "Boston Dynamics": r"Boston Dynamics(?! AI)",
    "Physical Intelligence": r"Physical Intelligence|pi\.website|@physicalintelligence",
    "Tesla": r"\bTesla\b",
    "Apple": r"\bApple\b|@apple\.com",
    "Samsung": r"Samsung",
    "Sony": r"\bSony\b",
    "Huawei": r"Huawei|Noah'?s Ark",
    "Tencent": r"Tencent",
    "Alibaba": r"Alibaba|DAMO Academy",
    "ByteDance": r"ByteDance|Bytedance",
    "Baidu": r"\bBaidu\b",
    "Xiaomi": r"Xiaomi",
    "Honda Research Institute": r"Honda",
    "Bosch": r"\bBosch\b",
    "Intel": r"\bIntel\b(?! ?ligen)|Intel Labs",
    "Qualcomm": r"Qualcomm",
    "IBM": r"\bIBM\b",
    "Disney Research": r"Disney",
    "OpenAI": r"OpenAI",
    "Figure AI": r"Figure AI",
    "Skild AI": r"Skild",
    "1X": r"\b1X Technologies\b|\b1X\b(?= ?,|$)",
    "Agility Robotics": r"Agility Robotics",
    "Unitree": r"Unitree",
    "AgiBot": r"AgiBot|Agibot|Zhiyuan Robotics",
    "Galbot": r"Galbot|GALBOT",
    "Horizon Robotics": r"Horizon Robotics",
    "Mitsubishi Electric (MERL)": r"\bMERL\b|Mitsubishi",
    "Hyundai": r"Hyundai",
    "LG": r"\bLG\b|LG AI",
    "NAVER LABS": r"NAVER",
    "Waymo": r"Waymo",
    "Zoox": r"\bZoox\b",
    "Covariant": r"Covariant",
    "Dyna Robotics": r"Dyna Robotics",
    "Generalist AI": r"Generalist AI",
    "Field AI": r"Field AI",
    "Preferred Networks": r"Preferred Networks",
    "OMRON SINIC X": r"OMRON|Omron",
    "Siemens": r"Siemens",
    "ABB": r"\bABB\b",
    "Kuaishou": r"Kuaishou",
    "Meituan": r"Meituan",
    "JD": r"\bJD\.com\b|\bJD Explore\b|\bJD\b",
    "SenseTime": r"SenseTime",
    "Lenovo": r"Lenovo",
    "Li Auto": r"Li Auto",
    "XPeng": r"XPeng|Xpeng",
    "BYD": r"\bBYD\b",
    "Midea": r"Midea",
    "DJI": r"\bDJI\b",
    "Hugging Face": r"Hugging ?Face",
    "LimX Dynamics": r"LimX",
    "Fourier": r"Fourier Intelligence|Fourier Robotics",
    "UBTech": r"UBTech|UBTECH",
    "Astribot": r"Astribot",
    "Sanctuary AI": r"Sanctuary AI",
    "Apptronik": r"Apptronik",
    "Wayve": r"Wayve",
    "Ant Group": r"Ant Group",
    "Dexmate": r"Dexmate",
}
COMPANY_RES = {name: re.compile(p) for name, p in COMPANIES.items()}
# only these candidates are worth a ROR lookup
AFFIL_HINT = re.compile(r"Univ|Institut|College|School|Lab|Academ|Polytechn|ETH|EPFL|\bMIT\b|KAIST|Research|"
                        r"\bUC ?[A-Z]|\bCMU\b|HKUST|\bNUS\b|\bNTU\b|UCLA|UCSD|\bUSC\b|UIUC|Inria|CNRS|\bCEA\b|"
                        r"Max Planck|Fraunhofer|\bDLR\b|\bAIST\b|RIKEN|"
                        r"Cent(er|re)|\bInc\b|Corp|Ltd|GmbH|Company|Technolog|Robotics|\bAI\b|Dynamics|"
                        r"Intelligence|Hospital|Department|Dept")
NOT_AFFIL = re.compile(r"@|https?://|www\.|contribution|[Cc]orresponding|advis|[Pp]roject (page|lead)|"
                       r"arXiv|Conference on Robot Learning|©")
MARKERS = r"[\d∗*†‡§¶➤♮♯♭#]+"
# ROR doesn't resolve bare acronyms
ACRONYMS = {"MIT": "Massachusetts Institute of Technology", "CMU": "Carnegie Mellon University",
            "UCSD": "University of California San Diego", "UCLA": "University of California Los Angeles",
            "USC": "University of Southern California", "UIUC": "University of Illinois Urbana-Champaign",
            "HKUST": "Hong Kong University of Science and Technology", "NUS": "National University of Singapore",
            "NTU": "Nanyang Technological University", "KAIST": "Korea Advanced Institute of Science and Technology",
            "ETH": "ETH Zurich", "EPFL": "EPFL", "TUM": "Technical University of Munich",
            "KIT": "Karlsruhe Institute of Technology", "UT Austin": "University of Texas at Austin",
            "CUHK": "Chinese University of Hong Kong", "HKU": "University of Hong Kong",
            "SJTU": "Shanghai Jiao Tong University", "PKU": "Peking University", "ZJU": "Zhejiang University",
            "USTC": "University of Science and Technology of China", "GaTech": "Georgia Institute of Technology",
            "Georgia Tech": "Georgia Institute of Technology", "UW": "University of Washington",
            "UPenn": "University of Pennsylvania", "Penn": "University of Pennsylvania"}


def is_heading(text):
    """'1 Introduction', not '1 Dartmouth College, 2 Harvard University'."""
    return "," not in text and len(text.split()) <= 5


def candidates(page):
    """Affiliation-looking strings from the page-1 header and footnotes, plus the raw text for patterns."""
    # header by line, not block: some PDFs put title + authors + affiliations in one block
    lines = sorted(((pymupdf.Rect(l["bbox"]), "".join(sp["text"] for sp in l["spans"]).strip(),
                    max(sp["size"] for sp in l["spans"]))
                   for b in page.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] if l["spans"]),
                  key=lambda l: (round(l[0].y0), l[0].x0))
    lines = [l for l in lines if l[1]]
    # header ends at the abstract, section 1 or a figure caption (captions mention robot brands like Unitree)
    end = next((i for i, l in enumerate(lines) if l[1].startswith("Abstract") or ANY_CAPTION_RE.match(l[1]) or
                (SECTION_RE.match(l[1]) and l[2] >= ANCHOR_SIZE and is_heading(l[1]))), len(lines))
    big = max((l[2] for l in lines[:end]), default=0)
    header = [l[1] for l in lines[:end] if l[2] < big - 0.5 and l[2] >= 6]
    # footnotes wrap, so join each footnote block into one line before splitting on markers
    bl = blocks(page)
    foot = [b[1].replace("-\n", "").replace("\n", " ") for b in bl
            if b[0].y0 > 0.75 * page.rect.height and b[2] < ANCHOR_SIZE + 1
            and re.match(rf"\s*{MARKERS}|.*\b(is|are) with\b", b[1], re.S)]  # not captions / body text
    raw = "\n".join(header + foot)
    out, emails = [], []
    for line in raw.split("\n"):
        # "1Stanford University, 2University of Waterloo, 3NVIDIA" -> one entry per marker
        for seg in re.split(rf"(?:^|[\s,;]){MARKERS}\s*(?=[A-Z])", line):
            seg = re.sub(rf"^{MARKERS}\s*", "", seg).strip(" ,;.")
            seg = re.split(r"Correspondence|<|\S+@", seg)[0].strip(" ,;.")  # footnotes run on into emails
            seg = ACRONYMS.get(seg, seg)
            for bad, good in (("´e", "é"), ("´a", "á"), ("`e", "è"), ("¨o", "ö"), ("¨u", "ü"), ("¨a", "ä")):
                seg = seg.replace(bad, good)  # LaTeX accents extracted as separate glyphs
            hinted = AFFIL_HINT.search(seg) or any(rx.search(seg) for rx in COMPANY_RES.values())  # bare "3NVIDIA"
            if len(seg) >= 3 and hinted and not NOT_AFFIL.search(seg):
                out.append(seg[:200])
        if "@" in line or "pi.website" in line:
            emails.append(line)
    # company patterns only see affiliation lines + emails, never body/caption prose
    return out, "\n".join(out + emails)


def ror_match(text):
    """Chosen ROR org for an affiliation string -> {name, types}, None if no confident match."""
    for attempt in range(5):
        try:
            r = requests.get(ROR, params={"affiliation": text}, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 + 2 ** attempt)
                continue
            r.raise_for_status()
            for it in r.json().get("items", []):
                if it.get("chosen"):
                    org = it["organization"]
                    name = next((n["value"] for n in org["names"] if "ror_display" in n["types"]), org["names"][0]["value"])
                    return {"name": name, "types": org.get("types", [])}
            return None
        except requests.RequestException:
            time.sleep(2 + 2 ** attempt)
    return "error"


def canonical_company(name):
    return next((c for c, rx in COMPANY_RES.items() if rx.search(name)),
                re.sub(r"\s*\([^)]*\)$", "", name))  # "Nvidia (United States)" -> "Nvidia"


def main():
    cache = json.load(open(OUT)) if os.path.exists(OUT) else {}
    ror = cache.get("ror", {})
    per_paper = {}
    for pdf in sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf"))):
        pid = os.path.basename(pdf).split("_", 1)[0]
        try:
            per_paper[pid] = candidates(pymupdf.open(pdf)[0])
        except Exception as e:  # one broken pdf shouldn't stop the batch
            print(f"{pid}: {e}")

    todo = sorted({c for cands, _ in per_paper.values() for c in cands} - set(ror))
    print(f"{len(per_paper)} papers, {len(todo)} new affiliation strings to resolve with ROR")
    # ponytail: 4 workers keeps us well under ROR's 2000 requests / 5 min
    with cf.ThreadPoolExecutor(4) as ex:
        for n, (c, m) in enumerate(zip(todo, ex.map(ror_match, todo)), 1):
            if m != "error":
                ror[c] = m
            if n % 200 == 0:
                print(f"  {n}/{len(todo)}")

    papers = {}
    for pid, (cands, raw) in per_paper.items():
        companies = {c for c, rx in COMPANY_RES.items() if rx.search(raw)}
        universities = set()
        for c in cands:
            m = ror.get(c)
            if not m:
                continue
            if "education" in m["types"]:
                universities.add(m["name"])
            elif "company" in m["types"]:
                companies.add(canonical_company(m["name"]))
        papers[pid] = {"companies": sorted(companies), "universities": sorted(universities), "candidates": cands}

    with open(OUT, "w") as f:
        json.dump({"papers": papers, "ror": ror}, f, ensure_ascii=False, indent=0)
    print(f"{sum(1 for p in papers.values() if p['companies'])} papers with a company, "
          f"{sum(1 for p in papers.values() if p['universities'])} with a university -> {OUT}")


if __name__ == "__main__":
    main()
