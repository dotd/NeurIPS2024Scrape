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

## Output

- `ConferencesData/` — pickle caches, CSVs, PDFs, videos
- `htmls/` — generated HTML reports
- `logs/` — log files
