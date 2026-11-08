"""CoRL 2026 videos on YouTube: find the authors' own YouTube videos, put them in a playlist on your channel,
and list who to ask for permission when a paper's video is only in its OpenReview supplementary material.

    uv run python specific_scripts/corl2026_youtube.py find       # PDFs + project pages -> movies/youtube.json (free)
    uv run python specific_scripts/corl2026_youtube.py check      # print paper title vs video title, to spot wrong matches
    uv run python specific_scripts/corl2026_youtube.py playlist   # add them to a public playlist (browser login once)
    uv run python specific_scripts/corl2026_youtube.py contacts   # movies/permission_contacts.csv + permission_email.txt

Re-uploading the supplementary videos needs the authors' permission; a playlist of their own YouTube videos doesn't.
playlist needs credentials/client_secret2.json (the Drive OAuth client) with "YouTube Data API v3" enabled in its
Google Cloud project; the token is cached in credentials/youtube_token.json. Each added video costs 50 of the
10,000 daily API units (~190 a day), so a long run stops at the quota and the next day's run continues.
"""

import concurrent.futures
import csv
import glob
import json
import os
import re
import sys

import httplib2
import pymupdf
import requests
from googleapiclient.discovery import build as yt_build
from googleapiclient.errors import HttpError
from oauth2client import client, file, tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "website", "corl2026")
sys.path.insert(0, HERE)
import build  # noqa: E402  (website/corl2026/build.py: csv_rows)

MOVIES = os.path.join(HERE, "movies")
STATE = os.path.join(MOVIES, "youtube.json")  # {"videos": {pid: [video ids]}, "playlist": id, "added": [pid]}
SECRET = os.path.join(ROOT, "credentials", "client_secret2.json")
TOKEN = os.path.join(ROOT, "credentials", "youtube_token.json")
PLAYLIST_TITLE = "CoRL 2026 paper videos"
YT_RE = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
EMAIL_TEMPLATE = """Subject: Sharing your CoRL 2026 video: "{title}"

Hi,

I enjoyed your CoRL 2026 paper "{title}". I'm putting together a public YouTube playlist of
CoRL 2026 paper videos, and your supplementary video isn't on YouTube yet.

Would you be OK with me uploading it to my channel, credited to you, with a link to the paper
and your project page? If you'd rather upload it yourself, send me the link and I'll add that instead.

Thanks,
"""


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"videos": {}, "playlist": None, "added": []}


def save_state(state):
    json.dump(state, open(STATE, "w"), indent=1)


def papers():
    """pid -> {title, authors} from the scraped CoRL 2026 CSV."""
    columns, rows = build.csv_rows()
    return {r[0].split("id=")[-1]: dict(zip(columns, r)) for r in rows}


def with_movies():
    """Note ids whose supplementary material has a video."""
    return [pid for pid, files in json.load(open(os.path.join(MOVIES, "index.json"))).items() if files]


def pdf_text(pid):
    """(text, link targets) of the paper's PDF, or ("", []) if it's missing or unreadable."""
    pdfs = glob.glob(os.path.join(glob.escape(os.path.join(HERE, "pdfs")), glob.escape(pid) + "_*.pdf"))
    try:
        doc = pymupdf.open(pdfs[0])
        return "".join(p.get_text() for p in doc), [l.get("uri") or "" for p in doc for l in p.get_links()]
    except (IndexError, RuntimeError, ValueError):
        return "", []


def project_pages(text, links):
    # ponytail: heuristic (github.io / sites.google / "project" in URL); misses custom domains
    urls = dict.fromkeys(u.rstrip(".,;") for u in links + URL_RE.findall(text) if u.startswith("http"))
    return [u for u in urls if "github.io" in u or "sites.google" in u or "project" in u.lower()][:3]


