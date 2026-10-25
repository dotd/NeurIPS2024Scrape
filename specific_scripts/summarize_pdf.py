"""Summarize a research-paper PDF: abstract + LLM summary + architecture figure + results.

Usage:
  uv run python specific_scripts/summarize_pdf.py paper.pdf                        # markdown to stdout, local ollama
  uv run python specific_scripts/summarize_pdf.py paper.pdf --model qwen3:14b -o out.md
  uv run python specific_scripts/summarize_pdf.py paper.pdf -o out.html
  uv run python specific_scripts/summarize_pdf.py paper.pdf --backend anthropic --api-key sk-ant-...
  uv run python specific_scripts/summarize_pdf.py paper.pdf --backend openai      # key from OPENAI_API_KEY

Requires poppler (pdftotext, pdftoppm) on PATH. Ollama backend needs a running
`ollama serve` with the model pulled (qwen3:4b, qwen3:14b, gemma3:12b, ...).
"""

import argparse
import base64
import html
import json
import os
import re
import subprocess
import sys
import tempfile

import requests

MAX_PROMPT_CHARS = 30000

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "~200 word summary: problem, method, key results",
        },
        "architecture_figure": {
            "type": "integer",
            "description": "Figure number showing the method/architecture overview, 0 if none",
        },
        "architecture_reason": {
            "type": "string",
            "description": "One sentence: why this figure is the architecture figure",
        },
        "results_summary": {
            "type": "string",
            "description": "Markdown summary of the main results, as a table when the paper reports comparable numbers",
        },
    },
    "required": ["summary", "architecture_figure", "architecture_reason", "results_summary"],
    "additionalProperties": False,
}


def extract_pages(pdf_path):
    text = subprocess.run(
        ["pdftotext", pdf_path, "-"], capture_output=True, text=True, check=True
    ).stdout
    return text.split("\f")


def extract_abstract(text):
    m = re.search(r"\bAbstract\b(.*?)\n\s*(?:1\s+)?Introduction\b", text, re.S | re.I)
    if m:
        abstract = " ".join(m.group(1).split())
        if 100 < len(abstract) < 4000:
            return abstract
    return ""  # model summary covers it if the layout defeats the regex


def figure_captions(pages):
    caps = []
    for pageno, page in enumerate(pages, 1):
        for m in re.finditer(r"^Fig(?:ure)?\.?\s*(\d+)\s*[.:|]\s*(.{0,120})", page, re.M):
            caps.append((int(m.group(1)), pageno, " ".join(m.group(2).split())))
    return caps


def build_prompt(pages, captions):
    text = "\n".join(pages)[:MAX_PROMPT_CHARS]
    caption_list = "\n".join(f"Figure {n} (page {p}): {c}" for n, p, c in captions) or "none found"
    # ponytail: instruction goes AFTER the paper text — small local models ignore a leading one
    return f"""PAPER TEXT (extracted from PDF, may contain artifacts):
{text}

FIGURE CAPTIONS FOUND:
{caption_list}

---
You are summarizing the research paper above. Respond with a single JSON object with exactly these keys:
- "summary": ~200 words covering the problem, the proposed method, and key results.
- "architecture_figure": the figure number that shows the method/architecture overview (often Figure 1, but check the captions — pick the one that actually depicts the system/model architecture). Use 0 if no figure does.
- "architecture_reason": one sentence explaining the choice.
- "results_summary": markdown summarizing the main experimental results; use a markdown table when the paper reports comparable numbers (method vs. baselines, scores per benchmark).
Output only the JSON object."""


