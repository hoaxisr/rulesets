import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from scripts import build_catalog as bc
from scripts.build_catalog import (
    MAX_CATALOG_BYTES, MAX_LIST_BYTES, MIN_SAGER_NAMES, SOURCES, build, changed, encode, enough_names,
)

NOW = "2026-10-22T19:00:00Z"
SAGER = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-{}.srs"
OWN = "https://raw.githubusercontent.com/hoaxisr/rulesets/master/srs/{}.srs"

# How each source's files are named in its listing; filler clears a source's floor so tests see their own names.
LAYOUT = {
    "sagernet": "geosite-%s.srs",
    "hoaxisr": "%s.srs",
}
FILL = "zz-fill"


def listings(**paths):
    """Every source listed with filler past its floor, plus paths keyed by source id (- written as _)."""
    out = {}
    for s in SOURCES:
        given = paths.get(s.id.replace("-", "_"), [])
        out[s.id] = list(given) + [LAYOUT[s.id] % ("%s%d" % (FILL, i)) for i in range(s.floor)]
    return out


def by_id(catalog):
    return {s["id"]: s for s in catalog["sources"]}


def real(names):
    return [n for n in names if not n.startswith(FILL)]


class BuildTest(unittest.TestCase):
    def test_sources_ids_templates_and_order(self):
        # Catches: sagernet/hoaxisr ids, templates or order changing under existing subscriptions.
        got, stale = build(listings(sagernet=["geosite-youtube.srs", "geosite-youtube@cn.srs"],
                                    hoaxisr=["discord-full.srs", "claude.srs"]), NOW)
        self.assertEqual(stale, [])
        self.assertEqual(got["generated"], NOW)
        self.assertEqual([(s["id"], s["url"]) for s in got["sources"]], [
            ("sagernet", SAGER), ("hoaxisr", OWN),
        ])
        self.assertEqual(real(got["sources"][0]["names"]), ["youtube", "youtube@cn"])
        self.assertEqual(got["sources"][1]["names"], ["claude", "discord-full"])

    def test_same_name_in_every_source_stays_apart(self):
        # Catches: one provider's tag shadowing another's, or a GeoSite tag merged with a GeoIP one.
        got, _ = build(listings(**{k.replace("-", "_"): [v % "google"] for k, v in LAYOUT.items()}), NOW)
        urls = [s["url"].replace("{}", "google") for s in got["sources"] if "google" in s["names"]]
        self.assertEqual(len(urls), len(SOURCES))
        self.assertEqual(len(set(urls)), len(SOURCES))

    def test_skips_non_matching_paths(self):
        # Catches: emitting files of another kind or directory.
        got, _ = build(listings(sagernet=["README.md", "geosite-x.json", "geosite-.srs", "geosite-ok.srs"],
                                hoaxisr=["notes.txt"]), NOW)
        ids = by_id(got)
        self.assertEqual(real(ids["sagernet"]["names"]), ["ok"])
        self.assertEqual(ids["hoaxisr"]["names"], [])

    def test_skips_invalid_names(self):
        # Catches: emitting names outside FIRC's charset or length, or refusing its special characters.
        got, _ = build(listings(sagernet=["geosite-a b.srs", "geosite-a/b.srs", "geosite-" + "x" * 129 + ".srs",
                                          "geosite-" + "x" * 128 + ".srs", "geosite-geolocation-!cn@!cn.srs",
                                          "geosite-a_b.c-d.srs"],
                                hoaxisr=["bad name.srs", "é.srs"]), NOW)
        ids = by_id(got)
        self.assertEqual(real(ids["sagernet"]["names"]), ["a_b.c-d", "geolocation-!cn@!cn", "x" * 128])
        self.assertEqual(ids["hoaxisr"]["names"], [])

    def test_skips_files_firc_cannot_fetch(self):
        # Catches: listing an empty file, or one over FIRC's 8 MiB list cap.
        got, _ = build(listings(sagernet=[("geosite-empty.srs", 0), ("geosite-huge.srs", MAX_LIST_BYTES + 1),
                                          ("geosite-edge.srs", MAX_LIST_BYTES), ("geosite-ok.srs", 10)]), NOW)
        self.assertEqual(real(by_id(got)["sagernet"]["names"]), ["edge", "ok"])

    def test_order_of_listing_does_not_matter(self):
        # Catches: output depending on the order the API returns entries in.
        paths = ["geosite-%s.srs" % n for n in ("us", "ru", "cn", "private")]
        a, _ = build(listings(sagernet=paths), NOW)
        b, _ = build(listings(sagernet=list(reversed(paths))), NOW)
        self.assertEqual(encode(a), encode(b))


