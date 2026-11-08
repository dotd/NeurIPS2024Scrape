"""Google Drive links for the CoRL 2026 movies: list the shared Drive folder holding movies/paper_movies/ into
website/corl2026/drive_movies.json = {"folder": url, "files": {file name: Drive file id}}; build.py links each movie.

The folder is shared by link, so its public embedded view lists every file; no login needed.

    uv run python specific_scripts/corl2026_drive_movies.py && uv run python website/corl2026/build.py
"""

import html
import json
import os
import re

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "website", "corl2026", "drive_movies.json")
FOLDER = "1W8o5NEXjVEeCV68ctOshicE2bKfV7x6C"
ENTRY_RE = re.compile(r'<a href="https://drive\.google\.com/file/d/([\w-]+)/[^"]*"[^>]*>.*?'
                      r'<div class="flip-entry-title">([^<]*)</div>', re.S)


def main():
    page = requests.get(f"https://drive.google.com/embeddedfolderview?id={FOLDER}", timeout=60).text
    files = {html.unescape(name): fid for fid, name in ENTRY_RE.findall(page)}
    assert files, "no files found: is the folder still shared by link?"
    json.dump({"folder": f"https://drive.google.com/drive/folders/{FOLDER}", "files": files},
              open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"{len(files)} movies -> {OUT}")


if __name__ == "__main__":
    main()
