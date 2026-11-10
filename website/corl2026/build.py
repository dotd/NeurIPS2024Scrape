"""Build website/corl2026/index.html from the CoRL 2026 CSV.

Standalone HTML (data embedded, no server): open index.html in a browser.
    uv run python website/corl2026/build.py

build() makes the same page for any folder laid out like this one (pdfs/, figs/, first_page.json, robots.json, …);
website/papers/papers.py uses it for the papers you add yourself.
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
PRESENTATION = {"Oral": "🎤 Oral", "Spotlight": "✨ Spotlight", "Poster": "🖼️ Poster"}  # last word of venue
# files in a site folder (here = website/<site>/):
#   first_page.json  specific_scripts/extract_first_page.py    openalex.json    specific_scripts/fetch_corl2026_openalex.py
#   github.json      specific_scripts/corl2026_github.py       affiliations.json specific_scripts/corl2026_affiliations.py
#   robots.json      specific_scripts/corl2026_robots.py       backbones.json   specific_scripts/corl2026_backbones.py
#   summaries.json, ratings.json, links.json, htmls_claude/, htmls_python/   website/serve.py (buttons on the page)
#   schedule.json    specific_scripts/corl2026_schedule.py      (talk + poster session of each paper)
#   drive_movies.json specific_scripts/corl2026_drive_movies.py (Google Drive copies of the movies)
#   arxiv.json, slide_summaries.json  specific_scripts/corl2026_whatsapp.py (the WhatsApp message)
#   movies/paper_movies/<id>_<title>[_N].<ext>                 specific_scripts/corl2026_sort_movies.py
HTML_KINDS = ("claude", "python")  # htmls_<kind>/<id>_<title>/index.html
TOP_COMPANIES, TOP_UNIVERSITIES, TOP_RESEARCHERS, TOP_ROBOTS, TOP_KEYWORDS = 20, 50, 50, 50, 50

csv.field_size_limit(sys.maxsize)
sys.path.insert(0, os.path.join(ROOT, "specific_scripts"))

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.4 system-ui, sans-serif; color: #222; background: #fff;
         height: 100vh; display: flex; flex-direction: column; }
  nav { flex: none; height: 48px; display: flex; align-items: center; gap: 8px; padding: 0 16px; border-bottom: 1px solid #ddd; }
  nav b { margin-right: 12px; }
  nav button { padding: 6px 14px; border: 1px solid #bbb; border-radius: 6px; background: #f6f6f6; cursor: pointer; }
  nav button.active { background: #2b6cb0; color: #fff; border-color: #2b6cb0; }
  nav .stats { margin-left: 16px; color: #666; font-size: 13px; }
  nav .count { margin-left: auto; color: #666; }
  nav #clear { background: #fff; }
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
  .sumbox { margin: 8px 0; }
  .sumbox button { padding: 3px 10px; border: 1px solid #bbb; border-radius: 6px; background: #fff; cursor: pointer; }
  .htmlrow { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin: 0 0 8px; }
  .htmlbox button { padding: 3px 10px; border: 1px solid #bbb; border-radius: 6px; background: #fff; cursor: pointer; }
  .sumbox .erase { margin-top: 6px; color: #b42318; }
  .sumbox details > div { white-space: pre-wrap; background: #f6f8fb; border-left: 3px solid #2b6cb0;
                          padding: 8px 12px; margin-top: 4px; max-width: 900px; }
  summary .stars { margin-left: 8px; color: #e0a100; font-size: 15px; letter-spacing: 1px; cursor: pointer; }
  summary .stars span:hover { color: #b47f00; }
  summary .sumflag { margin-left: 6px; font-weight: normal; font-size: 12px; color: #777; }
  summary .badges { font-weight: normal; color: #777; font-size: 12px; margin-left: 6px; }
  .view.active { display: block; }
  .btbar { position: sticky; top: 0; z-index: 4; background: #fff; padding: 8px 0; display: flex; gap: 8px; align-items: center; }
  .btbar select { padding: 5px 8px; border: 1px solid #bbb; border-radius: 6px; font-size: 14px; }
  .btnum { color: #2b6cb0; font-weight: bold; }
  .rd { padding: 6px 0; border-bottom: 1px solid #eee; }
  .wa { margin: 4px 0; }
  .wa > button, .wa .panel button { padding: 3px 10px; border: 1px solid #bbb; border-radius: 6px; background: #f7f7f7; cursor: pointer; }
  .wa .panel { margin-top: 4px; }
  .wa textarea { display: block; width: min(100%, 640px); font: 13px/1.4 system-ui, sans-serif; margin-bottom: 4px; }
  .rd .rdtitle { font-weight: bold; }
  .rd .rdtitle a { font-weight: normal; margin-left: 8px; }
  .drive { margin: 4px 0; font-size: 13px; }
  .nextmov { margin: 4px 0; padding: 3px 10px; border: 1px solid #bbb; border-radius: 6px; background: #f7f7f7; cursor: pointer; }
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
  .movies { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px 18px; }
  .movies video, .movies img { width: min(100%, 640px); background: #000; }
  .movies iframe { width: min(100%, 640px); aspect-ratio: 16 / 9; border: 0; background: #000; }
  details > img { display: block; max-width: min(100%, 900px); margin: 8px 0 4px 18px; }
</style>
</head>
<body>
<nav>
  <select id="site" title="Go to another paper browser" style="font-weight:bold;padding:5px 8px;border:1px solid #bbb;border-radius:6px">
    <option data-dir="corl2026" value="/Corl2026/">CoRL 2026</option>
    <option data-dir="papers" value="/Papers/">My papers</option>
  </select>
  <script>  // ponytail: sites listed by hand, same as SITES in serve.py
  { const sel = document.getElementById('site');
    sel.value = [...sel.options].find(o => o.textContent === '__TITLE__')?.value ?? sel.value;
    sel.onchange = () => location.href = location.protocol.startsWith('http') ? sel.value
      : '../' + sel.selectedOptions[0].dataset.dir + '/index.html'; }  // opened as a file: the sibling folder
  </script>
  <button data-view="papers">Papers</button>
  <button data-view="table">Table</button>
  <button data-view="bytime">🕒 By time</button>
  <button data-view="random">🎲 Random</button>
  <span class="stats"></span>
  <span class="count"></span>
  <button id="clear" title="Clear every filter, search and sort">↺ Reset filters</button>
</nav>
__ADD__
<div id="filters">
  <input type="search" id="q" placeholder="🔍 search titles, authors, abstracts, keywords…">
  <details class="facet" data-key="d"><summary>📅 Session</summary><div class="panel"></div></details>
  <details class="facet" data-key="t"><summary>🎤 Oral / Spotlight / Poster</summary><div class="panel"></div></details>
  <details class="facet" data-key="p"><summary>🏷️ Primary keyword</summary><div class="panel"></div></details>
  <details class="facet" data-key="s"><summary>🔖 Secondary keyword</summary><div class="panel"></div></details>
  <details class="facet" data-key="k"><summary>🏷️ Keywords</summary><div class="panel"></div></details>
  <details class="facet" data-key="b"><summary>🤖 Robots</summary><div class="panel"></div></details>
  <details class="facet" data-key="m"><summary>🧠 Backbones</summary><div class="panel"></div></details>
  <details class="facet" data-key="c"><summary>🏢 Companies</summary><div class="panel"></div></details>
  <details class="facet" data-key="u"><summary>🎓 Universities</summary><div class="panel"></div></details>
  <details class="facet" data-key="r"><summary>🧑‍🔬 Researchers</summary><div class="panel"></div></details>
  <select id="rateHas" title="Whether you rated the paper">
    <option value="">⭐ Rated: all</option>
    <option value="y">⭐ with rating</option>
    <option value="n">☆ without rating</option>
  </select>
  <select id="rateF" title="Your star rating (only rated papers pass)">
    <option value="">⭐ Rating: all</option>
    <option value="g1">⭐ above 1</option><option value="g2">⭐ above 2</option>
    <option value="g3">⭐ above 3</option><option value="g4">⭐ above 4 (5 only)</option>
    <option value="l5">⭐ below 5</option><option value="l4">⭐ below 4</option>
    <option value="l3">⭐ below 3</option><option value="l2">⭐ below 2 (1 only)</option>
  </select>
  <select id="sumF" title="Papers with a Claude summary">
    <option value="">📝 Summary: all</option>
    <option value="y">📝 summarized</option>
    <option value="n">⬜ not summarized</option>
  </select>
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
</div>
<div id="table" class="view"><table><colgroup></colgroup><thead><tr></tr></thead><tbody></tbody></table></div>
<div id="papers" class="view"></div>
<div id="bytime" class="view"><div class="btbar"><button id="btPrev" title="Previous session">◀</button>
  <select id="btSession"></select><button id="btNext" title="Next session">▶</button><span id="btCount"></span></div>
  <div id="btList"></div></div>
<div id="random" class="view"><div class="btbar"><span id="rdCount"></span>
  <a href="#" id="rdReset" title="Shuffle again; the movies you watched come back">🔀 Reset random</a></div>
  <div id="rdList"></div></div>
<svg hidden><symbol id="gh" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></symbol></svg>
<script id="data" type="application/json">__DATA__</script>
<script>
const {columns, rows, firstPage, meta, facets, summaries, ratings, links, htmlv, movies, here, store, schedule, drive, arxiv, shortSum} = JSON.parse(document.getElementById('data').textContent);

function cellContent(v) {
  if (/^https:\/\/github\.com\/\S+ /.test(v)) {  // several space-separated repos
    const f = document.createDocumentFragment();
    v.split(' ').forEach((u, i) => { if (i) f.append(document.createElement('br')); f.append(cellContent(u)); });
    return f;
  }
  if (v.startsWith('pdfs/')) {  // local copy: open in Preview via OpenPDF.app (specific_scripts/install_openpdf_handler.sh)
    const a = document.createElement('a'), path = (here + '/' + v).split('/').map(encodeURIComponent).join('/');
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
const buttons = document.querySelectorAll('nav button[data-view]');
function show(view) {
  buttons.forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === view));
  if (view === 'bytime') renderByTime();
  if (view === 'random' && !rdList.childElementCount) renderRandom();
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

// ---- Summarize button: POST /summarize/<id> to serve.py (holds the Claude API key), result in a dropdown ----
if (location.protocol.startsWith('http'))  // pick up summaries / ratings made since index.html was built
  [['summaries.json', summaries], ['ratings.json', ratings], ['links.json', links]].forEach(([f, o]) =>
    fetch(f).then(r => r.ok ? r.json() : {}).then(s => { Object.assign(o, s); updateStats(); }).catch(() => {}));

// ---- star rating on the summary line: click a star to rate, click the same star again to clear ----
// Served (serve.py): saved to ratings.json. Opened as a file: kept in localStorage ("pending", 0 = cleared)
// and pushed to the server the next time the page is opened through serve.py.
const SERVED = location.protocol.startsWith('http');
let pending = {};
try { pending = JSON.parse(localStorage.getItem(store + 'Ratings') || '{}'); } catch (e) {}
const setRating = (pid, v) => { if (v) ratings[pid] = v; else delete ratings[pid]; };
const refilter = () => { if (dets.length) applyFilters(); else updateStats(); };  // so the rating / summary filters apply at once
Object.entries(pending).forEach(([pid, v]) => {
  setRating(pid, v);
  if (SERVED) fetch('rate/' + pid, {method: 'POST', body: String(v)}).then(r => {
    if (r.ok) { delete pending[pid]; try { localStorage.setItem(store + 'Ratings', JSON.stringify(pending)); } catch (e) {} }
  });
});
function stars(pid) {
  const span = document.createElement('span');
  span.className = 'stars'; span.title = 'Your rating (click the same star again to clear)';
  const paint = () => [...span.children].forEach((st, i) => st.textContent = i < (ratings[pid] || 0) ? '★' : '☆');
  for (let n = 1; n <= 5; n++) {
    const st = document.createElement('span');
    st.onclick = async e => {
      e.preventDefault();  // don't toggle the paper's dropdown
      const prev = ratings[pid] || 0, v = prev === n ? 0 : n;
      setRating(pid, v); paint(); refilter();
      if (!SERVED) {
        pending[pid] = v;
        try { localStorage.setItem(store + 'Ratings', JSON.stringify(pending)); } catch (e) {}
        return;
      }
      const res = await fetch('rate/' + pid, {method: 'POST', body: String(v)}).catch(() => null);
      if (!res || !res.ok) { span.title = '⚠️ rating not saved (is serve.py running?)'; setRating(pid, prev); paint(); refilter(); }
    };
    span.append(st);
  }
  paint();
  return span;
}
// a summary is {text, cost, input_tokens, output_tokens} (older ones are a plain string)
const sumText = x => typeof x === 'string' ? x : x.text;
const sumTitle = x => '📝 Summary (Claude Opus' + (x.cost != null
  ? ` · $${x.cost.toFixed(3)} · ${x.input_tokens.toLocaleString()} in / ${x.output_tokens.toLocaleString()} out tokens)` : ')');
function summaryBox(pid, flag) {  // flag: the 📝 marker on the paper's summary line, shown while a summary exists
  const box = document.createElement('div');
  box.className = 'sumbox';
  const needServer = () => location.protocol.startsWith('http') ? '' :
    'run: uv run python website/serve.py, then open this page through http://127.0.0.1:8026/';
  const empty = () => {  // no summary yet: just the button
    const btn = document.createElement('button');
    btn.textContent = '📝 Summarize';
    btn.onclick = async () => {
      if (needServer()) return btn.textContent = '📝 Summarize (' + needServer() + ')';
      btn.disabled = true; btn.textContent = '⏳ Summarizing with Claude… (~30 s)';
      try {
        const res = await fetch('summarize/' + pid, {method: 'POST'}), j = await res.json();
        if (!res.ok) throw new Error(j.error);
        summaries[pid] = j.summary; filled(true); refilter();
      } catch (e) { btn.disabled = false; btn.textContent = '⚠️ ' + e.message + ' (retry)'; }
    };
    box.replaceChildren(btn);
  };
  const filled = open => {  // summary dropdown, "Erase summary" at its bottom
    const sd = document.createElement('details'), ss = document.createElement('summary'),
          body = document.createElement('div'), erase = document.createElement('button');
    ss.textContent = sumTitle(summaries[pid]); body.textContent = sumText(summaries[pid]); sd.open = open;
    const cost = summaries[pid].cost;
    flag.hidden = false; flag.title = 'Has a Claude summary';
    flag.textContent = '📝' + (cost != null ? ` $${cost.toFixed(3)}` : '');
    erase.className = 'erase'; erase.textContent = '🗑️ Erase summary';
    erase.onclick = async () => {
      if (needServer()) return erase.textContent = '🗑️ Erase summary (' + needServer() + ')';
      if (!confirm('Erase the summary of this paper?')) return;
      const res = await fetch('summarize/' + pid, {method: 'DELETE'});
      if (!res.ok) return erase.textContent = '⚠️ erase failed (retry)';
      delete summaries[pid]; flag.hidden = true; empty(); refilter();
    };
    sd.append(ss, body, erase); box.replaceChildren(sd);
  };
  summaries[pid] ? filled(false) : empty();
  return box;
}

// ---- HTML versions: POST /html_<kind>/<id> to serve.py, then a link that opens it in a new tab ----
const HTML_KINDS = {
  claude: {make: '🌐 Make HTML with Claude', open: '🌐 Open HTML (Claude)', busy: '⏳ Converting the whole paper with Claude… (several minutes)'},
  python: {make: '🐍 Make HTML with python', open: '🐍 Open HTML (python)', busy: '⏳ Converting with python… (~20 s)'},
  claude2: {open: '✂️ Open HTML Claude #2'},  // made by the Condense button on the Claude HTML page
};
function htmlBox(pid, kind) {
  const box = document.createElement('span'), k = HTML_KINDS[kind];
  box.className = 'htmlbox';
  const link = () => {
    const a = document.createElement('a'), v = htmlv[kind][pid];
    a.href = v.path.split('/').map(encodeURIComponent).join('/'); a.target = '_blank';
    a.textContent = k.open + (v.cost != null ? ` ($${v.cost.toFixed(2)})` : '');
    box.replaceChildren(a);
  };
  if (htmlv[kind][pid]) { link(); return box; }
  if (!k.make) return box;
  const btn = document.createElement('button');
  btn.textContent = k.make;
  btn.onclick = async () => {
    if (!location.protocol.startsWith('http'))
      return btn.textContent = k.make + ' (run: uv run python website/serve.py, then open this page through http://127.0.0.1:8026/)';
    btn.disabled = true; btn.textContent = k.busy;
    try {
      const res = await fetch(`html_${kind}/${pid}`, {method: 'POST'}), j = await res.json();
      if (!res.ok) throw new Error(j.error);
      htmlv[kind][pid] = j; link(); updateStats();
    } catch (e) { btn.disabled = false; btn.textContent = '⚠️ ' + e.message + ' (retry)'; }
  };
  box.append(btn);
  return box;
}
// ---- Find link to paper: POST /find_link/<id>, Claude + web search for a non-OpenReview copy (arXiv preferred) ----
function linkBox(pid) {
  const box = document.createElement('span');
  box.className = 'htmlbox';
  const link = () => {
    const a = document.createElement('a'), v = links[pid];
    a.href = v.url; a.target = '_blank'; a.textContent = '🔗 ' + v.url.replace(/^https?:\/\//, '');
    a.title = `Found by Claude ($${v.cost.toFixed(3)}, ${v.searches} web searches)`;
    box.replaceChildren(a);
  };
  if (links[pid]?.url) { link(); return box; }
  const btn = document.createElement('button');
  btn.textContent = links[pid] ? '🔗 Find link to paper (none found last time)' : '🔗 Find link to paper';
  btn.onclick = async () => {
    if (!location.protocol.startsWith('http'))
      return btn.textContent = '🔗 Find link to paper (run: uv run python website/serve.py, then open this page through http://127.0.0.1:8026/)';
    btn.disabled = true; btn.textContent = '⏳ Searching the web with Claude… (~30 s)';
    try {
      const res = await fetch('find_link/' + pid, {method: 'POST'}), j = await res.json();
      if (!res.ok) throw new Error(j.error);
      links[pid] = j; updateStats();
      if (j.url) return link();
      btn.disabled = false; btn.textContent = '🔗 No public copy found (retry)';
    } catch (e) { btn.disabled = false; btn.textContent = '⚠️ ' + e.message + ' (retry)'; }
  };
  box.append(btn);
  return box;
}
function htmlBoxes(pid) {
  const row = document.createElement('div');
  row.className = 'htmlrow';
  row.append(htmlBox(pid, 'claude'), htmlBox(pid, 'claude2'), htmlBox(pid, 'python'), linkBox(pid));
  return row;
}

// ---- papers view (native <details> dropdowns) ----
const titleIdx = columns.indexOf('title'), idIdx = columns.indexOf('id'), ghIdx = columns.indexOf('💻 github');
const kwIdx = ['primary_keyword', 'secondary_keyword', 'free_keyword_1', 'free_keyword_2', '🏷️ keywords']
  .map(c => columns.indexOf(c)).filter(i => i >= 0);
// ---- WhatsApp message: bold title, CoRL 2026, talk / poster time and place, the movie on GitHub Pages, arXiv, OpenReview,
// GitHub, a one-slide summary ----
const WA = store === 'corl';  // ponytail: only the CoRL site is on GitHub Pages; "your papers" has no public page
const PAGES = 'https://dotd.github.io/corl2026/';
const gist = x => ((x && sumText(x) || '').match(/^Gist:\s*([\s\S]*?)(?:\n\n|$)/) || [])[1];  // from the full-PDF summary
function waText(pid) {
  const r = rows[rowOf[pid]], lines = [`*${r[titleIdx].trim()}*`, 'CoRL 2026'];
  const talk = r[columns.indexOf('🎤 talk')], poster = r[columns.indexOf('🖼️ poster session')];  // schedule.json
  if (talk) lines.push(`🎤 Talk: ${talk}`);
  if (poster) lines.push(`🖼️ Poster: ${poster}`);
  lines.push((movies[pid] || []).length ? `🎬 Movie: ${PAGES}#${pid}/movie` : `📄 Paper: ${PAGES}#${pid}`);
  const arx = arxiv[pid] || ((links[pid] || {}).url || '').match(/^https?:\/\/arxiv\.org\/\S+/)?.[0];
  if (arx) lines.push(`📝 arXiv: ${arx}`);
  lines.push(`💬 OpenReview: https://openreview.net/forum?id=${pid}`);
  if (ghIdx >= 0 && r[ghIdx]) lines.push(...r[ghIdx].split(' ').map(u => `💻 GitHub: ${u}`));
  lines.push('', shortSum[pid] || gist(summaries[pid]) || r[columns.indexOf('abstract')] || '');
  return lines.join('\n').trim();
}
function waButton(pid) {
  const wrap = document.createElement('div'), b = document.createElement('button'),
        panel = document.createElement('div'), ta = document.createElement('textarea'), cp = document.createElement('button');
  wrap.className = 'wa'; panel.className = 'panel'; panel.hidden = true; ta.rows = 10;
  b.textContent = '💬 WhatsApp'; b.title = 'Prepare a WhatsApp message about this paper';
  cp.textContent = '📋 Copy';
  b.onclick = () => { if (!ta.value) ta.value = waText(pid); panel.hidden = !panel.hidden; };  // you can edit it before copying
  cp.onclick = async () => {
    ta.select();  // copying the selection works on file:// and http too; the Clipboard API is the fallback
    if (!document.execCommand('copy')) await navigator.clipboard.writeText(ta.value);
    cp.textContent = '✅ Copied'; setTimeout(() => cp.textContent = '📋 Copy', 1500);
  };
  panel.append(ta, cp); wrap.append(b, panel);
  return wrap;
}
function players(movs, ids) {  // local players; Google Drive's (ids[i]) where the local file is missing (GitHub Pages)
  return movs.map((p, i) => {
    const src = p.split('/').map(encodeURIComponent).join('/');
    const v = document.createElement(p.endsWith('.gif') ? 'img' : 'video');
    v.src = src; v.title = p.split('/').pop();
    if (v.tagName === 'VIDEO') { v.controls = true; v.preload = 'metadata'; }
    if (ids[i]) v.onerror = () => {
      const f = document.createElement('iframe');
      f.src = `https://drive.google.com/file/d/${ids[i]}/preview`; f.title = v.title;
      f.allow = 'autoplay; fullscreen'; f.allowFullscreen = true;
      v.replaceWith(f);
    };
    return v;
  });
}
function card(r, ri) {  // one paper's dropdown; the By time view builds its own copies
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
  const sumFlag = document.createElement('span');
  sumFlag.className = 'sumflag'; sumFlag.textContent = '📝'; sumFlag.hidden = true;
  s.append(stars(r[idIdx].split('id=').pop()), sumFlag);
  const m = meta[ri], b = [...m.t, ...m.d.map(x => '📅 ' + x)];
  if (m.cites) b.push(`📈 ${m.cites}`);
  if (m.h != null) b.push(`🏅 h ${m.h}`);
  if (m.b.length) b.push('🤖 ' + m.b.join(', '));
  if (m.m.length) b.push('🧠 ' + m.m.join(', '));
  if (m.c.length) b.push('🏢 ' + m.c.join(', '));
  if (b.length) { const e = document.createElement('span'); e.className = 'badges'; e.textContent = b.join('  ·  '); s.append(e); }
  const dl = document.createElement('dl');
  columns.forEach((c, i) => {
    if (i === titleIdx || !r[i]) return;
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = c; dd.appendChild(cellContent(r[i]));
    dl.append(dt, dd);
  });
  d.append(s, summaryBox(r[idIdx].split('id=').pop(), sumFlag), htmlBoxes(r[idIdx].split('id=').pop()));
  if (WA) d.append(waButton(r[idIdx].split('id=').pop()));
  d.append(dl);
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
  const movs = movies[r[idIdx].split('id=').pop()] || [];
  if (movs.length) {
    const mv = document.createElement('details'), ms = document.createElement('summary');
    ms.textContent = movs.length > 1 ? `🎬 Movies (${movs.length})` : '🎬 Movie';
    const box = document.createElement('div'); box.className = 'movies';
    const ids = movs.map(p => drive.files[p.split('/').pop()]);
    if (ids.some(Boolean)) {  // the same movies on Google Drive; they also play where the local files aren't (GitHub Pages)
      const dl2 = document.createElement('div'); dl2.className = 'drive';
      dl2.append('☁️ Google Drive: ');
      ids.forEach((id, i) => {
        if (!id) return;
        const a = document.createElement('a');
        a.href = `https://drive.google.com/file/d/${id}/view`; a.target = '_blank';
        a.textContent = movs.length > 1 ? `movie ${i + 1}` : 'movie';
        dl2.append(a, ' · ');
      });
      const f = document.createElement('a');
      f.href = drive.folder; f.target = '_blank'; f.textContent = 'all movies folder';
      dl2.append(f);
      mv.append(ms, dl2, box);
    } else mv.append(ms, box);
    mv.className = 'movie';
    const nx = document.createElement('button');
    nx.className = 'nextmov'; nx.textContent = '⏭ Next movie';
    nx.title = 'Next paper with a movie, in the list as shown now (filters, sort, session)';
    nx.onclick = () => {  // d's container holds only the papers on screen, in screen order
      const cards = [...d.parentElement.children];
      const next = cards.slice(cards.indexOf(d) + 1).find(c => c.querySelector(':scope > details.movie'));
      if (!next) { nx.textContent = '⏹ No more movies in this list'; return; }
      const m = next.querySelector(':scope > details.movie');
      mv.open = false; d.open = false;
      m.dataset.autoplay = '1'; next.open = true; m.open = true;
      next.scrollIntoView({block: 'start'});
    };
    mv.insertBefore(nx, box);
    mv.ontoggle = () => {  // players made on first open; preload="metadata" fetches only the first frame until played
      if (!mv.open) return box.querySelectorAll('video').forEach(v => v.pause());
      const play = () => { if (mv.dataset.autoplay) { delete mv.dataset.autoplay; box.querySelector('video')?.play().catch(() => {}); } };
      if (box.childElementCount) return play();
      box.append(...players(movs, ids));
      play();
    };
    dl.before(mv);  // right after the HTML / link buttons, before the fields
  }
  return d;
}
dets = rows.map(card);

// ---- filters ----
const picked = {d: new Set(), t: new Set(), p: new Set(), s: new Set(), k: new Set(), b: new Set(), m: new Set(), c: new Set(), u: new Set(), r: new Set()};
document.querySelectorAll('.facet').forEach(fd => {
  const key = fd.dataset.key, panel = fd.querySelector('.panel'), label = fd.querySelector('summary');
  if (!(facets[key] || []).length) return fd.hidden = true;  // nothing to pick on this site (e.g. Oral/Poster on your papers)
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
const FIELDS = ['q', 'minH', 'minC', 'sort', 'ghF', 'sumF', 'rateHas', 'rateF'];
FIELDS.forEach(id => document.getElementById(id).oninput = applyFilters);
const haystack = rows.map(r => r.join(' ').toLowerCase());  // every column, incl. companies/universities
document.getElementById('clear').onclick = () => {
  Object.values(picked).forEach(p => p.clear());
  document.querySelectorAll('.facet').forEach(fd => {
    fd.classList.remove('on'); fd.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = false);
    const l = fd.querySelector('summary'); l.textContent = l.textContent.replace(/ \(\d+\)$/, '');
  });
  FIELDS.forEach(id => document.getElementById(id).value = '');
  applyFilters();
};

// ---- remember the last filters (this browser only; file:// and http://127.0.0.1:8026/Corl2026/ keep separate copies) ----
function restoreFilters() {
  let saved;
  try { saved = JSON.parse(localStorage.getItem(store + 'Filters')); } catch (e) {}
  if (!saved) return;
  FIELDS.forEach(id => { if (saved.fields?.[id] != null) document.getElementById(id).value = saved.fields[id]; });
  document.querySelectorAll('.facet').forEach(fd => fd.querySelectorAll('input[type=checkbox]').forEach(cb => {
    if ((saved.picked?.[fd.dataset.key] || []).includes(cb.value)) { cb.checked = true; cb.onchange(); }
  }));
}
function saveFilters() {
  const fields = Object.fromEntries(FIELDS.map(id => [id, document.getElementById(id).value]));
  const pk = Object.fromEntries(Object.entries(picked).map(([k, v]) => [k, [...v]]));
  try { localStorage.setItem(store + 'Filters', JSON.stringify({fields, picked: pk})); } catch (e) {}
}

function applyFilters() {
  if (!dets.length) return;  // first renderTable() runs before the papers view exists
  const minH = +document.getElementById('minH').value || 0, minC = +document.getElementById('minC').value || 0;
  const sort = document.getElementById('sort').value;
  const hit = (key, ri) => !picked[key].size || meta[ri][key].some(x => picked[key].has(x));
  const terms = document.getElementById('q').value.toLowerCase().split(/\s+/).filter(Boolean);  // all must match
  const ghSel = document.getElementById('ghF').value, gh = i => !ghSel || (ghSel === 'y') === !!rows[i][ghIdx];
  const sumSel = document.getElementById('sumF').value,  // live: summaries changes as you summarize / erase
        sm = i => !sumSel || (sumSel === 'y') === !!summaries[rows[i][idIdx].split('id=').pop()];
  const hasSel = document.getElementById('rateHas').value, rateSel = document.getElementById('rateF').value, rt = i => {
    const v = ratings[rows[i][idIdx].split('id=').pop()] || 0, n = +rateSel.slice(1);
    return (!hasSel || (hasSel === 'y') === v > 0) && (!rateSel || v > 0 && (rateSel[0] === 'g' ? v > n : v < n));
  };
  let idx = rows.map((_, i) => i).filter(i => gh(i) && sm(i) && rt(i) &&
    terms.every(t => haystack[i].includes(t)) &&
    hit('d', i) && hit('t', i) && hit('p', i) && hit('s', i) && hit('k', i) && hit('b', i) && hit('m', i) && hit('c', i) && hit('u', i) && hit('r', i) && (meta[i].h || 0) >= minH && (meta[i].cites || 0) >= minC);
  if (sort === 'az') idx.sort((a, b) => rows[a][titleIdx].localeCompare(rows[b][titleIdx], undefined, {sensitivity: 'base'}));
  else if (sort) idx.sort((a, b) => (meta[b][sort] || 0) - (meta[a][sort] || 0));
  table.querySelector('tbody').replaceChildren(...idx.map(i => trs[i]));
  document.getElementById('papers').replaceChildren(...idx.map(i => dets[i]));
  shown = new Set(idx);
  if (document.getElementById('bytime').classList.contains('active')) renderByTime();
  document.querySelector('.count').textContent = idx.length === rows.length
    ? `📄 ${rows.length} papers` : `📄 ${idx.length} / ${rows.length} papers`;
  saveFilters();
  updateStats();
}

// ---- top-bar statistics over all papers (not just the filtered ones) ----
function updateStats() {
  const costOf = o => Object.values(o).reduce((t, x) => t + (x.cost || 0), 0);
  const rated = Object.values(ratings), avg = rated.length ? rated.reduce((a, b) => a + b, 0) / rated.length : 0;
  const spent = costOf(summaries) + costOf(htmlv.claude) + costOf(htmlv.claude2) + costOf(links);
  document.querySelector('nav .stats').textContent = [
    `📝 ${Object.keys(summaries).length} summaries`,
    `🌐 ${Object.keys(htmlv.claude).length} HTML (Claude)`,
    `🐍 ${Object.keys(htmlv.python).length} HTML (python)`,
    `🔗 ${Object.values(links).filter(v => v.url).length} links`,
    `⭐ ${rated.length} rated` + (rated.length ? ` (avg ${avg.toFixed(1)})` : ''),
    `💲 $${spent.toFixed(2)} Claude spend`,
  ].join('  ·  ');
}

// ---- by-time view: one session's papers in presentation order (talk order / poster number), same filters ----
const btSel = document.getElementById('btSession'), posterIdx = columns.indexOf('🖼️ poster session');
const rowOf = Object.fromEntries(rows.map((r, i) => [r[idIdx].split('id=').pop(), i]));
let shown = null;  // rows passing the filters, set by applyFilters
if (!schedule.sessions.length) document.querySelector('nav button[data-view=bytime]').hidden = true;  // no schedule (your papers)
btSel.append(...schedule.sessions.map(x => new Option(x, x)));
// ponytail: "Mon 11/9, 5:00–6:30 PM" read as this year in this computer's time zone (not converted from the venue's)
const endOf = x => {
  const m = x.match(/(\d+)\/(\d+),.*–(\d+):(\d+)\s*([AP]M)/);
  return m && new Date(new Date().getFullYear(), m[1] - 1, +m[2], m[3] % 12 + (m[5] === 'PM' ? 12 : 0), +m[4]);
};
btSel.value = schedule.sessions.find(x => endOf(x) > new Date()) || schedule.sessions[0] || '';  // the next session
function renderByTime() {
  const ids = schedule.order[btSel.value] || [], poster = btSel.value.startsWith('Poster');
  const list = ids.map((pid, k) => [rowOf[pid], k]).filter(([i]) => i != null && (!shown || shown.has(i)));
  document.getElementById('btCount').textContent = `📄 ${list.length} / ${ids.length} papers` +
    (list.length < ids.length ? ' (the rest are hidden by your filters)' : '');
  document.getElementById('btList').replaceChildren(...list.map(([i, k]) => {
    const d = card(rows[i], i), n = document.createElement('span');
    n.className = 'btnum';
    n.textContent = poster ? (rows[i][posterIdx].match(/#\d+$/) || [''])[0] + ' ' : `${k + 1}. `;
    d.querySelector('summary').prepend(n);
    return d;
  }));
}
btSel.onchange = renderByTime;
const step = by => { btSel.selectedIndex = Math.min(Math.max(btSel.selectedIndex + by, 0), btSel.options.length - 1); renderByTime(); };
document.getElementById('btPrev').onclick = () => step(-1);
document.getElementById('btNext').onclick = () => step(1);

// ---- random view: papers with a movie in a shuffled order; ⏭ Next drops the one you watched and opens the next.
// The order and what you watched are kept in this browser (localStorage) until 🔀 Reset random ----
const rdKey = store + 'Random', rdList = document.getElementById('rdList');
const pdfIdx = columns.indexOf('local_pdf'), webIdx = columns.indexOf('pdf');
const withMovies = rows.map(r => r[idIdx].split('id=').pop()).filter(pid => (movies[pid] || []).length);
if (!withMovies.length) document.querySelector('nav button[data-view=random]').hidden = true;
let rd = null;
try { rd = JSON.parse(localStorage.getItem(rdKey)); } catch (e) {}
const saveRd = () => { try { localStorage.setItem(rdKey, JSON.stringify(rd)); } catch (e) {} };
function shuffle() {  // Fisher-Yates
  const a = [...withMovies];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  rd = {order: a, seen: []}; saveRd();
}
if (!rd?.order) shuffle();
else {  // papers added or dropped since: new ones go in at random places
  const have = new Set(withMovies), known = new Set(rd.order);
  rd.order = rd.order.filter(p => have.has(p));
  withMovies.filter(p => !known.has(p)).forEach(p => rd.order.splice(Math.floor(Math.random() * (rd.order.length + 1)), 0, p));
  saveRd();
}
const rdCount = () => document.getElementById('rdCount').textContent = rdList.childElementCount
  ? `🎲 ${rdList.childElementCount} movies left of ${rd.order.length}` : `🎉 All ${rd.order.length} movies watched`;
function rdEntry(pid) {
  const r = rows[rowOf[pid]], e = document.createElement('div'), h = document.createElement('div');
  e.className = 'rd'; h.className = 'rdtitle'; h.textContent = r[titleIdx];
  const link = (href, text, title) => {
    const a = document.createElement('a'); a.href = encodeURI(href); a.target = '_blank'; a.textContent = text; a.title = title; h.append(a);
  };
  if (pdfIdx >= 0 && r[pdfIdx]) link(r[pdfIdx], '📄 PDF', 'Local PDF');
  if (webIdx >= 0 && r[webIdx]) link(r[webIdx], '🌐 OpenReview', 'PDF on OpenReview');
  const movs = movies[pid], ids = movs.map(p => drive.files[p.split('/').pop()]);
  const mv = document.createElement('details'), ms = document.createElement('summary'),
        box = document.createElement('div'), nx = document.createElement('button');
  ms.textContent = movs.length > 1 ? `🎬 Movies (${movs.length})` : '🎬 Movie';
  box.className = 'movies'; nx.className = 'nextmov'; nx.textContent = '⏭ Next';
  nx.title = 'Done with this one: remove it and open the next movie';
  mv.append(ms, nx, box);
  mv.ontoggle = () => {
    if (!mv.open) return box.replaceChildren();  // players only while open, so only one movie holds memory
    box.replaceChildren(...players(movs, ids));
    if (mv.dataset.autoplay) { delete mv.dataset.autoplay; box.querySelector('video')?.play().catch(() => {}); }
  };
  nx.onclick = () => {
    rd.seen.push(pid); saveRd();
    const next = e.nextElementSibling;
    e.remove(); rdCount();
    if (!next) return;
    const m = next.querySelector('details');
    m.dataset.autoplay = '1'; m.open = true;
    next.scrollIntoView({block: 'start'});
  };
  e.append(h);
  if (WA) e.append(waButton(pid));
  e.append(mv);
  return e;
}
function renderRandom() {
  const seen = new Set(rd.seen);
  rdList.replaceChildren(...rd.order.filter(p => !seen.has(p)).map(rdEntry));
  rdCount();
}
document.getElementById('rdReset').onclick = ev => {
  ev.preventDefault();
  if (!confirm('Start a new random order? The movies you already watched will come back.')) return;
  shuffle(); renderRandom();
};

restoreFilters();
renderTable();
show('papers');
// ---- #<paper id> in the address scrolls to that paper, closed (the Add box on the papers site jumps to the one it added) ----
// #<paper id>/movie (the WhatsApp link) also opens the paper and its movie
const [target, want] = decodeURIComponent(location.hash.slice(1)).split('/'),
      ti = target ? rows.findIndex(r => r[idIdx].split('id=').pop() === target) : -1;
if (ti >= 0) {
  if (!dets[ti].isConnected) document.getElementById('clear').click();  // hidden by saved filters: show everything
  const m = want === 'movie' && dets[ti].querySelector(':scope > details.movie');
  if (m) { dets[ti].open = true; m.open = true; }
  dets[ti].scrollIntoView();
}
if (location.hash) history.replaceState(null, '', location.pathname + location.search);  // a refresh starts at the top
</script>
</body>
</html>
"""


