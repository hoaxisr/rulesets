import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import namedtuple
from datetime import datetime, timezone

SAGER_URL = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-{}.srs"
OWN_URL = "https://raw.githubusercontent.com/hoaxisr/rulesets/master/srs/{}.srs"
TREE_API = "https://api.github.com/repos/{}/git/trees/{}?recursive=1"
NAME = re.compile(r"[A-Za-z0-9._@!-]{1,128}")
MIN_SAGER_NAMES = 1000
# FIRC refuses a list body over 8 MiB (FIRC_SUB_FETCH_MAX_BODY_BYTES) and a catalog over 1 MiB.
MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_CATALOG_BYTES = 512 * 1024

# tree is "owner/repo@ref" listed through the API, or None for this checkout's srs/; path's group 1 is the name;
# floor is the fewest names a listing may have before it is taken for a broken one.
Source = namedtuple("Source", "id url tree path floor")
SOURCES = [
    Source("sagernet", SAGER_URL, "SagerNet/sing-geosite@rule-set", re.compile(r"geosite-(.*)\.srs"), MIN_SAGER_NAMES),
    Source("hoaxisr", OWN_URL, None, re.compile(r"(.*)\.srs"), 0),
]


def names(entries, pattern):
    """entries are paths, or (path, size) pairs; a size FIRC could not fetch drops the file."""
    out = set()
    for e in entries:
        path, size = (e, None) if isinstance(e, str) else e
        if size is not None and not 0 < size <= MAX_LIST_BYTES:
            continue
        m = pattern.fullmatch(path)
        if m and NAME.fullmatch(m.group(1)):
            out.add(m.group(1))
    return sorted(out)


def enough_names(geosite_paths):
    return len(names(geosite_paths, SOURCES[0].path)) >= MIN_SAGER_NAMES


def build(listings, now, old=None):
    """listings maps a source id to its entries, or to None when it could not be listed.

    A source listed short or not at all keeps its names from old; one old does not have is left out.
    Returns the catalog and the ids that were not taken from a fresh listing.
    """
    kept = {(s.get("id"), s.get("url")): s for s in (old or {}).get("sources", [])}
    sources, stale = [], []
    for src in SOURCES:
        entries = listings.get(src.id)
        got = names(entries, src.path) if entries is not None else None
        if got is None or len(got) < src.floor:
            stale.append(src.id)
            prev = kept.get((src.id, src.url))
            if prev is None:
                continue
            got = prev["names"]
        sources.append({"id": src.id, "url": src.url, "names": got})
    return {"generated": now, "sources": sources}, stale


def changed(old, new):
    return old is None or old.get("sources") != new["sources"]


def encode(catalog):
    return json.dumps(catalog, indent=2) + "\n"


def fetch_tree(tree, attempts=3):
    repo, ref = tree.split("@")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(TREE_API.format(repo, ref), headers=headers)
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
            break
        except OSError as e:
            # A 4xx (a branch not created yet, a rate limit) does not get better by asking again.
            if i == attempts - 1 or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
                raise
            time.sleep(5 * (i + 1))
    if body.get("truncated"):
        raise ValueError(tree + " tree is truncated")
    return [(e["path"], e.get("size")) for e in body["tree"] if e["type"] == "blob"]


def list_sources(root):
    out = {}
    for src in SOURCES:
        try:
            if src.tree is None:
                d = os.path.join(root, "srs")
                out[src.id] = [(f, os.path.getsize(os.path.join(d, f))) for f in os.listdir(d)]
            else:
                out[src.id] = fetch_tree(src.tree)
        except (OSError, ValueError, KeyError) as e:
            print("::warning::%s not listed: %s" % (src.id, e), file=sys.stderr)
            out[src.id] = None
    return out


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "catalog.json")
    try:
        with open(out) as f:
            old = json.load(f)
    except FileNotFoundError:
        old = None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new, stale = build(list_sources(root), now, old)
    for sid in stale:
        print("::warning::%s listing missing or too small, previous names kept" % sid, file=sys.stderr)
    if not changed(old, new):
        print("catalog unchanged")
        return 0
    body = encode(new)
    if len(body.encode()) > MAX_CATALOG_BYTES:
        print("catalog is %d bytes, over %d; catalog kept" % (len(body.encode()), MAX_CATALOG_BYTES), file=sys.stderr)
        return 1
    with open(out, "w") as f:
        f.write(body)
    print("catalog written:", {s["id"]: len(s["names"]) for s in new["sources"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
