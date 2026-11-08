"""One page of every robot the CoRL 2026 papers use: a photo cropped from a paper figure, specs, website, price.

Claude (web search) fills in maker, specs, website and price; Claude (vision) picks a paper figure that shows the
robot and a box to crop it to. Both are cached in website/corl2026/robot_cards.json (delete an entry to redo it).
Writes website/corl2026/robots.html (served at /Corl2026/robots.html) and robot_photos/.

    uv run python specific_scripts/corl2026_robot_page.py            # all robots (~$5-10 the first time)
    uv run python specific_scripts/corl2026_robot_page.py "Unitree G1" "LEAP Hand"
"""

import base64
import collections
import concurrent.futures
import html
import json
import os
import re
import sys
import threading

import anthropic
import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "website", "corl2026")
CARDS = os.path.join(HERE, "robot_cards.json")
PHOTOS = os.path.join(HERE, "robot_photos")
KEY_FILE = os.path.join(ROOT, "secrets", "claude_api", "claude_api.txt")
MODEL = "claude-opus-5-5"
MAX_FIGS = 8  # figures shown to Claude per robot
sys.path.insert(0, HERE)
import build  # noqa: E402

client = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip())
lock = threading.Lock()

SPEC_PROMPT = """Research this robot, used in robot-learning research papers: {name}
Find its maker, what kind of robot it is, its official product page, its price and its main specifications.
For the price, give the list price in USD (or the local currency) of the configuration researchers usually buy,
with "≈" if approximate and the year; say "on request" if it is not public, or "discontinued" with the last price.
Answer with only one JSON object (no markdown), in this form:
{{"name": "full product name", "maker": "company", "type": "e.g. 7-DoF arm / humanoid / quadruped / dexterous hand",
 "description": "one or two sentences: what it is and why researchers use it",
 "website": "official product page URL", "price": "e.g. ≈ $16,000 (2025)", "price_source": "URL backing the price or empty",
 "specs": {{"DoF": "...", "Payload": "...", "Reach": "...", "Weight": "...", "Height": "...", "Speed": "...", "Battery": "..."}}}}
Put only the specs that apply and that you found (3 to 8), with units. Use "" for anything you could not find."""

PHOTO_PROMPT = """These are figures from robotics papers that use the robot "{name}" ({kind}).
Pick the one figure where this robot is shown most clearly and largest, as a real photo (not a diagram or rendering if
a photo exists), and give a box around the robot. Answer with only JSON (no markdown):
{{"figure": <index of the figure, 0-based, or -1 if none shows this robot>, "box": [x0, y0, x1, y1]}}
where the box is in pixels of that figure (its size is given above it), snug around the robot with a small margin.
Keep captions, labels, arrows and text outside the box as much as possible."""


def call(content, effort="low", search=False):
    """One Claude answer, as the JSON object at its end; continues a paused web search loop."""
    messages = [{"role": "user", "content": content}]
    for _ in range(4):
        with client.beta.messages.stream(
            model=MODEL, max_tokens=16000, output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}] if search else [],
            messages=messages,
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": msg.content})
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"no JSON in Claude's answer: {text[-200:]!r}")
    return json.loads(m.group(0))


def small_jpeg(path, side=1000):
    """The figure as a JPEG pixmap, longest side at most `side` px."""
    with pymupdf.open(path) as d:
        r = d[0].rect
        z = min(1, side / max(r.width, r.height))
        return d[0].get_pixmap(matrix=pymupdf.Matrix(z, z))


def candidate_figures(name, robots, first):
    """Figures from the papers using this robot, papers with fewer robots first (their figures show this one)."""
    pids = sorted((p for p, rs in robots.items() if name in rs), key=lambda p: len(robots[p]))
    out = []
    for p in pids:
        for f in first.get(p, {}).get("figures", [])[:3]:  # ponytail: setup figures are usually among the first few
            if os.path.exists(os.path.join(HERE, f["src"])):
                out.append(f["src"])
    return out[:MAX_FIGS]


def photo(name, kind, figs, slug):
    """Claude picks a figure and box; the crop is saved to robot_photos/<slug>.jpg. Returns {photo, from} or {}."""
    if not figs:
        return {}
    content, sizes = [], []
    for i, f in enumerate(figs):
        pix = small_jpeg(os.path.join(HERE, f))
        sizes.append((pix.width, pix.height))
        content += [{"type": "text", "text": f"Figure {i} ({pix.width}x{pix.height} px):"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()}}]
    content.append({"type": "text", "text": PHOTO_PROMPT.format(name=name, kind=kind)})
    ans = call(content)
    i = ans.get("figure", -1)
    if not isinstance(i, int) or not 0 <= i < len(figs):
        return {}
    w, h = sizes[i]
    box = ans.get("box") or [0, 0, w, h]
    pad = 0.1  # ponytail: Claude's boxes are often off by ~10% of the figure; a loose crop beats a missed robot
    x0, y0, x1, y1 = [min(1, max(0, float(v) / s + d)) for v, s, d in zip(box, (w, h, w, h), (-pad, -pad, pad, pad))]
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        x0, y0, x1, y1 = 0, 0, 1, 1
    with pymupdf.open(os.path.join(HERE, figs[i])) as d:
        r = d[0].rect
        clip = pymupdf.Rect(r.width * x0, r.height * y0, r.width * x1, r.height * y1)
        native = pymupdf.Pixmap(os.path.join(HERE, figs[i])).width / r.width  # the page is in points, not pixels
        z = min(native, 900 / max(clip.width, clip.height))  # ~900 px on the long side, never upscaled
        os.makedirs(PHOTOS, exist_ok=True)
        out = os.path.join(PHOTOS, slug + ".jpg")
        with open(out, "wb") as f:
            f.write(d[0].get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip).tobytes("jpeg", jpg_quality=85))
    return {"photo": os.path.relpath(out, HERE), "from": figs[i].split("/")[1]}  # figs/<paper id>/figN.png