class FallbackTest(unittest.TestCase):
    def old(self):
        return build(listings(**{k.replace("-", "_"): [v % "old"] for k, v in LAYOUT.items()}), NOW)[0]

    def test_failed_listing_keeps_previous_names(self):
        # Catches: a network error or truncated tree wiping one provider out of the published index.
        old = self.old()
        ls = listings(sagernet=["geosite-old.srs", "geosite-new.srs"])
        ls["hoaxisr"] = None
        got, stale = build(ls, NOW, old)
        self.assertEqual(stale, ["hoaxisr"])
        self.assertEqual(by_id(got)["hoaxisr"], by_id(old)["hoaxisr"])
        self.assertIn("new", by_id(got)["sagernet"]["names"])

    def test_short_listing_keeps_previous_names(self):
        # Catches: an emptied or half-published upstream replacing a good list of names.
        old = self.old()
        ls = listings()
        ls["sagernet"] = ["geosite-a%d.srs" % i for i in range(MIN_SAGER_NAMES - 1)]
        got, stale = build(ls, NOW, old)
        self.assertEqual(stale, ["sagernet"])
        self.assertEqual(by_id(got)["sagernet"], by_id(old)["sagernet"])

    def test_source_without_history_is_left_out(self):
        # Catches: publishing an empty source that could not be listed and was never published before.
        old = self.old()
        old["sources"] = [s for s in old["sources"] if s["id"] != "hoaxisr"]
        ls = listings()
        ls["hoaxisr"] = None
        got, stale = build(ls, NOW, old)
        self.assertEqual(stale, ["hoaxisr"])
        self.assertNotIn("hoaxisr", by_id(got))

    def test_previous_entry_is_matched_by_url_too(self):
        # Catches: carrying over names that belong to an old URL template.
        old = self.old()
        by_id(old)["sagernet"]["url"] = "https://raw.githubusercontent.com/x/y/z/{}.srs"
        ls = listings()
        ls["sagernet"] = None
        got, _ = build(ls, NOW, old)
        self.assertNotIn("sagernet", by_id(got))


class FetchTreeTest(unittest.TestCase):
    def reply(self, body):
        r = mock.MagicMock()
        r.__enter__.return_value = r
        r.read.return_value = json.dumps(body).encode()
        return r

    def test_blobs_with_sizes(self):
        # Catches: listing directories, or losing the sizes the 8 MiB filter needs.
        body = {"truncated": False, "tree": [{"type": "blob", "path": "a.srs", "size": 3},
                                             {"type": "tree", "path": "d"}]}
        with mock.patch.object(bc.urllib.request, "urlopen", return_value=self.reply(body)):
            self.assertEqual(bc.fetch_tree("o/r@b"), [("a.srs", 3)])

    def test_truncated_tree_is_an_error(self):
        # Catches: a partial listing taken for the whole one.
        with mock.patch.object(bc.urllib.request, "urlopen", return_value=self.reply({"truncated": True, "tree": []})):
            with self.assertRaises(ValueError):
                bc.fetch_tree("o/r@b")

    def http(self, code):
        e = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO())
        self.addCleanup(e.close)
        return e

    def test_client_error_is_not_retried(self):
        # Catches: three slow retries for a branch that does not exist yet.
        with mock.patch.object(bc.urllib.request, "urlopen", side_effect=self.http(404)) as op, \
                mock.patch.object(bc.time, "sleep") as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                bc.fetch_tree("o/r@b")
        self.assertEqual(op.call_count, 1)
        sleep.assert_not_called()

    def test_server_error_is_retried(self):
        # Catches: one 502 from the API dropping a provider for the day.
        ok = self.reply({"truncated": False, "tree": []})
        with mock.patch.object(bc.urllib.request, "urlopen", side_effect=[self.http(502), OSError("reset"), ok]) as op, \
                mock.patch.object(bc.time, "sleep"):
            self.assertEqual(bc.fetch_tree("o/r@b"), [])
        self.assertEqual(op.call_count, 3)


