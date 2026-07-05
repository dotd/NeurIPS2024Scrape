"""Build htmls/all_conferences_filter.html from ConferenceTables/*.csv.

Single self-contained HTML: topic + conference filter buttons, free-text
search, papers as native <details> dropdowns. See
docs/new_html_viewer_of_conferences.md.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalize_keywords import normalize, load_keyword_counts, build_groups

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOPICS = [
    # (key, label, icon, regex over title+keywords+tldr)
    ("robotics", "Robotics", "\U0001F916", r"robot|manipulat|embodied|locomotion|grasp"),
    ("rl", "Reinforcement Learning", "\U0001F579", r"reinforcement learning|\brl\b"),
    ("vla", "VLA", "\U0001F9BE", r"vision.language.action|\bvla\b"),
    ("vlm", "VLM", "\U0001F441", r"vision.language model|\bvlms?\b"),
    ("open", "Open Models", "\U0001F310", r"open.(source|weight)|open model"),
    ("world", "World Models", "\U0001F30D", r"world.model"),
]
TOPIC_RES = [(key, re.compile(rx, re.I)) for key, _, _, rx in TOPICS]


def parse_row(cols):
    """Return dict from a CSV row; two layouts exist (9 and 11 columns)."""
    if len(cols) == 11:  # id,title,authors,keywords,area,venue,pdf,supp,tldr,spotlight,abstract
        return dict(forum=cols[0], title=cols[1], authors=cols[2], keywords=cols[3],
                    venue=cols[5], pdf=cols[6], tldr=cols[8], abstract=cols[10])
    if len(cols) == 9:  # title,authors,keywords,area,venue,pdf,supp,tldr,abstract
        return dict(forum="", title=cols[0], authors=cols[1], keywords=cols[2],
                    venue=cols[4], pdf=cols[5], tldr=cols[7], abstract=cols[8])
    return None


def canonical_keywords():
    """normalized form -> canonical display (most common original spelling)."""
    groups = build_groups(load_keyword_counts())
    return {norm: variants[0][0] for norm, variants in groups.items()}


def load_citations():
    """normalized title -> citation count, from fetch_citations.py's cache."""
    path = os.path.join(ROOT, "ConferencesData", "citations_openalex.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {k: v["cites"] for k, v in json.load(f).items() if v.get("cites") is not None}


def load_papers():
    canon = canonical_keywords()
    citations = load_citations()
    papers = []
    conferences = []
    for path in sorted(glob.glob(os.path.join(ROOT, "ConferenceTables", "*.csv"))):
        m = re.search(r"(CoRL|ICLR|ICML|NeurIPS)\D*(\d{4})", os.path.basename(path))
        conf = f"{m.group(1)} {m.group(2)}"
        conferences.append(conf)
        with open(path) as f:
            for line in f:
                p = parse_row(line.rstrip("\n").split("\t"))
                if p is None or not p["title"]:
                    continue
                normed = list(dict.fromkeys(  # dedup, keep order
                    canon[normalize(k.strip())]
                    for k in p["keywords"].split(";") if normalize(k.strip())))
                p["keywords"] = ";".join(normed)
                tag_text = f"{p['title']} {p['keywords']} {p['tldr']}"
                topics = [key for key, rx in TOPIC_RES if rx.search(tag_text)]
                cites = citations.get(re.sub(r"[^a-z0-9]", "", p["title"].lower()))
                papers.append([conf, p["title"], p["authors"], p["keywords"], p["venue"],
                               p["pdf"], p["forum"], p["tldr"], p["abstract"], topics, cites])
    # newest first: by year, then by when the conference happens within a year
    conf_month = {"ICLR": 4, "ICML": 7, "CoRL": 11, "NeurIPS": 12}
    def recency(conf):
        name, year = conf.split()
        return int(year), conf_month.get(name, 0)
    papers.sort(key=lambda p: recency(p[0]), reverse=True)
    return conferences, papers


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>All Conferences Paper Filter</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; margin: 0; background: #f6f7f9; color: #1a1a1a; }
  header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 12px 20px; z-index: 1; }
  h1 { font-size: 18px; margin: 0 0 10px; }
  .btnrow { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .btnrow span.grp { font-size: 12px; color: #777; align-self: center; width: 90px; }
  button.flt { border: 1px solid #ccc; background: #fff; border-radius: 14px; padding: 4px 12px; cursor: pointer; font-size: 13px; }
  button.flt.on { background: #2563eb; border-color: #2563eb; color: #fff; }
  #search { width: 340px; padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }
  #count { font-size: 13px; color: #555; margin-left: 10px; }
  main { padding: 12px 20px; }
  details { background: #fff; border: 1px solid #e3e5e8; border-radius: 6px; margin-bottom: 6px; }
  summary { cursor: pointer; padding: 8px 12px; font-size: 14px; list-style-position: outside; }
  summary .icons { margin-right: 6px; }
  summary .conf { color: #888; font-size: 12px; margin-left: 8px; white-space: nowrap; }
  summary .cites { color: #b45309; font-size: 12px; margin-left: 8px; white-space: nowrap; }
  .body { padding: 0 14px 12px; font-size: 13px; color: #333; }
  .body .meta { color: #666; margin: 4px 0; }
  .body a { color: #2563eb; margin-right: 12px; }
  .more { text-align: center; padding: 14px; }
  #kwpanel { background: #fff; border: 1px solid #e3e5e8; border-radius: 6px; margin-bottom: 12px; padding: 8px 12px; }
  #kwpanel summary { cursor: pointer; font-size: 14px; }
  #kwfilter { width: 260px; padding: 4px 8px; margin: 8px 0; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; }
  #kwlist { display: flex; flex-wrap: wrap; gap: 4px; max-height: 300px; overflow-y: auto; }
  #kwlist button { font-size: 12px; padding: 2px 8px; }
  #kwmore { margin-top: 8px; }
</style>
</head>
<body>
<header>
  <h1>All Conferences Paper Filter</h1>
  <div class="btnrow"><span class="grp">Topics</span>__TOPIC_BUTTONS__</div>
  <div class="btnrow"><span class="grp">Conferences</span>__CONF_BUTTONS__</div>
  <div class="btnrow"><span class="grp">Search</span>
    <input id="search" type="search" placeholder="free words, all must match...">
    <span class="grp" style="width:auto;margin-left:14px">Sort</span>
    <button class="flt srt on" data-sort="new">Newest</button>
    <button class="flt srt" data-sort="cites">Most cited</button>
    <span id="count"></span>
  </div>
</header>
<main>
<details id="kwpanel"><summary>Keywords (author-defined, by number of papers)</summary>
  <input id="kwfilter" type="search" placeholder="filter keywords...">
  <button id="kwmode" class="flt on" title="how selected keywords combine">Intersection</button>
  <div id="kwlist"></div>
  <button id="kwmore" class="flt">Show more</button>
</details>
<div id="list"></div><div class="more" id="more"></div></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const PAPERS = JSON.parse(document.getElementById('data').textContent);
const ICONS = __ICONS__;
const PAGE = 300;
let shown = PAGE;
const activeTopics = new Set(), activeConfs = new Set();

// precompute lowercase search blob + keyword set per paper; global keyword counts
const KW = new Map(); // lowercase -> [display form, paper count]
for (const p of PAPERS) {
  p.blob = (p[1] + ' ' + p[2] + ' ' + p[3] + ' ' + p[8]).toLowerCase();
  p.kws = new Set();
  for (let k of p[3].split(';')) {
    k = k.trim();
    if (!k) continue;
    const lc = k.toLowerCase();
    if (p.kws.has(lc)) continue;
    p.kws.add(lc);
    const e = KW.get(lc);
    e ? e[1]++ : KW.set(lc, [k, 1]);
  }
}
const KW_SORTED = [...KW.entries()].sort((a, b) => b[1][1] - a[1][1]);
const activeKws = new Set();
const KWPAGE = 300;
let kwShown = KWPAGE;

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }

// conferences: union; topics: intersection; keywords: toggleable via kwUnion
let kwUnion = false;
function matches(p, words) {
  if (activeConfs.size && !activeConfs.has(p[0])) return false;
  for (const t of activeTopics) if (!p[9].includes(t)) return false;
  if (activeKws.size) {
    if (kwUnion) {
      let any = false;
      for (const k of activeKws) if (p.kws.has(k)) { any = true; break; }
      if (!any) return false;
    } else {
      for (const k of activeKws) if (!p.kws.has(k)) return false;
    }
  }
  return words.every(w => p.blob.includes(w));
}

function renderKws() {
  const q = document.getElementById('kwfilter').value.toLowerCase().trim();
  const pool = q ? KW_SORTED.filter(([lc]) => lc.includes(q)) : KW_SORTED;
  document.getElementById('kwlist').innerHTML = pool.slice(0, kwShown).map(([lc, [disp, n]]) =>
    `<button class="flt${activeKws.has(lc) ? ' on' : ''}" data-kw="${esc(lc)}">${esc(disp)} (${n})</button>`).join('');
  document.getElementById('kwmore').style.display = pool.length > kwShown ? '' : 'none';
}

let sortBy = 'new';
function render() {
  const words = document.getElementById('search').value.toLowerCase().split(/\\s+/).filter(Boolean);
  let hits = PAPERS.filter(p => matches(p, words));
  if (sortBy === 'cites') hits = hits.slice().sort((a, b) => (b[10] ?? -1) - (a[10] ?? -1));
  const html = hits.slice(0, shown).map(p => {
    const icons = p[9].map(t => ICONS[t]).join('');
    const cites = p[10] != null ? `<span class="cites">&#128200; ${p[10]}</span>` : '';
    const links = [p[6] && `<a href="${p[6]}" target="_blank">OpenReview</a>`,
                   p[5] && `<a href="${p[5]}" target="_blank">PDF</a>`].filter(Boolean).join('');
    return `<details><summary><span class="icons">${icons}</span>${esc(p[1])}` +
      `<span class="conf">${esc(p[0])} — ${esc(p[4])}</span>${cites}</summary><div class="body">` +
      `<div class="meta"><b>Authors:</b> ${esc(p[2])}</div>` +
      (p[3] ? `<div class="meta"><b>Keywords:</b> ${esc(p[3])}</div>` : '') +
      (p[7] ? `<div class="meta"><b>TLDR:</b> ${esc(p[7])}</div>` : '') +
      `<p>${esc(p[8])}</p><div>${links}</div></div></details>`;
  }).join('');
  document.getElementById('list').innerHTML = html;
  document.getElementById('count').textContent = `${hits.length} / ${PAPERS.length} papers`;
  document.getElementById('more').innerHTML = hits.length > shown
    ? `<button class="flt" onclick="shown+=${PAGE};render()">Show ${Math.min(PAGE, hits.length - shown)} more</button>` : '';
}

function toggle(btn, set, val) {
  btn.classList.toggle('on') ? set.add(val) : set.delete(val);
  shown = PAGE; render();
}
document.querySelectorAll('[data-topic]').forEach(b =>
  b.onclick = () => toggle(b, activeTopics, b.dataset.topic));
document.querySelectorAll('[data-conf]').forEach(b =>
  b.onclick = () => toggle(b, activeConfs, b.dataset.conf));
document.querySelectorAll('.srt').forEach(b => b.onclick = () => {
  document.querySelectorAll('.srt').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  sortBy = b.dataset.sort;
  shown = PAGE; render();
});
document.getElementById('kwlist').onclick = e => {
  const b = e.target.closest('button[data-kw]');
  if (!b) return;
  const k = b.dataset.kw;
  b.classList.toggle('on') ? activeKws.add(k) : activeKws.delete(k);
  shown = PAGE; render();
};
document.getElementById('kwmore').onclick = () => { kwShown += KWPAGE; renderKws(); };
document.getElementById('kwmode').onclick = e => {
  kwUnion = !kwUnion;
  e.target.textContent = kwUnion ? 'Union' : 'Intersection';
  shown = PAGE; render();
};
let deb, kwdeb;
document.getElementById('search').oninput = () => {
  clearTimeout(deb); deb = setTimeout(() => { shown = PAGE; render(); }, 250);
};
document.getElementById('kwfilter').oninput = () => {
  clearTimeout(kwdeb); kwdeb = setTimeout(() => { kwShown = KWPAGE; renderKws(); }, 250);
};
renderKws();
render();
</script>
</body>
</html>
"""


def write_html(papers, conferences, out_name):
    topic_buttons = "".join(
        f'<button class="flt" data-topic="{key}">{icon} {label}</button>'
        for key, label, icon, _ in TOPICS)
    conf_buttons = "".join(
        f'<button class="flt" data-conf="{c}">{c}</button>' for c in conferences)
    data = json.dumps(papers, ensure_ascii=False).replace("</", "<\\/")
    icons = json.dumps({key: icon for key, _, icon, _ in TOPICS}, ensure_ascii=False)
    html = (HTML_TEMPLATE
            .replace("__TOPIC_BUTTONS__", topic_buttons)
            .replace("__CONF_BUTTONS__", conf_buttons)
            .replace("__ICONS__", icons)
            .replace("__DATA__", data))
    out = os.path.join(ROOT, "htmls", out_name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html)
    print(f"Wrote {out}: {len(papers)} papers, {len(conferences)} conferences, "
          f"{os.path.getsize(out) / 1e6:.1f} MB")


def main():
    conferences, papers = load_papers()
    write_html(papers, conferences, "all_conferences_filter.html")
    # short version: only papers tagged with at least one topic
    write_html([p for p in papers if p[9]], conferences, "all_conferences_filter_short.html")


if __name__ == "__main__":
    main()
