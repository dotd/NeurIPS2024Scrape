"""Serve the paper browsers locally; summarize papers and make HTML versions of them with Claude on demand.

Each site is a folder under website/ served at its own path (SITES below): CoRL 2026 at /Corl2026/, the papers
you add yourself at /Papers/. The API key stays here (secrets/claude_api/claude_api.txt), never in index.html.
Summaries, ratings and links are cached in each site's folder; its builder embeds them so they also show when
index.html is opened as a file.

    uv run python website/serve.py      # then open http://127.0.0.1:8026/
"""

import base64
import glob
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse

import anthropic
import pymupdf

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
KEY_FILE = os.path.join(ROOT, "secrets", "claude_api", "claude_api.txt")
# per-site files: summaries.json, ratings.json (your 1-5 stars), links.json (Find link), htmls_claude/, htmls_python/
PORT = 8026
MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4 / 1e6, 20 / 1e6  # $ per token, Opus 5.5
MAX_PDF_BYTES = 23 * 1024 * 1024  # 32 MB request limit after base64 (+33%); bigger PDFs go as extracted text
PROMPT = """Summarize this robotics paper for a robotics researcher deciding whether to read it.
Write 3 to 10 paragraphs of plain prose (no markdown, no bullet lists), separated by blank lines.
Start each paragraph with a short label and a colon, covering at least:
Gist: what the paper does and why it matters, in two or three sentences.
Question: the research question or gap it addresses.
Method: the key idea and how it works.
Robots and setup: the robots (exact models), sensors, simulators, tasks and datasets used.
Results: the main quantitative findings versus baselines, with numbers.
Add paragraphs (e.g. ablations, limitations, takeaways) when the paper warrants it."""

WEB_SEARCH_PRICE = 10 / 1000  # $ per web search
LINK_PROMPT = """Find a publicly accessible copy of this paper that is not on openreview.net.
Prefer its arXiv abstract page (https://arxiv.org/abs/...); otherwise the project page or another open copy.
Make sure it is this exact paper (same title and authors), not a related one.
Title: {title}
Authors: {authors}
End your answer with one line: "URL: <the url>", or "URL: NONE" if there is no such copy."""

WA_PROMPT = """Summarize this robotics paper as a single slide for a WhatsApp message to robotics researchers:
at most 7 bullets with the paper's main points (problem, key idea, method, setup, main results with numbers, what's new).
Each bullet is one line of at most 20 words and starts with "• ". Output only the bullets: no title, no intro,
no markdown, no emojis, no hashtags."""  # the CoRL 2026 prompt (specific_scripts/corl2026_whatsapp.py), from the PDF
MATERIAL_PROMPT = """Search the web for public material about this paper: its project page, code repository, videos
(YouTube or other), dataset, blog post, slides, recorded talk. Include only material about this exact paper, not
related work, not the paper itself (arXiv / OpenReview / PDF) and not the authors' homepages.
Title: {title}
Authors: {authors}
End your answer with one line per item: "LINK: <kind> | <url>", kind one of project, code, video, dataset, blog,
slides, talk, other. If you find nothing, end with "LINK: NONE"."""
MATERIAL_KINDS = ("project", "code", "video", "dataset", "blog", "slides", "talk", "other")
PDF_TO_HTML = os.path.join(ROOT, "specific_scripts", "pdf_to_html.py")
HTML_PROMPT = """Convert this paper into a faithful HTML version of the whole paper, including the appendix.
Output only the inner HTML of <body>, with no <html>/<head>/<body> tags, no markdown and no code fences.
Reproduce the text verbatim: title (<h1>), authors and affiliations, abstract, every section and subsection
(<h2>/<h3>), paragraphs, lists, footnotes, algorithms (<pre>) and tables (<table> with every cell).
Write all math as LaTeX: inline \\( ... \\), display \\[ ... \\] (keep equation numbers with \\tag{n}).
For each figure, at the place it appears, output exactly:
<figure data-fig="N"><figcaption>Figure N: the full caption</figcaption></figure>
where N is the figure number. Do not describe the image. Put the references in an <ol class="refs">."""
CONDENSE_PROMPT = """Below is the inner HTML of a paper's web version. Rewrite it with about 50% less text.
Condense the prose of every section: keep the claims, method, numbers and conclusions, cut repetition and filler.
Keep every heading, the title, authors and affiliations, and the section order unchanged.
Tokens like ⟦K12⟧ stand for figures, tables, equations and references: copy each one exactly, in its place.
Every token that sits on its own (not inside a sentence) must be kept. A token inside a sentence may only be
dropped if you drop that whole sentence.
Output only the condensed inner HTML, with no markdown and no code fences."""
KEEP_RE = re.compile(r'<figure\b.*?</figure>|<table\b.*?</table>|<pre\b.*?</pre>|<ol class="refs">.*?</ol>'
                     r"|\\\[.*?\\\]|\\\(.*?\\\)", re.S)
HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script>window.MathJax = {{tex: {{inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']], tags: 'ams'}}}};</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"></script>
<style>
  body {{ font: 17px/1.6 Georgia, "Times New Roman", serif; max-width: 860px; margin: 0 auto; padding: 24px 20px 80px; color: #222; }}
  h1 {{ font-size: 1.7em; line-height: 1.25; }} h2 {{ margin-top: 1.8em; }} .src {{ font: 13px system-ui, sans-serif; color: #666; }}
  figure {{ margin: 1.5em 0; text-align: center; }} figure img {{ max-width: 100%; }}
  figcaption {{ font-size: 0.9em; color: #444; text-align: left; margin-top: 6px; }}
  table {{ border-collapse: collapse; margin: 1em auto; font-size: 0.85em; }} td, th {{ border: 1px solid #ccc; padding: 3px 6px; }}
  pre {{ background: #f6f8fa; padding: 10px; overflow-x: auto; font-size: 0.85em; }} .refs {{ font-size: 0.85em; }}
</style></head><body>
<p class="src">HTML version made by Claude ({model}) from <a href="../../{pdf}">the PDF</a>; check the PDF for exact wording and figures.</p>
{body}
</body></html>
"""

sys.path.insert(0, os.path.join(WEB, "corl2026"))
sys.path.insert(0, os.path.join(WEB, "papers"))
import build  # noqa: E402  re-run after every change so index.html carries the summaries
import papers  # noqa: E402
sys.path.insert(0, os.path.join(WEB, "corl2026_workshops"))
import workshops  # noqa: E402

client = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip())
lock = threading.Lock()


class Site:
    """One paper browser: its folder, the path it's served at, how to rebuild its page and look up a paper.

    info(pid) -> (title, authors) or None; adder is the module with add_url() / add_pdf(), for sites with an Add box.
    """

    def __init__(self, prefix, title, here, rebuild, info, adder=None):
        self.prefix, self.title, self.here = prefix, title, here
        self.rebuild, self.info, self.adder = rebuild, info, adder


SITES = [Site("/Corl2026", "CoRL 2026", build.HERE, build.main, build.paper_info),
         Site("/Papers", papers.TITLE, papers.HERE, papers.build_page, papers.paper_info, papers),
         Site("/Workshops", workshops.TITLE, workshops.HERE, workshops.build_page, workshops.paper_info)]
INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Paper browsers</title></head>
<body style="font:16px/1.6 system-ui,sans-serif;margin:40px"><h1>Paper browsers</h1><ul>{}</ul></body></html>"""


def load(site, name):
    return build.load(site.here, name, {})


def ask(pdf, prompt, max_tokens, effort):
    """Send the PDF + prompt to Claude; returns {text, cost, input_tokens, output_tokens}."""
    if os.path.getsize(pdf) <= MAX_PDF_BYTES:
        doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                              "data": base64.standard_b64encode(open(pdf, "rb").read()).decode()}}
    else:
        with pymupdf.open(pdf) as d:
            doc = {"type": "text", "text": "\n".join(p.get_text() for p in d)}
    return ask_content([doc, {"type": "text", "text": prompt}], max_tokens, effort)


def ask_content(content, max_tokens, effort):
    """Send one user message to Claude; returns {text, cost, input_tokens, output_tokens}."""
    with client.beta.messages.stream(
        model=MODEL, max_tokens=max_tokens,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},  # re-run on a fallback model if a safety classifier declines
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude declined this paper")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Claude's output was cut off (paper too long)")
    return {"text": "".join(b.text for b in msg.content if b.type == "text").strip(), **usage(msg.usage)}


def usage(u):
    """{cost, input_tokens, output_tokens} of one response."""
    # ponytail: priced at Opus rates even if a refusal fallback model answered (rare); thinking is in output_tokens
    tokens_in = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    return {"cost": round(tokens_in * PRICE_IN + u.output_tokens * PRICE_OUT, 4),
            "input_tokens": tokens_in, "output_tokens": u.output_tokens}


def summarize(pdf):
    return ask(pdf, PROMPT, 16000, "medium")


def find_link(site, pid):
    """Claude + web search for a non-OpenReview copy of the paper (arXiv preferred). Returns {url or None, cost, searches}."""
    info = site.info(pid)
    if not info:
        raise RuntimeError("unknown paper")
    messages = [{"role": "user", "content": LINK_PROMPT.format(title=info[0], authors=info[1] or "unknown")}]
    cost = searches = 0
    for _ in range(4):  # a long server-side search loop stops with pause_turn; send it back to continue
        with client.beta.messages.stream(
            model=MODEL, max_tokens=16000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
            messages=messages,
        ) as stream:
            msg = stream.get_final_message()
        n = (msg.usage.server_tool_use.web_search_requests or 0) if msg.usage.server_tool_use else 0
        searches += n
        cost += usage(msg.usage)["cost"] + n * WEB_SEARCH_PRICE
        if msg.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": msg.content})
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude declined this paper")
    text = "".join(b.text for b in msg.content if b.type == "text")
    found = re.findall(r"URL:\s*(\S+)", text)
    url = found[-1].strip("`<>*.,;)\"'") if found else ""
    ok = re.match(r"https?://", url) and "openreview.net" not in url  # the answer comes from web pages: check it
    return {"url": url if ok else None, "cost": round(cost, 4), "searches": searches}


def html_version(site, pid, pdf):
    """Claude transcribes text + LaTeX; figures are the crops from extract_first_page.py. Returns {path, cost}."""
    r = ask(pdf, HTML_PROMPT, 128000, "low")  # ponytail: low effort, it's transcription not reasoning
    name = os.path.splitext(os.path.basename(pdf))[0]
    out = os.path.join(site.here, "htmls_claude", name)
    os.makedirs(out, exist_ok=True)
    figs = {f["n"]: f["src"] for f in load(site, "first_page.json").get(pid, {}).get("figures", [])}

    def figure(m):
        n = int(m.group(1))
        if n not in figs:
            return m.group(0)
        shutil.copy(os.path.join(site.here, figs[n]), os.path.join(out, f"fig{n}.png"))
        # the crop already contains the caption, so Claude's <figcaption> is dropped (kept as alt text)
        cap = re.sub(r"<[^>]+>", "", m.group(2)).strip().replace('"', "&quot;")
        return f'<figure data-fig="{n}"><img src="fig{n}.png" alt="{cap}" loading="lazy"></figure>'

    body = re.sub(r"^```(?:html)?\s*|\s*```$", "", r["text"])
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S | re.I)  # the PDF is untrusted input
    body = re.sub(r'<figure data-fig="(\d+)">(.*?)</figure>', figure, body, flags=re.S)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(HTML_TEMPLATE.format(title=re.sub(r"<[^>]+>", "", title.group(1)).strip() if title else name,
                                     model=MODEL, pdf=urllib.parse.quote(os.path.relpath(pdf, site.here)), body=body))
    meta = {"cost": r["cost"], "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"]}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    with lock:
        site.rebuild()
    return {"path": os.path.relpath(os.path.join(out, "index.html"), site.here), **meta}


def condense(site, page):
    """Claude HTML version -> condensed.html beside it (+ condensed.json): prose ~50% shorter.

    Figures, tables, algorithms, references and math are swapped for ⟦Kn⟧ tokens before Claude sees the
    page and put back after, so they come through byte for byte. Returns {path, cost, ...}."""
    html = open(page).read().replace(CONDENSED_LINK, "")  # a re-condense must not link condensed.html to itself
    m = re.search(r'(<p class="src">.*?</p>\n)(.*)(\n</body>)', html, re.S)
    if not m:
        raise RuntimeError("unexpected HTML layout")
    kept = []

    def keep(k):
        kept.append(k.group(0))
        return f"⟦K{len(kept) - 1}⟧"

    body = KEEP_RE.sub(keep, m.group(2))
    r = ask_content(CONDENSE_PROMPT + "\n\n" + body, 128000, "low")
    out = re.sub(r"^```(?:html)?\s*|\s*```$", "", r["text"])
    out = re.sub(r"<script\b.*?</script>", "", out, flags=re.S | re.I)
    missing = [i for i, k in enumerate(kept) if not k.startswith("\\(") and f"⟦K{i}⟧" not in out]
    if missing:  # inline math may go with a cut sentence; nothing else may
        raise RuntimeError(f"Claude dropped {len(missing)} figures / tables / equations; retry")
    out = re.sub(r"⟦K(\d+)⟧", lambda t: kept[int(t.group(1))] if int(t.group(1)) < len(kept) else "", out)
    src = m.group(1).replace("HTML version made by Claude", "Condensed HTML version (text ~50% shorter; "
                             '<a href="index.html">full version</a>) made by Claude')
    path = os.path.join(os.path.dirname(page), "condensed.html")
    with open(path, "w") as f:
        f.write(html[:m.start()] + src + out + html[m.start(3):])
    meta = {"cost": r["cost"], "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
            "chars_before": len(re.sub(r"<[^>]+>", "", body)), "chars_after": len(re.sub(r"<[^>]+>", "", out))}
    json.dump(meta, open(os.path.join(os.path.dirname(page), "condensed.json"), "w"))
    link_condensed(page)
    with lock:
        site.rebuild()
    return {"path": os.path.relpath(path, site.here), **meta}


CONDENSED_LINK = ' · <a href="condensed.html">✂️ Condensed version</a>'


def link_condensed(page):
    """Add a Condensed version link to the original Claude page's source line; the page is otherwise kept as is."""
    html = open(page).read()
    if CONDENSED_LINK not in html:
        with open(page, "w") as f:
            f.write(re.sub(r'(<p class="src">.*?)(</p>)', lambda t: t.group(1) + CONDENSED_LINK + t.group(2),
                           html, count=1, flags=re.S))


def condense_button(page):
    """Snippet added to a served Claude HTML page: the Condense button, or the link once condensed."""
    pid = os.path.basename(os.path.dirname(page)).split("_", 1)[0]
    meta = os.path.join(os.path.dirname(page), "condensed.json")
    inner = (f'<a href="condensed.html">✂️ Condensed version (${json.load(open(meta))["cost"]:.2f})</a>'
             if os.path.exists(meta) else "<button>✂️ Condense</button>")
    return f"""<div id="condense" style="position:fixed;top:10px;right:12px;font:13px system-ui,sans-serif;
background:#fff;padding:4px 8px;border:1px solid #ccc;border-radius:6px">{inner}</div>
<script>
const cb = document.querySelector('#condense button');
if (cb) cb.onclick = async () => {{
  cb.disabled = true; cb.textContent = '⏳ Condensing with Claude… (a few minutes)';
  try {{
    const r = await fetch('../../condense/{pid}', {{method: 'POST'}}), j = await r.json();  // page is htmls_claude/<dir>/
    if (!r.ok) throw new Error(j.error);
    cb.outerHTML = `<a href="condensed.html">✂️ Condensed version ($${{j.cost.toFixed(2)}})</a>`;
  }} catch (e) {{ cb.disabled = false; cb.textContent = '⚠️ ' + e.message + ' (retry)'; }}
}};
</script>
"""


def html_python(site, pdf):
    """No-LLM conversion (specific_scripts/pdf_to_html.py); a subprocess, as MuPDF isn't thread-safe. Returns {path, ...}."""
    out = os.path.join(site.here, "htmls_python", os.path.splitext(os.path.basename(pdf))[0])
    r = subprocess.run([sys.executable, PDF_TO_HTML, pdf, out], capture_output=True, text=True, timeout=900)
    if r.returncode:
        raise RuntimeError("conversion failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    with lock:
        site.rebuild()
    return {"path": os.path.relpath(os.path.join(out, "index.html"), site.here),
            **json.load(open(os.path.join(out, "meta.json")))}


def save(site, pid, value, name="summaries.json"):
    """Store (or erase, value=None) one summary / rating / link and rebuild the site's index.html with it."""
    with lock:  # ponytail: whole-file rewrite + full rebuild per change (~seconds), fine for one user
        s = load(site, name)
        if value is None:
            s.pop(pid, None)
        else:
            s[pid] = value
        json.dump(s, open(os.path.join(site.here, name), "w"), ensure_ascii=False, indent=1)
        site.rebuild()


def material(title, authors):
    """Claude + web search: [[kind, url], ...] of the paper's project page, code, videos, ... ([] if none)."""
    messages = [{"role": "user", "content": MATERIAL_PROMPT.format(title=title, authors=authors or "unknown")}]
    for _ in range(4):  # a long server-side search loop stops with pause_turn; send it back to continue
        with client.beta.messages.stream(
            model=MODEL, max_tokens=16000, output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}], messages=messages,
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": msg.content})
    text = "".join(b.text for b in msg.content if b.type == "text")
    out = []
    for kind, url in re.findall(r"LINK:\s*(\w+)\s*\|\s*(\S+)", text):  # the answer comes from web pages: check it
        url = url.strip("`<>*.,;)\"'")
        if kind.lower() in MATERIAL_KINDS and re.match(r"https?://", url) and [kind.lower(), url] not in out:
            out.append([kind.lower(), url])
    return out


def whatsapp(site, pid):
    """(code, {text, material}) for the WhatsApp message; Claude runs only for what isn't stored yet."""
    pdfs = glob.glob(os.path.join(site.here, "pdfs", f"{pid}_*.pdf"))
    p = site.info(pid)
    if not pdfs or not p:
        return 404, {"error": "paper PDF not found"}
    short, found = load(site, "slide_summaries.json").get(pid), load(site, "material.json").get(pid)
    try:
        short = short or ask(pdfs[0], WA_PROMPT, 4000, "low")
        found = found if found is not None else material(*p)
    except (anthropic.APIError, RuntimeError) as e:
        return 502, {"error": str(e)}
    with lock:  # the files may have changed while Claude ran: re-read before writing
        for name, value in [("slide_summaries.json", {"text": short["text"], "cost": short["cost"]}), ("material.json", found)]:
            d = load(site, name)
            d[pid] = value
            json.dump(d, open(os.path.join(site.here, name), "w"), ensure_ascii=False, indent=1)
        gh = [u for k, u in found if re.match(r"https://github\.com/[\w.-]+/[\w.-]+/?$", u)]  # the GitHub sign + column
        if gh:
            g = load(site, "github.json")
            g[pid] = list(dict.fromkeys(g.get(pid, []) + [u.rstrip("/") for u in gh]))
            json.dump(g, open(os.path.join(site.here, "github.json"), "w"), ensure_ascii=False, indent=1)
        site.rebuild()
    return 200, {"text": short["text"], "material": found}


class Handler(http.server.SimpleHTTPRequestHandler):
    def parse_request(self):
        """Find the site the path starts with and strip its prefix, so the handlers see paths in its folder."""
        if not super().parse_request():
            return False
        for site in SITES:
            if self.path.startswith(site.prefix + "/"):
                self.site, self.directory, self.path = site, site.here, self.path[len(site.prefix):]
                return True
        path = self.path.split("?")[0]
        site = next((s for s in SITES if s.prefix == path), None)
        if site:  # the page's links are relative, so it needs the trailing slash
            self.send_response(301)
            self.send_header("Location", site.prefix + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/":
            body = INDEX.format("".join(f'<li><a href="{s.prefix}/">{s.title}</a></li>' for s in SITES)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)
        return False

    def do_GET(self):
        """Claude HTML pages get the Condense button; byte ranges, so movies seek (and play at all in Safari)."""
        c = re.fullmatch(r"/htmls_claude/([^/]+)/index\.html", urllib.parse.unquote(self.path.split("?")[0]))
        page = c and os.path.join(self.site.here, "htmls_claude", c.group(1), "index.html")
        if page and c.group(1) not in {".", ".."} and os.path.isfile(page):
            body = open(page).read().replace("</body>", condense_button(page) + "</body>", 1).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if re.fullmatch(r"/(index\.html)?", self.path.split("?")[0]):
            del self.headers["If-Modified-Since"]  # rebuilt after every click, maybe within the same second: always resend
        rng = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        start, end = int(rng.group(1)), min(int(rng.group(2) or size - 1), size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            return self.end_headers()
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0 and (chunk := f.read(min(1 << 20, left))):
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):  # the browser drops the rest of "bytes=0-" once it seeks
            pass

    def do_POST(self):
        site = self.site
        if self.path == "/add" and site.adder:  # body: {"url": ...} as JSON, or the PDF itself
            n = int(self.headers.get("Content-Length", 0))
            if n > site.adder.MAX_BYTES:
                return self.reply(413, {"error": "the file is over 100 MB"})
            body = self.rfile.read(n)
            before = set(build.load(site.here, "papers.json", {}))
            try:
                with lock:  # ponytail: one add at a time (MuPDF isn't thread-safe); also queues behind rebuilds
                    if self.headers.get("Content-Type", "").startswith("application/pdf"):
                        name = urllib.parse.unquote(self.headers.get("X-Filename", "file.pdf"))
                        pid = site.adder.add_pdf(body, "uploaded: " + name)
                    else:
                        pid = site.adder.add_url(json.loads(body)["url"])
            except (ValueError, KeyError, OSError) as e:  # bad link, not a PDF, private address, download failed
                return self.reply(400, {"error": str(e)})
            return self.reply(200, {"id": pid, "exists": pid in before})
        r = re.fullmatch(r"/rate/([A-Za-z0-9_-]+)", self.path)
        if r:  # body: "1".."5", or "0" to clear
            v = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode().strip()
            if v not in {"0", "1", "2", "3", "4", "5"}:
                return self.reply(400, {"error": "rating must be 0-5"})
            save(site, r.group(1), int(v) or None, "ratings.json")
            return self.reply(200, {})
        c = re.fullmatch(r"/condense/([A-Za-z0-9_-]+)", self.path)
        if c:
            pages = glob.glob(os.path.join(site.here, "htmls_claude", f"{c.group(1)}_*", "index.html"))
            if not pages:
                return self.reply(404, {"error": "make the Claude HTML version first"})
            try:
                return self.reply(200, condense(site, pages[0]))
            except (anthropic.APIError, RuntimeError) as e:
                return self.reply(502, {"error": str(e)})
        k = re.fullmatch(r"/find_link/([A-Za-z0-9_-]+)", self.path)
        if k:
            try:
                link = find_link(site, k.group(1))
            except (anthropic.APIError, RuntimeError) as e:
                return self.reply(502, {"error": str(e)})
            save(site, k.group(1), link, "links.json")
            return self.reply(200, link)
        h = re.fullmatch(r"/html_(claude|python)/([A-Za-z0-9_-]+)", self.path)
        if h:
            pdfs = glob.glob(os.path.join(site.here, "pdfs", f"{h.group(2)}_*.pdf"))
            if not pdfs:
                return self.reply(404, {"error": "paper PDF not found"})
            try:
                made = html_version(site, h.group(2), pdfs[0]) if h.group(1) == "claude" else html_python(site, pdfs[0])
                return self.reply(200, made)
            except (anthropic.APIError, RuntimeError, subprocess.TimeoutExpired) as e:
                return self.reply(502, {"error": str(e)})
        w = re.fullmatch(r"/whatsapp/([A-Za-z0-9_-]+)", self.path)
        if w and site.prefix != "/Corl2026":  # My papers / Workshops: the slide from the PDF + material links, cached
            return self.reply(*whatsapp(site, w.group(1)))
        m = re.fullmatch(r"/summarize/([A-Za-z0-9_-]+)", self.path)
        pdfs = glob.glob(os.path.join(site.here, "pdfs", f"{m.group(1)}_*.pdf")) if m else []
        if not pdfs:
            return self.reply(404, {"error": "paper PDF not found"})
        pid = m.group(1)
        cached = load(site, "summaries.json").get(pid)
        if cached:
            return self.reply(200, {"summary": cached})
        try:
            summary = summarize(pdfs[0])
        except (anthropic.APIError, RuntimeError) as e:
            return self.reply(502, {"error": str(e)})
        save(site, pid, summary)
        self.reply(200, {"summary": summary})

    def do_DELETE(self):
        m = re.fullmatch(r"/summarize/([A-Za-z0-9_-]+)", self.path)
        if not m:
            return self.reply(404, {"error": "bad path"})
        save(self.site, m.group(1), None)
        self.reply(200, {})

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
