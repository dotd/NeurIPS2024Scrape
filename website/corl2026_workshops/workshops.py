"""CoRL 2026 workshop papers, browsed with the same page and buttons as CoRL 2026 (one dropdown per workshop).

website/serve.py serves this folder at http://127.0.0.1:8026/Workshops/. Steps (each skips what's done, so rerun freely):

    uv run python website/corl2026_workshops/workshops.py fetch    # corl.org schedule + OpenReview accepted papers
    uv run python website/corl2026_workshops/workshops.py pdfs     # PDFs from OpenReview (logged in)
    uv run python website/corl2026_workshops/workshops.py extract  # figures, robots, backbones, GitHub, affiliations
    uv run python website/corl2026_workshops/workshops.py          # rebuild index.html

fetch: the workshop table of https://www.corl.org/program/workshops (title, website, venue, room, morning/afternoon),
each matched to its OpenReview group under robot-learning.org/CoRL/2026/Workshop by website, else title, else an
openreview.net/group link on the workshop's own site. Each workshop is a "session" of schedule.json, labelled
"time · venue room · title" and sorted by time then location, so the page's Session filter and By time view work as is.
"""

import concurrent.futures
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TITLE = "CoRL 2026 Workshops"
PAGE = "https://www.corl.org/program/workshops"
GROUP = "robot-learning.org/CoRL/2026/Workshop"
DAY = "Thu 11/12"  # the page: all workshops are on Thursday, November 12, 2026
COLUMNS = ["id", "title", "authors", "abstract", "🛠️ workshop", "🏷️ keywords", "pdf"]
UA = {"User-Agent": "Mozilla/5.0 (paper browser)"}

sys.path[:0] = [os.path.join(ROOT, "website", "corl2026"), os.path.join(ROOT, "specific_scripts"), os.path.join(ROOT, "OpenreviewScrape")]
import build  # noqa: E402


def load(name, default):
    return build.load(HERE, name, default)