class ChangedTest(unittest.TestCase):
    def base(self):
        return build(listings(sagernet=["geosite-a.srs"], hoaxisr=["b.srs"]), NOW)[0]

    def test_only_generated_differs(self):
        # Catches: committing every run because the timestamp moved.
        new = build(listings(sagernet=["geosite-a.srs"], hoaxisr=["b.srs"]), "2026-10-23T00:00:00Z")[0]
        self.assertFalse(changed(self.base(), new))

    def test_name_added(self):
        # Catches: missing a new rule-set.
        new = build(listings(sagernet=["geosite-a.srs", "geosite-c.srs"], hoaxisr=["b.srs"]), NOW)[0]
        self.assertTrue(changed(self.base(), new))

    def test_name_removed(self):
        # Catches: keeping a tag upstream has deleted.
        new = build(listings(sagernet=["geosite-a.srs"]), NOW)[0]
        self.assertTrue(changed(self.base(), new))

    def test_no_old(self):
        # Catches: never writing the first file.
        self.assertTrue(changed(None, self.base()))

    def test_encoding_matches_the_committed_layout(self):
        # Catches: a reformatted catalog.json diffing every line on the first run.
        cat = self.base()
        self.assertEqual(encode(cat), json.dumps(cat, indent=2) + "\n")


class FloorTest(unittest.TestCase):
    def test_floor_boundary(self):
        # Catches: an empty or truncated sagernet listing replacing the published index.
        self.assertEqual(MIN_SAGER_NAMES, 1000)
        self.assertFalse(enough_names(["geosite-a%d.srs" % i for i in range(999)]))
        self.assertTrue(enough_names(["geosite-a%d.srs" % i for i in range(1000)]))


class SizeTest(unittest.TestCase):
    def test_catalog_fits_firc_with_room_to_spare(self):
        # Catches: the index growing past what FIRC accepts (1 MiB) at today's tag counts plus margin.
        counts = {"sagernet": 2100, "hoaxisr": 30}
        tag = lambda i: "category-something-long-%04d@!cn" % i
        got, _ = build(listings(**{k.replace("-", "_"): [LAYOUT[k] % tag(i) for i in range(n)]
                                   for k, n in counts.items()}), NOW)
        self.assertLess(len(encode(got).encode()), MAX_CATALOG_BYTES)


def provider(pid="demo", name="Demo", **over):
    src = {"id": pid + "-geoip", "url": "https://raw.githubusercontent.com/o/r/release/text/{}.txt",
           "tree": "o/r@release", "path": r"text/([^/]+)\.txt", "floor": 1,
           "examples": {"text/ru.txt": "ru", "srs/ru.srs": None}}
    src.update(over)
    return {"name": name, "sources": [src]}


