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
RAW_PREFIX = "https://raw.githubusercontent.com/"
TREE_API = "https://api.github.com/repos/{}/git/trees/{}?recursive=1"
NAME = re.compile(r"[A-Za-z0-9._@!-]{1,128}")
ID = re.compile(r"[a-z0-9-]{1,32}")
TREE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[A-Za-z0-9_./-]+")
MIN_SAGER_NAMES = 1000
# FIRC refuses a list body over 8 MiB (FIRC_SUB_FETCH_MAX_BODY_BYTES) and a catalog over 1 MiB.
MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_CATALOG_BYTES = 512 * 1024
MAX_PROVIDERS = 64  # Includes the two built-in sources.
# Optional providers: scripts/providers/<id>.json in, catalog/<id>.json out. A router fetches a provider's file only
# once its owner turns that provider on; catalog.json carries the built-in sources and the list of providers.
PROVIDERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "providers")
CATALOG_DIR = "catalog"

# tree is "owner/repo@ref" listed through the API, or None for this checkout's srs/; path's group 1 is the name;
# floor is the fewest names a listing may have before it is taken for a broken one.
Source = namedtuple("Source", "id url tree path floor")
SOURCES = [
    Source("sagernet", SAGER_URL, "SagerNet/sing-geosite@rule-set", re.compile(r"geosite-(.*)\.srs"), MIN_SAGER_NAMES),
    Source("hoaxisr", OWN_URL, None, re.compile(r"(.*)\.srs"), 0),
]
BUILTIN_NAMES = {"sagernet": "SagerNet", "hoaxisr": "hoaxisr"}
Provider = namedtuple("Provider", "id name sources")


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


def build(listings, now, old=None, sources=SOURCES):
    """listings maps a source id to its entries, or to None when it could not be listed.

    A source listed short or not at all keeps its names from old; one old does not have is left out.
    Returns the catalog and the ids that were not taken from a fresh listing.
    """
    kept = {(s.get("id"), s.get("url")): s for s in (old or {}).get("sources", [])}
    out, stale = [], []
    for src in sources:
        entries = listings.get(src.id)
        got = names(entries, src.path) if entries is not None else None
        if got is None or len(got) < src.floor:
            stale.append(src.id)
            prev = kept.get((src.id, src.url))
            if prev is None:
                continue
            got = prev["names"]
        out.append({"id": src.id, "url": src.url, "names": got})
    return {"generated": now, "sources": out}, stale


def build_all(listings, now, providers, old=None, old_files=None):
    """catalog.json plus one catalog per provider that has any source; a provider with none is not listed."""
    main, stale = build(listings, now, old)
    files = {}
    for p in providers:
        got, missed = build(listings, now, (old_files or {}).get(p.id), p.sources)
        stale += missed
        if got["sources"]:
            files[p.id] = got
    main["providers"] = [{"id": s.id, "name": BUILTIN_NAMES[s.id]} for s in SOURCES] + [
        {"id": p.id, "name": p.name} for p in providers if p.id in files]
    return main, files, stale


def check_provider(pid, data):
    """A provider file, checked against the rules FIRC applies to the catalog it becomes."""
    def bad(why):
        raise ValueError("provider %s: %s" % (pid, why))
    if not ID.fullmatch(pid) or pid in BUILTIN_NAMES:
        bad("its file name is not a free id")
    if not isinstance(data, dict) or set(data) - {"name", "sources"}:
        bad("only name and sources are allowed")
    name = data.get("name")
    if not isinstance(name, str) or not name.isprintable() or not 0 < len(name.encode("utf-8")) <= 32:
        bad("name is printable and between 1 and 32 UTF-8 bytes")
    if not isinstance(data.get("sources"), list) or not data["sources"]:
        bad("sources is a non-empty list")
    out = []
    for s in data["sources"]:
        if not isinstance(s, dict) or set(s) != {"id", "url", "tree", "path", "floor", "examples"}:
            bad("a source has exactly id, url, tree, path, floor and examples")
        sid = s["id"]
        if not isinstance(sid, str) or not ID.fullmatch(sid) or not (sid == pid or sid.startswith(pid + "-")):
            bad("source id %r is not %s or %s-..." % (sid, pid, pid))
        url = s["url"]
        if not isinstance(url, str) or not url.startswith(RAW_PREFIX) or url.count("{}") != 1:
            bad("%s url is not on raw.githubusercontent.com with one {}" % sid)
        if not isinstance(s["tree"], str) or not TREE.fullmatch(s["tree"]):
            bad("%s tree is not owner/repo@ref" % sid)
        try:
            path = re.compile(s["path"])
        except (re.error, TypeError):
            bad("%s path is not a regular expression" % sid)
        if path.groups != 1:
            bad("%s path has to capture exactly the name" % sid)
        if not isinstance(s["floor"], int) or isinstance(s["floor"], bool) or s["floor"] < 1:
            bad("%s floor is a positive number" % sid)
        ex = s["examples"]
        if not isinstance(ex, dict) or not any(v is not None for v in ex.values()):
            bad("%s examples map paths to names (or null), at least one name" % sid)
        for p, want in ex.items():
            got = names([p], path)
            if got != ([want] if want is not None else []):
                bad("%s path %r gives %r, not %r" % (sid, p, got, want))
        out.append(Source(sid, url, s["tree"], path, s["floor"]))
    return Provider(pid, name, out)


