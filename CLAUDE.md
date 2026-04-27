# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenReview conference paper scraper focused on NeurIPS, ICML, ICLR, and CoRL (2024-2026). Downloads paper metadata, PDFs, and spotlight videos from the OpenReview API, exports to tab-separated CSV/HTML reports, and optionally uploads to Google Sheets.

## Setup

```bash
pip install -r requirements.txt
```

Requires OpenReview credentials at `credentials/openreview_api.txt` (line 1: email, line 2: password). Google Drive features additionally need `credentials/mycreds.txt` and `credentials/client_secret2.json`.

## Running

```bash
# Main pipeline (scrape, download PDFs, download videos)
python OpenreviewScrape/run_pipeline.py

# Post-process already-scraped CSVs into HTML report with keyword filter
python tst/tst_robotic_papers.py

# Build HTML report directly from pickled CoRL notes
python tst/tst_corl_2024_html.py
```

## Architecture

**Data flow:**
1. OpenReview API → pickle cache (`ConferencesData/<venue>.pkl`)
2. Pickled notes → filtered by venue string → tab-separated CSV (`ConferencesData/<venue>.csv`)
3. CSV → HTML report (`htmls/`) with optional keyword filtering

**Modules:**
- **`OpenreviewScrape/definitions.py`** — `PROJECT_ROOT_DIR`, `PACKAGE_ROOT_DIR`, custom Unicode separators (``, ``), `config.txt` loading
- **`OpenreviewScrape/openreview_utils.py`** — Auth, `get_conference()` (cache-first), `get_notes_helper()` (multi-format fallback), venue/title normalization
- **`OpenreviewScrape/pdf_downloader.py`** — `PDFDownloader` class: retry + exponential backoff, skip-if-exists, tqdm progress
- **`OpenreviewScrape/drive_utils.py`** — Google Drive OAuth (PyDrive2), folder listing, Sheets API integration
- **`OpenreviewScrape/run_pipeline.py`** — Top-level orchestrator: `venues` list config, `scrape_conference()`, multiprocessing PDF download, video download + ffmpeg script generation

**`tst/` scripts** (standalone, not a test suite):
- `tst_basic.py` — Minimal scrape example, writes to `data/` (not `ConferencesData/`)
- `tst_robotic_papers.py` — Reads from `ConferencesData/*.csv`, filters by keywords, generates HTML
- `tst_corl_2024_html.py` — Reads directly from `ConferencesData/*.pkl`, generates HTML with video links

## Key Patterns

**To add/change venues:** Edit the `venues` list at the top of `run_pipeline.py`. Venue IDs follow OpenReview's format (e.g., `"ICLR.cc/2026/Conference"`).

**Cache invalidation:** Delete `ConferencesData/<normalized_venue_id>.pkl` to force a fresh API fetch. Normalization replaces `/`, `:`, `.`, ` ` with `_`.

**Paper filtering:** `scrape_conference()` keeps only notes whose `venue` field contains `poster`, `spotlight`, `talk`, `oral`, or `corl 2024` (case-insensitive). Notes not matching any filter are skipped entirely and won't appear in output CSVs.

**CSV column order matters:** `tst_robotic_papers.py` hardcodes `expected_fields = 9` and maps columns positionally. If you change the `fields` list in `run_pipeline.py`, update `tst_robotic_papers.py`'s column list to match.

**PDF URL selection:** `get_pdfs_names_and_urls()` returns `(filename, pdf_url_full, pdf_url_by_id)` tuples. The download pipeline uses `pdf_url_by_id` (`/pdf?id=<note_id>`), not the direct path URL.

**API fallbacks:** `get_notes_helper()` tries `/-/Submission` first, then `/-/Paper`, `/-/Final_Decision`, `/-/Final_Submission` — OpenReview's invitation format varies by venue year.

**ffmpeg script:** `download_spotlight_videos_pipeline()` generates `ConferencesData/<venue>_spotlight_videos/command.sh` to concatenate all downloaded `.mp4` files into `output.mp4`.

**Output locations:**
- `ConferencesData/` — pickle caches, processed CSVs, PDF subdirectories, video subdirectories
- `htmls/` — generated HTML reports
- `logs/` — timestamped + rolling `latest` log files
