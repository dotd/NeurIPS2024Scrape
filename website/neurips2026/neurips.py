"""NeurIPS 2026 papers, browsed with the same page and buttons as CoRL 2026.

website/serve.py serves this folder at http://127.0.0.1:8026/Neurips2026/. Steps (each skips what's done, so rerun freely):

    uv run python website/neurips2026/neurips.py fetch    # neurips.cc paper list: sessions, rooms, oral / spotlight / poster
    uv run python website/neurips2026/neurips.py pdfs     # orals + spotlights: arXiv abstract + PDF (~3 s a paper)
    uv run python website/neurips2026/neurips.py extract  # figures, robots, backbones, GitHub, affiliations, movies
    uv run python website/neurips2026/neurips.py          # rebuild index.html

The papers are still private on OpenReview (Nov 2026), so the list comes from neurips.cc's virtual-site JSON and the
abstracts / PDFs from arXiv (title match). Posters get nothing up front; their "Download paper locally" button calls
download() through serve.py.
The Claude HTML and WhatsApp slide are made on demand by the page's buttons (serve.py), as on the other sites. Movies: video files and YouTube links found in the PDF and on the project page.
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TITLE = "NeurIPS 2026"
VIRTUAL = "https://neurips.cc/static/virtual/data/neurips-2026-orals-posters.json"
COLUMNS = ["id", "title", "authors", "abstract", "venue", "primary_keyword", "🏛️ track", "🎬 youtube", "🌐 url", "pdf"]
UA = {"User-Agent": "Mozilla/5.0 (paper browser)"}
ATOM = "{http://www.w3.org/2005/Atom}"
TOP = ("Oral", "Spotlight")
LOCK = threading.Lock()
VIDEO_RE = re.compile(r"https?://[^\s\"'<>]+?\.(?:mp4|webm|mov)\b", re.I)

sys.path[:0] = [os.path.join(ROOT, "website", "corl2026"), os.path.join(ROOT, "website", "corl2026_workshops"),
                os.path.join(ROOT, "specific_scripts"), os.path.join(ROOT, "website")]
import build  # noqa: E402
import workshops  # noqa: E402  its pdf_path() / extract() take the site folder


def pdf_path(pid):
    return workshops.pdf_path(pid, HERE)


def load(name, default):
    return build.load(HERE, name, default)


def store(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w"), ensure_ascii=False, indent=1)


def when(iso):
    """"2026-12-09T15:00:00-08:00" -> "Wed 12/9 15:00" (the time as neurips.cc gives it)."""
    t = time.strptime(iso[:16], "%Y-%m-%dT%H:%M")
    return time.strftime("%a ", t) + f"{t.tm_mon}/{t.tm_mday} " + time.strftime("%H:%M", t)


def fetch():
    events = requests.get(VIRTUAL, headers=UA, timeout=120).json()["results"]
    papers, sched = {}, {"papers": {}, "sessions": [], "order": {}}
    starts = {}
    for e in events:
        pid = (e.get("paper_url") or "").split("id=")[-1] or f"nips-{e['id']}"  # journal-track posters: no OpenReview
        dec = (e.get("decision") or "").lower()
        kind = "Oral" if "oral" in dec else "Spotlight" if "spotlight" in dec else "Poster"
        p = papers.setdefault(pid, {"title": e["name"].strip(), "authors": ", ".join(a["fullname"] for a in e["authors"]),
                                    "kind": kind, "topic": e.get("topic") or "", "abstract": "",
                                    "track": (e.get("sourceurl") or "").split("NeurIPS.cc/2026/")[-1].replace("_", " "),
                                    "url": e.get("url") or "", "virtual": "https://neurips.cc" + e["virtualsite_url"]})
        if e["eventtype"] == "Oral":
            p["kind"] = "Oral"
        if not e.get("session") or not e.get("starttime"):
            continue
        label = f"{when(e['starttime'])} · {e['session']}"
        starts[label] = e["starttime"]
        where = " · ".join(x for x in [e.get("room_name"), e.get("poster_position")] if x)
        s = sched["papers"].setdefault(pid, {"sessions": []})
        s["talk" if e["eventtype"] == "Oral" else "poster"] = f"{label} · {where}"
        s["sessions"].append(label)
        sched["order"].setdefault(label, []).append(pid)
    sched["sessions"] = sorted(starts, key=lambda s: (starts[s], s))
    store("papers.json", papers)
    store("schedule.json", sched)
    print(f"{len(papers)} papers: " + ", ".join(f"{k} {sum(p['kind'] == k for p in papers.values())}" for k in TOP + ("Poster",)))


def norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def arxiv_find(title):
    """{url, abstract, authors} of the arXiv paper with this exact title, {} if none, None if arXiv failed."""
    q = re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", title)).strip()
    for attempt in range(3):
        try:
            r = requests.get("https://export.arxiv.org/api/query", timeout=30, params={"search_query": f'ti:"{q}"', "max_results": 5})
            r.raise_for_status()
            break
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
    else:
        return None
    for e in ET.fromstring(r.content).iter(ATOM + "entry"):
        if norm(e.findtext(ATOM + "title", "")) == norm(title):
            return {"url": re.sub(r"v\d+$", "", e.findtext(ATOM + "id", "")).replace("http://", "https://"),
                    "abstract": " ".join(e.findtext(ATOM + "summary", "").split())}
    return {}


def get_pdf(pid, p, abs_url):
    try:
        r = requests.get(abs_url.replace("arxiv.org/abs/", "arxiv.org/pdf/"), headers=UA, timeout=120)
    except requests.RequestException:
        return False
    if not (r.ok and r.content.startswith(b"%PDF-")):
        return False
    os.makedirs(os.path.join(HERE, "pdfs"), exist_ok=True)
    name = re.sub(r"[^\w\- .,()]", " ", p["title"])[:100].strip()
    open(os.path.join(HERE, "pdfs", f"{pid}_{name}.pdf"), "wb").write(r.content)
    return True


def lookup(pid, papers, arx):
    """arXiv search + PDF for one paper; saves arxiv.json and the abstract. False if not on arXiv."""
    p = papers[pid]
    if pid not in arx:
        found = arxiv_find(p["title"])
        if found is None:
            return False  # arXiv down: a rerun retries
        arx[pid] = found.get("url", "")
        if found.get("abstract"):
            p["abstract"] = found["abstract"]
        time.sleep(3)  # arXiv API terms: one request every 3 seconds
    return bool(arx[pid]) and (bool(pdf_path(pid)) or get_pdf(pid, p, arx[pid]))


def site():
    import serve  # lazy: serve.py imports this module
    return serve, serve.Site("/Neurips2026", TITLE, HERE, lambda: None, paper_info)


def web_copy(pid, papers, arx):
    """Not on arXiv by title: Claude + web search (~$0.10) for another copy; its PDF if it's arXiv or a PDF link."""
    serve, s = site()
    link = load("links.json", {}).get(pid) or serve.find_link(s, pid)
    with LOCK:  # the batch runs 4 at a time: re-read, so no one's result is lost
        links = load("links.json", {})
        links[pid] = link
        store("links.json", links)
    url = (link or {}).get("url") or ""
    if url and get_pdf(pid, papers[pid], url):
        if "arxiv.org/abs/" in url:
            arx[pid] = re.sub(r"v\d+$", "", url)
        return True
    return False


