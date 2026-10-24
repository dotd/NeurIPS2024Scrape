"""Extract title, abstract, first figure and all figures of each CoRL 2026 PDF.

Only looks above the first section heading ("1 Introduction"). Papers whose
Figure 1 isn't before that heading get no figure.

Writes htmls/corl2026/figs/<id>.png, htmls/corl2026/figs/<id>/fig<N>.png and
htmls/corl2026/first_page.json,
which htmls/corl2026/build.py picks up.

    uv run python specific_scripts/extract_first_page.py --limit 3
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "htmls", "corl2026", "pdfs")
CSV = os.path.join(ROOT, "ConferenceTables", "robot-learning_org_CoRL_2026_Conference.csv")
OUT_DIR = os.path.join(ROOT, "htmls", "corl2026")
FIG_DIR = os.path.join(OUT_DIR, "figs")
OUT_JSON = os.path.join(OUT_DIR, "first_page.json")

SECTION_RE = re.compile(r"^1\s+[A-Z]")  # not "1Carnegie Mellon" affiliations
# "Figure 1: ...", "Fig. 1. ...", "Figure 1 Overview ..." -- not prose like "Figure 1 shows ..."
CAPTION_RE = re.compile(r"^(?:Figure|Fig\.?)\s*1(?:\s*[:.|]|\s+(?=[A-Z(]))")
HEADING_RE = re.compile(r"^[A-Z0-9](\.\d+)*\s+[A-Z]")  # "4 Methodology", "A.1 Setup"
ANY_CAPTION_RE = re.compile(r"^(?:Figure|Fig\.?)\s*(\d+)(?:\s*[:.|]|\s+(?=[A-Z(]))")
# ponytail: figure-internal labels are small text; body/abstract/caption text is >= this size
ANCHOR_SIZE = 8.5
CAPTION_SIZE = 7.5  # IEEE-style templates use 8pt captions
# ponytail: vertical whitespace (pt) that ends a figure; raise if figures with sparse panels get cut
FIG_GAP = 20


def blocks(page):
    """Text blocks as (rect, text, max font size), top to bottom."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        spans = [s for line in b["lines"] for s in line["spans"]]
        text = "\n".join("".join(s["text"] for s in line["spans"]) for line in b["lines"]).strip()
        if text:
            out.append((pymupdf.Rect(b["bbox"]), text, max(s["size"] for s in spans)))
    return sorted(out, key=lambda b: b[0].y0)


def extract(pdf_path, fig_path):
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    bl = blocks(page)

    # stop at the first section heading
    end = next((i for i, b in enumerate(bl) if SECTION_RE.match(b[1]) and b[2] >= ANCHOR_SIZE), len(bl))
    bl = bl[:end]

    biggest = max(b[2] for b in bl)
    title = " ".join(b[1].replace("\n", " ") for b in bl if b[2] >= biggest - 0.5)

    abstract = ""
    for i, b in enumerate(bl):
        if b[1].startswith("Abstract"):
            parts = [b[1]]
            for x in bl[i + 1:]:
                if x[1].startswith("Keywords") or CAPTION_RE.match(x[1]) or x[2] < ANCHOR_SIZE:
                    break
                parts.append(x[1])
            abstract = re.sub(r"^Abstract[:.]?\s*", "", " ".join(parts).replace("-\n", "").replace("\n", " "))
            break

    # first-page figure (above section 1), else Figure 1 wherever it is
    figure_page = 1 if crop_figure(page, bl, first_caption(bl), fig_path) else None
    if figure_page is None:
        for pn, pg in enumerate(doc):
            pbl = blocks(pg)
            if crop_figure(pg, pbl, first_caption(pbl), fig_path):
                figure_page = pn + 1
                break
    figure = os.path.relpath(fig_path, OUT_DIR) if figure_page else None

    # every captioned figure in the paper, first occurrence of each number
    fig_dir = os.path.splitext(fig_path)[0]
    os.makedirs(fig_dir, exist_ok=True)
    figures = {}
    for pn, pg in enumerate(doc):
        pbl = blocks(pg)
        for b in pbl:
            m = ANY_CAPTION_RE.match(b[1])
            n = m and int(m.group(1))
            if not m or b[2] < CAPTION_SIZE or n in figures:
                continue
            out = os.path.join(fig_dir, f"fig{n}.png")
            size = crop_figure(pg, pbl, b, out)
            if size:
                figures[n] = {"n": n, "page": pn + 1, "src": os.path.relpath(out, OUT_DIR), "w": size[0], "h": size[1]}

    return {"title": title, "abstract": abstract, "figure": figure, "figure_page": figure_page,
            "figures": [figures[n] for n in sorted(figures)]}