class ProviderFileTest(unittest.TestCase):
    def test_a_good_file_loads(self):
        # Catches: a valid provider being refused, or its path pattern not compiled.
        p = bc.check_provider("demo", provider())
        self.assertEqual((p.id, p.name, [s.id for s in p.sources]), ("demo", "Demo", ["demo-geoip"]))
        self.assertEqual(bc.names(["text/us.txt", "text/a/b.txt"], p.sources[0].path), ["us"])

    def test_bad_files_are_refused(self):
        # Catches: a provider file that would make FIRC refuse the whole catalog, or claim another's sources.
        cases = [
            ("bad!id", provider()),  # file name is not an id
            ("sagernet", provider("sagernet")),  # a built-in id
            ("demo", {"name": "", "sources": provider()["sources"]}),
            ("demo", {"name": "x" * 33, "sources": provider()["sources"]}),
            ("demo", {"name": "Demo", "sources": []}),
            ("demo", dict(provider(), extra=1)),
            ("demo", provider(id="other-geoip")),  # another provider's prefix
            ("demo", provider(id="demox")),  # prefix without the dash
            ("demo", provider(id="demo_geoip")),  # not an id FIRC accepts
            ("demo", provider(url="https://example.com/{}.txt")),
            ("demo", provider(url="https://raw.githubusercontent.com/o/r/{}/{}.txt")),
            ("demo", provider(url="https://raw.githubusercontent.com/o/r/a.txt")),
            ("demo", provider(tree="o/r")),
            ("demo", provider(path="text/.*\\.txt")),  # captures nothing
            ("demo", provider(path="(text)/(.*)\\.txt")),  # captures twice
            ("demo", provider(path="(")),
            ("demo", provider(floor=0)),
            ("demo", provider(floor=True)),
            ("demo", provider(examples={})),
            ("demo", provider(examples={"text/ru.txt": "us"})),  # an example the pattern contradicts
            ("demo", provider(examples={"srs/ru.srs": None})),  # no positive example
        ]
        for pid, data in cases:
            with self.subTest(pid=pid, data=data):
                with self.assertRaises(ValueError):
                    bc.check_provider(pid, data)

    def test_directory_is_loaded_in_order_and_ids_are_unique(self):
        # Catches: output depending on directory order, or two providers publishing one source id.
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for pid in ("zeta", "alpha"):
            with open(os.path.join(d, pid + ".json"), "w") as f:
                json.dump(provider(pid), f)
        with open(os.path.join(d, "alpha.md"), "w") as f:
            f.write("notes are not providers")
        self.assertEqual([p.id for p in bc.load_providers(d)], ["alpha", "zeta"])
        with open(os.path.join(d, "zeta.json"), "w") as f:
            json.dump(provider("zeta", id="zeta"), f)
        with open(os.path.join(d, "zeta-geo.json"), "w") as f:
            json.dump(provider("zeta-geo", id="zeta-geo"), f)
        bc.load_providers(d)
        # zeta-geo-geoip fits both zeta- and zeta-geo-; two files claiming it must not load.
        with open(os.path.join(d, "zeta-geo.json"), "w") as f:
            json.dump(provider("zeta-geo", id="zeta-geo-geoip"), f)
        with open(os.path.join(d, "zeta.json"), "w") as f:
            json.dump(provider("zeta", id="zeta-geo-geoip"), f)
        with self.assertRaises(ValueError):
            bc.load_providers(d)

    def test_every_provider_in_this_repository_is_valid(self):
        # Catches: a committed provider file, or one of its examples, that the builder would refuse.
        for p in bc.load_providers():
            self.assertTrue(p.sources)


def demo(pid="demo", floor=1):
    return bc.check_provider(pid, provider(pid, pid.title(), floor=floor))


