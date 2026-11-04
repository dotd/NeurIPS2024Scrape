"""Pull the videos out of CoRL 2026 supplementary material into website/corl2026/movies/.

For each paper with supplementary material, download the zip from OpenReview, extract every video in it
to movies/<id>_<title>.<ext> (_2, _3... when there are several) and drop the rest of the zip.
movies/index.json maps note id -> saved files ([] when the zip has no video), so reruns skip done papers.

    uv run python specific_scripts/corl2026_movies.py              # all papers
    uv run python specific_scripts/corl2026_movies.py Glj2RSQIS4   # just these note ids
"""

import io
import json
import os
import pickle
import re
import sys
import time
import zipfile

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "OpenreviewScrape"))
import openreview_utils

PKL = os.path.join(ROOT, "ConferencesData", "robot-learning_org_CoRL_2026_Conference.pkl")
CREDS = os.path.join(ROOT, "credentials", "openreview_api.txt")
OUT = os.path.join(ROOT, "website", "corl2026", "movies")
INDEX = os.path.join(OUT, "index.json")
MIN_GAP = 26  # s between downloads: OpenReview allows ~140 requests/hour
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".gif"}

_client = [None]


def get_supp(note_id):
    """Supplementary bytes. Plain requests with a timeout: the openreview client has none and hung for hours."""
    for attempt in range(5):
        if _client[0] is None:
            _client[0] = openreview_utils.get_client(CREDS)
        try:
            r = requests.get("https://api2.openreview.net/attachment", timeout=(30, 120),
                             params={"id": note_id, "name": "supplementary_materials"},
                             headers={"Authorization": f"Bearer {_client[0].token}"})
        except requests.RequestException as e:
            print(f"  {note_id}: {e}, retrying")
            continue
        if r.status_code == 429:  # rate limited: wait it out
            print(f"  {note_id}: rate limited, sleeping 10 min")
            time.sleep(600)
        elif r.status_code in (401, 403):
            _client[0] = None  # expired token: log in again
        else:
            r.raise_for_status()
            return r.content
    raise RuntimeError("gave up after 5 attempts")


def safe(s, n=90):
    return re.sub(r"[\\/:*?\"<>|]+", " ", s).strip()[:n]


def extract_videos(data, stem):
    """Write each video in the zip bytes to OUT/stem[_k].ext; returns the saved file names."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = [m for m in z.infolist() if not m.is_dir() and "__MACOSX" not in m.filename
                   and os.path.splitext(m.filename)[1].lower() in VIDEO_EXT]
        members.sort(key=lambda m: -m.file_size)  # biggest first: likely the main video
        saved = []
        for k, m in enumerate(members, 1):
            name = f"{stem}{'' if k == 1 else f'_{k}'}{os.path.splitext(m.filename)[1].lower()}"
            with z.open(m) as src, open(os.path.join(OUT, name), "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            saved.append(name)
        return saved


def main():
    os.makedirs(OUT, exist_ok=True)
    index = json.load(open(INDEX)) if os.path.exists(INDEX) else {}
    notes = [n for n in pickle.load(open(PKL, "rb")) if n.content.get("supplementary_materials", {}).get("value")]
    if sys.argv[1:]:
        notes = [n for n in notes if n.id in sys.argv[1:]]
    todo = [n for n in notes if n.id not in index]
    print(f"{len(notes)} papers with supplementary material, {len(todo)} to do")

    last = 0
    for i, n in enumerate(todo, 1):
        title = n.content["title"]["value"]
        time.sleep(max(0, last + MIN_GAP - time.time()))
        last = time.time()
        try:
            data = get_supp(n.id)
            if data[:4] == b"PK\x03\x04":
                saved = extract_videos(data, f"{n.id}_{safe(title)}")
            else:  # ponytail: every CoRL 2026 supplement is a zip; a bare video would land here as unknown
                print(f"  {n.id}: not a zip, skipped")
                continue
        except Exception as e:
            print(f"  {n.id}: failed ({e})")
            continue
        index[n.id] = saved
        json.dump(index, open(INDEX, "w"), indent=1)
        print(f"[{i}/{len(todo)}] {n.id} {len(data) >> 20} MB -> {saved or 'no video'}")

    have = sum(1 for v in index.values() if v)
    print(f"done: {have} papers with video, {len(index) - have} without")


if __name__ == "__main__":
    main()