def first_caption(bl):
    return next((b for b in bl if CAPTION_RE.match(b[1]) and b[2] >= CAPTION_SIZE), None)


def crop_figure(page, bl, cap, fig_path):
    """Save the region from the text above the caption down to the caption's end; return (w, h) px."""
    if not cap:
        return None
    c = pymupdf.Rect(cap[0])
    for b in bl[bl.index(cap) + 1:]:  # caption continued in the next block(s)
        if b[2] >= CAPTION_SIZE and b[0].y0 <= c.y1 + 3 and abs(b[0].x0 - c.x0) < 5:  # same column
            c |= b[0]
    # narrow caption with body text beside it = wrapfigure; only text in the caption's column bounds the top
    # (a short centered caption under a full-width figure has nothing beside it)
    # (words, not blocks: PyMuPDF sometimes merges the side column with full-width text into one block)
    # text margins of this page (templates differ: CoRL, IEEE two-column, narrow-margin preprints)
    body = [b[0] for b in bl if b[2] >= ANCHOR_SIZE and b[0].width > 100] or [page.rect]
    left, right = min(r.x0 for r in body) - 6, max(r.x1 for r in body) + 6
    narrow = c.width < 0.6 * (right - left) and any(
        w[3] > c.y0 and w[1] < c.y1 and (w[2] < c.x0 - 2 or w[0] > c.x1 + 2) for w in page.get_text("words"))
    x0, x1 = (c.x0 - 4, c.x1 + 4) if narrow else (left, right)
    # grow upward from the caption over graphics and labels; stop at a wide body-text block or a gap
    page_area = page.rect.get_area()
    # (rect, is_body_text, is_graphic)
    stuff = [(b[0], b[2] >= ANCHOR_SIZE and (b[0].width >= 0.6 * c.width or HEADING_RE.match(b[1])), False)
             for b in bl if b is not cap]
    stuff += [(pymupdf.Rect(d["rect"]), False, True) for d in page.get_drawings()
              if pymupdf.Rect(d["rect"]).get_area() < 0.8 * page_area]  # skip page frames
    stuff += [(pymupdf.Rect(r), False, True) for img in page.get_images() for r in page.get_image_rects(img[0])]
    stuff = sorted((s for s in stuff if s[0].y1 <= c.y0 + 1 and s[0].x1 > x0 and s[0].x0 < x1),
                   key=lambda s: -s[0].y1)
    top = c.y0
    for r, is_body, is_graphic in stuff:
        if r.y1 < top - FIG_GAP or is_body:
            break
        top = min(top, r.y0)
        if narrow and is_graphic:  # a wrapfigure's graphic can be wider than its caption
            x0, x1 = max(min(x0, r.x0 - 2), left), min(max(x1, r.x1 + 2), right)
    if top >= c.y0 - 10:  # nothing above the caption: not a figure we can crop
        return None
    pix = page.get_pixmap(clip=pymupdf.Rect(x0, top - 2, x1, c.y1 + 2), dpi=200)
    pix.save(fig_path)
    return pix.width, pix.height


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N papers of the CSV")
    args = ap.parse_args()

    csv.field_size_limit(sys.maxsize)
    with open(CSV, newline="") as f:
        ids = [r["id"].split("id=")[-1] for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE) if r["id"]]
    ids = ids[: args.limit]

    os.makedirs(FIG_DIR, exist_ok=True)
    result = json.load(open(OUT_JSON)) if os.path.exists(OUT_JSON) else {}
    for pid in ids:
        pdfs = glob.glob(os.path.join(PDF_DIR, f"{pid}_*.pdf"))
        if not pdfs:
            print(f"{pid}: no pdf")
            continue
        try:
            result[pid] = extract(pdfs[0], os.path.join(FIG_DIR, f"{pid}.png"))
        except Exception as e:  # one broken pdf shouldn't stop the batch
            print(f"{pid}: {e}")
            continue
        r = result[pid]
        print(f"{pid}: figure={r['figure']} all={len(r['figures'])} | {r['title'][:60]}")

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"wrote {OUT_JSON} ({len(result)} papers)")


if __name__ == "__main__":
    main()
