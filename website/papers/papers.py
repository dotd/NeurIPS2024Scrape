"""Papers you add yourself (a link or an uploaded PDF), browsed with the same page and buttons as CoRL 2026.

website/serve.py serves this folder at http://127.0.0.1:8026/Papers/; its Add box calls add_url() / add_pdf().
The folder is laid out like website/corl2026/ (pdfs/, figs/, first_page.json, robots.json, …), so build.build()
and every button work unchanged. papers.json holds what the CSV holds for CoRL: title, authors, abstract, source.

    uv run python website/papers/papers.py      # rebuild index.html
"""

import datetime
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import anthropic
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TITLE = "My papers"
COLUMNS = ["id", "title", "authors", "abstract", "🏷️ keywords", "source", "pdf", "🎬 youtube", "added"]
KEY_FILE = os.path.join(ROOT, "secrets", "claude_api", "claude_api.txt")
KEYWORDS_PROMPT = """Give 3 to 6 keywords for this paper's topics (methods, tasks, application area), each 1 to 3 words,
lowercase. Reuse keywords from this list when they fit, so similar papers share them: {known}
Title: {title}
Abstract or start of the paper: {abstract}
Answer with only the keywords, separated by "; "."""
FIND_PAPER_PROMPT = """This web page ({url}) presents a research paper (e.g. a project page).
Pick the link to the main paper itself: prefer its arXiv abstract page, else OpenReview, else a direct PDF link.
Use only links from the list below. Not cited/related work, not the code repo or the authors' homepages.
Page text: {text}
Links on the page:
{links}
End your answer with one line: "URL: <the link>", or "URL: NONE" if the page links to no paper."""
YOUTUBE_PROMPT = """Search YouTube for a video presenting this paper (a talk, demo or project video).
Make sure the video is about this exact paper, not a related one.
Title: {title}
Authors: {authors}
End your answer with one line: "URL: <the youtube.com/watch link>", or "URL: NONE" if there is no such video."""
YOUTUBE_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")
GITHUB_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+")
MAX_BYTES = 100 * 1024 * 1024
UA = "Mozilla/5.0 (personal paper browser)"

sys.path.insert(0, os.path.join(ROOT, "website", "corl2026"))
sys.path.insert(0, os.path.join(ROOT, "specific_scripts"))
import build  # noqa: E402
from corl2026_affiliations import COMPANY_RES, candidates, canonical_company, ror_match  # noqa: E402
from corl2026_backbones import backbones  # noqa: E402
from corl2026_github import repos  # noqa: E402
from corl2026_robots import robots  # noqa: E402
from extract_first_page import extract  # noqa: E402