def pdfs():
    papers, arx = load("papers.json", {}), load("arxiv.json", {})
    os.makedirs(os.path.join(HERE, "pdfs"), exist_ok=True)
    todo = [pid for pid, p in papers.items() if p["kind"] in TOP and not pdf_path(pid) and pid not in arx]
    for n, pid in enumerate(todo, 1):
        lookup(pid, papers, arx)
        if n % 20 == 0 or n == len(todo):
            store("papers.json", papers)
            store("arxiv.json", arx)
            print(f"{n}/{len(todo)}  {len(os.listdir(os.path.join(HERE, 'pdfs')))} PDFs", flush=True)
    links = load("links.json", {})
    rest = [pid for pid, p in papers.items() if p["kind"] in TOP and not pdf_path(pid) and pid not in links]
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        found = sum(ex.map(lambda pid: web_copy(pid, papers, arx), rest))
    store("arxiv.json", arx)
    print(f"web search: {found} of {len(rest)} more PDFs; {len(os.listdir(os.path.join(HERE, 'pdfs')))} PDFs")


def movies(pid):
    """Video files (downloaded to movies/paper_movies/) and YouTube links from the PDF and its project pages."""
    import corl2026_youtube as yt
    pdf = pdf_path(pid)
    import pymupdf
    with pymupdf.open(pdf) as doc:
        text, links = "".join(p.get_text() for p in doc), [l.get("uri") or "" for p in doc for l in p.get_links()]
    found = text + "\n" + "\n".join(links)
    for u in yt.project_pages(text, links):
        try:
            found += requests.get(u, timeout=15, headers=UA).text.replace('src="', f'src="{u.rstrip("/")}/')
        except requests.RequestException:
            continue
    ytid = list(dict.fromkeys(yt.YT_RE.findall(found)))
    out = os.path.join(HERE, "movies", "paper_movies")
    os.makedirs(out, exist_ok=True)
    name = os.path.basename(pdf)[:-4]
    for i, u in enumerate(list(dict.fromkeys(VIDEO_RE.findall(found)))[:3], 1):  # ponytail: first 3 videos only
        u = re.sub(r"(?<!:)//+", "/", u)
        try:
            r = requests.get(u, headers=UA, timeout=120)
        except requests.RequestException:
            continue
        if r.ok and "video" in r.headers.get("Content-Type", "") and len(r.content) < 300e6:
            open(os.path.join(out, f"{name}{'' if i == 1 else f'_{i}'}{os.path.splitext(u)[1].lower()}"), "wb").write(r.content)
    return ["https://www.youtube.com/watch?v=" + v for v in ytid[:1]]


