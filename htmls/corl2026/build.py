"""Build htmls/corl2026/index.html from the CoRL 2026 CSV.

Standalone HTML (data embedded, no server): open index.html in a browser.
    uv run python htmls/corl2026/build.py
"""

import collections
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CSV = os.path.join(ROOT, "ConferenceTables", "robot-learning_org_CoRL_2026_Conference.csv")
FIRST_PAGE = os.path.join(HERE, "first_page.json")  # from specific_scripts/extract_first_page.py
OPENALEX = os.path.join(HERE, "openalex.json")  # from specific_scripts/fetch_corl2026_openalex.py
GITHUB = os.path.join(HERE, "github.json")  # from specific_scripts/corl2026_github.py
AFFILIATIONS = os.path.join(HERE, "affiliations.json")  # from specific_scripts/corl2026_affiliations.py
ROBOTS = os.path.join(HERE, "robots.json")  # from specific_scripts/corl2026_robots.py
TOP_COMPANIES, TOP_UNIVERSITIES, TOP_RESEARCHERS, TOP_ROBOTS, TOP_KEYWORDS = 20, 50, 50, 50, 50

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, os.path.join(ROOT, "specific_scripts"))

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CoRL 2026 Papers</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.4 system-ui, sans-serif; color: #222; background: #fff;
         height: 100vh; display: flex; flex-direction: column; }
  nav { flex: none; height: 48px; display: flex; align-items: center; gap: 8px; padding: 0 16px; border-bottom: 1px solid #ddd; }
  nav b { margin-right: 12px; }
  nav button { padding: 6px 14px; border: 1px solid #bbb; border-radius: 6px; background: #f6f6f6; cursor: pointer; }
  nav button.active { background: #2b6cb0; color: #fff; border-color: #2b6cb0; }
  nav .count { margin-left: auto; color: #666; }
  .view { display: none; flex: 1; min-height: 0; overflow: auto; }
  #filters { flex: none; display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
             padding: 8px 16px; border-bottom: 1px solid #ddd; background: #f8fafc; }
  .facet { position: relative; border: 0; padding: 0; }
  .facet > summary { list-style: none; font-weight: normal; padding: 5px 12px; border: 1px solid #bbb;
                     border-radius: 6px; background: #fff; user-select: none; }
  .facet > summary::-webkit-details-marker { display: none; }
  .facet.on > summary { border-color: #2b6cb0; background: #e8f0fb; }
  .facet .panel { position: absolute; z-index: 5; top: calc(100% + 4px); left: 0; width: max-content;
                  min-width: 260px; max-width: min(460px, 90vw); max-height: 60vh; overflow: auto;
                  background: #fff; border: 1px solid #bbb; border-radius: 6px; padding: 6px;
                  box-shadow: 0 4px 16px rgba(0,0,0,.15); }
  .facet .panel input[type=search] { width: 100%; margin-bottom: 4px; padding: 4px 6px; }
  .facet label { display: flex; gap: 6px; align-items: baseline; padding: 2px 4px; cursor: pointer; }
  .facet label:hover { background: #f0f4fa; }
  .facet label small { margin-left: auto; padding-left: 12px; color: #777; white-space: nowrap; }
  #filters select, #filters button, #filters input[type=number] { padding: 5px 8px; border: 1px solid #bbb;
                                                                 border-radius: 6px; background: #fff; }
  #filters input[type=number] { width: 70px; }
  #q { width: min(320px, 100%); padding: 5px 8px; border: 1px solid #bbb; border-radius: 6px; }
  svg { width: 14px; height: 14px; vertical-align: -2px; fill: currentColor; }
  summary a.gh { color: #24292f; margin-left: 6px; }
  summary .badges { font-weight: normal; color: #777; font-size: 12px; margin-left: 6px; }
  .view.active { display: block; }
  a { color: #2b6cb0; }

  /* table view */
  table { border-collapse: collapse; table-layout: fixed; }
  th, td { border: 1px solid #ddd; padding: 4px 6px; vertical-align: top; overflow: hidden; }
  th { position: sticky; top: 0; z-index: 1; background: #eef2f7; text-align: left;
       white-space: nowrap; text-overflow: ellipsis; cursor: grab; user-select: none; }
  th.drag-over { box-shadow: inset 3px 0 0 #2b6cb0; }
  th .resize { position: absolute; top: 0; right: 0; width: 6px; height: 100%; cursor: col-resize; }
  th .resize:hover { background: #2b6cb0; }
  td div { max-height: 4.2em; overflow: hidden; overflow-wrap: anywhere; }  /* ~3 lines */
  tr:nth-child(even) td { background: #fafafa; }

  /* papers view */
  #papers { padding: 8px 16px; }
  details { border-bottom: 1px solid #eee; padding: 6px 0; }
  summary { cursor: pointer; font-weight: 600; }
  summary .kw { font-weight: normal; color: #555; }
  dl { display: grid; grid-template-columns: 180px 1fr; gap: 4px 12px; margin: 8px 0 4px 18px; }
  dt { color: #666; }
  dd { margin: 0; overflow-wrap: anywhere; }
  /* justified collage: row height follows the viewport, images grow by aspect ratio to fill each row */
  .collage { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px 18px; }
  .collage::after { content: ''; flex-grow: 999; }
  .collage a { display: block; }
  .collage img { display: block; width: 100%; height: auto; margin: 0; max-width: none; border: 1px solid #ddd; }
  details details summary { font-weight: normal; color: #2b6cb0; margin-left: 18px; }
  details > img { display: block; max-width: min(100%, 900px); margin: 8px 0 4px 18px; }
</style>
</head>
<body>
<nav>
  <b>CoRL 2026</b>
  <button data-view="table">Table</button>
  <button data-view="papers">Papers</button>
  <span class="count"></span>
</nav>
<div id="filters">
  <input type="search" id="q" placeholder="🔍 search titles, authors, abstracts, keywords…">
  <details class="facet" data-key="p"><summary>🏷️ Primary keyword</summary><div class="panel"></div></details>
  <details class="facet" data-key="s"><summary>🔖 Secondary keyword</summary><div class="panel"></div></details>
  <details class="facet" data-key="b"><summary>🤖 Robots</summary><div class="panel"></div></details>
  <details class="facet" data-key="c"><summary>🏢 Companies</summary><div class="panel"></div></details>
  <details class="facet" data-key="u"><summary>🎓 Universities</summary><div class="panel"></div></details>
  <details class="facet" data-key="r"><summary>🧑‍🔬 Researchers</summary><div class="panel"></div></details>
  <select id="ghF" title="Papers whose PDF links a GitHub repo">
    <option value="">💻 GitHub: all</option>
    <option value="y">💻 GitHub</option>
    <option value="n">🚫 no GitHub</option>
  </select>
  <label title="Highest OpenAlex h-index among the paper's authors">🏅 min author h-index
    <input type="number" id="minH" min="0" step="5" placeholder="0"></label>
  <label title="OpenAlex citations of the paper itself">📈 min citations
    <input type="number" id="minC" min="0" step="1" placeholder="0"></label>
  <select id="sort">
    <option value="">🔀 Sort: default</option>
    <option value="h">🏅 Sort: author h-index</option>
    <option value="cites">📈 Sort: citations</option>
    <option value="az">🔤 Sort: title A–Z</option>
  </select>
  <button id="clear">✖️ Clear</button>
</div>
<div id="table" class="view"><table><colgroup></colgroup><thead><tr></tr></thead><tbody></tbody></table></div>
<div id="papers" class="view"></div>
<svg hidden><symbol id="gh" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></symbol></svg>
<script id="data" type="application/json">__DATA__</script>
<script>
const {columns, rows, firstPage, meta, facets} = JSON.parse(document.getElementById('data').textContent);

function cellContent(v) {
  if (/^https:\/\/github\.com\/\S+ /.test(v)) {  // several space-separated repos
    const f = document.createDocumentFragment();
    v.split(' ').forEach((u, i) => { if (i) f.append(document.createElement('br')); f.append(cellContent(u)); });
    return f;
  }
  if (v.startsWith('pdfs/')) {  // local copy: open in Preview via OpenPDF.app (specific_scripts/install_openpdf_handler.sh)
    const a = document.createElement('a'), path = new URL(v.split('/').map(encodeURIComponent).join('/'), location.href).pathname;
    a.href = 'openpdf://' + path; a.textContent = '🖊️ ' + v; a.title = 'Open in Preview';
    const web = document.createElement('a');
    web.href = encodeURI(v); web.target = '_blank'; web.textContent = ' 🌐'; web.title = 'Open in browser';
    const f = document.createDocumentFragment(); f.append(a, web);
    return f;
  }
  if (/^https?:\/\//.test(v)) {
    const a = document.createElement('a');
    a.href = encodeURI(v); a.target = '_blank'; a.textContent = v;
    return a;
  }
  return document.createTextNode(v);
}

// ---- view switching ----
const buttons = document.querySelectorAll('nav button');
function show(view) {
  buttons.forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === view));
}
buttons.forEach(b => b.onclick = () => show(b.dataset.view));

// ---- table view ----
let order = columns.map((_, i) => i);
const width = columns.map(c => ({title: 300, abstract: 500, authors: 220}[c] || 140));
const table = document.querySelector('#table table');
let dragFrom = null, trs = [], dets = [];

function renderTable() {
  table.querySelector('colgroup').replaceChildren(...order.map(i => {
    const col = document.createElement('col'); col.style.width = width[i] + 'px'; return col;
  }));
  table.style.width = order.reduce((s, i) => s + width[i], 0) + 'px';

  table.querySelector('thead tr').replaceChildren(...order.map((ci, pos) => {
    const th = document.createElement('th');
    th.textContent = columns[ci]; th.title = columns[ci]; th.draggable = true;
    th.ondragstart = e => { dragFrom = pos; e.dataTransfer.effectAllowed = 'move'; };
    th.ondragover = e => { e.preventDefault(); th.classList.add('drag-over'); };
    th.ondragleave = () => th.classList.remove('drag-over');
    th.ondrop = e => {
      e.preventDefault();
      if (dragFrom === null || dragFrom === pos) return renderTable();
      order.splice(pos, 0, order.splice(dragFrom, 1)[0]);
      dragFrom = null;
      renderTable();
    };
    const handle = document.createElement('span');
    handle.className = 'resize';
    handle.onmousedown = e => {
      e.preventDefault(); e.stopPropagation();  // preventDefault also blocks the column drag
      const startX = e.clientX, startW = width[ci], col = table.querySelectorAll('col')[pos];
      const others = table.offsetWidth - startW;
      const move = ev => {
        width[ci] = Math.max(40, startW + ev.clientX - startX);
        col.style.width = width[ci] + 'px';
        table.style.width = others + width[ci] + 'px';
      };
      const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
      addEventListener('mousemove', move); addEventListener('mouseup', up);
    };
    th.appendChild(handle);
    return th;
  }));

  trs = rows.map(r => {
    const tr = document.createElement('tr');
    for (const ci of order) {
      const td = document.createElement('td'), div = document.createElement('div');
      div.appendChild(cellContent(r[ci])); td.title = r[ci];
      td.appendChild(div); tr.appendChild(td);
    }
    return tr;
  });
  applyFilters();
}

// ---- papers view (native <details> dropdowns) ----
const titleIdx = columns.indexOf('title'), idIdx = columns.indexOf('id'), ghIdx = columns.indexOf('💻 github');
const kwIdx = ['primary_keyword', 'secondary_keyword', 'free_keyword_1', 'free_keyword_2']
  .map(c => columns.indexOf(c)).filter(i => i >= 0);
dets = rows.map((r, ri) => {
  const d = document.createElement('details'), s = document.createElement('summary');
  s.textContent = r[titleIdx];
  const kws = kwIdx.map(i => r[i]).filter(Boolean);
  if (kws.length) {
    const k = document.createElement('span');
    k.className = 'kw'; k.textContent = ' [' + kws.join(', ') + ']';
    s.append(k);
  }
  if (r[ghIdx]) {  // GitHub sign linking the first repo; preventDefault so the click doesn't toggle the dropdown
    const a = document.createElement('a'), url = r[ghIdx].split(' ')[0];
    a.className = 'gh'; a.href = url; a.title = r[ghIdx].replaceAll(' ', '\n');
    a.innerHTML = '<svg><use href="#gh"/></svg>';
    a.onclick = e => { e.preventDefault(); open(url, '_blank'); };
    s.append(a);
  }
  const m = meta[ri], b = [];
  if (m.cites) b.push(`📈 ${m.cites}`);
  if (m.h != null) b.push(`🏅 h ${m.h}`);
  if (m.b.length) b.push('🤖 ' + m.b.join(', '));
  if (m.c.length) b.push('🏢 ' + m.c.join(', '));
  if (b.length) { const e = document.createElement('span'); e.className = 'badges'; e.textContent = b.join('  ·  '); s.append(e); }
  const dl = document.createElement('dl');
  columns.forEach((c, i) => {
    if (i === titleIdx || !r[i]) return;
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = c; dd.appendChild(cellContent(r[i]));
    dl.append(dt, dd);
  });
  d.append(s, dl);
  const fig = (firstPage[r[idIdx].split('id=').pop()] || {}).figure;
  if (fig) { const img = document.createElement('img'); img.src = fig; img.loading = 'lazy'; d.append(img); }
  const figs = (firstPage[r[idIdx].split('id=').pop()] || {}).figures || [];
  if (figs.length) {
    const all = document.createElement('details'), as = document.createElement('summary');
    as.textContent = `All figures (${figs.length})`;
    const box = document.createElement('div'); box.className = 'collage';
    all.append(as, box);
    all.ontoggle = () => {  // build on first open so 687 papers don't load thousands of images
      if (!all.open || box.childElementCount) return;
      box.append(...figs.map(f => {
        const a = document.createElement('a'), img = document.createElement('img'), ar = f.w / f.h;
        a.href = encodeURI(f.src); a.target = '_blank'; a.title = `Figure ${f.n} (page ${f.page})`;
        a.style.flex = `${ar} 1 calc(${ar} * clamp(140px, 28vh, 360px))`;
        img.src = encodeURI(f.src);
        a.append(img);
        return a;
      }));
    };
    d.append(all);
  }
  return d;
});

// ---- filters ----
const picked = {p: new Set(), s: new Set(), b: new Set(), c: new Set(), u: new Set(), r: new Set()};
document.querySelectorAll('.facet').forEach(fd => {
  const key = fd.dataset.key, panel = fd.querySelector('.panel'), label = fd.querySelector('summary');
  const base = label.textContent;
  const search = document.createElement('input');
  search.type = 'search'; search.placeholder = '🔍 search…';
  const items = facets[key].map(f => {
    const l = document.createElement('label'), cb = document.createElement('input'), sm = document.createElement('small');
    cb.type = 'checkbox'; cb.value = f.id;
    sm.textContent = f.note;
    l.append(cb, document.createTextNode(f.name), sm);
    cb.onchange = () => {
      cb.checked ? picked[key].add(f.id) : picked[key].delete(f.id);
      label.textContent = base + (picked[key].size ? ` (${picked[key].size})` : '');
      fd.classList.toggle('on', picked[key].size > 0);
      applyFilters();
    };
    return l;
  });
  search.oninput = () => items.forEach(l => l.hidden = !l.textContent.toLowerCase().includes(search.value.toLowerCase()));
  panel.append(search, ...items);
  fd.ontoggle = () => fd.open && document.querySelectorAll('.facet').forEach(o => o !== fd && (o.open = false));
});
addEventListener('click', e => { if (!e.target.closest('.facet')) document.querySelectorAll('.facet').forEach(f => f.open = false); });
['q', 'minH', 'minC', 'sort', 'ghF'].forEach(id => document.getElementById(id).oninput = applyFilters);
const haystack = rows.map(r => r.join(' ').toLowerCase());  // every column, incl. companies/universities
document.getElementById('clear').onclick = () => {
  Object.values(picked).forEach(p => p.clear());
  document.querySelectorAll('.facet').forEach(fd => {
    fd.classList.remove('on'); fd.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = false);
    const l = fd.querySelector('summary'); l.textContent = l.textContent.replace(/ \(\d+\)$/, '');
  });
  ['q', 'minH', 'minC', 'sort', 'ghF'].forEach(id => document.getElementById(id).value = '');
  applyFilters();
};

function applyFilters() {
  if (!dets.length) return;  // first renderTable() runs before the papers view exists
  const minH = +document.getElementById('minH').value || 0, minC = +document.getElementById('minC').value || 0;
  const sort = document.getElementById('sort').value;
  const hit = (key, ri) => !picked[key].size || meta[ri][key].some(x => picked[key].has(x));
  const terms = document.getElementById('q').value.toLowerCase().split(/\s+/).filter(Boolean);  // all must match
  const ghSel = document.getElementById('ghF').value, gh = i => !ghSel || (ghSel === 'y') === !!rows[i][ghIdx];
  let idx = rows.map((_, i) => i).filter(i => gh(i) &&
    terms.every(t => haystack[i].includes(t)) &&
    hit('p', i) && hit('s', i) && hit('b', i) && hit('c', i) && hit('u', i) && hit('r', i) && (meta[i].h || 0) >= minH && (meta[i].cites || 0) >= minC);
  if (sort === 'az') idx.sort((a, b) => rows[a][titleIdx].localeCompare(rows[b][titleIdx], undefined, {sensitivity: 'base'}));
  else if (sort) idx.sort((a, b) => (meta[b][sort] || 0) - (meta[a][sort] || 0));
  table.querySelector('tbody').replaceChildren(...idx.map(i => trs[i]));
  document.getElementById('papers').replaceChildren(...idx.map(i => dets[i]));
  document.querySelector('.count').textContent = idx.length === rows.length
    ? `📄 ${rows.length} papers` : `📄 ${idx.length} / ${rows.length} papers`;
}

renderTable();
show('papers');
</script>
</body>
</html>
"""


def clean_inst(name):
    """"Google (United States)" -> "Google"; OpenAlex suffixes countries on company names."""
    return re.sub(r"\s*\([^)]*\)$", "", name).strip()


def openalex_meta(rows, columns):
    """Per-row {c: companies, u: universities, r: top-researcher ids, cites, h} and the filter option lists."""
    from corl2026_affiliations import COMPANY_RES
    oa = json.load(open(OPENALEX)) if os.path.exists(OPENALEX) else {"works": {}, "authors": {}}
    robots = json.load(open(ROBOTS)) if os.path.exists(ROBOTS) else {}
    pdf_aff = json.load(open(AFFILIATIONS))["papers"] if os.path.exists(AFFILIATIONS) else {}
    authors = oa["authors"]
    id_col = columns.index("id")
    kw_cols = {k: columns.index(c) for k, c in [("p", "primary_keyword"), ("s", "secondary_keyword")] if c in columns}
    meta = []
    for r in rows:
        pid = r[id_col].split("id=")[-1]
        w = oa["works"].get(pid) or {"authors": [], "cites": None}
        aff = pdf_aff.get(pid, {"companies": [], "universities": []})
        insts = [(clean_inst(i["name"]), i["type"]) for a in w["authors"] for i in a["institutions"]]
        hs = [authors[a["id"]]["h_index"] for a in w["authors"] if a["id"] in authors and authors[a["id"]]["h_index"] is not None]
        meta.append({
            # PDF page-1 affiliations, plus OpenAlex's (its odd company names only when they map to a known one)
            "c": sorted(set(aff["companies"]) | {c for n, t in insts if t == "company"
                                                 for c, rx in COMPANY_RES.items() if rx.search(n)}),
            "u": sorted({re.sub(r"^The ", "", n) for n in  # "The University of Tokyo" == "University of Tokyo"
                         set(aff["universities"]) | {n for n, t in insts if t == "education"}}),
            "b": robots.get(pid, []),
            **{k: [r[i]] if r[i] else [] for k, i in kw_cols.items()},
            "r": sorted({a["id"] for a in w["authors"] if a["id"] in authors}),
            "cites": w["cites"],
            "h": max(hs) if hs else None,
        })

    def top(key, n):
        counts = collections.Counter(x for m in meta for x in m[key])
        return [{"id": k, "name": k, "note": f"{v} 📄"} for k, v in counts.most_common(n)]

    papers_of = collections.Counter(a for m in meta for a in m["r"])
    # ponytail: ranked by OpenAlex h-index; its author disambiguation can merge namesakes and inflate a few
    ranked = sorted(papers_of, key=lambda a: -(authors[a]["h_index"] or 0))[:TOP_RESEARCHERS]
    researchers = [{"id": a, "name": authors[a]["name"],
                    "note": f"🏅 h {authors[a]['h_index']} · 📈 {authors[a]['cites']:,} · {papers_of[a]} 📄"}
                   for a in ranked]
    top_ids = {a["id"] for a in researchers}
    for m in meta:
        m["r"] = [a for a in m["r"] if a in top_ids]
    return meta, {"c": top("c", TOP_COMPANIES), "u": top("u", TOP_UNIVERSITIES), "r": researchers, "b": top("b", TOP_ROBOTS),
                  **{k: top(k, TOP_KEYWORDS) for k in kw_cols}}


def main():
    with open(CSV, newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        columns = next(reader)
        rows = [r + [""] * (len(columns) - len(r)) for r in reader if any(r)]
    local = {os.path.basename(p).split("_", 1)[0]: os.path.relpath(p, HERE) for p in glob.glob(os.path.join(HERE, "pdfs", "*.pdf"))}
    columns.insert(columns.index("pdf") + 1, "local_pdf")
    for r in rows:
        r.insert(columns.index("local_pdf"), local.get(r[0].split("id=")[-1], ""))
    github = json.load(open(GITHUB)) if os.path.exists(GITHUB) else {}
    columns.insert(columns.index("local_pdf") + 1, "💻 github")
    for r in rows:
        r.insert(columns.index("💻 github"), " ".join(github.get(r[0].split("id=")[-1], [])))
    keep = [i for i in range(len(columns)) if any(r[i] for r in rows)]  # drop all-empty columns
    columns = [columns[i] for i in keep]
    rows = [[r[i] for i in keep] for r in rows]
    first_page = json.load(open(FIRST_PAGE)) if os.path.exists(FIRST_PAGE) else {}
    meta, facets = openalex_meta(rows, columns)
    for name, key in [("🤖 robots", "b"), ("🏢 companies", "c"), ("🎓 universities", "u")]:
        columns.append(name)
        for r, m in zip(rows, meta):
            r.append("; ".join(m[key]))
    columns += ["📈 citations", "🏅 max author h-index"]
    for r, m in zip(rows, meta):
        r += ["" if m["cites"] is None else str(m["cites"]), "" if m["h"] is None else str(m["h"])]
    data = json.dumps({"columns": columns, "rows": rows, "firstPage": first_page, "meta": meta, "facets": facets}, ensure_ascii=False).replace("</", "<\\/")
    out = os.path.join(HERE, "index.html")
    with open(out, "w") as f:
        f.write(HTML.replace("__DATA__", data))
    print(f"wrote {out} ({len(rows)} papers, {len(columns)} columns)")


if __name__ == "__main__":
    main()