def clean_inst(name):
    """"Google (United States)" -> "Google"; OpenAlex suffixes countries on company names."""
    return re.sub(r"\s*\([^)]*\)$", "", name).strip()


def load(here, name, default):
    """A JSON file of the site folder, or default when it doesn't exist yet."""
    path = os.path.join(here, name)
    return json.load(open(path)) if os.path.exists(path) else default


def openalex_meta(rows, columns, here):
    """Per-row {c: companies, u: universities, r: top-researcher ids, cites, h} and the filter option lists."""
    from corl2026_affiliations import COMPANY_RES
    oa = load(here, "openalex.json", {"works": {}, "authors": {}})
    robots = load(here, "robots.json", {})
    backbones = load(here, "backbones.json", {})
    schedule = load(here, "schedule.json", {"papers": {}, "sessions": []})
    pdf_aff = load(here, "affiliations.json", {"papers": {}})["papers"]
    authors = oa["authors"]
    id_col = columns.index("id")
    venue_col = columns.index("venue") if "venue" in columns else None
    kw_cols = {k: columns.index(c) for k, c in [("p", "primary_keyword"), ("s", "secondary_keyword")] if c in columns}
    gen_col = columns.index("🏷️ keywords") if "🏷️ keywords" in columns else None  # "a; b; c", from Claude (papers site)
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
            "t": [PRESENTATION.get(r[venue_col].split()[-1], r[venue_col])] if venue_col is not None and r[venue_col] else [],
            "d": schedule["papers"].get(pid, {}).get("sessions", []),
            "b": robots.get(pid, []),
            "m": backbones.get(pid, []),
            "k": r[gen_col].split("; ") if gen_col is not None and r[gen_col] else [],
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
    in_session = collections.Counter(x for m in meta for x in m["d"])
    sessions = [{"id": x, "name": x, "note": f"{in_session[x]} 📄"} for x in schedule["sessions"]]  # in time order
    return meta, {"d": sessions, "c": top("c", TOP_COMPANIES), "u": top("u", TOP_UNIVERSITIES), "r": researchers, "b": top("b", TOP_ROBOTS), "m": top("m", TOP_ROBOTS), "k": top("k", TOP_KEYWORDS), "t": top("t", 3),
                  **{k: top(k, TOP_KEYWORDS) for k in kw_cols}}