ADD_BOX = """<div id="add" style="flex:none;display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 16px;
border-bottom:1px solid #ddd;background:#fffbea">
  <b>➕ Add a paper</b>
  <input id="addUrl" type="url" placeholder="arXiv / OpenReview / PDF link, or a project page (github.io) that links to the paper"
         style="flex:1;min-width:240px;padding:5px 8px;border:1px solid #bbb;border-radius:6px">
  <button id="addGo" style="padding:5px 12px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer">Add link</button>
  <span>or</span>
  <label style="padding:5px 12px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer">📄 Upload PDF
    <input id="addFile" type="file" accept="application/pdf,.pdf" hidden></label>
  <span id="addMsg" style="color:#666"></span>
</div>
<script>
async function addPaper(opts, what) {
  const msg = document.getElementById('addMsg');
  if (!location.protocol.startsWith('http'))
    return msg.textContent = 'run: uv run python website/serve.py, then open http://127.0.0.1:8026/Papers/';
  msg.textContent = `⏳ Adding ${what}: downloading, extracting figures, robots, backbones, affiliations… (~30 s)`;
  try {
    const r = await fetch('add', {method: 'POST', ...opts}), j = await r.json();
    if (!r.ok) throw new Error(j.error);
    if (j.exists) {  // nothing added: say so and scroll to it, no Claude calls
      const i = rows.findIndex(x => x[0] === j.id);
      msg.textContent = 'ℹ️ Already in the list: ' + (i >= 0 ? rows[i][1] : j.id);
      if (i >= 0 && dets[i].isConnected) dets[i].scrollIntoView();
      return;
    }
    location.hash = 'claude:' + j.id; location.reload();  // show it now; Claude runs after the reload (below)
  } catch (e) { msg.textContent = '⚠️ ' + e.message; }
}
// after an add the page reloads with #claude:<id>: show the paper, then press 📝 Summarize and the Claude HTML
// button for it; the server finishes them even if the tab closes. Runs before the page script reads the #.
if (location.hash.startsWith('#claude:')) (async () => {
  const pid = decodeURIComponent(location.hash.slice(8)), msg = document.getElementById('addMsg');
  history.replaceState(null, '', '#' + encodeURIComponent(pid));  // the page script scrolls to it, then clears it
  msg.textContent = '⏳ Added. Claude is summarizing it and making the HTML version… (a few minutes)';
  const errs = (await Promise.all(['summarize/', 'html_claude/'].map(p => fetch(p + pid, {method: 'POST'})
    .then(async x => x.ok ? '' : (await x.json()).error).catch(e => e.message)))).filter(Boolean);
  if (errs.length) alert('Added, but: ' + errs.join('; '));
  location.hash = pid; location.reload();  // rebuilt with the summary and HTML link
})();
document.getElementById('addGo').onclick = () => {
  const u = document.getElementById('addUrl').value.trim();
  if (u) addPaper({headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: u})}, 'the link');
};
document.getElementById('addUrl').onkeydown = e => { if (e.key === 'Enter') document.getElementById('addGo').click(); };
document.getElementById('addFile').onchange = e => {
  const f = e.target.files[0];
  if (f) addPaper({headers: {'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(f.name)}, body: f}, f.name);
};
</script>"""


def load(name, default):
    return build.load(HERE, name, default)


