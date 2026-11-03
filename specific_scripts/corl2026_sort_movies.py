"""Sort htmls/corl2026/movies/ by length: >= 30 s into paper_movies/ (explainer videos), shorter into samples/.

Only moves files of papers already listed in movies/index.json, so a paper corl2026_movies.py is still
extracting is left alone; safe to run while it downloads, and again once it finishes.

    uv run python specific_scripts/corl2026_sort_movies.py
"""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVIES = os.path.join(ROOT, "htmls", "corl2026", "movies")
MIN_LEN = 30  # seconds; ponytail: length alone decides explainer vs sample


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out and out != "N/A" else None


def main():
    for d in ("paper_movies", "samples"):
        os.makedirs(os.path.join(MOVIES, d), exist_ok=True)
    done = {name for names in json.load(open(os.path.join(MOVIES, "index.json"))).values() for name in names}
    moved = {"paper_movies": 0, "samples": 0}
    for name in sorted(done):
        src = os.path.join(MOVIES, name)
        if not os.path.exists(src):
            continue  # already sorted
        sec = duration(src)
        if sec is None:
            print(f"  no duration, left in place: {name}")
            continue
        d = "paper_movies" if sec >= MIN_LEN else "samples"
        shutil.move(src, os.path.join(MOVIES, d, name))
        moved[d] += 1
    print(f"moved {moved['paper_movies']} to paper_movies/, {moved['samples']} to samples/")


if __name__ == "__main__":
    main()
