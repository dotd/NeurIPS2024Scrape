"""Serve the conference viewers and force-download PDFs.

Browsers can't force-download a cross-origin PDF from a file:// page, and
OpenReview now gates PDF URLs behind a bot challenge anyway. This serves
htmls/ over http and proxies /dl?id=<note_id>&n=<name> using the
authenticated OpenReview client (get_pdf), returning the bytes with an
attachment disposition so the download button saves instead of opening.

    uv run python specific_scripts/serve_conferences.py
    # then open http://localhost:8000/all_conferences_filter_short.html
"""

import http.server
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "OpenreviewScrape"))
import openreview_utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTMLS = os.path.join(ROOT, "htmls")
CREDS = os.path.join(ROOT, "credentials", "openreview_api.txt")
PORT = 8000

client = openreview_utils.get_client(CREDS)


def get_pdf_reauth(note_id):
    """get_pdf, re-logging in once if the cached token has expired."""
    global client
    try:
        return client.get_pdf(note_id)
    except Exception:
        client = openreview_utils.get_client(CREDS)  # token expires periodically; refresh
        return client.get_pdf(note_id)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HTMLS, **k)

    def do_GET(self):
        if self.path.startswith("/dl?"):
            return self.proxy_download()
        return super().do_GET()

    def proxy_download(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        note_id = (q.get("id") or [""])[0]
        name = (q.get("n") or ["paper.pdf"])[0]
        if not note_id:
            self.send_error(400, "missing note id")
            return
        try:
            data = get_pdf_reauth(note_id)
        except Exception as e:
            self.send_error(502, f"fetch failed: {e}")
            return
        safe = name.replace('"', "").replace("\n", " ")
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    os.chdir(HTMLS)
    print(f"Serving {HTMLS} at http://localhost:{PORT}")
    print(f"Open http://localhost:{PORT}/all_conferences_filter_short.html")
    http.server.ThreadingHTTPServer(("", PORT), Handler).serve_forever()