def store(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w"), ensure_ascii=False, indent=1)


def check_public(url):
    """Only http(s) to public addresses: on AWS, 169.254.169.254 hands out the machine's credentials."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("only http(s) links")
    for *_, addr in socket.getaddrinfo(u.hostname, u.port or 443):
        if not ipaddress.ip_address(addr[0].split("%")[0]).is_global:
            raise ValueError(f"{u.hostname} is not a public address")


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    # ponytail: DNS could change between the check and the connect (rebinding); acceptable behind the login
    check_public(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.build_opener(PublicRedirects).open(req, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("the file is over 100 MB")
    return data


def arxiv_info(aid):
    """{title, authors, abstract} from the arXiv API, {} if it fails (then the PDF's first page is used)."""
    try:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        e = ET.fromstring(fetch(f"https://export.arxiv.org/api/query?id_list={aid}")).find("a:entry", ns)
        text = lambda tag: " ".join(e.findtext(tag, "", ns).split())  # noqa: E731
        return {"title": text("a:title"), "abstract": text("a:summary"),
                "authors": ", ".join(a.findtext("a:name", "", ns) for a in e.findall("a:author", ns))}
    except (OSError, ValueError, ET.ParseError, AttributeError):
        return {}


def openreview_info(nid):
    """{title, authors, abstract} from the OpenReview API, {} if it fails."""
    try:
        c = json.loads(fetch(f"https://api2.openreview.net/notes?id={nid}"))["notes"][0]["content"]
        v = lambda k: c.get(k, {}).get("value") or ""  # noqa: E731
        return {"title": v("title"), "abstract": v("abstract"), "authors": ", ".join(v("authors"))}
    except (OSError, ValueError, KeyError, IndexError):
        return {}


def find_paper(url, page):
    """Claude reads a project page (e.g. a github.io site) and picks the link to its main paper; returns it."""
    html = page.decode("utf-8", "replace")
    links = sorted({urllib.parse.urljoin(url, h) for h in re.findall(r'href=["\']([^"\'#][^"\']*)', html)})
    text = " ".join(re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<[^>]+>", " ", html, flags=re.S | re.I).split())
    msg = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip()).beta.messages.create(
        model="claude-opus-5-5", max_tokens=4000, output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
        messages=[{"role": "user", "content": FIND_PAPER_PROMPT.format(
            url=url, text=text[:30000], links="\n".join(links[:500]))}])
    found = re.findall(r"URL:\s*(\S+)", "".join(b.text for b in msg.content if b.type == "text"))
    paper = found[-1].strip("`<>*.,;)\"'") if found else ""
    if not re.match(r"https?://", paper):  # the page is untrusted input; fetch() still refuses private addresses
        raise ValueError("Claude found no paper on that page: paste the arXiv or PDF link")
    return paper, links


def add_url(url, source=None, page_links=()):
    """Add the paper behind a link (arXiv, OpenReview, a direct PDF link, or a project page that links to one).

    Returns its id. source: the link the user pasted, when url is the paper found on it."""
    url = url.strip()
    pid, info, pdf_url = None, {}, url
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?", url)
    if m:
        pid, info = "arxiv-" + m.group(1).replace(".", "-"), arxiv_info(m.group(1))
        pdf_url = f"https://arxiv.org/pdf/{m.group(1)}{m.group(2) or ''}"
    m = re.search(r"openreview\.net/(?:forum|pdf)\?(?:.*&)?id=([A-Za-z0-9_-]+)", url)
    if m:
        pid, info, pdf_url = m.group(1), openreview_info(m.group(1)), f"https://openreview.net/pdf?id={m.group(1)}"
    if pid and pid in load("papers.json", {}):
        return pid
    data = fetch(pdf_url)
    if not data.startswith(b"%PDF-"):
        if source:  # already followed one page; don't chase links forever
            raise ValueError(f"the paper link Claude found ({url}) is not a PDF either")
        try:
            paper, links = find_paper(url, data)
            return add_url(paper, source=url, page_links=links)
        except anthropic.APIError as e:
            raise ValueError(f"Claude could not read the page: {e}")
    return add_pdf(data, source or url, pdf_url, pid, info, page_links)


def add_pdf(data, source, pdf_url="", pid=None, info=None, page_links=()):
    """Store one PDF and run the per-paper extraction CoRL 2026 got in batch; returns its id."""
    if not data.startswith(b"%PDF-"):
        raise ValueError("that file is not a PDF")
    pid = pid or "pdf-" + hashlib.sha1(data).hexdigest()[:10]
    papers = load("papers.json", {})
    if pid in papers:
        return pid
    info = info or {}
    for d in ("pdfs", "figs"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    pdf = os.path.join(HERE, "pdfs", f"{pid}_.pdf")
    with open(pdf, "wb") as f:
        f.write(data)
    try:
        first = extract(pdf, os.path.join(HERE, "figs", f"{pid}.png"), base=HERE)
    except Exception:  # an odd PDF (scanned, no text) still gets added, just without figures
        first = {"title": "", "abstract": "", "figure": None, "figures": []}
    title = info.get("title") or first["title"] or source.rsplit("/", 1)[-1]
    named = os.path.join(HERE, "pdfs", f"{pid}_{re.sub(r'[^\w\- .,()]', ' ', title)[:100].strip()}.pdf")
    os.replace(pdf, named)

    with pymupdf.open(named) as doc:
        text = "\n".join(p.get_text() for p in doc)
        cands, raw = candidates(doc[0])
    # a project page links its repo even when the PDF doesn't
    gh = list(dict.fromkeys(repos(named) + [m.group(0).removesuffix(".git") for u in page_links if (m := GITHUB_RE.match(u))]))
    for name, found in [("robots.json", robots(text)), ("backbones.json", backbones(text)), ("github.json", gh)]:
        if found:
            store(name, {**load(name, {}), pid: found})
    aff = load("affiliations.json", {"papers": {}, "ror": {}})
    companies, universities = {c for c, rx in COMPANY_RES.items() if rx.search(raw)}, set()
    for c in cands:  # ROR API, cached per affiliation string like corl2026_affiliations.py
        if c not in aff["ror"] and (m := ror_match(c)) != "error":
            aff["ror"][c] = m
        org = aff["ror"].get(c)
        if org and "education" in org["types"]:
            universities.add(org["name"])
        elif org and "company" in org["types"]:
            companies.add(canonical_company(org["name"]))
    aff["papers"][pid] = {"companies": sorted(companies), "universities": sorted(universities), "candidates": cands}
    store("affiliations.json", aff)
    store("first_page.json", {**load("first_page.json", {}), pid: first})
    abstract = info.get("abstract") or first["abstract"]
    papers[pid] = {"title": title, "authors": info.get("authors", ""), "abstract": abstract,
                   "keywords": keywords(title, abstract or text[:4000], papers),
                   "source": source, "pdf": pdf_url, "youtube": youtube(title, info.get("authors", ""), page_links), "added": datetime.datetime.now().isoformat(" ", "minutes")}
    store("papers.json", papers)
    build_page()
    return pid


def keywords(title, abstract, papers):
    """3-6 keywords from Claude for the Keywords filter, reusing ones other papers have; [] if the call fails."""
    known = sorted({k for p in papers.values() for k in p.get("keywords", [])})
    try:
        msg = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip()).beta.messages.create(
            model="claude-opus-5-5", max_tokens=2000, output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
            messages=[{"role": "user", "content": KEYWORDS_PROMPT.format(
                known="; ".join(known) or "(none yet)", title=title, abstract=abstract)}])
    except (anthropic.APIError, OSError):  # the paper is still added, just without keywords
        return []
    if msg.stop_reason != "end_turn":
        return []
    text = "".join(b.text for b in msg.content if b.type == "text")
    return list(dict.fromkeys(k.strip(" .\"'\n").lower() for k in text.split(";") if k.strip(" .\n")))[:6]


def youtube(title, authors, page_links=()):
    """A YouTube video of the paper: one the project page links, else Claude + web search; "" if none or it fails."""
    for u in page_links:
        if m := YOUTUBE_RE.match(u):
            return "https://www.youtube.com/watch?v=" + m.group(1)
    messages = [{"role": "user", "content": YOUTUBE_PROMPT.format(title=title, authors=authors or "unknown")}]
    try:
        for _ in range(4):  # a long server-side search loop stops with pause_turn; send it back to continue
            msg = anthropic.Anthropic(api_key=open(KEY_FILE).read().strip()).beta.messages.create(
                model="claude-opus-5-5", max_tokens=8000, output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}], messages=messages)
            if msg.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": msg.content})
    except (anthropic.APIError, OSError):  # the paper is still added, just without a video
        return ""
    found = re.findall(r"URL:\s*(\S+)", "".join(b.text for b in msg.content if b.type == "text"))
    m = found and YOUTUBE_RE.match(found[-1].strip("`<>*.,;)\"'"))
    return "https://www.youtube.com/watch?v=" + m.group(1) if m else ""


def paper_info(pid):
    """(title, authors), for the Find link button."""
    p = load("papers.json", {}).get(pid)
    return (p["title"], p["authors"]) if p else None


def build_page():
    papers = load("papers.json", {})
    rows = [[pid] + ["; ".join(p.get("keywords", [])) if c == "🏷️ keywords" else p.get(c.split()[-1], "") for c in COLUMNS[1:]]  # newest first
            for pid, p in sorted(papers.items(), key=lambda kv: kv[1]["added"], reverse=True)]
    build.build(HERE, TITLE, list(COLUMNS), rows, ADD_BOX, store="papers")


if __name__ == "__main__":
    build_page()
