# Rule-set catalog sources

FIRC searches this catalog when a list is added to a group. The catalog lists names only. A router
downloads just the lists its owner picks, straight from their URLs, and refreshes them on the list's
interval like any other subscription.

## Files

- `catalog.json` — what every router fetches:
  - the built-in sources, `sagernet` and `hoaxisr`;
  - `providers`, the id and display name of every provider.

  FIRC versions that predate `providers` ignore it and see the same catalog as before.
- `catalog/<provider>.json` — one optional provider's sources, in the same format (`generated`, `sources`).
  - A router fetches it only once its owner turns that provider on.
  - Every source id in it is the provider id, or the provider id and a dash (`loyalsoldier-geoip`).

| id | What | URL template | Names from |
|---|---|---|---|
| `sagernet` | GeoSite: v2fly domain-list-community compiled by SagerNet/sing-geosite | `SagerNet/sing-geosite/rule-set/geosite-{}.srs` | that branch |
| `hoaxisr` | this repository's own rule-sets | `hoaxisr/rulesets/master/srs/{}.srs` | `srs/` |

All templates start with `https://raw.githubusercontent.com/`. A name in two sources is two separate
lists; the WebUI tells them apart by the source id badge.

## Adding a provider

Add `scripts/providers/<id>.json`, plus `scripts/providers/<id>.md` with its notes and license:

```json
{
  "name": "Display name",
  "sources": [
    {
      "id": "<id>-geoip",
      "url": "https://raw.githubusercontent.com/<owner>/<repo>/<ref>/text/{}.txt",
      "tree": "<owner>/<repo>@<ref>",
      "path": "text/([^/]+)\\.txt",
      "floor": 200,
      "examples": {"text/ru.txt": "ru", "srs/ru.srs": null}
    }
  ]
}
```

Each field of a source:
- `tree` is listed through one GitHub Trees API call.
- `path` captures the name from each file path.
- `floor` is the fewest names a listing may have before it is taken for a broken one.
- `examples` are paths the pattern must turn into those names (or skip, for `null`); the tests check them.

A file the router could not fetch (empty, or over FIRC's 8 MiB list cap) is left out. Nothing else is
needed: `build_catalog.py` picks the file up and writes `catalog/<id>.json`.

## Updates and failures

`Build rule-set catalog` (`catalog.yml`) lists every source again, daily and after the workflows that
change rule-sets.
- A source that cannot be listed, or comes back with fewer names than its floor, keeps its previous names. Other sources and providers are not affected.
- A provider with no source at all is left out of `providers` and gets no file.
- Provider files are written before `catalog.json`, in the same commit.
- A file over 512 KiB (half of FIRC's 1 MiB cap) is not written, and the previous files stay.

A tag that upstream deletes disappears from the catalog. A router subscribed to it keeps its last rules
and reports the failed refresh.

## Licenses

- v2fly/domain-list-community (behind `sagernet`) — MIT.
- Each optional provider's license and attribution are in `scripts/providers/<id>.md`.