def extract():
    workshops.extract(HERE)
    yt = load("youtube.json", {})
    todo = [pid for pid in load("papers.json", {}) if pid not in yt and pdf_path(pid)]
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for pid, v in zip(todo, ex.map(movies, todo)):
            yt[pid] = v
    store("youtube.json", yt)
    print(f"{sum(bool(v) for v in yt.values())} YouTube links, {len(os.listdir(os.path.join(HERE, 'movies', 'paper_movies')))} movie files")


def download(pid, lock):
    """The "Download paper locally" button (serve.py): arXiv PDF (else a web search) + figures/filters. Raises if not found."""
    papers, arx = load("papers.json", {}), load("arxiv.json", {})
    if pid not in papers:
        raise ValueError("unknown paper")
    arx.pop(pid, None) if arx.get(pid) == "" else None  # search again: it may be on arXiv by now
    ok = lookup(pid, papers, arx) or web_copy(pid, papers, arx)
    with lock:  # MuPDF isn't thread-safe; the files and the rebuild are shared with serve.py's other buttons
        fresh = load("papers.json", {})
        fresh[pid]["abstract"] = papers[pid]["abstract"]
        store("papers.json", fresh)
        store("arxiv.json", {**load("arxiv.json", {}), **({pid: arx[pid]} if pid in arx else {})})
        if not ok:
            raise ValueError("no public copy found (arXiv, web search); the OpenReview PDF is not public yet")
        workshops.extract(HERE, [pid])
        build_page()
    return os.path.relpath(pdf_path(pid), HERE)


def paper_info(pid):
    """(title, authors), for the Find link and WhatsApp buttons."""
    p = load("papers.json", {}).get(pid)
    return (p["title"], p["authors"]) if p else None


def build_page():
    papers, arx, yt = load("papers.json", {}), load("arxiv.json", {}), load("youtube.json", {})
    rows = [[f"https://openreview.net/forum?id={pid}" if not pid.startswith("nips-") else p["virtual"] + "?id=" + pid,
             p["title"], p["authors"], p["abstract"], f"NeurIPS 2026 {p['kind']}", p["topic"], p["track"],
             " ".join(yt.get(pid, [])), p["url"],
             arx[pid].replace("/abs/", "/pdf/") if arx.get(pid) else f"https://openreview.net/pdf?id={pid}"]
            for pid, p in papers.items()]
    build.build(HERE, TITLE, list(COLUMNS), rows, store="neurips")


if __name__ == "__main__":
    {"fetch": fetch, "pdfs": pdfs, "extract": extract}.get((sys.argv[1:] or [""])[0], build_page)()
