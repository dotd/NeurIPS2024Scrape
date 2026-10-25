"""Download CoRL 2026 workshop sites and build corl/2026/workshops/summary.html.

Usage: uv run python specific_scripts/scrape_corl_workshops.py
"""
import datetime
import html
import json
import re
import urllib.request

GROUP = "robot-learning.org/CoRL/2026/Workshop"
OUT_DIR = "corl/2026/workshops"
UA = {"User-Agent": "Mozilla/5.0 (workshop-summary-scraper)"}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode(r.headers.get_content_charset() or "utf-8", "replace")


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style|nav|footer|head)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def localize(page, site):
    """Point relative css/img/font URLs back at the origin so the saved copy keeps its design."""
    if re.search(r"(?i)<base\s", page):
        return page
    tag = f'<base href="{html.escape(site, quote=True)}">'
    m = re.search(r"(?i)<head[^>]*>", page)
    return page[:m.end()] + tag + page[m.end():] if m else tag + page


def blurb(page, limit=900):
    """First paragraphs of visible text; falls back to whole-page text."""
    paras = [strip_tags(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", page)]
    paras = [p for p in paras if len(p) > 80]
    if not paras:
        paras = [strip_tags(page)]
    out = ""
    for p in paras:
        if len(out) > limit:
            break
        out += p + "\n\n"
    out = out.strip()
    return out[:2000] + ("..." if len(out) > 2000 else "")


def when(c):
    d = c.get("start_date") or c.get("date")
    if isinstance(d, int):  # epoch ms, UTC (OpenReview stores it that way)
        return datetime.datetime.fromtimestamp(d / 1000, datetime.UTC).strftime("%b %d %Y")
    return d or ""


def main():
    groups = json.loads(get(f"https://api2.openreview.net/groups?parent={GROUP}&limit=500"))["groups"]
    workshops = []
    for g in groups:
        c = {k: v.get("value") for k, v in g.get("content", {}).items() if isinstance(v, dict)}
        if not c.get("title"):
            print(f"skip (no metadata): {g['id']}")
            continue
        key = g["id"].rsplit("/", 1)[-1].replace("@", "_at_")
        text, page = "", None
        site = c.get("website")
        if site:
            try:
                page = get(site)
            except Exception as e:  # site down / TLS / 404 -- keep the row, skip the blurb
                print(f"fetch failed {site}: {e}")
        if page:
            path = f"{OUT_DIR}/{key}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(localize(page, site))
            text = blurb(page)
            print(f"saved {path} ({len(page)} bytes)")
        workshops.append({
            "key": key, "id": g["id"], "title": c["title"], "subtitle": c.get("subtitle") or "",
            "website": site or "", "location": c.get("location") or "", "date": when(c),
            "contact": c.get("contact") or "", "blurb": text,
        })

    workshops.sort(key=lambda w: w["title"].lower())
    e = html.escape
    cards = []
    for w in workshops:
        links = [f'<a href="https://openreview.net/group?id={e(w["id"])}">OpenReview</a>']
        if w["website"]:
            links.insert(0, f'<a href="{e(w["website"])}">Website</a>')
        if w["blurb"]:
            links.append(f'<a href="{e(w["key"])}.html">saved HTML</a>')
        cards.append(f"""<section class="ws">
<h2>{e(w["title"])}</h2>
<p class="meta">{e(" · ".join(x for x in [w["date"], w["location"], w["subtitle"]] if x))}</p>
<p class="links">{" | ".join(links)}</p>
<div class="blurb">{"".join(f"<p>{e(p)}</p>" for p in w["blurb"].split(chr(10) * 2)) or "<p><em>No description retrieved.</em></p>"}</div>
</section>""")

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>CoRL 2026 Workshops</title>
<style>
body{{font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}}
h1{{margin-bottom:.2rem}} .ws{{border-top:1px solid #ddd;padding-top:1rem;margin-top:1.5rem}}
h2{{font-size:1.15rem;margin:0 0 .3rem}} .meta{{color:#666;font-size:.9rem;margin:.2rem 0}}
.links{{font-size:.9rem;margin:.3rem 0}} .blurb p{{margin:.5rem 0}} a{{color:#06c}}
ol{{columns:2;font-size:.95rem}}
</style></head><body>
<h1>CoRL 2026 Workshops</h1>
<p class="meta">{len(workshops)} workshops · Austin, Texas · generated {datetime.date.today()} from
<a href="https://openreview.net/group?id={GROUP}">OpenReview</a> + workshop websites</p>
<ol>{"".join(f'<li><a href="#{e(w["key"])}">{e(w["title"])}</a></li>' for w in workshops)}</ol>
{"".join(c.replace('<section class="ws">', f'<section class="ws" id="{e(w["key"])}">', 1) for c, w in zip(cards, workshops))}
</body></html>"""
    with open(f"{OUT_DIR}/summary.html", "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {OUT_DIR}/summary.html ({len(workshops)} workshops)")


if __name__ == "__main__":
    main()


def _selfcheck():
    assert localize("<html><head><meta></head>", "https://x.io/") == \
        '<html><head><base href="https://x.io/"><meta></head>'
    assert localize('<head><base href="y">', "https://x.io/").count("<base") == 1
    assert blurb("<p>%s</p><p>short</p>" % ("a" * 200)) == "a" * 200
    print("selfcheck ok")
