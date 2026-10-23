import unittest

from scripts.build_catalog import build, changed, enough_names, MIN_SAGER_NAMES

NOW = "2026-10-22T19:00:00Z"
SAGER = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-{}.srs"
OWN = "https://raw.githubusercontent.com/hoaxisr/rulesets/master/srs/{}.srs"


class BuildTest(unittest.TestCase):
    def test_sources_names_urls_and_order(self):
        # Catches: wrong prefix stripping, source order, or URL templates.
        got = build(["geosite-youtube.srs", "geosite-youtube@cn.srs"], ["discord-full.srs", "claude.srs"], NOW)
        self.assertEqual(got, {
            "generated": NOW,
            "sources": [
                {"id": "sagernet", "url": SAGER, "names": ["youtube", "youtube@cn"]},
                {"id": "hoaxisr", "url": OWN, "names": ["claude", "discord-full"]},
            ],
        })

    def test_skips_non_matching_paths(self):
        # Catches: emitting files that are not geosite-*.srs.
        got = build(["README.md", "geosite-x.json", "geosite-.srs", "geosite-ok.srs"], ["notes.txt"], NOW)
        self.assertEqual(got["sources"][0]["names"], ["ok"])
        self.assertEqual(got["sources"][1]["names"], [])

    def test_skips_invalid_names(self):
        # Catches: emitting names outside the allowed charset or length.
        got = build(["geosite-a b.srs", "geosite-a/b.srs", "geosite-" + "x" * 129 + ".srs", "geosite-" + "x" * 128 + ".srs"], ["bad name.srs", "é.srs"], NOW)
        self.assertEqual(got["sources"][0]["names"], ["x" * 128])
        self.assertEqual(got["sources"][1]["names"], [])


class ChangedTest(unittest.TestCase):
    def base(self):
        return build(["geosite-a.srs"], ["b.srs"], NOW)

    def test_only_generated_differs(self):
        # Catches: committing every run because the timestamp moved.
        new = build(["geosite-a.srs"], ["b.srs"], "2026-10-23T00:00:00Z")
        self.assertFalse(changed(self.base(), new))

    def test_name_added(self):
        # Catches: missing a new rule-set.
        new = build(["geosite-a.srs", "geosite-c.srs"], ["b.srs"], NOW)
        self.assertTrue(changed(self.base(), new))

    def test_no_old(self):
        # Catches: never writing the first file.
        self.assertTrue(changed(None, self.base()))


class FloorTest(unittest.TestCase):
    def test_floor_boundary(self):
        # Catches: an empty or truncated sagernet listing replacing the published index.
        self.assertEqual(MIN_SAGER_NAMES, 1000)
        self.assertFalse(enough_names(["geosite-a%d.srs" % i for i in range(999)]))
        self.assertTrue(enough_names(["geosite-a%d.srs" % i for i in range(1000)]))


if __name__ == "__main__":
    unittest.main()
