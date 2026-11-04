# CoRL 2026 paper browser

A single-page browser for the 687 accepted CoRL 2026 papers. It shows each paper's first figure,
its affiliations, robots, citations and GitHub link, has filters for all of these, and can produce
on-demand Claude summaries.

## Quick start

```bash
# browse only (static file; summaries can't be generated)
open website/corl2026/index.html

# browse + Summarize button
uv run python website/serve.py      # then open http://127.0.0.1:8026/Corl2026/
```

To open local PDFs in Preview, so you can highlight them, install the link handler once:

```bash
specific_scripts/install_openpdf_handler.sh
```

## Using the page

**Views.** Use **Papers** (the default) or **Table**.
- In Papers, each paper is a dropdown. Its summary line shows the title, `[keywords]`, the GitHub
  icon, then badges: presentation type, 📈 citations, 🏅 max author h-index, 🤖 robots,
  🧠 backbones and 🏢 companies.
- Opening a paper shows:
  - the Summarize button or summary;
  - the HTML-version and 🔗 Find link to paper buttons;
  - a nested **🎬 Movie / Movies (N)** dropdown (594 papers). The players are created only when it is
    opened and load just the first frame until you press play; closing it pauses them;
  - every field;
  - the first figure;
  - a nested **All figures (N)** dropdown, a collage sized to fit the screen.
- In Table, you can drag column headers to reorder them and drag their edges to resize. Columns
  that are empty for every paper are dropped.

**Top bar.** Papers / Table view buttons, then statistics over all papers: number of summaries, HTML
versions (Claude and python), rated papers (with the average rating), and total Claude spend (summaries + Claude HTML versions with
a recorded cost). On the right are the shown / total count and ↺ Reset filters.

**Filters.** These all work in both views.
- Within a checkbox dropdown, ticked options are combined with OR. Different filters are combined
  with AND.
- The count at the top right shows `📄 shown / total`.

| Filter | What it matches |
|---|---|
| 🔍 search | Every word must appear somewhere in the paper's data (title, authors, abstract, keywords, affiliations, …). Case-insensitive. |
| 🎤 Oral / Spotlight / Poster | Presentation type, taken from the `venue` field (21 oral, 72 spotlight, 594 poster). |
| 🏷️ Primary / 🔖 Secondary keyword | The author-chosen CoRL topic (22 fixed topics each). |
| 🤖 Robots | The top 50 robot platforms detected in the PDF text. |
| 🧠 Backbones | Known models the paper mentions at least twice before References: vision encoders (ViT, DINO, CLIP, SigLIP, …), LLMs / VLMs (Qwen, Gemma, PaliGemma, …), VLAs (π0, OpenVLA, GR00T, Octo, …) and policy families (Diffusion Policy, ACT, …). |
| 🏢 Companies | The top 20 companies in the affiliations. |
| 🎓 Universities | The top 50 universities in the affiliations. |
| 🧑‍🔬 Researchers | The 50 authors with the highest OpenAlex h-index. |
| ⭐ Rated | all / with rating / without rating. |
| ⭐ Rating | all / above 1…4 / below 5…2, on your own star ratings (only rated papers pass). |
| 📝 Summary | all / summarized / not summarized: whether a Claude summary exists. The list updates as soon as you summarize or erase. |
| 💻 GitHub | all / GitHub / no GitHub: whether the PDF links a repo. |
| 🏅 min author h-index, 📈 min citations | Numeric minimums. Papers missing from OpenAlex count as 0. |
| Sort | Default, author h-index, citations, or title A–Z. |

The page remembers your last filters, search and sort, and restores them when you reopen it. This is
per browser: the file page and http://127.0.0.1:8026/Corl2026/ each keep their own copy. **↺ Reset filters** at the
right end of the top bar clears everything.

**Local PDF links.**
- 🖊️ opens the PDF in macOS Preview through `openpdf://` (needs the handler above). Highlights
  save into `pdfs/…`.
- 🌐 opens it in the browser.

**Rating.** The ☆☆☆☆☆ on each paper's summary line is your 1–5 rating. Click a star to rate, click the
same star again to clear it. Through `serve.py` ratings are saved to `ratings.json` and baked into
`index.html`. On the page opened as a file they are kept in the browser (localStorage) and sent to the
server the next time you open http://127.0.0.1:8026/Corl2026/.