def html_versions(kind, here):
    """paper id -> {path, cost / seconds, ...} for every htmls_<kind>/<id>_<title>/index.html."""
    out = {}
    for idx in glob.glob(os.path.join(here, f"htmls_{kind}", "*", "index.html")):
        meta = os.path.join(os.path.dirname(idx), "meta.json")
        pid = os.path.basename(os.path.dirname(idx)).split("_", 1)[0]
        out[pid] = {"path": os.path.relpath(idx, here), **(json.load(open(meta)) if os.path.exists(meta) else {})}
    return out


def paper_movies(here):
    """paper id -> movie paths relative to here, the main one first, then _2, _3, …"""
    def n(p):
        m = re.search(r"_(\d+)\.\w+$", p)
        return int(m.group(1)) if m else 1
    out = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(here, "movies", "paper_movies", "*")),
                    key=lambda p: (os.path.basename(p).split("_", 1)[0], n(p))):
        out[os.path.basename(p).split("_", 1)[0]].append(os.path.relpath(p, here))
    return out


def condensed_versions(here):
    """paper id -> {path, cost, ...} for every htmls_claude/<id>_<title>/condensed.html (the Condense button)."""
    out = {}
    for page in glob.glob(os.path.join(here, "htmls_claude", "*", "condensed.html")):
        meta = os.path.join(os.path.dirname(page), "condensed.json")
        pid = os.path.basename(os.path.dirname(page)).split("_", 1)[0]
        out[pid] = {"path": os.path.relpath(page, here), **(json.load(open(meta)) if os.path.exists(meta) else {})}
    return out


