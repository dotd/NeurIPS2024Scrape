"""Serve the CoRL 2026 browser locally; summarize papers and make HTML versions of them with Claude on demand.

The API key stays here (secrets/claude_api/claude_api.txt), never in index.html. Summaries are cached in
summaries.json next to this file; build.py embeds them so they also show when index.html is opened as a file.

    uv run python htmls/corl2026/serve.py      # then open http://127.0.0.1:8026
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KEY_FILE = os.path.join(ROOT, "secrets", "claude_api", "claude_api.txt")
SUMMARIES = os.path.join(HERE, "summaries.json")
RATINGS = os.path.join(HERE, "ratings.json")  # your 1-5 star ratings
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

HTML_DIR = os.path.join(HERE, "htmls_claude")  # htmls_claude/<pdf name>/index.html + figN.png + meta.json
HTML_PY_DIR = os.path.join(HERE, "htmls_python")  # htmls_python/<pdf name>/index.html + img/ + meta.json
PDF_TO_HTML = os.path.join(ROOT, "specific_scripts", "pdf_to_html.py")
HTML_PROMPT = """Convert this paper into a faithful HTML version of the whole paper, including the appendix.
Output only the inner HTML of <body>, with no <html>/<head>/<body> tags, no markdown and no code fences.
Reproduce the text verbatim: title (<h1>), authors and affiliations, abstract, every section and subsection
(<h2>/<h3>), paragraphs, lists, footnotes, algorithms (<pre>) and tables (<table> with every cell).
Write all math as LaTeX: inline \\( ... \\), display \\[ ... \\] (keep equation numbers with \\tag{n}).
For each figure, at the place it appears, output exactly:
<figure data-fig="N"><figcaption>Figure N: the full caption</figcaption></figure>
where N is the figure number. Do not describe the image. Put the references in an <ol class="refs">."""
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

sys.path.insert(0, HERE)
import build  # noqa: E402  re-run after every change so index.html carries the summaries

client = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip())
lock = threading.Lock()


def load(path=SUMMARIES):
    return json.load(open(path)) if os.path.exists(path) else {}


def ask(pdf, prompt, max_tokens, effort):
    """Send the PDF + prompt to Claude; returns {text, cost, input_tokens, output_tokens}."""
    if os.path.getsize(pdf) <= MAX_PDF_BYTES:
        doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                              "data": base64.standard_b64encode(open(pdf, "rb").read()).decode()}}
    else:
        with pymupdf.open(pdf) as d:
            doc = {"type": "text", "text": "\n".join(p.get_text() for p in d)}
    with client.beta.messages.stream(
        model=MODEL, max_tokens=max_tokens,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},  # re-run on a fallback model if a safety classifier declines
        messages=[{"role": "user", "content": [doc, {"type": "text", "text": prompt}]}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude declined this paper")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Claude's output was cut off (paper too long)")
    u = msg.usage
    # ponytail: priced at Opus rates even if a refusal fallback model answered (rare); thinking is in output_tokens
    tokens_in = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    return {"text": "".join(b.text for b in msg.content if b.type == "text").strip(),
            "cost": round(tokens_in * PRICE_IN + u.output_tokens * PRICE_OUT, 4),
            "input_tokens": tokens_in, "output_tokens": u.output_tokens}


def summarize(pdf):
    return ask(pdf, PROMPT, 16000, "medium")


def html_version(pid, pdf):
    """Claude transcribes text + LaTeX; figures are the crops from extract_first_page.py. Returns {path, cost}."""
    r = ask(pdf, HTML_PROMPT, 128000, "low")  # ponytail: low effort, it's transcription not reasoning
    name = os.path.splitext(os.path.basename(pdf))[0]
    out = os.path.join(HTML_DIR, name)
    os.makedirs(out, exist_ok=True)
    figs = {f["n"]: f["src"] for f in json.load(open(build.FIRST_PAGE)).get(pid, {}).get("figures", [])}

    def figure(m):
        n = int(m.group(1))
        if n not in figs:
            return m.group(0)
        shutil.copy(os.path.join(HERE, figs[n]), os.path.join(out, f"fig{n}.png"))
        # the crop already contains the caption, so Claude's <figcaption> is dropped (kept as alt text)
        cap = re.sub(r"<[^>]+>", "", m.group(2)).strip().replace('"', "&quot;")
        return f'<figure data-fig="{n}"><img src="fig{n}.png" alt="{cap}" loading="lazy"></figure>'

    body = re.sub(r"^```(?:html)?\s*|\s*```$", "", r["text"])
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S | re.I)  # the PDF is untrusted input
    body = re.sub(r'<figure data-fig="(\d+)">(.*?)</figure>', figure, body, flags=re.S)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(HTML_TEMPLATE.format(title=re.sub(r"<[^>]+>", "", title.group(1)).strip() if title else name,
                                     model=MODEL, pdf=urllib.parse.quote(os.path.relpath(pdf, HERE)), body=body))
    meta = {"cost": r["cost"], "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"]}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    with lock:
        build.main()
    return {"path": os.path.relpath(os.path.join(out, "index.html"), HERE), **meta}


def html_python(pdf):
    """No-LLM conversion (specific_scripts/pdf_to_html.py); a subprocess, as MuPDF isn't thread-safe. Returns {path, ...}."""
    out = os.path.join(HTML_PY_DIR, os.path.splitext(os.path.basename(pdf))[0])
    r = subprocess.run([sys.executable, PDF_TO_HTML, pdf, out], capture_output=True, text=True, timeout=900)
    if r.returncode:
        raise RuntimeError("conversion failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    with lock:
        build.main()
    return {"path": os.path.relpath(os.path.join(out, "index.html"), HERE),
            **json.load(open(os.path.join(out, "meta.json")))}


def save(pid, value, path=SUMMARIES):
    """Store (or erase, value=None) one summary / rating and rebuild index.html with it."""
    with lock:  # ponytail: whole-file rewrite + full rebuild per change (~seconds), fine for one user
        s = load(path)
        if value is None:
            s.pop(pid, None)
        else:
            s[pid] = value
        json.dump(s, open(path, "w"), ensure_ascii=False, indent=1)
        build.main()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def do_POST(self):
        r = re.fullmatch(r"/rate/([A-Za-z0-9_-]+)", self.path)
        if r:  # body: "1".."5", or "0" to clear
            v = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode().strip()
            if v not in {"0", "1", "2", "3", "4", "5"}:
                return self.reply(400, {"error": "rating must be 0-5"})
            save(r.group(1), int(v) or None, RATINGS)
            return self.reply(200, {})
        h = re.fullmatch(r"/html_(claude|python)/([A-Za-z0-9_-]+)", self.path)
        if h:
            pdfs = glob.glob(os.path.join(HERE, "pdfs", f"{h.group(2)}_*.pdf"))
            if not pdfs:
                return self.reply(404, {"error": "paper PDF not found"})
            try:
                made = html_version(h.group(2), pdfs[0]) if h.group(1) == "claude" else html_python(pdfs[0])
                return self.reply(200, made)
            except (anthropic.APIError, RuntimeError, subprocess.TimeoutExpired) as e:
                return self.reply(502, {"error": str(e)})
        m = re.fullmatch(r"/summarize/([A-Za-z0-9_-]+)", self.path)
        pdfs = glob.glob(os.path.join(HERE, "pdfs", f"{m.group(1)}_*.pdf")) if m else []
        if not pdfs:
            return self.reply(404, {"error": "paper PDF not found"})
        pid = m.group(1)
        cached = load().get(pid)
        if cached:
            return self.reply(200, {"summary": cached})
        try:
            summary = summarize(pdfs[0])
        except (anthropic.APIError, RuntimeError) as e:
            return self.reply(502, {"error": str(e)})
        save(pid, summary)
        self.reply(200, {"summary": summary})

    def do_DELETE(self):
        m = re.fullmatch(r"/summarize/([A-Za-z0-9_-]+)", self.path)
        if not m:
            return self.reply(404, {"error": "bad path"})
        save(m.group(1), None)
        self.reply(200, {})

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