def find_one(pid):
    """YouTube ids linked from the PDF, else embedded on its project page(s)."""
    text, links = pdf_text(pid)
    if ids := list(dict.fromkeys(YT_RE.findall(text + "\n" + "\n".join(links)))):
        return pid, ids
    for u in project_pages(text, links):
        try:
            html = requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text
        except requests.RequestException:
            continue
        if ids := list(dict.fromkeys(YT_RE.findall(html))):
            return pid, ids
    return pid, []


def find():
    state = load_state()
    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        state["videos"] = {pid: ids for pid, ids in ex.map(find_one, with_movies()) if ids}
    save_state(state)
    print(f"{len(state['videos'])} of {len(with_movies())} papers with a video have one on YouTube -> {STATE}")


def youtube():
    """YouTube API client; opens the browser for Google login the first time."""
    if not os.path.exists(SECRET):
        sys.exit(f"missing {SECRET}: download the OAuth client JSON from Google Cloud Console")
    store = file.Storage(TOKEN)
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets(SECRET, "https://www.googleapis.com/auth/youtube")
        creds = tools.run_flow(flow, store, tools.argparser.parse_args([]))
    return yt_build("youtube", "v3", http=creds.authorize(httplib2.Http()))


def check():
    """Paper title next to the first video's title, to catch a project page that embeds someone else's video."""
    state, info, yt = load_state(), papers(), youtube()
    first = {pid: ids[0] for pid, ids in state["videos"].items()}
    titles = {}
    ids = list(first.values())
    for i in range(0, len(ids), 50):  # 1 API unit per 50 videos
        for v in yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()["items"]:
            titles[v["id"]] = v["snippet"]["title"]
    for pid, vid in first.items():
        print(f"{pid}  {info.get(pid, {}).get('title', '?')[:60]:60}  |  {titles.get(vid, '(gone/private)')[:60]}")


def playlist():
    state, info, yt = load_state(), papers(), youtube()
    if not state["playlist"]:
        body = {"snippet": {"title": PLAYLIST_TITLE, "description": "Videos made by the authors of CoRL 2026 papers."},
                "status": {"privacyStatus": "public"}}
        state["playlist"] = yt.playlists().insert(part="snippet,status", body=body).execute()["id"]
        save_state(state)
    for pid, ids in state["videos"].items():
        if pid in state["added"]:
            continue
        body = {"snippet": {"playlistId": state["playlist"], "resourceId": {"kind": "youtube#video", "videoId": ids[0]}}}
        try:
            yt.playlistItems().insert(part="snippet", body=body).execute()
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("daily API quota reached; rerun tomorrow to continue")
                break
            print(f"skip {pid} ({info.get(pid, {}).get('title', '?')[:50]}): {e.reason}")  # deleted / private video
            continue
        state["added"].append(pid)
        save_state(state)  # after each, so an interrupted run resumes where it stopped
    print(f"{len(state['added'])} videos in https://www.youtube.com/playlist?list={state['playlist']}")


def contacts():
    """Papers with a supplementary video but none on YouTube: who to ask, and the email to send."""
    state, info = load_state(), papers()
    out = os.path.join(MOVIES, "permission_contacts.csv")
    todo = [pid for pid in with_movies() if pid not in state["videos"]]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "authors", "emails in PDF", "project page", "openreview"])
        for pid in todo:
            text, links = pdf_text(pid)
            emails = "; ".join(dict.fromkeys(e.lower() for e in EMAIL_RE.findall(text[:6000])))  # first page or so
            p = info.get(pid, {})
            w.writerow([pid, p.get("title", ""), p.get("authors", ""), emails, " ".join(project_pages(text, links)),
                        f"https://openreview.net/forum?id={pid}"])
    open(os.path.join(MOVIES, "permission_email.txt"), "w").write(EMAIL_TEMPLATE)
    print(f"{len(todo)} papers -> {out}; email template -> {os.path.join(MOVIES, 'permission_email.txt')}")


if __name__ == "__main__":
    {"find": find, "check": check, "playlist": playlist, "contacts": contacts}[sys.argv[1]]()
