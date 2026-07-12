"""Download the top-20 most-influential papers per (topic, conference).

For every (topic, conference) pair, sort that group's papers by
influentialCitationCount (desc) and download the top 20 PDFs into
pdfs/<topic>_<conference>/ via the authenticated OpenReview client.

    uv run python specific_scripts/download_top_pdfs.py          # download
    uv run python specific_scripts/download_top_pdfs.py --dry    # just counts

Papers without a note id (older hash-only CSVs) can't be fetched and are
reported as skips. Existing files are skipped, so reruns resume.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_all_conferences_filter import ROOT, TOPICS, load_papers

sys.path.insert(0, os.path.join(ROOT, "OpenreviewScrape"))
import openreview_utils

CREDS = os.path.join(ROOT, "credentials", "openreview_api.txt")
PDFS = os.path.join(ROOT, "pdfs")
TOP_N = 5
DRY = "--dry" in sys.argv

_client = [None]


def get_pdf(note_id):
    if _client[0] is None:
        _client[0] = openreview_utils.get_client(CREDS)
    try:
        return _client[0].get_pdf(note_id)
    except Exception:
        _client[0] = openreview_utils.get_client(CREDS)  # refresh expired token
        return _client[0].get_pdf(note_id)


def safe(s, n=90):
    return re.sub(r"[\\/:*?\"<>|]+", " ", s).strip()[:n]


def note_id(p):
    m = re.search(r"id=([^&]+)", p[6] or "")
    return m.group(1) if m else None


def main():
    _, papers = load_papers()
    topic_label = {key: label for key, label, _, _ in TOPICS}
    confs = sorted({p[0] for p in papers})

    total_dl = total_skip_noid = total_exist = total_fail = 0
    for key in topic_label:
        for conf in confs:
            group = [p for p in papers if key in p[9] and p[0] == conf]
            group.sort(key=lambda p: p[11] if p[11] is not None else -1, reverse=True)
            top = group[:TOP_N]
            if not top:
                continue
            folder = os.path.join(PDFS, f"{key}_{openreview_utils.normalize_venue_id(conf)}")
            have_id = sum(1 for p in top if note_id(p))
            print(f"{key}/{conf}: {len(top)} papers, {have_id} downloadable")
            if DRY:
                continue
            os.makedirs(folder, exist_ok=True)
            for rank, p in enumerate(top, 1):
                nid = note_id(p)
                fname = f"{rank:02d}_{p[11] or 0}infl_{safe(p[1])}.pdf"
                path = os.path.join(folder, fname)
                if os.path.exists(path):
                    total_exist += 1
                    continue
                if not nid:
                    total_skip_noid += 1
                    continue
                try:
                    data = get_pdf(nid)
                    with open(path, "wb") as f:
                        f.write(data)
                    total_dl += 1
                    time.sleep(0.3)  # ponytail: be polite to OpenReview
                except Exception as e:
                    total_fail += 1
                    print(f"  FAIL {nid}: {e}")
    print(f"\ndownloaded {total_dl}, existing {total_exist}, "
          f"no-id skips {total_skip_noid}, failures {total_fail}")


if __name__ == "__main__":
    main()
