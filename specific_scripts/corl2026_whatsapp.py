"""Data for the WhatsApp button of the CoRL 2026 browser: arXiv links and one-paragraph summaries.

    uv run python specific_scripts/corl2026_whatsapp.py arxiv      # arxiv.json: pid -> abs URL or "" (free, ~35 min)
    uv run python specific_scripts/corl2026_whatsapp.py summaries  # slide_summaries.json: pid -> {text, cost} (Claude)
    uv run python website/corl2026/build.py

arxiv: the arXiv API searched by title (exact match after normalizing case and punctuation), one request per 3 s as
arXiv asks. summaries: one slide (up to 7 bullets) per paper from its title + abstract. Both skip papers already done and save as they go, so they can be rerun.
"""

import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "website", "corl2026")
sys.path[:0] = [HERE, os.path.join(ROOT, "website")]
import build  # noqa: E402

ARXIV = os.path.join(HERE, "arxiv.json")
SHORT = os.path.join(HERE, "slide_summaries.json")
ATOM = "{http://www.w3.org/2005/Atom}"
PROMPT = """Summarize this CoRL 2026 robotics paper as a single slide for a WhatsApp message to robotics researchers:
at most 7 bullets with the paper's main points (problem, key idea, method, setup, main results with numbers, what's new).
Each bullet is one line of at most 20 words and starts with "• ". Output only the bullets: no title, no intro,
no markdown, no emojis, no hashtags.

Title: {title}
Abstract: {abstract}"""


def papers():
    columns, rows = build.csv_rows()
    return {r[0].split("id=")[-1]: dict(zip(columns, r)) for r in rows}


def norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def load(path):
    return json.load(open(path)) if os.path.exists(path) else {}


def arxiv():
    done = load(ARXIV)
    todo = {pid: p["title"] for pid, p in papers().items() if pid not in done}
    for n, (pid, title) in enumerate(todo.items(), 1):
        q = re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", title)).strip()
        for attempt in range(3):
            try:
                r = requests.get("https://export.arxiv.org/api/query", timeout=30,
                                 params={"search_query": f'ti:"{q}"', "max_results": 5})
                r.raise_for_status()
                break
            except requests.RequestException:
                time.sleep(10 * (attempt + 1))
        else:
            continue  # stays undone; a rerun retries it
        url = ""
        for e in ET.fromstring(r.content).iter(ATOM + "entry"):
            if norm(e.findtext(ATOM + "title", "")) == norm(title):
                url = re.sub(r"v\d+$", "", e.findtext(ATOM + "id", "")).replace("http://", "https://")
                break
        done[pid] = url
        json.dump(done, open(ARXIV, "w"), indent=1)
        if n % 50 == 0:
            print(f"{n}/{len(todo)}  {sum(bool(v) for v in done.values())} found", flush=True)
        time.sleep(3)  # arXiv API terms: one request every 3 seconds
    print(f"{sum(bool(v) for v in done.values())} of {len(done)} papers on arXiv -> {ARXIV}")


def summaries():
    import serve  # the Claude client and its cost accounting
    done, lock = load(SHORT), threading.Lock()
    todo = {pid: p for pid, p in papers().items() if pid not in done}

    def one(item):
        pid, p = item
        try:
            r = serve.ask_content(PROMPT.format(title=p["title"], abstract=p["abstract"]), 2000, "low")
        except Exception as e:  # noqa: BLE001  one failure shouldn't stop the batch; a rerun retries it
            print(f"skip {pid}: {e}", flush=True)
            return
        with lock:
            done[pid] = {"text": r["text"], "cost": r["cost"]}
            json.dump(done, open(SHORT, "w"), indent=1, ensure_ascii=False)

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        list(ex.map(one, todo.items()))
    print(f"{len(done)} summaries, ${sum(v['cost'] for v in done.values()):.2f} -> {SHORT}")


if __name__ == "__main__":
    {"arxiv": arxiv, "summaries": summaries}[sys.argv[1]]()
