import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

SAGER_URL = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-{}.srs"
OWN_URL = "https://raw.githubusercontent.com/hoaxisr/rulesets/master/srs/{}.srs"
TREE_API = "https://api.github.com/repos/SagerNet/sing-geosite/git/trees/rule-set"
NAME = re.compile(r"[A-Za-z0-9._@!-]{1,128}")
GEOSITE = re.compile(r"geosite-(.*)\.srs")
OWN = re.compile(r"(.*)\.srs")


def names(paths, pattern):
    out = set()
    for p in paths:
        m = pattern.fullmatch(p)
        if m and NAME.fullmatch(m.group(1)):
            out.add(m.group(1))
    return sorted(out)


def build(geosite_paths, own_files, now):
    return {
        "generated": now,
        "sources": [
            {"id": "sagernet", "url": SAGER_URL, "names": names(geosite_paths, GEOSITE)},
            {"id": "hoaxisr", "url": OWN_URL, "names": names(own_files, OWN)},
        ],
    }


def changed(old, new):
    return old is None or old.get("sources") != new["sources"]


def fetch_tree():
    req = urllib.request.Request(
        TREE_API,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        tree = json.load(r)
    if tree.get("truncated"):
        raise SystemExit("sing-geosite tree is truncated")
    return [e["path"] for e in tree["tree"] if e["type"] == "blob"]


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "catalog.json")
    try:
        with open(out) as f:
            old = json.load(f)
    except FileNotFoundError:
        old = None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = build(fetch_tree(), os.listdir(os.path.join(root, "srs")), now)
    if not changed(old, new):
        print("catalog unchanged")
        return 0
    with open(out, "w") as f:
        json.dump(new, f, indent=2)
        f.write("\n")
    print("catalog written:", {s["id"]: len(s["names"]) for s in new["sources"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
