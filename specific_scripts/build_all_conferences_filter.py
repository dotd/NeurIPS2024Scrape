"""Build htmls/all_conferences_filter.html from ConferenceTables/*.csv.

Single self-contained HTML: topic + conference filter buttons, free-text
search, papers as native <details> dropdowns. See
docs/new_html_viewer_of_conferences.md.
"""

import glob
import json
import os
import re

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


def load_papers():
    papers = []
    conferences = []
    for path in sorted(glob.glob(os.path.join(ROOT, "ConferenceTables", "*.csv"))):
        conf = os.path.basename(path).replace("_Conference.csv", "").replace("_cc_", " ").replace("_", " ")
        conferences.append(conf)
        with open(path) as f:
            for line in f:
                p = parse_row(line.rstrip("\n").split("\t"))
                if p is None or not p["title"]:
                    continue
                tag_text = f"{p['title']} {p['keywords']} {p['tldr']}"
                topics = [key for key, rx in TOPIC_RES if rx.search(tag_text)]
                papers.append([conf, p["title"], p["authors"], p["keywords"], p["venue"],
                               p["pdf"], p["forum"], p["tldr"], p["abstract"], topics])
    # newest first: by year, then by when the conference happens within a year
    conf_month = {"ICLR": 4, "ICML": 7, "NeurIPS": 12}
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
  .body { padding: 0 14px 12px; font-size: 13px; color: #333; }
  .body .meta { color: #666; margin: 4px 0; }
  .body a { color: #2563eb; margin-right: 12px; }
  .more { text-align: center; padding: 14px; }
</style>
</head>
<body>
<header>
  <h1>All Conferences Paper Filter</h1>
  <div class="btnrow"><span class="grp">Topics</span>__TOPIC_BUTTONS__</div>
  <div class="btnrow"><span class="grp">Conferences</span>__CONF_BUTTONS__</div>
  <div class="btnrow"><span class="grp">Search</span>
    <input id="search" type="search" placeholder="free words, all must match...">
    <span id="count"></span>
  </div>
</header>
<main><div id="list"></div><div class="more" id="more"></div></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const PAPERS = JSON.parse(document.getElementById('data').textContent);
const ICONS = __ICONS__;
const PAGE = 300;
let shown = PAGE;
const activeTopics = new Set(), activeConfs = new Set();

// precompute lowercase search blob per paper
for (const p of PAPERS) p.blob = (p[1] + ' ' + p[2] + ' ' + p[3] + ' ' + p[8]).toLowerCase();

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }

function matches(p, words) {
  if (activeConfs.size && !activeConfs.has(p[0])) return false;
  if (activeTopics.size && !p[9].some(t => activeTopics.has(t))) return false;
  return words.every(w => p.blob.includes(w));
}

function render() {
  const words = document.getElementById('search').value.toLowerCase().split(/\\s+/).filter(Boolean);
  const hits = PAPERS.filter(p => matches(p, words));
  const html = hits.slice(0, shown).map(p => {
    const icons = p[9].map(t => ICONS[t]).join('');
    const links = [p[6] && `<a href="${p[6]}" target="_blank">OpenReview</a>`,
                   p[5] && `<a href="${p[5]}" target="_blank">PDF</a>`].filter(Boolean).join('');
    return `<details><summary><span class="icons">${icons}</span>${esc(p[1])}` +
      `<span class="conf">${esc(p[0])} — ${esc(p[4])}</span></summary><div class="body">` +
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
let deb;
document.getElementById('search').oninput = () => {
  clearTimeout(deb); deb = setTimeout(() => { shown = PAGE; render(); }, 250);
};
render();
</script>
</body>
</html>
"""


def main():
    conferences, papers = load_papers()
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
    out = os.path.join(ROOT, "htmls", "all_conferences_filter.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html)
    print(f"Wrote {out}: {len(papers)} papers, {len(conferences)} conferences, "
          f"{os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