**Summaries.**
- **📝 Summarize** sends the PDF to Claude Opus (`claude-opus-5-5`). It needs `serve.py` running
  and takes about 30 s.
- The summary is 3–10 paragraphs: Gist, Question, Method, Robots and setup, Results, and
  optionally ablations, limitations or takeaways.
- It is saved to `summaries.json`, `index.html` is rebuilt, and it appears as a dropdown in place
  of the button.
- The dropdown title shows what that API call cost (Opus 5.5 at $4 / $20 per million input / output
  tokens) and the token counts. Papers with a summary get 📝 and that cost on their summary line.
- **🗑️ Erase summary** at the bottom asks for confirmation, then removes it.
- Under the summary are two ways to turn the paper into a web page; each becomes an **Open HTML** link
  (new tab) once made:
- **🐍 Make HTML with python** runs `specific_scripts/pdf_to_html.py` (free, ~15–25 s, no LLM) into
  `htmls_python/<pdf name>/`. PyMuPDF's layout analysis finds title, headings, paragraphs (with bold /
  italics), lists, captions, footnotes, figures, display equations and tables in reading order. Figures,
  equations and tables are cropped from the PDF as images (exact rendering); tables also get their cells
  as text. Inline math stays as plain text (subscripts flatten). Can also be run by hand:
  `uv run python specific_scripts/pdf_to_html.py paper.pdf out_dir`.
- **🌐 Make HTML with Claude** converts the whole paper, appendix included, to a web
  page in `htmls_claude/<pdf name>/index.html`. Claude transcribes the text, tables and equations (as LaTeX,
  rendered with MathJax from a CDN, so viewing needs internet). The figures are the crops in `figs/`,
  copied next to the page. It takes several minutes and needs `serve.py`. Once it exists, the button
  becomes **🌐 Open HTML version ($cost)**, which opens the page in a new tab. Claude can make
  transcription mistakes; the page links back to the PDF.
- **🔗 Find link to paper** (next to the HTML buttons) asks Claude Opus with web search for a public copy of the
  paper that is not on OpenReview, preferring the arXiv abstract page. It needs `serve.py` and takes about
  30 s (about $0.10). The link replaces the button and is saved to `links.json`. If nothing is found, the button says so
  and can be retried. Claude checks title and authors, but a wrong match is possible.
- The API key is read by the server from `secrets/claude_api/claude_api.txt` and never goes into
  the HTML.

## Files

| File | What it is | Made by |
|---|---|---|
| `index.html` | The page. Self-contained: all data is embedded as JSON. | `build.py` |
| `build.py` | Builds `index.html` from the CSV and the JSON files below. | — |
| `../serve.py` | Local server for all sites (`website/serve.py`), at http://127.0.0.1:8026/Corl2026/ (`/` redirects there; other paths are free for more sites). Serves the page (with HTTP Range, for the movies) and handles `POST`/`DELETE /summarize/<id>`, `POST /rate/<id>` and `POST /html_claude/<id>` / `POST /html_python/<id>`. Rebuilds after each change. | — |
| `first_page.json` | Title, abstract and figure paths per paper. | `specific_scripts/extract_first_page.py` |
| `affiliations.json` | Companies and universities per paper, from the PDF header and footnotes, matched with ROR. | `specific_scripts/corl2026_affiliations.py` |
| `openalex.json` | Paper citations, plus author ids and h-index. | `specific_scripts/fetch_corl2026_openalex.py` |
| `github.json` | GitHub repos mentioned before References. | `specific_scripts/corl2026_github.py` |
| `robots.json` | Robots mentioned at least twice before References. | `specific_scripts/corl2026_robots.py` |
| `backbones.json` | Backbone models mentioned at least twice before References. | `specific_scripts/corl2026_backbones.py` |
| `ratings.json` | Your 1–5 star ratings. | `serve.py` |
| `summaries.json` | Claude summaries, empty until you press Summarize. | `serve.py` |
| `links.json` | Non-OpenReview links (`url`, or `null` when none was found), with cost and number of searches. | `serve.py` |
| `htmls_claude/<id>_<title>/` | Claude HTML versions: `index.html`, `figN.png`, `meta.json` (cost, tokens). | `serve.py` |
| `htmls_python/<id>_<title>/` | Python HTML versions: `index.html`, `img/`, `meta.json` (seconds, pages). | `serve.py` → `specific_scripts/pdf_to_html.py` |
| `pdfs/` | The paper PDFs (gitignored). | `OpenreviewScrape/pdf_downloader_CoRL_2026.py` |
| `movies/paper_movies/` | Paper movies `<id>_<title>[_N].<ext>` (~55 GB, gitignored). Only their paths go into `index.html`; `serve.py` streams them with byte ranges so seeking works. | `specific_scripts/corl2026_sort_movies.py` |
| `figs/` | Main figure `<id>.png` and all figures `<id>/fig<N>.png` (~2.5 GB, gitignored). | `extract_first_page.py` |

