import io
import json
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


if __name__ == "__main__":
    unittest.main()
