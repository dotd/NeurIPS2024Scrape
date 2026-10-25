"""Build one HTML summary per topic from the downloaded PDFs.

For each topic (robotics, rl, ...) lists its downloaded papers (top-5 most
influential per conference) with: title/authors/venue/citations, a summary
(the paper's TLDR as a lead + its abstract), and one representative figure
extracted from the PDF. Writes htmls/<topic>_summary.html.

    uv run python specific_scripts/build_topic_summaries.py [topic ...]

Figure = largest raster image on the first pages (pdfimages), downscaled to
jpeg with sips (macOS-native, no deps). Papers whose figure can't be found
just show text.
"""

import base64
import glob
import os
import re
import struct
import subprocess
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_all_conferences_filter import ROOT, TOPICS, load_papers

sys.path.insert(0, os.path.join(ROOT, "OpenreviewScrape"))
import openreview_utils

PDFS = os.path.join(ROOT, "pdfs")
TOP_N = 5


def safe(s, n=90):
    return re.sub(r'[\\/:*?"<>|]+', " ", s).strip()[:n]


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def extract_figure(pdf_path):
    """Largest raster image on the first pages, as a compressed jpeg data URI."""
    with tempfile.TemporaryDirectory() as tmp:
        pref = os.path.join(tmp, "img")
        subprocess.run(["pdfimages", "-png", "-f", "1", "-l", "5", pdf_path, pref],
                       capture_output=True)
        best, best_area = None, 0
        for p in glob.glob(pref + "-*.png"):
            wh = png_size(p)
            if not wh:
                continue
            w, h = wh
            if w < 250 or h < 150 or not (0.2 <= w / h <= 6):
                continue
            if w * h > best_area:
                best, best_area = p, w * h
        if not best:
            return None
        out = os.path.join(tmp, "fig.jpg")
        r = subprocess.run(["sips", "-Z", "1000", "-s", "format", "jpeg",
                            "-s", "formatOptions", "75", best, "--out", out],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            return None
        with open(out, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def paras(text):
    """Split abstract into paragraphs on blank lines / hard breaks."""
    parts = [p.strip() for p in re.split(r"\n\s*\n|\r", text or "") if p.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{topic} — Paper Summaries</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 0; background: #f6f7f9; color: #1a1a1a; }}
  header {{ background: #fff; border-bottom: 1px solid #ddd; padding: 16px 24px; }}
  h1 {{ margin: 0; font-size: 22px; }}
  header p {{ margin: 4px 0 0; color: #666; font-size: 14px; }}
  main {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
  .paper {{ background: #fff; border: 1px solid #e3e5e8; border-radius: 8px; padding: 18px 20px; margin-bottom: 18px; }}
  .paper h2 {{ font-size: 17px; margin: 0 0 4px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 4px; }}
  .cites {{ color: #b45309; font-weight: 600; }}
  .tldr {{ background: #eff6ff; border-left: 3px solid #2563eb; padding: 6px 12px; margin: 10px 0; font-size: 14px; }}
  .paper p {{ font-size: 14px; line-height: 1.55; color: #333; }}
  .paper img {{ max-width: 100%; border: 1px solid #eee; border-radius: 4px; margin: 10px 0; }}
  .paper a {{ color: #2563eb; font-size: 13px; margin-right: 12px; }}
</style></head><body>
<header><h1>{topic} — Paper Summaries</h1>
<p>{count} papers (top {top_n} most-influential per conference), sorted by influential citations.</p></header>
<main>{body}</main></body></html>
"""


def build_topic(key, label, papers):
    confs = sorted({p[0] for p in papers})
    entries = []
    for conf in confs:
        group = [p for p in papers if key in p[9] and p[0] == conf]
        group.sort(key=lambda p: p[11] if p[11] is not None else -1, reverse=True)
        for rank, p in enumerate(group[:TOP_N], 1):
            folder = os.path.join(PDFS, f"{key}_{openreview_utils.normalize_venue_id(conf)}")
            path = os.path.join(folder, f"{rank:02d}_{p[11] or 0}infl_{safe(p[1])}.pdf")
            if os.path.exists(path):
                entries.append((p, path))
    entries.sort(key=lambda e: e[0][11] if e[0][11] is not None else -1, reverse=True)

    htmldir = os.path.join(ROOT, "htmls")
    blocks_v1, blocks_v2 = [], []
    for p, path in entries:
        fig = extract_figure(path)
        cite = ""
        if p[10] is not None:
            cite = f'<span class="cites">{p[10]} citations ({p[11] or 0} influential)</span> · '
        tldr = f'<div class="tldr"><b>TL;DR:</b> {esc(p[7])}</div>' if p[7] else ""
        abstract = "".join(f"<p>{esc(par)}</p>" for par in paras(p[8]))
        img = f'<img src="{fig}" alt="figure">' if fig else ""
        or_link = f'<a href="{p[6] or p[5]}" target="_blank">OpenReview</a>' if (p[6] or p[5]) else ""
        local_href = urllib.parse.quote(os.path.relpath(path, htmldir))  # ../pdfs/<folder>/<file>.pdf
        local_link = f'<a href="{local_href}" target="_blank">Local PDF</a>'
        head = (f'<div class="paper"><h2>{esc(p[1])}</h2>'
                f'<div class="meta">{esc(p[2])}</div>'
                f'<div class="meta">{cite}{esc(p[0])} — {esc(p[4])}</div>'
                f"{tldr}{img}{abstract}")
        blocks_v1.append(f"{head}{or_link}</div>")
        blocks_v2.append(f'{head}<div class="links">{or_link} {local_link}</div></div>')
        print(f"  {p[0]:<13} {'[fig]' if fig else '[   ]'} {p[1][:55]}")

    for suffix, blocks in [("", blocks_v1), ("_v2", blocks_v2)]:
        html = PAGE.format(topic=esc(label), count=len(entries), top_n=TOP_N, body="".join(blocks))
        out = os.path.join(htmldir, f"{key}_summary{suffix}.html")
        with open(out, "w") as f:
            f.write(html)
        print(f"Wrote {out}: {len(entries)} papers, {os.path.getsize(out) / 1e6:.1f} MB")


def main():
    _, papers = load_papers()
    want = sys.argv[1:]
    for key, label, _, _ in TOPICS:
        if want and key not in want:
            continue
        print(f"=== {label} ({key}) ===")
        build_topic(key, label, papers)


if __name__ == "__main__":
    main()