The paper list itself is `ConferenceTables/robot-learning_org_CoRL_2026_Conference.csv`.

## Rebuilding from scratch

Run from the repo root:

```bash
uv run python OpenreviewScrape/pdf_downloader_CoRL_2026.py     # PDFs -> pdfs/
uv run python specific_scripts/extract_first_page.py           # figures + first_page.json (--limit N to test)
uv run python specific_scripts/corl2026_affiliations.py        # affiliations.json (calls api.ror.org)
uv run python specific_scripts/fetch_corl2026_openalex.py      # openalex.json (calls api.openalex.org)
uv run python specific_scripts/corl2026_github.py              # github.json
uv run python specific_scripts/corl2026_robots.py              # robots.json
uv run python specific_scripts/corl2026_backbones.py           # backbones.json
uv run python website/corl2026/build.py                          # index.html
```

Every step can be re-run on its own. After any step, re-run `build.py` to update the page.

## How the data is derived

- **Figures.**
  - The main figure is the one before the first section; if there is none, Figure 1 wherever it
    appears.
  - The crop grows upward from the caption over graphics and small text, and stops at body text
    or a large gap.
  - 654 of 686 papers have a main figure (6,018 figures in total).
- **Affiliations.**
  - Taken from the page-1 header lines and the marked footnotes, and normalized through the ROR
    affiliation API. ROR's organization type separates universities from companies.
  - Known companies are canonicalized by regex (`COMPANIES` in `corl2026_affiliations.py`).
- **Citations and researchers.**
  - From OpenAlex, using an exact title match.
  - The free tier has a small daily budget per IP, so some papers may be missing. Re-running
    fetches only what is missing; add a free key in `credentials/openalex_key.txt` to avoid the
    limit.
  - OpenAlex sometimes merges namesakes, which can inflate a few h-indexes.
- **Robots.**
  - About 70 hand-written name patterns (`ROBOTS` in `corl2026_robots.py`). Ambiguous words such
    as Spot or Stretch need a robot-like neighbouring word.
  - A robot must be mentioned at least twice before References, so robots cited only in related
    work are ignored.
  - Simulated robots (e.g. the Panda in LIBERO) still count.
  - Robots not on the list are missed. To add one, add a pattern and re-run the script.
- **Backbones.**
  - About 40 hand-written model-name patterns (`BACKBONES` in `corl2026_backbones.py`), with the same
    two-mentions-before-References rule as robots.
  - A model compared against as a baseline counts too, so the filter means "uses or compares with".
    π0 / π0.5 matches ~220 papers for that reason.
  - Models not on the list are missed. To add one, add a pattern and re-run the script.
- **GitHub.**
  - `github.com/owner/repo` links in the PDF text and link annotations before References.
  - The first repo is usually the paper's own; others may be baselines.
- **Presentation type.** The last word of the `venue` field.

## OpenPDF.app (Preview handler)

- `specific_scripts/install_openpdf_handler.sh` builds `~/Applications/OpenPDF.app` and registers
  the `openpdf://` URL scheme.
- It only opens `.pdf` files under this folder's `pdfs/`, and rejects `..` in paths.
- Chrome asks once whether to open it; tick "Always allow".
- Re-run the script if you move the repo. Uninstall with `rm -rf ~/Applications/OpenPDF.app`.