def card(name, robots, first):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    c = call(SPEC_PROMPT.format(name=name), effort="medium", search=True)
    c.update(photo(name, c.get("type", "robot"), candidate_figures(name, robots, first), slug))
    return c


def page(cards, robots):
    """robots.html: 3 columns of cards (1 on a phone), most-used robot first."""
    used = collections.Counter(r for rs in robots.values() for r in rs)
    titles = {r[0].split("id=")[-1]: r[1] for r in build.csv_rows()[1]}
    out = []
    for name, n in used.most_common():
        c = cards.get(name)
        if not c:
            continue
        e = lambda k: html.escape(str(c.get(k) or ""))  # noqa: E731  the answers come from web pages: escape all
        link = lambda u, t: f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{t}</a>' if re.match(r"https?://", u or "") else t  # noqa: E731
        specs = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
                        for k, v in (c.get("specs") or {}).items() if v)
        price = link(c.get("price_source"), e("price") or "unknown")
        src = c.get("from", "")
        img = (f'<img src="{html.escape(c["photo"])}" alt="{e("name")}" loading="lazy" '
               f'title="Photo from: {html.escape(titles.get(src, src))}">' if c.get("photo")
               else '<div class="nophoto">no photo found in the papers</div>')
        papers = "".join(f'<li><a href="https://openreview.net/forum?id={p}" target="_blank">{html.escape(titles.get(p, p))}</a></li>'
                         for p, rs in robots.items() if name in rs)
        out.append(f"""<article>{img}
<h2>{link(c.get("website"), e("name") or html.escape(name))}</h2>
<p class="maker">{e("maker")} · {e("type")}</p>
<p class="price">💲 {price}</p>
<p>{e("description")}</p>
<table>{specs}</table>
<details><summary>Used in {n} CoRL 2026 paper{"s" * (n > 1)}</summary><ul>{papers}</ul></details>
</article>""")
    with open(os.path.join(HERE, "robots.html"), "w") as f:
        f.write(PAGE.replace("__CARDS__", "\n".join(out)).replace("__N__", str(len(out))))


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CoRL 2026 robots</title>
<style>
  body { margin: 0; font: 14px/1.5 system-ui, sans-serif; color: #222; background: #fff; }
  nav { display: flex; align-items: center; gap: 12px; height: 48px; padding: 0 16px; border-bottom: 1px solid #ddd; }
  nav select { font-weight: bold; padding: 5px 8px; border: 1px solid #bbb; border-radius: 6px; }
  main { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; padding: 16px; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  article { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
  article img, .nophoto { width: 100%; height: 260px; object-fit: contain; background: #f6f6f6; border-radius: 6px; }
  .nophoto { display: flex; align-items: center; justify-content: center; color: #888; }
  h2 { font-size: 17px; margin: 10px 0 2px; } .maker { color: #666; margin: 0; } .price { font-weight: 600; margin: 4px 0; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th { text-align: left; color: #555; font-weight: normal; padding: 2px 8px 2px 0; white-space: nowrap; vertical-align: top; }
  td, th { border-top: 1px solid #eee; } details { margin-top: 8px; color: #2b6cb0; } details ul { color: #222; padding-left: 18px; }
</style></head><body>
<nav>
  <select id="site" title="Go to another page">
    <option data-file="corl2026/index.html" value="/Corl2026/">CoRL 2026</option>
    <option data-file="corl2026/robots.html" value="/Corl2026/robots.html" selected>CoRL 2026 robots</option>
    <option data-file="papers/index.html" value="/Papers/">My papers</option>
  </select>
  <span style="color:#666">__N__ robots · specs, websites and prices found by Claude with web search: check before buying</span>
</nav>
<script>
  { const sel = document.getElementById('site');
    sel.onchange = () => location.href = location.protocol.startsWith('http') ? sel.value : '../' + sel.selectedOptions[0].dataset.file; }
</script>
<main>
__CARDS__
</main>
</body></html>
"""


def main(names):
    robots = json.load(open(os.path.join(HERE, "robots.json")))
    first = json.load(open(os.path.join(HERE, "first_page.json")))
    cards = json.load(open(CARDS)) if os.path.exists(CARDS) else {}
    todo = names or [n for n in collections.Counter(r for rs in robots.values() for r in rs) if n not in cards]

    def one(name):
        try:
            c = card(name, robots, first)
        except (anthropic.APIError, RuntimeError, ValueError) as e:
            return print(f"  {name}: failed ({e})")
        with lock:  # save as we go, so a crash keeps what's done
            cards[name] = c
            json.dump(cards, open(CARDS, "w"), ensure_ascii=False, indent=1)
        print(f"  {name}: {c.get('price')} {'📷' if c.get('photo') else 'no photo'}")

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        list(ex.map(one, todo))
    page(cards, robots)
    print("wrote", os.path.join(HERE, "robots.html"), f"({len(cards)} robots)")


if __name__ == "__main__":
    main(sys.argv[1:])