def llm_ollama(prompt, model):
    r = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "think": False,
        },
        timeout=600,
    )
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def llm_anthropic(prompt, api_key):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def llm_openai(prompt, api_key):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-5",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        },
        timeout=600,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def render_figure_page(pdf_path, pages, fig_num, out_png):
    """Find the page holding the caption of figure `fig_num` and render it to PNG."""
    # ponytail: renders the whole page, not the cropped figure; crop via caption bbox if needed
    pat = re.compile(rf"^Fig(?:ure)?\.?\s*{fig_num}\s*[.:|]", re.M)
    pageno = next((i for i, p in enumerate(pages, 1) if pat.search(p)), None)
    if pageno is None:
        return None
    with tempfile.TemporaryDirectory() as td:
        prefix = os.path.join(td, "fig")
        subprocess.run(
            ["pdftoppm", "-png", "-r", "120", "-f", str(pageno), "-l", str(pageno), pdf_path, prefix],
            check=True,
        )
        produced = [f for f in os.listdir(td) if f.endswith(".png")]
        if not produced:
            return None
        os.replace(os.path.join(td, produced[0]), out_png)
    return out_png


def to_markdown(title, abstract, result, fig_path):
    parts = [f"# {title}", ""]
    if abstract:
        parts += ["## Abstract", "", abstract, ""]
    parts += ["## Summary", "", result["summary"], ""]
    if fig_path:
        parts += [
            f"## Architecture (Figure {result['architecture_figure']})",
            "",
            result["architecture_reason"],
            "",
            f"![architecture]({os.path.basename(fig_path)})",
            "",
        ]
    parts += ["## Results", "", result["results_summary"], ""]
    return "\n".join(parts)


def to_html(title, abstract, result, fig_path):
    def sec(heading, body, pre=False):
        body = html.escape(body)
        return f"<h2>{heading}</h2>\n" + (f"<pre>{body}</pre>" if pre else f"<p>{body}</p>")

    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        "<style>body{max-width:800px;margin:2em auto;font-family:sans-serif;line-height:1.5}img{max-width:100%}</style>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    if abstract:
        parts.append(sec("Abstract", abstract))
    parts.append(sec("Summary", result["summary"]))
    if fig_path:
        b64 = base64.b64encode(open(fig_path, "rb").read()).decode()
        parts.append(f"<h2>Architecture (Figure {result['architecture_figure']})</h2>")
        parts.append(f"<p>{html.escape(result['architecture_reason'])}</p>")
        parts.append(f"<img src='data:image/png;base64,{b64}'>")
    # ponytail: results markdown shown as <pre>; render properly if this becomes user-facing
    parts.append(sec("Results", result["results_summary"], pre=True))
    return "\n".join(parts)


def summarize(pdf_path, backend="ollama", model="qwen3:4b", api_key=None, out=None):
    pages = extract_pages(pdf_path)
    full_text = "\n".join(pages)
    abstract = extract_abstract(full_text)
    prompt = build_prompt(pages, figure_captions(pages))

    if backend == "ollama":
        result = llm_ollama(prompt, model)
    elif backend == "anthropic":
        result = llm_anthropic(prompt, api_key)
    elif backend == "openai":
        result = llm_openai(prompt, api_key or os.environ.get("OPENAI_API_KEY"))
    else:
        raise ValueError(f"unknown backend: {backend}")

    title = os.path.splitext(os.path.basename(pdf_path))[0]
    fig_path = None
    fig_num = int(result.get("architecture_figure") or 0)
    if fig_num > 0:
        base = os.path.splitext(out)[0] if out else os.path.splitext(pdf_path)[0]
        fig_path = render_figure_page(pdf_path, pages, fig_num, f"{base}_arch.png")

    if out and out.endswith(".html"):
        content = to_html(title, abstract, result, fig_path)
    else:
        content = to_markdown(title, abstract, result, fig_path)

    if out:
        with open(out, "w") as f:
            f.write(content)
    return content


def main():
    ap = argparse.ArgumentParser(description="Summarize a research-paper PDF with an LLM")
    ap.add_argument("pdf")
    ap.add_argument("--backend", choices=["ollama", "anthropic", "openai"], default="ollama")
    ap.add_argument("--model", default="qwen3:4b", help="ollama model (qwen3:4b, qwen3:14b, gemma3:12b)")
    ap.add_argument("--api-key", default=None, help="API key for anthropic/openai (or use env var)")
    ap.add_argument("-o", "--out", default=None, help="output file; .html extension switches to HTML, else markdown")
    args = ap.parse_args()

    content = summarize(args.pdf, args.backend, args.model, args.api_key, args.out)
    if args.out:
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    main()
