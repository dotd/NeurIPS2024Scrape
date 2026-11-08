"""When each CoRL 2026 paper is presented: its oral / spotlight talk and its poster session + board number.

Scraped from https://www.corl.org/program/accepted-papers (a Google Sites page; the list is an HTML embed stored
escaped inside it) into website/corl2026/schedule.json:
    {"papers": {pid: {"talk": "...", "poster": "...", "sessions": [...]}}, "sessions": [session names in page (= time) order],
     "order": {session: [pid, ...] in talk order / poster-number order}}

    uv run python specific_scripts/corl2026_schedule.py && uv run python website/corl2026/build.py
"""

import html
import json
import os
import re

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "website", "corl2026", "schedule.json")
URL = "https://www.corl.org/program/accepted-papers"
SECTION_RE = re.compile(r'<section class="session[^"]*"[^>]*>(.*?)</section>', re.S)
TAG_RE = re.compile(r'<span class="tag">([^<]*)</span>\s*([^<]*)</h3>\s*<p class="meta">(.*?)</p>', re.S)
ID_RE = re.compile(r"openreview\.net/forum\?id=([\w-]+)")
ROOM_RE = re.compile(r"([^·<>]+?):\s*posters\s*(\d+)\s*[–-]\s*(\d+)")


def text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def parse(page):
    page = html.unescape(html.unescape(page))  # the embed is escaped once inside the Sites page JSON, once more as HTML
    papers, sessions, order = {}, [], {}
    for sec in SECTION_RE.findall(page):
        m = TAG_RE.search(sec)
        if not m:
            continue
        tag, topic, meta = m.group(1).strip(), m.group(2).strip(), m.group(3)
        when, *where = [p.strip() for p in text(meta.split("<br")[0]).split("·")]
        if tag == "Poster":  # "Poster Session 1", "Mon 11/9, 5:00–6:30 PM", rows of "<td class=num>N</td> … id"
            name = f"{topic} · {when}"
            rooms = [(r.strip(), int(a), int(b)) for r, a, b in ROOM_RE.findall(text(meta.split("<br", 1)[-1]))]
            for num, pid in re.findall(r'<td class="num">(\d+)</td>\s*<td><a href="[^"]*id=([\w-]+)"', sec):
                room = next((r for r, a, b in rooms if a <= int(num) <= b), "")
                e = papers.setdefault(pid, {"sessions": []})
                e["poster"] = f"{name} · {where[0] if where else ''}{', ' + room if room else ''} · #{num}"
                e["sessions"].append(name)
                order.setdefault(name, []).append(pid)
        else:  # "Oral O1" / "Spotlight S2" with its topic, time and place
            name = f"{tag} · {when}"
            for pid in ID_RE.findall(sec):
                e = papers.setdefault(pid, {"sessions": []})
                e["talk"] = f"{tag}: {topic} · {when}{' · ' + where[0] if where else ''}"
                e["sessions"].append(name)
                order.setdefault(name, []).append(pid)
        sessions.append(name)
    return papers, sessions, order


def main():
    papers, sessions, order = parse(requests.get(URL, timeout=30).text)
    assert papers, "no sessions found: the page layout changed"
    json.dump({"papers": papers, "sessions": sessions, "order": order}, open(OUT, "w"), indent=1, ensure_ascii=False)
    talks = sum("talk" in p for p in papers.values())
    print(f"{len(papers)} papers ({talks} with a talk) in {len(sessions)} sessions -> {OUT}")


if __name__ == "__main__":
    main()
