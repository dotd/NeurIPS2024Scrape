"""Convert a paper PDF to a standalone HTML page with Python only (no LLM), using the PyMuPDF layout engine.

pymupdf4llm's layout analysis gives reading-ordered boxes classed as title / section-header / text /
list-item / caption / picture / formula / table / footnote / page-header / page-footer. Text keeps bold and
italics; pictures and display formulas are cropped from the page as images (exact rendering); tables are
shown as an image of the original plus their extracted cells.

    uv run python specific_scripts/pdf_to_html.py paper.pdf out_dir     # writes out_dir/index.html + img/
"""

import html
import json
import os
import re
import sys
import time
import urllib.parse

import pymupdf
import pymupdf4llm

DPI = 200
URL_RE = re.compile(r"(https?://[^\s<>\"]+[^\s<>\".,;:)\]])")
TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font: 17px/1.6 Georgia, "Times New Roman", serif; max-width: 860px; margin: 0 auto; padding: 24px 20px 80px; color: #222; }}
  h1 {{ font-size: 1.7em; line-height: 1.25; }} h2 {{ margin-top: 1.8em; }} .src {{ font: 13px system-ui, sans-serif; color: #666; }}
  img {{ max-width: 100%; }} p, li {{ overflow-wrap: anywhere; }} .picture, .formula, .table {{ text-align: center; margin: 1.2em 0; }}
  img {{ height: auto; }} .caption {{ font-size: 0.9em; color: #444; }} .footnote {{ font-size: 0.8em; color: #555; }}
  details {{ font: 13px system-ui, sans-serif; text-align: left; }} table {{ border-collapse: collapse; margin: 6px auto; }}
  td {{ border: 1px solid #ccc; padding: 2px 6px; }} .page {{ font: 11px system-ui, sans-serif; color: #aaa; text-align: right; }}
</style></head><body>
<p class="src">HTML version made with Python (PyMuPDF layout analysis) from <a href="{pdf}">the PDF</a>.
Figures, display equations and tables are images cropped from the PDF; check it for exact wording.</p>
{body}
</body></html>
"""


def span_html(span):
    t = html.escape(span["text"])
    if span["flags"] & 16:  # bold
        t = f"<b>{t}</b>"
    if span["flags"] & 2:  # italic
        t = f"<i>{t}</i>"
    return t


def box_lines(page_lines, box):
    """The box's text lines from MuPDF's own extraction (the layout spans drop spaces in some PDFs)."""
    r = pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"])
    # ponytail: a line belongs to the box holding its center; misses only lines straddling two boxes
    return [ln for ln in page_lines
            if pymupdf.Point((ln["bbox"][0] + ln["bbox"][2]) / 2, (ln["bbox"][1] + ln["bbox"][3]) / 2) in r]


def lines_text(lines, rich=True):
    """Join lines into one string, undoing end-of-line hyphenation."""
    out = ""
    for line in lines:
        s = re.sub(r"\s+", " ", "".join(span_html(sp) if rich else sp["text"] for sp in line["spans"])).strip()
        if not s:
            continue
        if out.endswith("-") and s[:1].islower():
            out = out[:-1] + s
        else:
            out += (" " if out else "") + s
    return out


def crop(page, box, out, name):
    """Render the box at DPI; returns the img attributes, displayed at ~1.4x the PDF size (17px vs ~10pt text)."""
    rect = (pymupdf.Rect(box["x0"], box["y0"], box["x1"], box["y1"]) + (-2, -2, 2, 2)) & page.rect
    page.get_pixmap(clip=rect, dpi=DPI).save(os.path.join(out, "img", name))
    return f'src="img/{name}" width="{round(rect.width * 1.4)}"'



def convert(pdf, out):
    os.makedirs(os.path.join(out, "img"), exist_ok=True)
    t0 = time.time()
    doc = pymupdf.open(pdf)
    layout = json.loads(pymupdf4llm.to_json(doc, use_ocr=False))
    parts, in_list, title = [], False, None
    for p in layout["pages"]:
        page = doc[p["page_number"] - 1]
        page_lines = [ln for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                      if abs(ln["dir"][1]) < 0.1]  # skip rotated text, e.g. the arXiv stamp in the margin
        for k, box in enumerate(p["boxes"]):
            cls = box["boxclass"]
            lines = box_lines(page_lines, box)
            if cls == "page-header" and p["page_number"] == 1 and title is None and \
                    max((sp["size"] for ln in lines for sp in ln["spans"]), default=0) >= 13:
                cls = "title"  # paper titles on page 1 are sometimes classed as page headers
            elif cls in ("page-header", "page-footer"):
                continue
            if cls == "list-item" and not in_list:
                parts.append("<ul>")
            elif cls != "list-item" and in_list:
                parts.append("</ul>")
            in_list = cls == "list-item"
            alt = html.escape(lines_text(lines, rich=False), quote=True)
            img = f"p{p['page_number']}_{k}.png"
            if cls in ("picture", "formula"):
                parts.append(f'<div class="{cls}"><img {crop(page, box, out, img)} alt="{alt}" loading="lazy"></div>')
            elif cls == "table":
                cells = (box["table"] or {}).get("extract") or []
                rows = "".join("<tr>" + "".join(f"<td>{html.escape(c or '')}</td>" for c in r) + "</tr>" for r in cells)
                parts.append(f'<div class="table"><img {crop(page, box, out, img)} alt="table" loading="lazy">'
                             f"<details><summary>table as text</summary><table>{rows}</table></details></div>")
            else:
                text = URL_RE.sub(r'<a href="\1">\1</a>', lines_text(lines))
                if not text:
                    continue
                if cls == "title" and title is None:
                    title = lines_text(lines, rich=False)
                    parts.append(f"<h1>{text}</h1>")
                elif cls in ("title", "section-header"):
                    level = min(max(int(box.get("header_level") or 1), 1) + 1, 4)
                    parts.append(f"<h{level}>{text}</h{level}>")
                elif cls == "list-item":
                    parts.append(f"<li>{re.sub(r'^(?:<[bi]>)?[•▪◦·∙‣–-](?:</[bi]>)?\s*', '', text)}</li>")  # <ul> has its own bullet
                elif cls in ("caption", "footnote"):
                    parts.append(f'<p class="{cls}">{text}</p>')
                else:
                    parts.append(f"<p>{text}</p>")
        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(f'<p class="page">page {p["page_number"]}</p>')
    pdf_href = urllib.parse.quote(os.path.relpath(os.path.abspath(pdf), os.path.abspath(out)))
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(TEMPLATE.format(title=html.escape(title or os.path.basename(pdf)), pdf=pdf_href, body="\n".join(parts)))
    meta = {"method": "python", "seconds": round(time.time() - t0, 1), "pages": len(layout["pages"])}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    return meta


if __name__ == "__main__":
    assert lines_text([{"spans": [{"text": "robot-", "flags": 0}]},
                       {"spans": [{"text": "ics", "flags": 2}]}], rich=False) == "robotics"
    print(convert(sys.argv[1], sys.argv[2]), flush=True)
    os._exit(0)  # pymupdf4llm's layout workers sometimes keep a normal exit hanging forever
