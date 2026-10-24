"""Download all CoRL 2026 PDFs listed in ConferenceTables/ into htmls/corl2026/pdfs/.

    uv run python OpenreviewScrape/pdf_downloader_CoRL_2026.py             # all papers
    uv run python OpenreviewScrape/pdf_downloader_CoRL_2026.py --limit 10  # quick check
    uv run python OpenreviewScrape/pdf_downloader_CoRL_2026.py --delay 10  # slower, if the default 3s hits the bot challenge
    uv run python OpenreviewScrape/pdf_downloader_CoRL_2026.py --arxiv     # fetch missing PDFs from arXiv instead

--arxiv searches arXiv by title and only accepts a near-identical title match.
Papers not found on arXiv are remembered in arxiv_not_found.txt and not
searched again; delete that file to retry them.

Resumable: finished PDFs are skipped on rerun. Each PDF is written to a .part
file and renamed only when complete, so a Ctrl+C never leaves a truncated PDF.
"""

import argparse
import difflib
import os
import re
import time
import xml.etree.ElementTree as ET

import requests
from tqdm import tqdm

from OpenreviewScrape import openreview_utils
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR

CSV = f"{PROJECT_ROOT_DIR}/ConferenceTables/robot-learning_org_CoRL_2026_Conference.csv"
OUT = f"{PROJECT_ROOT_DIR}/htmls/corl2026/pdfs"
CREDS = f"{PROJECT_ROOT_DIR}/credentials/openreview_api.txt"
NOT_FOUND = f"{OUT}/arxiv_not_found.txt"
ATOM = "{http://www.w3.org/2005/Atom}"

_client = [None]


def get_pdf(note_id):
    if _client[0] is None:
        _client[0] = openreview_utils.get_client(CREDS)
    try:
        return _client[0].get_pdf(note_id)
    except Exception:
        _client[0] = openreview_utils.get_client(CREDS)  # refresh expired token
        return _client[0].get_pdf(note_id)


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def arxiv_pdf(title, delay):
    """Return PDF bytes of the arXiv paper whose title matches, or None."""
    # short words ("to", "be", "via") break arXiv's ti: search; 5/8 vs 1/8 hits in testing
    words = [w for w in norm(title).split() if len(w) > 3] or norm(title).split()
    query = " AND ".join(f"ti:{w}" for w in words)
    r = requests.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": query, "max_results": 5},
        timeout=60,
    )
    r.raise_for_status()
    time.sleep(delay)  # arXiv API terms: no more than one request every 3s
    for entry in ET.fromstring(r.content).iter(f"{ATOM}entry"):
        found = entry.findtext(f"{ATOM}title", "")
        # ponytail: fuzzy title match, 0.9 tolerates punctuation/casing edits only
        if difflib.SequenceMatcher(None, norm(found), norm(title)).ratio() < 0.9:
            continue
        abs_url = entry.findtext(f"{ATOM}id")  # http://arxiv.org/abs/<id>v<n>
        pdf = requests.get(abs_url.replace("/abs/", "/pdf/"), timeout=120)
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF"):
            raise ValueError(f"not a PDF: {abs_url}")
        return pdf.content
    return None


def safe(s, n=90):
    return re.sub(r"[\\/:*?\"<>|]+", " ", s).strip()[:n]


def load_papers():
    papers = []
    with open(CSV) as f:
        for line in f:
            if line.startswith("id\t"):  # header row
                continue
            cols = line.rstrip("\n").split("\t")
            note_id = cols[0].split("id=")[-1]
            papers.append((note_id, cols[1]))
    return papers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only the first N papers")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between downloads")
    parser.add_argument("--arxiv", action="store_true", help="download from arXiv instead of OpenReview")
    args = parser.parse_args()

    papers = load_papers()[: args.limit]
    os.makedirs(OUT, exist_ok=True)
    not_found = set(open(NOT_FOUND).read().split()) if os.path.exists(NOT_FOUND) else set()

    downloaded = existing = failed = missing = 0
    for note_id, title in (bar := tqdm(papers, unit="pdf")):
        path = os.path.join(OUT, f"{note_id}_{safe(title)}.pdf")
        if os.path.exists(path):
            existing += 1
            continue
        if args.arxiv and note_id in not_found:
            missing += 1
            continue
        try:
            if args.arxiv:
                data = arxiv_pdf(title, args.delay)
                if data is None:
                    missing += 1
                    with open(NOT_FOUND, "a") as f:
                        f.write(note_id + "\n")
                    bar.set_postfix(new=downloaded, skip=existing, no_arxiv=missing, fail=failed)
                    continue
            else:
                data = get_pdf(note_id)
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
            downloaded += 1
            time.sleep(args.delay)  # 0.3s tripped OpenReview's bot challenge after ~26 PDFs
        except Exception as e:
            if "ChallengeRequired" in repr(e):
                tqdm.write("OpenReview bot challenge hit; stopping. Rerun later to resume.")
                break
            failed += 1
            tqdm.write(f"FAIL {note_id}: {e}")
        bar.set_postfix(new=downloaded, skip=existing, no_arxiv=missing, fail=failed)

    print(f"downloaded {downloaded}, existing {existing}, not on arXiv {missing}, failed {failed} -> {OUT}")


if __name__ == "__main__":
    main()