def load_providers(directory=PROVIDERS_DIR):
    providers, seen = [], {s.id for s in SOURCES}
    for f in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        if not f.endswith(".json"):
            continue
        with open(os.path.join(directory, f), encoding="utf-8") as fh:
            p = check_provider(f[:-5], json.load(fh))
        for s in p.sources:
            if s.id in seen:
                raise ValueError("source id %s is used twice" % s.id)
            seen.add(s.id)
        providers.append(p)
    if len(providers) + len(SOURCES) > MAX_PROVIDERS:
        raise ValueError("more than %d providers, including built-ins" % MAX_PROVIDERS)
    return providers


def changed(old, new):
    strip = lambda c: {k: v for k, v in c.items() if k != "generated"}
    return old is None or strip(old) != strip(new)


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


def list_sources(root, sources=SOURCES):
    out, trees = {}, {}
    for src in sources:
        try:
            if src.tree is None:
                d = os.path.join(root, "srs")
                out[src.id] = [(f, os.path.getsize(os.path.join(d, f))) for f in os.listdir(d)]
            else:
                if src.tree not in trees:  # sources of one provider often share a tree
                    try:
                        trees[src.tree] = fetch_tree(src.tree)
                    except (OSError, ValueError, KeyError) as e:
                        trees[src.tree] = e
                tree = trees[src.tree]
                if isinstance(tree, Exception):
                    raise tree
                out[src.id] = tree
        except (OSError, ValueError, KeyError) as e:
            print("::warning::%s not listed: %s" % (src.id, e), file=sys.stderr)
            out[src.id] = None
    return out


def read_json(path):
    """A previous catalog, or None when there is none or it does not parse (it is then rebuilt, not kept)."""
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (FileNotFoundError, ValueError):
        return None
    sources = got.get("sources") if isinstance(got, dict) else None
    if not isinstance(sources, list):
        return None
    for src in sources:
        if (not isinstance(src, dict)
                or not isinstance(src.get("id"), str) or not ID.fullmatch(src["id"])
                or not isinstance(src.get("url"), str) or not src["url"].startswith(RAW_PREFIX)
                or src["url"].count("{}") != 1
                or not isinstance(src.get("names"), list)
                or any(not isinstance(n, str) or not NAME.fullmatch(n) for n in src["names"])):
            return None
    return got


def publish(root, providers, list_all, now):
    """Writes catalog.json and catalog/<provider>.json under root; returns the exit code."""
    out = os.path.join(root, "catalog.json")
    out_dir = os.path.join(root, CATALOG_DIR)
    old = read_json(out)
    old_files = {p.id: read_json(os.path.join(out_dir, p.id + ".json")) for p in providers}
    main_cat, files, stale = build_all(list_all(SOURCES + [s for p in providers for s in p.sources]), now,
                                       providers, old, old_files)
    for sid in stale:
        print("::warning::%s listing missing or too small, previous names kept" % sid, file=sys.stderr)
    if {s["id"] for s in main_cat["sources"]} != set(BUILTIN_NAMES):
        print("missing a built-in source; catalog kept", file=sys.stderr)
        return 1
    bodies = {out: (old, main_cat)}
    bodies.update({os.path.join(out_dir, pid + ".json"): (old_files.get(pid), c) for pid, c in files.items()})
    for path, (_, cat) in bodies.items():
        size = len(encode(cat).encode())
        if size > MAX_CATALOG_BYTES:
            print("%s is %d bytes, over %d; catalog kept" % (path, size, MAX_CATALOG_BYTES), file=sys.stderr)
            return 1
    gone = [os.path.join(out_dir, f) for f in (sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else [])
            if f.endswith(".json") and f[:-5] not in files]
    written = [path for path, (was, cat) in bodies.items() if changed(was, cat)]
    if not written and not gone:
        print("catalog unchanged")
        return 0
    os.makedirs(out_dir, exist_ok=True)
    # Provider files first: catalog.json never lists a provider whose file is not there.
    for path in sorted(written, key=lambda p: p == out):
        with open(path, "w") as f:
            f.write(encode(bodies[path][1]))
    for path in gone:
        os.remove(path)
    print("catalog written:", {s["id"]: len(s["names"]) for c in [main_cat, *files.values()] for s in c["sources"]})
    return 0


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return publish(root, load_providers(), lambda sources: list_sources(root, sources), now)


if __name__ == "__main__":
    sys.exit(main())
