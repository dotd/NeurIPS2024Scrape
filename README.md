# OpenReview Conference Scrape

Scrapes conference paper data (NeurIPS, ICML, ICLR, CoRL) from the
OpenReview API: paper metadata to CSV, plus optional PDF and spotlight
video downloads.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Install dependencies:

```bash
uv sync
```

### OpenReview credentials

Create `./credentials/openreview_api.txt` with your OpenReview account:

```
<EMAIL>
<PASSWORD>
```

Google Drive/Sheets features additionally need `credentials/mycreds.txt`
and `credentials/client_secret2.json`.

## Running

```bash
# Main pipeline: scrape papers to ConferencesData/<venue>.csv
uv run python OpenreviewScrape/run_pipeline.py

# Post-process scraped CSVs into an HTML report with keyword filtering
uv run python tst/tst_robotic_papers.py

# Build HTML report directly from pickled CoRL notes
uv run python tst/tst_corl_2024_html.py
```

### Choosing conferences

Edit the `venues` list at the top of `OpenreviewScrape/run_pipeline.py`,
e.g.:

```python
venues = [
    "ICML.cc/2026/Conference",
]
```

To also download PDFs / spotlight videos, flip the flags in `main()`:

```python
scrape_conferences_pipeline(download_pdfs=True, download_spotlight_videos=True, limit_names_and_urls=10000)
```

### Cache

API responses are cached in `ConferencesData/<venue>.pkl`. Delete the
`.pkl` to force a fresh fetch (e.g. after decisions are released):

```bash
rm ConferencesData/ICML_cc_2026_Conference.pkl
```

## Scraped data (`ConferenceTables/`)

Paper counts per CSV, as of July 2026:

| Conference | Total | Poster | Spotlight | Oral | Other |
|---|---:|---:|---:|---:|---|
| ICLR 2024 | 2,260 | 1,807 | 367 | 86 | — |
| ICLR 2025 | 3,704 | 3,111 | 380 | 213 | — |
| ICLR 2026 | 5,357 | 5,119 | — | 223 | 14 conditional poster, 1 conditional oral |
| ICML 2024 | 2,614 | 2,275 | 191 | 144 | 4 malformed rows (venue field missing) |
| ICML 2025 | 3,258 | 2,938 | 212 ("spotlightposter") | 108 | — |
| ICML 2026 | 6,559 | 5,805 ("regular") | 536 | — | 218 "Submitted to ICML 2026" |
| NeurIPS 2023 | 3,218 | 2,773 | 378 | 67 | — |
| NeurIPS 2024 | 4,035 | 3,648 | 326 | 61 | — |
| NeurIPS 2025 | 5,543 | 4,522 | 687 | 77 | 254 submitted/rejected, 2 withdrawn, 1 desk-rejected |

Notes: 2023–2025 files have 9 columns (venue at index 4); newer files
(ICLR/ICML 2026, NeurIPS 2025) have 11 columns (venue at index 5).
ICML 2026 oral decisions were not yet released. NeurIPS 2025 and
ICML 2026 include non-accepted papers since the pipeline doesn't
filter by decision.

## Output

- `ConferencesData/` — pickle caches, CSVs, PDFs, videos
- `htmls/` — generated HTML reports
- `logs/` — log files
