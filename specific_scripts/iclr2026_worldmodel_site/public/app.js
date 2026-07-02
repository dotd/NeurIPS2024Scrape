const state = {
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