def build(here, title, columns, rows, add_box="", store="corl"):
    """Write here/index.html for these rows (columns must include id, title and pdf; id ends in the paper id).

    store prefixes the browser-storage keys (saved filters, pending ratings): sites on one server share the storage."""
    local = {os.path.basename(p).split("_", 1)[0]: os.path.relpath(p, here) for p in glob.glob(os.path.join(here, "pdfs", "*.pdf"))}
    columns.insert(columns.index("pdf") + 1, "local_pdf")
    for r in rows:
        r.insert(columns.index("local_pdf"), local.get(r[0].split("id=")[-1], ""))
    github = load(here, "github.json", {})
    columns.insert(columns.index("local_pdf") + 1, "💻 github")
    for r in rows:
        r.insert(columns.index("💻 github"), " ".join(github.get(r[0].split("id=")[-1], [])))
    schedule = load(here, "schedule.json", {"papers": {}})["papers"]
    at = columns.index("title") + 1
    columns[at:at] = ["🎤 talk", "🖼️ poster session"]
    for r in rows:
        s = schedule.get(r[0].split("id=")[-1], {})
        r[at:at] = [s.get("talk", ""), s.get("poster", "")]
    meta, facets = openalex_meta(rows, columns, here)
    for name, key in [("🤖 robots", "b"), ("🧠 backbones", "m"), ("🏢 companies", "c"), ("🎓 universities", "u")]:
        columns.append(name)
        for r, m in zip(rows, meta):
            r.append("; ".join(m[key]))
    columns += ["📈 citations", "🏅 max author h-index"]
    for r, m in zip(rows, meta):
        r += ["" if m["cites"] is None else str(m["cites"]), "" if m["h"] is None else str(m["h"])]
    keep = [i for i in range(len(columns)) if any(r[i] for r in rows) or not rows]  # drop all-empty columns
    columns = [columns[i] for i in keep]
    rows = [[r[i] for i in keep] for r in rows]
    data = json.dumps({"columns": columns, "rows": rows, "firstPage": load(here, "first_page.json", {}), "meta": meta,
                       "facets": facets, "summaries": load(here, "summaries.json", {}),
                       "ratings": load(here, "ratings.json", {}), "links": load(here, "links.json", {}),
                       "htmlv": {**{k: html_versions(k, here) for k in HTML_KINDS}, "claude2": condensed_versions(here)},
                       "movies": paper_movies(here), "here": here, "store": store,
                       "drive": load(here, "drive_movies.json", {"folder": "", "files": {}}),
                       "arxiv": {k: v for k, v in load(here, "arxiv.json", {}).items() if v},
                       "shortSum": {k: v["text"] for k, v in load(here, "slide_summaries.json", {}).items()},
                       "schedule": {k: v for k, v in load(here, "schedule.json", {"sessions": [], "order": {}}).items()
                                    if k in ("sessions", "order")}}, ensure_ascii=False).replace("</", "<\\/")
    out = os.path.join(here, "index.html")
    with open(out, "w") as f:
        f.write(HTML.replace("__TITLE__", title).replace("__ADD__", add_box).replace("__DATA__", data))
    print(f"wrote {out} ({len(rows)} papers, {len(columns)} columns)")


def csv_rows():
    with open(CSV, newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        columns = next(reader)
        return columns, [r + [""] * (len(columns) - len(r)) for r in reader if any(r)]


def paper_info(pid):
    """(title, authors) of a CoRL 2026 paper, for the Find link button."""
    columns, rows = csv_rows()
    row = next((dict(zip(columns, r)) for r in rows if r[0].split("id=")[-1] == pid), None)
    return (row["title"], row["authors"]) if row else None


def main():
    build(HERE, "CoRL 2026", *csv_rows())


if __name__ == "__main__":
    main()
