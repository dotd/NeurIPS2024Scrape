"""Build and launch a Node/Express website showing ICLR 2026 world-model papers.

Pipeline:
  1. Read ConferencesData/ICLR_cc_2026_Conference.csv
  2. Filter rows whose title / keywords / primary_area / TLDR / abstract match
     world-model-ish terms (see WORLD_MODEL_PATTERNS)
  3. Write papers.json + frontend (HTML/CSS/JS) + Express server.js + package.json
     under specific_scripts/iclr2026_worldmodel_site/
  4. Run `npm install` (only if node_modules is missing) and `node server.js`
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from OpenreviewScrape.definitions import PROJECT_ROOT_DIR


CSV_PATH = os.path.join(
    PROJECT_ROOT_DIR, "ConferencesData", "ICLR_cc_2026_Conference.csv"
)
SITE_DIR = os.path.join(
    PROJECT_ROOT_DIR, "specific_scripts", "iclr2026_worldmodel_site"
)

# Order must match OpenreviewScrape/run_pipeline.py `fields`.
CSV_COLUMNS = [
    "id",
    "title",
    "authors",
    "keywords",
    "primary_area",
    "venue",
    "pdf",
    "supplementary_material",
    "TLDR",
    "spotlight",
    "abstract",
]

# Terms that mark a paper as world-model-related. Matched case-insensitively as
# whole substrings against the SEARCHABLE_FIELDS below.
WORLD_MODEL_PATTERNS = [
    re.compile(r"world[\s\-]?models?", re.IGNORECASE),
    re.compile(r"\bdreamer\b", re.IGNORECASE),
    re.compile(r"latent[\s\-]?dynamics", re.IGNORECASE),
]
SEARCHABLE_FIELDS = ("title", "keywords", "primary_area", "TLDR", "abstract")


class Paper:
    def __init__(self, row):
        for col, value in zip(CSV_COLUMNS, row):
            setattr(self, col, value)

    def matches_world_model(self):
        for field in SEARCHABLE_FIELDS:
            text = getattr(self, field, "")
            if not text:
                continue
            for pattern in WORLD_MODEL_PATTERNS:
                if pattern.search(text):
                    return True
        return False

    def to_dict(self):
        keywords = [k.strip() for k in self.keywords.split(";") if k.strip()]
        authors = [a.strip() for a in self.authors.split(";") if a.strip()]
        return {
            "id": self.id,
            "title": self.title,
            "authors": authors,
            "keywords": keywords,
            "primary_area": self.primary_area,
            "venue": self.venue,
            "pdf": self.pdf,
            "supplementary_material": self.supplementary_material,
            "tldr": self.TLDR,
            "spotlight": self.spotlight,
            "abstract": self.abstract,
        }


def load_papers(csv_path):
    papers = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line:
                continue
            row = line.split("\t")
            if len(row) != len(CSV_COLUMNS):
                print(
                    f"  skipping line {line_no}: {len(row)} fields "
                    f"(expected {len(CSV_COLUMNS)})",
                    file=sys.stderr,
                )
                continue
            papers.append(Paper(row))
    return papers


def filter_world_model(papers):
    return [p for p in papers if p.matches_world_model()]


# ---------------------------------------------------------------------------
# Site scaffolding
# ---------------------------------------------------------------------------

PACKAGE_JSON = {
    "name": "iclr2026-worldmodel-site",
    "version": "1.0.0",
    "private": True,
    "description": "ICLR 2026 world-model papers browser",
    "main": "server.js",
    "scripts": {"start": "node server.js"},
    "dependencies": {"express": "^4.19.2"},
}

SERVER_JS = r"""const express = require('express');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '127.0.0.1';

const app = express();
const papersPath = path.join(__dirname, 'data', 'papers.json');
const papers = JSON.parse(fs.readFileSync(papersPath, 'utf-8'));

app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/papers', (_req, res) => {
  res.json(papers);
});

app.get('/api/meta', (_req, res) => {
  res.json({
    count: papers.papers.length,
    generated_at: papers.generated_at,
    source: papers.source,
    patterns: papers.patterns,
  });
});