class BuildAllTest(unittest.TestCase):
    def test_builtins_stay_in_catalog_json_and_providers_get_their_own_file(self):
        # Catches: optional providers leaking into the file every router downloads, or old FIRC losing sources.
        ls = listings(sagernet=["geosite-a.srs"], hoaxisr=["b.srs"])
        ls["demo-geoip"] = ["text/ru.txt", "text/us.txt"]
        main, files, stale = bc.build_all(ls, NOW, [demo()])
        self.assertEqual(stale, [])
        self.assertEqual([s["id"] for s in main["sources"]], ["sagernet", "hoaxisr"])
        self.assertEqual(main["providers"], [{"id": "sagernet", "name": "SagerNet"},
                                             {"id": "hoaxisr", "name": "hoaxisr"}, {"id": "demo", "name": "Demo"}])
        self.assertEqual(files, {"demo": {"generated": NOW, "sources": [
            {"id": "demo-geoip", "url": "https://raw.githubusercontent.com/o/r/release/text/{}.txt",
             "names": ["ru", "us"]}]}})

    def test_provider_with_nothing_is_not_listed(self):
        # Catches: catalog.json naming a provider whose file was not written.
        ls = listings()
        ls["demo-geoip"] = None
        main, files, stale = bc.build_all(ls, NOW, [demo()])
        self.assertEqual(stale, ["demo-geoip"])
        self.assertEqual(files, {})
        self.assertNotIn("demo", [p["id"] for p in main["providers"]])

    def test_provider_keeps_its_previous_names_when_it_fails(self):
        # Catches: one provider's outage emptying its file or touching another provider.
        ls = listings()
        ls["demo-geoip"], ls["other-geoip"] = ["text/ru.txt"], ["text/us.txt"]
        _, before, _ = bc.build_all(ls, NOW, [demo(), demo("other")])
        ls["demo-geoip"] = None
        ls["other-geoip"] = ["text/us.txt", "text/de.txt"]
        main, files, stale = bc.build_all(ls, NOW, [demo(), demo("other")], None, before)
        self.assertEqual(stale, ["demo-geoip"])
        self.assertEqual(files["demo"]["sources"], before["demo"]["sources"])
        self.assertEqual(files["other"]["sources"][0]["names"], ["de", "us"])


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.ls = listings(sagernet=["geosite-a.srs"], hoaxisr=["b.srs"])
        self.ls["demo-geoip"] = ["text/ru.txt"]

    def run_publish(self, providers, now=NOW):
        return bc.publish(self.root, providers, lambda sources: self.ls, now)

    def read(self, *path):
        with open(os.path.join(self.root, *path)) as f:
            return json.load(f)

    def test_writes_catalog_and_provider_files(self):
        # Catches: a missing provider file, or catalog.json written with the provider list but no file.
        self.assertEqual(self.run_publish([demo()]), 0)
        self.assertEqual([p["id"] for p in self.read("catalog.json")["providers"]], ["sagernet", "hoaxisr", "demo"])
        self.assertEqual(self.read("catalog", "demo.json")["sources"][0]["names"], ["ru"])

    def test_unchanged_run_writes_nothing(self):
        # Catches: a commit every day because the timestamp moved.
        self.run_publish([demo()])
        stamp = os.path.getmtime(os.path.join(self.root, "catalog", "demo.json"))
        self.assertEqual(self.run_publish([demo()], "2030-01-01T00:00:00Z"), 0)
        self.assertEqual(self.read("catalog.json")["generated"], NOW)
        self.assertEqual(os.path.getmtime(os.path.join(self.root, "catalog", "demo.json")), stamp)

    def test_removed_provider_file_is_deleted(self):
        # Catches: a provider dropped from the repository still being served to routers.
        self.run_publish([demo()])
        self.run_publish([])
        self.assertFalse(os.path.exists(os.path.join(self.root, "catalog", "demo.json")))
        self.assertNotIn("demo", [p["id"] for p in self.read("catalog.json")["providers"]])

    def test_corrupt_previous_file_is_rebuilt(self):
        # Catches: a damaged catalog file crashing every later run.
        self.run_publish([demo()])
        with open(os.path.join(self.root, "catalog", "demo.json"), "w") as f:
            f.write("{")
        self.assertEqual(self.run_publish([demo()]), 0)
        self.assertEqual(self.read("catalog", "demo.json")["sources"][0]["names"], ["ru"])

    def test_oversized_catalog_writes_nothing(self):
        # Catches: publishing a file FIRC would refuse; the previous files stay.
        self.run_publish([demo()])
        self.ls["demo-geoip"] = ["text/%s-%s.txt" % ("x" * 100, i) for i in range(6000)]
        self.assertEqual(self.run_publish([demo()]), 1)
        self.assertEqual(self.read("catalog", "demo.json")["sources"][0]["names"], ["ru"])


if __name__ == "__main__":
    unittest.main()
