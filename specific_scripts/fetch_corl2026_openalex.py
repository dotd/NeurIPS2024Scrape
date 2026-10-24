"""Fetch OpenAlex metadata for CoRL 2026 papers: citations, author institutions
(typed company / education), and author citation stats.

Cached to htmls/corl2026/openalex.json (rerun only fetches missing papers; failed requests
are not cached, so a rerun retries them). Without an API key OpenAlex shares a small daily
budget per IP; put a free key (https://openalex.org/settings/api) in credentials/openalex_key.txt.
htmls/corl2026/build.py turns it into the company / university / researcher filters.

    uv run python specific_scripts/fetch_corl2026_openalex.py
"""

import concurrent.futures as cf
import csv
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "ConferenceTables", "robot-learning_org_CoRL_2026_Conference.csv")
OUT = os.path.join(ROOT, "htmls", "corl2026", "openalex.json")
API = "https://api.openalex.org"
KEY_FILE = os.path.join(ROOT, "credentials", "openalex_key.txt")
KEY = open(KEY_FILE).read().strip() if os.path.exists(KEY_FILE) else None


def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def get(url, params):
    for attempt in range(6):
        try:
            r = requests.get(url, params={**params, **({"api_key": KEY} if KEY else {})}, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None


def fetch_work(title):
    """Exact (normalized) title match; None = not in OpenAlex, "error" = request failed (retry later)."""
    q = re.sub(r"[^\w\s-]", " ", title)  # OpenAlex search chokes on ':' and ','
    d = get(f"{API}/works", {"search": q, "per-page": 5, "select": "id,title,cited_by_count,authorships"})
    if not d or "results" not in d:  # budget exhausted / network error
        return "error"
    for w in d["results"]:
        if w.get("title") and norm(w["title"]) == norm(title):
            return {
                "openalex_id": w["id"],
                "cites": w["cited_by_count"],
                "authors": [{
                    "id": a["author"].get("id"),
                    "name": a["author"].get("display_name"),
                    "institutions": [{"name": i["display_name"], "type": i.get("type")}
                                     for i in a.get("institutions", []) if i.get("display_name")],
                } for a in w.get("authorships", [])],
            }
    return None


def fetch_authors(ids):
    """OpenAlex author id -> {name, cites, h_index}, 50 per request."""
    out = {}
    for i in range(0, len(ids), 50):
        chunk = [a.rsplit("/", 1)[-1] for a in ids[i:i + 50]]
        d = get(f"{API}/authors", {"filter": "ids.openalex:" + "|".join(chunk), "per-page": 50,
                                   "select": "id,display_name,cited_by_count,summary_stats"})
        for a in (d or {}).get("results", []):
            out[a["id"]] = {"name": a["display_name"], "cites": a["cited_by_count"],
                            "h_index": (a.get("summary_stats") or {}).get("h_index")}
    return out


def main():
    csv.field_size_limit(sys.maxsize)
    with open(CSV, newline="") as f:
        papers = {r["id"].split("id=")[-1]: r["title"]
                  for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE) if r["id"]}

    cache = json.load(open(OUT)) if os.path.exists(OUT) else {"works": {}, "authors": {}}
    todo = [pid for pid in papers if pid not in cache["works"]]
    errors = 0
    print(f"{len(todo)} papers to fetch")
    # ponytail: 4 workers stays under OpenAlex's anonymous rate limit
    with cf.ThreadPoolExecutor(4) as ex:
        for n, (pid, w) in enumerate(zip(todo, ex.map(lambda p: fetch_work(papers[p]), todo)), 1):
            if w == "error":
                errors += 1
                continue
            cache["works"][pid] = w
            if n % 50 == 0:
                print(f"  {n}/{len(todo)}")

    ids = sorted({a["id"] for w in cache["works"].values() if w for a in w["authors"] if a["id"]}
                 - set(cache["authors"]))
    print(f"{len(ids)} authors to fetch")
    cache["authors"].update(fetch_authors(ids))

    with open(OUT, "w") as f:
        json.dump(cache, f, ensure_ascii=False)
    found = [w for w in cache["works"].values() if w]
    with_inst = sum(1 for w in found if any(a["institutions"] for a in w["authors"]))
    print(f"matched {len(found)}/{len(papers)} papers, {with_inst} with institutions, "
          f"{len(cache['authors'])} authors -> {OUT}")
    if errors:
        print(f"{errors} requests failed (rate limit?) -- rerun later or add {KEY_FILE}")


if __name__ == "__main__":
    main()
