"""Find GitHub repos mentioned in each CoRL 2026 PDF (text + link annotations, before References).

Writes htmls/corl2026/github.json: {paper_id: [repo urls]}; htmls/corl2026/build.py adds them as a column.

    uv run python specific_scripts/corl2026_github.py
"""

import glob
import json
import os
import re

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "htmls", "corl2026")
OUT = os.path.join(HERE, "github.json")
# owner/repo; text extraction may put spaces after '/' at line breaks
REPO_RE = re.compile(r"github\.com/\s*([A-Za-z0-9-]+)/\s*([A-Za-z0-9._-]+)", re.I)
REFS_RE = re.compile(r"^\s*(References|Bibliography)\s*$", re.M | re.I)
NOT_OWNER = {"features", "about", "orgs", "topics", "sponsors", "settings", "marketplace"}


def repos(path):
    found = {}
    with pymupdf.open(path) as doc:
        for page in doc:
            text = page.get_text()
            refs = REFS_RE.search(text)
            # ponytail: links on the References page itself are kept only above the heading by y-position
            refs_y = page.search_for(refs.group(1))[0].y0 if refs and page.search_for(refs.group(1)) else None
            uris = [l["uri"] for l in page.get_links()
                    if l.get("uri") and (refs_y is None or l["from"].y0 < refs_y)]
            for s in uris + [text[:refs.start()] if refs else text]:
                for owner, repo in REPO_RE.findall(s):
                    repo = re.sub(r"(\.git|[.,;:)]+)$", "", repo)
                    if owner.lower() not in NOT_OWNER and repo:
                        found.setdefault(f"{owner}/{repo}".lower(), f"https://github.com/{owner}/{repo}")
            if refs:
                break
    return list(found.values())


def main():
    out = {}
    for p in sorted(glob.glob(os.path.join(HERE, "pdfs", "*.pdf"))):
        r = repos(p)
        if r:
            out[os.path.basename(p).split("_", 1)[0]] = r
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(out)} papers with GitHub repos, {sum(map(len, out.values()))} repos -> {OUT}")


if __name__ == "__main__":
    assert REPO_RE.findall("code: https://github.com/ foo/bar-baz.") == [("foo", "bar-baz.")]
    main()
