"""Fetch citation counts from OpenAlex for topic-tagged papers.

Queries api.openalex.org by title (free, no key; mailto for the polite
pool), accepts a result only when the normalized titles match exactly,
and caches to ConferencesData/citations_openalex.json so reruns only
fetch new papers. Rerun after decisions/new conferences to refresh.
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

CACHE = os.path.join(ROOT, "ConferencesData", "citations_openalex.json")
MAILTO = "dotan.dicastro@forsightrobotics.com"


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def fetch_one(title):
    for attempt in range(5):
        try:
            r = requests.get(
                "https://api.openalex.org/works",
                params={"search": title, "per-page": 1,
                        "select": "display_name,cited_by_count,id",
                        "mailto": MAILTO},
                timeout=30,
            )
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            results = r.json()["results"]
            if results and norm_title(results[0]["display_name"] or "") == norm_title(title):
                return {"cites": results[0]["cited_by_count"], "id": results[0]["id"]}
            return {"cites": None}
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None  # transient failure; retry on next run


def main():
    _, papers = load_papers()
    titles = [p[1] for p in papers if p[9]]  # topic-tagged = short-viewer set
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [t for t in titles if norm_title(t) not in cache]
    print(f"{len(titles)} tagged papers, {len(todo)} to fetch")

    done = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for title, res in zip(todo, ex.map(fetch_one, todo)):
            done += 1
            if res is not None:
                cache[norm_title(title)] = res
            if done % 200 == 0:
                json.dump(cache, open(CACHE, "w"))
                print(f"{done}/{len(todo)}")
    json.dump(cache, open(CACHE, "w"))
    matched = sum(1 for t in titles if cache.get(norm_title(t), {}).get("cites") is not None)
    print(f"done: {matched}/{len(titles)} papers matched on OpenAlex")


if __name__ == "__main__":
    main()