def store(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w"), ensure_ascii=False, indent=1)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def norm_url(u):
    return re.sub(r"^https?://(www\.)?|/+$", "", (u or "").strip().lower())


def words(t):
    return set(re.findall(r"[a-z0-9]+", t.lower())) - {"corl", "2026", "workshop", "on", "the", "and", "for", "of", "a", "in", "to"}


def schedule_page():
    """[{title, url, venue, room, time, slot}] in page order; slot 0 = morning, 1 = afternoon."""
    page = html.unescape(html.unescape(get(PAGE)))  # a Google Sites embed: escaped in the page JSON, then as HTML
    out = []
    parts = re.split(r'<h3 id="(morning|afternoon)" class="section-heading">', page)
    for slot, (name, body) in enumerate(zip(parts[1::2], parts[2::2])):
        time = re.search(r'<span class="time">([^<]+)</span>', body).group(1).strip()
        for tr in re.findall(r'<tr class="ws">(.*?)</tr>', body.split("<h3", 1)[0], re.S):
            a = re.search(r'<td class="wtitle">\s*(?:<a href="([^"]*)"[^>]*>)?(.*?)(?:</a>)?\s*</td>', tr, re.S)
            venue = re.sub(r"<[^>]+>", "", re.search(r'data-label="Venue">(.*?)</td>', tr, re.S).group(1)).strip()
            room = re.sub(r"<[^>]+>", "", re.search(r'class="room">(.*?)</td>', tr, re.S).group(1)).strip()
            out.append({"title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a.group(2))).strip(), "url": a.group(1) or "",
                        "venue": venue, "room": room, "time": time, "slot": slot})
    return out


def match_group(w, groups):
    """The OpenReview group id of one workshop, or ""."""
    for g in groups:
        if w["url"] and norm_url(g["website"]) == norm_url(w["url"]):
            return g["id"]
    best = max(groups, key=lambda g: len(words(g["title"]) & words(w["title"])) / (len(words(w["title"]) | words(g["title"])) or 1))
    if len(words(best["title"]) & words(w["title"])) / (len(words(w["title"]) | words(best["title"])) or 1) >= 0.5:
        return best["id"]
    try:  # the workshop's own site may link its OpenReview page
        m = re.search(r"openreview\.net/group\?id=(" + re.escape(GROUP) + r"/[\w@.-]+)", urllib.parse.unquote(get(w["url"])))
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001  site down: the workshop is listed without papers
        return ""


def room_key(w):
    n = re.search(r"\d+", w["room"])
    return (w["slot"], w["venue"], int(n.group(0)) if n else 0, w["room"])


def fetch():
    from openreview_utils import get_client
    client = get_client(os.path.join(ROOT, "credentials", "openreview_api.txt"))
    groups = []
    for g in json.loads(get(f"https://api2.openreview.net/groups?parent={GROUP}&limit=500"))["groups"]:
        c = {k: v.get("value") for k, v in g.get("content", {}).items() if isinstance(v, dict)}
        if c.get("title"):
            groups.append({"id": g["id"], "title": c["title"], "website": c.get("website") or ""})
    workshops = sorted(schedule_page(), key=room_key)  # by time, then location
    papers, sched = {}, {"papers": {}, "sessions": [], "order": {}, "links": {}}
    for w in workshops:
        w["group"] = match_group(w, groups)
        w["label"] = f"{DAY}, {w['time']} · {w['venue']} {w['room']} · {w['title']}"
        notes = client.get_all_notes(content={"venueid": w["group"]}) if w["group"] else []
        print(f"{len(notes):4d} papers  {w['group'] or '(no OpenReview group)':55s} {w['title'][:60]}", flush=True)
        sched["sessions"].append(w["label"])
        sched["order"][w["label"]] = []
        sched["links"][w["label"]] = w["url"]
        for n in sorted(notes, key=lambda n: n.content["title"]["value"].lower()):
            c = {k: v.get("value") for k, v in n.content.items()}
            papers.setdefault(n.id, {"title": c["title"].strip(), "authors": ", ".join(x if isinstance(x, str) else x.get("fullname") or x.get("name") or ""  # str or {fullname, …}
                                                                for x in c.get("authors") or []),
                                     "abstract": (c.get("abstract") or "").strip(), "keywords": c.get("keywords") or [],
                                     "workshops": []})["workshops"].append(w["title"])
            sched["papers"].setdefault(n.id, {"sessions": []})["sessions"].append(w["label"])
            sched["order"][w["label"]].append(n.id)
    store("workshops.json", workshops)
    store("papers.json", papers)
    store("schedule.json", sched)
    print(f"{len(papers)} papers in {sum(bool(w['group']) for w in workshops)} of {len(workshops)} workshops")


def pdf_path(pid):
    return next((os.path.join(HERE, "pdfs", f) for f in os.listdir(os.path.join(HERE, "pdfs")) if f.startswith(pid + "_")), None)


def pdfs():
    import time

    import requests
    from openreview_utils import get_client
    token = get_client(os.path.join(ROOT, "credentials", "openreview_api.txt")).token
    os.makedirs(os.path.join(HERE, "pdfs"), exist_ok=True)
    todo = {pid: p for pid, p in load("papers.json", {}).items() if not pdf_path(pid)}

    def one(item):
        # plain requests with the login token: the openreview client's get_pdf can sleep for very long on rate limits
        pid, p = item
        for attempt in range(5):
            wait = 5 * 2 ** attempt
            try:
                r = requests.get("https://api2.openreview.net/pdf", params={"id": pid}, timeout=60,
                                 headers={"Authorization": "Bearer " + token})
            except requests.RequestException as e:
                err = str(e)
            else:
                if r.ok and r.content.startswith(b"%PDF-"):
                    name = re.sub(r"[^\w\- .,()]", " ", p["title"])[:100].strip()
                    with open(os.path.join(HERE, "pdfs", f"{pid}_{name}.pdf"), "wb") as f:
                        f.write(r.content)
                    return None
                err = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
                wait = min(int(r.headers.get("Retry-After") or wait), 120)
            time.sleep(wait)
        return f"skip {pid}: {err}"  # a rerun retries it

    with concurrent.futures.ThreadPoolExecutor(2) as ex:  # ponytail: 2 at a time, gentle on OpenReview
        for n, err in enumerate(ex.map(one, todo.items()), 1):
            if err:
                print(err, flush=True)
            if n % 25 == 0:
                print(f"{n}/{len(todo)}", flush=True)
    print(f"{len(os.listdir(os.path.join(HERE, 'pdfs')))} PDFs")


def extract():
    """What CoRL 2026 got from its batch scripts, per PDF (same as website/papers/papers.py add_pdf())."""
    from corl2026_affiliations import COMPANY_RES, candidates, canonical_company, ror_match
    from corl2026_backbones import backbones
    from corl2026_github import repos
    from corl2026_robots import robots
    from extract_first_page import extract as first_page
    os.makedirs(os.path.join(HERE, "figs"), exist_ok=True)
    fp, rb, bb, gh = (load(n, {}) for n in ("first_page.json", "robots.json", "backbones.json", "github.json"))
    aff = load("affiliations.json", {"papers": {}, "ror": {}})
    todo = [pid for pid in load("papers.json", {}) if pid not in fp and pdf_path(pid)]
    for n, pid in enumerate(todo, 1):
        pdf = pdf_path(pid)
        try:
            fp[pid] = first_page(pdf, os.path.join(HERE, "figs", f"{pid}.png"), base=HERE)
            with pymupdf.open(pdf) as doc:
                text = "\n".join(p.get_text() for p in doc)
                cands, raw = candidates(doc[0])
        except Exception as e:  # noqa: BLE001  an odd PDF: no figures / filters for it
            print(f"skip {pid}: {e}", flush=True)
            fp[pid] = {"title": "", "abstract": "", "figure": None, "figures": []}
            continue
        for d, found in [(rb, robots(text)), (bb, backbones(text)), (gh, repos(pdf))]:
            if found:
                d[pid] = found
        companies, universities = {c for c, rx in COMPANY_RES.items() if rx.search(raw)}, set()
        for c in cands:  # ROR API, cached per affiliation string
            if c not in aff["ror"] and (m := ror_match(c)) != "error":
                aff["ror"][c] = m
            org = aff["ror"].get(c)
            if org and "education" in org["types"]:
                universities.add(org["name"])
            elif org and "company" in org["types"]:
                companies.add(canonical_company(org["name"]))
        aff["papers"][pid] = {"companies": sorted(companies), "universities": sorted(universities), "candidates": cands}
        if n % 25 == 0 or n == len(todo):  # save as it goes, so a stop loses little
            for name, d in [("first_page.json", fp), ("robots.json", rb), ("backbones.json", bb), ("github.json", gh), ("affiliations.json", aff)]:
                store(name, d)
            print(f"{n}/{len(todo)}", flush=True)


def paper_info(pid):
    """(title, authors), for the Find link and WhatsApp buttons."""
    p = load("papers.json", {}).get(pid)
    return (p["title"], p["authors"]) if p else None


def build_page():
    papers = load("papers.json", {})
    rows = [[f"https://openreview.net/forum?id={pid}", p["title"], p["authors"], p["abstract"], "; ".join(p["workshops"]),
             "; ".join(k.strip().lower() for k in p["keywords"]), f"https://openreview.net/pdf?id={pid}"]
            for pid, p in papers.items()]
    build.build(HERE, TITLE, list(COLUMNS), rows, store="workshops")


if __name__ == "__main__":
    {"fetch": fetch, "pdfs": pdfs, "extract": extract}.get((sys.argv[1:] or [""])[0], build_page)()
