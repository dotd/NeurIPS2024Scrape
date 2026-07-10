"""Fetch citation counts from Semantic Scholar for topic-tagged papers.

Uses the title-match endpoint (free, no key). Accepts a result only when
normalized titles match exactly. Stores citationCount and
influentialCitationCount, cached to ConferencesData/citations_s2.json so
reruns only fetch new papers. Rerun to refresh after new conferences.

ponytail: low concurrency + delay to stay under S2's shared rate limit;
add an API key (x-api-key header) if you need it faster.
"""

import concurrent.futures as cf
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_all_conferences_filter import ROOT, load_papers

CACHE = os.path.join(ROOT, "ConferencesData", "citations_s2.json")
MATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/match"
FIELDS = "title,citationCount,influentialCitationCount,paperId"


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def fetch_one(title):
    for attempt in range(6):
        try:
            r = requests.get(MATCH_URL, params={"query": title, "fields": FIELDS}, timeout=30)
            if r.status_code == 429:
                time.sleep(2 + 2 ** attempt)
                continue
            if r.status_code == 404:  # S2 found no title match
                return {"cites": None}
            r.raise_for_status()
            data = r.json().get("data") or []
            if data and norm_title(data[0].get("title") or "") == norm_title(title):
                return {"cites": data[0]["citationCount"],
                        "influential": data[0]["influentialCitationCount"],
                        "id": data[0]["paperId"]}
            return {"cites": None}
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None  # transient failure; retry on next run


def main():
    _, papers = load_papers()
    titles = [p[1] for p in papers if p[9]]  # topic-tagged = short-viewer set
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [t for t in titles if norm_title(t) not in cache]
    print(f"{len(titles)} tagged papers, {len(todo)} to fetch", flush=True)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        for title, res in zip(todo, ex.map(fetch_one, todo)):
            done += 1
            if res is not None:
                cache[norm_title(title)] = res
            if done % 200 == 0:
                json.dump(cache, open(CACHE, "w"))
                print(f"{done}/{len(todo)}", flush=True)
    json.dump(cache, open(CACHE, "w"))
    matched = sum(1 for t in titles if cache.get(norm_title(t), {}).get("cites") is not None)
    print(f"done: {matched}/{len(titles)} papers matched on Semantic Scholar", flush=True)


if __name__ == "__main__":
    main()