app.listen(PORT, HOST, () => {
  console.log(`ICLR 2026 world-model site running at http://${HOST}:${PORT}`);
  console.log(`Serving ${papers.papers.length} papers from ${papersPath}`);
});
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ICLR 2026 - World Model Papers</title>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <header>
    <h1>ICLR 2026 &middot; World Model Papers</h1>
    <p id="meta" class="meta">Loading&hellip;</p>
    <div class="controls">
      <input id="search" type="search" placeholder="Search title, author, keyword, abstract&hellip;" />
      <select id="venue-filter">
        <option value="">All venues</option>
      </select>
      <select id="sort">
        <option value="title">Sort: Title (A-Z)</option>
        <option value="title-desc">Sort: Title (Z-A)</option>
        <option value="authors">Sort: First author</option>
      </select>
    </div>
  </header>
  <main id="papers"></main>
  <template id="paper-tpl">
    <article class="paper">
      <h2 class="title"></h2>
      <p class="venue"></p>
      <p class="authors"></p>
      <p class="primary-area"></p>
      <p class="tldr"></p>
      <details class="abstract-wrap">
        <summary>Abstract</summary>
        <p class="abstract"></p>
      </details>
      <ul class="keywords"></ul>
      <p class="links"></p>
    </article>
  </template>
  <script src="/app.js"></script>
</body>
</html>
"""

STYLES_CSS = r""":root {
  --bg: #0f1115;
  --panel: #171a21;
  --border: #262b36;
  --text: #e6e8ee;
  --muted: #99a0ad;
  --accent: #6ea8ff;
  --accent-soft: #1e2a44;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}

header {
  padding: 24px 32px 16px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: rgba(15, 17, 21, 0.95);
  backdrop-filter: blur(8px);
  z-index: 5;
}

header h1 { margin: 0 0 4px; font-size: 22px; }
.meta { margin: 0 0 12px; color: var(--muted); font-size: 13px; }

.controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.controls input,
.controls select {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 14px;
}

.controls input { flex: 1; min-width: 240px; }

main {
  padding: 24px 32px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
  gap: 16px;
}

.paper {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
}

.paper .title {
  margin: 0 0 6px;
  font-size: 16px;
  line-height: 1.35;
}

.paper .venue {
  display: inline-block;
  margin: 0 0 8px;
  padding: 2px 8px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  border-radius: 12px;
}

.paper .authors,
.paper .primary-area,
.paper .tldr {
  margin: 4px 0;
  font-size: 13px;
  color: var(--muted);
}

.paper .tldr { color: var(--text); font-style: italic; }

.paper .abstract-wrap {
  margin: 8px 0;
  font-size: 13px;
}
.paper .abstract-wrap summary {
  cursor: pointer;
  color: var(--accent);
}
.paper .abstract { margin: 6px 0 0; color: var(--text); }

.paper .keywords {
  list-style: none;
  padding: 0;
  margin: 8px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.paper .keywords li {
  font-size: 11px;
  background: #1f2330;
  border: 1px solid var(--border);
  color: var(--muted);
  padding: 2px 6px;
  border-radius: 10px;
}

.paper .links { margin: 8px 0 0; font-size: 13px; }
.paper .links a { color: var(--accent); text-decoration: none; margin-right: 12px; }
.paper .links a:hover { text-decoration: underline; }

.empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--muted);
  padding: 40px 0;
}
"""

APP_JS = r"""const state = {
  papers: [],
  filtered: [],
  query: '',
  venue: '',
  sort: 'title',
};

const papersEl = document.getElementById('papers');
const metaEl = document.getElementById('meta');
const searchEl = document.getElementById('search');
const venueEl = document.getElementById('venue-filter');
const sortEl = document.getElementById('sort');
const tpl = document.getElementById('paper-tpl');

async function load() {
  const resp = await fetch('/api/papers');
  const data = await resp.json();
  state.papers = data.papers;
  metaEl.textContent =
    `${state.papers.length} papers · generated ${data.generated_at} · source: ${data.source}`;

  const venues = Array.from(new Set(state.papers.map(p => p.venue).filter(Boolean))).sort();
  for (const v of venues) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    venueEl.appendChild(opt);
  }

  apply();
}

function apply() {
  const q = state.query.toLowerCase();
  state.filtered = state.papers.filter(p => {
    if (state.venue && p.venue !== state.venue) return false;
    if (!q) return true;
    const hay = [
      p.title,
      p.tldr,
      p.abstract,
      p.primary_area,
      (p.authors || []).join(' '),
      (p.keywords || []).join(' '),
    ].join(' ').toLowerCase();
    return hay.includes(q);
  });

  const cmp = {
    'title': (a, b) => a.title.localeCompare(b.title),
    'title-desc': (a, b) => b.title.localeCompare(a.title),
    'authors': (a, b) => (a.authors[0] || '').localeCompare(b.authors[0] || ''),
  }[state.sort];
  state.filtered.sort(cmp);

  render();
}

