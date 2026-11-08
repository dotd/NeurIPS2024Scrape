"""Copy the CoRL 2026 browser into a checkout of the GitHub Pages repo (dotd.github.io), at <repo>/corl2026/.

The page goes as is, minus your local folder path; figures go as WebP thumbnails (<=900 px wide, ~8x smaller than the
PNGs) so they fit GitHub Pages' ~1 GB site limit. PDFs and movies stay local. Commit + push the repo afterwards.

    uv run python website/corl2026/build.py
    uv run python specific_scripts/publish_corl2026_pages.py <path to dotd.github.io checkout>
"""

import concurrent.futures
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "website", "corl2026")
MAX_W = 900


def to_webp(src, dst, w):
    if os.path.exists(dst):  # done on an earlier run
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    resize = ["-resize", str(MAX_W), "0"] if w > MAX_W else []  # never upscale
    subprocess.run(["cwebp", "-quiet", "-q", "70", *resize, src, "-o", dst], check=True)


def main(repo):
    out = os.path.join(repo, "corl2026")
    first = json.load(open(os.path.join(HERE, "first_page.json")))
    jobs = {}  # relative png path -> width (0 = unknown, resize to be safe)
    for v in first.values():
        if v.get("figure"):
            jobs.setdefault(v["figure"], 10 ** 6)
        for f in v.get("figures", []):
            jobs[f["src"]] = f.get("w", 10 ** 6)
    jobs = {p: w for p, w in jobs.items() if os.path.exists(os.path.join(HERE, p))}
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as ex:
        list(ex.map(lambda p: to_webp(os.path.join(HERE, p), os.path.join(out, p[:-4] + ".webp"), jobs[p]), jobs))

    page = open(os.path.join(HERE, "index.html")).read()
    page = re.sub(r'"here": "[^"]*"', '"here": ""', page, count=1)  # only used to open PDFs from your disk
    page = re.sub(r'"(figs/[^"]+)\.png"', r'"\1.webp"', page)
    assert os.path.expanduser("~") not in page, "a local path is still in the page"
    open(os.path.join(out, "index.html"), "w").write(page)
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
    print(f"{len(jobs)} figures + index.html -> {out} ({size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main(sys.argv[1])