function render() {
  papersEl.innerHTML = '';
  if (!state.filtered.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'No papers match the current filters.';
    papersEl.appendChild(empty);
    return;
  }
  for (const p of state.filtered) {
    const node = tpl.content.cloneNode(true);
    node.querySelector('.title').textContent = p.title;
    node.querySelector('.venue').textContent = p.venue;
    node.querySelector('.authors').textContent = (p.authors || []).join(', ');
    node.querySelector('.primary-area').textContent = p.primary_area
      ? `Primary area: ${p.primary_area}`
      : '';
    const tldrEl = node.querySelector('.tldr');
    if (p.tldr) {
      tldrEl.textContent = p.tldr;
    } else {
      tldrEl.remove();
    }
    const absWrap = node.querySelector('.abstract-wrap');
    if (p.abstract) {
      node.querySelector('.abstract').textContent = p.abstract;
    } else {
      absWrap.remove();
    }
    const kwUl = node.querySelector('.keywords');
    for (const k of p.keywords || []) {
      const li = document.createElement('li');
      li.textContent = k;
      kwUl.appendChild(li);
    }
    const linksEl = node.querySelector('.links');
    const links = [];
    if (p.id) links.push(`<a href="${p.id}" target="_blank" rel="noopener">OpenReview</a>`);
    if (p.pdf) links.push(`<a href="${p.pdf}" target="_blank" rel="noopener">PDF</a>`);
    if (p.supplementary_material) {
      links.push(`<a href="${p.supplementary_material}" target="_blank" rel="noopener">Supplementary</a>`);
    }
    if (p.spotlight) {
      links.push(`<a href="${p.spotlight}" target="_blank" rel="noopener">Spotlight video</a>`);
    }
    linksEl.innerHTML = links.join(' · ');
    papersEl.appendChild(node);
  }
}

searchEl.addEventListener('input', e => { state.query = e.target.value; apply(); });
venueEl.addEventListener('change', e => { state.venue = e.target.value; apply(); });
sortEl.addEventListener('change', e => { state.sort = e.target.value; apply(); });

load();
"""


def write_site(papers, site_dir):
    data_dir = os.path.join(site_dir, "data")
    public_dir = os.path.join(site_dir, "public")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(public_dir, exist_ok=True)

    payload = {
        "generated_at": _now_iso(),
        "source": os.path.relpath(CSV_PATH, PROJECT_ROOT_DIR),
        "patterns": [p.pattern for p in WORLD_MODEL_PATTERNS],
        "papers": [p.to_dict() for p in papers],
    }
    with open(os.path.join(data_dir, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(os.path.join(site_dir, "package.json"), "w", encoding="utf-8") as f:
        json.dump(PACKAGE_JSON, f, indent=2)

    with open(os.path.join(site_dir, "server.js"), "w", encoding="utf-8") as f:
        f.write(SERVER_JS)

    with open(os.path.join(public_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_HTML)
    with open(os.path.join(public_dir, "styles.css"), "w", encoding="utf-8") as f:
        f.write(STYLES_CSS)
    with open(os.path.join(public_dir, "app.js"), "w", encoding="utf-8") as f:
        f.write(APP_JS)


def _now_iso():
    import datetime as _dt
    return _dt.datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Node lifecycle
# ---------------------------------------------------------------------------

def ensure_node_modules(site_dir):
    if os.path.isdir(os.path.join(site_dir, "node_modules")):
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH. Install Node.js to continue.")
    print("Installing Node dependencies (npm install)...")
    subprocess.check_call([npm, "install", "--no-audit", "--no-fund"], cwd=site_dir)


def run_server(site_dir, port, host):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found on PATH. Install Node.js to continue.")
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = host
    print(f"Starting server: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        subprocess.run([node, "server.js"], cwd=site_dir, env=env, check=True)
    except KeyboardInterrupt:
        print("\nShutting down.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Build the site and exit without starting the Node server.",
    )
    parser.add_argument(
        "--csv",
        default=CSV_PATH,
        help="Path to the ICLR 2026 CSV (default: %(default)s).",
    )
    args = parser.parse_args()

    print(f"Loading papers from {args.csv}")
    all_papers = load_papers(args.csv)
    print(f"  loaded {len(all_papers)} papers")

    matched = filter_world_model(all_papers)
    print(f"  matched {len(matched)} world-model papers")
    if not matched:
        print("No matching papers; aborting.")
        sys.exit(1)

    print(f"Writing site to {SITE_DIR}")
    write_site(matched, SITE_DIR)

    if args.no_serve:
        print("Build complete. To serve manually:")
        print(f"  cd {SITE_DIR} && npm install && node server.js")
        return

    ensure_node_modules(SITE_DIR)
    run_server(SITE_DIR, args.port, args.host)


if __name__ == "__main__":
    main()
